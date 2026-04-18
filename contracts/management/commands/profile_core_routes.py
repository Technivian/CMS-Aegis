import json
import time
from statistics import median

from django.core.management.base import BaseCommand
from django.test import Client


class Command(BaseCommand):
    help = 'Profile core route latency (p50/p95/max) using Django test client.'

    def add_arguments(self, parser):
        parser.add_argument('--iterations', type=int, default=20, help='Requests per route (default: 20).')
        parser.add_argument('--username', type=str, default='', help='Optional username for authenticated routes.')
        parser.add_argument('--password', type=str, default='', help='Optional password for authenticated routes.')
        parser.add_argument('--output', type=str, default='', help='Optional output JSON file path.')

    def handle(self, *args, **options):
        iterations = max(1, int(options['iterations']))
        username = (options.get('username') or '').strip()
        password = (options.get('password') or '').strip()
        output_path = (options.get('output') or '').strip()

        client = Client()
        if username and password:
            if not client.login(username=username, password=password):
                self.stderr.write(self.style.ERROR('Authentication failed for provided credentials.'))
                return

        routes = [
            '/_health/',
            '/_health/?format=json',
            '/contracts/',
            '/contracts/api/contracts/',
        ]

        report = {
            'iterations': iterations,
            'authenticated': bool(username and password),
            'routes': {},
        }

        for route in routes:
            timings = []
            statuses = []
            for _ in range(iterations):
                started = time.perf_counter()
                response = client.get(route)
                latency_ms = (time.perf_counter() - started) * 1000
                timings.append(latency_ms)
                statuses.append(response.status_code)

            sorted_timings = sorted(timings)
            p50 = sorted_timings[len(sorted_timings) // 2]
            p95_index = max(0, int(len(sorted_timings) * 0.95) - 1)
            p95 = sorted_timings[p95_index]
            success_count = sum(1 for status in statuses if status < 500)

            report['routes'][route] = {
                'count': len(sorted_timings),
                'p50_ms': round(p50, 2),
                'p95_ms': round(p95, 2),
                'max_ms': round(max(sorted_timings), 2),
                'mean_ms': round(sum(sorted_timings) / len(sorted_timings), 2),
                'median_ms': round(median(sorted_timings), 2),
                'status_codes': sorted(set(statuses)),
                'success_rate': round(success_count / len(statuses), 3),
            }

        rendered = json.dumps(report, indent=2)
        self.stdout.write(rendered)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as output_file:
                output_file.write(rendered)
            self.stdout.write(self.style.SUCCESS(f'Wrote report to {output_path}'))
