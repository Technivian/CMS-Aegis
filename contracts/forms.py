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
