from django.core.management.base import BaseCommand

from contracts.models import (
    ApprovalRule,
    ClauseCategory,
    ClauseTemplate,
    Counterparty,
    Organization,
    RetentionPolicy,
    Subprocessor,
)
from contracts.services.starter_content import ensure_org_starter_content


GLOBAL_MODELS = [
    Counterparty,
    ClauseCategory,
    ClauseTemplate,
    Subprocessor,
    RetentionPolicy,
    ApprovalRule,
]


class Command(BaseCommand):
    help = 'Copy starter catalog data into every organization and optionally remove legacy global rows.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup-global',
            action='store_true',
            help='Delete legacy global starter rows after promotion.',
        )

    def handle(self, *args, **options):
        orgs = list(Organization.objects.filter(is_active=True).order_by('id'))
        for organization in orgs:
            ensure_org_starter_content(organization)
            self.stdout.write(f'Ensured starter content for {organization.slug}')

        if options['cleanup_global']:
            for model in GLOBAL_MODELS:
                deleted, _ = model.objects.filter(organization__isnull=True).delete()
                self.stdout.write(f'Deleted {deleted} global row(s) from {model.__name__}')

        self.stdout.write(self.style.SUCCESS('Starter content promotion complete.'))
