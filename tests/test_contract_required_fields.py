from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.forms import ClauseTemplateForm, ContractForm
from contracts.models import ClauseCategory, ClausePlaybook, ClauseTemplate, ClauseVariant, Contract, Organization, OrganizationMembership
from contracts.services.clause_policy import get_clause_fallback_summary


User = get_user_model()


class ContractRequiredFieldPolicyTests(TestCase):
    def test_nda_requires_party_and_jurisdiction_metadata(self):
        form = ContractForm(
            data={
                'title': 'NDA',
                'contract_type': Contract.ContractType.NDA,
                'content': 'Mutual confidentiality terms.',
                'status': Contract.Status.DRAFT,
                'currency': Contract.Currency.USD,
                'risk_level': Contract.RiskLevel.LOW,
                'lifecycle_stage': 'DRAFTING',
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('counterparty', form.errors)
        self.assertIn('governing_law', form.errors)
        self.assertIn('jurisdiction', form.errors)

    def test_msa_with_required_fields_is_valid(self):
        form = ContractForm(
            data={
                'title': 'MSA',
                'contract_type': Contract.ContractType.MSA,
                'content': 'Services terms.',
                'status': Contract.Status.DRAFT,
                'counterparty': 'Acme Corp',
                'currency': Contract.Currency.USD,
                'governing_law': 'State of Delaware',
                'jurisdiction': 'New York',
                'risk_level': Contract.RiskLevel.MEDIUM,
                'lifecycle_stage': 'DRAFTING',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)


class ClausePolicyTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Clause Org', slug='clause-org')
        self.user = User.objects.create_user(username='clause-owner', password='testpass123')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.category = ClauseCategory.objects.create(
            organization=self.organization,
            name='Privacy',
            order=1,
        )

    def test_mandatory_clause_requires_fallback_or_playbook(self):
        form = ClauseTemplateForm(
            data={
                'title': 'Data Processing',
                'category': self.category.pk,
                'content': 'Base clause text.',
                'fallback_content': '',
                'jurisdiction_scope': ClauseTemplate.JurisdictionScope.GLOBAL,
                'is_mandatory': True,
                'applicable_contract_types': '',
                'playbook_notes': '',
                'tags': 'privacy,dp',
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_clause_fallback_summary_prefers_fallback_content(self):
        clause = ClauseTemplate.objects.create(
            organization=self.organization,
            title='Data Processing',
            category=self.category,
            content='Base clause text.',
            fallback_content='Fallback clause text.',
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.CUSTOM,
            is_mandatory=True,
            applicable_contract_types='NDA, MSA',
            playbook_notes='Use fallback if the vendor resists.',
            tags='privacy,dp',
            created_by=self.user,
        )

        summary = get_clause_fallback_summary(clause)
        self.assertTrue(summary['has_fallback'])
        self.assertEqual(summary['fallback_text'], 'Fallback clause text.')
        self.assertEqual(summary['jurisdiction_scope'], ClauseTemplate.JurisdictionScope.CUSTOM)


class ContractDraftingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='draft-owner', password='testpass123')
        self.organization = Organization.objects.create(name='Draft Org', slug='draft-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.category = ClauseCategory.objects.create(
            organization=self.organization,
            name='Privacy',
            order=1,
        )
        self.playbook = ClausePlaybook.objects.create(
            organization=self.organization,
            name='EU Privacy Playbook',
            fallback_position='Use stronger DPA language',
            jurisdiction_scope=ClausePlaybook.JurisdictionScope.EU,
            risk_level='HIGH',
        )
        self.template = ClauseTemplate.objects.create(
            organization=self.organization,
            title='Data Processing Clause',
            category=self.category,
            content='Standard processing language.',
            fallback_content='Fallback processing language.',
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.GLOBAL,
            applicable_contract_types='MSA',
            playbook_notes='Use this clause for core privacy commitments.',
            tags='privacy,data',
            created_by=self.user,
        )
        ClauseVariant.objects.create(
            organization=self.organization,
            template=self.template,
            playbook=self.playbook,
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.EU,
            contract_type=Contract.ContractType.MSA,
            risk_level=Contract.RiskLevel.HIGH,
            fallback_content='EU fallback language.',
            playbook_notes='EU negotiation notes.',
            priority=10,
        )

    def test_contract_create_auto_populates_content_from_selected_clause_templates(self):
        form = ContractForm(
            data={
                'title': 'Drafted Contract',
                'contract_type': Contract.ContractType.MSA,
                'content': '',
                'status': Contract.Status.DRAFT,
                'counterparty': 'Acme Corp',
                'currency': Contract.Currency.USD,
                'governing_law': 'EU',
                'jurisdiction': 'Netherlands',
                'risk_level': Contract.RiskLevel.HIGH,
                'lifecycle_stage': 'DRAFTING',
                'clause_templates': [self.template.pk],
            },
            organization=self.organization,
        )

        self.assertTrue(form.is_valid(), form.errors)
        contract = form.save(commit=False)
        self.assertIn('Data Processing Clause', contract.content)
        self.assertIn('Resolved playbook: EU Privacy Playbook', contract.content)
        self.assertIn('Negotiation notes:', contract.content)
        self.assertIn('Fallback position:', contract.content)

    def test_contract_create_view_auto_populates_content_from_selected_clause_templates(self):
        self.client.login(username='draft-owner', password='testpass123')

        response = self.client.post(
            reverse('contracts:contract_create'),
            data={
                'title': 'Drafted Contract via View',
                'contract_type': Contract.ContractType.MSA,
                'content': '',
                'status': Contract.Status.DRAFT,
                'counterparty': 'Acme Corp',
                'currency': Contract.Currency.USD,
                'governing_law': 'EU',
                'jurisdiction': 'Netherlands',
                'risk_level': Contract.RiskLevel.HIGH,
                'lifecycle_stage': 'DRAFTING',
                'clause_templates': [self.template.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        contract = Contract.objects.get(title='Drafted Contract via View')
        self.assertIn('Data Processing Clause', contract.content)
        self.assertIn('Resolved playbook: EU Privacy Playbook', contract.content)
        self.assertIn('Negotiation notes:', contract.content)
        self.assertIn('Fallback position:', contract.content)

    def test_contract_create_preview_returns_generated_content_without_saving(self):
        self.client.login(username='draft-owner', password='testpass123')

        response = self.client.post(
            reverse('contracts:contract_create'),
            data={
                'title': 'Preview Only',
                'contract_type': Contract.ContractType.MSA,
                'content': '',
                'status': Contract.Status.DRAFT,
                'counterparty': 'Acme Corp',
                'currency': Contract.Currency.USD,
                'governing_law': 'EU',
                'jurisdiction': 'Netherlands',
                'risk_level': Contract.RiskLevel.HIGH,
                'lifecycle_stage': 'DRAFTING',
                'clause_templates': [self.template.pk],
                'preview_draft': '1',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Draft sections', html=False)
        self.assertContains(response, 'Data Processing Clause', html=False)
        self.assertContains(response, 'Resolved playbook: EU Privacy Playbook', html=False)
        self.assertContains(response, 'EU Privacy Playbook', html=False)
        self.assertContains(response, 'Fallback available', html=False)
        self.assertContains(response, 'Playbook notes', html=False)
        self.assertContains(response, 'High risk', html=False)
        self.assertContains(response, 'Open source clause', html=False)
        self.assertContains(response, 'Open playbook context', html=False)
        self.assertFalse(Contract.objects.filter(title='Preview Only').exists())

    def test_contract_create_saves_edited_preview_sections_in_order(self):
        form = ContractForm(
            data={
                'title': 'Editable Sections Contract',
                'contract_type': Contract.ContractType.MSA,
                'content': '',
                'status': Contract.Status.DRAFT,
                'counterparty': 'Acme Corp',
                'currency': Contract.Currency.USD,
                'governing_law': 'EU',
                'jurisdiction': 'Netherlands',
                'risk_level': Contract.RiskLevel.HIGH,
                'lifecycle_stage': 'DRAFTING',
                'draft_section_count': '3',
                'draft_section_0_include': 'on',
                'draft_section_0_order': '2',
                'draft_section_0_title': 'Section Two',
                'draft_section_0_content': 'Second section body.',
                'draft_section_1_include': 'on',
                'draft_section_1_order': '1',
                'draft_section_1_title': 'Section One',
                'draft_section_1_content': 'First section body.',
                'draft_section_2_order': '3',
                'draft_section_2_title': 'Section Three',
                'draft_section_2_content': 'Third section body.',
                'clause_templates': [self.template.pk],
            },
            organization=self.organization,
        )

        self.assertTrue(form.is_valid(), form.errors)
        contract = form.save(commit=False)
        self.assertIn('Section One', contract.content)
        self.assertIn('Section Two', contract.content)
        self.assertNotIn('Section Three', contract.content)
        self.assertLess(contract.content.index('Section One'), contract.content.index('Section Two'))

    def test_contract_create_preview_reflects_edited_sections(self):
        self.client.login(username='draft-owner', password='testpass123')

        response = self.client.post(
            reverse('contracts:contract_create'),
            data={
                'title': 'Previewed Sections Contract',
                'contract_type': Contract.ContractType.MSA,
                'content': '',
                'status': Contract.Status.DRAFT,
                'counterparty': 'Acme Corp',
                'currency': Contract.Currency.USD,
                'governing_law': 'EU',
                'jurisdiction': 'Netherlands',
                'risk_level': Contract.RiskLevel.HIGH,
                'lifecycle_stage': 'DRAFTING',
                'draft_section_count': '2',
                'draft_section_0_include': 'on',
                'draft_section_0_order': '2',
                'draft_section_0_title': 'Late Section',
                'draft_section_0_content': 'Second section body.',
                'draft_section_1_include': 'on',
                'draft_section_1_order': '1',
                'draft_section_1_title': 'Early Section',
                'draft_section_1_content': 'First section body.',
                'preview_draft': '1',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Draft sections', html=False)
        self.assertContains(response, 'Late Section', html=False)
        self.assertContains(response, 'Early Section', html=False)
        self.assertContains(response, 'Source: Edited draft section', html=False)
        self.assertLess(response.content.decode().find('Early Section'), response.content.decode().find('Late Section'))
