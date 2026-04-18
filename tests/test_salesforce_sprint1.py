import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from contracts.models import Organization, OrganizationContractFieldMap, OrganizationMembership, SalesforceOrganizationConnection
from contracts.services.salesforce import SalesforceTokenPayload, default_field_map_records


User = get_user_model()


@override_settings(
    SALESFORCE_CLIENT_ID='sf-client-id',
    SALESFORCE_CLIENT_SECRET='sf-client-secret',
    SALESFORCE_AUTHORIZATION_URL='https://login.salesforce.com/services/oauth2/authorize',
    SALESFORCE_TOKEN_URL='https://login.salesforce.com/services/oauth2/token',
    SALESFORCE_REDIRECT_URI='http://testserver/contracts/api/integrations/salesforce/oauth/callback/',
    SALESFORCE_SCOPES='api refresh_token offline_access',
)
class SalesforceSprintOneFoundationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username='owner', password='pass12345', email='owner@example.com')
        self.member = User.objects.create_user(username='member', password='pass12345', email='member@example.com')
        self.organization = Organization.objects.create(name='SF Org', slug='sf-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )

    def test_oauth_start_returns_authorize_url_for_org_admin(self):
        self.client.login(username='owner', password='pass12345')
        response = self.client.post(reverse('contracts:salesforce_oauth_start_api'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('authorize_url', payload)
        self.assertIn('state', payload)
        self.assertIn('response_type=code', payload['authorize_url'])
        self.assertIn('client_id=sf-client-id', payload['authorize_url'])

    def test_oauth_start_for_non_admin_is_forbidden(self):
        self.client.login(username='member', password='pass12345')
        response = self.client.post(reverse('contracts:salesforce_oauth_start_api'))
        self.assertEqual(response.status_code, 403)

    @patch('contracts.api.views.exchange_salesforce_code_for_tokens')
    def test_oauth_callback_persists_connection(self, mock_exchange):
        mock_exchange.return_value = SalesforceTokenPayload(
            access_token='access-token',
            refresh_token='refresh-token',
            instance_url='https://example.my.salesforce.com',
            external_org_id='https://login.salesforce.com/id/00D/005',
            scope='api refresh_token',
            token_expires_at=None,
        )
        self.client.login(username='owner', password='pass12345')
        start_response = self.client.post(reverse('contracts:salesforce_oauth_start_api'))
        state = start_response.json()['state']

        callback_response = self.client.get(
            reverse('contracts:salesforce_oauth_callback_api'),
            {'state': state, 'code': 'auth-code-123'},
        )
        self.assertEqual(callback_response.status_code, 200)
        connection = SalesforceOrganizationConnection.objects.get(organization=self.organization)
        self.assertTrue(connection.is_active)
        self.assertEqual(connection.instance_url, 'https://example.my.salesforce.com')
        self.assertEqual(connection.connected_by, self.owner)

    @patch('contracts.api.views.exchange_salesforce_code_for_tokens')
    def test_oauth_callback_masks_upstream_error_details(self, mock_exchange):
        mock_exchange.side_effect = RuntimeError('provider says invalid_grant')
        self.client.login(username='owner', password='pass12345')
        start_response = self.client.post(reverse('contracts:salesforce_oauth_start_api'))
        state = start_response.json()['state']

        callback_response = self.client.get(
            reverse('contracts:salesforce_oauth_callback_api'),
            {'state': state, 'code': 'auth-code-123'},
        )
        self.assertEqual(callback_response.status_code, 502)
        payload = callback_response.json()
        self.assertEqual(payload['error'], 'Salesforce OAuth exchange failed.')
        self.assertNotIn('invalid_grant', payload['error'])

    def test_field_map_get_returns_default_fixture_when_no_org_map(self):
        self.client.login(username='owner', password='pass12345')
        response = self.client.get(reverse('contracts:salesforce_field_map_api'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['source'], 'default')
        self.assertEqual(len(payload['mappings']), 20)

    def test_field_map_put_persists_org_specific_mapping(self):
        self.client.login(username='owner', password='pass12345')
        mappings = [
            {
                'canonical_field': 'contract_title',
                'salesforce_object': 'Contract__c',
                'salesforce_field': 'Name',
                'is_required': True,
                'transform_rule': '',
            },
            {
                'canonical_field': 'contract_value',
                'salesforce_object': 'Contract__c',
                'salesforce_field': 'Total_Value__c',
                'is_required': True,
                'transform_rule': '',
            },
        ]
        put_response = self.client.put(
            reverse('contracts:salesforce_field_map_api'),
            data=json.dumps({'mappings': mappings}),
            content_type='application/json',
        )
        self.assertEqual(put_response.status_code, 200)
        self.assertEqual(OrganizationContractFieldMap.objects.filter(organization=self.organization, is_active=True).count(), 2)

        get_response = self.client.get(reverse('contracts:salesforce_field_map_api'))
        self.assertEqual(get_response.status_code, 200)
        payload = get_response.json()
        self.assertEqual(payload['source'], 'database')
        self.assertEqual(len(payload['mappings']), 2)

    def test_field_map_put_rejects_unknown_canonical_field(self):
        self.client.login(username='owner', password='pass12345')
        mappings = [
            {
                'canonical_field': 'unsupported_field',
                'salesforce_object': 'Contract__c',
                'salesforce_field': 'Some_Field__c',
                'is_required': False,
                'transform_rule': '',
            }
        ]
        put_response = self.client.put(
            reverse('contracts:salesforce_field_map_api'),
            data=json.dumps({'mappings': mappings}),
            content_type='application/json',
        )
        self.assertEqual(put_response.status_code, 400)
        self.assertIn('Unsupported canonical_field', put_response.json()['error'])

    def test_default_mapping_fixture_matches_service_schema(self):
        fixture_path = Path('tests/fixtures/salesforce_default_field_map.json')
        fixture_rows = json.loads(fixture_path.read_text(encoding='utf-8'))
        service_rows = default_field_map_records()
        self.assertEqual(len(fixture_rows), 20)
        self.assertEqual(len(service_rows), 20)
        self.assertEqual(
            {row['canonical_field'] for row in fixture_rows},
            {row['canonical_field'] for row in service_rows},
        )

    def test_collect_control_evidence_writes_snapshot(self):
        with TemporaryDirectory() as tmpdir:
            call_command('collect_control_evidence', output_dir=tmpdir)
            files = list(Path(tmpdir).glob('control-evidence-*.json'))
            self.assertTrue(files)
            payload = json.loads(files[0].read_text(encoding='utf-8'))
            self.assertIn('controls', payload)
            self.assertIn('ops.alert_policy', payload['controls'])
