
import os
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from contracts.models import Contract, Organization, OrganizationMembership


class BoltonRedesignTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.organization = Organization.objects.create(name='Bolton Firm', slug='bolton-firm')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Set feature flag
        os.environ['FEATURE_REDESIGN'] = 'true'

    def test_dashboard_kpi_cards(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Active Contracts')
        self.assertContains(response, 'Clients')
        self.assertContains(response, 'Outstanding')
        self.assertContains(response, 'Pending Tasks')
        self.assertContains(response, 'kpi-card')

    def test_dashboard_container_constraint(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'max-width: 1400px')

    def test_dashboard_top_bar(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'title="Search"')
        self.assertContains(response, 'title="Toggle theme"')
        self.assertContains(response, 'title="Notifications"')
        self.assertContains(response, 'New Contract')
        self.assertContains(response, 'Logout')

    def test_dashboard_panels(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recent Contracts')
        self.assertContains(response, 'Upcoming Deadlines')
        self.assertContains(response, 'Activity Feed')
        self.assertContains(response, 'Billing Snapshot')

    def test_contracts_table_structure(self):
        Contract.objects.create(
            organization=self.organization,
            title='Test Contract',
            content='Test content',
            status='DRAFT',
            created_by=self.user
        )

        response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Title')
        self.assertContains(response, 'Type')
        self.assertContains(response, 'Status')
        self.assertContains(response, 'Value')
        self.assertContains(response, 'Counterparty')
        self.assertContains(response, 'Test Contract')

    def test_contracts_list_filters_and_actions(self):
        response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Search contracts...')
        self.assertContains(response, 'All Statuses')
        self.assertContains(response, 'Search')
        self.assertContains(response, 'New Contract')

    def test_accessibility_features(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'title="Search"')
        self.assertContains(response, 'title="Toggle theme"')
        self.assertContains(response, 'title="Search"')
        self.assertContains(response, 'type="submit"')

    def test_typography_and_spacing(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "font-family: 'Inter'")
        self.assertContains(response, 'dash-grid')
        self.assertContains(response, 'gap: 20px')

    def tearDown(self):
        """Clean up environment variables"""
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
