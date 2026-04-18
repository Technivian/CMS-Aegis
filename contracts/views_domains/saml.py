from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from django.utils import timezone

from contracts.middleware import log_action
from contracts.models import AuditLog, Organization, OrganizationMembership
from contracts.saml import (
    build_saml_auth,
    build_saml_request_data,
    assertion_is_fresh,
    extract_saml_identity,
    get_saml_metadata_xml,
    get_saml_organization,
    provision_saml_membership,
    validate_saml_response,
)

logger = logging.getLogger(__name__)


def _saml_telemetry(event: str, organization: Organization | None, request, level: str = 'info', **details):
    payload = {
        'event': event,
        'organization_id': getattr(organization, 'id', None),
        'organization_slug': getattr(organization, 'slug', None),
        'path': getattr(request, 'path', None),
        'request_id': getattr(request, 'request_id', None),
        **details,
    }
    log_fn = getattr(logger, level, logger.info)
    log_fn('saml_telemetry', extra=payload)


@require_GET
def saml_select(request):
    organizations = Organization.objects.filter(
        identity_provider=Organization.IdentityProvider.SAML,
        is_active=True,
    ).order_by('name')
    return render(request, 'contracts/saml_select.html', {
        'organizations': organizations,
    })


@require_GET
def saml_login(request, organization_slug):
    organization = get_saml_organization(organization_slug)
    if organization is None:
        messages.error(request, 'SAML is not configured for that organization.')
        return redirect('saml_select')

    if not organization.saml_sso_url:
        messages.error(request, 'That organization does not have a SAML SSO URL yet.')
        return redirect('saml_select')

    auth = build_saml_auth(request, organization)
    redirect_url = auth.login(
        return_to=request.build_absolute_uri('/dashboard/'),
    )
    return redirect(redirect_url)


@csrf_exempt
@require_http_methods(['POST'])
def saml_acs(request, organization_slug):
    organization = get_saml_organization(organization_slug)
    if organization is None:
        return HttpResponseForbidden('SAML is not configured for that organization.')
    if not organization.saml_sso_url:
        return HttpResponseForbidden('Missing SAML identity provider configuration.')

    auth = build_saml_auth(request, organization)
    auth.process_response()

    errors = auth.get_errors()
    errors.extend(validate_saml_response(auth, organization, build_saml_request_data(request)))
    if errors:
        _saml_telemetry('saml_login_failed', organization, request, level='warning', errors=errors)
        messages.error(
            request,
            'SAML authentication failed: ' + '; '.join(errors),
        )
        return redirect('login')

    if not auth.is_authenticated():
        _saml_telemetry('saml_login_failed', organization, request, level='warning', errors=['auth_not_authenticated'])
        messages.error(request, 'SAML authentication did not complete.')
        return redirect('login')

    if not assertion_is_fresh(auth):
        _saml_telemetry('saml_login_failed', organization, request, level='warning', errors=['assertion_expired'])
        messages.error(request, 'SAML assertion has expired.')
        return redirect('login')

    identity = extract_saml_identity(auth)
    if not identity['email']:
        _saml_telemetry('saml_login_failed', organization, request, level='warning', errors=['missing_email'])
        messages.error(request, 'SAML response did not include an email address.')
        return redirect('login')

    membership, profile = provision_saml_membership(
        organization,
        email=identity['email'],
        first_name=identity['first_name'],
        last_name=identity['last_name'],
        role=identity['role'],
    )

    if organization.require_mfa and not profile.mfa_enabled:
        profile.mfa_enabled = True
        profile.mfa_verified_at = timezone.now()
        profile.save(update_fields=['mfa_enabled', 'mfa_verified_at', 'updated_at'])

    auth_login(request, membership.user, backend='django.contrib.auth.backends.ModelBackend')
    log_action(
        membership.user,
        AuditLog.Action.LOGIN,
        'OrganizationMembership',
        object_id=membership.id,
        object_repr=str(membership),
        changes={
            'event': 'saml_login',
            'organization_id': organization.id,
            'email': identity['email'],
        },
        request=request,
    )
    messages.success(request, f'Signed in with SAML as {membership.user.get_full_name() or membership.user.username}.')
    _saml_telemetry(
        'saml_login_succeeded',
        organization,
        request,
        email=identity['email'],
        role=identity['role'],
        session_index=auth.get_session_index(),
    )
    return redirect('dashboard')


@require_GET
def saml_logout(request, organization_slug):
    organization = get_saml_organization(organization_slug)
    if organization is None:
        _saml_telemetry('saml_logout_fallback', None, request, level='warning', errors=['organization_not_found'])
        auth_logout(request)
        return redirect('login')

    try:
        auth = build_saml_auth(request, organization)
        return_to = request.build_absolute_uri('/login/')
        redirect_url = auth.logout(return_to=return_to)
        auth_logout(request)
        _saml_telemetry(
            'saml_logout_initiated',
            organization,
            request,
            name_id=auth.get_nameid(),
            session_index=auth.get_session_index(),
        )
        return redirect(redirect_url)
    except Exception as exc:
        logger.exception('saml_logout_failed')
        _saml_telemetry('saml_logout_failed', organization, request, level='error', error=str(exc))
        messages.error(request, 'SAML logout could not be completed. You have been signed out locally.')
        auth_logout(request)
        return redirect('login')


@require_GET
def saml_metadata(request, organization_slug):
    organization = get_saml_organization(organization_slug)
    if organization is None:
        return HttpResponseForbidden('SAML is not configured for that organization.')
    if not organization.saml_sso_url:
        return HttpResponseForbidden('Missing SAML identity provider configuration.')

    metadata = get_saml_metadata_xml(request, organization)
    response = HttpResponse(metadata, content_type='application/xml')
    response['Content-Disposition'] = f'inline; filename="saml-metadata-{organization.slug}.xml"'
    _saml_telemetry('saml_metadata_served', organization, request)
    return response
