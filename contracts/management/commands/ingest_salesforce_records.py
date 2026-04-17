import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from contracts.models import Organization
from contracts.services.salesforce import ingest_salesforce_records


class Command(BaseCommand):
    help = 'Ingest Salesforce JSON records into contracts using org field mapping.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', required=True)
        parser.add_argument('--path', required=True, help='Path to JSON file with a top-level list of records.')
        parser.add_argument('--dry-run', action='store_true', default=False)

    def handle(self, *args, **options):
        organization = Organization.objects.filter(slug=options['organization_slug']).first()
        if organization is None:
            raise CommandError('Organization not found.')

        source_path = Path(options['path'])
        if not source_path.exists():
            raise CommandError(f'File not found: {source_path}')

        try:
            payload = json.loads(source_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid JSON: {exc}')

        if not isinstance(payload, list):
            raise CommandError('JSON payload must be a top-level list.')

        summary = ingest_salesforce_records(organization, payload, dry_run=options['dry_run'])
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
