
import json
import os

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from contracts.models import AuditLog, Contract, Organization, OrganizationMembership


class IroncladFeaturesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )
        self.organization = Organization.objects.create(name='Iron Firm', slug='iron-firm')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        os.environ['FEATURE_REDESIGN'] = 'true'

        self.contract = Contract.objects.create(
            organization=self.organization,
            title='Test Contract',
            content='Test content',
            status='ACTIVE',
            created_by=self.user,
        )
        self.client.login(username='testuser', password='testpass123')

    def test_contract_list_has_search_filter_and_table(self):
        response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Search contracts...')
        self.assertContains(response, 'All Statuses')
        self.assertContains(response, 'Title')
        self.assertContains(response, 'Status')
        self.assertContains(response, 'Test Contract')

    def test_contracts_api_returns_payload(self):
        response = self.client.get(reverse('contracts:contracts_api'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('contracts', payload)
        self.assertIn('total_count', payload)

    def test_contract_detail_api_existing_contract(self):
        response = self.client.get(reverse('contracts:contract_detail_api', args=[str(self.contract.pk)]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get('id'), str(self.contract.pk))

    def test_contract_detail_api_missing_contract(self):
        response = self.client.get(reverse('contracts:contract_detail_api', args=['999999']))
        self.assertIn(response.status_code, [404, 500])

    def test_bulk_update_api_contract_status(self):
        body = {
            'contract_ids': [str(self.contract.pk)],
            'updates': {'status': 'DRAFT'},
        }
        response = self.client.post(
            reverse('contracts:contracts_bulk_update_api'),
            data=json.dumps(body),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, Contract.Status.DRAFT)

    def test_bulk_update_api_lifecycle_stage_and_audit_log(self):
        body = {
            'contract_ids': [str(self.contract.pk)],
            'updates': {'lifecycle_stage': 'INTERNAL_REVIEW'},
        }
        response = self.client.post(
            reverse('contracts:contracts_bulk_update_api'),
            data=json.dumps(body),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.lifecycle_stage, 'INTERNAL_REVIEW')
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.user,
                model_name='Contract',
                changes__event='bulk_contract_update',
            ).exists()
        )

    def test_bulk_update_api_rejects_disallowed_fields(self):
        body = {
            'contract_ids': [str(self.contract.pk)],
            'updates': {'title': 'Injected Title'},
        }
        response = self.client.post(
            reverse('contracts:contracts_bulk_update_api'),
            data=json.dumps(body),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn('unsupported fields', payload.get('error', ''))
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.title, 'Test Contract')

    def test_bulk_update_api_rejects_invalid_status(self):
        body = {
            'contract_ids': [str(self.contract.pk)],
            'updates': {'status': 'NOT_A_REAL_STATUS'},
        }
        response = self.client.post(
            reverse('contracts:contracts_bulk_update_api'),
            data=json.dumps(body),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('valid contract status', response.json().get('error', ''))

    def test_bulk_update_api_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertTrue(csrf_client.login(username='testuser', password='testpass123'))

        body = {
            'contract_ids': [str(self.contract.pk)],
            'updates': {'status': 'DRAFT'},
        }
        response = csrf_client.post(
            reverse('contracts:contracts_bulk_update_api'),
            data=json.dumps(body),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
