from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from contracts.forms import DeadlineForm
from contracts.middleware import log_action
from contracts.models import Deadline
from contracts.permissions import ContractAction, can_access_contract_action
from contracts.tenancy import get_user_organization
from contracts.view_support import TenantAssignCreateMixin, TenantScopedQuerysetMixin


class DeadlineListView(LoginRequiredMixin, ListView):
    model = Deadline
    template_name = 'contracts/deadline_list.html'
    context_object_name = 'deadlines'
    paginate_by = 25

    def get_organization(self):
        if not hasattr(self.request, '_cached_organization'):
            self.request._cached_organization = get_user_organization(self.request.user)
        return self.request._cached_organization

    def get_queryset(self):
        org = self.get_organization()
        queryset = Deadline.objects.select_related('matter', 'contract', 'assigned_to').for_organization(org)
        show = self.request.GET.get('show', 'upcoming')
        if show == 'overdue':
            queryset = queryset.filter(is_completed=False, due_date__lt=date.today())
        elif show == 'completed':
            queryset = queryset.filter(is_completed=True)
        elif show != 'all':
            queryset = queryset.filter(is_completed=False, due_date__gte=date.today())
        return queryset.order_by('due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.get_organization()
        org_deadlines = Deadline.objects.for_organization(org)
        context['overdue_count'] = org_deadlines.filter(is_completed=False, due_date__lt=date.today()).count()
        context['upcoming_count'] = org_deadlines.filter(is_completed=False, due_date__gte=date.today()).count()
        context['show'] = self.request.GET.get('show', 'upcoming')
        return context


class DeadlineCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('contracts:deadline_list')

    def form_valid(self, form):
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create deadlines for this contract.')
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Deadline', self.object.id, str(self.object), request=self.request)
        return response


class DeadlineUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('contracts:deadline_list')

    def get_queryset(self):
        org = self.get_organization()
        if not org:
            return Deadline.objects.none()
        return Deadline.objects.for_organization(org)

    def dispatch(self, request, *args, **kwargs):
        deadline = self.get_object()
        if deadline.contract and not can_access_contract_action(request.user, deadline.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit this contract deadline.')
        return super().dispatch(request, *args, **kwargs)


@login_required
@require_POST
def deadline_complete(request, pk):
    if not hasattr(request, '_cached_organization'):
        request._cached_organization = get_user_organization(request.user)
    organization = request._cached_organization

    deadline_queryset = Deadline.objects.for_organization(organization)
    deadline = get_object_or_404(deadline_queryset, pk=pk)
    if deadline.contract and not can_access_contract_action(request.user, deadline.contract, ContractAction.EDIT):
        return HttpResponseForbidden('You do not have permission to complete this contract deadline.')
    deadline.is_completed = True
    deadline.completed_at = timezone.now()
    deadline.completed_by = request.user
    deadline.save()
    log_action(request.user, 'UPDATE', 'Deadline', deadline.id, str(deadline), request=request)
    messages.success(request, f'Deadline "{deadline.title}" marked as complete.')
    return redirect('contracts:deadline_list')
