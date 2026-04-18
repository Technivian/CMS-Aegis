
"""
API views for Ironclad-mode functionality
"""
import json
import logging
import secrets

from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from contracts.services.repository import BulkUpdateValidationError, get_repository_service
from contracts.services.salesforce import (
    CANONICAL_CONTRACT_FIELDS,
    build_salesforce_authorize_url,
    create_salesforce_sync_run,
    decrypt_salesforce_token,
    default_field_map_records,
    encrypt_salesforce_token,
    exchange_salesforce_code_for_tokens,
    get_effective_field_map_records,
    ingest_salesforce_records,
    SalesforceSyncError,
    refresh_salesforce_access_token,
    salesforce_oauth_is_configured,
    sync_salesforce_connection,
)
from contracts.domain.contracts import ListParams
from contracts.middleware import log_action
from contracts.permissions import can_manage_organization
from contracts.tenancy import get_user_organization
from contracts.models import (
    Contract,
    OrganizationAPIToken,
    OrganizationContractFieldMap,
    Organization,
    OrganizationMembership,
    SalesforceOrganizationConnection,
    OrganizationSCIMGroup,
    OrganizationSCIMGroupMembership,
    SalesforceSyncRun,
    UserProfile,
    AuditLog,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def _error_response(request, message, status):
    return JsonResponse(
        {
            'error': message,
            'request_id': getattr(request, 'request_id', None),
        },
        status=status,
    )


def _scim_response(payload, status=200):
    response = JsonResponse(payload, status=status)
    response['Content-Type'] = 'application/scim+json'
    return response


def _api_version_response(payload, status=200, version='1'):
    response = JsonResponse(payload, status=status)
    response['X-API-Version'] = str(version)
    return response


def _scim_user_payload(membership):
    profile, _ = UserProfile.objects.get_or_create(user=membership.user)
    return {
        'schemas': ['urn:ietf:params:scim:schemas:core:2.0:User'],
        'id': str(membership.id),
        'userName': membership.user.email or membership.user.username,
        'name': {
            'givenName': membership.user.first_name or '',
            'familyName': membership.user.last_name or '',
        },
        'displayName': membership.user.get_full_name() or membership.user.username,
        'active': membership.is_active,
        'emails': [
            {
                'value': membership.user.email or '',
                'primary': True,
            }
        ],
        'externalId': membership.scim_external_id or str(membership.user.id),
        'meta': {
            'resourceType': 'User',
        },
        'urn:ietf:params:scim:schemas:extension:enterprise:2.0:User': {
            'role': membership.role,
            'mfaEnabled': profile.mfa_enabled,
            'sessionRevocationCounter': profile.session_revocation_counter,
        },
    }


def _scim_error(message, status, scim_type=None):
    payload = {'detail': message, 'status': str(status)}
    if scim_type:
        payload['scimType'] = scim_type
    return _scim_response(payload, status=status)


def _scim_value_to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {'true', '1', 'yes', 'on'}


def _scim_first_non_empty_value(value):
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                candidate = entry.get('value')
            else:
                candidate = entry
            if candidate not in {None, ''}:
                return candidate
        return ''
    if isinstance(value, dict):
        candidate = value.get('value')
        return candidate if candidate not in {None, ''} else ''
    return value if value not in {None, ''} else ''


def _scim_paginated_list(queryset, request):
    total_results = queryset.count()
    try:
        start_index = max(int(request.GET.get('startIndex', 1)), 1)
    except (TypeError, ValueError):
        start_index = 1
    try:
        count = int(request.GET.get('count', total_results or 0))
    except (TypeError, ValueError):
        count = total_results or 0
    count = max(count, 0)
    zero_based_start = start_index - 1
    resources = list(queryset[zero_based_start:zero_based_start + count]) if count else []
    return total_results, start_index, count, resources


def _api_paginated_contracts(queryset, request):
    try:
        limit = int(request.GET.get('limit', 25))
    except (TypeError, ValueError):
        limit = 25
    try:
        offset = int(request.GET.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    limit = max(0, min(limit, 100))
    offset = max(0, offset)
    total_count = queryset.count()
    resources = list(queryset[offset:offset + limit]) if limit else []
    return {
        'total_count': total_count,
        'limit': limit,
        'offset': offset,
        'next_offset': offset + limit if offset + limit < total_count else None,
        'previous_offset': max(0, offset - limit) if offset > 0 and limit else None,
        'resources': resources,
    }


def _resolve_scim_organization(request):
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return None, None
    token = auth_header.split(' ', 1)[1].strip()
    if not token:
        return None, None
    for organization in Organization.objects.filter(scim_enabled=True).only('id', 'scim_token_hash', 'scim_token_last4', 'name', 'slug'):
        if organization.matches_scim_token(token):
            return organization, token
    return None, token


def _resolve_api_organization(request, required_scope='contracts:read'):
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return None, None, None
    token = auth_header.split(' ', 1)[1].strip()
    if not token:
        return None, None, None
    for api_token in OrganizationAPIToken.objects.select_related('organization').filter(is_active=True, organization__is_active=True):
        if api_token.matches_token(token):
            if not api_token.has_scope(required_scope):
                return None, token, api_token
            api_token.last_used_at = timezone.now()
            api_token.save(update_fields=['last_used_at', 'updated_at'])
            return api_token.organization, token, api_token
    return None, token, None


def _scim_member_queryset(organization):
    return (
        OrganizationMembership.objects
        .filter(organization=organization)
        .select_related('user')
        .order_by('user__username')
    )


def _scim_group_queryset(organization):
    return (
        OrganizationSCIMGroup.objects
        .filter(organization=organization)
        .prefetch_related('members__user', 'nested_groups')
        .order_by('display_name')
    )


def _scim_role_priority(role):
    priorities = {
        OrganizationMembership.Role.MEMBER: 0,
        OrganizationMembership.Role.ADMIN: 1,
        OrganizationMembership.Role.OWNER: 2,
    }
    return priorities.get(role, 0)


def _scim_normalize_role(role):
    if not role:
        return OrganizationMembership.Role.MEMBER
    role_value = str(role).strip().upper()
    if role_value == OrganizationMembership.Role.OWNER:
        return OrganizationMembership.Role.OWNER
    if role_value == OrganizationMembership.Role.ADMIN:
        return OrganizationMembership.Role.ADMIN
    return OrganizationMembership.Role.MEMBER


def _scim_parse_filter(filter_value):
    if not filter_value:
        return None, None
    parts = str(filter_value).strip().split(' ', 2)
    if len(parts) != 3:
        return None, None
    field, operator, raw_value = parts
    if operator.lower() != 'eq':
        return None, None
    value = raw_value.strip().strip('"').strip("'")
    return field, value


def _scim_filter_memberships(organization, filter_value):
    field, value = _scim_parse_filter(filter_value)
    queryset = _scim_member_queryset(organization)
    if field is None:
        return queryset
    field_lower = field.lower()
    if field_lower in {'username', 'usernamevalue', 'username.value', 'usernamevalue.value'}:
        return queryset.filter(Q(user__email__iexact=value) | Q(user__username__iexact=value))
    if field_lower == 'externalid':
        return queryset.filter(scim_external_id__iexact=value)
    if field_lower in {'emails.value', 'email'}:
        return queryset.filter(user__email__iexact=value)
    if field_lower in {'name.givenname', 'givenname'}:
        return queryset.filter(user__first_name__icontains=value)
    if field_lower in {'name.familyname', 'familyname'}:
        return queryset.filter(user__last_name__icontains=value)
    if field_lower == 'displayname':
        return queryset.filter(
            Q(user__first_name__icontains=value)
            | Q(user__last_name__icontains=value)
            | Q(user__username__icontains=value)
            | Q(user__email__iexact=value)
        ).distinct()
    if field_lower == 'active':
        return queryset.filter(is_active=str(value).lower() in {'true', '1'})
    return queryset


def _scim_filter_groups(organization, filter_value):
    field, value = _scim_parse_filter(filter_value)
    queryset = _scim_group_queryset(organization)
    if field is None:
        return queryset
    field_lower = field.lower()
    if field_lower == 'displayname':
        return queryset.filter(display_name__icontains=value)
    if field_lower == 'externalid':
        return queryset.filter(external_id__iexact=value)
    if field_lower == 'active':
        return queryset.filter(is_active=str(value).lower() in {'true', '1'})
    return queryset


def _upsert_scim_member(organization, user_name, first_name='', last_name='', active=True, role=None, external_id=''):
    email = (user_name or '').strip().lower()
    if not email:
        raise ValueError('userName is required')
    external_id = (external_id or '').strip()
    membership = None
    if external_id:
        membership = (
            OrganizationMembership.objects
            .select_related('user')
            .filter(organization=organization, scim_external_id__iexact=external_id)
            .first()
        )
    user = membership.user if membership else User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User.objects.create_user(
            username=email.split('@', 1)[0] or email,
            email=email,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            is_active=active,
        )
    else:
        updates = []
        if user.username != (email.split('@', 1)[0] or email):
            user.username = email.split('@', 1)[0] or email
            updates.append('username')
        if first_name.strip() and user.first_name != first_name.strip():
            user.first_name = first_name.strip()
            updates.append('first_name')
        if last_name.strip() and user.last_name != last_name.strip():
            user.last_name = last_name.strip()
            updates.append('last_name')
        if user.is_active != active:
            user.is_active = active
            updates.append('is_active')
        if updates:
            user.save(update_fields=updates)

    if membership is None:
        membership, _ = OrganizationMembership.objects.get_or_create(
            organization=organization,
            user=user,
            defaults={
                'role': role or OrganizationMembership.Role.MEMBER,
                'is_active': active,
                'scim_external_id': external_id,
            },
        )
    updates = []
    if membership.user_id != user.id:
        membership.user = user
        updates.append('user')
    if external_id and membership.scim_external_id != external_id:
        membership.scim_external_id = external_id
        updates.append('scim_external_id')
    if role and membership.role != role:
        membership.role = role
        updates.append('role')
    if membership.is_active != active:
        membership.is_active = active
        updates.append('is_active')
    if updates:
        membership.save(update_fields=updates)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return membership, profile


def _apply_scim_user_updates(membership, data):
    user = membership.user
    name = data.get('name') or {}
    enterprise = data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User') or {}
    active = data.get('active')
    updates = []
    membership_updates = []

    user_name = (data.get('userName') or '').strip().lower()
    if user_name and user.email != user_name:
        user.email = user_name
        user.username = user_name.split('@', 1)[0] or user_name
        updates.extend(['email', 'username'])
    if name.get('givenName') is not None and user.first_name != (name.get('givenName') or '').strip():
        user.first_name = (name.get('givenName') or '').strip()
        updates.append('first_name')
    if name.get('familyName') is not None and user.last_name != (name.get('familyName') or '').strip():
        user.last_name = (name.get('familyName') or '').strip()
        updates.append('last_name')
    if active is not None and user.is_active != _scim_value_to_bool(active):
        user.is_active = _scim_value_to_bool(active)
        updates.append('is_active')
    external_id = data.get('externalId')
    if external_id is not None:
        external_id = str(external_id).strip()
        if membership.scim_external_id != external_id:
            membership.scim_external_id = external_id
            membership_updates.append('scim_external_id')
    if updates:
        user.save(update_fields=list(dict.fromkeys(updates)))

    if active is not None and membership.is_active != _scim_value_to_bool(active):
        membership.is_active = _scim_value_to_bool(active)
        membership_updates.append('is_active')
    role = enterprise.get('role')
    if role and membership.role != role:
        membership.role = role
        membership_updates.append('role')
    if membership_updates:
        membership.save(update_fields=membership_updates)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if enterprise.get('mfaEnabled') is not None or profile.mfa_enabled != _scim_value_to_bool(enterprise.get('mfaEnabled', profile.mfa_enabled), profile.mfa_enabled):
        profile.mfa_enabled = _scim_value_to_bool(enterprise.get('mfaEnabled', profile.mfa_enabled), profile.mfa_enabled)
        if profile.mfa_enabled:
            profile.mfa_verified_at = timezone.now()
        profile.save(update_fields=['mfa_enabled', 'mfa_verified_at', 'updated_at'])

    return membership


def _scim_group_payload(group):
    members = []
    for membership in group.members.select_related('user').order_by('user__username'):
        members.append({
            'value': str(membership.id),
            'type': 'User',
            'display': membership.user.get_full_name() or membership.user.username,
        })
    for nested_group in group.nested_groups.order_by('display_name'):
        members.append({
            'value': str(nested_group.id),
            'type': 'Group',
            'display': nested_group.display_name,
        })

    return {
        'schemas': ['urn:ietf:params:scim:schemas:core:2.0:Group'],
        'id': str(group.id),
        'displayName': group.display_name,
        'externalId': group.external_id or '',
        'active': group.is_active,
        'members': members,
        'meta': {
            'resourceType': 'Group',
        },
        'urn:ietf:params:scim:schemas:extension:enterprise:2.0:Group': {
            'role': group.role,
        },
    }


def _scim_group_membership_contains(group, membership_id, seen=None):
    seen = seen or set()
    if group.id in seen:
        return False
    seen.add(group.id)
    if group.members.filter(id=membership_id).exists():
        return True
    for nested_group in group.nested_groups.filter(is_active=True):
        if _scim_group_membership_contains(nested_group, membership_id, seen):
            return True
    return False


def _reconcile_scim_group_membership_role(organization, membership):
    target_role = OrganizationMembership.Role.MEMBER
    for group in _scim_group_queryset(organization).filter(is_active=True):
        if _scim_group_membership_contains(group, membership.id):
            group_role = _scim_normalize_role(group.role)
            if _scim_role_priority(group_role) > _scim_role_priority(target_role):
                target_role = group_role
    if membership.role != target_role:
        membership.role = target_role
        membership.save(update_fields=['role'])


def _reconcile_all_scim_group_memberships(organization):
    for membership in _scim_member_queryset(organization):
        _reconcile_scim_group_membership_role(organization, membership)


def _resolve_scim_group_reference(organization, value):
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    if value.isdigit():
        return OrganizationSCIMGroup.objects.filter(organization=organization, id=int(value)).first()
    return OrganizationSCIMGroup.objects.filter(
        organization=organization,
        display_name__iexact=value,
    ).first() or OrganizationSCIMGroup.objects.filter(
        organization=organization,
        external_id__iexact=value,
    ).first()


def _sync_scim_group_relations(group, member_entries):
    desired_memberships = set()
    desired_nested_groups = set()
    for entry in member_entries or []:
        if not isinstance(entry, dict):
            continue
        member_type = str(entry.get('type') or 'User').strip().lower()
        member_value = entry.get('value')
        if member_type == 'group':
            nested_group = _resolve_scim_group_reference(group.organization, member_value)
            if nested_group and nested_group.id != group.id:
                desired_nested_groups.add(nested_group.id)
            continue
        if member_value is not None:
            desired_memberships.add(str(member_value))

    current_memberships = set(str(member.id) for member in group.members.all())
    current_nested_groups = set(str(nested_group.id) for nested_group in group.nested_groups.all())

    for membership_id in current_memberships - desired_memberships:
        membership = OrganizationMembership.objects.filter(id=membership_id, organization=group.organization).first()
        if membership:
            group.members.remove(membership)
            _reconcile_scim_group_membership_role(group.organization, membership)

    for membership_id in desired_memberships - current_memberships:
        membership = OrganizationMembership.objects.filter(id=membership_id, organization=group.organization).first()
        if membership:
            group.members.add(membership)

    for nested_group_id in current_nested_groups - desired_nested_groups:
        nested_group = OrganizationSCIMGroup.objects.filter(id=nested_group_id, organization=group.organization).first()
        if nested_group:
            group.nested_groups.remove(nested_group)

    for nested_group_id in desired_nested_groups - current_nested_groups:
        nested_group = OrganizationSCIMGroup.objects.filter(id=nested_group_id, organization=group.organization).first()
        if nested_group:
            group.nested_groups.add(nested_group)

    for membership_id in desired_memberships | current_memberships:
        membership = OrganizationMembership.objects.filter(id=membership_id, organization=group.organization).first()
        if membership:
            _reconcile_scim_group_membership_role(group.organization, membership)
    _reconcile_all_scim_group_memberships(group.organization)


def _upsert_scim_group(organization, display_name, external_id='', role=None, active=True, member_entries=None):
    display_name = (display_name or '').strip()
    if not display_name:
        raise ValueError('displayName is required')

    group = None
    external_id = (external_id or '').strip()
    if external_id:
        group = OrganizationSCIMGroup.objects.filter(organization=organization, external_id=external_id).first()
    if group is None:
        group = OrganizationSCIMGroup.objects.filter(organization=organization, display_name__iexact=display_name).first()
    if group is None:
        group = OrganizationSCIMGroup.objects.create(
            organization=organization,
            external_id=external_id,
            display_name=display_name,
            role=_scim_normalize_role(role),
            is_active=active,
        )
    else:
        updates = []
        if group.display_name != display_name:
            group.display_name = display_name
            updates.append('display_name')
        if external_id and group.external_id != external_id:
            group.external_id = external_id
            updates.append('external_id')
        normalized_role = _scim_normalize_role(role or group.role)
        if group.role != normalized_role:
            group.role = normalized_role
            updates.append('role')
        if group.is_active != active:
            group.is_active = active
            updates.append('is_active')
        if updates:
            group.save(update_fields=updates)

    if member_entries is not None:
        _sync_scim_group_relations(group, member_entries)
    return group


@login_required
@require_http_methods(["GET"])
def contracts_api(request):
    """
    API endpoint for listing contracts with filtering and pagination
    Used by Ironclad repository UI
    """
    try:
        # Get service
        service = get_repository_service(request.user, use_mock=False)
        
        # Parse filters from request
        params = ListParams(
            q=request.GET.get('q', ''),
            status=[s for s in request.GET.getlist('status') if s],
            contract_type=[t for t in request.GET.getlist('contract_type') if t],
            sort=request.GET.get('sort', 'updated_desc'),
            page=int(request.GET.get('page', 1)),
            page_size=int(request.GET.get('page_size', 25))
        )
        
        # Get results
        result = service.list(params)
        
        return JsonResponse(result.to_dict())
        
    except Exception:
        logger.exception('contracts_api_failed')
        return _error_response(request, 'An unexpected error occurred.', 500)


@csrf_exempt
@require_http_methods(["GET"])
def contracts_api_v1(request):
    organization, token, api_token = _resolve_api_organization(request, required_scope='contracts:read')
    if organization is None:
        return _error_response(request, 'Missing or invalid API bearer token.', 401)

    try:
        service = get_repository_service(request.user, use_mock=False)
        service.organization = organization
        try:
            page_size = int(request.GET.get('limit', request.GET.get('page_size', 25)) or 25)
        except (TypeError, ValueError):
            page_size = 25
        try:
            page = int(request.GET.get('page', 1) or 1)
        except (TypeError, ValueError):
            page = 1
        params = ListParams(
            q=request.GET.get('q', ''),
            status=[s for s in request.GET.getlist('status') if s],
            contract_type=[t for t in request.GET.getlist('contract_type') if t],
            sort=request.GET.get('sort', 'updated_desc'),
            page=max(1, page),
            page_size=max(1, min(page_size, 100)),
        )
        result = service.list(params)
        response = _api_version_response({
            'meta': {
                'version': '1',
                'organization': organization.slug,
                'token_label': api_token.label if api_token else '',
                'token_scopes': api_token.scopes if api_token else [],
                'limit': params.page_size,
                'offset': max(0, int(request.GET.get('offset', 0) or 0)),
                'total_count': result.total_count,
            },
            'data': result.to_dict(),
        })
        return response
    except Exception:
        logger.exception('contracts_api_v1_failed')
        return _error_response(request, 'An unexpected error occurred.', 500)

@login_required
@require_http_methods(["GET"])
def contract_detail_api(request, contract_id):
    """Get single contract details"""
    try:
        service = get_repository_service(request.user, use_mock=False)
        contract = service.get_by_id(contract_id)
        
        if not contract:
            return JsonResponse({'error': 'Contract not found'}, status=404)
            
        return JsonResponse(contract.to_dict())
        
    except Exception:
        logger.exception('contract_detail_api_failed')
        return _error_response(request, 'An unexpected error occurred.', 500)


@csrf_exempt
@require_http_methods(["GET"])
def contract_detail_api_v1(request, contract_id):
    organization, token, api_token = _resolve_api_organization(request, required_scope='contracts:read')
    if organization is None:
        return _error_response(request, 'Missing or invalid API bearer token.', 401)

    try:
        service = get_repository_service(request.user, use_mock=False)
        service.organization = organization
        contract = service.get_by_id(contract_id)
        if not contract:
            return _error_response(request, 'Contract not found', 404)
        response = _api_version_response({
            'meta': {
                'version': '1',
                'organization': organization.slug,
                'token_label': api_token.label if api_token else '',
                'token_scopes': api_token.scopes if api_token else [],
            },
            'data': contract.to_dict(),
        })
        return response
    except Exception:
        logger.exception('contract_detail_api_v1_failed')
        return _error_response(request, 'An unexpected error occurred.', 500)

@login_required
@require_http_methods(["POST"])
def contracts_bulk_update_api(request):
    """Bulk update contracts"""
    try:
        data = json.loads(request.body)
        contract_ids = data.get('contract_ids', [])
        updates = data.get('updates', {})

        if not isinstance(contract_ids, list) or not contract_ids:
            return _error_response(request, 'contract_ids must be a non-empty list', 400)

        try:
            normalized_contract_ids = [str(int(contract_id)) for contract_id in contract_ids]
        except (TypeError, ValueError):
            return _error_response(request, 'contract_ids must contain numeric IDs only', 400)

        service = get_repository_service(request.user, use_mock=False)
        result = service.bulk_update(normalized_contract_ids, updates)
        log_action(
            request.user,
            AuditLog.Action.UPDATE,
            'Contract',
            changes={
                'event': 'bulk_contract_update',
                'contract_ids': normalized_contract_ids,
                'updates': updates,
                'updated_count': result,
            },
            request=request,
        )

        return JsonResponse({'success': True, 'updated_count': result})
    except json.JSONDecodeError:
        return _error_response(request, 'Invalid JSON body', 400)
    except BulkUpdateValidationError as exc:
        return _error_response(request, str(exc), 400)
    except Exception:
        logger.exception('contracts_bulk_update_api_failed')
        return _error_response(request, 'An unexpected error occurred.', 500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def scim_users_api(request):
    organization, token = _resolve_scim_organization(request)
    if organization is None:
        return _scim_error('Missing or invalid SCIM bearer token.', 401)

    if request.method == 'GET':
        queryset = _scim_filter_memberships(organization, request.GET.get('filter', ''))
        total_results, start_index, items_per_page, memberships = _scim_paginated_list(queryset, request)
        resources = [_scim_user_payload(membership) for membership in memberships]
        return _scim_response({
            'schemas': ['urn:ietf:params:scim:api:messages:2.0:ListResponse'],
            'totalResults': total_results,
            'itemsPerPage': items_per_page,
            'startIndex': start_index,
            'Resources': resources,
        })

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _scim_error('Invalid JSON body.', 400, scim_type='invalidSyntax')

    if data.get('Operations'):
        return _scim_error(
            'SCIM POST create does not accept Operations; use PATCH on /Users/{id}.',
            400,
            scim_type='invalidSyntax',
        )

    user_name = data.get('userName') or ''
    name = data.get('name') or {}
    enterprise = data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User') or {}
    active = _scim_value_to_bool(data.get('active', True), True)
    role = enterprise.get('role') or OrganizationMembership.Role.MEMBER
    membership, profile = _upsert_scim_member(
        organization,
        user_name=user_name,
        first_name=name.get('givenName', ''),
        last_name=name.get('familyName', ''),
        active=active,
        role=role,
        external_id=data.get('externalId', ''),
    )
    profile.mfa_enabled = _scim_value_to_bool(enterprise.get('mfaEnabled', profile.mfa_enabled), profile.mfa_enabled)
    if profile.mfa_enabled:
        profile.mfa_verified_at = timezone.now()
    profile.save(update_fields=['mfa_enabled', 'mfa_verified_at', 'updated_at'])
    _apply_scim_user_updates(membership, data)
    log_action(
        None,
        AuditLog.Action.CREATE,
        'OrganizationMembership',
        object_id=membership.id,
        object_repr=str(membership),
        changes={
            'organization_id': organization.id,
            'event': 'scim_user_provisioned',
            'user_name': user_name,
            'active': active,
        },
    )
    return _scim_response(_scim_user_payload(membership), status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def scim_user_api(request, scim_id):
    organization, token = _resolve_scim_organization(request)
    if organization is None:
        return _scim_error('Missing or invalid SCIM bearer token.', 401)

    membership = get_object_or_404(OrganizationMembership, id=scim_id, organization=organization)

    if request.method == 'GET':
        return _scim_response(_scim_user_payload(membership))

    if request.method == 'DELETE':
        membership.is_active = False
        membership.save(update_fields=['is_active'])
        _reconcile_all_scim_group_memberships(organization)
        log_action(
            None,
            AuditLog.Action.DELETE,
            'OrganizationMembership',
            object_id=membership.id,
            object_repr=str(membership),
            changes={'organization_id': organization.id, 'event': 'scim_user_deprovisioned'},
        )
        return HttpResponse(status=204)

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _scim_error('Invalid JSON body.', 400, scim_type='invalidSyntax')

    operations = data.get('Operations') or []
    if operations:
        for operation in operations:
            op = (operation.get('op') or operation.get('operation') or '').lower()
            path = (operation.get('path') or '').lower()
            value = operation.get('value')
            if op not in {'add', 'replace'}:
                continue
            if path == 'active' and value is not None:
                membership.is_active = _scim_value_to_bool(value)
                membership.save(update_fields=['is_active'])
            elif path == 'externalid' and value is not None:
                membership.scim_external_id = str(value).strip()
                membership.save(update_fields=['scim_external_id'])
            elif path in {'username', 'usernamevalue'} and value:
                _apply_scim_user_updates(membership, {'userName': value})
            elif path in {'name', 'displayname'} and isinstance(value, dict):
                _apply_scim_user_updates(membership, {'name': value})
            elif path in {'name.givenname', 'givenname'}:
                _apply_scim_user_updates(membership, {'name': {'givenName': value}})
            elif path in {'name.familyname', 'familyname'}:
                _apply_scim_user_updates(membership, {'name': {'familyName': value}})
            elif path.startswith('emails') and isinstance(value, (list, dict, str)):
                first_email = _scim_first_non_empty_value(value)
                if first_email:
                    _apply_scim_user_updates(membership, {'userName': first_email})
            elif path == 'urn:ietf:params:scim:schemas:extension:enterprise:2.0:user' and isinstance(value, dict):
                _apply_scim_user_updates(membership, {'urn:ietf:params:scim:schemas:extension:enterprise:2.0:User': value})
        _apply_scim_user_updates(membership, data)
        _reconcile_scim_group_membership_role(organization, membership)
    else:
        active = data.get('active')
        updates = []
        if active is not None:
            new_active = _scim_value_to_bool(active)
            if membership.is_active != new_active:
                membership.is_active = new_active
                updates.append('is_active')
        enterprise = data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User') or {}
        if data.get('externalId') is not None:
            external_id = str(data.get('externalId')).strip()
            if membership.scim_external_id != external_id:
                membership.scim_external_id = external_id
                updates.append('scim_external_id')
        if enterprise.get('role') and enterprise['role'] != membership.role:
            membership.role = enterprise['role']
            updates.append('role')
        if updates:
            membership.save(update_fields=updates)
            _reconcile_scim_group_membership_role(organization, membership)
    return _scim_response(_scim_user_payload(membership))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def scim_groups_api(request):
    organization, token = _resolve_scim_organization(request)
    if organization is None:
        return _scim_error('Missing or invalid SCIM bearer token.', 401)

    if request.method == 'GET':
        queryset = _scim_filter_groups(organization, request.GET.get('filter', ''))
        total_results, start_index, items_per_page, groups = _scim_paginated_list(queryset, request)
        resources = [_scim_group_payload(group) for group in groups]
        return _scim_response({
            'schemas': ['urn:ietf:params:scim:api:messages:2.0:ListResponse'],
            'totalResults': total_results,
            'itemsPerPage': items_per_page,
            'startIndex': start_index,
            'Resources': resources,
        })

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _scim_error('Invalid JSON body.', 400, scim_type='invalidSyntax')

    enterprise = data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:Group') or {}
    member_entries = [member for member in data.get('members', []) if isinstance(member, dict)]
    active = _scim_value_to_bool(data.get('active', True), True)
    group = _upsert_scim_group(
        organization,
        display_name=data.get('displayName', ''),
        external_id=data.get('externalId', ''),
        role=enterprise.get('role'),
        active=active,
        member_entries=member_entries,
    )
    log_action(
        None,
        AuditLog.Action.CREATE,
        'OrganizationSCIMGroup',
        object_id=group.id,
        object_repr=str(group),
        changes={
            'organization_id': organization.id,
            'event': 'scim_group_provisioned',
            'display_name': group.display_name,
        },
    )
    return _scim_response(_scim_group_payload(group), status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def scim_group_api(request, scim_id):
    organization, token = _resolve_scim_organization(request)
    if organization is None:
        return _scim_error('Missing or invalid SCIM bearer token.', 401)

    group = get_object_or_404(OrganizationSCIMGroup, id=scim_id, organization=organization)

    if request.method == 'GET':
        return _scim_response(_scim_group_payload(group))

    if request.method == 'DELETE':
        group.is_active = False
        group.save(update_fields=['is_active'])
        for membership in list(group.members.all()):
            group.members.remove(membership)
        for nested_group in list(group.nested_groups.all()):
            group.nested_groups.remove(nested_group)
        _reconcile_all_scim_group_memberships(organization)
        log_action(
            None,
            AuditLog.Action.DELETE,
            'OrganizationSCIMGroup',
            object_id=group.id,
            object_repr=str(group),
            changes={'organization_id': organization.id, 'event': 'scim_group_deprovisioned'},
        )
        return HttpResponse(status=204)

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _scim_error('Invalid JSON body.', 400, scim_type='invalidSyntax')

    operations = data.get('Operations') or []
    changed = False
    if operations:
        for operation in operations:
            op = (operation.get('op') or operation.get('operation') or '').lower()
            path = (operation.get('path') or '').lower()
            value = operation.get('value')
            if path in {'displayname', 'externalid', 'active'} or not path:
                if 'displayName' in operation and group.display_name != operation['displayName']:
                    group.display_name = operation['displayName']
                    changed = True
                if 'externalId' in operation and group.external_id != operation['externalId']:
                    group.external_id = operation['externalId']
                    changed = True
                if 'active' in operation:
                    new_active = _scim_value_to_bool(operation['active'])
                    if group.is_active != new_active:
                        group.is_active = new_active
                        changed = True
            if path == 'members' or (op in {'add', 'replace'} and isinstance(value, dict) and 'members' in value):
                member_values = value if isinstance(value, list) else value.get('members', [])
                _sync_scim_group_relations(group, member_values)
                changed = True
    else:
        if 'displayName' in data and group.display_name != data['displayName']:
            group.display_name = data['displayName']
            changed = True
        if 'externalId' in data and group.external_id != data['externalId']:
            group.external_id = data['externalId']
            changed = True
        if 'active' in data:
            new_active = _scim_value_to_bool(data['active'])
            if group.is_active != new_active:
                group.is_active = new_active
                changed = True
        enterprise = data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:Group') or {}
        if enterprise.get('role'):
            normalized_role = _scim_normalize_role(enterprise['role'])
            if group.role != normalized_role:
                group.role = normalized_role
                changed = True
        if 'members' in data:
            _sync_scim_group_relations(group, data.get('members', []))
            changed = True

    if changed:
        group.save()
    return _scim_response(_scim_group_payload(group))


def _require_org_admin_for_salesforce(request):
    if not getattr(request.user, 'is_authenticated', False):
        return None, _error_response(request, 'Authentication required.', 401)
    organization = get_user_organization(request.user)
    if organization is None:
        return None, _error_response(request, 'No active organization context.', 403)
    if not can_manage_organization(request.user, organization):
        return None, _error_response(request, 'Only organization admins/owners can manage integrations.', 403)
    return organization, None


@login_required
@require_http_methods(["GET"])
def salesforce_connection_status_api(request):
    organization, error = _require_org_admin_for_salesforce(request)
    if error:
        return error

    connection = SalesforceOrganizationConnection.objects.filter(organization=organization).first()
    if connection and connection.refresh_token and connection.token_expired:
        try:
            refreshed = refresh_salesforce_access_token(decrypt_salesforce_token(connection.refresh_token))
            connection.access_token = encrypt_salesforce_token(refreshed.access_token)
            connection.instance_url = refreshed.instance_url or connection.instance_url
            connection.scope = refreshed.scope or connection.scope
            connection.token_expires_at = refreshed.token_expires_at
            if refreshed.refresh_token:
                connection.refresh_token = encrypt_salesforce_token(refreshed.refresh_token)
            connection.save(update_fields=['access_token', 'instance_url', 'scope', 'token_expires_at', 'updated_at'])
        except Exception:
            logger.exception('Salesforce token refresh failed for org_id=%s', organization.id)

    persisted_maps = get_effective_field_map_records(organization)
    return JsonResponse(
        {
            'configured': salesforce_oauth_is_configured(),
            'connected': bool(connection and connection.is_active and connection.access_token),
            'connection': (
                {
                    'instance_url': connection.instance_url,
                    'external_org_id': connection.external_org_id,
                    'scope': connection.scope,
                    'token_expires_at': connection.token_expires_at.isoformat() if connection.token_expires_at else None,
                    'updated_at': connection.updated_at.isoformat() if connection.updated_at else None,
                }
                if connection and connection.is_active
                else None
            ),
            'mapping_count': len(persisted_maps),
        }
    )


@login_required
@require_http_methods(["POST"])
def salesforce_oauth_start_api(request):
    organization, error = _require_org_admin_for_salesforce(request)
    if error:
        return error
    if not salesforce_oauth_is_configured():
        return _error_response(request, 'Salesforce OAuth is not configured.', 400)

    state = secrets.token_urlsafe(24)
    request.session['salesforce_oauth_state'] = state
    request.session['salesforce_oauth_org_id'] = organization.id
    authorize_url = build_salesforce_authorize_url(state)
    return JsonResponse({'authorize_url': authorize_url, 'state': state})


@login_required
@require_http_methods(["GET"])
def salesforce_oauth_callback_api(request):
    organization, error = _require_org_admin_for_salesforce(request)
    if error:
        return error
    if not salesforce_oauth_is_configured():
        return _error_response(request, 'Salesforce OAuth is not configured.', 400)

    state = request.GET.get('state', '').strip()
    code = request.GET.get('code', '').strip()
    expected_state = request.session.get('salesforce_oauth_state')
    expected_org_id = request.session.get('salesforce_oauth_org_id')
    if not state or state != expected_state or expected_org_id != organization.id:
        return _error_response(request, 'Invalid OAuth state.', 400)
    if not code:
        return _error_response(request, 'Missing Salesforce authorization code.', 400)

    try:
        token_data = exchange_salesforce_code_for_tokens(code)
    except Exception:
        logger.exception('Salesforce OAuth callback failed for org_id=%s', organization.id)
        return _error_response(request, 'Salesforce OAuth exchange failed.', 502)

    connection, _ = SalesforceOrganizationConnection.objects.get_or_create(
        organization=organization,
        defaults={'connected_by': request.user},
    )
    connection.connected_by = request.user
    connection.external_org_id = token_data.external_org_id
    connection.instance_url = token_data.instance_url
    connection.access_token = encrypt_salesforce_token(token_data.access_token)
    connection.refresh_token = (
        encrypt_salesforce_token(token_data.refresh_token) if token_data.refresh_token else connection.refresh_token
    )
    connection.scope = token_data.scope
    connection.token_expires_at = token_data.token_expires_at
    connection.is_active = True
    connection.save()

    request.session.pop('salesforce_oauth_state', None)
    request.session.pop('salesforce_oauth_org_id', None)
    return JsonResponse({'connected': True, 'instance_url': connection.instance_url, 'external_org_id': connection.external_org_id})


@login_required
@require_http_methods(["POST"])
def salesforce_disconnect_api(request):
    organization, error = _require_org_admin_for_salesforce(request)
    if error:
        return error
    connection = SalesforceOrganizationConnection.objects.filter(organization=organization).first()
    if not connection:
        return JsonResponse({'disconnected': True, 'message': 'No active Salesforce connection.'})

    connection.is_active = False
    connection.access_token = ''
    connection.refresh_token = ''
    connection.scope = ''
    connection.token_expires_at = None
    connection.save(update_fields=['is_active', 'access_token', 'refresh_token', 'scope', 'token_expires_at', 'updated_at'])
    return JsonResponse({'disconnected': True})


@login_required
@require_http_methods(["GET", "PUT"])
def salesforce_field_map_api(request):
    organization, error = _require_org_admin_for_salesforce(request)
    if error:
        return error

    if request.method == 'GET':
        persisted = list(
            OrganizationContractFieldMap.objects.filter(organization=organization, is_active=True)
            .values('canonical_field', 'salesforce_object', 'salesforce_field', 'is_required', 'transform_rule')
            .order_by('canonical_field')
        )
        mappings = persisted or default_field_map_records()
        return JsonResponse({'mappings': mappings, 'source': 'database' if persisted else 'default'})

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _error_response(request, 'Invalid JSON body.', 400)
    mappings = payload.get('mappings')
    if not isinstance(mappings, list) or not mappings:
        return _error_response(request, 'mappings must be a non-empty list.', 400)

    seen_fields = set()
    allowed_fields = set(CANONICAL_CONTRACT_FIELDS)
    normalized = []
    for item in mappings:
        if not isinstance(item, dict):
            return _error_response(request, 'Each mapping must be an object.', 400)
        canonical_field = str(item.get('canonical_field', '')).strip()
        salesforce_field = str(item.get('salesforce_field', '')).strip()
        salesforce_object = str(item.get('salesforce_object', '')).strip() or 'Opportunity'
        transform_rule = str(item.get('transform_rule', '')).strip()
        is_required = bool(item.get('is_required', False))
        if not canonical_field or not salesforce_field:
            return _error_response(request, 'canonical_field and salesforce_field are required.', 400)
        if canonical_field not in allowed_fields:
            return _error_response(request, f'Unsupported canonical_field: {canonical_field}', 400)
        if canonical_field in seen_fields:
            return _error_response(request, f'Duplicate canonical_field: {canonical_field}', 400)
        seen_fields.add(canonical_field)
        normalized.append(
            {
                'canonical_field': canonical_field,
                'salesforce_field': salesforce_field,
                'salesforce_object': salesforce_object,
                'transform_rule': transform_rule,
                'is_required': is_required,
            }
        )

    active_fields = [item['canonical_field'] for item in normalized]
    OrganizationContractFieldMap.objects.filter(organization=organization).exclude(canonical_field__in=active_fields).update(
        is_active=False,
        updated_by=request.user,
    )
    for item in normalized:
        mapping, _ = OrganizationContractFieldMap.objects.get_or_create(
            organization=organization,
            canonical_field=item['canonical_field'],
            defaults={'created_by': request.user},
        )
        mapping.salesforce_field = item['salesforce_field']
        mapping.salesforce_object = item['salesforce_object']
        mapping.transform_rule = item['transform_rule']
        mapping.is_required = item['is_required']
        mapping.is_active = True
        mapping.updated_by = request.user
        mapping.save()

    return JsonResponse({'updated': len(normalized)})


@login_required
@require_http_methods(["POST"])
def salesforce_ingest_preview_api(request):
    organization, error = _require_org_admin_for_salesforce(request)
    if error:
        return error

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _error_response(request, 'Invalid JSON body.', 400)

    records = payload.get('records')
    dry_run = bool(payload.get('dry_run', True))
    if not isinstance(records, list):
        return _error_response(request, 'records must be a list.', 400)

    summary = ingest_salesforce_records(organization, records, dry_run=dry_run)
    return JsonResponse({'summary': summary, 'dry_run': dry_run})


@login_required
@require_http_methods(["POST"])
def salesforce_sync_api(request):
    organization, error = _require_org_admin_for_salesforce(request)
    if error:
        return error

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return _error_response(request, 'Invalid JSON body.', 400)

    connection = SalesforceOrganizationConnection.objects.filter(organization=organization, is_active=True).first()
    if connection is None:
        return _error_response(request, 'No active Salesforce connection.', 400)

    dry_run = bool(payload.get('dry_run', False))
    limit = payload.get('limit', getattr(settings, 'SALESFORCE_SYNC_DEFAULT_LIMIT', 200))
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return _error_response(request, 'limit must be an integer.', 400)
    if limit <= 0 or limit > 2000:
        return _error_response(request, 'limit must be between 1 and 2000.', 400)

    try:
        run = create_salesforce_sync_run(
            organization=organization,
            connection=connection,
            trigger_source=SalesforceSyncRun.TriggerSource.API,
            dry_run=dry_run,
            limit=limit,
            triggered_by=request.user,
        )
    except SalesforceSyncError as exc:
        return _error_response(request, str(exc), 409)

    try:
        summary = sync_salesforce_connection(connection, dry_run=dry_run, limit=limit)
    except Exception:
        logger.exception('Salesforce sync failed for org_id=%s', organization.id)
        run.status = SalesforceSyncRun.Status.FAILED
        run.error_message = 'Salesforce sync failed.'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'error_message', 'completed_at'])
        return _error_response(request, 'Salesforce sync failed.', 502)

    run.status = SalesforceSyncRun.Status.SUCCESS
    run.source_object = str(summary.get('source_object', '') or '')
    run.fetched_records = int(summary.get('fetched_records', 0) or 0)
    run.created_count = int(summary.get('created', 0) or 0)
    run.updated_count = int(summary.get('updated', 0) or 0)
    run.skipped_count = int(summary.get('skipped', 0) or 0)
    run.error_count = len(summary.get('errors') or [])
    run.summary = summary
    run.completed_at = timezone.now()
    run.save(
        update_fields=[
            'status',
            'source_object',
            'fetched_records',
            'created_count',
            'updated_count',
            'skipped_count',
            'error_count',
            'summary',
            'completed_at',
        ]
    )
    return JsonResponse({'summary': summary, 'dry_run': dry_run})


@login_required
@require_http_methods(["GET"])
def salesforce_sync_runs_api(request):
    organization, error = _require_org_admin_for_salesforce(request)
    if error:
        return error

    limit = request.GET.get('limit', 20)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return _error_response(request, 'limit must be an integer.', 400)
    limit = max(1, min(limit, 100))

    runs = (
        SalesforceSyncRun.objects.filter(organization=organization)
        .select_related('triggered_by')
        .order_by('-started_at')[:limit]
    )
    payload = []
    for run in runs:
        payload.append(
            {
                'id': run.id,
                'status': run.status,
                'trigger_source': run.trigger_source,
                'dry_run': run.dry_run,
                'limit_applied': run.limit_applied,
                'source_object': run.source_object,
                'fetched_records': run.fetched_records,
                'created_count': run.created_count,
                'updated_count': run.updated_count,
                'skipped_count': run.skipped_count,
                'error_count': run.error_count,
                'error_message': run.error_message,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'completed_at': run.completed_at.isoformat() if run.completed_at else None,
                'triggered_by': run.triggered_by.username if run.triggered_by else None,
            }
        )
    return JsonResponse({'runs': payload})
