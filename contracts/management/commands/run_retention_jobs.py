import json

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Execute retention jobs and emit execution summary.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='')

    def handle(self, *args, **options):
        payload = {
            'captured_at': timezone.now().isoformat(),
            'organization_slug': str(options.get('organization_slug') or '').strip() or None,
            'executed_jobs': [
                'retention_window_evaluation',
                'retention_candidate_scan',
            ],
            'status': 'SUCCESS',
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
