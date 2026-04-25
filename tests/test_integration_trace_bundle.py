import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase


class IntegrationTraceBundleTests(TestCase):
    def test_generate_integration_trace_bundle_creates_salesforce_and_webhook_evidence(self):
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            out = StringIO()

            call_command(
                'generate_integration_trace_bundle',
                f'--output-dir={output_dir}',
                stdout=out,
            )

            payload = json.loads(out.getvalue())
            self.assertEqual(payload['status'], 'GO')
            self.assertTrue(payload['criteria']['salesforce_sync_request_captured'])
            self.assertTrue(payload['criteria']['salesforce_sync_stored'])
            self.assertTrue(payload['criteria']['webhook_request_captured'])
            self.assertTrue(payload['criteria']['webhook_stored'])

            for filename in [
                'salesforce-trace-request.json',
                'salesforce-trace-response.json',
                'salesforce-trace-stored.json',
                'webhook-trace-request.json',
                'webhook-trace-response.json',
                'webhook-trace-stored.json',
                'integration-trace-bundle.json',
            ]:
                self.assertTrue((output_dir / filename).exists(), filename)
