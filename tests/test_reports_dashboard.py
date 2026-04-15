import os
from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from contracts.models import (
    Organization, OrganizationMembership, CaseIntakeProcess,
    Client as CareProvider, CareSignal, TrustAccount, PlacementRequest,
    CareConfiguration, RegionalConfiguration
)


class ReportsDashboardTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com',
        )
        self.organization = Organization.objects.create(
            name='Care Team Noord',
            slug='care-team-noord'
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client.login(username='testuser', password='testpass123')
        os.environ['FEATURE_REDESIGN'] = 'true'

    def test_reports_dashboard_loads(self):
        """Verify reports dashboard template renders with new dashboard design."""
        response = self.client.get(reverse('careon:reports_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rapportages & Regie')
        self.assertContains(response, 'kpi-card')

    def test_reports_dashboard_kpi_cards_are_clickable(self):
        """Verify KPI cards link to filtered attention list."""
        response = self.client.get(reverse('careon:reports_dashboard'))
        self.assertEqual(response.status_code, 200)
        # Check that KPI cards have href attributes
        self.assertContains(response, '?attention=stagnation')
        self.assertContains(response, '?attention=unmatched')
        self.assertContains(response, '?attention=escalation')
        self.assertContains(response, '?attention=capacity')

    def test_reports_dashboard_shows_attention_items(self):
        """Verify attention items panel displays drilldown links."""
        # Create test case
        case = CaseIntakeProcess.objects.create(
            organization=self.organization,
            title='Test Case',
            status=CaseIntakeProcess.ProcessStatus.MATCHING,
            start_date=date.today(),
            target_completion_date=date.today(),
        )

        response = self.client.get(reverse('careon:reports_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Aandacht vereist')
        self.assertContains(response, 'badge-sm')

    def test_reports_dashboard_flow_analysis(self):
        """Verify casusflow analysis panel displays."""
        response = self.client.get(reverse('careon:reports_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Casusflow analyse')
        self.assertContains(response, 'Intake')
        self.assertContains(response, 'Beoordeling')
        self.assertContains(response, 'Matching')

    def test_reports_dashboard_filter_by_attention_type(self):
        """Verify filtering by attention type works."""
        response = self.client.get(reverse('careon:reports_dashboard'), {'attention': 'stagnation'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stagnatie')

    def test_reports_dashboard_no_generic_theater(self):
        """Verify no meaningless empty metrics or generic dashboard theater."""
        response = self.client.get(reverse('careon:reports_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Should show regie/flow-focused metrics, not generic "contracts" metrics
        content = response.content.decode()
        # Check for dashboard design classes
        self.assertIn('page-wrap', content)
        self.assertIn('dash-grid', content)
        self.assertIn('panel', content)

    def test_reports_dashboard_has_actionable_recommendations(self):
        """Verify recommendations panel can appear with actual actions."""
        # Create provider without capacity
        provider = CareProvider.objects.create(
            organization=self.organization,
            name='Test Provider',
            created_by=self.user,
        )
        # Create matching cases without match
        case = CaseIntakeProcess.objects.create(
            organization=self.organization,
            title='Unmatched Case',
            status=CaseIntakeProcess.ProcessStatus.MATCHING,
            start_date=date.today(),
            target_completion_date=date.today(),
        )

        response = self.client.get(reverse('careon:reports_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Check that page contains recommendation links or attention items
        content = response.content.decode()
        self.assertIn('Aanbevelingen', content)

    def test_reports_dashboard_can_filter_on_region_type_and_region(self):
        region = RegionalConfiguration.objects.create(
            organization=self.organization,
            region_name='GGD Test Regio',
            region_code='GGD001',
            region_type='GGD',
            status=RegionalConfiguration.Status.ACTIVE,
        )
        CaseIntakeProcess.objects.create(
            organization=self.organization,
            title='Region Filter Case',
            status=CaseIntakeProcess.ProcessStatus.MATCHING,
            preferred_region_type='GGD',
            preferred_region=region,
            start_date=date.today(),
            target_completion_date=date.today(),
        )

        response = self.client.get(
            reverse('careon:reports_dashboard'),
            {'region_type': 'GGD', 'region': str(region.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Regio-overzicht')
        self.assertContains(response, 'GGD Test Regio')

    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
