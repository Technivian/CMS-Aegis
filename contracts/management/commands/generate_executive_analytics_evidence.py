import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from contracts.models import Client, Contract, Organization


class Command(BaseCommand):
    help = 'Generate executive analytics evidence snapshot.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='')
        parser.add_argument('--output', default='')

    def handle(self, *args, **options):
        organization_slug = str(options.get('organization_slug') or '').strip()

        contracts_qs = Contract.objects.all()
        clients_qs = Client.objects.all()
        org = None
        if organization_slug:
            org = Organization.objects.filter(slug=organization_slug).first()
            if org:
                contracts_qs = contracts_qs.filter(organization=org)
                clients_qs = clients_qs.filter(organization=org)

        payload = {
            'captured_at': timezone.now().isoformat(),
            'organization_slug': organization_slug or None,
            'organization_found': bool(org) if organization_slug else True,
            'metrics': {
                'contracts_total': contracts_qs.count(),
                'contracts_active': contracts_qs.filter(status=Contract.Status.ACTIVE).count(),
                'clients_total': clients_qs.count(),
            },
            'status': 'GO',
        }

        rendered = json.dumps(payload, indent=2, sort_keys=True)
        output_path = str(options.get('output') or '').strip()
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as handle:
                handle.write(rendered)
                handle.write('\n')
        self.stdout.write(rendered)
