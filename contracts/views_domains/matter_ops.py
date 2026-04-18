from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.db.models import Q, Sum, Count
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import (
    BudgetExpenseForm,
    BudgetForm,
    ChecklistItemForm,
    ComplianceChecklistForm,
    DueDiligenceProcessForm,
    DueDiligenceRiskForm,
    DueDiligenceTaskForm,
    LegalTaskForm,
    RiskLogForm,
    TrademarkRequestForm,
)
from contracts.models import (
    Budget,
    BudgetExpense,
    ChecklistItem,
    ComplianceChecklist,
    Contract,
    DueDiligenceProcess,
    DueDiligenceRisk,
    DueDiligenceTask,
    LegalTask,
    Matter,
    RiskLog,
    TrademarkRequest,
)
from contracts.permissions import ContractAction, can_access_contract_action
from contracts.tenancy import get_user_organization, scope_queryset_for_organization
from contracts.view_support import TenantAssignCreateMixin, TenantScopedFormMixin, TenantScopedQuerysetMixin


class LegalTaskKanbanView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = LegalTask
    template_name = 'contracts/legal_task_board.html'
    context_object_name = 'legal_tasks'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return LegalTask.objects.none()
        return LegalTask.objects.select_related('contract', 'matter', 'assigned_to').filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        ).order_by('-updated_at', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['task_signals'] = context['legal_tasks']
        context['open_task_signal_count'] = context['legal_tasks'].filter(status='PENDING').count()
        return context


class LegalTaskCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/legal_task_form.html'
    success_url = reverse_lazy('contracts:legal_task_kanban')
    scoped_form_fields = {'contract': Contract, 'matter': Matter}

    def form_valid(self, form):
        org = get_user_organization(self.request.user)
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create tasks for this contract.')
        if form.instance.matter and org and form.instance.matter.organization_id != org.id:
            return HttpResponseForbidden('You do not have permission to create tasks for this matter.')
        return super().form_valid(form)


class LegalTaskUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/legal_task_form.html'
    success_url = reverse_lazy('contracts:legal_task_kanban')
    scoped_form_fields = {'contract': Contract, 'matter': Matter}

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return LegalTask.objects.none()
        return LegalTask.objects.filter(Q(contract__organization=org) | Q(matter__organization=org))

    def dispatch(self, request, *args, **kwargs):
        task = self.get_object()
        if task.contract and not can_access_contract_action(request.user, task.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit tasks for this contract.')
        org = get_user_organization(request.user)
        if task.matter and org and task.matter.organization_id != org.id:
            return HttpResponseForbidden('You do not have permission to edit tasks for this matter.')
        return super().dispatch(request, *args, **kwargs)


class TrademarkRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_list.html'
    context_object_name = 'trademark_requests'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if org:
            qs = TrademarkRequest.objects.select_related('client', 'matter').filter(Q(client__organization=org) | Q(matter__organization=org))
        else:
            qs = TrademarkRequest.objects.none()
        search_query = (self.request.GET.get('q') or '').strip()
        status = (self.request.GET.get('status') or '').strip()
        if search_query:
            qs = qs.filter(Q(mark_text__icontains=search_query) | Q(description__icontains=search_query) | Q(client__name__icontains=search_query) | Q(matter__title__icontains=search_query))
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-updated_at', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        if org:
            tenant_requests = TrademarkRequest.objects.filter(Q(client__organization=org) | Q(matter__organization=org))
        else:
            tenant_requests = TrademarkRequest.objects.none()
        ctx['search_query'] = (self.request.GET.get('q') or '').strip()
        ctx['selected_status'] = (self.request.GET.get('status') or '').strip()
        ctx['status_choices'] = TrademarkRequest.Status.choices
        ctx['total_requests'] = tenant_requests.count()
        ctx['pending_requests'] = tenant_requests.filter(status=TrademarkRequest.Status.PENDING).count()
        ctx['approved_requests'] = tenant_requests.filter(status=TrademarkRequest.Status.APPROVED).count()
        ctx['request_tabs'] = [('All Requests', ''), ('Pending', TrademarkRequest.Status.PENDING), ('Approved', TrademarkRequest.Status.APPROVED)]
        return ctx


class TrademarkRequestDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_detail.html'
    context_object_name = 'trademark_request'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return TrademarkRequest.objects.none()
        return TrademarkRequest.objects.filter(Q(client__organization=org) | Q(matter__organization=org))


class TrademarkRequestCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = TrademarkRequest
    form_class = TrademarkRequestForm
    template_name = 'contracts/trademark_request_form.html'
    success_url = reverse_lazy('contracts:trademark_request_list')


class TrademarkRequestUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = TrademarkRequest
    form_class = TrademarkRequestForm
    template_name = 'contracts/trademark_request_form.html'
    success_url = reverse_lazy('contracts:trademark_request_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return TrademarkRequest.objects.none()
        return TrademarkRequest.objects.filter(Q(client__organization=org) | Q(matter__organization=org))


class RiskLogListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = RiskLog
    template_name = 'contracts/risk_log_list.html'
    context_object_name = 'risk_logs'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if org:
            qs = RiskLog.objects.select_related('contract', 'matter', 'created_by').filter(Q(contract__organization=org) | Q(matter__organization=org))
        else:
            qs = RiskLog.objects.none()
        search_query = (self.request.GET.get('q') or '').strip()
        risk_level = (self.request.GET.get('risk_level') or '').strip()
        if search_query:
            qs = qs.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query) | Q(contract__title__icontains=search_query) | Q(matter__title__icontains=search_query))
        if risk_level:
            qs = qs.filter(risk_level=risk_level)
        risk_order = models.Case(
            models.When(risk_level=RiskLog.RiskLevel.CRITICAL, then=models.Value(0)),
            models.When(risk_level=RiskLog.RiskLevel.HIGH, then=models.Value(1)),
            models.When(risk_level=RiskLog.RiskLevel.MEDIUM, then=models.Value(2)),
            default=models.Value(3),
            output_field=models.IntegerField(),
        )
        return qs.annotate(risk_sort=risk_order).order_by('risk_sort', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        if org:
            tenant_risks = RiskLog.objects.filter(Q(contract__organization=org) | Q(matter__organization=org))
        else:
            tenant_risks = RiskLog.objects.none()
        ctx['search_query'] = (self.request.GET.get('q') or '').strip()
        ctx['selected_risk_level'] = (self.request.GET.get('risk_level') or '').strip()
        ctx['total_risks'] = tenant_risks.count()
        ctx['high_risk_count'] = tenant_risks.filter(risk_level=RiskLog.RiskLevel.HIGH).count()
        ctx['critical_risk_count'] = tenant_risks.filter(risk_level=RiskLog.RiskLevel.CRITICAL).count()
        ctx['risk_tabs'] = [('All Risks', ''), ('High Risk', RiskLog.RiskLevel.HIGH), ('Critical Risk', RiskLog.RiskLevel.CRITICAL)]
        return ctx


class RiskLogCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = RiskLog
    form_class = RiskLogForm
    template_name = 'contracts/risk_log_form.html'
    success_url = reverse_lazy('contracts:risk_log_list')

    def form_valid(self, form):
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create risk logs for this contract.')
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class RiskLogUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = RiskLog
    form_class = RiskLogForm
    template_name = 'contracts/risk_log_form.html'
    success_url = reverse_lazy('contracts:risk_log_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return RiskLog.objects.none()
        return RiskLog.objects.filter(Q(contract__organization=org) | Q(matter__organization=org))

    def dispatch(self, request, *args, **kwargs):
        risk_log = self.get_object()
        if risk_log.contract and not can_access_contract_action(request.user, risk_log.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit risk logs for this contract.')
        return super().dispatch(request, *args, **kwargs)


class ComplianceChecklistListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_list.html'
    context_object_name = 'compliance_checklists'


class ComplianceChecklistDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_detail.html'
    context_object_name = 'compliance_checklist'


class ComplianceChecklistCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ComplianceChecklist
    form_class = ComplianceChecklistForm
    template_name = 'contracts/compliance_checklist_form.html'
    success_url = reverse_lazy('contracts:compliance_checklist_list')

    def form_valid(self, form):
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create checklists for this contract.')
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ComplianceChecklistUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ComplianceChecklist
    form_class = ComplianceChecklistForm
    template_name = 'contracts/compliance_checklist_form.html'
    success_url = reverse_lazy('contracts:compliance_checklist_list')

    def dispatch(self, request, *args, **kwargs):
        checklist = self.get_object()
        if checklist.contract and not can_access_contract_action(request.user, checklist.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit this contract checklist.')
        return super().dispatch(request, *args, **kwargs)


class DueDiligenceListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_list.html'
    context_object_name = 'processes'


class DueDiligenceCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')


class DueDiligenceDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_detail.html'
    context_object_name = 'process'


class DueDiligenceUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')


class BudgetListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'contracts/budget_list.html'
    context_object_name = 'budgets'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        queryset = scope_queryset_for_organization(Budget.objects.all(), org)
        search_query = (self.request.GET.get('q') or '').strip()
        year = (self.request.GET.get('year') or '').strip()
        if search_query:
            queryset = queryset.filter(Q(department__icontains=search_query) | Q(description__icontains=search_query))
        if year and year.isdigit():
            queryset = queryset.filter(year=int(year))
        return queryset.order_by('-year', 'quarter', 'department')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_budgets = scope_queryset_for_organization(Budget.objects.all(), org)
        current_year = timezone.localdate().year
        ctx['search_query'] = (self.request.GET.get('q') or '').strip()
        ctx['selected_year'] = (self.request.GET.get('year') or '').strip()
        ctx['current_year'] = current_year
        budget_stats = tenant_budgets.aggregate(total=Count('id'), current_year=Count('id', filter=Q(year=current_year)), total_allocated=Sum('allocated_amount'))
        ctx['total_budgets'] = budget_stats['total']
        ctx['current_year_budgets'] = budget_stats['current_year']
        ctx['total_allocated'] = budget_stats['total_allocated'] or Decimal('0')
        ctx['budget_tabs'] = [('All Budgets', ''), (str(current_year), str(current_year))]
        return ctx


class BudgetCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')


class BudgetDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Budget
    template_name = 'contracts/budget_detail.html'
    context_object_name = 'budget'


class BudgetUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')
