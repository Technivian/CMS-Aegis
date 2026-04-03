
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
        self.assertContains(response, 'Client Management')
        self.assertContains(response, 'Contracts')
        self.assertContains(response, 'Risk')
        self.assertContains(response, 'Dashboard')
        self.assertContains(response, 'Contracts')
        self.assertContains(response, 'Tasks')
        self.assertContains(response, 'Workflows')

    def test_topbar_actions(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'title="Notifications"')
        self.assertContains(response, 'New Contract')
        self.assertContains(response, 'Logout')
        self.assertContains(response, '/profile/')

    def test_dashboard_kpis_and_panels(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Active Contracts')
        self.assertContains(response, 'Clients')
        self.assertContains(response, 'Outstanding')
        self.assertContains(response, 'Pending Tasks')
        self.assertContains(response, 'Recent Contracts')
        self.assertContains(response, 'Upcoming Deadlines')

    def test_dashboard_quick_actions(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'New Contract')
        self.assertContains(response, 'New Client')
        self.assertContains(response, 'Log Time')

    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
