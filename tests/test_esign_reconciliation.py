import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from contracts.models import AuditLog, Contract, Organization, SignatureRequest


User = get_user_model()


class ESignReconciliationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='esign-owner', password='pass12345')
        self.organization = Organization.objects.create(name='E-Sign Org', slug='esign-org')
        self.contract = Contract.objects.create(
            organization=self.organization,
            title='Vendor Agreement',
        )
        self.signature_request = SignatureRequest.objects.create(
            organization=self.organization,
            contract=self.contract,
            signer_name='Signer',
            signer_email='signer@example.com',
            status=SignatureRequest.Status.SENT,
            external_id='ext-123',
            created_by=self.user,
        )

    def _run_reconcile(self, events):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'events.json'
            path.write_text(json.dumps(events), encoding='utf-8')
            out = StringIO()
            call_command('reconcile_esign_events', path=str(path), organization_slug='esign-org', stdout=out)
            return json.loads(out.getvalue())

    def test_reconcile_esign_events_applies_out_of_order_events(self):
        summary = self._run_reconcile(
            [
                {
                    'event_id': 'evt-2',
                    'external_id': 'ext-123',
                    'status': 'signed',
                    'event_at': '2026-04-18T10:05:00Z',
                },
                {
                    'event_id': 'evt-1',
                    'external_id': 'ext-123',
                    'status': 'viewed',
                    'event_at': '2026-04-18T10:00:00Z',
                },
            ]
        )
        self.signature_request.refresh_from_db()
        self.assertEqual(summary['applied'], 2)
        self.assertEqual(self.signature_request.status, SignatureRequest.Status.SIGNED)
        self.assertIsNotNone(self.signature_request.signed_at)

    def test_reconcile_esign_events_is_idempotent_for_duplicate_event_id(self):
        events = [
            {
                'event_id': 'evt-dup',
                'external_id': 'ext-123',
                'status': 'viewed',
                'event_at': '2026-04-18T10:00:00Z',
            }
        ]
        first_summary = self._run_reconcile(events)
        second_summary = self._run_reconcile(events)
        self.assertEqual(first_summary['applied'], 1)
        self.assertEqual(second_summary['duplicate'], 1)
        self.assertEqual(
            AuditLog.objects.filter(model_name='ESignEvent', object_id=self.signature_request.id).count(),
            1,
        )

    def test_reconcile_esign_events_ignores_stale_after_terminal_status(self):
        self.signature_request.status = SignatureRequest.Status.SIGNED
        self.signature_request.save(update_fields=['status'])
        summary = self._run_reconcile(
            [
                {
                    'event_id': 'evt-stale',
                    'external_id': 'ext-123',
                    'status': 'viewed',
                    'event_at': '2026-04-18T11:00:00Z',
                }
            ]
        )
        self.signature_request.refresh_from_db()
        self.assertEqual(summary['stale'], 1)
        self.assertEqual(self.signature_request.status, SignatureRequest.Status.SIGNED)
