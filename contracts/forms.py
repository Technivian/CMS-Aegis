from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from .permissions import can_manage_organization
from .services.clause_policy import validate_clause_policy
from .services.clause_variants import resolve_clause_variant
from .services.contract_policies import get_required_fields_for_contract_type
from .services.contract_lifecycle import can_transition_lifecycle_stage
from .tenancy import scope_queryset_for_organization
from .models import (
    Contract, NegotiationThread, TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist, ChecklistItem,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk, Budget, BudgetExpense,
    Client, Matter, Document, TimeEntry, Invoice, TrustAccount, TrustTransaction,
    Deadline, UserProfile, ConflictCheck,
    Counterparty, ClauseCategory, ClauseTemplate, EthicalWall, SignatureRequest,
    DataInventoryRecord, DSARRequest, Subprocessor, TransferRecord, RetentionPolicy,
    LegalHold, ApprovalRule, ApprovalRequest,
    ClausePlaybook, ClauseVariant,
    DocumentOCRReview,
    Organization,
    OrganizationInvitation,
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
    mfa_enrollment_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'autocomplete': 'one-time-code', 'inputmode': 'numeric'}),
    )
    mfa_recovery_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'autocomplete': 'one-time-code', 'inputmode': 'numeric'}),
    )

    class Meta:
        model = UserProfile
        fields = ['role', 'phone', 'bar_number', 'department', 'hourly_rate', 'bio', 'mfa_enabled']
        widgets = {
            'role': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'phone': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'bar_number': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'department': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'hourly_rate': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'bio': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'mfa_enabled': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }


class OrganizationIdentitySettingsForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            'identity_provider',
            'saml_entity_id',
            'saml_sso_url',
            'saml_slo_url',
            'saml_metadata_url',
            'saml_x509_certificate',
            'scim_enabled',
        ]
        widgets = {
            'identity_provider': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'saml_entity_id': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'saml_sso_url': forms.URLInput(attrs={'class': TAILWIND_INPUT}),
            'saml_slo_url': forms.URLInput(attrs={'class': TAILWIND_INPUT}),
            'saml_metadata_url': forms.URLInput(attrs={'class': TAILWIND_INPUT}),
            'saml_x509_certificate': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 6}),
            'scim_enabled': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'client_type', 'status', 'email', 'phone', 'address', 'city',
                  'state', 'zip_code', 'country', 'tax_id', 'website', 'industry',
                  'primary_contact', 'primary_contact_email', 'primary_contact_phone',
                  'responsible_attorney', 'originating_attorney', 'notes']
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
            'responsible_attorney': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'originating_attorney': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


class MatterForm(forms.ModelForm):
    class Meta:
        model = Matter
        fields = ['title', 'client', 'practice_area', 'status', 'responsible_attorney',
                  'originating_attorney', 'billing_type', 'budget_amount', 'open_date',
                  'statute_of_limitations', 'court_name', 'case_number', 'opposing_party',
                  'opposing_counsel', 'is_confidential', 'description', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'practice_area': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'responsible_attorney': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'originating_attorney': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'billing_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'budget_amount': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'open_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'statute_of_limitations': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'court_name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'case_number': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'opposing_party': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'opposing_counsel': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'is_confidential': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


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
            'tags': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Comma-separated tags'}),
            'is_privileged': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'is_confidential': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }


class DocumentOCRReviewForm(forms.ModelForm):
    class Meta:
        model = DocumentOCRReview
        fields = ['status', 'extracted_text', 'confidence_score', 'review_notes']
        widgets = {
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'extracted_text': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 8}),
            'confidence_score': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01', 'min': '0', 'max': '1'}),
            'review_notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        extracted_text = (cleaned_data.get('extracted_text') or '').strip()
        if status == DocumentOCRReview.Status.VERIFIED and not extracted_text:
            self.add_error('extracted_text', 'Verified OCR reviews must include extracted text.')
        return cleaned_data


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ['matter', 'date', 'hours', 'description', 'activity_type', 'rate', 'is_billable']
        widgets = {
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'hours': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.25', 'min': '0.1'}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'activity_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'rate': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'is_billable': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }

    def clean_hours(self):
        hours = self.cleaned_data.get('hours')
        if hours is None:
            return hours
        if hours < 0.1:
            raise forms.ValidationError('Hours must be at least 0.1.')
        if hours > 999.99:
            raise forms.ValidationError('Hours cannot exceed 999.99.')
        return hours


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['client', 'matter', 'issue_date', 'due_date', 'subtotal',
                  'tax_rate', 'notes', 'payment_terms']
        widgets = {
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'issue_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'subtotal': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'tax_rate': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'payment_terms': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
        }

    def clean_tax_rate(self):
        tax_rate = self.cleaned_data.get('tax_rate')
        if tax_rate is None:
            return tax_rate
        if tax_rate < 0:
            raise forms.ValidationError('Tax rate cannot be negative.')
        if tax_rate > 100:
            raise forms.ValidationError('Tax rate cannot exceed 100%.')
        return tax_rate

    def clean(self):
        cleaned_data = super().clean()
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        if issue_date and due_date and due_date < issue_date:
            self.add_error('due_date', 'Due date must be on or after the issue date.')
        return cleaned_data


class TrustAccountForm(forms.ModelForm):
    class Meta:
        model = TrustAccount
        fields = ['client', 'matter', 'account_name', 'balance']
        widgets = {
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'account_name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'balance': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
        }


class TrustTransactionForm(forms.ModelForm):
    class Meta:
        model = TrustTransaction
        fields = ['transaction_type', 'amount', 'description', 'reference_number']
        widgets = {
            'transaction_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'amount': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'description': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'reference_number': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
        }


class DeadlineForm(forms.ModelForm):
    class Meta:
        model = Deadline
        fields = ['title', 'description', 'deadline_type', 'priority', 'due_date',
                  'due_time', 'reminder_days', 'matter', 'contract', 'assigned_to']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'deadline_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'priority': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'due_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'due_time': forms.TimeInput(attrs={'class': TAILWIND_INPUT, 'type': 'time'}),
            'reminder_days': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }


class ConflictCheckForm(forms.ModelForm):
    class Meta:
        model = ConflictCheck
        fields = ['client', 'matter', 'checked_party', 'checked_party_type', 'status', 'notes', 'conflicts_found']
        widgets = {
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'checked_party': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'checked_party_type': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'conflicts_found': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


class ContractForm(forms.ModelForm):
    clause_templates = forms.ModelMultipleChoiceField(
        queryset=ClauseTemplate.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': TAILWIND_SELECT, 'size': '8'}),
        help_text='Select clause templates to auto-generate draft content when the content field is left blank.',
    )

    class Meta:
        model = Contract
        fields = ['title', 'contract_type', 'content', 'status', 'counterparty', 'value', 'currency',
                  'governing_law', 'jurisdiction', 'language', 'risk_level',
                  'data_transfer_flag', 'dpa_attached', 'scc_attached', 'lifecycle_stage',
                  'start_date', 'end_date', 'renewal_date', 'auto_renew', 'notice_period_days',
                  'termination_notice_date', 'client', 'matter']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'contract_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'content': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 10}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'counterparty': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'value': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'currency': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'governing_law': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'e.g. State of Delaware, England & Wales'}),
            'jurisdiction': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'e.g. New York, EU'}),
            'language': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'risk_level': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'data_transfer_flag': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'dpa_attached': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'scc_attached': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
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

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        clause_queryset = scope_queryset_for_organization(ClauseTemplate.objects.select_related('category'), organization).order_by('title')
        self.fields['clause_templates'].queryset = clause_queryset
        self.fields['clause_templates'].label_from_instance = self._clause_template_label

    @staticmethod
    def _clause_template_label(clause_template):
        category_name = clause_template.category.name if clause_template.category else 'Uncategorized'
        return f'{clause_template.title} (v{clause_template.version}, {category_name})'

    def _build_clause_draft_contract(self, cleaned_data):
        return Contract(
            contract_type=cleaned_data.get('contract_type') or Contract.ContractType.OTHER,
            governing_law=cleaned_data.get('governing_law') or '',
            jurisdiction=cleaned_data.get('jurisdiction') or '',
            risk_level=cleaned_data.get('risk_level') or Contract.RiskLevel.LOW,
        )

    def _render_clause_section(self, clause_template, draft_contract):
        resolved = resolve_clause_variant(clause_template, draft_contract)
        lines = [clause_template.title]
        if resolved.playbook_name:
            lines.append(f'Resolved playbook: {resolved.playbook_name}')
        base_text = (clause_template.content or '').strip()
        if base_text:
            lines.append('')
            lines.append(base_text)
        negotiation_notes = (resolved.playbook_notes or clause_template.playbook_notes or '').strip()
        if negotiation_notes:
            lines.append('')
            lines.append('Negotiation notes:')
            lines.append(negotiation_notes)
        fallback_position = (resolved.fallback_content or clause_template.fallback_content or '').strip()
        if fallback_position:
            lines.append('')
            lines.append('Fallback position:')
            lines.append(fallback_position)
        return '\n'.join(lines).strip()

    def build_clause_preview_section(self, clause_template):
        draft_contract = self._build_clause_draft_contract(self.cleaned_data)
        resolved = resolve_clause_variant(clause_template, draft_contract)
        badges = []
        if resolved.playbook_name:
            badges.append({'label': resolved.playbook_name, 'tone': 'indigo'})
        scope_label = clause_template.get_jurisdiction_scope_display()
        if scope_label:
            badges.append({'label': scope_label, 'tone': 'blue'})
        if clause_template.is_mandatory:
            badges.append({'label': 'Mandatory', 'tone': 'red'})
        risk_level = (resolved.variant.risk_level if resolved.variant and resolved.variant.risk_level else '').strip()
        if risk_level:
            badges.append({'label': f'{risk_level.title()} risk', 'tone': 'amber'})
        if resolved.playbook_notes or clause_template.playbook_notes:
            badges.append({'label': 'Playbook notes', 'tone': 'emerald'})
        if resolved.fallback_content or clause_template.fallback_content:
            badges.append({'label': 'Fallback available', 'tone': 'slate'})
        return {
            'title': clause_template.title,
            'content': self._render_clause_section(clause_template, draft_contract),
            'source_label': str(clause_template),
            'badges': badges,
            'resolved_playbook': resolved.playbook_name,
            'resolved_scope': scope_label,
            'resolved_risk_level': risk_level,
            'has_fallback': bool(resolved.fallback_content or clause_template.fallback_content),
            'has_playbook_notes': bool(resolved.playbook_notes or clause_template.playbook_notes),
        }

    def _get_draft_sections_from_submission(self):
        if not self.data:
            return []

        raw_count = self.data.get('draft_section_count')
        try:
            section_count = int(raw_count or 0)
        except (TypeError, ValueError):
            section_count = 0

        sections = []
        for index in range(section_count):
            prefix = f'draft_section_{index}_'
            include_value = self.data.get(f'{prefix}include')
            if include_value not in {'on', '1', 'true', 'True', True}:
                continue

            title = (self.data.get(f'{prefix}title') or '').strip()
            content = (self.data.get(f'{prefix}content') or '').strip()
            if not title and not content:
                continue

            try:
                order = int(self.data.get(f'{prefix}order') or index + 1)
            except (TypeError, ValueError):
                order = index + 1

            sections.append({
                'order': order,
                'title': title,
                'content': content,
            })

        sections.sort(key=lambda item: (item['order'], item['title'].lower()))
        return sections

    @staticmethod
    def _render_draft_sections_content(sections):
        rendered_sections = []
        for section in sections:
            block_lines = []
            if section.get('title'):
                block_lines.append(section['title'].strip())
            if section.get('content'):
                block_lines.append(section['content'].strip())
            block = '\n\n'.join(line for line in block_lines if line).strip()
            if block:
                rendered_sections.append(block)
        return '\n\n'.join(rendered_sections).strip()

    def clean(self):
        cleaned_data = super().clean()
        contract_type = cleaned_data.get('contract_type')
        required_fields = get_required_fields_for_contract_type(contract_type)

        for field_name in required_fields:
            value = cleaned_data.get(field_name)
            if value in (None, '', []):
                self.add_error(field_name, f'{field_name.replace("_", " ").capitalize()} is required for this contract type.')

        lifecycle_stage = cleaned_data.get('lifecycle_stage')
        if self.instance and self.instance.pk and lifecycle_stage:
            if not can_transition_lifecycle_stage(self.instance, lifecycle_stage):
                self.add_error(
                    'lifecycle_stage',
                    f'Invalid lifecycle stage transition from {self.instance.lifecycle_stage} to {lifecycle_stage}.',
                )

        draft_sections = self._get_draft_sections_from_submission()
        if draft_sections:
            cleaned_data['content'] = self._render_draft_sections_content(draft_sections)
            cleaned_data['draft_sections'] = draft_sections
            return cleaned_data

        clause_templates = cleaned_data.get('clause_templates') or []
        content = (cleaned_data.get('content') or '').strip()
        if not content and clause_templates:
            draft_contract = self._build_clause_draft_contract(cleaned_data)
            generated_sections = [
                self._render_clause_section(clause_template, draft_contract)
                for clause_template in clause_templates
            ]
            generated_sections = [section for section in generated_sections if section]
            if generated_sections:
                cleaned_data['content'] = '\n\n'.join(generated_sections)

        return cleaned_data


class NegotiationThreadForm(forms.ModelForm):
    class Meta:
        model = NegotiationThread
        fields = ['title', 'content']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'content': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 5}),
        }


class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': TAILWIND_INPUT}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT}))
    remember = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}))

    def clean(self):
        cleaned_data = super().clean()
        username = (cleaned_data.get('username') or '').strip()
        password = cleaned_data.get('password') or ''
        if not username:
            self.add_error('username', 'Username is required.')
        if not password:
            self.add_error('password', 'Password is required.')
        if not username or not password:
            return cleaned_data

        user = User.objects.filter(username__iexact=username).first()
        if user is None or not user.check_password(password):
            raise ValidationError('Invalid username or password.')
        if not user.is_active:
            raise ValidationError('This account is inactive.')

        cleaned_data['user'] = user
        return cleaned_data


class RegistrationForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': TAILWIND_INPUT}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': TAILWIND_INPUT}))
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={'class': TAILWIND_INPUT}))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={'class': TAILWIND_INPUT}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT}))

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('A user with that username already exists.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1') or ''
        password2 = cleaned_data.get('password2') or ''
        if password1 and password2 and password1 != password2:
            raise ValidationError('The two password fields must match.')
        if password1:
            try:
                password_validation.validate_password(password1)
            except ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            first_name=self.cleaned_data.get('first_name', ''),
            last_name=self.cleaned_data.get('last_name', ''),
            password=self.cleaned_data['password1'],
        )
        return user


class OrganizationInvitationForm(forms.ModelForm):
    class Meta:
        model = OrganizationInvitation
        fields = ['email', 'role']
        widgets = {
            'email': forms.EmailInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'name@company.com'}),
            'role': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ['title', 'description', 'is_completed', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'is_completed': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'order': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
        }


class DueDiligenceProcessForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceProcess
        fields = ['title', 'transaction_type', 'target_company', 'deal_value',
                 'lead_attorney', 'start_date', 'target_completion_date', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'transaction_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'target_company': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'deal_value': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'lead_attorney': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'start_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'target_completion_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
        }


# Backward-compatible aliases for older care workflow views.
CareConfigurationForm = MatterForm
MunicipalityConfigurationForm = MatterForm
RegionalConfigurationForm = MatterForm
CaseAssessmentForm = DueDiligenceProcessForm


class DueDiligenceTaskForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceTask
        fields = ['title', 'category', 'description', 'assigned_to', 'due_date', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'category': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'due_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


class DueDiligenceRiskForm(forms.ModelForm):
    class Meta:
        model = DueDiligenceRisk
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
        fields = ['year', 'quarter', 'department', 'allocated_amount', 'description']
        widgets = {
            'year': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
            'quarter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'department': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'allocated_amount': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


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


class WorkflowTemplateForm(forms.ModelForm):
    class Meta:
        model = WorkflowTemplate
        fields = ['name', 'description', 'category']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'category': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }


class WorkflowTemplateStepForm(forms.ModelForm):
    order = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': '1'}),
    )

    class Meta:
        model = WorkflowTemplateStep
        fields = ['name', 'description', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


class WorkflowStepForm(forms.ModelForm):
    order = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': '1'}),
    )

    class Meta:
        model = WorkflowStep
        fields = ['name', 'description', 'status', 'assigned_to', 'due_date', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'due_date': forms.DateTimeInput(attrs={'class': TAILWIND_INPUT, 'type': 'datetime-local'}),
        }


class TrademarkRequestForm(forms.ModelForm):
    class Meta:
        model = TrademarkRequest
        fields = ['mark_text', 'description', 'goods_services', 'filing_basis', 'client', 'matter']
        widgets = {
            'mark_text': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'goods_services': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'filing_basis': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }


class LegalTaskForm(forms.ModelForm):
    class Meta:
        model = LegalTask
        fields = ['title', 'description', 'priority', 'due_date', 'assigned_to', 'contract', 'matter']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'priority': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'due_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }


class RiskLogForm(forms.ModelForm):
    class Meta:
        model = RiskLog
        fields = ['title', 'description', 'risk_level', 'mitigation_plan', 'contract', 'matter']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'risk_level': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'mitigation_plan': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }


class ComplianceChecklistForm(forms.ModelForm):
    class Meta:
        model = ComplianceChecklist
        fields = ['title', 'description', 'regulation_type', 'contract']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'regulation_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }


class CounterpartyForm(forms.ModelForm):
    class Meta:
        model = Counterparty
        fields = ['name', 'entity_type', 'jurisdiction', 'registration_number', 'address',
                  'contact_name', 'contact_email', 'contact_phone', 'website', 'notes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'entity_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'jurisdiction': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'registration_number': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'address': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'contact_name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'contact_email': forms.EmailInput(attrs={'class': TAILWIND_INPUT}),
            'contact_phone': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'website': forms.URLInput(attrs={'class': TAILWIND_INPUT}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }


class ClauseCategoryForm(forms.ModelForm):
    class Meta:
        model = ClauseCategory
        fields = ['name', 'description', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'order': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
        }


class ClauseTemplateForm(forms.ModelForm):
    class Meta:
        model = ClauseTemplate
        fields = ['title', 'category', 'content', 'fallback_content', 'jurisdiction_scope',
                  'is_mandatory', 'applicable_contract_types', 'playbook_notes', 'tags']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'category': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'content': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 8}),
            'fallback_content': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 5}),
            'jurisdiction_scope': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'applicable_contract_types': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'NDA, MSA, SOW'}),
            'playbook_notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'tags': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'comma-separated tags'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        clause = ClauseTemplate(
            title=cleaned_data.get('title') or '',
            content=cleaned_data.get('content') or '',
            fallback_content=cleaned_data.get('fallback_content') or '',
            jurisdiction_scope=cleaned_data.get('jurisdiction_scope') or ClauseTemplate.JurisdictionScope.GLOBAL,
            is_mandatory=cleaned_data.get('is_mandatory') or False,
            applicable_contract_types=cleaned_data.get('applicable_contract_types') or '',
            playbook_notes=cleaned_data.get('playbook_notes') or '',
            tags=cleaned_data.get('tags') or '',
        )
        for issue in validate_clause_policy(clause):
            self.add_error(None, issue)
        return cleaned_data


class ClauseVariantForm(forms.ModelForm):
    class Meta:
        model = ClauseVariant
        fields = ['playbook', 'jurisdiction_scope', 'contract_type', 'risk_level', 'fallback_content', 'playbook_notes', 'priority', 'is_active']
        widgets = {
            'playbook': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'jurisdiction_scope': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'contract_type': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'risk_level': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'fallback_content': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'playbook_notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'priority': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }


class ClausePlaybookForm(forms.ModelForm):
    class Meta:
        model = ClausePlaybook
        fields = ['name', 'description', 'fallback_position', 'jurisdiction_scope', 'risk_level', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'fallback_position': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'jurisdiction_scope': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'risk_level': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }


class EthicalWallForm(forms.ModelForm):
    class Meta:
        model = EthicalWall
        fields = ['name', 'description', 'matter', 'client', 'restricted_users', 'is_active', 'reason', 'expires_at']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'restricted_users': forms.SelectMultiple(attrs={'class': TAILWIND_SELECT, 'size': 5}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'reason': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'expires_at': forms.DateTimeInput(attrs={'class': TAILWIND_INPUT, 'type': 'datetime-local'}),
        }


class SignatureRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = SignatureRequest
        fields = ['contract', 'document', 'signer_name', 'signer_email', 'signer_role', 'status', 'order']
        widgets = {
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'document': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'signer_name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'signer_email': forms.EmailInput(attrs={'class': TAILWIND_INPUT}),
            'signer_role': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'e.g. CEO, General Counsel'}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'order': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
        }

    def clean(self):
        cleaned_data = super().clean()
        new_status = cleaned_data.get('status')
        if not self.instance.pk or not new_status:
            return cleaned_data

        if not self.instance.can_transition_to(new_status):
            self.add_error('status', 'Invalid signature status transition.')
            return cleaned_data

        if new_status != self.instance.status and not self.instance.can_actor_transition(self.actor, new_status):
            self.add_error('status', 'You are not authorized to perform this signature transition.')
        return cleaned_data


class DataInventoryForm(forms.ModelForm):
    class Meta:
        model = DataInventoryRecord
        fields = ['title', 'description', 'data_categories', 'data_subjects', 'purpose',
                  'lawful_basis', 'retention_period', 'recipients', 'third_country_transfers',
                  'transfer_safeguards', 'technical_measures', 'organizational_measures',
                  'dpia_required', 'dpia_completed', 'controller', 'processor', 'dpo_contact', 'client']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'data_categories': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'data_subjects': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'purpose': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'lawful_basis': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'retention_period': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'recipients': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'third_country_transfers': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'transfer_safeguards': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'technical_measures': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'organizational_measures': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'dpia_required': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'dpia_completed': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'controller': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'processor': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'dpo_contact': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }


class DSARRequestForm(forms.ModelForm):
    class Meta:
        model = DSARRequest
        fields = ['request_type', 'status', 'requester_name', 'requester_email',
                  'requester_id_verified', 'description', 'response', 'denial_reason',
                  'received_date', 'due_date', 'completed_date', 'extended', 'client', 'assigned_to']
        widgets = {
            'request_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'requester_name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'requester_email': forms.EmailInput(attrs={'class': TAILWIND_INPUT}),
            'requester_id_verified': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'response': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'denial_reason': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'received_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'completed_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'extended': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
        }


class SubprocessorForm(forms.ModelForm):
    class Meta:
        model = Subprocessor
        fields = ['name', 'description', 'service_type', 'country', 'is_eu_based',
                  'dpa_in_place', 'scc_in_place', 'dpf_certified', 'data_categories',
                  'contact_email', 'contract_start_date', 'contract_end_date',
                  'last_audit_date', 'risk_level', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'service_type': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'country': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'is_eu_based': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'dpa_in_place': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'scc_in_place': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'dpf_certified': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'data_categories': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'contact_email': forms.EmailInput(attrs={'class': TAILWIND_INPUT}),
            'contract_start_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'contract_end_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'last_audit_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'risk_level': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


class TransferRecordForm(forms.ModelForm):
    class Meta:
        model = TransferRecord
        fields = ['title', 'source_country', 'destination_country', 'transfer_mechanism',
                  'data_categories', 'subprocessor', 'contract', 'tia_completed',
                  'supplementary_measures', 'is_active', 'start_date', 'review_date', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'source_country': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'destination_country': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'transfer_mechanism': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'data_categories': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'subprocessor': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'tia_completed': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'supplementary_measures': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'start_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'review_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


class RetentionPolicyForm(forms.ModelForm):
    class Meta:
        model = RetentionPolicy
        fields = ['title', 'category', 'description', 'retention_period_days', 'legal_basis',
                  'deletion_method', 'auto_delete', 'review_frequency_days', 'last_reviewed',
                  'next_review', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'category': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'retention_period_days': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
            'legal_basis': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 2}),
            'deletion_method': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'auto_delete': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'review_frequency_days': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
            'last_reviewed': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'next_review': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
        }


class LegalHoldForm(forms.ModelForm):
    class Meta:
        model = LegalHold
        fields = ['title', 'description', 'status', 'matter', 'client', 'custodians',
                  'hold_start_date', 'hold_end_date', 'reason', 'scope']
        widgets = {
            'title': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'matter': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'client': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'custodians': forms.SelectMultiple(attrs={'class': TAILWIND_SELECT, 'size': 5}),
            'hold_start_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'hold_end_date': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'scope': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
        }


class ApprovalRuleForm(forms.ModelForm):
    class Meta:
        model = ApprovalRule
        fields = ['name', 'description', 'trigger_type', 'trigger_value', 'approval_step',
                  'approver_role', 'specific_approver', 'sla_hours', 'escalation_after_hours',
                  'is_active', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 3}),
            'trigger_type': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'trigger_value': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'approval_step': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'approver_role': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'specific_approver': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'sla_hours': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
            'escalation_after_hours': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
            'is_active': forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
            'order': forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
        }


class ApprovalRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = ApprovalRequest
        fields = ['contract', 'approval_step', 'status', 'assigned_to', 'delegated_to', 'comments', 'due_date']
        widgets = {
            'contract': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'approval_step': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'status': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'assigned_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'delegated_to': forms.Select(attrs={'class': TAILWIND_SELECT}),
            'comments': forms.Textarea(attrs={'class': TAILWIND_TEXTAREA, 'rows': 4}),
            'due_date': forms.DateTimeInput(attrs={'class': TAILWIND_INPUT, 'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        new_status = cleaned_data.get('status')
        if not self.instance.pk or not new_status:
            return cleaned_data

        if not self.instance.can_transition_to(new_status):
            self.add_error('status', 'Invalid approval status transition.')
            return cleaned_data

        if new_status != self.instance.status and not self.instance.can_actor_transition(self.actor):
            self.add_error('status', 'You are not authorized to perform this approval transition.')

        assigned_to = cleaned_data.get('assigned_to')
        delegated_to = cleaned_data.get('delegated_to')
        actor = self.actor
        if actor and assigned_to and assigned_to != actor and not can_manage_organization(actor, self.instance.organization):
            self.add_error('assigned_to', 'Only organization admins or owners can reassign approval requests.')
        if actor and delegated_to and delegated_to != actor and not can_manage_organization(actor, self.instance.organization):
            self.add_error('delegated_to', 'Only organization admins or owners can delegate approval requests.')
        return cleaned_data
