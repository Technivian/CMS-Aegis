from django.contrib.auth import get_user_model

from .models import OrganizationMembership

User = get_user_model()


class ContractAction:
    VIEW = 'view'
    COMMENT = 'comment'
    AI = 'ai'
    EDIT = 'edit'


def get_active_org_membership(user, organization):
    if not user or not getattr(user, 'is_authenticated', False) or organization is None:
        return None
    return (
        OrganizationMembership.objects
        .filter(
            user=user,
            organization=organization,
            is_active=True,
            organization__is_active=True,
        )
        .first()
    )


def can_manage_organization(user, organization):
    membership = get_active_org_membership(user, organization)
    if membership is None:
        return False
    return membership.role in [OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN]


def is_organization_owner(user, organization):
    membership = get_active_org_membership(user, organization)
    return bool(membership and membership.role == OrganizationMembership.Role.OWNER)


def can_access_contract_action(user, contract, action=ContractAction.VIEW):
    if contract is None:
        return False

    membership = get_active_org_membership(user, contract.organization)
    if membership is None:
        return False

    if action in [ContractAction.VIEW, ContractAction.COMMENT, ContractAction.AI]:
        return True

    if action == ContractAction.EDIT:
        if membership.role in [OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN]:
            return True
        return bool(contract.created_by_id and contract.created_by_id == user.id)

    return False
