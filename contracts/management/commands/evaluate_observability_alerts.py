import json

from django.core.management.base import BaseCommand

from contracts.observability import evaluate_alert_policy


class Command(BaseCommand):
    help = 'Evaluate observability alert policy from in-app telemetry snapshots.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Emit JSON output.')

    def handle(self, *args, **options):
        evaluation = evaluate_alert_policy()

        if options['json']:
            self.stdout.write(json.dumps(evaluation, indent=2))
        else:
            self.stdout.write(self.style.SUCCESS(f"Alert status: {evaluation['alert_status']}"))
            if evaluation['p1_alerts']:
                self.stdout.write(self.style.ERROR(f"P1 alerts: {', '.join(evaluation['p1_alerts'])}"))
            if evaluation['p2_alerts']:
                self.stdout.write(self.style.WARNING(f"P2 alerts: {', '.join(evaluation['p2_alerts'])}"))
            self.stdout.write(f"5xx rate: {evaluation['five_xx_rate_pct']}%")

        if evaluation['alert_status'] == 'P1':
            raise SystemExit(2)
        if evaluation['alert_status'] == 'P2':
            raise SystemExit(1)
