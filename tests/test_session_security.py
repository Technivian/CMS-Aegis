from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import Organization, OrganizationMembership, UserProfile
from contracts.session_security import revoke_user_sessions


User = get_user_model()


class SessionSecurityTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Session Org', slug='session-org')
        self.user = User.objects.create_user(username='session-user', password='testpass123')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        UserProfile.objects.get_or_create(user=self.user)
        self.dashboard_url = reverse('dashboard')

    def test_idle_timeout_redirects_and_flushes_session(self):
        self.client.login(username='session-user', password='testpass123')
        session = self.client.session
        session['session_last_activity_at'] = int((timezone.now() - timedelta(minutes=180)).timestamp())
        session['session_revocation_counter'] = 0
        session.save()

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_session_revoke_invalidates_existing_session(self):
        self.client.login(username='session-user', password='testpass123')
        session = self.client.session
        session['session_last_activity_at'] = int(timezone.now().timestamp())
        session['session_revocation_counter'] = 0
        session.save()

        revoke_user_sessions(self.user)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])
