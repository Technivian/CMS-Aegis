import json

from django.core.management.base import BaseCommand, CommandError

from contracts.models import Organization
from contracts.services.netsuite import (
    NetSuiteSyncError,
    fetch_netsuite_records,
    ingest_netsuite_records,
    map_netsuite_record,
    netsuite_is_configured,
)


class Command(BaseCommand):
    help = 'Fetch and sync NetSuite records through authenticated API access.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', required=True)
        parser.add_argument('--limit', type=int, default=200)
        parser.add_argument('--dry-run', action='store_true', default=False)

    def handle(self, *args, **options):
        organization = Organization.objects.filter(slug=options['organization_slug']).first()
        if organization is None:
            raise CommandError('Organization not found.')
        if not netsuite_is_configured():
            raise CommandError('NetSuite integration is not configured.')

        limit = max(1, int(options['limit']))
        try:
            records = fetch_netsuite_records(limit=limit)
        except NetSuiteSyncError as exc:
            raise CommandError(str(exc))

        if options['dry_run']:
            summary = {'total_records': len(records), 'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}
            for index, record in enumerate(records):
                try:
                    mapped = map_netsuite_record(record)
                    source_id = str(mapped.get('source_system_id', '') or '').strip()
                    title = str(mapped.get('contract_title', '') or '').strip()
                    if not source_id or not title:
                        summary['skipped'] += 1
                        continue
                    exists = organization.contracts.filter(source_system='netsuite', source_system_id=source_id).exists()
                    if exists:
                        summary['updated'] += 1
                    else:
                        summary['created'] += 1
                except Exception as exc:
                    summary['errors'].append({'index': index, 'error': str(exc)})
        else:
            summary = ingest_netsuite_records(organization, records)
        summary['fetched_records'] = len(records)
        summary['dry_run'] = bool(options['dry_run'])
        summary['source'] = 'netsuite_api'

        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
