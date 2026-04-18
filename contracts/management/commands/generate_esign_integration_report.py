import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contracts.models import AuditLog, Organization, SignatureRequest


class Command(BaseCommand):
    help = 'Generate Sprint 3 e-sign integration evidence report.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='')
        parser.add_argument('--days', type=int, default=14)
        parser.add_argument('--output', default='')
        parser.add_argument('--fail-on-no-go', action='store_true')

    def handle(self, *args, **options):
        days = max(1, int(options['days']))
        since = timezone.now() - timedelta(days=days)
        organization_slug = str(options.get('organization_slug') or '').strip()

        organization = None
        if organization_slug:
            organization = Organization.objects.filter(slug=organization_slug).first()
            if organization is None:
                raise CommandError('Organization not found.')

        signature_queryset = SignatureRequest.objects.all()
        if organization is not None:
            signature_queryset = signature_queryset.filter(organization=organization)
        signature_ids = list(signature_queryset.values_list('id', flat=True))

        esign_events = AuditLog.objects.filter(
            model_name='ESignEvent',
            timestamp__gte=since,
        )
        if signature_ids:
            esign_events = esign_events.filter(object_id__in=signature_ids)
        else:
            esign_events = esign_events.none()

        applied_events = esign_events.filter(changes__applied=True)
        duplicate_events = esign_events.filter(changes__applied=False, changes__dry_run=False, changes__to_status__isnull=False)
        latest_applied = applied_events.order_by('-timestamp').first()

        terminal_signatures = signature_queryset.filter(
            status__in=[
                SignatureRequest.Status.SIGNED,
                SignatureRequest.Status.DECLINED,
                SignatureRequest.Status.EXPIRED,
                SignatureRequest.Status.CANCELLED,
            ],
            created_at__gte=since,
        )

        integrations_ok = applied_events.exists() and terminal_signatures.exists()
        payload = {
            'captured_at': timezone.now().isoformat(),
            'window_days': days,
            'organization_slug': organization.slug if organization else None,
            'requirements': {
                'applied_esign_event_present': True,
                'terminal_signature_state_present': True,
            },
            'observed': {
                'applied_event_count': applied_events.count(),
                'duplicate_or_stale_event_count': duplicate_events.count(),
                'latest_applied_event': (
                    {
                        'id': latest_applied.id,
                        'timestamp': latest_applied.timestamp.isoformat() if latest_applied.timestamp else None,
                        'signature_request_id': latest_applied.object_id,
                        'event_id': (latest_applied.changes or {}).get('event_id'),
                        'to_status': (latest_applied.changes or {}).get('to_status'),
                    }
                    if latest_applied
                    else None
                ),
                'terminal_signature_count': terminal_signatures.count(),
            },
            'status': 'GO' if integrations_ok else 'NO-GO',
        }

        rendered = json.dumps(payload, indent=2, sort_keys=True)
        output_path = str(options.get('output') or '').strip()
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as handle:
                handle.write(rendered)
                handle.write('\n')
        self.stdout.write(rendered)

        if options['fail_on_no_go'] and payload['status'] != 'GO':
            raise CommandError('E-sign integration report is NO-GO.')
