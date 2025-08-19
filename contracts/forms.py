from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from .models import (
    Contract, LegalTask, RiskLog, ComplianceChecklist, ChecklistItem,
    TrademarkRequest, Workflow, WorkflowStep, WorkflowTemplate,
    WorkflowTemplateStep, Budget, BudgetExpense, DueDiligenceProcess,
    DueDiligenceTask, DueDiligenceRisk, NegotiationThread, Tag
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
        fields = ['round_number', 'internal_note', 'external_note', 'attachment']
        widgets = {
            'internal_note': forms.Textarea(attrs={'rows': 3}),
            'external_note': forms.Textarea(attrs={'rows': 3}),
        }


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    notifications = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2")

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return username

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The two password fields didn't match.")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
        return user


class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full pl-12 pr-4 py-4 border-2 border-border rounded-xl focus:border-primary-500 focus:ring-4 focus:ring-primary-100 transition-all duration-200 bg-white text-primary-700 placeholder-muted',
            'placeholder': 'Enter your email address or username'
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full pl-12 pr-4 py-4 border-2 border-border rounded-xl focus:border-primary-500 focus:ring-4 focus:ring-primary-100 transition-all duration-200 bg-white text-primary-700 placeholder-muted',
            'placeholder': 'Enter your password'
        })
    )

    error_messages = {
        'invalid_login': (
            "Please enter a correct email/username and password. Note that both "
            "fields may be case-sensitive."
        ),
        'inactive': "This account is inactive.",
    }


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