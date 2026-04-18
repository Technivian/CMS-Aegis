import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contracts.models import Organization, SalesforceOrganizationConnection, SalesforceSyncRun
from contracts.services.salesforce import (
    SalesforceSyncError,
    create_salesforce_sync_run,
    sync_salesforce_connection,
)
from contracts.services.webhooks import queue_webhook_event


class Command(BaseCommand):
    help = 'Sync Salesforce records into contracts for an organization connection.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', required=True)
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--limit', type=int, default=200)

    def handle(self, *args, **options):
        organization = Organization.objects.filter(slug=options['organization_slug']).first()
        if organization is None:
            raise CommandError('Organization not found.')

        connection = SalesforceOrganizationConnection.objects.filter(organization=organization, is_active=True).first()
        if connection is None:
            raise CommandError('No active Salesforce connection.')

        dry_run = bool(options['dry_run'])
        limit = max(1, int(options['limit']))
        try:
            run = create_salesforce_sync_run(
                organization=organization,
                connection=connection,
                trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
                dry_run=dry_run,
                limit=limit,
            )
        except SalesforceSyncError as exc:
            raise CommandError(str(exc))

        try:
            summary = sync_salesforce_connection(
                connection,
                dry_run=dry_run,
                limit=limit,
            )
        except SalesforceSyncError as exc:
            run.status = SalesforceSyncRun.Status.FAILED
            run.error_message = str(exc)
            run.completed_at = timezone.now()
            run.save(update_fields=['status', 'error_message', 'completed_at'])
            queue_webhook_event(
                organization=organization,
                event_type='salesforce.sync.failed',
                payload={
                    'run_id': run.id,
                    'status': run.status,
                    'error_message': run.error_message,
                    'dry_run': dry_run,
                    'limit': limit,
                },
            )
            raise CommandError(str(exc))

        run.status = SalesforceSyncRun.Status.SUCCESS
        run.source_object = str(summary.get('source_object', '') or '')
        run.fetched_records = int(summary.get('fetched_records', 0) or 0)
        run.created_count = int(summary.get('created', 0) or 0)
        run.updated_count = int(summary.get('updated', 0) or 0)
        run.skipped_count = int(summary.get('skipped', 0) or 0)
        run.error_count = len(summary.get('errors') or [])
        run.summary = summary
        run.completed_at = timezone.now()
        run.save(
            update_fields=[
                'status',
                'source_object',
                'fetched_records',
                'created_count',
                'updated_count',
                'skipped_count',
                'error_count',
                'summary',
                'completed_at',
            ]
        )
        queue_webhook_event(
            organization=organization,
            event_type='salesforce.sync.completed',
            payload={
                'run_id': run.id,
                'status': run.status,
                'dry_run': dry_run,
                'summary': summary,
            },
        )

        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
