import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase


class ReleaseEvidenceBundleTests(TestCase):
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

    def test_generate_release_evidence_bundle_writes_all_reports_and_goes_green(self):
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            out = StringIO()

            from unittest.mock import patch

            with patch(
                'contracts.management.commands.generate_release_gate_report.shutil.which',
                side_effect=self._tool_lookup,
            ), patch(
                'contracts.management.commands.generate_release_gate_report.Command._run_command',
                side_effect=self._passing_command_result,
            ):
                call_command(
                    'generate_release_evidence_bundle',
                    f'--output-dir={output_dir}',
                    stdout=out,
                )

            payload = json.loads(out.getvalue())
            self.assertEqual(payload['go_no_go'], 'GO')
            self.assertTrue((output_dir / 'release-gate-report.json').exists())
            self.assertTrue((output_dir / 'sprint3-integration-report.json').exists())
            self.assertTrue((output_dir / 'esign-integration-report.json').exists())
            self.assertTrue((output_dir / 'release-evidence-bundle.json').exists())
            self.assertEqual(payload['reports']['release_gate']['go_no_go'], 'GO')
            self.assertEqual(payload['reports']['sprint3_integration']['status'], 'GO')
            self.assertEqual(payload['reports']['esign_integration']['status'], 'GO')
