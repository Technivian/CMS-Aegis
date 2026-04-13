from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import (
    CareCase, PlacementRequest, CareTask, CareSignal,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep,
    CaseIntakeProcess, IntakeTask, CaseRiskSignal, Budget, BudgetExpense,
    Client, CareConfiguration, Document, TrustAccount,
    Deadline, UserProfile, CaseAssessment,
    OrganizationInvitation,
    CareCategoryMain,
    MunicipalityConfiguration, RegionalConfiguration,
)

User = get_user_model()

TAILWIND_INPUT = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm'
TAILWIND_SELECT = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm bg-white'
TAILWIND_TEXTAREA = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm'
TAILWIND_CHECKBOX = 'h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
TAILWIND_FILE = 'w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={'class': TAILWIND_INPUT}))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={'class': TAILWIND_INPUT}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': TAILWIND_INPUT}))

    class Meta:
        model = UserProfile
        fields = ['role', 'phone', 'department', 'bio']
        widgets = {
            'role': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'phone': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'department': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'bio': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }
        labels = {
            'role': 'Rol',
            'phone': 'Telefoon',
            'department': 'Team / afdeling',
            'bio': 'Korte profielnotitie',
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'client_type', 'status', 'email', 'phone', 'address', 'city',
                  'state', 'zip_code', 'country', 'tax_id', 'website', 'industry',
                  'primary_contact', 'primary_contact_email', 'primary_contact_phone',
                  'responsible_coordinator', 'intake_coordinator', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'client_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'email': forms.EmailInput(attrs={'class': TAILWIND_INPUT}),
            'phone': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'address': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'city': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'state': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'zip_code': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'country': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'tax_id': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'website': forms.URLInput(attrs={'class': TAILWIND_INPUT}),
            'industry': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'primary_contact': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'primary_contact_email': forms.EmailInput(attrs={'class': TAILWIND_INPUT}),
            'primary_contact_phone': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'responsible_coordinator': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'intake_coordinator': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }
        labels = {
            'name': 'Naam zorgaanbieder',
            'client_type': 'Type aanbieder',
            'status': 'Beschikbaarheidsstatus',
            'industry': 'Specialisatie',
            'responsible_coordinator': 'Casusregisseur',
            'intake_coordinator': 'Backoffice contact',
            'notes': 'Notities en voorwaarden',
        }


class CareConfigurationForm(forms.ModelForm):
    class Meta:
        model = CareConfiguration
        fields = [
            'title',
            'scope',
            'is_active',
            'care_domains',
            'linked_providers',
            'max_wait_days',
            'priority_rules',
            'responsible_care_coordinator',
            'responsible_team',
            'intake_creator',
            'open_date',
            'description',
            'notes',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. Gemeente Utrecht'}),
            'scope': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'care_domains': forms.SelectMultiple(attrs={'class': TAILWIND_SELECT}),
            'linked_providers': forms.SelectMultiple(attrs={'class': TAILWIND_SELECT}),
            'max_wait_days': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': '0'}),
            'priority_rules': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'responsible_care_coordinator': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'responsible_team': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. Team Jeugd Noord'}),
            'intake_creator': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'open_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }
        labels = {
            'title': 'Gemeente / regio naam',
            'scope': 'Type',
            'is_active': 'Actief',
            'care_domains': 'Zorgdomeinen',
            'linked_providers': 'Aanbieders',
            'max_wait_days': 'Max wachttijd (dagen)',
            'priority_rules': 'Prioriteitsregels (optioneel)',
            'responsible_care_coordinator': 'Verantwoordelijke',
            'responsible_team': 'Verantwoordelijk team',
            'intake_creator': 'Back-up verantwoordelijke',
            'open_date': 'Startdatum',
            'description': 'Configuratiebeschrijving',
            'notes': 'Regienotities',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['care_domains'].queryset = CareCategoryMain.objects.filter(is_active=True).order_by('order', 'name')
        self.fields['linked_providers'].queryset = Client.objects.filter(status='ACTIVE').order_by('name')
        self.fields['care_domains'].required = False
        self.fields['linked_providers'].required = False

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'document_type', 'status', 'description', 'file',
                  'contract', 'matter', 'client', 'tags', 'is_privileged', 'is_confidential']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'document_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'file': forms.FileInput(attrs={'class': TAILWIND_FILE}),
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'tags': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Tags gescheiden door komma\'s'}),
            'is_privileged': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'is_confidential': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }
        labels = {
            'title': 'Documenttitel',
            'document_type': 'Documentsoort',
            'status': 'Documentstatus',
            'description': 'Omschrijving',
            'file': 'Bestand',
            'contract': 'Casus',
            'matter': 'Configuratie',
            'client': 'Aanbieder',
            'tags': 'Tags',
            'is_privileged': 'Beperkte inzage',
            'is_confidential': 'Vertrouwelijk',
        }


class TrustAccountForm(forms.ModelForm):
    class Meta:
        model = TrustAccount
        fields = ['provider', 'region', 'care_type', 'wait_days', 'open_slots', 'waiting_list_size', 'notes']
        widgets = {
            'provider': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'region': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. Regio Midden'}),
            'care_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'wait_days': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': '0'}),
            'open_slots': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': '0'}),
            'waiting_list_size': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': '0'}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }
        labels = {
            'provider': 'Aanbieder',
            'region': 'Regio / gemeente',
            'care_type': 'Zorgtype',
            'wait_days': 'Gemiddelde wachttijd (dagen)',
            'open_slots': 'Beschikbare plekken',
            'waiting_list_size': 'Wachtlijst (aantal)',
            'notes': 'Toelichting',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['provider'].required = True
        self.fields['region'].required = True


class DeadlineForm(forms.ModelForm):
    class Meta:
        model = Deadline
        fields = [
            'due_diligence_process',
            'title',
            'task_type',
            'description',
            'due_date',
            'due_time',
            'priority',
            'assigned_to',
        ]
        widgets = {
            'due_diligence_process': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'task_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'priority': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'due_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'due_time': forms.TimeInput(attrs={'class': TAILWIND_INPUT, 'type': 'time'}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }
        labels = {
            'due_diligence_process': 'Casus selecteren',
            'title': 'Taak',
            'task_type': 'Taaksoort',
            'description': 'Beschrijving',
            'due_date': 'Streefdatum',
            'due_time': 'Tijd (optioneel)',
            'priority': 'Prioriteit',
            'assigned_to': 'Toegewezen aan',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_diligence_process'].required = True
        self.fields['due_time'].required = False


class CaseAssessmentForm(forms.ModelForm):
    """Form for care case assessment (Casusbeoordeling)"""
    
    # Multi-select for care signals
    risk_signals = forms.MultipleChoiceField(
        choices=CaseAssessment.RiskSignal.choices,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'space-y-2'}),
        required=False,
        label='Signalen'
    )
    
    class Meta:
        model = CaseAssessment
        fields = [
            'due_diligence_process',
            'assessment_status',
            'risk_signals',
            'matching_ready',
            'reason_not_ready',
            'notes',
        ]
        widgets = {
            'due_diligence_process': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'assessment_status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matching_ready': forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded'}),
            'reason_not_ready': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.risk_signals:
            # Convert comma-separated string back to list for multi-select display.
            self.fields['risk_signals'].initial = [
                s.strip() for s in self.instance.risk_signals.split(',')
            ]
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        # Convert list of selected signals to comma-separated storage.
        risk_signals = self.cleaned_data.get('risk_signals', [])
        instance.risk_signals = ','.join(risk_signals) if risk_signals else ''
        if commit:
            instance.save()
        return instance


class CareCaseForm(forms.ModelForm):
    class Meta:
        model = CareCase
        fields = ['title', 'contract_type', 'content', 'status', 'preferred_provider', 'value', 'currency',
                  'risk_level', 'lifecycle_stage',
                  'start_date', 'end_date', 'renewal_date', 'auto_renew', 'notice_period_days',
                  'termination_notice_date', 'client', 'matter']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'contract_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'content': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 10}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'preferred_provider': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'value': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'currency': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'risk_level': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'lifecycle_stage': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'start_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'renewal_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'auto_renew': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'notice_period_days': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
            'termination_notice_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }
        labels = {
            'title': 'Casustitel',
            'contract_type': 'Type zorgvraag',
            'content': 'Intake samenvatting',
            'status': 'Casusstatus',
            'preferred_provider': 'Voorkeursaanbieder',
            'value': 'Complexiteitsscore',
            'risk_level': 'Urgentie',
            'start_date': 'Intakedatum',
            'end_date': 'Doeldatum plaatsing',
            'renewal_date': 'Herbeoordelingsdatum',
            'auto_renew': 'Vervolgtraject verwacht',
            'notice_period_days': 'Escalatietermijn (dagen)',
            'termination_notice_date': 'Afsluitdatum',
            'client': 'Zorgaanbieder',
            'matter': 'Gemeente / regio',
        }


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')


class OrganizationInvitationForm(forms.ModelForm):
    class Meta:
        model = OrganizationInvitation
        fields = ['email', 'role']
        widgets = {
            'email': forms.EmailInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'naam@organisatie.nl'}),
            'role': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }
        labels = {
            'email': 'E-mailadres',
            'role': 'Organisatierol',
        }

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class CaseIntakeProcessForm(forms.ModelForm):
    class Meta:
        model = CaseIntakeProcess
        fields = [
            'title',
            'start_date',
            'target_completion_date',
            'care_category_main',
            'care_category_sub',
            'assessment_summary',
            'urgency',
            'complexity',
            'preferred_care_form',
            'client_age_category',
            'family_situation',
            'school_work_status',
            'case_coordinator',
            'description',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'start_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'target_completion_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'care_category_main': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'care_category_sub': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'assessment_summary': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'urgency': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'complexity': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'preferred_care_form': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'client_age_category': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'family_situation': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'school_work_status': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'case_coordinator': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
        }
        labels = {
            'title': 'Casustitel',
            'start_date': 'Startdatum casus',
            'target_completion_date': 'Doeldatum matchbesluit',
            'care_category_main': 'Hoofdcategorie zorgvraag',
            'care_category_sub': 'Subcategorie zorgvraag',
            'assessment_summary': 'Intake samenvatting',
            'urgency': 'Urgentie',
            'complexity': 'Complexiteit',
            'preferred_care_form': 'Gewenste zorgvorm',
            'client_age_category': 'Leeftijdscategorie cliënt',
            'family_situation': 'Gezinssituatie',
            'school_work_status': 'School- / werkstatus',
            'case_coordinator': 'Casusregisseur',
            'description': 'Aanvullende opmerkingen',
        }


class IntakeTaskForm(forms.ModelForm):
    class Meta:
        model = IntakeTask
        fields = ['title', 'category', 'description', 'assigned_to', 'due_date', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'category': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'due_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


class CaseRiskSignalForm(forms.ModelForm):
    class Meta:
        model = CaseRiskSignal
        fields = ['title', 'category', 'description', 'risk_level', 'likelihood',
                 'impact', 'mitigation_strategy', 'owner', 'target_resolution_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'category': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'risk_level': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'likelihood': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'impact': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'mitigation_strategy': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'owner': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'target_resolution_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
        }


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = [
            'scope_type',
            'scope_name',
            'target_group',
            'care_type',
            'allocated_amount',
            'year',
            'linked_providers',
            'linked_cases',
            'linked_placements',
            'description',
        ]
        widgets = {
            'scope_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'scope_name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'target_group': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'care_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'year': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
            'allocated_amount': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'linked_providers': forms.SelectMultiple(attrs={'class': TAILWIND_SELECT}),
            'linked_cases': forms.SelectMultiple(attrs={'class': TAILWIND_SELECT}),
            'linked_placements': forms.SelectMultiple(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['linked_providers'].required = False
        self.fields['linked_cases'].required = False
        self.fields['linked_placements'].required = False

        self.fields['linked_providers'].queryset = Client.objects.filter(
            provider_profile__isnull=False,
            status='ACTIVE'
        ).order_by('name')
        self.fields['linked_cases'].queryset = CaseIntakeProcess.objects.order_by('-updated_at')
        self.fields['linked_placements'].queryset = PlacementRequest.objects.order_by('-updated_at')


class BudgetExpenseForm(forms.ModelForm):
    class Meta:
        model = BudgetExpense
        fields = ['description', 'amount', 'category', 'date', 'receipt_url']
        widgets = {
            'description': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'amount': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'category': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'receipt_url': forms.URLInput(attrs={'class': TAILWIND_INPUT}),
        }


class WorkflowForm(forms.ModelForm):
    class Meta:
        model = Workflow
        fields = ['title', 'description', 'template', 'contract']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'template': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }
        labels = {
            'title': 'Naam matchingflow',
            'description': 'Toelichting processtap',
            'template': 'Flowtemplate',
            'contract': 'Casus',
        }


class WorkflowTemplateForm(forms.ModelForm):
    class Meta:
        model = WorkflowTemplate
        fields = ['name', 'description', 'category']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'category': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }
        labels = {
            'name': 'Template naam',
            'description': 'Template beschrijving',
            'category': 'Template categorie',
        }


class PlacementRequestForm(forms.ModelForm):
    """Indicatieformulier voor zorgtoewijzing."""

    class Meta:
        model = PlacementRequest
        fields = [
            'due_diligence_process',
            'proposed_provider',
            'selected_provider',
            'care_form',
            'start_date',
            'duration_weeks',
            'status',
            'decision_notes',
        ]
        widgets = {
            'due_diligence_process': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'proposed_provider': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'selected_provider': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'care_form': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'start_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'duration_weeks': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': 1, 'placeholder': 'Bijv. 12'}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'decision_notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_diligence_process'].label = 'Casus'
        self.fields['decision_notes'].label = 'Notities'

        self.fields['proposed_provider'].queryset = Client.objects.filter(
            provider_profile__isnull=False,
            status='ACTIVE'
        ).order_by('name')
        self.fields['selected_provider'].queryset = self.fields['proposed_provider'].queryset

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Keep compatibility storage fields populated while the schema catches up.
        if instance.intake:
            instance.mark_text = instance.mark_text or f'Indicatie {instance.intake.title}'
            instance.description = instance.description or instance.decision_notes or 'Indicatiebesluit'

        if commit:
            instance.save()
        return instance


class CareTaskForm(forms.ModelForm):
    class Meta:
        model = CareTask
        fields = ['title', 'description', 'priority', 'due_date', 'assigned_to', 'case_record', 'configuration']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'priority': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'due_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'case_record': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'configuration': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }
        labels = {
            'title': 'Taaktitel',
            'description': 'Taakomschrijving',
            'priority': 'Prioriteit',
            'due_date': 'Streefdatum',
            'assigned_to': 'Toegewezen aan',
            'case_record': 'Casus',
            'configuration': 'Configuratie',
        }


class CareSignalForm(forms.ModelForm):
    class Meta:
        model = CareSignal
        fields = [
            'due_diligence_process',
            'signal_type',
            'risk_level',
            'status',
            'description',
            'follow_up',
            'assigned_to',
        ]
        widgets = {
            'due_diligence_process': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'signal_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'risk_level': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'follow_up': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }
        labels = {
            'due_diligence_process': 'Casus',
            'signal_type': 'Type signaal',
            'risk_level': 'Signaalniveau',
            'status': 'Status',
            'description': 'Beschrijving',
            'follow_up': 'Vervolgactie',
            'assigned_to': 'Toegewezen aan',
        }


# ============================================
# MUNICIPALITY & REGIONAL CONFIGURATION FORMS
# ============================================

class MunicipalityConfigurationForm(forms.ModelForm):
    class Meta:
        model = MunicipalityConfiguration
        fields = [
            'municipality_name', 'municipality_code', 'status',
            'care_domains', 'linked_providers',
            'max_wait_days', 'priority_rules',
            'responsible_coordinator', 'notes'
        ]
        widgets = {
            'municipality_name': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. Amsterdam'}),
            'municipality_code': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. 0363'}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'care_domains': forms.CheckboxSelectMultiple(attrs={'class': 'h-4 w-4'}),
            'linked_providers': forms.CheckboxSelectMultiple(attrs={'class': 'h-4 w-4'}),
            'max_wait_days': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. 14'}),
            'priority_rules': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4, 'placeholder': 'Prioriteringsregels...'}),
            'responsible_coordinator': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3, 'placeholder': 'Aanvullende notities...'}),
        }
        labels = {
            'municipality_name': 'Gemeente',
            'municipality_code': 'Gemeentecode',
            'status': 'Status',
            'care_domains': 'Zorgdomeinen',
            'linked_providers': 'Gekoppelde aanbieders',
            'max_wait_days': 'Maximale wachttijd (dagen)',
            'priority_rules': 'Prioriteringsregels',
            'responsible_coordinator': 'Verantwoordelijke',
            'notes': 'Notities',
        }


class RegionalConfigurationForm(forms.ModelForm):
    class Meta:
        model = RegionalConfiguration
        fields = [
            'region_name', 'region_code', 'status',
            'served_municipalities', 'care_domains', 'linked_providers',
            'max_wait_days', 'priority_rules',
            'responsible_coordinator', 'notes'
        ]
        widgets = {
            'region_name': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. Metropoolregio Amsterdam'}),
            'region_code': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. MRA'}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'served_municipalities': forms.CheckboxSelectMultiple(attrs={'class': 'h-4 w-4'}),
            'care_domains': forms.CheckboxSelectMultiple(attrs={'class': 'h-4 w-4'}),
            'linked_providers': forms.CheckboxSelectMultiple(attrs={'class': 'h-4 w-4'}),
            'max_wait_days': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Bijv. 14'}),
            'priority_rules': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4, 'placeholder': 'Prioriteringsregels...'}),
            'responsible_coordinator': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3, 'placeholder': 'Aanvullende notities...'}),
        }
        labels = {
            'region_name': 'Regio',
            'region_code': 'Regio code',
            'status': 'Status',
            'served_municipalities': 'Bediende gemeenten',
            'care_domains': 'Zorgdomeinen',
            'linked_providers': 'Gekoppelde aanbieders',
            'max_wait_days': 'Maximale wachttijd (dagen)',
            'priority_rules': 'Prioriteringsregels',
            'responsible_coordinator': 'Verantwoordelijke',
            'notes': 'Notities',
        }


# Deprecated aliases removed: concrete form classes above are authoritative.
