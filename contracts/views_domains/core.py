from datetime import date

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.generic import FormView, View
from django.contrib.auth import get_user_model

from contracts.forms import UserProfileForm, RegistrationForm, LoginForm
from contracts.models import AuditLog, BackgroundJob, Case, CaseMatter, Client, Deadline, Invoice, Notification, RiskLog, TimeEntry, TrustAccount, UserProfile, Workflow, CaseSignal, ApprovalRequest, SignatureRequest, DSARRequest, Document
from contracts.middleware import log_action
from contracts.observability import db_health_snapshot, request_metrics_snapshot, scheduler_health_snapshot, evaluate_alert_policy
from contracts.tenancy import get_user_organization, scope_queryset_for_organization

User = get_user_model()


def get_or_create_profile(user):
    profile, created = UserProfile.objects.get_or_create(user=user)
    return profile


def index(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def health_check(request):
    response_format = request.GET.get('format', '').lower()
    if response_format != 'json':
        return HttpResponse('OK', content_type='text/plain')

    scheduler = scheduler_health_snapshot()
    database = db_health_snapshot()
    request_metrics = request_metrics_snapshot()
    status = 'ok'
    status_code = 200
    if scheduler.get('status') == 'stale' or database.get('status') == 'down':
        status = 'degraded'
        status_code = 503
    elif database.get('status') == 'slow':
        status = 'degraded'

    return JsonResponse(
        {
            'status': status,
            'scheduler': scheduler,
            'database': database,
            'request_metrics': request_metrics,
        },
        status=status_code,
    )


@login_required
def operations_dashboard(request):
    org = get_user_organization(request.user)
    if not org:
        messages.error(request, 'No active organization found.')
        return redirect('settings_hub')

    recent_jobs = BackgroundJob.objects.filter(organization=org).order_by('-created_at')[:12]
    job_counts = {
        'pending': BackgroundJob.objects.filter(organization=org, status=BackgroundJob.Status.PENDING).count(),
        'running': BackgroundJob.objects.filter(organization=org, status=BackgroundJob.Status.RUNNING).count(),
        'completed': BackgroundJob.objects.filter(organization=org, status=BackgroundJob.Status.COMPLETED).count(),
        'failed': BackgroundJob.objects.filter(organization=org, status=BackgroundJob.Status.FAILED).count(),
    }
    context = {
        'organization': org,
        'scheduler': scheduler_health_snapshot(),
        'database': db_health_snapshot(),
        'request_metrics': request_metrics_snapshot(),
        'alerts': evaluate_alert_policy(),
        'job_counts': job_counts,
        'recent_jobs': recent_jobs,
        'drill_state': {
            'last_run_iso': cache.get('operations_drill.last_run_iso'),
            'last_summary': cache.get('operations_drill.last_summary'),
        },
    }
    return render(request, 'contracts/operations_dashboard.html', context)


@login_required
def switch_organization(request):
    org_id = request.POST.get('organization_id')
    membership = (
        OrganizationMembership.objects
        .filter(
            user=request.user,
            is_active=True,
            organization__is_active=True,
            organization_id=org_id,
        )
        .select_related('organization')
        .first()
    )
    if membership:
        request.session['active_organization_id'] = membership.organization_id
        log_action(
            request.user,
            AuditLog.Action.UPDATE,
            'OrganizationMembership',
            object_id=membership.id,
            object_repr=str(membership),
            changes={'event': 'switch_organization', 'organization_id': membership.organization_id},
            request=request,
        )
        messages.success(request, f'Switched to {membership.organization.name}.')
    else:
        messages.error(request, 'You do not have access to that organization.')
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


class ProfileView(LoginRequiredMixin, View):
    def get(self, request):
        profile = get_or_create_profile(request.user)
        form = UserProfileForm(instance=profile, initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
        })
        return render(request, 'profile.html', {'form': form, 'profile': profile})

    def post(self, request):
        profile = get_or_create_profile(request.user)
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            request.user.first_name = form.cleaned_data.get('first_name', '')
            request.user.last_name = form.cleaned_data.get('last_name', '')
            request.user.email = form.cleaned_data.get('email', '')
            request.user.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
        return render(request, 'profile.html', {'form': form, 'profile': profile})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class SignUpView(FormView):
    form_class = RegistrationForm
    success_url = reverse_lazy('dashboard')
    template_name = 'registration/register.html'

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Exception as exc:
            logger.exception('signup_view_failed')
            return HttpResponse(f'Signup failed: {exc.__class__.__name__}: {exc}', status=500, content_type='text/plain')

    def form_valid(self, form):
        self.object = form.save()
        UserProfile.objects.get_or_create(user=self.object)

        login(
            self.request,
            self.object,
            backend='django.contrib.auth.backends.ModelBackend',
        )
        return super().form_valid(form)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(FormView):
    form_class = LoginForm
    success_url = reverse_lazy('dashboard')
    template_name = 'registration/login.html'

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Exception as exc:
            logger.exception('login_view_failed')
            return HttpResponse(f'Login failed: {exc.__class__.__name__}: {exc}', status=500, content_type='text/plain')

    def form_valid(self, form):
        user = form.cleaned_data['user']
        login(
            self.request,
            user,
            backend='django.contrib.auth.backends.ModelBackend',
        )
        if not form.cleaned_data.get('remember'):
            self.request.session.set_expiry(0)
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return super().form_valid(form)


if settings.DEBUG:
    SignUpView = method_decorator(csrf_exempt, name='dispatch')(SignUpView)
