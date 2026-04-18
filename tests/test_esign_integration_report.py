import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from contracts.models import AuditLog, Contract, Organization, SignatureRequest


User = get_user_model()


class ESignIntegrationReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='esign-report-user', password='pass12345')
        self.organization = Organization.objects.create(name='E-Sign Report Org', slug='esign-report-org')
        self.contract = Contract.objects.create(
            organization=self.organization,
            title='E-Sign Contract',
        )
        self.signature = SignatureRequest.objects.create(
            organization=self.organization,
            contract=self.contract,
            signer_name='Signer',
            signer_email='signer@example.com',
            status=SignatureRequest.Status.SIGNED,
            external_id='sig-123',
            created_by=self.user,
        )

    def test_generate_esign_integration_report_is_go_with_applied_event_and_terminal_signature(self):
        AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            model_name='ESignEvent',
            object_id=self.signature.id,
            object_repr='event:evt-123',
            changes={
                'event_id': 'evt-123',
                'applied': True,
                'to_status': SignatureRequest.Status.SIGNED,
                'dry_run': False,
            },
        )

        out = StringIO()
        call_command(
            'generate_esign_integration_report',
            '--organization-slug=esign-report-org',
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertEqual(payload['status'], 'GO')
        self.assertEqual(payload['observed']['applied_event_count'], 1)
        self.assertEqual(payload['observed']['terminal_signature_count'], 1)

    def test_generate_esign_integration_report_no_go_without_applied_event(self):
        out = StringIO()
        call_command(
            'generate_esign_integration_report',
            '--organization-slug=esign-report-org',
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertEqual(payload['status'], 'NO-GO')
        self.assertEqual(payload['observed']['applied_event_count'], 0)

    def test_generate_esign_integration_report_fail_on_no_go_raises(self):
        with self.assertRaises(CommandError):
            call_command(
                'generate_esign_integration_report',
                '--organization-slug=esign-report-org',
                '--fail-on-no-go',
            )
