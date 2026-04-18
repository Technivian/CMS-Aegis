from django.contrib.auth import get_user_model
from django.test import TestCase

from contracts.forms import ClauseTemplateForm, ContractForm
from contracts.models import ClauseCategory, ClauseTemplate, Contract, Organization, OrganizationMembership
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
