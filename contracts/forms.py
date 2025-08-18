from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import NegotiationThread, ChecklistItem

User = get_user_model()


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')


class NegotiationThreadForm(forms.ModelForm):
    class Meta:
        model = NegotiationThread
        fields = ['round_number', 'internal_note', 'external_note', 'attachment']
        widgets = {
            'round_number': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm'}),
            'internal_note': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm', 'rows': 3}),
            'external_note': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm', 'rows': 3}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'mt-1 block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none'}),
        }

class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ['text']
        widgets = {
            'text': forms.TextInput(attrs={'placeholder': 'New item description...'}),
        }


from .models import Workflow, WorkflowTemplate

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
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'placeholder': 'Enter template name...'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md', 'rows': 3, 'placeholder': 'Describe this template'}),
            'contract_type': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contract_type'].required = False
