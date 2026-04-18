import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contracts.models import SalesforceSyncRun, WebhookDelivery


class Command(BaseCommand):
    help = 'Generate Sprint 3 integration evidence report (Salesforce sync + webhook outcomes).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=14)
        parser.add_argument('--output', default='')
        parser.add_argument('--require-dead-letter-evidence', action='store_true')
        parser.add_argument('--fail-on-no-go', action='store_true')

    def handle(self, *args, **options):
        days = max(1, int(options['days']))
        since = timezone.now() - timedelta(days=days)

        successful_sync = (
            SalesforceSyncRun.objects.filter(
                status=SalesforceSyncRun.Status.SUCCESS,
                completed_at__gte=since,
            )
            .filter(created_count__gt=0)
            .order_by('-completed_at')
            .first()
        )
        if successful_sync is None:
            successful_sync = (
                SalesforceSyncRun.objects.filter(
                    status=SalesforceSyncRun.Status.SUCCESS,
                    completed_at__gte=since,
                )
                .filter(updated_count__gt=0)
                .order_by('-completed_at')
                .first()
            )

        sent_delivery = (
            WebhookDelivery.objects.filter(
                status=WebhookDelivery.Status.SENT,
                created_at__gte=since,
            )
            .order_by('-created_at')
            .first()
        )
        dead_letter_delivery = (
            WebhookDelivery.objects.filter(
                status=WebhookDelivery.Status.DEAD_LETTER,
                created_at__gte=since,
            )
            .order_by('-created_at')
            .first()
        )

        sync_ok = successful_sync is not None
        sent_ok = sent_delivery is not None
        dead_letter_ok = dead_letter_delivery is not None
        dead_letter_required = bool(options['require_dead_letter_evidence'])
        integrations_ok = sync_ok and sent_ok and (dead_letter_ok if dead_letter_required else True)

        payload = {
            'captured_at': timezone.now().isoformat(),
            'window_days': days,
            'requirements': {
                'salesforce_sync_created_or_updated_gt_zero': True,
                'webhook_sent_event_present': True,
                'webhook_dead_letter_present': dead_letter_required,
            },
            'observed': {
                'salesforce_sync_run': (
                    {
                        'id': successful_sync.id,
                        'organization_id': successful_sync.organization_id,
                        'completed_at': successful_sync.completed_at.isoformat() if successful_sync.completed_at else None,
                        'created_count': successful_sync.created_count,
                        'updated_count': successful_sync.updated_count,
                        'status': successful_sync.status,
                    }
                    if successful_sync
                    else None
                ),
                'webhook_sent_delivery': (
                    {
                        'id': sent_delivery.id,
                        'organization_id': sent_delivery.organization_id,
                        'event_type': sent_delivery.event_type,
                        'sent_at': sent_delivery.sent_at.isoformat() if sent_delivery.sent_at else None,
                        'status': sent_delivery.status,
                    }
                    if sent_delivery
                    else None
                ),
                'webhook_dead_letter_delivery': (
                    {
                        'id': dead_letter_delivery.id,
                        'organization_id': dead_letter_delivery.organization_id,
                        'event_type': dead_letter_delivery.event_type,
                        'dead_lettered_at': (
                            dead_letter_delivery.dead_lettered_at.isoformat()
                            if dead_letter_delivery.dead_lettered_at
                            else None
                        ),
                        'status': dead_letter_delivery.status,
                    }
                    if dead_letter_delivery
                    else None
                ),
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
            raise CommandError('Sprint 3 integration report is NO-GO.')
