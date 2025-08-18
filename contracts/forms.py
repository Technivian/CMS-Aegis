from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import (
    ChecklistItem, Workflow, WorkflowTemplate,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk,
    Budget, BudgetExpense
)

User = get_user_model()


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ['title', 'description', 'is_required', 'order']


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
        fields = ['year', 'quarter', 'department', 'total_budget', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class BudgetExpenseForm(forms.ModelForm):
    class Meta:
        model = BudgetExpense
        fields = ['title', 'category', 'amount', 'description', 'date_incurred', 
                 'vendor', 'invoice_number']
        widgets = {
            'date_incurred': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class WorkflowForm(forms.ModelForm):
    class Meta:
        model = Workflow
        fields = ['name', 'contract', 'template']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input-field w-full', 'placeholder': 'Enter workflow name...'}),
            'contract': forms.Select(attrs={'class': 'input-field w-full'}),
            'template': forms.Select(attrs={'class': 'input-field w-full'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure all contracts are available
        from .models import Contract
        self.fields['contract'].queryset = Contract.objects.all()
        self.fields['template'].queryset = WorkflowTemplate.objects.filter(is_active=True)
        self.fields['template'].required = False


class WorkflowTemplateForm(forms.ModelForm):
    class Meta:
        model = WorkflowTemplate
        fields = ['name', 'description', 'contract_type']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contract_type'].required = False





class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ['title', 'description', 'is_completed']


class WorkflowForm(forms.ModelForm):
    class Meta:
        model = Workflow
        fields = ['title', 'description', 'template']


class WorkflowTemplateForm(forms.ModelForm):
    class Meta:
        model = WorkflowTemplate
        fields = ['name', 'description', 'category']


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['year', 'quarter', 'department', 'allocated_amount', 'description']


class TrademarkRequestForm(forms.ModelForm):
    class Meta:
        model = TrademarkRequest
        fields = ['mark_text', 'description', 'goods_services', 'filing_basis']


class LegalTaskForm(forms.ModelForm):
    class Meta:
        model = LegalTask
        fields = ['title', 'description', 'priority', 'due_date', 'assigned_to']


class RiskLogForm(forms.ModelForm):
    class Meta:
        model = RiskLog
        fields = ['title', 'description', 'risk_level', 'mitigation_strategy']


class ComplianceChecklistForm(forms.ModelForm):
    class Meta:
        model = ComplianceChecklist
        fields = ['title', 'description', 'regulation_type']


class DueDiligenceProcessForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceProcess
        fields = ['title', 'transaction_type', 'target_company', 'deal_value', 'start_date', 'target_completion_date', 'lead_attorney', 'description']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'target_completion_date': forms.DateInput(attrs={'type': 'date'}),
        }


class DueDiligenceTaskForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceTask
        fields = ['title', 'category', 'description', 'assigned_to', 'due_date', 'notes']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class DueDiligenceRiskForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceRisk
        fields = ['title', 'category', 'description', 'risk_level', 'likelihood', 'impact', 'mitigation_strategy', 'owner', 'target_resolution_date']
        widgets = {
            'target_resolution_date': forms.DateInput(attrs={'type': 'date'}),
        }


class BudgetExpenseForm(forms.ModelForm):
    class Meta:
        model = BudgetExpense
        fields = ['description', 'amount', 'category', 'date', 'receipt_url']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }
