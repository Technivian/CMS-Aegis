import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from contracts.models import AuditLog, Contract, Organization, RetentionPolicy


class RetentionJobsCommandTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Retention Org', slug='retention-org')
        self.policy = RetentionPolicy.objects.create(
            organization=self.organization,
            title='Contract Retention',
            category=RetentionPolicy.Category.CONTRACTS,
            retention_period_days=30,
            is_active=True,
        )

    def test_run_retention_jobs_archives_eligible_contracts_and_writes_audit(self):
        old_date = timezone.now().date() - timedelta(days=120)
        contract = Contract.objects.create(
            organization=self.organization,
            title='Old Contract',
            end_date=old_date,
            lifecycle_stage='EXECUTED',
        )
        out = StringIO()
        call_command('run_retention_jobs', organization_slug=self.organization.slug, stdout=out)
        payload = json.loads(out.getvalue())

        contract.refresh_from_db()
        self.assertEqual(contract.lifecycle_stage, 'ARCHIVED')
        self.assertEqual(payload['contracts_archived'], 1)
        self.assertEqual(
            AuditLog.objects.filter(model_name='RetentionExecution', object_id=contract.id).count(),
            1,
        )

    def test_run_retention_jobs_dry_run_does_not_mutate_contracts(self):
        old_date = timezone.now().date() - timedelta(days=120)
        contract = Contract.objects.create(
            organization=self.organization,
            title='Dry Run Contract',
            end_date=old_date,
            lifecycle_stage='EXECUTED',
        )
        out = StringIO()
        call_command('run_retention_jobs', organization_slug=self.organization.slug, dry_run=True, stdout=out)
        payload = json.loads(out.getvalue())

        contract.refresh_from_db()
        self.assertEqual(contract.lifecycle_stage, 'EXECUTED')
        self.assertEqual(payload['contracts_archived'], 0)
        self.assertEqual(
            AuditLog.objects.filter(model_name='RetentionExecution', object_id=contract.id).count(),
            0,
        )

    def test_export_retention_audit_actions_includes_trace_ids(self):
        old_date = timezone.now().date() - timedelta(days=120)
        Contract.objects.create(
            organization=self.organization,
            title='Audit Export Contract',
            end_date=old_date,
            lifecycle_stage='EXECUTED',
        )
        call_command('run_retention_jobs', organization_slug=self.organization.slug)

        out = StringIO()
        call_command('export_retention_audit_actions', organization_slug=self.organization.slug, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload['count'], 1)
        self.assertTrue(payload['actions'][0]['trace_id'])
        self.assertEqual(payload['actions'][0]['organization_id'], self.organization.id)

    def test_export_retention_audit_actions_writes_output_file(self):
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / 'retention-audit.json'
            call_command('export_retention_audit_actions', f'--output={output_path}')
            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertIn('actions', payload)
