import json
import shutil
import subprocess
import sys
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from contracts.models import SalesforceSyncRun, WebhookDelivery


class Command(BaseCommand):
    help = 'Generate a release gate status report for Sprint 3 RC execution.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default='',
            help='Optional file path to write the JSON report.',
        )
        parser.add_argument(
            '--fail-on-no-go',
            action='store_true',
            help='Exit with non-zero status when go_no_go is NO-GO.',
        )

    def _run_command(self, args):
        try:
            completed = subprocess.run(args, capture_output=True, text=True, timeout=180)
            return {
                'command': ' '.join(args),
                'exit_code': completed.returncode,
                'stdout': completed.stdout[-4000:],
                'stderr': completed.stderr[-4000:],
                'status': 'pass' if completed.returncode == 0 else 'fail',
            }
        except Exception as exc:
            return {
                'command': ' '.join(args),
                'exit_code': None,
                'stdout': '',
                'stderr': str(exc),
                'status': 'error',
            }

    def _missing_tool_result(self, tool_name, command):
        return {
            'command': command,
            'exit_code': None,
            'stdout': '',
            'stderr': f'{tool_name} not installed',
            'status': 'fail',
        }

    def handle(self, *args, **options):
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        unapplied = executor.migration_plan(targets)

        try:
            table_names = set(connection.introspection.table_names())
        except Exception:
            table_names = set()

        latest_successful_sync = None
        dead_letter_count = 0
        integrations_status = 'warn'
        integrations_reason = None
        if {'contracts_salesforcesyncrun', 'contracts_webhookdelivery'}.issubset(table_names):
            try:
                latest_successful_sync = (
                    SalesforceSyncRun.objects.filter(
                        status=SalesforceSyncRun.Status.SUCCESS,
                        completed_at__gte=seven_days_ago,
                    )
                    .order_by('-completed_at')
                    .first()
                )
                dead_letter_count = WebhookDelivery.objects.filter(status=WebhookDelivery.Status.DEAD_LETTER).count()
                integrations_status = 'pass' if latest_successful_sync is not None and dead_letter_count == 0 else 'warn'
            except (OperationalError, ProgrammingError) as exc:
                integrations_reason = f'integrations tables unavailable: {exc.__class__.__name__}'
        else:
            integrations_reason = 'integrations tables unavailable: run migrations'

        pip_audit_result = self._missing_tool_result(
            'pip-audit',
            f'{sys.executable} -m pip_audit --disable-pip --no-deps -r requirements/runtime.txt',
        )
        if shutil.which('pip-audit'):
            pip_audit_result = self._run_command(['pip-audit', '--disable-pip', '--no-deps', '-r', 'requirements/runtime.txt'])
        else:
            pip_audit_result = self._run_command(
                [sys.executable, '-m', 'pip_audit', '--disable-pip', '--no-deps', '-r', 'requirements/runtime.txt']
            )
            if pip_audit_result.get('status') == 'error':
                pip_audit_result = self._missing_tool_result(
                    'pip-audit',
                    f'{sys.executable} -m pip_audit --disable-pip --no-deps -r requirements/runtime.txt',
                )

        client_npm_result = self._missing_tool_result('npm', 'npm --prefix client audit --audit-level=high')
        theme_npm_result = self._missing_tool_result('npm', 'npm --prefix theme/static_src audit --audit-level=high')
        if shutil.which('npm'):
            client_npm_result = self._run_command(['npm', '--prefix', 'client', 'audit', '--audit-level=high'])
            theme_npm_result = self._run_command(['npm', '--prefix', 'theme/static_src', 'audit', '--audit-level=high'])

        report = {
            'captured_at': now.isoformat(),
            'sprint_stage': 'SPR3-001',
            'gates': {
                'database': {
                    'unapplied_migrations': len(unapplied),
                    'status': 'pass' if len(unapplied) == 0 else 'fail',
                },
                'security': {
                    'pip_audit': pip_audit_result,
                    'npm_client_audit': client_npm_result,
                    'npm_theme_audit': theme_npm_result,
                },
                'integrations': {
                    'latest_successful_salesforce_sync_at': (
                        latest_successful_sync.completed_at.isoformat()
                        if latest_successful_sync and latest_successful_sync.completed_at
                        else None
                    ),
                    'webhook_dead_letter_count': dead_letter_count,
                    'status': integrations_status,
                    'reason': integrations_reason,
                },
            },
        }

        security_statuses = [
            report['gates']['security']['pip_audit'].get('status'),
            report['gates']['security']['npm_client_audit'].get('status'),
            report['gates']['security']['npm_theme_audit'].get('status'),
        ]
        security_ok = all(status == 'pass' for status in security_statuses)
        database_ok = report['gates']['database']['status'] == 'pass'
        integration_ok = report['gates']['integrations']['status'] == 'pass'
        report['go_no_go'] = 'GO' if database_ok and security_ok and integration_ok else 'NO-GO'

        output_json = json.dumps(report, indent=2, sort_keys=True)
        output_path = options.get('output') or ''
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as handle:
                handle.write(output_json)
                handle.write('\n')

        self.stdout.write(output_json)

        if options.get('fail_on_no_go') and report['go_no_go'] != 'GO':
            raise CommandError('Release gate report produced NO-GO.')
