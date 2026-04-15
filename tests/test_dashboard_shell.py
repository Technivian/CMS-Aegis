import os

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from contracts.models import CareConfiguration, Client as CareProvider, Organization, OrganizationMembership


class DashboardShellTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com',
        )
        self.organization = Organization.objects.create(name='Care Team Noord', slug='care-team-noord')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client.login(username='testuser', password='testpass123')
        os.environ['FEATURE_REDESIGN'] = 'true'

    def test_dashboard_alert_strip(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cases without match')
        self.assertContains(response, 'Cases waiting too long')
        self.assertContains(response, 'Missing beoordeling')
        self.assertContains(response, 'Urgent cases')

    def test_dashboard_container_constraint(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'max-width: 1440px')

    def test_dashboard_top_bar(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="Search"')
        self.assertContains(response, 'title="Thema wisselen"')
        self.assertContains(response, 'title="Meldingen"')
        self.assertContains(response, 'Nieuwe casus')
        self.assertContains(response, 'Uitloggen')

    def test_dashboard_panels(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Priority Case Queue')
        self.assertContains(response, 'Active Case Panel')
        self.assertContains(response, 'Bottlenecks')
        self.assertContains(response, 'Capacity Signals')
        self.assertContains(response, 'Laatst bijgewerkt')

    def test_case_list_alias_uses_configuration_shell(self):
        provider = CareProvider.objects.create(
            organization=self.organization,
            name='ZorgPlus Noord',
            created_by=self.user,
        )
        CareConfiguration.objects.create(
            organization=self.organization,
            matter_number='CFG-DASH-1',
            title='Test Configuration',
            client=provider,
            created_by=self.user,
        )

        response = self.client.get(reverse('careon:case_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Casussen')
        self.assertContains(response, 'Zoek op titel of casus-ID...')
        self.assertContains(response, 'Nieuwe casus')

    def test_accessibility_features(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="Search"')
        self.assertContains(response, 'title="Thema wisselen"')
        self.assertContains(response, 'type="submit"')

    def test_typography_and_spacing(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'command-grid')
        self.assertContains(response, 'command-alert-strip')
        self.assertContains(response, 'queue-row')

    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
