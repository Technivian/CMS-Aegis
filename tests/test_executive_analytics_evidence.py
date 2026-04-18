import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from contracts.models import Contract, Organization, OrganizationMembership


User = get_user_model()


class ExecutiveAnalyticsEvidenceCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='evidence-owner', password='pass12345')
        self.org_a = Organization.objects.create(name='Evidence Org A', slug='evidence-org-a')
        self.org_b = Organization.objects.create(name='Evidence Org B', slug='evidence-org-b')
        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        Contract.objects.create(organization=self.org_a, title='Org A Contract', created_by=self.user)

    def test_generate_executive_analytics_evidence_outputs_snapshots(self):
        out = StringIO()
        call_command(
            'generate_executive_analytics_evidence',
            '--organization-slug=evidence-org-a',
            '--organization-slug=evidence-org-b',
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertEqual(payload['organization_count'], 2)
        slugs = [item['organization']['slug'] for item in payload['snapshots']]
        self.assertEqual(slugs, ['evidence-org-a', 'evidence-org-b'])

    def test_generate_executive_analytics_evidence_writes_output_file(self):
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / 'exec-evidence.json'
            call_command('generate_executive_analytics_evidence', f'--output={output}')
            self.assertTrue(output.exists())
            payload = json.loads(output.read_text(encoding='utf-8'))
            self.assertGreaterEqual(payload['organization_count'], 2)

    def test_generate_executive_analytics_evidence_rejects_unknown_org_slug(self):
        with self.assertRaises(CommandError):
            call_command('generate_executive_analytics_evidence', '--organization-slug=missing-org')
