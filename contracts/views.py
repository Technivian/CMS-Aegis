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
    TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist, ChecklistItem,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk, Budget, BudgetExpense
)

# --- Index View ---
def index(request):
    return redirect('dashboard')

# --- Contract Views ---

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
    pending_tasks = 0
    # Trademark data
    try:
        trademark_requests = TrademarkRequest.objects.all().count()
        pending_trademarks = TrademarkRequest.objects.filter(status__in=['PENDING', 'FILED', 'IN_REVIEW']).count()
    except:
        trademark_requests = 0
        pending_trademarks = 0

    # Due Diligence data
    try:
        active_due_diligence = DueDiligenceProcess.objects.filter(status__in=['PLANNING', 'IN_PROGRESS', 'REVIEW']).count()
        high_risk_dd = DueDiligenceRisk.objects.filter(risk_level='HIGH').count()
    except:
        active_due_diligence = 0
        high_risk_dd = 0

    # Budget data
    try:
        from datetime import datetime
        current_year = datetime.now().year
        current_quarter = f"Q{((datetime.now().month - 1) // 3) + 1}"
        current_budgets = Budget.objects.filter(year=current_year, quarter=current_quarter)
        over_budget_count = sum(1 for budget in current_budgets if budget.is_over_budget)
    except:
        over_budget_count = 0

    context = {
        'all_contracts_count': 0,
        'pending_tasks': pending_tasks,
        'trademark_requests': trademark_requests,
        'pending_trademarks': pending_trademarks,
        'active_due_diligence': active_due_diligence,
        'high_risk_dd': high_risk_dd,
        'over_budget_count': over_budget_count,
    }
    return render(request, 'dashboard.html', context)