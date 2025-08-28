from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import (
    Contract, NegotiationThread, TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist, ChecklistItem,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk, Budget, BudgetExpense
)

User = get_user_model()


class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ['title', 'content', 'status']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 10}),
        }


class NegotiationThreadForm(forms.ModelForm):
    class Meta:
        model = NegotiationThread
        fields = ['title', 'content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 5}),
        }


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ['title', 'description', 'is_completed', 'order']


class DueDiligenceProcessForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceProcess
        fields = ['title', 'transaction_type', 'target_company', 'deal_value',
                 'lead_attorney', 'start_date', 'target_completion_date', 'description']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'target_completion_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }


class DueDiligenceTaskForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceTask
        fields = ['title', 'category', 'description', 'assigned_to', 'due_date', 'notes']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class DueDiligenceRiskForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceRisk
        fields = ['title', 'category', 'description', 'risk_level', 'likelihood',
                 'impact', 'mitigation_strategy', 'owner', 'target_resolution_date']
        widgets = {
            'target_resolution_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'mitigation_strategy': forms.Textarea(attrs={'rows': 3}),
        }


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['year', 'quarter', 'department', 'allocated_amount', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class BudgetExpenseForm(forms.ModelForm):
    class Meta:
        model = BudgetExpense
        fields = ['description', 'amount', 'category', 'date', 'receipt_url']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }


class WorkflowForm(forms.ModelForm):
    class Meta:
        model = Workflow
        fields = ['title', 'description', 'template']


class WorkflowTemplateForm(forms.ModelForm):
    class Meta:
        model = WorkflowTemplate
        fields = ['name', 'description', 'category']


class TrademarkRequestForm(forms.ModelForm):
    class Meta:
        model = TrademarkRequest
        fields = ['mark_text', 'description', 'goods_services', 'filing_basis']


class LegalTaskForm(forms.ModelForm):
    class Meta:
        model = LegalTask
        fields = ['title', 'description', 'priority', 'due_date', 'assigned_to']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class RiskLogForm(forms.ModelForm):
    class Meta:
        model = RiskLog
        fields = ['title', 'description', 'risk_level', 'mitigation_strategy']


class ComplianceChecklistForm(forms.ModelForm):
    class Meta:
        model = ComplianceChecklist
        fields = ['title', 'description', 'regulation_type']