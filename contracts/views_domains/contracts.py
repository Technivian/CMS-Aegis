from datetime import date, timedelta
from decimal import Decimal
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import ContractForm, UserProfileForm
from contracts.middleware import log_action
from contracts.models import (
    AuditLog,
    Budget,
    Case,
    CaseMatter,
    Client,
    Contract,
    Document,
    Invoice,
    Matter,
    NegotiationThread,
    Notification,
    Organization,
    OrganizationMembership,
    RiskLog,
    SignatureRequest,
    TimeEntry,
    TrustAccount,
    UserProfile,
    Workflow,
    CaseSignal,
    Deadline,
    DSARRequest,
    ApprovalRequest,
)
from contracts.permissions import ContractAction, can_access_contract_action, can_manage_organization
from contracts.tenancy import get_user_organization, scope_queryset_for_organization, set_organization_on_instance
from contracts.view_support import TenantAssignCreateMixin, TenantScopedQuerysetMixin
from contracts.services.contract_lifecycle import build_contract_audit_changes
from contracts.services.ai_policy import evaluate_prompt
from contracts.services.ai_actions import build_action_plan, execute_action_plan
from config.feature_flags import is_feature_redesign_enabled

from .contract_helpers import _build_contract_ai_response


class ContractListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/contract_list.html'
    context_object_name = 'contracts'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        queryset = scope_queryset_for_organization(Case.objects.select_related('client', 'matter', 'created_by'), org)
        query = self.request.GET.get('q')
        status = self.request.GET.get('status')
        contract_type = self.request.GET.get('type')
        sort = self.request.GET.get('sort', '-created_at')
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(counterparty__icontains=query))
        if status:
            queryset = queryset.filter(status=status)
        if contract_type:
            queryset = queryset.filter(contract_type=contract_type)

        allowed_sort_fields = {'title', '-title', 'status', '-status', 'end_date', '-end_date', 'created_at', '-created_at', 'value', '-value'}
        if sort not in allowed_sort_fields:
            sort = '-created_at'
        return queryset.order_by(sort)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        today = date.today()
        thirty_days_from_today = today + timedelta(days=30)
        tenant_cases = scope_queryset_for_organization(Case.objects.all(), org)
        case_stats = tenant_cases.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
            expiring_soon=Count('id', filter=Q(status='ACTIVE', end_date__lte=thirty_days_from_today, end_date__gte=today)),
        )
        expiring_ids_qs = tenant_cases.filter(
            status='ACTIVE',
            end_date__lte=thirty_days_from_today,
            end_date__gte=today,
        ).values_list('id', flat=True)

        context['FEATURE_REDESIGN'] = is_feature_redesign_enabled()
        context['search_query'] = self.request.GET.get('q', '')
        context['sort'] = self.request.GET.get('sort', '-created_at')
        context['status_tabs'] = [('All', ''), ('Active', 'ACTIVE'), ('Draft', 'DRAFT'), ('Pending', 'PENDING'), ('Expired', 'EXPIRED')]
        context['total_cases'] = case_stats['total'] or 0
        context['active_cases'] = case_stats['active'] or 0
        context['expiring_case_count'] = case_stats['expiring_soon'] or 0
        context['expiring_contract_ids'] = set(expiring_ids_qs)
        context['cases'] = context['object_list']
        context['total_contracts'] = context['total_cases']
        context['active_contracts'] = context['active_cases']
        context['expiring_soon'] = context['expiring_case_count']

        if context['FEATURE_REDESIGN']:
            case_payload = []
            for case_record in context['object_list']:
                case_payload.append({
                    'id': case_record.id,
                    'title': case_record.title,
                    'status': case_record.status,
                    'status_display': case_record.get_status_display(),
                    'contract_type': case_record.get_contract_type_display(),
                    'start_date': case_record.start_date.strftime('%b %d, %Y') if case_record.start_date else None,
                    'end_date': case_record.end_date.strftime('%b %d, %Y') if case_record.end_date else None,
                    'value': float(case_record.value) if case_record.value else None,
                    'counterparty': case_record.counterparty or '',
                    'client': case_record.client.name if case_record.client else '',
                    'owner': case_record.created_by.get_full_name() if case_record.created_by else 'System',
                    'updated_at': case_record.updated_at.strftime('%b %d, %Y'),
                })
            context['cases_json'] = json.dumps(case_payload)
            context['contracts_json'] = context['cases_json']
        return context


class ContractDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Contract
    template_name = 'contracts/contract_detail.html'
    context_object_name = 'contract'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Contract.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        case_record = self.object
        ctx['case'] = case_record
        ctx['case_record'] = case_record
        ctx['documents'] = case_record.documents.all()[:10]
        ctx['case_documents'] = ctx['documents']
        ctx['deadlines'] = case_record.deadlines.filter(is_completed=False)[:5]
        ctx['case_deadlines'] = ctx['deadlines']
        ctx['negotiation_threads'] = case_record.negotiation_threads.all()[:10]
        ctx['case_negotiation_threads'] = ctx['negotiation_threads']
        ctx['related_case_matter'] = case_record.matter
        return ctx


class ContractCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Contract
    form_class = ContractForm
    template_name = 'contracts/contract_form.html'
    success_url = reverse_lazy('contracts:contract_list')

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(
            self.request.user,
            'CREATE',
            'Contract',
            self.object.id,
            str(self.object),
            changes={
                'event': 'contract_created',
                'status': self.object.status,
                'lifecycle_stage': self.object.lifecycle_stage,
                'contract_type': self.object.contract_type,
            },
            request=self.request,
        )
        messages.success(self.request, f'Contract "{self.object.title}" created.')
        return response


class ContractUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Contract
    form_class = ContractForm
    template_name = 'contracts/contract_form.html'
    success_url = reverse_lazy('contracts:contract_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Contract.objects.all(), org)

    def dispatch(self, request, *args, **kwargs):
        contract = self.get_object()
        self.original_contract = contract
        if not can_access_contract_action(request.user, contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit this contract.')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        changes = build_contract_audit_changes(getattr(self, 'original_contract', None), self.object)
        event = 'contract_updated'
        if changes.get('lifecycle_stage'):
            event = 'contract_lifecycle_stage_changed'
        log_action(
            self.request.user,
            'UPDATE',
            'Contract',
            self.object.id,
            str(self.object),
            changes={
                'event': event,
                'changed_fields': sorted(changes.keys()),
                'field_changes': changes,
            },
            request=self.request,
        )
        return response


class RepositoryView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/repository.html'
    context_object_name = 'contracts'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Contract.objects.select_related('created_by'), org).order_by('-updated_at', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_contracts = scope_queryset_for_organization(Contract.objects.all(), org)
        expiry_cutoff = timezone.localdate() + timedelta(days=30)
        doc_stats = tenant_contracts.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status=Contract.Status.ACTIVE)),
            draft=Count('id', filter=Q(status=Contract.Status.DRAFT)),
            expiring=Count('id', filter=Q(end_date__isnull=False, end_date__lte=expiry_cutoff)),
        )
        ctx['total_documents'] = doc_stats['total']
        ctx['active_documents'] = doc_stats['active']
        ctx['draft_documents'] = doc_stats['draft']
        ctx['expiring_documents'] = doc_stats['expiring']
        return ctx


@login_required
@require_POST
def contract_ai_assistant(request, pk):
    organization = get_user_organization(request.user)
    contract = get_object_or_404(scope_queryset_for_organization(Contract.objects.all(), organization), id=pk)
    if not can_access_contract_action(request.user, contract, ContractAction.COMMENT):
        return HttpResponseForbidden('You do not have access to this contract organization.')

    prompt = ''
    execute_actions = False
    approval_confirmed = False
    content_type = (request.content_type or '').lower()
    if 'application/json' in content_type:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            prompt = (payload.get('prompt') or '').strip()
            execute_actions = bool(payload.get('execute_actions'))
            approval_confirmed = bool(payload.get('approval_confirmed'))
        except (ValueError, UnicodeDecodeError):
            prompt = ''
    else:
        prompt = (request.POST.get('prompt') or '').strip()
        execute_actions = str(request.POST.get('execute_actions', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        approval_confirmed = str(request.POST.get('approval_confirmed', '')).strip().lower() in {'1', 'true', 'yes', 'on'}

    if not prompt:
        prompt = 'Give me a risk and renewal summary for this contract.'

    prompt_policy = evaluate_prompt(prompt)
    if not prompt_policy.get('allowed'):
        log_action(
            request.user,
            AuditLog.Action.EXPORT,
            'ContractAI',
            object_id=contract.id,
            object_repr=contract.title,
            changes={
                'organization_id': contract.organization_id,
                'event': 'contract_ai_assistant_blocked',
                'prompt_length': len(prompt),
                'policy_reason': prompt_policy.get('reason'),
            },
            request=request,
        )
        return JsonResponse(
            {
                'ok': False,
                'error': 'Prompt rejected by AI policy.',
                'policy': {
                    'allowed': False,
                    'reason': prompt_policy.get('reason'),
                },
            },
            status=400,
        )

    normalized_prompt = prompt_policy.get('normalized_prompt') or prompt
    ai_response = _build_contract_ai_response(contract, normalized_prompt)
    action_plan = build_action_plan(contract, normalized_prompt)
    action_plan_payload = [
        {
            'action_type': action.action_type,
            'description': action.description,
            'payload': action.payload,
            'requires_approval': action.requires_approval,
        }
        for action in action_plan
    ]
    action_execution = None

    if execute_actions and action_plan_payload:
        if not can_manage_organization(request.user, organization):
            return HttpResponseForbidden('Only organization owners/admins can execute AI actions.')
        if not approval_confirmed:
            return JsonResponse(
                {
                    'ok': False,
                    'error': 'AI action execution requires explicit approval confirmation.',
                    'action_execution': {
                        'status': 'approval_required',
                        'required': True,
                        'action_plan': action_plan_payload,
                    },
                },
                status=409,
            )
        action_execution = execute_action_plan(
            organization=organization,
            contract=contract,
            actor=request.user,
            plan=action_plan,
        )

    log_action(
        request.user,
        AuditLog.Action.EXPORT,
        'ContractAI',
        object_id=contract.id,
        object_repr=contract.title,
        changes={
            'organization_id': contract.organization_id,
            'event': 'contract_ai_assistant_invoked',
            'prompt_length': len(prompt),
            'mode': ai_response.get('mode'),
            'policy_reason': prompt_policy.get('reason'),
            'execute_actions': execute_actions,
            'action_plan_count': len(action_plan_payload),
            'action_trace_id': action_execution.get('trace_id') if action_execution else '',
            'rollback_plan': action_execution.get('rollback_plan') if action_execution else [],
        },
        request=request,
    )
    return JsonResponse(
        {
            'ok': True,
            'response': ai_response,
            'action_plan': action_plan_payload,
            'action_execution': action_execution,
        }
    )


@login_required
def dashboard(request):
    today = date.today()
    seven_days = today + timedelta(days=7)
    thirty_days = today + timedelta(days=30)
    org = get_user_organization(request.user)

    case_qs = scope_queryset_for_organization(Case.objects.all(), org)
    clients_qs = scope_queryset_for_organization(Client.objects.all(), org)
    case_matter_qs = scope_queryset_for_organization(CaseMatter.objects.all(), org)
    workflows_qs = scope_queryset_for_organization(Workflow.objects.all(), org)
    invoices_qs = scope_queryset_for_organization(Invoice.objects.all(), org)
    documents_qs = scope_queryset_for_organization(Document.objects.all(), org)
    approvals_qs = scope_queryset_for_organization(ApprovalRequest.objects.all(), org)
    signatures_qs = scope_queryset_for_organization(SignatureRequest.objects.all(), org)
    dsars_qs = scope_queryset_for_organization(DSARRequest.objects.all(), org)
    time_entries_qs = scope_queryset_for_organization(TimeEntry.objects.all(), org)
    trust_accounts_qs = scope_queryset_for_organization(TrustAccount.objects.all(), org)
    legal_tasks_qs = CaseSignal.objects.for_organization(org) if org else CaseSignal.objects.none()
    risks_qs = RiskLog.objects.for_organization(org) if org else RiskLog.objects.none()
    deadlines_qs = Deadline.objects.for_organization(org)

    case_stats = case_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='ACTIVE')),
        draft=Count('id', filter=Q(status='DRAFT')),
        pending=Count('id', filter=Q(status='PENDING')),
        expiring_soon=Count('id', filter=Q(status='ACTIVE', end_date__lte=thirty_days, end_date__gte=today)),
    )
    client_stats = clients_qs.aggregate(total=Count('id'))
    case_matter_stats = case_matter_qs.aggregate(total=Count('id'), active=Count('id', filter=Q(status='ACTIVE')))
    task_signal_stats = legal_tasks_qs.aggregate(pending=Count('id', filter=Q(status='PENDING')))
    workflow_stats = workflows_qs.aggregate(active=Count('id', filter=Q(status='ACTIVE')))
    risk_stats = risks_qs.aggregate(high_critical=Count('id', filter=Q(risk_level__in=['HIGH', 'CRITICAL'])))
    deadline_stats = deadlines_qs.aggregate(
        overdue=Count('id', filter=Q(is_completed=False, due_date__lt=today)),
        upcoming=Count('id', filter=Q(is_completed=False, due_date__gte=today, due_date__lte=seven_days)),
    )
    invoice_stats = invoices_qs.aggregate(
        outstanding=Sum('total_amount', filter=Q(status__in=['SENT', 'OVERDUE'])) or Decimal('0'),
        overdue=Sum('total_amount', filter=Q(status='OVERDUE')) or Decimal('0'),
        paid_this_month=Sum('total_amount', filter=Q(status='PAID', updated_at__month=today.month, updated_at__year=today.year)) or Decimal('0'),
    )
    approval_stats = approvals_qs.aggregate(pending=Count('id', filter=Q(status='PENDING')))
    signature_stats = signatures_qs.aggregate(pending=Count('id', filter=Q(status='PENDING')))
    dsar_stats = dsars_qs.aggregate(open=Count('id', filter=Q(status__in=['RECEIVED', 'IN_PROGRESS'])))
    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).count() if request.user.is_authenticated else 0

    recent_cases = list(case_qs.select_related('client', 'created_by').order_by('-created_at')[:6])
    upcoming_deadlines = list(deadlines_qs.select_related('contract', 'matter', 'assigned_to').filter(is_completed=False, due_date__gte=today).order_by('due_date')[:6])
    upcoming_tasks = list(legal_tasks_qs.select_related('contract', 'matter', 'assigned_to').filter(status='PENDING', due_date__gte=today).order_by('due_date')[:5])
    recent_audit = list(AuditLog.objects.select_related('user').filter(changes__organization_id=org.id).order_by('-timestamp')[:8]) if org else []

    case_status_data = []
    status_mapping = [('ACTIVE', 'Active'), ('DRAFT', 'Draft'), ('PENDING', 'In Review'), ('EXPIRED', 'Expired'), ('TERMINATED', 'Terminated')]
    status_counts = case_qs.values('status').annotate(count=Count('id'))
    status_counts_dict = {item['status']: item['count'] for item in status_counts}
    for status_code, status_label in status_mapping:
        cnt = status_counts_dict.get(status_code, 0)
        if cnt > 0:
            case_status_data.append({'label': status_label, 'count': cnt})

    billable_hours = time_entries_qs.filter(date__month=today.month, date__year=today.year).aggregate(total=Sum('hours'))['total'] or Decimal('0')
    trust_balance = trust_accounts_qs.aggregate(total=Sum('balance'))['total'] or Decimal('0')
    total_documents = documents_qs.count()

    from django.shortcuts import render

    return render(request, 'dashboard.html', {
        'case_stats': case_stats,
        'client_stats': client_stats,
        'case_matter_stats': case_matter_stats,
        'task_signal_stats': task_signal_stats,
        'workflow_stats': workflow_stats,
        'risk_stats': risk_stats,
        'deadline_stats': deadline_stats,
        'invoice_stats': invoice_stats,
        'approval_stats': approval_stats,
        'signature_stats': signature_stats,
        'dsar_stats': dsar_stats,
        'unread_notifications': unread_notifications,
        'recent_cases': recent_cases,
        'upcoming_deadlines': upcoming_deadlines,
        'upcoming_tasks': upcoming_tasks,
        'recent_audit': recent_audit,
        'case_status_data': case_status_data,
        'billable_hours': billable_hours,
        'trust_balance': trust_balance,
        'total_documents': total_documents,
        'total_cases': case_stats['total'] or 0,
        'active_cases': case_stats['active'] or 0,
        'expiring_case_count': case_stats['expiring_soon'] or 0,
        'total_contracts': case_stats['total'] or 0,
        'active_contracts': case_stats['active'] or 0,
        'expiring_soon': case_stats['expiring_soon'] or 0,
    })
