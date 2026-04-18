import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from contracts.models import Organization
from contracts.services.netsuite import ingest_netsuite_records


class Command(BaseCommand):
    help = 'Ingest NetSuite contract records (JSON list) into contracts for an organization.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', required=True)
        parser.add_argument('--path', required=True, help='Path to JSON file containing a list of records.')

    def handle(self, *args, **options):
        organization = Organization.objects.filter(slug=options['organization_slug']).first()
        if organization is None:
            raise CommandError('Organization not found.')

        payload_path = Path(options['path'])
        if not payload_path.exists():
            raise CommandError(f'File not found: {payload_path}')

        try:
            records = json.loads(payload_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid JSON payload: {exc}')
        if not isinstance(records, list):
            raise CommandError('JSON payload must be a top-level list.')

        summary = ingest_netsuite_records(organization, records)
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
