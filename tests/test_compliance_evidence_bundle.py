import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class ComplianceEvidenceBundleTests(SimpleTestCase):
    def test_export_and_verify_compliance_evidence_bundle(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            evidence_file = tmp / 'evidence.txt'
            evidence_file.write_text('compliance evidence', encoding='utf-8')

            out = StringIO()
            call_command(
                'export_compliance_evidence_bundle',
                f'--include={evidence_file}',
                f'--output-dir={tmpdir}',
                '--signing-key=test-signing-key',
                stdout=out,
            )
            payload = json.loads(out.getvalue())
            self.assertEqual(payload['status'], 'exported')

            verify_out = StringIO()
            call_command(
                'verify_compliance_evidence_bundle',
                f"--bundle-path={payload['bundle_path']}",
                f"--sha256-path={payload['sha256_path']}",
                f"--signature-path={payload['signature_path']}",
                '--signing-key=test-signing-key',
                stdout=verify_out,
            )
            verify_payload = json.loads(verify_out.getvalue())
            self.assertEqual(verify_payload['status'], 'verified')
            self.assertEqual(verify_payload['files_verified'], 1)

    def test_verify_compliance_evidence_bundle_fails_when_tampered(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            evidence_file = tmp / 'evidence.txt'
            evidence_file.write_text('compliance evidence', encoding='utf-8')

            out = StringIO()
            call_command(
                'export_compliance_evidence_bundle',
                f'--include={evidence_file}',
                f'--output-dir={tmpdir}',
                '--signing-key=test-signing-key',
                stdout=out,
            )
            payload = json.loads(out.getvalue())
            bundle_path = Path(payload['bundle_path'])
            with bundle_path.open('ab') as handle:
                handle.write(b'tampered')

            with self.assertRaises(CommandError):
                call_command(
                    'verify_compliance_evidence_bundle',
                    f"--bundle-path={payload['bundle_path']}",
                    f"--sha256-path={payload['sha256_path']}",
                    f"--signature-path={payload['signature_path']}",
                    '--signing-key=test-signing-key',
                )
