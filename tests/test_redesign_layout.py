
import os

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class RedesignLayoutTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )
        os.environ['FEATURE_REDESIGN'] = 'true'
        self.client.login(username='testuser', password='testpass123')

    def test_base_shell_and_theme_controls(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CMS Aegis')
        self.assertContains(response, 'data-theme="dark"')
        self.assertContains(response, 'toggleTheme()')
        self.assertContains(response, 'title="Search"')

    def test_sidebar_navigation_sections_and_links(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'COUNTERPARTIES')
        self.assertContains(response, 'Contracts')
        self.assertContains(response, 'GOVERNANCE')
        self.assertContains(response, 'Dashboard')
        self.assertContains(response, 'Contracts')
        self.assertContains(response, 'Tasks')
        self.assertContains(response, 'Workflows')

    def test_topbar_actions(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'title="Meldingen"')
        self.assertContains(response, 'New Contract')
        self.assertContains(response, 'Uitloggen')
        self.assertContains(response, '/profile/')

    def test_dashboard_kpis_and_panels(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Active Matters')
        self.assertContains(response, 'Clients')
        self.assertContains(response, 'Contracts in intake')
        self.assertContains(response, 'Open Task Signals')
        self.assertContains(response, 'Recent Contracts')
        self.assertContains(response, 'Workflow recommendations open')

    def test_dashboard_quick_actions(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'New Contract')
        self.assertContains(response, 'New Counterparty')
        self.assertContains(response, 'Start intake from contract')

    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
