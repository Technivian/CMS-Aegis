from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from datetime import timezone as dt_timezone
from datetime import datetime

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings

from .models import Organization, OrganizationMembership, UserProfile

User = get_user_model()

EMAIL_ATTRIBUTE_KEYS = {
    'email',
    'mail',
    'upn',
    'preferred_username',
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name',
}
GIVEN_NAME_ATTRIBUTE_KEYS = {
    'given_name',
    'givenname',
    'first_name',
    'firstname',
    'first',
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname',
}
FAMILY_NAME_ATTRIBUTE_KEYS = {
    'family_name',
    'familyname',
    'last_name',
    'lastname',
    'last',
    'surname',
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname',
}
ROLE_ATTRIBUTE_KEYS = {
    'role',
    'roles',
    'groups',
    'memberof',
    'member_of',
    'http://schemas.microsoft.com/ws/2008/06/identity/claims/role',
}


def get_saml_organization(slug: str) -> Organization | None:
    if not slug:
        return None
    return Organization.objects.filter(
        slug=slug,
        identity_provider=Organization.IdentityProvider.SAML,
        is_active=True,
    ).first()


def _absolute_reverse(request, name: str, kwargs: dict[str, str]) -> str:
    return request.build_absolute_uri(reverse(name, kwargs=kwargs))


def build_saml_request_data(request) -> dict:
    return {
        'https': 'on' if request.is_secure() else 'off',
        'http_host': request.get_host(),
        'server_port': request.get_port(),
        'script_name': request.path,
        'get_data': request.GET.copy(),
        'post_data': request.POST.copy(),
    }


def build_saml_settings(request, organization: Organization) -> OneLogin_Saml2_Settings:
    entity_id = settings.SAML_SP_ENTITY_ID.strip() or _absolute_reverse(
        request,
        'saml_metadata',
        {'organization_slug': organization.slug},
    )
    acs_url = _absolute_reverse(request, 'saml_acs', {'organization_slug': organization.slug})
    certificate = organization.saml_x509_certificate.strip()

    settings_dict = {
        'strict': settings.SAML_STRICT,
        'debug': settings.DEBUG,
        'sp': {
            'entityId': entity_id,
            'assertionConsumerService': {
                'url': acs_url,
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
            },
            'singleLogoutService': {
                'url': _absolute_reverse(request, 'saml_logout', {'organization_slug': organization.slug}),
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
            'x509cert': settings.SAML_SP_X509_CERT.strip(),
            'privateKey': settings.SAML_SP_PRIVATE_KEY.strip(),
            'NameIDFormat': 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress',
        },
        'idp': {
            'entityId': organization.saml_entity_id or organization.slug,
            'singleSignOnService': {
                'url': organization.saml_sso_url,
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
            'singleLogoutService': {
                'url': organization.saml_slo_url or organization.saml_sso_url,
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
            'x509cert': certificate,
        },
        'security': {
            'authnRequestsSigned': False,
            'logoutRequestSigned': False,
            'logoutResponseSigned': False,
            'wantAssertionsSigned': bool(certificate),
            'wantMessagesSigned': bool(certificate),
            'wantNameId': True,
            'wantAttributeStatement': True,
        },
    }
    return OneLogin_Saml2_Settings(settings_dict)


def build_saml_auth(request, organization: Organization) -> OneLogin_Saml2_Auth:
    return OneLogin_Saml2_Auth(build_saml_request_data(request), old_settings=build_saml_settings(request, organization))


def get_saml_metadata_xml(request, organization: Organization) -> str:
    return build_saml_settings(request, organization).get_sp_metadata()


def _first_matching_attribute(attributes: dict[str, list[str]], keys: list[str]) -> str:
    normalized_keys = [key.lower() for key in keys]
    for key, values in attributes.items():
        if key.lower() in normalized_keys and values:
            return (values[0] or '').strip()
    return ''


def _flatten_attribute_values(values) -> list[str]:
    flattened = []
    if isinstance(values, dict):
        candidate = values.get('value')
        if candidate not in {None, ''}:
            flattened.append(str(candidate))
        return flattened
    if not isinstance(values, (list, tuple, set)):
        if values not in {None, ''}:
            flattened.append(str(values))
        return flattened
    for value in values:
        flattened.extend(_flatten_attribute_values(value))
    return flattened


def _attribute_tokens(attributes: dict[str, list[str]], keys: set[str]) -> set[str]:
    tokens: set[str] = set()
    for key, values in attributes.items():
        if key.lower() not in keys:
            continue
        for value in _flatten_attribute_values(values):
            for token in str(value).replace(',', ' ').replace(';', ' ').split():
                normalized = token.strip().lower()
                if normalized:
                    tokens.add(normalized)
    return tokens


def _infer_role_from_attributes(attributes: dict[str, list[str]]) -> str:
    tokens = _attribute_tokens(attributes, ROLE_ATTRIBUTE_KEYS)
    role_text = ' '.join(sorted(tokens))
    if any(token in role_text for token in {'owner', 'superuser', 'super-admin', 'superadmin'}):
        return OrganizationMembership.Role.OWNER
    if any(token in role_text for token in {'admin', 'administrator', 'legal-admin', 'org-admin'}):
        return OrganizationMembership.Role.ADMIN
    return OrganizationMembership.Role.MEMBER


def extract_saml_identity(auth: OneLogin_Saml2_Auth) -> dict[str, str]:
    attributes = auth.get_attributes() or {}
    email = (
        _first_matching_attribute(attributes, list(EMAIL_ATTRIBUTE_KEYS))
        or (auth.get_nameid() or '')
    ).strip().lower()
    first_name = _first_matching_attribute(
        attributes,
        list(GIVEN_NAME_ATTRIBUTE_KEYS),
    )
    last_name = _first_matching_attribute(
        attributes,
        list(FAMILY_NAME_ATTRIBUTE_KEYS),
    )
    display_name = _first_matching_attribute(
        attributes,
        ['display_name', 'displayname', 'name', 'full_name', 'fullname'],
    )
    role = _infer_role_from_attributes(attributes)
    return {
        'email': email,
        'first_name': first_name.strip(),
        'last_name': last_name.strip(),
        'display_name': display_name.strip(),
        'role': role,
    }


def assertion_is_fresh(auth: OneLogin_Saml2_Auth) -> bool:
    not_on_or_after = auth.get_last_assertion_not_on_or_after()
    if not not_on_or_after:
        return True
    if isinstance(not_on_or_after, datetime):
        expiry = not_on_or_after
    else:
        from django.utils.dateparse import parse_datetime
        expiry = parse_datetime(str(not_on_or_after))
    if expiry is None:
        return False
    if timezone.is_naive(expiry):
        expiry = timezone.make_aware(expiry, dt_timezone.utc)
    return expiry > timezone.now()


def validate_saml_response(auth: OneLogin_Saml2_Auth, organization: Organization, request_data: dict) -> list[str]:
    errors: list[str] = []
    try:
        if not auth.validate_response_signature(request_data):
            errors.append('Response signature validation failed.')
    except Exception:
        errors.append('Response signature validation raised an exception.')

    settings_obj = auth.get_settings()
    response = getattr(auth, 'response', None)
    expected_audience = (settings_obj.get_sp_data() or {}).get('entityId', '').strip()
    expected_issuer = (organization.saml_entity_id or '').strip()

    if response is not None:
        try:
            audiences = {str(audience).strip() for audience in (response.get_audiences() or []) if str(audience).strip()}
        except Exception:
            audiences = set()
        if expected_audience and expected_audience not in audiences:
            errors.append('SAML audience did not match the configured SP entity ID.')

        try:
            issuers = {str(issuer).strip() for issuer in (response.get_issuers() or []) if str(issuer).strip()}
        except Exception:
            issuers = set()
        if expected_issuer and expected_issuer not in issuers:
            errors.append('SAML issuer did not match the configured IdP entity ID.')

    return errors


def provision_saml_membership(
    organization: Organization,
    email: str,
    first_name: str = '',
    last_name: str = '',
    role: str | None = None,
) -> tuple[OrganizationMembership, UserProfile]:
    normalized_email = (email or '').strip().lower()
    if not normalized_email:
        raise ValueError('email is required')

    if not first_name and not last_name:
        display_name = email.split('@', 1)[0].replace('.', ' ').replace('_', ' ').strip()
        if display_name:
            parts = display_name.split()
            first_name = parts[0] if parts else ''
            last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''

    user = User.objects.filter(email__iexact=normalized_email).first()
    if user is None:
        username_base = slugify(normalized_email.split('@', 1)[0] or normalized_email)[:30] or 'saml-user'
        username = username_base
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f'{username_base[:24]}-{suffix}'
        user = User.objects.create_user(
            username=username,
            email=normalized_email,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
        )

    updates = []
    if user.email != normalized_email:
        user.email = normalized_email
        updates.append('email')
    if first_name.strip() and user.first_name != first_name.strip():
        user.first_name = first_name.strip()
        updates.append('first_name')
    if last_name.strip() and user.last_name != last_name.strip():
        user.last_name = last_name.strip()
        updates.append('last_name')
    if updates:
        user.save(update_fields=updates)

    membership, _ = OrganizationMembership.objects.get_or_create(
        organization=organization,
        user=user,
        defaults={
            'role': role or OrganizationMembership.Role.MEMBER,
            'is_active': True,
        },
    )
    membership_updates = []
    if role and membership.role != role:
        membership.role = role
        membership_updates.append('role')
    if not membership.is_active:
        membership.is_active = True
        membership_updates.append('is_active')
    if membership_updates:
        membership.save(update_fields=membership_updates)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_active:
        profile.is_active = True
        profile.save(update_fields=['is_active', 'updated_at'])
    return membership, profile
