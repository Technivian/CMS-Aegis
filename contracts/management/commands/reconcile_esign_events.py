import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from contracts.models import SignatureRequest
from contracts.services.esign import ESignReconciliationError, apply_esign_event


class Command(BaseCommand):
    help = 'Reconcile e-sign provider webhook events idempotently (supports out-of-order events).'

    def add_arguments(self, parser):
        parser.add_argument('--path', required=True, help='Path to JSON file with webhook events list.')
        parser.add_argument('--organization-slug', default='')
        parser.add_argument('--dry-run', action='store_true', default=False)

    def handle(self, *args, **options):
        payload_path = Path(options['path'])
        if not payload_path.exists():
            raise CommandError(f'File not found: {payload_path}')

        try:
            payload = json.loads(payload_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid JSON payload: {exc}')
        if not isinstance(payload, list):
            raise CommandError('JSON payload must be a top-level list of events.')

        def _sort_key(event):
            dt = parse_datetime(str(event.get('event_at') or ''))
            if dt is None:
                return '9999-12-31T23:59:59+00:00'
            return dt.isoformat()

        events = sorted(payload, key=_sort_key)
        org_slug = str(options.get('organization_slug') or '').strip()
        dry_run = bool(options['dry_run'])
        summary = {
            'total_events': len(events),
            'applied': 0,
            'would_apply': 0,
            'duplicate': 0,
            'stale': 0,
            'errors': [],
        }

        for index, event in enumerate(events):
            if not isinstance(event, dict):
                summary['errors'].append({'index': index, 'error': 'Event must be an object.'})
                continue
            signature_request = None
            signature_request_id = event.get('signature_request_id')
            external_id = str(event.get('external_id') or '').strip()
            if signature_request_id:
                signature_request = SignatureRequest.objects.filter(id=signature_request_id).first()
            if signature_request is None and external_id:
                signature_request = SignatureRequest.objects.filter(external_id=external_id).order_by('-id').first()
            if signature_request is None:
                summary['errors'].append({'index': index, 'error': 'Signature request not found.'})
                continue
            if org_slug and signature_request.organization and signature_request.organization.slug != org_slug:
                summary['errors'].append({'index': index, 'error': 'Signature request outside organization scope.'})
                continue

            try:
                result = apply_esign_event(signature_request, event, dry_run=dry_run)
            except ESignReconciliationError as exc:
                summary['errors'].append({'index': index, 'error': str(exc)})
                continue

            result_key = str(result.get('result') or '')
            if result_key in summary:
                summary[result_key] += 1
            else:
                summary['errors'].append({'index': index, 'error': f'Unknown reconciliation result: {result_key}'})

        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
