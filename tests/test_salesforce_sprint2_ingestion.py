import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from contracts.models import Contract, Organization, OrganizationMembership, SalesforceOrganizationConnection
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
