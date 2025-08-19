from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import ValidationError
import json
from .models import *
from .forms import *
from .services import get_repository_service, get_template_service, get_clause_service, get_obligation_service

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

class RepositoryView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'contracts/repository.html')

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
@csrf_protect
def user_login(request):
    """Handle user login with comprehensive error handling"""
    if request.user.is_authenticated:
        return redirect('contracts:dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                if user.is_active:
                    login(request, user)
                    messages.success(request, f'Welcome back, {user.first_name or username}!')
                    next_url = request.GET.get('next', 'contracts:dashboard')
                    return redirect(next_url)
                else:
                    messages.error(request, 'Your account has been disabled.')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = AuthenticationForm()

    return render(request, 'registration/login.html', {'form': form})

@csrf_protect
def user_register(request):
    """Handle user registration with comprehensive validation"""
    if request.user.is_authenticated:
        return redirect('contracts:dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                username = form.cleaned_data.get('username')
                messages.success(request, f'Account created successfully for {username}!')

                # Auto-login after successful registration
                user = authenticate(username=username, password=form.cleaned_data.get('password1'))
                if user:
                    login(request, user)
                    return redirect('contracts:dashboard')
                else:
                    return redirect('contracts:login')
            except ValidationError as e:
                messages.error(request, f'Registration failed: {e}')
            except Exception as e:
                messages.error(request, 'An unexpected error occurred during registration.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = UserCreationForm()

    return render(request, 'registration/register.html', {'form': form})

def user_logout(request):
    """Handle user logout"""
    username = request.user.username if request.user.is_authenticated else 'User'
    logout(request)
    messages.success(request, f'You have been logged out successfully. See you soon!')
    return redirect('contracts:login')

def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('contracts:login')

    try:
        context = {
            'total_contracts': Contract.objects.count(),
            'active_contracts': Contract.objects.filter(status='active').count(),
            'pending_tasks': LegalTask.objects.filter(status='pending').count(),
            'recent_contracts': Contract.objects.order_by('-created_at')[:5],
            'recent_tasks': LegalTask.objects.order_by('-created_at')[:5],
        }
    except Exception as e:
        messages.warning(request, 'Some dashboard data is unavailable.')
        context = {
            'total_contracts': 0,
            'active_contracts': 0,
            'pending_tasks': 0,
            'recent_contracts': [],
            'recent_tasks': [],
        }

    return render(request, 'dashboard.html', context)