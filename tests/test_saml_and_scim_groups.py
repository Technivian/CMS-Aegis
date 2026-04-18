import json
from unittest.mock import Mock, patch
from datetime import timedelta

from django.utils import timezone

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from contracts.models import Organization, OrganizationMembership, UserProfile
from contracts.saml import extract_saml_identity


User = get_user_model()


@override_settings(SAML_ENABLED=True)
class SamlAndScimGroupTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='testpass123')
        self.member = User.objects.create_user(username='member', email='member@example.com', password='testpass123')
        self.organization = Organization.objects.create(
            name='SAML Org',
            slug='saml-org',
            identity_provider=Organization.IdentityProvider.SAML,
            require_mfa=True,
            saml_entity_id='https://idp.example.com/entity',
            saml_sso_url='https://idp.example.com/sso',
            saml_slo_url='https://idp.example.com/slo',
            saml_x509_certificate='CERTDATA',
            scim_enabled=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
        )
        UserProfile.objects.get_or_create(user=self.owner)
        UserProfile.objects.get_or_create(user=self.member)

    def test_saml_select_lists_enabled_organizations(self):
        response = self.client.get(reverse('saml_select'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SAML Org')

    @patch('contracts.views_domains.saml.build_saml_auth')
    def test_saml_login_redirects_to_idp(self, mock_build_auth):
        auth = Mock()
        auth.login.return_value = 'https://idp.example.com/authorize'
        mock_build_auth.return_value = auth

        response = self.client.get(reverse('saml_login', kwargs={'organization_slug': self.organization.slug}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://idp.example.com/authorize')

    @patch('contracts.views_domains.saml.build_saml_auth')
    @patch('contracts.views_domains.saml.validate_saml_response', return_value=[])
    @patch('contracts.views_domains.saml.extract_saml_identity')
    def test_saml_acs_provisions_and_authenticates_user(self, mock_extract_identity, mock_validate_response, mock_build_auth):
        auth = Mock()
        auth.get_errors.return_value = []
        auth.is_authenticated.return_value = True
        auth.get_last_assertion_not_on_or_after.return_value = timezone.now() + timedelta(minutes=5)
        auth.login.return_value = None
        auth.process_response.return_value = None
        mock_build_auth.return_value = auth
        mock_extract_identity.return_value = {
            'email': 'new-saml@example.com',
            'first_name': 'Saml',
            'last_name': 'User',
            'role': OrganizationMembership.Role.ADMIN,
        }

        response = self.client.post(reverse('saml_acs', kwargs={'organization_slug': self.organization.slug}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('dashboard'))

        user = User.objects.get(email='new-saml@example.com')
        profile = UserProfile.objects.get(user=user)
        membership = OrganizationMembership.objects.get(organization=self.organization, user=user)
        self.assertTrue(profile.mfa_enabled)
        self.assertEqual(membership.role, OrganizationMembership.Role.ADMIN)

    @patch('contracts.views_domains.saml.build_saml_auth')
    @patch('contracts.views_domains.saml.validate_saml_response', return_value=[])
    @patch('contracts.views_domains.saml.assertion_is_fresh', return_value=False)
    def test_saml_acs_rejects_expired_assertions(self, mock_assertion_is_fresh, mock_validate_response, mock_build_auth):
        auth = Mock()
        auth.get_errors.return_value = []
        auth.is_authenticated.return_value = True
        auth.process_response.return_value = None
        mock_build_auth.return_value = auth

        response = self.client.post(reverse('saml_acs', kwargs={'organization_slug': self.organization.slug}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('login'))
        mock_validate_response.assert_called_once()
        mock_assertion_is_fresh.assert_called_once()

    @patch('contracts.views_domains.saml.build_saml_auth')
    @patch('contracts.views_domains.saml.validate_saml_response', return_value=['Response signature validation failed.'])
    def test_saml_acs_rejects_bad_signature(self, mock_validate_response, mock_build_auth):
        auth = Mock()
        auth.get_errors.return_value = []
        auth.is_authenticated.return_value = True
        auth.get_last_assertion_not_on_or_after.return_value = timezone.now() + timedelta(minutes=5)
        auth.process_response.return_value = None
        mock_build_auth.return_value = auth

        response = self.client.post(reverse('saml_acs', kwargs={'organization_slug': self.organization.slug}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('login'))
        mock_validate_response.assert_called_once()

    @patch('contracts.views_domains.saml.build_saml_auth')
    def test_saml_logout_redirects_to_idp(self, mock_build_auth):
        auth = Mock()
        auth.logout.return_value = 'https://idp.example.com/logout'
        mock_build_auth.return_value = auth

        response = self.client.get(reverse('saml_logout', kwargs={'organization_slug': self.organization.slug}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://idp.example.com/logout')

    @patch('contracts.views_domains.saml.logger')
    @patch('contracts.views_domains.saml.build_saml_auth')
    def test_saml_logout_falls_back_when_idp_logout_fails(self, mock_build_auth, mock_logger):
        auth = Mock()
        auth.logout.side_effect = RuntimeError('logout failed')
        mock_build_auth.return_value = auth

        response = self.client.get(reverse('saml_logout', kwargs={'organization_slug': self.organization.slug}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('login'))
        mock_logger.exception.assert_called_once()

    def test_saml_identity_aliases_and_group_roles_resolve(self):
        auth = Mock()
        auth.get_attributes.return_value = {
            'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress': ['alias@example.com'],
            'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname': ['Alias'],
            'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname': ['User'],
            'displayName': ['Alias User'],
            'groups': [{'value': 'Legal Admins'}, ['Operations', 'Team']],
        }
        auth.get_nameid.return_value = ''

        identity = extract_saml_identity(auth)

        self.assertEqual(identity['email'], 'alias@example.com')
        self.assertEqual(identity['first_name'], 'Alias')
        self.assertEqual(identity['last_name'], 'User')
        self.assertEqual(identity['display_name'], 'Alias User')
        self.assertEqual(identity['role'], OrganizationMembership.Role.ADMIN)

    @patch('contracts.views_domains.saml.get_saml_metadata_xml')
    def test_saml_metadata_returns_xml(self, mock_get_metadata):
        mock_get_metadata.return_value = '<xml>metadata</xml>'

        response = self.client.get(reverse('saml_metadata', kwargs={'organization_slug': self.organization.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        self.assertContains(response, 'metadata', status_code=200)

    def test_scim_group_provisioning_and_deprovisioning_updates_roles(self):
        token = self.organization.rotate_scim_token()
        membership = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        create_response = self.client.post(
            reverse('scim_groups_api_root'),
            data=json.dumps({
                'displayName': 'Legal Ops',
                'externalId': 'group-legal-ops',
                'active': True,
                'members': [{'value': str(membership.id)}],
                'urn:ietf:params:scim:schemas:extension:enterprise:2.0:Group': {
                    'role': OrganizationMembership.Role.ADMIN,
                },
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(create_response.status_code, 201)

        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.ADMIN)

        list_response = self.client.get(
            reverse('scim_groups_api_root'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(list_response.status_code, 200)
        payload = json.loads(list_response.content)
        self.assertEqual(payload['totalResults'], 1)

        group_id = payload['Resources'][0]['id']
        delete_response = self.client.delete(
            reverse('scim_group_api_root', kwargs={'scim_id': group_id}),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(delete_response.status_code, 204)

        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.MEMBER)

    def test_scim_group_filter_supports_display_name(self):
        token = self.organization.rotate_scim_token()
        self.client.post(
            reverse('scim_groups_api_root'),
            data=json.dumps({
                'displayName': 'Legal Ops',
                'externalId': 'group-legal-ops',
                'active': True,
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        response = self.client.get(
            reverse('scim_groups_api_root'),
            {'filter': 'displayName eq "Legal Ops"'},
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['totalResults'], 1)

    def test_scim_users_support_pagination(self):
        token = self.organization.rotate_scim_token()
        response = self.client.get(
            reverse('scim_users_api_root'),
            {'startIndex': 2, 'count': 1},
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['startIndex'], 2)
        self.assertEqual(payload['itemsPerPage'], 1)

    def test_scim_user_patch_updates_identity_fields(self):
        token = self.organization.rotate_scim_token()
        membership = OrganizationMembership.objects.get(organization=self.organization, user=self.member)
        response = self.client.patch(
            reverse('scim_user_api_root', kwargs={'scim_id': membership.id}),
            data=json.dumps({
                'Operations': [
                    {'op': 'replace', 'path': 'name', 'value': {'givenName': 'Updated', 'familyName': 'User'}},
                    {'op': 'replace', 'path': 'userName', 'value': 'updated@example.com'},
                ]
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(response.status_code, 200)
        membership.refresh_from_db()
        updated_user = User.objects.get(pk=membership.user_id)
        self.assertEqual(updated_user.first_name, 'Updated')
        self.assertEqual(updated_user.email, 'updated@example.com')

    def test_scim_nested_group_memberships_propagate_roles(self):
        token = self.organization.rotate_scim_token()
        membership = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        child_response = self.client.post(
            reverse('scim_groups_api_root'),
            data=json.dumps({
                'displayName': 'Child Group',
                'externalId': 'child-group',
                'active': True,
                'members': [{'value': str(membership.id), 'type': 'User'}],
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        child_group_id = json.loads(child_response.content)['id']

        self.client.post(
            reverse('scim_groups_api_root'),
            data=json.dumps({
                'displayName': 'Parent Group',
                'externalId': 'parent-group',
                'active': True,
                'members': [{'value': child_group_id, 'type': 'Group'}],
                'urn:ietf:params:scim:schemas:extension:enterprise:2.0:Group': {
                    'role': OrganizationMembership.Role.ADMIN,
                },
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.ADMIN)
