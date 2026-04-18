from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from contracts.models import Organization, OrganizationMembership


class LegacyUrlAliasesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='legacyaliasowner',
            password='legacy-pass-123',
            email='legacy-owner@example.com',
        )
        self.organization = Organization.objects.create(name='Legacy Alias Org', slug='legacy-alias-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client.login(username='legacyaliasowner', password='legacy-pass-123')

    def test_legacy_list_routes_still_resolve(self):
        legacy_paths = [
            reverse('contracts:workflow_dashboard_legacy'),
            reverse('contracts:risk_log_list_legacy'),
            reverse('contracts:trademark_request_list_legacy'),
            reverse('contracts:due_diligence_list_legacy'),
        ]

        for path in legacy_paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=f'Legacy path should remain available: {path}')
