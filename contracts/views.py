from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from django.contrib.auth.forms import UserCreationForm
from .forms import (
    ChecklistItemForm, WorkflowForm, WorkflowTemplateForm,
    BudgetForm, TrademarkRequestForm, LegalTaskForm, RiskLogForm, ComplianceChecklistForm,
    DueDiligenceProcessForm, DueDiligenceTaskForm, DueDiligenceRiskForm, BudgetExpenseForm
)
from .models import (
    Contract, NegotiationThread, TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist, ChecklistItem,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk, Budget, BudgetExpense
)

# --- Index View ---
def index(request):
    return redirect('dashboard')

# --- Contract Views ---
class ContractListView(LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/contract_list.html'
    context_object_name = 'contracts'
    paginate_by = 25

class WorkflowDetailView(LoginRequiredMixin, DetailView):
    model = Workflow
    template_name = 'contracts/workflow_detail.html'
    context_object_name = 'workflow'

class WorkflowCreateView(LoginRequiredMixin, CreateView):
    model = Workflow
    form_class = WorkflowForm
    template_name = 'contracts/workflow_form.html'
    success_url = reverse_lazy('contracts:workflow_dashboard')

class WorkflowTemplateListView(LoginRequiredMixin, ListView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_list.html'
    context_object_name = 'workflow_templates'

class WorkflowTemplateCreateView(LoginRequiredMixin, CreateView):
    model = WorkflowTemplate
    form_class = WorkflowTemplateForm
    template_name = 'contracts/workflow_template_form.html'
    success_url = reverse_lazy('contracts:workflow_template_list')

class ComplianceChecklistUpdateView(LoginRequiredMixin, UpdateView):
    model = ComplianceChecklist
    form_class = ComplianceChecklistForm
    template_name = 'contracts/compliance_checklist_form.html'
    success_url = reverse_lazy('contracts:compliance_checklist_list')

class ToggleChecklistItemView(LoginRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(ChecklistItem, pk=pk)
        item.is_completed = not item.is_completed
        item.save()
        return redirect('contracts:compliance_checklist_detail', pk=item.checklist.pk)

class AddChecklistItemView(LoginRequiredMixin, CreateView):
    model = ChecklistItem
    form_class = ChecklistItemForm
    template_name = 'contracts/checklist_item_form.html'

    def form_valid(self, form):
        form.instance.checklist_id = self.kwargs['checklist_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:compliance_checklist_detail', kwargs={'pk': self.kwargs['checklist_pk']})

class RepositoryView(LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/repository.html'
    context_object_name = 'contracts'

class ContractDetailView(LoginRequiredMixin, DetailView):
    model = Contract
    template_name = 'contracts/contract_detail.html'
    context_object_name = 'contract'

class ContractCreateView(LoginRequiredMixin, CreateView):
    model = Contract
    fields = ['title', 'content', 'status']
    template_name = 'contracts/contract_form.html'
    success_url = reverse_lazy('contracts:contract_list')

class ContractUpdateView(LoginRequiredMixin, UpdateView):
    model = Contract
    fields = ['title', 'content', 'status']
    template_name = 'contracts/contract_form.html'
    success_url = reverse_lazy('contracts:contract_list')

# --- Missing View Classes ---
class ProfileView(View):
    def get(self, request):
        return render(request, 'profile.html')

class SignUpView(CreateView):
    form_class = UserCreationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('login')

# Workflow Dashboard View
class WorkflowDashboardView(LoginRequiredMixin, ListView):
    model = Workflow
    template_name = 'contracts/workflow_dashboard.html'
    context_object_name = 'workflows'

# Workflow Step Update View
class WorkflowStepUpdateView(LoginRequiredMixin, UpdateView):
    model = WorkflowStep
    fields = ['status', 'assigned_to', 'due_date']
    template_name = 'contracts/workflow_step_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.workflow.pk})

# Add Missing Negotiation Note View
class AddNegotiationNoteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        # Placeholder - redirect back for now
        return redirect('dashboard')

# --- Missing Views from URLs ---
class TrademarkRequestListView(LoginRequiredMixin, ListView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_list.html'
    context_object_name = 'trademark_requests'

class TrademarkRequestDetailView(LoginRequiredMixin, DetailView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_detail.html'
    context_object_name = 'trademark_request'

class TrademarkRequestCreateView(LoginRequiredMixin, CreateView):
    model = TrademarkRequest
    form_class = TrademarkRequestForm
    template_name = 'contracts/trademark_request_form.html'
    success_url = reverse_lazy('contracts:trademark_request_list')

class TrademarkRequestUpdateView(LoginRequiredMixin, UpdateView):
    model = TrademarkRequest
    form_class = TrademarkRequestForm
    template_name = 'contracts/trademark_request_form.html'
    success_url = reverse_lazy('contracts:trademark_request_list')

class LegalTaskKanbanView(LoginRequiredMixin, ListView):
    model = LegalTask
    template_name = 'contracts/legal_task_board.html'
    context_object_name = 'legal_tasks'

class LegalTaskCreateView(LoginRequiredMixin, CreateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/legal_task_form.html'
    success_url = reverse_lazy('contracts:legal_task_kanban')

class LegalTaskUpdateView(LoginRequiredMixin, UpdateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/legal_task_form.html'
    success_url = reverse_lazy('contracts:legal_task_kanban')

class RiskLogListView(LoginRequiredMixin, ListView):
    model = RiskLog
    template_name = 'contracts/risk_log_list.html'
    context_object_name = 'risk_logs'

class RiskLogCreateView(LoginRequiredMixin, CreateView):
    model = RiskLog
    form_class = RiskLogForm
    template_name = 'contracts/risk_log_form.html'
    success_url = reverse_lazy('contracts:risk_log_list')

class RiskLogUpdateView(LoginRequiredMixin, UpdateView):
    model = RiskLog
    form_class = RiskLogForm
    template_name = 'contracts/risk_log_form.html'
    success_url = reverse_lazy('contracts:risk_log_list')

class ComplianceChecklistListView(LoginRequiredMixin, ListView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_list.html'
    context_object_name = 'compliance_checklists'

class ComplianceChecklistDetailView(LoginRequiredMixin, DetailView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_detail.html'
    context_object_name = 'compliance_checklist'

class ComplianceChecklistCreateView(LoginRequiredMixin, CreateView):
    model = ComplianceChecklist
    form_class = ComplianceChecklistForm
    template_name = 'contracts/compliance_checklist_form.html'
    success_url = reverse_lazy('contracts:compliance_checklist_list')

# Removed duplicate ComplianceChecklistUpdateView
# Removed duplicate ToggleChecklistItemView
# Removed duplicate AddChecklistItemView

class RepositoryView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'contracts/repository.html')

# Function-based views that are imported
def workflow_create(request):
    if request.method == 'POST':
        form = WorkflowForm(request.POST)
        if form.is_valid():
            workflow = form.save(commit=False)
            workflow.created_by = request.user
            workflow.save()
            return redirect('contracts:workflow_detail', pk=workflow.pk)
    else:
        form = WorkflowForm()
    return render(request, 'contracts/workflow_form.html', {'form': form})

def workflow_template_create(request):
    if request.method == 'POST':
        form = WorkflowTemplateForm(request.POST)
        if form.is_valid():
            template = form.save()
            return redirect('contracts:workflow_template_list')
    else:
        form = WorkflowTemplateForm()
    return render(request, 'contracts/workflow_template_form.html', {'form': form})

def workflow_template_list(request):
    templates = WorkflowTemplate.objects.all()
    return render(request, 'contracts/workflow_template_list.html', {'workflow_templates': templates})

def toggle_dd_item(request, pk):
    task = get_object_or_404(DueDiligenceTask, pk=pk)
    if task.status == 'COMPLETED':
        task.status = 'PENDING'
    else:
        task.status = 'COMPLETED'
    task.save()
    return redirect('contracts:due_diligence_detail', pk=task.process.pk)

def profile(request):
    return render(request, 'profile.html')


# --- Workflow Views ---

class WorkflowTemplateListView(LoginRequiredMixin, ListView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_list.html'
    context_object_name = 'workflow_templates'


class WorkflowTemplateDetailView(LoginRequiredMixin, DetailView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_detail.html'
    context_object_name = 'workflow_template'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['steps'] = WorkflowTemplateStep.objects.filter(template=self.object).order_by('order')
        return context


class WorkflowTemplateCreateView(LoginRequiredMixin, CreateView):
    model = WorkflowTemplate
    form_class = WorkflowTemplateForm
    template_name = 'contracts/workflow_template_form.html'
    success_url = reverse_lazy('contracts:workflow_template_list')


class WorkflowTemplateUpdateView(LoginRequiredMixin, UpdateView):
    model = WorkflowTemplate
    form_class = WorkflowTemplateForm
    template_name = 'contracts/workflow_template_form.html'
    success_url = reverse_lazy('contracts:workflow_template_list')


class AddWorkflowTemplateStepView(LoginRequiredMixin, View):
    def post(self, request, pk):
        template = get_object_or_404(WorkflowTemplate, pk=pk)
        # Template step creation logic would go here
        return redirect('contracts:workflow_template_detail', pk=template.pk)


class WorkflowListView(LoginRequiredMixin, ListView):
    model = Workflow
    template_name = 'contracts/workflow_list.html'
    context_object_name = 'workflows'

    def get_queryset(self):
        queryset = Workflow.objects.all()
        contract_pk = self.request.GET.get('contract_pk')
        if contract_pk:
            queryset = queryset.filter(contract=contract_pk)
        return queryset.order_by('-created_at')


class WorkflowDetailView(LoginRequiredMixin, DetailView):
    model = Workflow
    template_name = 'contracts/workflow_detail.html'
    context_object_name = 'workflow'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['steps'] = WorkflowStep.objects.filter(workflow=self.object).order_by('order')
        context['step_form'] = WorkflowForm()
        return context


class WorkflowCreateView(LoginRequiredMixin, CreateView):
    model = Workflow
    form_class = WorkflowForm
    template_name = 'contracts/workflow_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class WorkflowUpdateView(LoginRequiredMixin, UpdateView):
    model = Workflow
    form_class = WorkflowForm
    template_name = 'contracts/workflow_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.pk})


class AddWorkflowStepView(LoginRequiredMixin, View):
    def post(self, request, pk):
        workflow = get_object_or_404(Workflow, pk=pk)
        form = WorkflowForm(request.POST)
        if form.is_valid():
            step = form.save(commit=False)
            step.workflow = workflow
            step.save()
        return redirect('contracts:workflow_detail', pk=workflow.pk)


class WorkflowStepCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        step = get_object_or_404(WorkflowStep, pk=pk)
        step.status = 'COMPLETED'
        step.save()
        return redirect('contracts:workflow_detail', pk=step.workflow.pk)


# Add remaining missing views
class DueDiligenceListView(LoginRequiredMixin, ListView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_list.html'
    context_object_name = 'processes'

class DueDiligenceCreateView(LoginRequiredMixin, CreateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')

class DueDiligenceDetailView(LoginRequiredMixin, DetailView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_detail.html'
    context_object_name = 'process'

class DueDiligenceUpdateView(LoginRequiredMixin, UpdateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')

class AddDueDiligenceItemView(LoginRequiredMixin, CreateView):
    model = DueDiligenceTask
    form_class = DueDiligenceTaskForm
    template_name = 'contracts/dd_task_form.html'

    def form_valid(self, form):
        form.instance.process_id = self.kwargs['process_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.kwargs['process_pk']})

class AddDueDiligenceRiskView(LoginRequiredMixin, CreateView):
    model = DueDiligenceRisk
    form_class = DueDiligenceRiskForm
    template_name = 'contracts/dd_risk_form.html'

    def form_valid(self, form):
        form.instance.process_id = self.kwargs['process_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.kwargs['process_pk']})

class BudgetListView(LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'contracts/budget_list.html'
    context_object_name = 'budgets'

class BudgetCreateView(LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')

class BudgetDetailView(LoginRequiredMixin, DetailView):
    model = Budget
    template_name = 'contracts/budget_detail.html'
    context_object_name = 'budget'

class BudgetUpdateView(LoginRequiredMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')

class AddExpenseView(LoginRequiredMixin, CreateView):
    model = BudgetExpense
    form_class = BudgetExpenseForm
    template_name = 'contracts/expense_form.html'

    def form_valid(self, form):
        form.instance.budget_id = self.kwargs['budget_pk']
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:budget_detail', kwargs={'pk': self.kwargs['budget_pk']})

def workflow_create(request):
    return redirect('contracts:workflow_dashboard')

def workflow_template_create(request):
    return redirect('contracts:workflow_template_list')

def workflow_template_list(request):
    return redirect('contracts:workflow_template_list')

def toggle_dd_item(request, pk):
    task = get_object_or_404(DueDiligenceTask, pk=pk)
    if task.status == 'COMPLETED':
        task.status = 'PENDING'
    else:
        task.status = 'COMPLETED'
    task.save()
    return redirect('contracts:due_diligence_detail', pk=task.process.pk)

# Corrected DueDiligenceDetailView and DueDiligenceUpdateView definitions to avoid duplication
class DueDiligenceDetailView(LoginRequiredMixin, DetailView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_detail.html'
    context_object_name = 'process'

class DueDiligenceUpdateView(LoginRequiredMixin, UpdateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'

class AddDueDiligenceItemView(LoginRequiredMixin, View):
    def post(self, request, pk):
        process = get_object_or_404(DueDiligenceProcess, pk=pk)
        form = DueDiligenceTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.process = process
            task.save()
        return redirect('contracts:due_diligence_detail', pk=process.pk)

class AddDueDiligenceRiskView(LoginRequiredMixin, View):
    def post(self, request, pk):
        process = get_object_or_404(DueDiligenceProcess, pk=pk)
        form = DueDiligenceRiskForm(request.POST)
        if form.is_valid():
            risk = form.save(commit=False)
            risk.process = process
            risk.save()
        return redirect('contracts:due_diligence_detail', pk=process.pk)

class AddExpenseView(LoginRequiredMixin, View):
    def post(self, request, pk):
        budget = get_object_or_404(Budget, pk=pk)
        form = BudgetExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.budget = budget
            expense.created_by = request.user
            expense.save()
        return redirect('contracts:budget_detail', pk=budget.pk)

# --- Due Diligence Views ---
class DueDiligenceProcessListView(LoginRequiredMixin, ListView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_list.html'
    context_object_name = 'processes'
    paginate_by = 25

    def get_queryset(self):
        queryset = DueDiligenceProcess.objects.all()
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = DueDiligenceProcess.ProcessStatus.choices
        return context


class DueDiligenceProcessDetailView(LoginRequiredMixin, DetailView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_detail.html'
    context_object_name = 'process'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tasks'] = self.object.dd_tasks.all()
        context['risks'] = self.object.dd_risks.all()
        context['high_risks'] = self.object.dd_risks.filter(risk_level='HIGH')
        context['medium_risks'] = self.object.dd_risks.filter(risk_level='MEDIUM')
        context['low_risks'] = self.object.dd_risks.filter(risk_level='LOW')
        return context


class DueDiligenceProcessCreateView(LoginRequiredMixin, CreateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')


class DueDiligenceProcessUpdateView(LoginRequiredMixin, UpdateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.object.pk})


# --- Budget Views ---
class BudgetListView(LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'contracts/budget_list.html'
    context_object_name = 'budgets'
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_year'] = timezone.now().year
        return context


class BudgetDetailView(LoginRequiredMixin, DetailView):
    model = Budget
    template_name = 'contracts/budget_detail.html'
    context_object_name = 'budget'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['expenses'] = self.object.expenses.all()
        context['expense_form'] = BudgetExpenseForm()
        return context


class BudgetCreateView(LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class BudgetUpdateView(LoginRequiredMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:budget_detail', kwargs={'pk': self.object.pk})


@login_required
@require_POST
def add_budget_expense(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id)
    form = BudgetExpenseForm(request.POST)

    if form.is_valid():
        expense = form.save(commit=False)
        expense.budget = budget
        expense.created_by = request.user
        expense.save()
        messages.success(request, 'Expense added successfully.')
    else:
        messages.error(request, 'Error adding expense. Please check the form.')

    return redirect('contracts:budget_detail', pk=budget_id)


# --- Dashboard View ---
def dashboard(request):
    # Contract data
    try:
        total_contracts = Contract.objects.count()
        recent_contracts = Contract.objects.all()[:10]

        # Pipeline data - count contracts by status
        pipeline_data = []
        for status, display in Contract.ContractStatus.choices:
            count = Contract.objects.filter(status=status).count()
            if count > 0:
                pipeline_data.append((display, count))
    except:
        total_contracts = 0
        recent_contracts = []
        pipeline_data = []

    # Legal Tasks data
    try:
        pending_tasks = LegalTask.objects.filter(status__in=['PENDING', 'IN_PROGRESS']).count()
    except:
        pending_tasks = 0

    # Workflow data
    try:
        active_workflows = Workflow.objects.filter(status='ACTIVE').count()
    except:
        active_workflows = 0

    # Trademark data
    try:
        trademark_requests = TrademarkRequest.objects.all().count()
        pending_trademarks = TrademarkRequest.objects.filter(status__in=['PENDING', 'FILED', 'IN_REVIEW']).count()
    except:
        trademark_requests = 0
        pending_trademarks = 0

    # Risk data
    try:
        risk_count = RiskLog.objects.count()
        top_risks = RiskLog.objects.filter(risk_level='HIGH')[:5]
    except:
        risk_count = 0
        top_risks = []

    # Due Diligence data
    try:
        dd_count = DueDiligenceProcess.objects.count()
    except:
        dd_count = 0

    # Budget data
    try:
        budget_count = Budget.objects.count()
    except:
        budget_count = 0

    # Compliance data
    try:
        upcoming_checklists = ComplianceChecklist.objects.all()[:5]
    except:
        upcoming_checklists = []

    context = {
        'total_contracts': total_contracts,
        'recent_contracts': recent_contracts,
        'pipeline_data': pipeline_data,
        'pending_tasks': pending_tasks,
        'active_workflows': active_workflows,
        'trademark_requests': trademark_requests,
        'pending_trademarks': pending_trademarks,
        'risk_count': risk_count,
        'top_risks': top_risks,
        'dd_count': dd_count,
        'budget_count': budget_count,
        'upcoming_checklists': upcoming_checklists,
    }
    return render(request, 'dashboard.html', context)