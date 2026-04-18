import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.models import Organization, OrganizationMembership, UserProfile


User = get_user_model()


class IdentitySettingsAndScimTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='testpass123')
        self.member = User.objects.create_user(username='member', email='member@example.com', password='testpass123')
        self.organization = Organization.objects.create(name='Identity Org', slug='identity-org')
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
        UserProfile.objects.get_or_create(user=self.owner)
        UserProfile.objects.get_or_create(user=self.member)

    def test_owner_can_save_identity_settings(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.post(
            reverse('organization_identity_settings'),
            {
                'identity_provider': Organization.IdentityProvider.SAML,
                'saml_entity_id': 'https://idp.example.com/entity',
                'saml_sso_url': 'https://idp.example.com/sso',
                'saml_metadata_url': 'https://idp.example.com/metadata',
                'saml_x509_certificate': 'CERTDATA',
                'scim_enabled': 'on',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.identity_provider, Organization.IdentityProvider.SAML)
        self.assertTrue(self.organization.scim_enabled)
        self.assertEqual(self.organization.saml_entity_id, 'https://idp.example.com/entity')

    def test_owner_can_rotate_scim_token(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.post(
            reverse('organization_identity_settings'),
            {'action': 'rotate_scim_token'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.organization.refresh_from_db()
        self.assertTrue(self.organization.scim_enabled)
        self.assertTrue(self.organization.scim_token_hash)
        self.assertTrue(self.organization.scim_token_last4)

    def test_scim_users_api_requires_valid_token(self):
        response = self.client.get(reverse('contracts:scim_users_api'))
        self.assertEqual(response.status_code, 401)

    def test_scim_can_list_and_provision_users(self):
        token = self.organization.rotate_scim_token()

        response = self.client.get(
            reverse('scim_users_api_root'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['totalResults'], 2)

        create_response = self.client.post(
            reverse('scim_users_api_root'),
            data=json.dumps({
                'userName': 'new-user@example.com',
                'name': {'givenName': 'New', 'familyName': 'User'},
                'active': True,
                'urn:ietf:params:scim:schemas:extension:enterprise:2.0:User': {
                    'role': OrganizationMembership.Role.ADMIN,
                    'mfaEnabled': True,
                },
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertTrue(OrganizationMembership.objects.filter(organization=self.organization, user__email='new-user@example.com').exists())

    def test_scim_reconciles_external_ids_and_boolean_strings(self):
        token = self.organization.rotate_scim_token()

        create_response = self.client.post(
            reverse('scim_users_api_root'),
            data=json.dumps({
                'userName': 'ext-user@example.com',
                'externalId': 'external-user-123',
                'active': 'false',
                'name': {'givenName': 'External', 'familyName': 'User'},
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(create_response.status_code, 201)

        membership = OrganizationMembership.objects.get(
            organization=self.organization,
            scim_external_id='external-user-123',
        )
        self.assertFalse(membership.is_active)

        update_response = self.client.post(
            reverse('scim_users_api_root'),
            data=json.dumps({
                'userName': 'renamed-ext-user@example.com',
                'externalId': 'external-user-123',
                'active': 'true',
                'name': {'givenName': 'Renamed', 'familyName': 'User'},
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(update_response.status_code, 201)

        membership.refresh_from_db()
        updated_user = User.objects.get(pk=membership.user_id)
        self.assertEqual(updated_user.email, 'renamed-ext-user@example.com')
        self.assertTrue(membership.is_active)
        self.assertEqual(
            OrganizationMembership.objects.filter(
                organization=self.organization,
                scim_external_id='external-user-123',
            ).count(),
            1,
        )

        filter_response = self.client.get(
            reverse('scim_users_api_root'),
            {'filter': 'externalId eq "external-user-123"'},
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(filter_response.status_code, 200)
        payload = json.loads(filter_response.content)
        self.assertEqual(payload['totalResults'], 1)

    def test_scim_post_rejects_operations_payloads(self):
        token = self.organization.rotate_scim_token()

        response = self.client.post(
            reverse('scim_users_api_root'),
            data=json.dumps({
                'Operations': [
                    {'op': 'replace', 'path': 'active', 'value': False},
                ],
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.content)
        self.assertEqual(payload['scimType'], 'invalidSyntax')

    def test_scim_can_deprovision_members(self):
        token = self.organization.rotate_scim_token()
        membership = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        response = self.client.delete(
            reverse('scim_user_api_root', kwargs={'scim_id': membership.id}),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 204)
        membership.refresh_from_db()
        self.assertFalse(membership.is_active)

    def test_scim_patch_supports_external_id_and_string_boolean_values(self):
        token = self.organization.rotate_scim_token()
        membership = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        response = self.client.patch(
            reverse('scim_user_api_root', kwargs={'scim_id': membership.id}),
            data=json.dumps({
                'Operations': [
                    {'op': 'replace', 'path': 'externalId', 'value': 'patched-external-id'},
                    {'op': 'replace', 'path': 'active', 'value': 'false'},
                    {'op': 'replace', 'path': 'name.givenName', 'value': 'Patched'},
                    {'op': 'replace', 'path': 'name.familyName', 'value': 'Member'},
                ]
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(response.status_code, 200)

        membership.refresh_from_db()
        updated_user = User.objects.get(pk=membership.user_id)
        self.assertEqual(membership.scim_external_id, 'patched-external-id')
        self.assertFalse(membership.is_active)
        self.assertEqual(updated_user.first_name, 'Patched')
        self.assertEqual(updated_user.last_name, 'Member')
