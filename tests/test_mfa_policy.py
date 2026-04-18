from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import AuditLog, Organization, OrganizationMembership, UserProfile


User = get_user_model()


class MfaPolicyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='mfa-user',
            email='mfa@example.com',
            password='testpass123',
            first_name='Mfa',
            last_name='User',
        )
        self.org = Organization.objects.create(name='MFA Org', slug='mfa-org', require_mfa=True)
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)

    def _profile_payload(self):
        return {
            'first_name': 'Mfa',
            'last_name': 'User',
            'email': 'mfa@example.com',
            'role': self.profile.role,
            'phone': '',
            'bar_number': '',
            'department': '',
            'hourly_rate': '',
            'bio': 'Security focused',
            'mfa_enabled': 'on',
            'mfa_enrollment_code': '123456',
        }

    @patch('contracts.views_domains.actions.send_mail')
    @patch('contracts.models.secrets.randbelow', return_value=123456)
    def test_mfa_required_org_blocks_dashboard_until_profile_enabled(self, mock_randbelow, mock_send_mail):
        self.assertTrue(self.client.login(username='mfa-user', password='testpass123'))

        blocked = self.client.get(reverse('dashboard'))
        self.assertEqual(blocked.status_code, 302)
        self.assertIn(reverse('login'), blocked.url)

        profile_page = self.client.get(reverse('profile'))
        self.assertEqual(profile_page.status_code, 200)

        request_code = self.client.post(reverse('profile'), data={'action': 'send_mfa_code'}, follow=True)
        self.assertEqual(request_code.status_code, 200)
        mock_send_mail.assert_called_once()

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.mfa_enrollment_code_hash)

        submit = self.client.post(reverse('profile'), data=self._profile_payload())
        self.assertEqual(submit.status_code, 302)

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.mfa_enabled)
        self.assertIsNotNone(self.profile.mfa_verified_at)

        allowed = self.client.get(reverse('dashboard'))
        self.assertEqual(allowed.status_code, 200)

        update = self.client.post(
            reverse('profile'),
            data={
                'first_name': 'Mfa',
                'last_name': 'User',
                'email': 'mfa@example.com',
                'role': self.profile.role,
                'phone': '555-0100',
                'bar_number': '',
                'department': '',
                'hourly_rate': '',
                'bio': 'Updated bio',
                'mfa_enabled': 'on',
                'mfa_enrollment_code': '',
            },
        )
        self.assertEqual(update.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, 'Updated bio')

    def test_mfa_enrollment_requires_verification_code(self):
        self.assertTrue(self.client.login(username='mfa-user', password='testpass123'))

        submit = self.client.post(reverse('profile'), data=self._profile_payload())
        self.assertEqual(submit.status_code, 200)
        self.assertContains(submit, 'Enter the 6-digit verification code sent to your email.', html=False)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.mfa_enabled)
        self.assertIsNone(self.profile.mfa_verified_at)

    def test_recovery_codes_can_be_generated_and_used(self):
        self.assertTrue(self.client.login(username='mfa-user', password='testpass123'))
        self.profile.mfa_enabled = True
        self.profile.mfa_verified_at = self.profile.mfa_verified_at or timezone.now()
        self.profile.save(update_fields=['mfa_enabled', 'mfa_verified_at', 'updated_at'])

        response = self.client.post(reverse('profile'), data={'action': 'generate_mfa_recovery_codes'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recovery codes', html=False)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.mfa_recovery_code_count, 8)
        recovery_codes = None
        for context in response.context:
            if 'recovery_codes_preview' in context:
                recovery_codes = context['recovery_codes_preview']
                break
        self.assertIsNotNone(recovery_codes)
        self.assertEqual(len(recovery_codes), 8)

        submit = self.client.post(
            reverse('profile'),
            data={
                'first_name': 'Mfa',
                'last_name': 'User',
                'email': 'mfa@example.com',
                'role': self.profile.role,
                'phone': '',
                'bar_number': '',
                'department': '',
                'hourly_rate': '',
                'bio': 'Security focused',
                'mfa_enabled': 'on',
                'mfa_enrollment_code': '',
                'mfa_recovery_code': recovery_codes[0],
            },
        )
        self.assertEqual(submit.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.mfa_recovery_code_count, 7)
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.user,
                model_name='UserProfile',
                changes__event='mfa_recovery_codes_generated',
            ).exists()
        )
