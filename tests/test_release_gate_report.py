import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from contracts.models import Organization, SalesforceSyncRun


class ReleaseGateReportTests(TestCase):
    @staticmethod
    def _tool_lookup(tool_name):
        if tool_name == 'npm':
            return '/usr/bin/npm'
        if tool_name == 'pip-audit':
            return '/usr/bin/pip-audit'
        return None

    @staticmethod
    def _passing_command_result(args):
        return {
            'command': ' '.join(args),
            'exit_code': 0,
            'stdout': '',
            'stderr': '',
            'status': 'pass',
        }

    def test_generate_release_gate_report_outputs_go_with_clean_state(self):
        organization = Organization.objects.create(name='Gate Org', slug='gate-org')
        SalesforceSyncRun.objects.create(
            organization=organization,
            trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
            status=SalesforceSyncRun.Status.SUCCESS,
            completed_at=timezone.now(),
        )

        with patch(
            'contracts.management.commands.generate_release_gate_report.shutil.which',
            side_effect=self._tool_lookup,
        ), patch(
            'contracts.management.commands.generate_release_gate_report.Command._run_command',
            side_effect=self._passing_command_result,
        ):
            out = StringIO()
            call_command('generate_release_gate_report', stdout=out)
            output = out.getvalue()

        payload = json.loads(output)
        self.assertEqual(payload['go_no_go'], 'GO')
        self.assertEqual(payload['gates']['database']['status'], 'pass')

    def test_generate_release_gate_report_outputs_no_go_when_no_sync(self):
        with patch(
            'contracts.management.commands.generate_release_gate_report.shutil.which',
            side_effect=self._tool_lookup,
        ), patch(
            'contracts.management.commands.generate_release_gate_report.Command._run_command',
            side_effect=self._passing_command_result,
        ):
            out = StringIO()
            call_command('generate_release_gate_report', stdout=out)
            output = out.getvalue()

        payload = json.loads(output)
        self.assertEqual(payload['go_no_go'], 'NO-GO')
        self.assertEqual(payload['gates']['integrations']['status'], 'warn')

    def test_generate_release_gate_report_fails_when_requested_and_no_go(self):
        with patch(
            'contracts.management.commands.generate_release_gate_report.shutil.which',
            side_effect=self._tool_lookup,
        ), patch(
            'contracts.management.commands.generate_release_gate_report.Command._run_command',
            side_effect=self._passing_command_result,
        ):
            with self.assertRaises(CommandError):
                call_command('generate_release_gate_report', '--fail-on-no-go')

    def test_generate_release_gate_report_writes_output_file(self):
        organization = Organization.objects.create(name='Gate Org', slug='gate-org')
        SalesforceSyncRun.objects.create(
            organization=organization,
            trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
            status=SalesforceSyncRun.Status.SUCCESS,
            completed_at=timezone.now(),
        )
        output_path = Path('/tmp/release-gate-report-test.json')
        if output_path.exists():
            output_path.unlink()

        with patch(
            'contracts.management.commands.generate_release_gate_report.shutil.which',
            side_effect=self._tool_lookup,
        ), patch(
            'contracts.management.commands.generate_release_gate_report.Command._run_command',
            side_effect=self._passing_command_result,
        ):
            call_command('generate_release_gate_report', f'--output={output_path}')

        self.assertTrue(output_path.exists())
        payload = json.loads(output_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['go_no_go'], 'GO')
        output_path.unlink(missing_ok=True)

    def test_generate_release_gate_report_handles_unmigrated_integration_tables(self):
        with patch(
            'contracts.management.commands.generate_release_gate_report.shutil.which',
            side_effect=self._tool_lookup,
        ), patch(
            'contracts.management.commands.generate_release_gate_report.Command._run_command',
            side_effect=self._passing_command_result,
        ), patch(
            'contracts.management.commands.generate_release_gate_report.connection.introspection.table_names'
        ) as mock_table_names:
            mock_table_names.return_value = []
            out = StringIO()
            call_command('generate_release_gate_report', stdout=out)
            payload = json.loads(out.getvalue())

        self.assertEqual(payload['go_no_go'], 'NO-GO')
        self.assertEqual(payload['gates']['integrations']['status'], 'warn')
        self.assertIn('run migrations', payload['gates']['integrations']['reason'])

    def test_generate_release_gate_report_fails_security_when_pip_audit_missing(self):
        organization = Organization.objects.create(name='Gate Org', slug='gate-org')
        SalesforceSyncRun.objects.create(
            organization=organization,
            trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
            status=SalesforceSyncRun.Status.SUCCESS,
            completed_at=timezone.now(),
        )

        def _tool_lookup(tool_name):
            if tool_name == 'npm':
                return '/usr/bin/npm'
            return None

        def _command_result(args):
            if len(args) >= 3 and args[1] == '-m' and args[2] == 'pip_audit':
                return {
                    'command': ' '.join(args),
                    'exit_code': 1,
                    'stdout': '',
                    'stderr': 'No module named pip_audit',
                    'status': 'fail',
                }
            return self._passing_command_result(args)

        with patch(
            'contracts.management.commands.generate_release_gate_report.shutil.which',
            side_effect=_tool_lookup,
        ), patch(
            'contracts.management.commands.generate_release_gate_report.Command._run_command',
            side_effect=_command_result,
        ):
            out = StringIO()
            call_command('generate_release_gate_report', stdout=out)
            payload = json.loads(out.getvalue())

        self.assertEqual(payload['go_no_go'], 'NO-GO')
        self.assertEqual(payload['gates']['security']['pip_audit']['status'], 'fail')
