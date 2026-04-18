import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from contracts.models import Organization, SalesforceSyncRun, WebhookDelivery, WebhookEndpoint


class Sprint3IntegrationReportTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Integration Org', slug='integration-org')
        self.endpoint = WebhookEndpoint.objects.create(
            organization=self.organization,
            name='primary',
            url='https://example.com/webhooks/contracts',
        )

    def test_report_is_go_with_success_sync_and_sent_delivery(self):
        SalesforceSyncRun.objects.create(
            organization=self.organization,
            trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
            status=SalesforceSyncRun.Status.SUCCESS,
            completed_at=timezone.now(),
            created_count=1,
        )
        WebhookDelivery.objects.create(
            organization=self.organization,
            endpoint=self.endpoint,
            event_type='salesforce.sync.completed',
            status=WebhookDelivery.Status.SENT,
            sent_at=timezone.now(),
        )

        out = StringIO()
        call_command('generate_sprint3_integration_report', stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload['status'], 'GO')
        self.assertIsNotNone(payload['observed']['salesforce_sync_run'])
        self.assertIsNotNone(payload['observed']['webhook_sent_delivery'])

    def test_report_is_no_go_when_dead_letter_required_but_missing(self):
        SalesforceSyncRun.objects.create(
            organization=self.organization,
            trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
            status=SalesforceSyncRun.Status.SUCCESS,
            completed_at=timezone.now(),
            updated_count=1,
        )
        WebhookDelivery.objects.create(
            organization=self.organization,
            endpoint=self.endpoint,
            event_type='salesforce.sync.completed',
            status=WebhookDelivery.Status.SENT,
            sent_at=timezone.now(),
        )

        out = StringIO()
        call_command('generate_sprint3_integration_report', '--require-dead-letter-evidence', stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload['status'], 'NO-GO')
        self.assertIsNone(payload['observed']['webhook_dead_letter_delivery'])

    def test_report_fail_on_no_go_raises(self):
        with self.assertRaises(CommandError):
            call_command(
                'generate_sprint3_integration_report',
                '--require-dead-letter-evidence',
                '--fail-on-no-go',
            )
