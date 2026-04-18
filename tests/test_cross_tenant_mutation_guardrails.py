import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.models import Contract, Deadline, Organization, OrganizationMembership


User = get_user_model()


class CrossTenantMutationGuardrailsTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name='Mutation Alpha', slug='mutation-alpha')
        self.org_b = Organization.objects.create(name='Mutation Beta', slug='mutation-beta')

        self.user_a = User.objects.create_user('mut_user_a', password='passA123!')
        self.user_b = User.objects.create_user('mut_user_b', password='passB123!')

        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.user_a,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org_b,
            user=self.user_b,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

        self.contract_a = Contract.objects.create(
            organization=self.org_a,
            title='Alpha Contract',
            contract_type=Contract.ContractType.NDA,
            status=Contract.Status.DRAFT,
            created_by=self.user_a,
        )
        self.contract_b = Contract.objects.create(
            organization=self.org_b,
            title='Beta Contract',
            contract_type=Contract.ContractType.NDA,
            status=Contract.Status.DRAFT,
            created_by=self.user_b,
        )

        self.deadline_b = Deadline.objects.create(
            title='Beta Deadline',
            due_date=datetime.date.today() + datetime.timedelta(days=10),
            contract=self.contract_b,
        )

    def test_cross_tenant_contract_update_returns_404(self):
        self.client.login(username='mut_user_a', password='passA123!')

        response = self.client.post(
            reverse('contracts:contract_update', kwargs={'pk': self.contract_b.pk}),
            data={
                'title': 'Illegal Update',
                'contract_type': Contract.ContractType.NDA,
                'status': Contract.Status.ACTIVE,
                'counterparty': 'Bad Actor',
                'currency': Contract.Currency.USD,
                'risk_level': Contract.RiskLevel.LOW,
                'lifecycle_stage': 'DRAFTING',
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_cross_tenant_deadline_complete_returns_404(self):
        self.client.login(username='mut_user_a', password='passA123!')
        response = self.client.post(
            reverse('contracts:deadline_complete', kwargs={'pk': self.deadline_b.pk})
        )
        self.assertEqual(response.status_code, 404)
