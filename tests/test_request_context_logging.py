import logging

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from contracts.logging_context import (
    RequestContextLogFilter,
    request_id_var,
    request_org_id_var,
    request_path_var,
    request_user_id_var,
)
from contracts.models import Organization, OrganizationMembership


class RequestContextLoggingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='logger',
            email='logger@example.com',
            password='testpass123',
        )
        self.organization = Organization.objects.create(name='Logging Org', slug='logging-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

    def test_dashboard_response_sets_request_id_header(self):
        self.client.login(username='logger', password='testpass123')

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('X-Request-ID', response)
        self.assertTrue(response['X-Request-ID'])

    def test_log_filter_injects_request_context(self):
        request_id_token = request_id_var.set('req-123')
        user_token = request_user_id_var.set('11')
        org_token = request_org_id_var.set('22')
        path_token = request_path_var.set('/dashboard/')

        try:
            record = logging.LogRecord(
                name='contracts.middleware',
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg='request_completed',
                args=(),
                exc_info=None,
            )

            RequestContextLogFilter().filter(record)

            self.assertEqual(record.request_id, 'req-123')
            self.assertEqual(record.request_user_id, '11')
            self.assertEqual(record.request_org_id, '22')
            self.assertEqual(record.request_path, '/dashboard/')
        finally:
            request_id_var.reset(request_id_token)
            request_user_id_var.reset(user_token)
            request_org_id_var.reset(org_token)
            request_path_var.reset(path_token)
