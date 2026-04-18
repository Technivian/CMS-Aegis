import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contracts.models import (
    BackgroundJob,
    Contract,
    Organization,
    OrganizationMembership,
    SalesforceOrganizationConnection,
    SalesforceSyncRun,
    WebhookDelivery,
    WebhookEndpoint,
)
from contracts.services.background_jobs import process_background_job
from contracts.services.salesforce import TOKEN_CIPHER_PREFIX, SalesforceTokenPayload, decrypt_salesforce_token


User = get_user_model()


@override_settings(
    SALESFORCE_CLIENT_ID='sf-client-id',
    SALESFORCE_CLIENT_SECRET='sf-client-secret',
    SALESFORCE_AUTHORIZATION_URL='https://login.salesforce.com/services/oauth2/authorize',
    SALESFORCE_TOKEN_URL='https://login.salesforce.com/services/oauth2/token',
    SALESFORCE_REDIRECT_URI='http://testserver/contracts/api/integrations/salesforce/oauth/callback/',
    SALESFORCE_SCOPES='api refresh_token offline_access',
    SALESFORCE_TOKEN_ENCRYPTION_SALT='tests-v1',
    NETSUITE_CLIENT_ID='ns-client-id',
    NETSUITE_CLIENT_SECRET='ns-client-secret',
    NETSUITE_TOKEN_URL='https://sandbox.netsuite.com/oauth2/v1/token',
    NETSUITE_API_URL='https://sandbox.netsuite.com/app/site/hosting/restlet.nl',
)
class SalesforceSprintTwoIngestionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username='owner2', password='pass12345', email='owner2@example.com')
        self.organization = Organization.objects.create(name='SF Org 2', slug='sf-org-2')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client.login(username='owner2', password='pass12345')

    @patch('contracts.api.views.exchange_salesforce_code_for_tokens')
    def test_oauth_callback_encrypts_stored_tokens(self, mock_exchange):
        mock_exchange.return_value = SalesforceTokenPayload(
            access_token='plain-access-token',
            refresh_token='plain-refresh-token',
            instance_url='https://example.my.salesforce.com',
            external_org_id='https://login.salesforce.com/id/00D/777',
            scope='api refresh_token',
            token_expires_at=None,
        )
        start_response = self.client.post(reverse('contracts:salesforce_oauth_start_api'))
        state = start_response.json()['state']
        callback_response = self.client.get(
            reverse('contracts:salesforce_oauth_callback_api'),
            {'state': state, 'code': 'auth-code-456'},
        )
        self.assertEqual(callback_response.status_code, 200)
        connection = SalesforceOrganizationConnection.objects.get(organization=self.organization)
        self.assertTrue(connection.access_token.startswith(TOKEN_CIPHER_PREFIX))
        self.assertTrue(connection.refresh_token.startswith(TOKEN_CIPHER_PREFIX))
        self.assertEqual(decrypt_salesforce_token(connection.access_token), 'plain-access-token')
        self.assertEqual(decrypt_salesforce_token(connection.refresh_token), 'plain-refresh-token')

    def test_ingest_preview_dry_run_returns_reconciliation_summary(self):
        Contract.objects.create(
            organization=self.organization,
            title='Existing contract',
            source_system='salesforce',
            source_system_id='006AAA',
        )
        records = [
            {'Id': '006AAA', 'Name': 'Existing contract'},
            {'Id': '006BBB', 'Name': 'New contract'},
            {'Id': '', 'Name': 'Bad record'},
        ]
        response = self.client.post(
            reverse('contracts:salesforce_ingest_preview_api'),
            data=json.dumps({'records': records, 'dry_run': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()['summary']
        self.assertEqual(payload['updated'], 1)
        self.assertEqual(payload['created'], 1)
        self.assertEqual(payload['skipped'], 1)

    @patch('contracts.api.views.sync_salesforce_connection')
    def test_sync_api_returns_summary(self, mock_sync):
        SalesforceOrganizationConnection.objects.create(
            organization=self.organization,
            connected_by=self.owner,
            access_token='plain-access',
            refresh_token='plain-refresh',
            instance_url='https://example.my.salesforce.com',
            is_active=True,
        )
        mock_sync.return_value = {'created': 1, 'updated': 0, 'skipped': 0, 'errors': []}
        response = self.client.post(
            reverse('contracts:salesforce_sync_api'),
            data=json.dumps({'dry_run': True, 'limit': 50}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['dry_run'])
        self.assertEqual(payload['summary']['created'], 1)
        run = SalesforceSyncRun.objects.get(organization=self.organization)
        self.assertEqual(run.status, SalesforceSyncRun.Status.SUCCESS)
        self.assertEqual(run.trigger_source, SalesforceSyncRun.TriggerSource.API)
        self.assertEqual(run.created_count, 1)

    def test_sync_api_blocks_when_run_is_already_running(self):
        connection = SalesforceOrganizationConnection.objects.create(
            organization=self.organization,
            connected_by=self.owner,
            access_token='plain-access',
            refresh_token='plain-refresh',
            instance_url='https://example.my.salesforce.com',
            is_active=True,
        )
        SalesforceSyncRun.objects.create(
            organization=self.organization,
            connection=connection,
            trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
            status=SalesforceSyncRun.Status.RUNNING,
        )
        response = self.client.post(
            reverse('contracts:salesforce_sync_api'),
            data=json.dumps({'dry_run': False, 'limit': 20}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn('already running', response.json().get('error', '').lower())

    def test_sync_runs_api_returns_recent_runs(self):
        SalesforceSyncRun.objects.create(
            organization=self.organization,
            trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
            status=SalesforceSyncRun.Status.SUCCESS,
            dry_run=False,
            fetched_records=3,
            created_count=2,
            updated_count=1,
            skipped_count=0,
            error_count=0,
        )
        response = self.client.get(reverse('contracts:salesforce_sync_runs_api'), {'limit': 10})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['runs']), 1)
        self.assertEqual(payload['runs'][0]['fetched_records'], 3)

    def test_ingest_salesforce_records_command_upserts_contracts(self):
        records = [
            {
                'Id': '006XYZ',
                'Name': 'Vendor MSA',
                'Type': 'MSA',
                'Amount': '125000.50',
                'CurrencyIsoCode': 'USD',
                'Status__c': 'ACTIVE',
                'Risk_Level__c': 'HIGH',
                'CreatedDate': '2026-04-15T08:00:00Z',
                'LastModifiedDate': '2026-04-17T12:30:00Z',
            }
        ]
        with TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / 'salesforce_records.json'
            payload_path.write_text(json.dumps(records), encoding='utf-8')
            call_command(
                'ingest_salesforce_records',
                organization_slug='sf-org-2',
                path=str(payload_path),
            )

        contract = Contract.objects.get(organization=self.organization, source_system='salesforce', source_system_id='006XYZ')
        self.assertEqual(contract.title, 'Vendor MSA')
        self.assertEqual(contract.contract_type, Contract.ContractType.MSA)
        self.assertEqual(contract.status, Contract.Status.ACTIVE)
        self.assertEqual(contract.risk_level, Contract.RiskLevel.HIGH)
        self.assertEqual(contract.value, Decimal('125000.50'))

    @patch('contracts.services.salesforce.fetch_salesforce_records')
    def test_sync_salesforce_contracts_command_fetches_and_upserts(self, mock_fetch):
        SalesforceOrganizationConnection.objects.create(
            organization=self.organization,
            connected_by=self.owner,
            access_token='plain-access',
            refresh_token='plain-refresh',
            instance_url='https://example.my.salesforce.com',
            is_active=True,
        )
        mock_fetch.return_value = [
            {'Id': '006LIVE', 'Name': 'Live Synced Contract', 'Type': 'NDA', 'Amount': '7000', 'CurrencyIsoCode': 'USD'}
        ]
        call_command('sync_salesforce_contracts', organization_slug='sf-org-2', limit=25)
        contract = Contract.objects.get(
            organization=self.organization,
            source_system='salesforce',
            source_system_id='006LIVE',
        )
        self.assertEqual(contract.title, 'Live Synced Contract')
        self.assertEqual(contract.contract_type, Contract.ContractType.NDA)
        run = SalesforceSyncRun.objects.get(organization=self.organization, trigger_source=SalesforceSyncRun.TriggerSource.COMMAND)
        self.assertEqual(run.status, SalesforceSyncRun.Status.SUCCESS)
        self.assertEqual(run.fetched_records, 1)

    def test_process_background_sync_job_retries_then_dead_letters(self):
        job = BackgroundJob.objects.create(
            organization=self.organization,
            job_type='sync_salesforce_contracts',
            payload={'limit': 50},
            max_attempts=2,
            scheduled_at=timezone.now(),
        )
        with patch('contracts.services.background_jobs.call_command', side_effect=RuntimeError('sync boom')):
            with self.assertRaises(RuntimeError):
                process_background_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.PENDING)
        self.assertEqual(job.attempt_count, 1)
        self.assertIsNone(job.dead_lettered_at)

        with patch('contracts.services.background_jobs.call_command', side_effect=RuntimeError('sync boom')):
            with self.assertRaises(RuntimeError):
                process_background_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(job.attempt_count, 2)
        self.assertIsNotNone(job.dead_lettered_at)

    def test_queue_background_jobs_queues_salesforce_sync_for_active_connection(self):
        SalesforceOrganizationConnection.objects.create(
            organization=self.organization,
            connected_by=self.owner,
            access_token='plain-access',
            refresh_token='plain-refresh',
            instance_url='https://example.my.salesforce.com',
            is_active=True,
        )
        call_command('queue_background_jobs')
        self.assertTrue(
            BackgroundJob.objects.filter(
                organization=self.organization,
                job_type='sync_salesforce_contracts',
                status=BackgroundJob.Status.PENDING,
            ).exists()
        )

    @patch('contracts.services.webhooks.urlopen')
    def test_dispatch_webhook_deliveries_retries_to_dead_letter(self, mock_urlopen):
        endpoint = WebhookEndpoint.objects.create(
            organization=self.organization,
            name='ERP Webhook',
            url='https://example.invalid/webhook',
            secret='top-secret',
            event_types=['salesforce.sync.completed'],
            max_attempts=2,
        )
        delivery = WebhookDelivery.objects.create(
            organization=self.organization,
            endpoint=endpoint,
            event_type='salesforce.sync.completed',
            payload={'ok': True},
            max_attempts=2,
            next_attempt_at=timezone.now(),
        )
        mock_urlopen.side_effect = RuntimeError('network down')
        call_command('dispatch_webhook_deliveries', limit=10)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.FAILED)
        self.assertEqual(delivery.attempt_count, 1)
        self.assertIsNotNone(delivery.next_attempt_at)
        delivery.next_attempt_at = timezone.now()
        delivery.save(update_fields=['next_attempt_at'])

        call_command('dispatch_webhook_deliveries', limit=10)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.DEAD_LETTER)
        self.assertEqual(delivery.attempt_count, 2)
        self.assertIsNotNone(delivery.dead_lettered_at)

    def test_netsuite_ingest_command_creates_contract(self):
        records = [
            {
                'id': 'NS-100',
                'title': 'NetSuite Vendor Agreement',
                'vendor_name': 'NetSuite Vendor',
                'contract_type': 'VENDOR',
                'status': 'ACTIVE',
                'value': '3210.55',
                'currency': 'USD',
                'effective_date': '2026-04-01',
                'end_date': '2027-03-31',
            }
        ]
        with TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / 'netsuite_records.json'
            payload_path.write_text(json.dumps(records), encoding='utf-8')
            call_command(
                'ingest_netsuite_records',
                organization_slug='sf-org-2',
                path=str(payload_path),
            )
        contract = Contract.objects.get(organization=self.organization, source_system='netsuite', source_system_id='NS-100')
        self.assertEqual(contract.title, 'NetSuite Vendor Agreement')
        self.assertEqual(contract.status, Contract.Status.ACTIVE)

    @patch('contracts.management.commands.sync_netsuite_contracts.fetch_netsuite_records')
    def test_sync_netsuite_contracts_command_fetches_and_upserts(self, mock_fetch):
        mock_fetch.return_value = [
            {
                'id': 'NS-200',
                'title': 'NetSuite API Synced Contract',
                'vendor_name': 'Acme Vendor',
                'contract_type': 'MSA',
                'status': 'ACTIVE',
                'value': '9000.00',
                'currency': 'USD',
            }
        ]
        call_command('sync_netsuite_contracts', organization_slug='sf-org-2', limit=25)
        contract = Contract.objects.get(
            organization=self.organization,
            source_system='netsuite',
            source_system_id='NS-200',
        )
        self.assertEqual(contract.title, 'NetSuite API Synced Contract')
        self.assertEqual(contract.contract_type, Contract.ContractType.MSA)

    @patch('contracts.management.commands.sync_netsuite_contracts.fetch_netsuite_records')
    def test_sync_netsuite_contracts_command_supports_dry_run(self, mock_fetch):
        Contract.objects.create(
            organization=self.organization,
            title='Existing NS Contract',
            source_system='netsuite',
            source_system_id='NS-201',
        )
        mock_fetch.return_value = [
            {'id': 'NS-201', 'title': 'Existing NS Contract'},
            {'id': 'NS-202', 'title': 'New NS Contract'},
            {'id': '', 'title': 'Missing ID'},
        ]
        call_command('sync_netsuite_contracts', organization_slug='sf-org-2', limit=25, dry_run=True)
        self.assertFalse(
            Contract.objects.filter(
                organization=self.organization,
                source_system='netsuite',
                source_system_id='NS-202',
            ).exists()
        )

    @patch('contracts.api.views.fetch_netsuite_records')
    def test_netsuite_sync_api_returns_summary(self, mock_fetch):
        mock_fetch.return_value = [
            {'id': 'NS-301', 'title': 'API NetSuite Contract', 'contract_type': 'NDA', 'status': 'ACTIVE'}
        ]
        response = self.client.post(
            reverse('contracts:netsuite_sync_api'),
            data=json.dumps({'dry_run': False, 'limit': 25}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['dry_run'])
        self.assertEqual(payload['summary']['created'], 1)
        self.assertTrue(
            Contract.objects.filter(
                organization=self.organization,
                source_system='netsuite',
                source_system_id='NS-301',
            ).exists()
        )

    @patch('contracts.api.views.fetch_netsuite_records')
    def test_netsuite_sync_api_dry_run_does_not_persist(self, mock_fetch):
        mock_fetch.return_value = [
            {'id': 'NS-302', 'title': 'Dry Run NetSuite Contract', 'contract_type': 'MSA', 'status': 'ACTIVE'}
        ]
        response = self.client.post(
            reverse('contracts:netsuite_sync_api'),
            data=json.dumps({'dry_run': True, 'limit': 25}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['dry_run'])
        self.assertEqual(payload['summary']['created'], 1)
        self.assertFalse(
            Contract.objects.filter(
                organization=self.organization,
                source_system='netsuite',
                source_system_id='NS-302',
            ).exists()
        )

    def test_verify_postgres_cutover_command_outputs_json(self):
        with patch('contracts.management.commands.verify_postgres_cutover.connection') as mock_connection, patch(
            'contracts.management.commands.verify_postgres_cutover.MigrationExecutor'
        ) as mock_executor:
            mock_connection.settings_dict = {'ENGINE': 'django.db.backends.postgresql'}
            mock_connection.vendor = 'postgresql'
            cursor_context = mock_connection.cursor.return_value.__enter__.return_value
            cursor_context.fetchone.side_effect = [
                [1],
                ['PostgreSQL 16.4'],
                ['cms_aegis'],
                ['postgres'],
            ]
            instance = mock_executor.return_value
            instance.loader.graph.leaf_nodes.return_value = []
            instance.migration_plan.return_value = []
            call_command('verify_postgres_cutover')

    def test_verify_postgres_cutover_command_handles_sqlite_non_production(self):
        with patch('contracts.management.commands.verify_postgres_cutover.connection') as mock_connection, patch(
            'contracts.management.commands.verify_postgres_cutover.MigrationExecutor'
        ) as mock_executor:
            mock_connection.settings_dict = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'db.sqlite3'}
            mock_connection.vendor = 'sqlite'
            cursor_context = mock_connection.cursor.return_value.__enter__.return_value
            cursor_context.fetchone.return_value = [1]
            instance = mock_executor.return_value
            instance.loader.graph.leaf_nodes.return_value = []
            instance.migration_plan.return_value = []
            with self.assertRaises(CommandError):
                call_command('verify_postgres_cutover')

    def test_encrypt_salesforce_tokens_command_backfills_plaintext_tokens(self):
        connection = SalesforceOrganizationConnection.objects.create(
            organization=self.organization,
            connected_by=self.owner,
            access_token='plain-access',
            refresh_token='plain-refresh',
            is_active=True,
        )
        call_command('encrypt_salesforce_tokens')
        connection.refresh_from_db()
        self.assertTrue(connection.access_token.startswith(TOKEN_CIPHER_PREFIX))
        self.assertTrue(connection.refresh_token.startswith(TOKEN_CIPHER_PREFIX))
        self.assertEqual(decrypt_salesforce_token(connection.access_token), 'plain-access')
        self.assertEqual(decrypt_salesforce_token(connection.refresh_token), 'plain-refresh')
