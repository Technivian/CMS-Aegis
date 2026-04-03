
import os

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from contracts.models import Contract, Organization, OrganizationMembership


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
        self.assertContains(response, 'Pending Tasks')
        self.assertContains(response, 'Recent Contracts')
        self.assertContains(response, 'Activity Feed')

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
        self.assertContains(response, 'All Statuses')
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

    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
