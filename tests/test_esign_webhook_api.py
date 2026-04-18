import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from contracts.models import Contract, Organization, SignatureRequest


User = get_user_model()


@override_settings(ESIGN_WEBHOOK_SECRET='test-esign-secret')
class ESignWebhookApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='esign-api', password='pass12345')
        self.organization = Organization.objects.create(name='E-Sign API Org', slug='esign-api-org')
        self.contract = Contract.objects.create(organization=self.organization, title='Master Services Agreement')
        self.signature_request = SignatureRequest.objects.create(
            organization=self.organization,
            contract=self.contract,
            signer_name='Signer',
            signer_email='signer@example.com',
            status=SignatureRequest.Status.SENT,
            external_id='esig-100',
            created_by=self.user,
        )
        self.url = reverse('contracts:esign_webhook_api')

    def test_esign_webhook_api_applies_event(self):
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    'event_id': 'evt-100',
                    'external_id': 'esig-100',
                    'status': 'viewed',
                    'event_at': '2026-04-18T10:00:00Z',
                }
            ),
            content_type='application/json',
            HTTP_X_ESIGN_WEBHOOK_SECRET='test-esign-secret',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['applied'], 1)
        self.signature_request.refresh_from_db()
        self.assertEqual(self.signature_request.status, SignatureRequest.Status.VIEWED)

    def test_esign_webhook_api_is_idempotent_for_duplicate_event_id(self):
        payload = {
            'event_id': 'evt-dup-100',
            'external_id': 'esig-100',
            'status': 'viewed',
            'event_at': '2026-04-18T10:00:00Z',
        }
        first = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_ESIGN_WEBHOOK_SECRET='test-esign-secret',
        )
        second = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_ESIGN_WEBHOOK_SECRET='test-esign-secret',
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['summary']['duplicate'], 1)

    def test_esign_webhook_api_rejects_invalid_secret(self):
        response = self.client.post(
            self.url,
            data=json.dumps({'event_id': 'evt-403', 'external_id': 'esig-100', 'status': 'viewed'}),
            content_type='application/json',
            HTTP_X_ESIGN_WEBHOOK_SECRET='wrong-secret',
        )
        self.assertEqual(response.status_code, 403)
