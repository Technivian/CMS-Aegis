import json

from django.core.management.base import BaseCommand, CommandError

from contracts.models import Organization, SalesforceOrganizationConnection
from contracts.services.salesforce import SalesforceSyncError, sync_salesforce_connection


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

        try:
            summary = sync_salesforce_connection(
                connection,
                dry_run=bool(options['dry_run']),
                limit=max(1, int(options['limit'])),
            )
        except SalesforceSyncError as exc:
            raise CommandError(str(exc))

        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
