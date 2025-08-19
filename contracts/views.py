from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.views.generic import CreateView, ListView, DetailView, UpdateView, View
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib import messages
from .forms import CustomUserCreationForm
from .models import (
    Contract, TrademarkRequest, LegalTask, RiskLog,
    ComplianceChecklist, Workflow, WorkflowTemplate,
    DueDiligenceProcess, Budget
)

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

@login_required
def dashboard(request):
    return render(request, 'dashboard.html')

@login_required
def profile(request):
    return render(request, 'profile.html')



# Contract Views
class ContractListView(LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/contract_list.html'
    context_object_name = 'contracts'
    paginate_by = 25

class ContractDetailView(LoginRequiredMixin, DetailView):
    model = Contract
    template_name = 'contracts/contract_detail.html'
    context_object_name = 'contract'

class ContractCreateView(LoginRequiredMixin, CreateView):
    model = Contract
    template_name = 'contracts/contract_form.html'
    fields = ['title', 'counterparty', 'status', 'contract_type', 'description']

    def get_success_url(self):
        return reverse('contracts:contract_detail', kwargs={'pk': self.object.pk})

class ContractUpdateView(LoginRequiredMixin, UpdateView):
    model = Contract
    template_name = 'contracts/contract_form.html'
    fields = ['title', 'counterparty', 'status', 'contract_type', 'description']

    def get_success_url(self):
        return reverse('contracts:contract_detail', kwargs={'pk': self.object.pk})

class AddNegotiationNoteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk)
        # Add negotiation note logic here
        messages.success(request, 'Note added successfully')
        return redirect('contracts:contract_detail', pk=pk)

# Trademark Views
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
    template_name = 'contracts/trademark_request_form.html'
    fields = ['name', 'description', 'status']

class TrademarkRequestUpdateView(LoginRequiredMixin, UpdateView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_form.html'
    fields = ['name', 'description', 'status']

# Legal Task Views
class LegalTaskKanbanView(LoginRequiredMixin, ListView):
    model = LegalTask
    template_name = 'contracts/legal_task_board.html'
    context_object_name = 'tasks'

class LegalTaskCreateView(LoginRequiredMixin, CreateView):
    model = LegalTask
    template_name = 'contracts/legal_task_form.html'
    fields = ['title', 'description', 'status', 'priority', 'assigned_to']

class LegalTaskUpdateView(LoginRequiredMixin, UpdateView):
    model = LegalTask
    template_name = 'contracts/legal_task_form.html'
    fields = ['title', 'description', 'status', 'priority', 'assigned_to']

# Risk Log Views
class RiskLogListView(LoginRequiredMixin, ListView):
    model = RiskLog
    template_name = 'contracts/risk_log_list.html'
    context_object_name = 'risks'

class RiskLogCreateView(LoginRequiredMixin, CreateView):
    model = RiskLog
    template_name = 'contracts/risk_log_form.html'
    fields = ['title', 'description', 'severity', 'likelihood']

class RiskLogUpdateView(LoginRequiredMixin, UpdateView):
    model = RiskLog
    template_name = 'contracts/risk_log_form.html'
    fields = ['title', 'description', 'severity', 'likelihood']

# Compliance Checklist Views
class ComplianceChecklistListView(LoginRequiredMixin, ListView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_list.html'
    context_object_name = 'checklists'

class ComplianceChecklistDetailView(LoginRequiredMixin, DetailView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_detail.html'
    context_object_name = 'checklist'

class ComplianceChecklistCreateView(LoginRequiredMixin, CreateView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_form.html'
    fields = ['title', 'description']

class ComplianceChecklistUpdateView(LoginRequiredMixin, UpdateView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_form.html'
    fields = ['title', 'description']

class ToggleChecklistItemView(LoginRequiredMixin, View):
    def post(self, request, pk):
        # Toggle checklist item logic
        return JsonResponse({'success': True})

class AddChecklistItemView(LoginRequiredMixin, View):
    def post(self, request, pk):
        # Add checklist item logic
        return JsonResponse({'success': True})

# Workflow Views
class WorkflowDashboardView(LoginRequiredMixin, ListView):
    model = Workflow
    template_name = 'contracts/workflow_dashboard.html'
    context_object_name = 'workflows'

class WorkflowTemplateListView(LoginRequiredMixin, ListView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_list.html'
    context_object_name = 'templates'

class WorkflowCreateView(LoginRequiredMixin, CreateView):
    model = Workflow
    template_name = 'contracts/workflow_form.html'
    fields = ['title', 'description']

class WorkflowTemplateCreateView(LoginRequiredMixin, CreateView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_form.html'
    fields = ['title', 'description']

class WorkflowDetailView(LoginRequiredMixin, DetailView):
    model = Workflow
    template_name = 'contracts/workflow_detail.html'
    context_object_name = 'workflow'

class WorkflowStepUpdateView(LoginRequiredMixin, UpdateView):
    model = Workflow
    template_name = 'contracts/workflow_step_form.html'
    fields = ['title', 'description']

class WorkflowStepCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        # Complete workflow step logic
        return JsonResponse({'success': True})

# Repository and other views
class RepositoryView(LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/repository.html'
    context_object_name = 'contracts'

# Due Diligence Views
class DueDiligenceListView(LoginRequiredMixin, ListView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_list.html'
    context_object_name = 'due_diligences'

class DueDiligenceCreateView(LoginRequiredMixin, CreateView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_form.html'
    fields = ['title', 'transaction_type', 'target_company', 'deal_value', 'start_date', 'target_completion_date', 'description']

class DueDiligenceDetailView(LoginRequiredMixin, DetailView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_form.html'
    context_object_name = 'due_diligence'

class DueDiligenceUpdateView(LoginRequiredMixin, UpdateView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_form.html'
    fields = ['title', 'transaction_type', 'target_company', 'deal_value', 'start_date', 'target_completion_date', 'description']

class AddDueDiligenceItemView(LoginRequiredMixin, View):
    def post(self, request, pk):
        return JsonResponse({'success': True})

class AddDueDiligenceRiskView(LoginRequiredMixin, View):
    def post(self, request, pk):
        return JsonResponse({'success': True})

# Budget Views
class BudgetListView(LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'contracts/budget_list.html'
    context_object_name = 'budgets'

class BudgetCreateView(LoginRequiredMixin, CreateView):
    model = Budget
    template_name = 'contracts/budget_form.html'
    fields = ['title', 'description']

class BudgetDetailView(LoginRequiredMixin, DetailView):
    model = Budget
    template_name = 'contracts/budget_form.html'
    context_object_name = 'budget'

class BudgetUpdateView(LoginRequiredMixin, UpdateView):
    model = Budget
    template_name = 'contracts/budget_form.html'
    fields = ['title', 'description']

class AddExpenseView(LoginRequiredMixin, View):
    def post(self, request, pk):
        return JsonResponse({'success': True})

# Function-based views referenced in URLs
@login_required
def workflow_create(request):
    return render(request, 'contracts/workflow_form.html')

@login_required
def workflow_template_create(request):
    return render(request, 'contracts/workflow_template_form.html')

@login_required
def workflow_template_list(request):
    return render(request, 'contracts/workflow_template_list.html')

@require_http_methods(["POST"])
@login_required
def toggle_dd_item(request, pk):
    return JsonResponse({'success': True})