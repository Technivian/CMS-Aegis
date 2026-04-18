from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.models import Organization, OrganizationMembership, UserProfile


User = get_user_model()


class OrganizationSecurityExportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='testpass123')
        self.member = User.objects.create_user(username='member', email='member@example.com', password='testpass123')
        self.organization = Organization.objects.create(
            name='Export Org',
            slug='export-org',
            require_mfa=True,
            session_idle_timeout_minutes=45,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )
        owner_profile, _ = UserProfile.objects.get_or_create(user=self.owner)
        owner_profile.mfa_enabled = True
        owner_profile.save(update_fields=['mfa_enabled', 'mfa_verified_at', 'updated_at'])

    def test_owner_can_export_security_csv(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.get(reverse('organization_security_export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        body = response.content.decode('utf-8')
        self.assertIn('organization,Export Org', body)
        self.assertIn('require_mfa,True', body)
        self.assertIn('session_idle_timeout_minutes,45', body)
        self.assertIn('username,email,role,mfa_enabled,mfa_verified_at,session_revocation_counter', body)
        self.assertIn('owner,owner@example.com,OWNER,True', body)

    def test_member_cannot_export_security_csv(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.get(reverse('organization_security_export'))

        self.assertEqual(response.status_code, 403)
