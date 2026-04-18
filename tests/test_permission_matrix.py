from django.contrib.auth import get_user_model
from django.test import TestCase

from contracts.models import Contract, Organization, OrganizationMembership
from contracts.permissions import ContractAction, can_access_contract_action, can_manage_organization


User = get_user_model()


class PermissionMatrixTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Matrix Org', slug='matrix-org')
        self.owner = User.objects.create_user(username='owner', password='testpass123')
        self.admin = User.objects.create_user(username='admin', password='testpass123')
        self.member = User.objects.create_user(username='member', password='testpass123')
        self.outsider = User.objects.create_user(username='outsider', password='testpass123')
        self.inactive_member = User.objects.create_user(username='inactive', password='testpass123')

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
            organization=self.organization,
            user=self.inactive_member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=False,
        )

        self.owner_created_contract = Contract.objects.create(
            organization=self.organization,
            title='Owner Created',
            contract_type='NDA',
            status='ACTIVE',
            created_by=self.owner,
        )
        self.member_created_contract = Contract.objects.create(
            organization=self.organization,
            title='Member Created',
            contract_type='NDA',
            status='ACTIVE',
            created_by=self.member,
        )

    def test_can_manage_organization_matches_role_and_membership_state(self):
        self.assertTrue(can_manage_organization(self.owner, self.organization))
        self.assertTrue(can_manage_organization(self.admin, self.organization))
        self.assertFalse(can_manage_organization(self.member, self.organization))
        self.assertFalse(can_manage_organization(self.inactive_member, self.organization))
        self.assertFalse(can_manage_organization(self.outsider, self.organization))
        self.assertFalse(can_manage_organization(None, self.organization))

    def test_can_access_contract_action_matches_role_matrix(self):
        allowed_actions = [ContractAction.VIEW, ContractAction.COMMENT, ContractAction.AI]

        for user in [self.owner, self.admin, self.member]:
            with self.subTest(user=user.username, contract='owner_created', action='read-like'):
                for action in allowed_actions:
                    self.assertTrue(
                        can_access_contract_action(user, self.owner_created_contract, action),
                        f'{user.username} should be allowed to {action} owner-created contract',
                    )

        self.assertTrue(
            can_access_contract_action(self.owner, self.owner_created_contract, ContractAction.EDIT)
        )
        self.assertTrue(
            can_access_contract_action(self.admin, self.owner_created_contract, ContractAction.EDIT)
        )
        self.assertFalse(
            can_access_contract_action(self.member, self.owner_created_contract, ContractAction.EDIT)
        )

        for action in allowed_actions:
            with self.subTest(user='member_creator', action=action):
                self.assertTrue(
                    can_access_contract_action(self.member, self.member_created_contract, action)
                )

        self.assertTrue(
            can_access_contract_action(self.member, self.member_created_contract, ContractAction.EDIT)
        )
        self.assertTrue(
            can_access_contract_action(self.admin, self.member_created_contract, ContractAction.EDIT)
        )
        self.assertTrue(
            can_access_contract_action(self.owner, self.member_created_contract, ContractAction.EDIT)
        )

        self.assertFalse(
            can_access_contract_action(self.outsider, self.owner_created_contract, ContractAction.VIEW)
        )
        self.assertFalse(
            can_access_contract_action(self.inactive_member, self.owner_created_contract, ContractAction.VIEW)
        )
        self.assertFalse(can_access_contract_action(None, self.owner_created_contract, ContractAction.VIEW))
        self.assertFalse(can_access_contract_action(self.owner, None, ContractAction.VIEW))
