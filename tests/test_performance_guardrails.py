from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from contracts.models import Client as ClientModel
from contracts.models import Contract, Organization, OrganizationMembership


User = get_user_model()


class PerformanceGuardrailsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='perf-user',
            email='perf@example.com',
            password='testpass123',
        )
        self.org = Organization.objects.create(name='Performance Org', slug='performance-org')
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client_obj = ClientModel.objects.create(
            organization=self.org,
            name='Perf Client',
            client_type=ClientModel.ClientType.CORPORATION,
            status=ClientModel.Status.ACTIVE,
            created_by=self.user,
        )
        self.assertTrue(self.client.login(username='perf-user', password='testpass123'))

    def _seed_contracts(self, count):
        for idx in range(count):
            Contract.objects.create(
                organization=self.org,
                client=self.client_obj,
                title=f'Contract {idx}',
                content='Performance test content',
                status=Contract.Status.ACTIVE,
                created_by=self.user,
            )

    def _query_count_for(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx)

    def test_contract_list_query_count_does_not_scale_linearly(self):
        self._seed_contracts(5)
        baseline = self._query_count_for(reverse('contracts:contract_list'))

        self._seed_contracts(40)
        expanded = self._query_count_for(reverse('contracts:contract_list'))

        self.assertLessEqual(expanded, baseline + 6)

    def test_contracts_api_query_count_does_not_scale_linearly(self):
        self._seed_contracts(5)
        baseline = self._query_count_for(reverse('contracts:contracts_api'))

        self._seed_contracts(40)
        expanded = self._query_count_for(reverse('contracts:contracts_api'))

        self.assertLessEqual(expanded, baseline + 4)
