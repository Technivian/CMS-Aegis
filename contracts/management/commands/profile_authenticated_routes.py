import json
from statistics import median
from time import perf_counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from contracts.models import Client, Contract, Organization, OrganizationMembership


User = get_user_model()


class Command(BaseCommand):
    help = 'Profile top authenticated routes with p50/p95/max latency metrics.'

    def add_arguments(self, parser):
        parser.add_argument('--iterations', type=int, default=20, help='Requests per route (default: 20).')
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
            defaults={
                'role': OrganizationMembership.Role.OWNER,
                'is_active': True,
            },
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
                content='Synthetic contract for route profiling.',
                status=Contract.Status.ACTIVE,
                created_by=user,
            )

        return user

    def handle(self, *args, **options):
        from django.test import Client as HttpClient

        iterations = max(1, int(options['iterations']))
        username = options['username'].strip()
        password = options['password'].strip()
        output = (options.get('output') or '').strip()

        user = self._ensure_probe_context(username, password)
        client = HttpClient()
        if not client.login(username=user.username, password=password):
            raise CommandError('Unable to authenticate for profiling run.')

        routes = [
            '/dashboard/',
            '/contracts/',
            '/contracts/api/contracts/',
            '/contracts/repository/',
            '/contracts/workflows/',
            '/contracts/approvals/',
            '/contracts/signatures/',
            '/contracts/privacy/',
            '/contracts/reports/',
            '/contracts/notifications/',
        ]

        report = {
            'iterations_per_route': iterations,
            'authenticated': True,
            'username': user.username,
            'routes': {},
        }

        for route in routes:
            latencies = []
            statuses = []
            for _ in range(iterations):
                started = perf_counter()
                response = client.get(route)
                latencies.append((perf_counter() - started) * 1000)
                statuses.append(response.status_code)

            ordered = sorted(latencies)
            p50 = ordered[len(ordered) // 2]
            p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
            report['routes'][route] = {
                'count': len(ordered),
                'p50_ms': round(p50, 2),
                'p95_ms': round(p95, 2),
                'max_ms': round(max(ordered), 2),
                'mean_ms': round(sum(ordered) / len(ordered), 2),
                'median_ms': round(median(ordered), 2),
                'status_codes': sorted(set(statuses)),
                'success_rate': round(sum(1 for s in statuses if s < 500) / len(statuses), 3),
            }

        rendered = json.dumps(report, indent=2)
        self.stdout.write(rendered)
        if output:
            with open(output, 'w', encoding='utf-8') as fh:
                fh.write(rendered)
            self.stdout.write(self.style.SUCCESS(f'Wrote report to {output}'))
