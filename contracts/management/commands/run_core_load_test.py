import json
import threading
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from time import perf_counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from contracts.models import Client, Contract, Organization, OrganizationMembership


User = get_user_model()


class Command(BaseCommand):
    help = 'Run a lightweight concurrent load test against core authenticated routes.'

    def add_arguments(self, parser):
        parser.add_argument('--peak-rps', type=int, default=5, help='Expected peak RPS baseline.')
        parser.add_argument('--multiplier', type=float, default=2.0, help='Load multiplier (default: 2.0).')
        parser.add_argument('--duration-seconds', type=int, default=20, help='Run duration in seconds.')
        parser.add_argument('--workers', type=int, default=4, help='Concurrent worker count.')
        parser.add_argument('--username', type=str, default='perf-probe-user', help='Login username.')
        parser.add_argument('--password', type=str, default='perf-probe-pass-123', help='Login password.')
        parser.add_argument('--output', type=str, default='', help='Optional JSON output path.')

    def _ensure_probe_context(self, username, password):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': f'{username}@example.com'},
        )
        if created or not user.check_password(password):
            user.set_password(password)
            user.save(update_fields=['password'])

        org, _ = Organization.objects.get_or_create(
            slug='perf-probe-org',
            defaults={'name': 'Performance Probe Org'},
        )
        OrganizationMembership.objects.get_or_create(
            organization=org,
            user=user,
            defaults={'role': OrganizationMembership.Role.OWNER, 'is_active': True},
        )

        probe_client, _ = Client.objects.get_or_create(
            organization=org,
            name='Performance Probe Client',
            defaults={
                'client_type': Client.ClientType.CORPORATION,
                'status': Client.Status.ACTIVE,
                'created_by': user,
            },
        )
        if not Contract.objects.filter(organization=org).exists():
            Contract.objects.create(
                organization=org,
                client=probe_client,
                title='Performance Probe Contract',
                content='Synthetic contract for load tests.',
                status=Contract.Status.ACTIVE,
                created_by=user,
            )
        return user

    def handle(self, *args, **options):
        from django.test import Client as HttpClient

        peak_rps = max(1, int(options['peak_rps']))
        multiplier = max(1.0, float(options['multiplier']))
        duration_seconds = max(1, int(options['duration_seconds']))
        workers = max(1, int(options['workers']))
        username = options['username'].strip()
        password = options['password'].strip()
        output = (options.get('output') or '').strip()

        total_requests = int(peak_rps * multiplier * duration_seconds)
        requests_per_worker = max(1, total_requests // workers)

        user = self._ensure_probe_context(username, password)

        routes = [
            '/dashboard/',
            '/contracts/',
            '/contracts/api/contracts/',
        ]

        lock = threading.Lock()
        latencies = []
        statuses = []

        def worker_fn(worker_idx):
            client = HttpClient()
            if not client.login(username=user.username, password=password):
                raise CommandError(f'Worker {worker_idx} failed login.')

            for req_idx in range(requests_per_worker):
                route = routes[(worker_idx + req_idx) % len(routes)]
                started = perf_counter()
                response = client.get(route)
                elapsed_ms = (perf_counter() - started) * 1000
                with lock:
                    latencies.append(elapsed_ms)
                    statuses.append(response.status_code)

        started_total = perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for i in range(workers):
                executor.submit(worker_fn, i)
        total_elapsed = perf_counter() - started_total

        if not latencies:
            raise CommandError('No requests executed during load test.')

        ordered = sorted(latencies)
        p50 = ordered[len(ordered) // 2]
        p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
        achieved_rps = len(ordered) / total_elapsed if total_elapsed > 0 else 0

        report = {
            'target': {
                'peak_rps': peak_rps,
                'multiplier': multiplier,
                'duration_seconds': duration_seconds,
                'target_rps': peak_rps * multiplier,
                'target_total_requests': total_requests,
            },
            'execution': {
                'workers': workers,
                'executed_requests': len(ordered),
                'wall_time_seconds': round(total_elapsed, 3),
                'achieved_rps': round(achieved_rps, 3),
            },
            'latency_ms': {
                'p50': round(p50, 2),
                'p95': round(p95, 2),
                'max': round(max(ordered), 2),
                'mean': round(sum(ordered) / len(ordered), 2),
                'median': round(median(ordered), 2),
            },
            'status_codes': sorted(set(statuses)),
            'success_rate': round(sum(1 for s in statuses if s < 500) / len(statuses), 3),
        }

        rendered = json.dumps(report, indent=2)
        self.stdout.write(rendered)
        if output:
            with open(output, 'w', encoding='utf-8') as fh:
                fh.write(rendered)
            self.stdout.write(self.style.SUCCESS(f'Wrote report to {output}'))
