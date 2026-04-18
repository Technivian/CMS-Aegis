import csv
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from contracts.models import Contract, Organization


DEFAULT_FIELD_MAPPING = {
    'title': 'title',
    'counterparty': 'counterparty',
    'contract_type': 'contract_type',
    'status': 'status',
    'value': 'value',
    'currency': 'currency',
    'governing_law': 'governing_law',
    'jurisdiction': 'jurisdiction',
    'risk_level': 'risk_level',
    'content': 'content',
    'start_date': 'start_date',
    'end_date': 'end_date',
}


class Command(BaseCommand):
    help = 'Import contracts from CSV with header mapping and reconciliation.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', required=True)
        parser.add_argument('--path', required=True)
        parser.add_argument('--mapping', default='')

    def handle(self, *args, **options):
        organization = Organization.objects.filter(slug=options['organization_slug']).first()
        if organization is None:
            raise CommandError('Organization not found.')

        path = options['path']
        try:
            with open(path, newline='', encoding='utf-8') as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
        except OSError as exc:
            raise CommandError(str(exc))

        mapping = DEFAULT_FIELD_MAPPING.copy()
        if options['mapping']:
            try:
                mapping.update(json.loads(options['mapping']))
            except json.JSONDecodeError as exc:
                raise CommandError(f'Invalid mapping JSON: {exc}')

        created = 0
        updated = 0
        for row in rows:
            data = {}
            for source_field, target_field in mapping.items():
                value = row.get(source_field, '')
                if value in {'', None}:
                    continue
                data[target_field] = value.strip() if isinstance(value, str) else value

            title = data.get('title')
            counterparty = data.get('counterparty', '')
            if not title:
                continue

            contract = Contract.objects.filter(organization=organization, title__iexact=title, counterparty__iexact=counterparty).first()
            if contract is None:
                contract = Contract(organization=organization)
                created += 1
            else:
                updated += 1

            contract.title = title
            contract.counterparty = counterparty
            contract.contract_type = data.get('contract_type', contract.contract_type)
            contract.status = data.get('status', contract.status)
            contract.currency = data.get('currency', contract.currency)
            contract.governing_law = data.get('governing_law', contract.governing_law)
            contract.jurisdiction = data.get('jurisdiction', contract.jurisdiction)
            contract.risk_level = data.get('risk_level', contract.risk_level)
            contract.content = data.get('content', contract.content)
            if data.get('value'):
                try:
                    contract.value = Decimal(str(data['value']))
                except Exception:
                    pass
            if data.get('start_date'):
                contract.start_date = parse_date(str(data['start_date']))
            if data.get('end_date'):
                contract.end_date = parse_date(str(data['end_date']))
            contract.save()

        self.stdout.write(self.style.SUCCESS(f'Imported {len(rows)} row(s): {created} created, {updated} updated.'))
