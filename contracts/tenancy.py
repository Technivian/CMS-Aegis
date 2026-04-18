from typing import Optional

from django.contrib.auth import get_user_model
from django.db.models import Model, QuerySet
from django.utils.text import slugify

from .models import Organization, OrganizationMembership
from .services.starter_content import ensure_org_starter_content

User = get_user_model()


def ensure_user_organization(user: Optional[User]) -> Optional[Organization]:
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    memberships = (
        OrganizationMembership.objects
        .filter(user=user, is_active=True, organization__is_active=True)
        .select_related('organization')
    )
    existing = memberships.order_by('id').first()
    if existing:
        return existing.organization

    base_slug = slugify(getattr(user, 'username', '') or f'user-{user.id}') or f'user-{user.id}'
    org_slug = base_slug
    n = 2
    while Organization.objects.filter(slug=org_slug).exists():
        org_slug = f'{base_slug}-{n}'
        n += 1

    org_name = f"{user.get_full_name().strip() or user.username}'s Firm"
    organization = Organization.objects.create(name=org_name, slug=org_slug)
    OrganizationMembership.objects.create(
        organization=organization,
        user=user,
        role=OrganizationMembership.Role.OWNER,
        is_active=True,
    )
    ensure_org_starter_content(organization)
    return organization


def get_user_organization(user: Optional[User]) -> Optional[Organization]:
    base_org = ensure_user_organization(user)
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    preferred_org_id = getattr(user, '_active_organization_id', None)
    if preferred_org_id:
        selected = (
            OrganizationMembership.objects
            .filter(
                user=user,
                is_active=True,
                organization__is_active=True,
                organization_id=preferred_org_id,
            )
            .select_related('organization')
            .first()
        )
        if selected:
            return selected.organization

    return base_org


def scope_queryset_for_organization(queryset: QuerySet, organization: Optional[Organization]) -> QuerySet:
    if organization is None:
        return queryset.none()

    model_cls: type[Model] = queryset.model
    field_names = {f.name for f in model_cls._meta.get_fields()}
    if 'organization' in field_names:
        return queryset.filter(organization=organization)
    return queryset


def set_organization_on_instance(instance: Model, organization: Optional[Organization]) -> None:
    if organization is None:
        return
    if hasattr(instance, 'organization_id') and not getattr(instance, 'organization_id', None):
        instance.organization = organization
