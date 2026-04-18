from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import Organization, OrganizationMembership, UserProfile


User = get_user_model()


class OrganizationSecuritySettingsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='testpass123')
        self.admin = User.objects.create_user(username='admin', email='admin@example.com', password='testpass123')
        self.member = User.objects.create_user(username='member', email='member@example.com', password='testpass123')
        self.organization = Organization.objects.create(name='Secure Org', slug='secure-org')

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )

        UserProfile.objects.get_or_create(user=self.owner)
        UserProfile.objects.get_or_create(user=self.admin)
        UserProfile.objects.get_or_create(user=self.member)

    def test_owner_can_toggle_mfa_policy(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.post(
            reverse('organization_security_settings'),
            {'require_mfa': 'on'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.organization.refresh_from_db()
        self.assertTrue(self.organization.require_mfa)

    def test_non_manager_cannot_open_security_settings(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.get(reverse('organization_security_settings'))

        self.assertEqual(response.status_code, 403)

    def test_owner_can_revoke_all_sessions(self):
        owner_client = Client()
        member_client = Client()
        self.assertTrue(owner_client.login(username='owner', password='testpass123'))
        self.assertTrue(member_client.login(username='member', password='testpass123'))

        self.assertEqual(member_client.get(reverse('dashboard')).status_code, 200)

        response = owner_client.post(
            reverse('organization_security_settings'),
            {'action': 'revoke_sessions'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        owner_dashboard = owner_client.get(reverse('dashboard'))
        member_dashboard = member_client.get(reverse('dashboard'))

        self.assertEqual(owner_dashboard.status_code, 302)
        self.assertIn(reverse('login'), owner_dashboard['Location'])
        self.assertEqual(member_dashboard.status_code, 302)
        self.assertIn(reverse('login'), member_dashboard['Location'])

    def test_owner_can_set_session_timeout_and_it_is_enforced(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.post(
            reverse('organization_security_settings'),
            {'session_idle_timeout_minutes': '5'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.session_idle_timeout_minutes, 5)

        session = self.client.session
        session['session_last_activity_at'] = int((timezone.now() - timedelta(minutes=6)).timestamp())
        session.save()

        redirected = self.client.get(reverse('dashboard'))
        self.assertEqual(redirected.status_code, 302)
        self.assertIn(reverse('login'), redirected['Location'])

    def test_owner_can_view_and_revoke_session_audit(self):
        owner_client = Client()
        member_client = Client()
        self.assertTrue(owner_client.login(username='owner', password='testpass123'))
        self.assertTrue(member_client.login(username='member', password='testpass123'))

        member_session = member_client.session
        member_session['session_last_activity_at'] = int(timezone.now().timestamp())
        member_session.save()
        session_key = member_client.session.session_key

        response = owner_client.get(reverse('organization_session_audit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'member@example.com', html=False)

        revoke_response = owner_client.post(
            reverse('organization_session_audit'),
            {'action': 'revoke_session', 'session_key': session_key},
            follow=True,
        )
        self.assertEqual(revoke_response.status_code, 200)

        member_dashboard = member_client.get(reverse('dashboard'))
        self.assertEqual(member_dashboard.status_code, 302)
        self.assertIn(reverse('login'), member_dashboard['Location'])

    def test_owner_can_export_session_audit_csv(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.get(reverse('organization_session_audit_export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        body = response.content.decode('utf-8')
        self.assertIn('organization,Secure Org', body)
        self.assertIn('session_key,username,email,role,last_activity_at,expire_date,is_expired', body)
