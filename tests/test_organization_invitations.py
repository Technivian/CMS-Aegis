from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from contracts.models import AuditLog, Organization, OrganizationInvitation, OrganizationMembership


class OrganizationInvitationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='testpass123',
        )
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='testpass123',
        )
        self.member = User.objects.create_user(
            username='member',
            email='member@example.com',
            password='testpass123',
        )
        self.invited_user = User.objects.create_user(
            username='invitee',
            email='invitee@example.com',
            password='testpass123',
        )
        self.outsider = User.objects.create_user(
            username='outsider',
            email='outsider@example.com',
            password='testpass123',
        )

        self.organization = Organization.objects.create(name='Acme Firm', slug='acme-firm')
        self.other_organization = Organization.objects.create(name='Other Firm', slug='other-firm')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.outsider,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

    def test_owner_can_create_invitation(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('contracts:organization_team'),
            {'email': 'newuser@example.com', 'role': OrganizationMembership.Role.ADMIN},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            OrganizationInvitation.objects.filter(
                organization=self.organization,
                email='newuser@example.com',
                role=OrganizationMembership.Role.ADMIN,
                status=OrganizationInvitation.Status.PENDING,
            ).exists()
        )

    def test_non_admin_member_cannot_manage_team(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('contracts:organization_team'))

        self.assertEqual(response.status_code, 403)

    def test_admin_can_view_team_management(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('contracts:organization_team'))

        self.assertEqual(response.status_code, 200)

    def test_admin_can_create_invitation(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(
            reverse('contracts:organization_team'),
            {'email': 'admininvite@example.com', 'role': OrganizationMembership.Role.MEMBER},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            OrganizationInvitation.objects.filter(
                organization=self.organization,
                email='admininvite@example.com',
                role=OrganizationMembership.Role.MEMBER,
                status=OrganizationInvitation.Status.PENDING,
            ).exists()
        )

    def test_matching_email_can_accept_invitation(self):
        invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email='invitee@example.com',
            role=OrganizationMembership.Role.MEMBER,
            invited_by=self.owner,
        )

        self.client.login(username='invitee', password='testpass123')
        response = self.client.get(
            reverse('contracts:accept_organization_invite', kwargs={'token': invitation.token}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            OrganizationMembership.objects.filter(
                organization=self.organization,
                user=self.invited_user,
                is_active=True,
            ).exists()
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.ACCEPTED)

    def test_mismatched_email_cannot_accept_invitation(self):
        invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email='different@example.com',
            role=OrganizationMembership.Role.MEMBER,
            invited_by=self.owner,
        )

        self.client.login(username='invitee', password='testpass123')
        response = self.client.get(
            reverse('contracts:accept_organization_invite', kwargs={'token': invitation.token}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            OrganizationMembership.objects.filter(
                organization=self.organization,
                user=self.invited_user,
            ).exists()
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)

    def test_owner_can_revoke_invitation(self):
        invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email='revoke@example.com',
            role=OrganizationMembership.Role.MEMBER,
            invited_by=self.owner,
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('contracts:revoke_organization_invite', kwargs={'invite_id': invitation.id}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.REVOKED)

    def test_owner_can_resend_invitation(self):
        invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email='resend@example.com',
            role=OrganizationMembership.Role.ADMIN,
            invited_by=self.owner,
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('contracts:resend_organization_invite', kwargs={'invite_id': invitation.id}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.REVOKED)
        self.assertTrue(
            OrganizationInvitation.objects.filter(
                organization=self.organization,
                email='resend@example.com',
                role=OrganizationMembership.Role.ADMIN,
                status=OrganizationInvitation.Status.PENDING,
            ).exclude(id=invitation.id).exists()
        )

    def test_owner_can_update_member_role(self):
        target = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('contracts:update_membership_role', kwargs={'membership_id': target.id}),
            {'role': OrganizationMembership.Role.ADMIN},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.role, OrganizationMembership.Role.ADMIN)

    def test_admin_can_update_member_role_to_admin(self):
        target = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        self.client.login(username='admin', password='testpass123')
        response = self.client.post(
            reverse('contracts:update_membership_role', kwargs={'membership_id': target.id}),
            {'role': OrganizationMembership.Role.ADMIN},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.role, OrganizationMembership.Role.ADMIN)

    def test_admin_cannot_promote_member_to_owner(self):
        target = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        self.client.login(username='admin', password='testpass123')
        response = self.client.post(
            reverse('contracts:update_membership_role', kwargs={'membership_id': target.id}),
            {'role': OrganizationMembership.Role.OWNER},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.role, OrganizationMembership.Role.MEMBER)

    def test_owner_can_deactivate_member(self):
        target = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('contracts:deactivate_organization_member', kwargs={'membership_id': target.id}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_admin_can_deactivate_member(self):
        target = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        self.client.login(username='admin', password='testpass123')
        response = self.client.post(
            reverse('contracts:deactivate_organization_member', kwargs={'membership_id': target.id}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_cannot_deactivate_self_membership(self):
        owner_membership = OrganizationMembership.objects.get(organization=self.organization, user=self.owner)

        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('contracts:deactivate_organization_member', kwargs={'membership_id': owner_membership.id}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        owner_membership.refresh_from_db()
        self.assertTrue(owner_membership.is_active)

    def test_invite_creation_writes_audit_log(self):
        self.client.login(username='owner', password='testpass123')
        self.client.post(
            reverse('contracts:organization_team'),
            {'email': 'audit@example.com', 'role': OrganizationMembership.Role.MEMBER},
            follow=True,
        )

        self.assertTrue(
            AuditLog.objects.filter(
                user=self.owner,
                action=AuditLog.Action.CREATE,
                model_name='OrganizationInvitation',
            ).exists()
        )

    def test_role_update_writes_audit_log(self):
        target = OrganizationMembership.objects.get(organization=self.organization, user=self.member)
        self.client.login(username='owner', password='testpass123')
        self.client.post(
            reverse('contracts:update_membership_role', kwargs={'membership_id': target.id}),
            {'role': OrganizationMembership.Role.ADMIN},
            follow=True,
        )

        self.assertTrue(
            AuditLog.objects.filter(
                user=self.owner,
                action=AuditLog.Action.UPDATE,
                model_name='OrganizationMembership',
                object_id=target.id,
            ).exists()
        )

    def test_invitation_history_shows_non_pending(self):
        OrganizationInvitation.objects.create(
            organization=self.organization,
            email='accepted@example.com',
            role=OrganizationMembership.Role.MEMBER,
            invited_by=self.owner,
            status=OrganizationInvitation.Status.ACCEPTED,
        )
        OrganizationInvitation.objects.create(
            organization=self.organization,
            email='pending@example.com',
            role=OrganizationMembership.Role.MEMBER,
            invited_by=self.owner,
            status=OrganizationInvitation.Status.PENDING,
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('contracts:organization_team'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'accepted@example.com')
        self.assertEqual(response.content.decode().count('pending@example.com'), 1)

    def test_owner_can_reactivate_member(self):
        target = OrganizationMembership.objects.get(organization=self.organization, user=self.member)
        target.is_active = False
        target.save(update_fields=['is_active'])

        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('contracts:reactivate_organization_member', kwargs={'membership_id': target.id}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_non_admin_cannot_view_organization_activity(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('contracts:organization_activity'))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_view_organization_activity(self):
        self.client.login(username='owner', password='testpass123')
        self.client.post(
            reverse('contracts:organization_team'),
            {'email': 'activity@example.com', 'role': OrganizationMembership.Role.MEMBER},
            follow=True,
        )

        response = self.client.get(reverse('contracts:organization_activity'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'OrganizationInvitation')

    def test_admin_can_view_organization_activity(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('contracts:organization_activity'))

        self.assertEqual(response.status_code, 200)

    def test_owner_can_export_organization_activity_csv(self):
        self.client.login(username='owner', password='testpass123')
        self.client.post(
            reverse('contracts:organization_team'),
            {'email': 'export@example.com', 'role': OrganizationMembership.Role.MEMBER},
            follow=True,
        )

        response = self.client.get(reverse('contracts:organization_activity_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        body = response.content.decode()
        self.assertIn('OrganizationInvitation', body)
        self.assertIn('export@example.com', body)

    def test_admin_can_export_organization_activity_csv(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('contracts:organization_activity_export'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_non_admin_cannot_export_organization_activity_csv(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('contracts:organization_activity_export'))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_revoke_member_sessions(self):
        target = OrganizationMembership.objects.get(organization=self.organization, user=self.member)

        owner_client = self.client
        member_client = self.client_class()
        owner_client.login(username='owner', password='testpass123')
        member_client.login(username='member', password='testpass123')

        self.assertEqual(member_client.get(reverse('dashboard')).status_code, 200)

        response = owner_client.post(
            reverse('contracts:revoke_member_sessions', kwargs={'membership_id': target.id}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        member_response = member_client.get(reverse('dashboard'))
        self.assertEqual(member_response.status_code, 302)
        self.assertIn(reverse('login'), member_response['Location'])

    def test_anonymous_user_is_redirected_from_organization_activity_export(self):
        response = self.client.get(reverse('contracts:organization_activity_export'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_export_only_contains_current_organization_activity(self):
        self.client.login(username='owner', password='testpass123')
        self.client.post(
            reverse('contracts:organization_team'),
            {'email': 'alpha-audit@example.com', 'role': OrganizationMembership.Role.MEMBER},
            follow=True,
        )
        self.client.logout()

        self.client.login(username='outsider', password='testpass123')
        self.client.post(
            reverse('contracts:organization_team'),
            {'email': 'beta-audit@example.com', 'role': OrganizationMembership.Role.MEMBER},
            follow=True,
        )

        response = self.client.get(reverse('contracts:organization_activity_export'))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('beta-audit@example.com', body)
        self.assertNotIn('alpha-audit@example.com', body)

    def test_activity_filters_apply(self):
        self.client.login(username='owner', password='testpass123')
        self.client.post(
            reverse('contracts:organization_team'),
            {'email': 'filter@example.com', 'role': OrganizationMembership.Role.MEMBER},
            follow=True,
        )

        response = self.client.get(reverse('contracts:organization_activity'), {
            'action': 'CREATE',
            'model': 'OrganizationInvitation',
            'start_date': '2000-01-01',
            'end_date': '2100-01-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'filter@example.com')
