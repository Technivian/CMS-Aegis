from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.models import Contract, ExecutiveDashboardPreset, Organization, OrganizationMembership


User = get_user_model()


class ExecutiveReportsDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='report-owner', password='pass12345')
        self.organization = Organization.objects.create(name='Reports Org', slug='reports-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        Contract.objects.create(
            organization=self.organization,
            title='Contract A',
            lifecycle_stage='APPROVAL',
            risk_level=Contract.RiskLevel.HIGH,
            created_by=self.user,
        )
        ExecutiveDashboardPreset.objects.create(
            organization=self.organization,
            name='Weekly Exec View',
            filters={'risk_level': ['HIGH', 'CRITICAL']},
            layout={'cards': ['cycle_time', 'bottlenecks']},
            created_by=self.user,
        )

    def test_reports_dashboard_renders_executive_sections(self):
        self.client.login(username='report-owner', password='pass12345')
        response = self.client.get(reverse('contracts:reports_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Executive Cycle Time')
        self.assertContains(response, 'Risk Trend (High + Critical)')
        self.assertContains(response, 'Saved Executive Dashboards')
        self.assertContains(response, 'Weekly Exec View')

    def test_reports_export_returns_csv_snapshot(self):
        self.client.login(username='report-owner', password='pass12345')
        response = self.client.get(reverse('contracts:reports_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertContains(response, 'category,metric,value', html=False)
        self.assertContains(response, 'summary,total_clients,0', html=False)
