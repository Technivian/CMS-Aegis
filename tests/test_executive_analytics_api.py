import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import Contract, ExecutiveDashboardPreset, Organization, OrganizationMembership


User = get_user_model()


class ExecutiveAnalyticsApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='exec-owner', password='pass12345')
        self.member = User.objects.create_user(username='exec-member', password='pass12345')
        self.other_owner = User.objects.create_user(username='exec-other-owner', password='pass12345')

        self.org_a = Organization.objects.create(name='Exec Org A', slug='exec-org-a')
        self.org_b = Organization.objects.create(name='Exec Org B', slug='exec-org-b')
        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org_b,
            user=self.other_owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

        now = timezone.now()
        contract_a = Contract.objects.create(
            organization=self.org_a,
            title='A Approved',
            risk_level=Contract.RiskLevel.HIGH,
            lifecycle_stage='APPROVAL',
            created_by=self.owner,
        )
        contract_a.created_at = now - timedelta(days=12)
        contract_a.approved_at = now - timedelta(days=2)
        contract_a.save(update_fields=['created_at', 'approved_at'])

        Contract.objects.create(
            organization=self.org_a,
            title='A Active',
            risk_level=Contract.RiskLevel.CRITICAL,
            lifecycle_stage='SIGNATURE',
            created_by=self.owner,
        )
        Contract.objects.create(
            organization=self.org_b,
            title='B Org Contract',
            risk_level=Contract.RiskLevel.CRITICAL,
            lifecycle_stage='SIGNATURE',
            created_by=self.other_owner,
        )

        self.analytics_url = reverse('contracts:executive_analytics_api')
        self.presets_url = reverse('contracts:executive_dashboard_presets_api')

    def test_executive_analytics_api_is_org_scoped(self):
        client = Client()
        client.login(username='exec-owner', password='pass12345')
        response = client.get(self.analytics_url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['organization']['slug'], 'exec-org-a')
        self.assertEqual(payload['cycle_time']['sample_size'], 1)
        stages = {item['stage']: item['count'] for item in payload['bottlenecks']}
        self.assertIn('SIGNATURE', stages)
        self.assertGreaterEqual(sum(item['high_or_critical_count'] for item in payload['risk_trend']), 2)

    def test_executive_dashboard_presets_persist_and_load(self):
        client = Client()
        client.login(username='exec-owner', password='pass12345')
        create_response = client.post(
            self.presets_url,
            data=json.dumps(
                {
                    'name': 'Legal Ops Weekly',
                    'filters': {'jurisdiction': ['US']},
                    'layout': {'cards': ['cycle_time', 'risk_trend']},
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 200)

        list_response = client.get(self.presets_url)
        self.assertEqual(list_response.status_code, 200)
        presets = list_response.json()['presets']
        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0]['name'], 'Legal Ops Weekly')
        self.assertEqual(presets[0]['filters']['jurisdiction'], ['US'])

    def test_member_cannot_create_or_delete_shared_presets(self):
        client = Client()
        client.login(username='exec-member', password='pass12345')
        create_response = client.post(
            self.presets_url,
            data=json.dumps({'name': 'Member Preset', 'filters': {}, 'layout': {}}),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 403)

        preset = ExecutiveDashboardPreset.objects.create(
            organization=self.org_a,
            name='Owner Preset',
            filters={},
            layout={},
            created_by=self.owner,
        )
        delete_response = client.delete(
            reverse('contracts:executive_dashboard_preset_delete_api', kwargs={'preset_id': preset.id})
        )
        self.assertEqual(delete_response.status_code, 403)
