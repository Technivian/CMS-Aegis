from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate full performance evidence bundle (core profile, auth profile, load test, query plan).'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default='perf-probe-user')
        parser.add_argument('--password', type=str, default='perf-probe-pass-123')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        self.stdout.write(self.style.SUCCESS('Running core route profile...'))
        call_command(
            'profile_core_routes',
            iterations=20,
            output='docs/PERFORMANCE_BASELINE_2026-04-13.json',
        )

        self.stdout.write(self.style.SUCCESS('Running top authenticated route profile...'))
        call_command(
            'profile_authenticated_routes',
            iterations=10,
            username=username,
            password=password,
            output='docs/AUTH_ROUTE_PROFILE_2026-04-13.json',
        )

        self.stdout.write(self.style.SUCCESS('Running 2x peak load test...'))
        call_command(
            'run_core_load_test',
            peak_rps=5,
            multiplier=2.0,
            duration_seconds=20,
            workers=4,
            username=username,
            password=password,
            output='docs/LOAD_TEST_2X_2026-04-13.json',
        )

        self.stdout.write(self.style.SUCCESS('Generating query plan report...'))
        # Shell wrapper keeps explain output deterministic in markdown.
        import subprocess

        subprocess.run(['./scripts/generate_query_plan_report.sh'], check=True)

        self.stdout.write(self.style.SUCCESS('Rendering markdown summaries...'))
        subprocess.run(['.venv/bin/python', 'scripts/render_performance_reports.py'], check=True)

        self.stdout.write(self.style.SUCCESS('Performance evidence bundle complete.'))
