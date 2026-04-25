import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import (
    ApprovalRequestForm,
    ApprovalRuleForm,
    DSARRequestForm,
    DataInventoryForm,
    LegalHoldForm,
    RetentionPolicyForm,
    SignatureRequestForm,
    SubprocessorForm,
    TransferRecordForm,
)
from contracts.models import (
    ApprovalRequest,
    ApprovalRule,
    AuditLog,
    Client,
    Contract,
    DSARRequest,
    DataInventoryRecord,
    Document,
    LegalHold,
    Matter,
    RetentionPolicy,
    SignatureRequest,
    Subprocessor,
    TransferRecord,
    Notification,
    OrganizationMembership,
)
from contracts.middleware import log_action
from contracts.tenancy import get_user_organization, scope_queryset_for_organization
from contracts.services.esign import ESignTransitionError, transition_signature_request
from contracts.view_support import (
    TenantAssignCreateMixin,
    TenantScopedFormMixin,
    TenantScopedQuerysetMixin,
    get_scoped_queryset_for_request,
    organization_user_queryset as _organization_user_queryset,
)
from contracts.permissions import can_manage_organization


class SignatureRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = SignatureRequest
    template_name = 'contracts/signature_request_list.html'
    context_object_name = 'signatures'

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(SignatureRequest.objects.select_related('contract').all(), org)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class SignatureRequestCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = SignatureRequest
    form_class = SignatureRequestForm
    template_name = 'contracts/signature_request_form.html'
    success_url = reverse_lazy('contracts:signature_request_list')
    scoped_form_fields = {'contract': Contract, 'document': Document}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class SignatureRequestDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = SignatureRequest
    template_name = 'contracts/signature_request_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['available_transitions'] = self.object.available_transitions_for_actor(self.request.user)
        context['needs_follow_up'] = self.object.is_follow_up_due()
        context['follow_up_threshold_days'] = 7
        context['routing_blockers'] = self.object.routing_blockers()
        context['routing_ready'] = self.object.is_routing_ready()
        context['can_send_reminder'] = (
            self.object.created_by_id == self.request.user.id
            or can_manage_organization(self.request.user, self.object.organization)
        )
        return context


def _signature_reminder_recipients(signature_request):
    recipients = set()
    if signature_request.created_by_id:
        recipients.add(signature_request.created_by)
    organization = signature_request.organization
    if organization:
        for membership in OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role__in=[OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN],
        ).select_related('user'):
            recipients.add(membership.user)
    return recipients


@login_required
@require_POST
def signature_request_send_reminder(request, pk):
    org = get_user_organization(request.user)
    queryset = scope_queryset_for_organization(SignatureRequest.objects.select_related('contract', 'document', 'created_by'), org)
    signature_request = get_object_or_404(queryset, pk=pk)
    if not (signature_request.created_by_id == request.user.id or can_manage_organization(request.user, signature_request.organization)):
        return HttpResponseForbidden('You are not authorized to send reminders for this signature request.')

    if signature_request.status not in {SignatureRequest.Status.PENDING, SignatureRequest.Status.SENT, SignatureRequest.Status.VIEWED}:
        messages.info(request, 'This signature request is already closed.')
        return redirect(reverse('contracts:signature_request_detail', kwargs={'pk': signature_request.pk}))

    recipients = _signature_reminder_recipients(signature_request)
    reminder_link = reverse('contracts:signature_request_detail', kwargs={'pk': signature_request.pk})
    reminder_title = f'Signature reminder: {signature_request.contract.title} ({signature_request.signer_name})'
    created_count = 0
    for recipient in recipients:
        exists = Notification.objects.filter(
            recipient=recipient,
            notification_type=Notification.NotificationType.SYSTEM,
            title=reminder_title,
            link=reminder_link,
            created_at__date=timezone.localdate(),
        ).exists()
        if exists:
            continue
        Notification.objects.create(
            recipient=recipient,
            notification_type=Notification.NotificationType.SYSTEM,
            title=reminder_title,
            message=(
                f'{signature_request.contract.title} is waiting on signature from '
                f'{signature_request.signer_name} ({signature_request.signer_email}).'
            ),
            link=reminder_link,
        )
        created_count += 1

    log_action(
        request.user,
        AuditLog.Action.UPDATE,
        'SignatureRequest',
        object_id=signature_request.id,
        object_repr=str(signature_request),
        changes={
            'event': 'signature_request_reminder_sent',
            'notification_count': created_count,
            'organization_id': getattr(org, 'id', None),
        },
        request=request,
    )
    messages.success(request, f'Signature reminder queued for {created_count} recipient(s).')
    return redirect(reverse('contracts:signature_request_detail', kwargs={'pk': signature_request.pk}))


class SignatureRequestUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = SignatureRequest
    form_class = SignatureRequestForm
    template_name = 'contracts/signature_request_form.html'
    success_url = reverse_lazy('contracts:signature_request_list')
    scoped_form_fields = {'contract': Contract, 'document': Document}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['actor'] = self.request.user
        return kwargs


@login_required
@require_POST
def signature_request_transition(request, pk, new_status):
    org = get_user_organization(request.user)
    queryset = scope_queryset_for_organization(SignatureRequest.objects.select_related('contract', 'document', 'created_by'), org)
    signature_request = get_object_or_404(queryset, pk=pk)
    try:
        transition_signature_request(signature_request, new_status, actor=request.user)
    except ESignTransitionError as exc:
        return HttpResponseForbidden(str(exc))

    log_action(
        request.user,
        AuditLog.Action.UPDATE,
        'SignatureRequest',
        object_id=signature_request.id,
        object_repr=str(signature_request),
        changes={
            'event': 'signature_request_transition',
            'to_status': new_status,
            'organization_id': getattr(org, 'id', None),
        },
        request=request,
    )
    messages.success(request, f'Signature request marked as {signature_request.get_status_display().lower()}.')
    return redirect(reverse('contracts:signature_request_detail', kwargs={'pk': signature_request.pk}))


class DataInventoryListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = DataInventoryRecord
    template_name = 'contracts/data_inventory_list.html'
    context_object_name = 'records'


class DataInventoryCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = DataInventoryRecord
    form_class = DataInventoryForm
    template_name = 'contracts/data_inventory_form.html'
    success_url = reverse_lazy('contracts:data_inventory_list')
    scoped_form_fields = {'client': Client}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class DataInventoryDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = DataInventoryRecord
    template_name = 'contracts/data_inventory_detail.html'


class DataInventoryUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = DataInventoryRecord
    form_class = DataInventoryForm
    template_name = 'contracts/data_inventory_form.html'
    success_url = reverse_lazy('contracts:data_inventory_list')
    scoped_form_fields = {'client': Client}


class DSARRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = DSARRequest
    template_name = 'contracts/dsar_list.html'
    context_object_name = 'requests'

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(DSARRequest.objects.all(), org).order_by('-received_date')
        status = self.request.GET.get('status')
        rtype = self.request.GET.get('type')
        if status:
            qs = qs.filter(status=status)
        if rtype:
            qs = qs.filter(request_type=rtype)
        return qs


class DSARRequestCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = DSARRequest
    form_class = DSARRequestForm
    template_name = 'contracts/dsar_form.html'
    success_url = reverse_lazy('contracts:dsar_list')
    scoped_form_fields = {'client': Client, 'assigned_to': _organization_user_queryset}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class DSARRequestDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = DSARRequest
    template_name = 'contracts/dsar_detail.html'


class DSARRequestUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = DSARRequest
    form_class = DSARRequestForm
    template_name = 'contracts/dsar_form.html'
    success_url = reverse_lazy('contracts:dsar_list')
    scoped_form_fields = {'client': Client, 'assigned_to': _organization_user_queryset}


class SubprocessorListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Subprocessor
    template_name = 'contracts/subprocessor_list.html'
    context_object_name = 'subprocessors'


class SubprocessorCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Subprocessor
    form_class = SubprocessorForm
    template_name = 'contracts/subprocessor_form.html'
    success_url = reverse_lazy('contracts:subprocessor_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class SubprocessorDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Subprocessor
    template_name = 'contracts/subprocessor_detail.html'


class SubprocessorUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Subprocessor
    form_class = SubprocessorForm
    template_name = 'contracts/subprocessor_form.html'
    success_url = reverse_lazy('contracts:subprocessor_list')


class TransferRecordListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = TransferRecord
    template_name = 'contracts/transfer_record_list.html'
    context_object_name = 'transfers'


class TransferRecordCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = TransferRecord
    form_class = TransferRecordForm
    template_name = 'contracts/transfer_record_form.html'
    success_url = reverse_lazy('contracts:transfer_record_list')
    scoped_form_fields = {'subprocessor': Subprocessor, 'contract': Contract}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class TransferRecordUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = TransferRecord
    form_class = TransferRecordForm
    template_name = 'contracts/transfer_record_form.html'
    success_url = reverse_lazy('contracts:transfer_record_list')
    scoped_form_fields = {'subprocessor': Subprocessor, 'contract': Contract}


class RetentionPolicyListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = RetentionPolicy
    template_name = 'contracts/retention_policy_list.html'
    context_object_name = 'policies'


class RetentionPolicyCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = RetentionPolicy
    form_class = RetentionPolicyForm
    template_name = 'contracts/retention_policy_form.html'
    success_url = reverse_lazy('contracts:retention_policy_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class RetentionPolicyUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = RetentionPolicy
    form_class = RetentionPolicyForm
    template_name = 'contracts/retention_policy_form.html'
    success_url = reverse_lazy('contracts:retention_policy_list')


class LegalHoldListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = LegalHold
    template_name = 'contracts/legal_hold_list.html'
    context_object_name = 'holds'


class LegalHoldCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = LegalHold
    form_class = LegalHoldForm
    template_name = 'contracts/legal_hold_form.html'
    success_url = reverse_lazy('contracts:legal_hold_list')
    scoped_form_fields = {
        'matter': Matter,
        'client': Client,
        'custodians': _organization_user_queryset,
    }

    def form_valid(self, form):
        form.instance.issued_by = self.request.user
        return super().form_valid(form)


class LegalHoldDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = LegalHold
    template_name = 'contracts/legal_hold_detail.html'


class LegalHoldUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = LegalHold
    form_class = LegalHoldForm
    template_name = 'contracts/legal_hold_form.html'
    success_url = reverse_lazy('contracts:legal_hold_list')
    scoped_form_fields = {
        'matter': Matter,
        'client': Client,
        'custodians': _organization_user_queryset,
    }


class ApprovalRuleListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ApprovalRule
    template_name = 'contracts/approval_rule_list.html'
    context_object_name = 'rules'


class ApprovalRuleCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ApprovalRule
    form_class = ApprovalRuleForm
    template_name = 'contracts/approval_rule_form.html'
    success_url = reverse_lazy('contracts:approval_rule_list')
    scoped_form_fields = {'specific_approver': _organization_user_queryset}


class ApprovalRuleUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ApprovalRule
    form_class = ApprovalRuleForm
    template_name = 'contracts/approval_rule_form.html'
    success_url = reverse_lazy('contracts:approval_rule_list')
    scoped_form_fields = {'specific_approver': _organization_user_queryset}


class ApprovalRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ApprovalRequest
    template_name = 'contracts/approval_request_list.html'
    context_object_name = 'approvals'

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            ApprovalRequest.objects.select_related('contract', 'assigned_to', 'delegated_to').all(),
            org,
        ).order_by('-created_at')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class ApprovalRequestCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ApprovalRequest
    form_class = ApprovalRequestForm
    template_name = 'contracts/approval_request_form.html'
    success_url = reverse_lazy('contracts:approval_request_list')
    scoped_form_fields = {'contract': Contract, 'assigned_to': _organization_user_queryset}


class ApprovalRequestUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ApprovalRequest
    form_class = ApprovalRequestForm
    template_name = 'contracts/approval_request_form.html'
    success_url = reverse_lazy('contracts:approval_request_list')
    scoped_form_fields = {'contract': Contract, 'assigned_to': _organization_user_queryset}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['actor'] = self.request.user
        return kwargs

    def form_valid(self, form):
        new_status = form.cleaned_data.get('status')
        delegated_to = form.cleaned_data.get('delegated_to')
        previous_assignee_id = self.object.assigned_to_id if self.object.pk else None
        if delegated_to:
            form.instance.assigned_to = delegated_to
            form.instance.delegated_at = timezone.now()
        if new_status in {ApprovalRequest.Status.APPROVED, ApprovalRequest.Status.REJECTED}:
            form.instance.decided_at = timezone.now()
            form.instance.decided_by = self.request.user
        elif new_status == ApprovalRequest.Status.PENDING:
            form.instance.decided_at = None
            form.instance.decided_by = None
        response = super().form_valid(form)
        if delegated_to and delegated_to.id != previous_assignee_id:
            log_action(
                self.request.user,
                AuditLog.Action.UPDATE,
                'ApprovalRequest',
                object_id=self.object.id,
                object_repr=str(self.object),
                changes={
                    'event': 'approval_request_delegated',
                    'delegated_to_id': delegated_to.id,
                },
                request=self.request,
            )
        return response


@login_required
def privacy_dashboard(request):
    data_inventory_qs = get_scoped_queryset_for_request(request, DataInventoryRecord)
    dsar_qs = get_scoped_queryset_for_request(request, DSARRequest)
    transfer_qs = get_scoped_queryset_for_request(request, TransferRecord)
    subprocessor_qs = get_scoped_queryset_for_request(request, Subprocessor)
    retention_qs = get_scoped_queryset_for_request(request, RetentionPolicy)
    legal_hold_qs = get_scoped_queryset_for_request(request, LegalHold)

    data_inventory_count = data_inventory_qs.count()
    dsar_pending = dsar_qs.filter(status__in=['RECEIVED', 'VERIFIED', 'IN_PROGRESS']).count()
    dsar_overdue = dsar_qs.filter(
        status__in=['RECEIVED', 'VERIFIED', 'IN_PROGRESS'],
        due_date__lt=date.today(),
    ).count()
    subprocessor_count = subprocessor_qs.filter(is_active=True).count()
    transfer_count = transfer_qs.filter(is_active=True).count()
    retention_count = retention_qs.filter(is_active=True).count()
    legal_hold_count = legal_hold_qs.filter(status='ACTIVE').count()
    recent_dsars = dsar_qs.order_by('-received_date')[:5]
    context = {
        'data_inventory_count': data_inventory_count,
        'dsar_pending': dsar_pending,
        'dsar_overdue': dsar_overdue,
        'subprocessor_count': subprocessor_count,
        'transfer_count': transfer_count,
        'retention_count': retention_count,
        'legal_hold_count': legal_hold_count,
        'recent_dsars': recent_dsars,
    }
    return render(request, 'contracts/privacy_dashboard.html', context)


@login_required
def privacy_evidence_export(request):
    org = get_user_organization(request.user)
    if org is None:
        return HttpResponseForbidden('No active organization found.')
    if not can_manage_organization(request.user, org):
        return HttpResponseForbidden('Only organization owners/admins can export privacy evidence.')

    data_inventory_qs = get_scoped_queryset_for_request(request, DataInventoryRecord)
    dsar_qs = get_scoped_queryset_for_request(request, DSARRequest)
    transfer_qs = get_scoped_queryset_for_request(request, TransferRecord)
    subprocessor_qs = get_scoped_queryset_for_request(request, Subprocessor)
    retention_qs = get_scoped_queryset_for_request(request, RetentionPolicy)
    legal_hold_qs = get_scoped_queryset_for_request(request, LegalHold)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="privacy-evidence-{org.slug}-{date.today().isoformat()}.csv"'
    writer = csv.writer(response)
    writer.writerow(['category', 'metric', 'value'])
    writer.writerow(['summary', 'data_inventory_count', data_inventory_qs.count()])
    writer.writerow(['summary', 'dsar_pending', dsar_qs.filter(status__in=['RECEIVED', 'VERIFIED', 'IN_PROGRESS']).count()])
    writer.writerow(['summary', 'dsar_overdue', dsar_qs.filter(status__in=['RECEIVED', 'VERIFIED', 'IN_PROGRESS'], due_date__lt=date.today()).count()])
    writer.writerow(['summary', 'subprocessor_count', subprocessor_qs.filter(is_active=True).count()])
    writer.writerow(['summary', 'transfer_count', transfer_qs.filter(is_active=True).count()])
    writer.writerow(['summary', 'retention_count', retention_qs.filter(is_active=True).count()])
    writer.writerow(['summary', 'legal_hold_count', legal_hold_qs.filter(status='ACTIVE').count()])
    for log in AuditLog.objects.filter(changes__organization_id=org.id).order_by('-timestamp')[:20]:
        writer.writerow(['audit_log', log.timestamp.isoformat(), f'{log.model_name}:{log.action}:{(log.changes or {}).get("event", "")}'])
    return response
