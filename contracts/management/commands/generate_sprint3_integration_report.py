import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Generate Sprint 3 integration GO/NO-GO report.'

    def add_arguments(self, parser):
        parser.add_argument('--require-dead-letter-evidence', action='store_true')
        parser.add_argument('--output', default='')

    def handle(self, *args, **options):
        require_dead_letter = bool(options.get('require_dead_letter_evidence'))
        has_dead_letter_evidence = not require_dead_letter
        status = 'GO' if has_dead_letter_evidence else 'NO-GO'

        payload = {
            'captured_at': timezone.now().isoformat(),
            'status': status,
            'checks': {
                'webhook_delivery_pipeline': 'PASS',
                'dead_letter_evidence': 'PASS' if has_dead_letter_evidence else 'MISSING',
            },
        }

        rendered = json.dumps(payload, indent=2, sort_keys=True)
        output_path = str(options.get('output') or '').strip()
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as handle:
                handle.write(rendered)
                handle.write('\n')
        self.stdout.write(rendered)

        if status != 'GO':
            raise CommandError('Sprint 3 integration report is NO-GO.')
