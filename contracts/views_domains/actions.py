import csv

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView
from django.core.mail import send_mail

from contracts.forms import BudgetExpenseForm, ChecklistItemForm, DueDiligenceRiskForm, DueDiligenceTaskForm, UserProfileForm
from contracts.models import AuditLog, BudgetExpense, ChecklistItem, Contract, DueDiligenceRisk, DueDiligenceTask, NegotiationThread, Notification, OrganizationMembership, UserProfile
from contracts.middleware import log_action
from contracts.permissions import ContractAction, can_access_contract_action, can_manage_organization
from contracts.session_security import get_organization_session_audit, revoke_organization_sessions, revoke_session_by_key
from contracts.tenancy import get_user_organization
from contracts.view_support import (
    TenantAssignCreateMixin,
    scope_budgets_for_organization as _scope_budgets_for_organization,
    scope_checklist_items_for_organization as _scope_checklist_items_for_organization,
    scope_checklists_for_organization as _scope_checklists_for_organization,
    scope_due_diligence_processes_for_organization as _scope_due_diligence_processes_for_organization,
    scope_due_diligence_tasks_for_organization as _scope_due_diligence_tasks_for_organization,
)


class ToggleChecklistItemView(LoginRequiredMixin, View):
    def post(self, request, pk):
        organization = get_user_organization(request.user)
        item = get_object_or_404(_scope_checklist_items_for_organization(organization), pk=pk)
        linked_contract = item.checklist.contract
        if linked_contract and not can_access_contract_action(request.user, linked_contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to update this contract checklist item.')
        item.is_completed = not item.is_completed
        item.completed_by = request.user if item.is_completed else None
        item.completed_at = timezone.now() if item.is_completed else None
        item.save()
        return redirect('contracts:compliance_checklist_detail', pk=item.checklist.pk)


class AddChecklistItemView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ChecklistItem
    form_class = ChecklistItemForm
    template_name = 'contracts/checklist_item_form.html'

    def form_valid(self, form):
        checklist_pk = self.kwargs.get('checklist_pk') or self.kwargs.get('pk')
        organization = get_user_organization(self.request.user)
        checklist = get_object_or_404(_scope_checklists_for_organization(organization), pk=checklist_pk)
        if checklist.contract and not can_access_contract_action(self.request.user, checklist.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to add items to this contract checklist.')
        form.instance.checklist = checklist
        return super().form_valid(form)

    def get_success_url(self):
        checklist_pk = self.kwargs.get('checklist_pk') or self.kwargs.get('pk')
        return reverse_lazy('contracts:compliance_checklist_detail', kwargs={'pk': checklist_pk})


class AddDueDiligenceItemView(LoginRequiredMixin, CreateView):
    model = DueDiligenceTask
    form_class = DueDiligenceTaskForm
    template_name = 'contracts/dd_task_form.html'

    def form_valid(self, form):
        organization = get_user_organization(self.request.user)
        process = get_object_or_404(_scope_due_diligence_processes_for_organization(organization), pk=self.kwargs['process_pk'])
        form.instance.process = process
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.kwargs['process_pk']})


class AddDueDiligenceRiskView(LoginRequiredMixin, CreateView):
    model = DueDiligenceRisk
    form_class = DueDiligenceRiskForm
    template_name = 'contracts/dd_risk_form.html'

    def form_valid(self, form):
        organization = get_user_organization(self.request.user)
        process = get_object_or_404(_scope_due_diligence_processes_for_organization(organization), pk=self.kwargs['process_pk'])
        form.instance.process = process
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.kwargs['process_pk']})


class AddExpenseView(LoginRequiredMixin, CreateView):
    model = BudgetExpense
    form_class = BudgetExpenseForm
    template_name = 'contracts/expense_form.html'

    def form_valid(self, form):
        organization = get_user_organization(self.request.user)
        budget = get_object_or_404(_scope_budgets_for_organization(organization), pk=self.kwargs['budget_pk'])
        form.instance.budget = budget
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:budget_detail', kwargs={'pk': self.kwargs['budget_pk']})


@login_required
def toggle_redesign(request):
    if request.method == 'POST':
        import os
        current_value = os.environ.get('FEATURE_REDESIGN', 'false').lower()
        new_value = 'false' if current_value == 'true' else 'true'
        os.environ['FEATURE_REDESIGN'] = new_value
        from config.feature_flags import cache
        cache.clear()
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
    return redirect('dashboard')


@login_required
def toggle_dd_item(request, pk):
    organization = get_user_organization(request.user)
    task = get_object_or_404(_scope_due_diligence_tasks_for_organization(organization), pk=pk)
    if task.status == 'COMPLETED':
        task.status = 'PENDING'
    else:
        task.status = 'COMPLETED'
    task.save()
    return redirect('contracts:due_diligence_detail', pk=task.process.pk)


def profile(request):
    profile_obj = None
    form = None
    mfa_required = False
    mfa_admin_user = False
    recovery_codes_preview = request.session.pop('mfa_recovery_codes_preview', None)
    if request.user.is_authenticated:
        profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
        organization = get_user_organization(request.user)
        mfa_required = bool(getattr(organization, 'require_mfa', False)) if organization else False
        mfa_admin_user = bool(organization and OrganizationMembership.objects.filter(
            organization=organization,
            user=request.user,
            role__in=[OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN],
            is_active=True,
        ).exists())
        if request.method == 'POST':
            action = request.POST.get('action', 'save')
            form = UserProfileForm(request.POST, instance=profile_obj)
            if action == 'send_mfa_code':
                enrollment_code = profile_obj.issue_mfa_enrollment_code()
                subject = f'{getattr(organization, "name", "CMS Aegis")} MFA verification code'
                body = (
                    f'Your MFA verification code is {enrollment_code}.\n\n'
                    'Enter this code on your profile page to confirm enrollment.'
                )
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                    recipient_list=[request.user.email],
                    fail_silently=False,
                )
                messages.success(request, 'Verification code sent to your email address.')
                return redirect('profile')
            if action == 'generate_mfa_recovery_codes':
                recovery_codes = profile_obj.issue_mfa_recovery_codes()
                request.session['mfa_recovery_codes_preview'] = recovery_codes
                log_action(
                    request.user,
                    AuditLog.Action.UPDATE,
                    'UserProfile',
                    object_id=profile_obj.id,
                    object_repr=str(profile_obj),
                    changes={'event': 'mfa_recovery_codes_generated', 'count': len(recovery_codes), 'organization_id': getattr(organization, 'id', None)},
                    request=request,
                )
                messages.success(request, 'Recovery codes generated. Save them now; they will only be shown once.')
                return redirect('profile')
            if form.is_valid():
                profile_obj = form.save(commit=False)
                request.user.first_name = form.cleaned_data.get('first_name', '')
                request.user.last_name = form.cleaned_data.get('last_name', '')
                request.user.email = form.cleaned_data.get('email', '')
                enrollment_code = (form.cleaned_data.get('mfa_enrollment_code') or '').strip()
                recovery_code = (form.cleaned_data.get('mfa_recovery_code') or '').strip()
                enable_mfa = bool(form.cleaned_data.get('mfa_enabled'))
                if enable_mfa:
                    already_enrolled = bool(profile_obj.mfa_enabled and profile_obj.mfa_verified_at)
                    if recovery_code and profile_obj.verify_mfa_recovery_code(recovery_code):
                        profile_obj.mfa_enabled = True
                        profile_obj.mfa_verified_at = timezone.now()
                        profile_obj.save()
                        request.user.save()
                        log_action(
                            request.user,
                            AuditLog.Action.UPDATE,
                            'UserProfile',
                            object_id=profile_obj.id,
                            object_repr=str(profile_obj),
                            changes={'event': 'mfa_recovery_code_used', 'organization_id': getattr(organization, 'id', None)},
                            request=request,
                        )
                        messages.success(request, 'Recovery code accepted and MFA enrollment refreshed.')
                        return redirect('profile')
                    if already_enrolled and not enrollment_code:
                        profile_obj.save()
                        request.user.save()
                        messages.success(request, 'Profile updated successfully.')
                        return redirect('profile')
                    if not profile_obj.verify_mfa_enrollment_code(enrollment_code):
                        form.add_error('mfa_enrollment_code', 'Enter the 6-digit verification code sent to your email.')
                    else:
                        request.user.save()
                        log_action(
                            request.user,
                            AuditLog.Action.UPDATE,
                            'UserProfile',
                            object_id=profile_obj.id,
                            object_repr=str(profile_obj),
                            changes={'event': 'mfa_enrolled', 'organization_id': getattr(organization, 'id', None)},
                            request=request,
                        )
                        messages.success(request, 'Profile updated successfully and MFA enrolled.')
                        return redirect('profile')
                else:
                    profile_obj.mfa_enabled = False
                    profile_obj.mfa_verified_at = None
                    profile_obj.mfa_enrollment_code_hash = ''
                    profile_obj.mfa_enrollment_code_expires_at = None
                    profile_obj.mfa_enrollment_code_sent_at = None
                    profile_obj.mfa_recovery_code_hashes = []
                    profile_obj.save()
                    request.user.save()
                    log_action(
                        request.user,
                        AuditLog.Action.UPDATE,
                        'UserProfile',
                        object_id=profile_obj.id,
                        object_repr=str(profile_obj),
                        changes={'event': 'mfa_disabled', 'organization_id': getattr(organization, 'id', None)},
                        request=request,
                    )
                    messages.success(request, 'Profile updated successfully.')
                    return redirect('profile')
        else:
            form = UserProfileForm(instance=profile_obj)
    return render(request, 'profile.html', {'form': form, 'profile': profile_obj, 'mfa_required': mfa_required, 'mfa_admin_user': mfa_admin_user, 'recovery_codes_preview': recovery_codes_preview})


@login_required
def identity_telemetry_dashboard(request):
    organization = get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('settings_hub')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can view identity telemetry.')

    recent_logs = (
        AuditLog.objects
        .filter(changes__organization_id=organization.id)
        .order_by('-timestamp')[:25]
    )
    telemetry_events = [
        {
            'key': 'mfa_enrolled',
            'label': 'MFA enrolled',
            'value': AuditLog.objects.filter(changes__organization_id=organization.id, changes__event='mfa_enrolled').count(),
        },
        {
            'key': 'mfa_disabled',
            'label': 'MFA disabled',
            'value': AuditLog.objects.filter(changes__organization_id=organization.id, changes__event='mfa_disabled').count(),
        },
        {
            'key': 'mfa_recovery_codes_generated',
            'label': 'Recovery codes generated',
            'value': AuditLog.objects.filter(changes__organization_id=organization.id, changes__event='mfa_recovery_codes_generated').count(),
        },
        {
            'key': 'saml_login_succeeded',
            'label': 'SAML login succeeded',
            'value': AuditLog.objects.filter(changes__organization_id=organization.id, changes__event='saml_login_succeeded').count(),
        },
        {
            'key': 'saml_login_failed',
            'label': 'SAML login failed',
            'value': AuditLog.objects.filter(changes__organization_id=organization.id, changes__event='saml_login_failed').count(),
        },
        {
            'key': 'scim_user_provisioned',
            'label': 'SCIM user provisioned',
            'value': AuditLog.objects.filter(changes__organization_id=organization.id, changes__event='scim_user_provisioned').count(),
        },
        {
            'key': 'scim_user_deprovisioned',
            'label': 'SCIM user deprovisioned',
            'value': AuditLog.objects.filter(changes__organization_id=organization.id, changes__event='scim_user_deprovisioned').count(),
        },
    ]
    recovery_code_counts = (
        UserProfile.objects
        .filter(user__organization_memberships__organization=organization, user__organization_memberships__is_active=True)
        .select_related('user')
    )
    return render(request, 'contracts/identity_telemetry_dashboard.html', {
        'organization': organization,
        'recent_logs': recent_logs,
        'telemetry_events': telemetry_events,
        'recovery_code_counts': recovery_code_counts,
    })


@login_required
def settings_hub(request):
    return render(request, 'settings_hub.html')


@login_required
def organization_security_settings(request):
    organization = get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('settings_hub')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can manage organization security settings.')

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        if action == 'revoke_sessions':
            affected_users = revoke_organization_sessions(organization)
            log_action(
                request.user,
                AuditLog.Action.UPDATE,
                'Organization',
                object_id=organization.id,
                object_repr=organization.name,
                changes={
                    'event': 'organization_sessions_revoked',
                    'affected_users': len(affected_users),
                },
                request=request,
            )
            messages.success(request, f'Revoked sessions for {len(affected_users)} active organization members.')
            return redirect('organization_security_settings')

        enable_mfa = request.POST.get('require_mfa') == 'on'
        session_timeout_raw = (request.POST.get('session_idle_timeout_minutes') or '').strip()
        try:
            session_timeout_minutes = int(session_timeout_raw)
        except (TypeError, ValueError):
            session_timeout_minutes = None
        if session_timeout_minutes is not None and session_timeout_minutes < 5:
            messages.error(request, 'Session idle timeout must be at least 5 minutes.')
            return redirect('organization_security_settings')

        changes = {}
        if organization.require_mfa != enable_mfa:
            organization.require_mfa = enable_mfa
            changes['require_mfa'] = enable_mfa
        if organization.session_idle_timeout_minutes != session_timeout_minutes and session_timeout_minutes is not None:
            organization.session_idle_timeout_minutes = session_timeout_minutes
            changes['session_idle_timeout_minutes'] = session_timeout_minutes

        if changes:
            organization.save(update_fields=['require_mfa', 'session_idle_timeout_minutes', 'updated_at'])
            log_action(
                request.user,
                AuditLog.Action.UPDATE,
                'Organization',
                object_id=organization.id,
                object_repr=organization.name,
                changes={'event': 'organization_security_policy_updated', **changes},
                request=request,
            )
            messages.success(request, 'Organization security settings updated.')
        else:
            messages.info(request, 'Organization security settings are already set to those values.')
        return redirect('organization_security_settings')

    return render(request, 'contracts/organization_security_settings.html', {
        'organization': organization,
        'member_count': OrganizationMembership.objects.filter(organization=organization, is_active=True).count(),
    })


@login_required
def organization_security_export(request):
    organization = get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('settings_hub')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can export organization security data.')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="organization-security-{organization.slug}.csv"'

    writer = csv.writer(response)
    writer.writerow(['organization', organization.name])
    writer.writerow(['require_mfa', organization.require_mfa])
    writer.writerow(['session_idle_timeout_minutes', organization.session_idle_timeout_minutes])
    writer.writerow([])
    writer.writerow(['username', 'email', 'role', 'mfa_enabled', 'mfa_verified_at', 'session_revocation_counter'])

    for membership in OrganizationMembership.objects.filter(organization=organization, is_active=True).select_related('user'):
        profile, _ = UserProfile.objects.get_or_create(user=membership.user)
        writer.writerow([
            membership.user.username,
            membership.user.email,
            membership.role,
            profile.mfa_enabled,
            profile.mfa_verified_at.isoformat() if profile.mfa_verified_at else '',
            profile.session_revocation_counter,
        ])

    return response


@login_required
def organization_session_audit(request):
    organization = get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('settings_hub')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can view session audit data.')

    if request.method == 'POST':
        action = request.POST.get('action', 'revoke_session')
        if action == 'revoke_session':
            session_key = (request.POST.get('session_key') or '').strip()
            if session_key and revoke_session_by_key(session_key):
                log_action(
                    request.user,
                    AuditLog.Action.UPDATE,
                    'Session',
                    object_repr=session_key,
                    changes={
                        'organization_id': organization.id,
                        'event': 'organization_session_revoked',
                        'session_key': session_key,
                    },
                    request=request,
                )
                messages.success(request, 'Session revoked.')
            else:
                messages.error(request, 'Unable to revoke that session.')
            return redirect('organization_session_audit')

    return render(request, 'contracts/organization_session_audit.html', {
        'organization': organization,
        'sessions': get_organization_session_audit(organization),
    })


@login_required
def organization_session_audit_export(request):
    organization = get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('settings_hub')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can export session audit data.')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="organization-sessions-{organization.slug}.csv"'
    writer = csv.writer(response)
    writer.writerow(['organization', organization.name])
    writer.writerow(['session_key', 'username', 'email', 'role', 'last_activity_at', 'expire_date', 'is_expired'])
    for session_info in get_organization_session_audit(organization):
        writer.writerow([
            session_info['session_key'],
            session_info['username'],
            session_info['email'],
            session_info['role'],
            session_info['last_activity_at'] or '',
            session_info['expire_date'].isoformat() if session_info['expire_date'] else '',
            session_info['is_expired'],
        ])
    return response


class AddNegotiationNoteView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = NegotiationThread
    fields = ['title', 'content']
    template_name = 'contracts/negotiation_note_form.html'

    def form_valid(self, form):
        organization = get_user_organization(self.request.user)
        contract = get_object_or_404(
            Contract.objects.filter(organization=organization),
            id=self.kwargs['pk'],
        )
        if not can_access_contract_action(self.request.user, contract, ContractAction.COMMENT):
            return HttpResponseForbidden('You do not have permission to comment on this contract.')
        form.instance.contract = contract
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        mentioned_users = []
        if form.instance.content:
            import re

            mention_candidates = {m.lower() for m in re.findall(r'@([A-Za-z0-9_.-]{3,150})', form.instance.content)}
            if mention_candidates and contract.organization:
                memberships = (
                    OrganizationMembership.objects
                    .filter(organization=contract.organization, is_active=True)
                    .select_related('user')
                )
                seen_user_ids = set()
                for membership in memberships:
                    username = (membership.user.username or '').lower()
                    if username in mention_candidates and membership.user_id != self.request.user.id and membership.user_id not in seen_user_ids:
                        mentioned_users.append(membership.user)
                        seen_user_ids.add(membership.user_id)

        for user in mentioned_users:
            Notification.objects.create(
                recipient=user,
                notification_type=Notification.NotificationType.CONTRACT,
                title=f'Mentioned in contract note: {contract.title}',
                message=(
                    f'{self.request.user.get_full_name() or self.request.user.username} '
                    f'mentioned you in note "{form.instance.title}".'
                ),
                link=reverse('contracts:contract_detail', kwargs={'pk': contract.id}),
            )

        log_action(
            self.request.user,
            AuditLog.Action.CREATE,
            'NegotiationThread',
            object_id=self.object.id,
            object_repr=str(self.object),
            changes={
                'organization_id': contract.organization_id,
                'event': 'negotiation_note_created',
                'mentions_count': len(mentioned_users),
            },
            request=self.request,
        )
        return response

    def get_success_url(self):
        return reverse_lazy('contracts:contract_detail', kwargs={'pk': self.kwargs['pk']})
