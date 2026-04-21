
import os

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from contracts.models import Budget, Client as ClientModel, Contract, Matter, Organization, OrganizationMembership, TrademarkRequest


class RedesignComponentsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com',
        )
        self.organization = Organization.objects.create(name='Test Firm', slug='test-firm')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client.login(username='testuser', password='testpass123')
        os.environ['FEATURE_REDESIGN'] = 'true'

    def test_dashboard_component_labels(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active Contracts')
        self.assertContains(response, 'Recent Contracts')
        self.assertContains(response, 'Case Portfolio')
        self.assertContains(response, 'Workflow recommendations open')
        self.assertContains(response, 'Task Signals')
        self.assertContains(response, 'Governance activity')

    def test_contracts_list_core_components(self):
        Contract.objects.create(
            organization=self.organization,
            title='Test Contract',
            content='Test content',
            status=Contract.Status.DRAFT,
            created_by=self.user,
        )

        response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Contract')
        self.assertContains(response, 'Search contracts...')
        self.assertContains(response, 'All statuses')
        self.assertContains(response, 'New Contract')

    def test_navigation_structure(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard')
        self.assertContains(response, 'Contracts')
        self.assertContains(response, 'Tasks')
        self.assertContains(response, 'Repository')
        self.assertContains(response, 'Workflows')

    def test_accessibility_and_responsive_markers(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="Search"')
        self.assertContains(response, '@media (max-width: 1024px)')
        self.assertContains(response, '@media (max-width: 640px)')

    def test_budget_list_matches_dashboard_style(self):
        Budget.objects.create(
            organization=self.organization,
            year=2025,
            quarter=Budget.Quarter.Q3,
            department='Legal Ops',
            allocated_amount='120000.00',
            description='Core operations budget',
            created_by=self.user,
        )

        response = self.client.get(reverse('contracts:budget_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Budgets')
        self.assertContains(response, 'Search budgets by department or description...')
        self.assertContains(response, 'New Budget')
        self.assertContains(response, 'Legal Ops')

    def test_trademark_request_list_uses_real_model_fields(self):
        client_record = ClientModel.objects.create(
            organization=self.organization,
            name='Acme Client',
            created_by=self.user,
        )
        matter = Matter.objects.create(
            organization=self.organization,
            matter_number='TM-0001',
            title='Brand Protection',
            client=client_record,
            created_by=self.user,
        )
        TrademarkRequest.objects.create(
            mark_text='AEGIS MARK',
            description='Primary trademark filing for the platform.',
            goods_services='Legal software services',
            filing_basis='Use in commerce',
            status=TrademarkRequest.Status.PENDING,
            client=client_record,
            matter=matter,
        )

        response = self.client.get(reverse('contracts:trademark_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trademark Requests')
        self.assertContains(response, 'Search marks, clients, matters, or descriptions...')
        self.assertContains(response, 'AEGIS MARK')
        self.assertContains(response, 'Brand Protection')
        self.assertContains(response, 'Use in commerce')

    def test_repository_page_preserves_js_hooks_in_new_shell(self):
        response = self.client.get(reverse('contracts:repository'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Repository')
        self.assertContains(response, 'id="search-input"')
        self.assertContains(response, 'id="sort-select"')
        self.assertContains(response, 'id="contracts-table"')
        self.assertContains(response, 'id="details-drawer"')

    def test_global_search_uses_case_flow_semantics(self):
        contract = Contract.objects.create(
            organization=self.organization,
            title='Case Search Contract',
            content='Searchable contract content',
            status=Contract.Status.ACTIVE,
            created_by=self.user,
        )

        response = self.client.get(reverse('contracts:global_search'), {'q': 'Case Search'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Search across contracts, matters, documents, and task signals with relevance ranking.')
        self.assertContains(response, 'Search contracts, clients, matters, documents, clauses, task signals...')
        self.assertContains(response, 'Contracts (1)')
        self.assertContains(response, contract.title)

    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
