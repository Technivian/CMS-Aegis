import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from contracts.observability import db_health_snapshot, evaluate_alert_policy, request_metrics_snapshot, scheduler_health_snapshot


class Command(BaseCommand):
    help = 'Collect weekly control evidence snapshots for security/operations controls.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            default='docs/evidence',
            help='Directory where evidence snapshots are written.',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        payload = {
            'captured_at': now.isoformat(),
            'control_catalog_version': 'sprint-1',
            'controls': {
                'ops.request_metrics': request_metrics_snapshot(),
                'ops.scheduler_health': scheduler_health_snapshot(),
                'ops.database_health': db_health_snapshot(),
                'ops.alert_policy': evaluate_alert_policy(),
            },
        }

        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f'control-evidence-{now.strftime("%Y%m%dT%H%M%SZ")}.json'
        output_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Control evidence written: {output_file}'))
