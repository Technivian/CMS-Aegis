import csv
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import BackgroundJob, Contract, Organization, OrganizationMembership, UserProfile


User = get_user_model()


class IdentityTelemetryAndExportsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner', email='owner@example.com', password='testpass123')
        self.organization = Organization.objects.create(name='Identity Org', slug='identity-org', require_mfa=True)
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.client.login(username='owner', password='testpass123')

    def test_identity_telemetry_dashboard_surfaces_event_counts(self):
        self.profile.mfa_enabled = True
        self.profile.mfa_verified_at = self.profile.mfa_verified_at or timezone.now()
        self.profile.save(update_fields=['mfa_enabled', 'mfa_verified_at', 'updated_at'])
        self.client.post(reverse('profile'), data={'action': 'generate_mfa_recovery_codes'}, follow=True)

        response = self.client.get(reverse('contracts:identity_telemetry_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Identity Telemetry')
        self.assertContains(response, 'mfa_recovery_codes_generated')

    def test_privacy_evidence_export_returns_csv(self):
        self.profile.mfa_enabled = True
        self.profile.mfa_verified_at = self.profile.mfa_verified_at or timezone.now()
        self.profile.save(update_fields=['mfa_enabled', 'mfa_verified_at', 'updated_at'])
        response = self.client.get(reverse('contracts:privacy_evidence_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertContains(response, 'category,metric,value', html=False)

    def test_background_job_processor_completes_pending_jobs(self):
        job = BackgroundJob.objects.create(
            organization=self.organization,
            job_type='send_contract_reminders',
            payload={},
        )
        call_command('process_background_jobs', limit=5)
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.COMPLETED)

    def test_contract_import_command_creates_or_updates_by_title_and_counterparty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / 'contracts.csv'
            with csv_path.open('w', newline='', encoding='utf-8') as handle:
                writer = csv.writer(handle)
                writer.writerow(['title', 'counterparty', 'contract_type', 'status', 'value', 'currency', 'governing_law', 'jurisdiction'])
                writer.writerow(['Imported MSA', 'Acme Corp', 'MSA', 'ACTIVE', '250000', 'USD', 'Delaware', 'New York'])

            call_command(
                'import_contracts_csv',
                organization_slug=self.organization.slug,
                path=str(csv_path),
            )

        contract = Contract.objects.get(organization=self.organization, title='Imported MSA')
        self.assertEqual(contract.counterparty, 'Acme Corp')
        self.assertEqual(str(contract.value), '250000.00')
