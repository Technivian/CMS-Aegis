from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest import mock

from contracts.models import AuditLog, Notification, Organization, OrganizationMembership


User = get_user_model()


class SecurityGuardrailsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='security-user',
            email='security@example.com',
            password='testpass123',
        )
        self.organization = Organization.objects.create(name='Security Org', slug='security-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

    @override_settings(
        SECURITY_HEADERS_ENABLED=True,
        CONTENT_SECURITY_POLICY="default-src 'self'",
        PERMISSIONS_POLICY='geolocation=()',
    )
    def test_security_headers_are_present(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Content-Security-Policy', response)
        self.assertEqual(response['Content-Security-Policy'], "default-src 'self'")
        self.assertIn('Permissions-Policy', response)
        self.assertEqual(response['Permissions-Policy'], 'geolocation=()')
        self.assertIn('X-Content-Type-Options', response)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    @override_settings(
        RATELIMIT_ENABLED=True,
        LOGIN_RATE_LIMIT_REQUESTS=2,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS=60,
        RATELIMIT_TRUSTED_IPS=(),
    )
    def test_login_rate_limit_blocks_after_threshold(self):
        for _ in range(2):
            response = self.client.post(
                reverse('login'),
                {'username': 'security-user', 'password': 'wrong-password'},
                REMOTE_ADDR='203.0.113.10',
            )
            self.assertEqual(response.status_code, 200)

        blocked = self.client.post(
            reverse('login'),
            {'username': 'security-user', 'password': 'wrong-password'},
            REMOTE_ADDR='203.0.113.10',
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertIn('Retry-After', blocked)

    @override_settings(
        RATELIMIT_ENABLED=True,
        RATELIMIT_TRUSTED_IPS=(),
    )
    def test_auth_rate_limit_fails_open_when_cache_errors(self):
        with mock.patch('contracts.middleware.cache.get', side_effect=RuntimeError('cache down')):
            response = self.client.post(
                reverse('register'),
                {
                    'username': 'cache-error-user',
                    'email': 'cache-error@example.com',
                    'password1': 'SafePass123!',
                    'password2': 'Mismatch123!',
                },
                REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(response.status_code, 500)
        self.assertContains(response, 'Auth rate limit failed open', status_code=500)

    def test_notification_mutations_emit_audit_logs(self):
        self.client.login(username='security-user', password='testpass123')
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Security notice',
            message='Test',
        )

        response_one = self.client.post(
            reverse('contracts:mark_notification_read', kwargs={'pk': notification.pk})
        )
        self.assertEqual(response_one.status_code, 302)

        response_all = self.client.post(reverse('contracts:mark_all_notifications_read'))
        self.assertEqual(response_all.status_code, 302)

        self.assertTrue(
            AuditLog.objects.filter(
                user=self.user,
                model_name='Notification',
                changes__event='mark_notification_read',
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.user,
                model_name='Notification',
                changes__event='mark_all_notifications_read',
            ).exists()
        )
