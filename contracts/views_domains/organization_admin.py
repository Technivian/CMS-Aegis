import csv
import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from contracts.forms import OrganizationIdentitySettingsForm, OrganizationInvitationForm
from contracts.middleware import log_action
from contracts.models import (
    AuditLog,
    Case,
    CaseMatter,
    Client,
    Deadline,
    Invoice,
    OrganizationInvitation,
    OrganizationMembership,
    RiskLog,
    SalesforceOrganizationConnection,
    SalesforceSyncRun,
    TimeEntry,
    WebhookDelivery,
)
from contracts.permissions import can_manage_organization, is_organization_owner
from contracts.services.executive_analytics import (
    build_executive_bottlenecks,
    build_executive_cycle_time_snapshot,
    build_executive_risk_trend,
    build_executive_saved_dashboards,
)
from contracts.session_security import revoke_user_sessions
from contracts.tenancy import get_user_organization, scope_queryset_for_organization
from contracts.view_support import get_scoped_queryset_for_request


def _build_invite_url(request, invitation):
    return request.build_absolute_uri(
        reverse('contracts:accept_organization_invite', kwargs={'token': invitation.token})
    )


def _send_invitation_email(invitation, invite_url):
    subject = f"You're invited to join {invitation.organization.name}"
    body = (
        f"You have been invited to join {invitation.organization.name} as {invitation.get_role_display()}.\n\n"
        f"Accept invitation: {invite_url}\n\n"
        'This link expires in 7 days.'
    )
    send_mail(
        subject=subject,
        message=body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        recipient_list=[invitation.email],
        fail_silently=False,
    )


@login_required
def organization_team(request):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('dashboard')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can manage team invites.')

    if request.method == 'POST':
        form = OrganizationInvitationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']

            existing_member = (
                OrganizationMembership.objects
                .filter(organization=organization, user__email__iexact=email, is_active=True)
                .select_related('user')
                .first()
            )
            if existing_member:
                messages.warning(request, f'{email} is already an active member of this organization.')
                return redirect('contracts:organization_team')

            pending_invitation = (
                OrganizationInvitation.objects
                .filter(
                    organization=organization,
                    email__iexact=email,
                    status=OrganizationInvitation.Status.PENDING,
                )
                .order_by('-created_at')
                .first()
            )
            if pending_invitation and (not pending_invitation.expires_at or pending_invitation.expires_at > timezone.now()):
                invite_url = _build_invite_url(request, pending_invitation)
                messages.info(request, f'An active invitation already exists for {email}: {invite_url}')
                return redirect('contracts:organization_team')

            invitation = OrganizationInvitation.objects.create(
                organization=organization,
                email=email,
                role=role,
                invited_by=request.user,
                expires_at=timezone.now() + timedelta(days=7),
            )
            log_action(
                request.user,
                AuditLog.Action.CREATE,
                'OrganizationInvitation',
                object_id=invitation.id,
                object_repr=invitation.email,
                changes={
                    'organization_id': organization.id,
                    'email': invitation.email,
                    'role': invitation.role,
                    'event': 'invite_created',
                },
                request=request,
            )
            invite_url = _build_invite_url(request, invitation)
            try:
                _send_invitation_email(invitation, invite_url)
                messages.success(request, f'Invitation created and emailed to {email}. Link: {invite_url}')
            except Exception:
                messages.warning(request, f'Invitation created for {email}, but email delivery failed. Share this link manually: {invite_url}')
            return redirect('contracts:organization_team')
    else:
        form = OrganizationInvitationForm()

    memberships = (
        OrganizationMembership.objects
        .filter(organization=organization, is_active=True)
        .select_related('user')
        .order_by('role', 'user__username')
    )
    inactive_memberships = (
        OrganizationMembership.objects
        .filter(organization=organization, is_active=False)
        .select_related('user')
        .order_by('user__username')
    )
    invitations = (
        OrganizationInvitation.objects
        .filter(organization=organization, status=OrganizationInvitation.Status.PENDING)
        .order_by('-created_at')
    )
    invitation_history = (
        OrganizationInvitation.objects
        .filter(organization=organization)
        .exclude(status=OrganizationInvitation.Status.PENDING)
        .select_related('invited_by', 'invited_user')
        .order_by('-created_at')[:20]
    )

    return render(request, 'contracts/organization_team.html', {
        'organization': organization,
        'memberships': memberships,
        'inactive_memberships': inactive_memberships,
        'invitations': invitations,
        'invitation_history': invitation_history,
        'invite_form': form,
        'is_owner': is_organization_owner(request.user, organization),
        'current_user_id': request.user.id,
    })


@login_required
@require_POST
def revoke_organization_invite(request, invite_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Insufficient permissions.')

    invitation = get_object_or_404(OrganizationInvitation, id=invite_id, organization=organization)
    if invitation.status == OrganizationInvitation.Status.PENDING:
        invitation.status = OrganizationInvitation.Status.REVOKED
        invitation.save(update_fields=['status'])
        log_action(
            request.user,
            AuditLog.Action.REJECT,
            'OrganizationInvitation',
            object_id=invitation.id,
            object_repr=invitation.email,
            changes={'organization_id': organization.id, 'event': 'invite_revoked'},
            request=request,
        )
        messages.success(request, f'Invitation for {invitation.email} was revoked.')
    else:
        messages.info(request, 'Only pending invitations can be revoked.')
    return redirect('contracts:organization_team')


@login_required
@require_POST
def resend_organization_invite(request, invite_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Insufficient permissions.')

    invitation = get_object_or_404(OrganizationInvitation, id=invite_id, organization=organization)
    if invitation.status != OrganizationInvitation.Status.PENDING:
        messages.info(request, 'Only pending invitations can be resent.')
        return redirect('contracts:organization_team')

    invitation.status = OrganizationInvitation.Status.REVOKED
    invitation.save(update_fields=['status'])
    log_action(
        request.user,
        AuditLog.Action.REJECT,
        'OrganizationInvitation',
        object_id=invitation.id,
        object_repr=invitation.email,
        changes={'organization_id': organization.id, 'event': 'invite_superseded_for_resend'},
        request=request,
    )

    new_invitation = OrganizationInvitation.objects.create(
        organization=organization,
        email=invitation.email,
        role=invitation.role,
        invited_by=request.user,
        expires_at=timezone.now() + timedelta(days=7),
    )
    log_action(
        request.user,
        AuditLog.Action.CREATE,
        'OrganizationInvitation',
        object_id=new_invitation.id,
        object_repr=new_invitation.email,
        changes={'organization_id': organization.id, 'event': 'invite_resent', 'role': new_invitation.role},
        request=request,
    )
    invite_url = _build_invite_url(request, new_invitation)
    try:
        _send_invitation_email(new_invitation, invite_url)
        messages.success(request, f'Invitation resent to {new_invitation.email}.')
    except Exception:
        messages.warning(request, f'New invitation generated, but email delivery failed. Share this link manually: {invite_url}')
    return redirect('contracts:organization_team')


@login_required
@require_POST
def update_membership_role(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Insufficient permissions.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization, is_active=True)
    requested_role = request.POST.get('role')
    allowed_roles = {choice[0] for choice in OrganizationMembership.Role.choices}
    if requested_role not in allowed_roles:
        messages.error(request, 'Invalid role selection.')
        return redirect('contracts:organization_team')

    actor_is_owner = is_organization_owner(request.user, organization)
    if requested_role == OrganizationMembership.Role.OWNER and not actor_is_owner:
        messages.error(request, 'Only organization owners can assign the Owner role.')
        return redirect('contracts:organization_team')

    if membership.user_id == request.user.id and membership.role == OrganizationMembership.Role.OWNER and requested_role != OrganizationMembership.Role.OWNER:
        owner_count = OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
        ).count()
        if owner_count <= 1:
            messages.error(request, 'At least one active owner must remain in the organization.')
            return redirect('contracts:organization_team')

    membership.role = requested_role
    membership.save(update_fields=['role'])
    log_action(
        request.user,
        AuditLog.Action.UPDATE,
        'OrganizationMembership',
        object_id=membership.id,
        object_repr=str(membership),
        changes={'organization_id': organization.id, 'event': 'role_updated', 'new_role': requested_role},
        request=request,
    )
    messages.success(request, f'Updated role for {membership.user.email or membership.user.username}.')
    return redirect('contracts:organization_team')


@login_required
@require_POST
def deactivate_organization_member(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Insufficient permissions.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization, is_active=True)
    if membership.user_id == request.user.id:
        messages.error(request, 'You cannot deactivate your own membership.')
        return redirect('contracts:organization_team')

    if membership.role == OrganizationMembership.Role.OWNER:
        owner_count = OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
        ).count()
        if owner_count <= 1:
            messages.error(request, 'At least one active owner must remain in the organization.')
            return redirect('contracts:organization_team')

    membership.is_active = False
    membership.save(update_fields=['is_active'])
    log_action(
        request.user,
        AuditLog.Action.DELETE,
        'OrganizationMembership',
        object_id=membership.id,
        object_repr=str(membership),
        changes={'organization_id': organization.id, 'event': 'member_deactivated'},
        request=request,
    )
    messages.success(request, f'Deactivated membership for {membership.user.email or membership.user.username}.')
    return redirect('contracts:organization_team')


@login_required
@require_POST
def reactivate_organization_member(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Insufficient permissions.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization)
    if membership.is_active:
        messages.info(request, 'This membership is already active.')
        return redirect('contracts:organization_team')

    membership.is_active = True
    membership.save(update_fields=['is_active'])
    log_action(
        request.user,
        AuditLog.Action.UPDATE,
        'OrganizationMembership',
        object_id=membership.id,
        object_repr=str(membership),
        changes={'organization_id': organization.id, 'event': 'member_reactivated'},
        request=request,
    )
    messages.success(request, f'Reactivated membership for {membership.user.email or membership.user.username}.')
    return redirect('contracts:organization_team')


@login_required
@require_POST
def revoke_member_sessions(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Insufficient permissions.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization, is_active=True)
    if membership.user_id == request.user.id:
        messages.error(request, 'You cannot revoke your own sessions from here.')
        return redirect('contracts:organization_team')

    new_counter = revoke_user_sessions(membership.user)
    log_action(
        request.user,
        AuditLog.Action.UPDATE,
        'OrganizationMembership',
        object_id=membership.id,
        object_repr=str(membership),
        changes={
            'organization_id': organization.id,
            'event': 'member_sessions_revoked',
            'revocation_counter': new_counter,
        },
        request=request,
    )
    messages.success(request, f'Revoked active sessions for {membership.user.email or membership.user.username}.')
    return redirect('contracts:organization_team')


def _filter_organization_activity_logs(request, organization):
    logs = AuditLog.objects.select_related('user').filter(changes__organization_id=organization.id)
    action = request.GET.get('action', '').strip()
    model_name = request.GET.get('model', '').strip()
    start_date = parse_date((request.GET.get('start_date') or '').strip())
    end_date = parse_date((request.GET.get('end_date') or '').strip())

    if action:
        logs = logs.filter(action=action)
    if model_name:
        logs = logs.filter(model_name=model_name)
    if start_date:
        logs = logs.filter(timestamp__date__gte=start_date)
    if end_date:
        logs = logs.filter(timestamp__date__lte=end_date)

    return logs.order_by('-timestamp')


@login_required
def organization_activity(request):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('dashboard')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can view organization activity.')

    logs = _filter_organization_activity_logs(request, organization)
    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    query_params = request.GET.copy()
    query_params.pop('page', None)

    return render(request, 'contracts/organization_activity.html', {
        'organization': organization,
        'logs': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'query_string': query_params.urlencode(),
    })


@login_required
def organization_activity_export(request):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('dashboard')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can export organization activity.')

    logs = _filter_organization_activity_logs(request, organization)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="organization-activity-{organization.slug}-{date.today().isoformat()}.csv"'

    writer = csv.writer(response)
    writer.writerow(['timestamp', 'user', 'action', 'model_name', 'object_repr', 'event', 'ip_address'])
    for log in logs.iterator():
        event = (log.changes or {}).get('event', '')
        writer.writerow([
            log.timestamp.isoformat(),
            (log.user.get_full_name() or log.user.username) if log.user else 'System',
            log.action,
            log.model_name,
            log.object_repr,
            event,
            log.ip_address or '',
        ])

    return response


@login_required
def organization_identity_settings(request):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('settings_hub')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Only organization owners/admins can manage identity settings.')

    scim_token_preview = request.session.pop('organization_scim_token_preview', None)
    api_token_preview = request.session.pop('organization_api_token_preview', None)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        if action == 'rotate_scim_token':
            raw_token = organization.rotate_scim_token()
            request.session['organization_scim_token_preview'] = raw_token
            log_action(
                request.user,
                AuditLog.Action.UPDATE,
                'Organization',
                object_id=organization.id,
                object_repr=organization.name,
                changes={'event': 'scim_token_rotated', 'scim_enabled': True},
                request=request,
            )
            messages.success(request, 'SCIM token rotated. Copy it now; it will not be shown again.')
            return redirect('organization_identity_settings')
        if action == 'rotate_api_token':
            token_record, raw_token = organization.rotate_api_token(
                scopes=['contracts:read'],
                label='Contracts API token',
                created_by=request.user,
            )
            request.session['organization_api_token_preview'] = {
                'token': raw_token,
                'scopes': token_record.scopes,
                'label': token_record.label,
            }
            log_action(
                request.user,
                AuditLog.Action.UPDATE,
                'Organization',
                object_id=organization.id,
                object_repr=organization.name,
                changes={'event': 'api_token_rotated', 'scopes': token_record.scopes},
                request=request,
            )
            messages.success(request, 'API token rotated. Copy it now; it will not be shown again.')
            return redirect('organization_identity_settings')

        form = OrganizationIdentitySettingsForm(request.POST, instance=organization)
        if form.is_valid():
            updated_org = form.save()
            log_action(
                request.user,
                AuditLog.Action.UPDATE,
                'Organization',
                object_id=updated_org.id,
                object_repr=updated_org.name,
                changes={
                    'event': 'organization_identity_settings_updated',
                    'identity_provider': updated_org.identity_provider,
                    'scim_enabled': updated_org.scim_enabled,
                },
                request=request,
            )
            messages.success(request, 'Identity settings updated.')
            return redirect('organization_identity_settings')
    else:
        form = OrganizationIdentitySettingsForm(instance=organization)

    salesforce_connection = SalesforceOrganizationConnection.objects.filter(organization=organization).first()
    salesforce_sync_runs = (
        SalesforceSyncRun.objects.filter(organization=organization)
        .select_related('triggered_by')
        .order_by('-started_at')[:10]
    )
    webhook_deliveries = (
        WebhookDelivery.objects.filter(organization=organization)
        .select_related('endpoint')
        .order_by('-created_at')[:10]
    )

    return render(request, 'contracts/organization_identity_settings.html', {
        'organization': organization,
        'form': form,
        'scim_token_preview': scim_token_preview,
        'api_token_preview': api_token_preview,
        'salesforce_connection': salesforce_connection,
        'salesforce_sync_runs': salesforce_sync_runs,
        'webhook_deliveries': webhook_deliveries,
        'saml_login_url': request.build_absolute_uri(
            reverse('saml_login', kwargs={'organization_slug': organization.slug})
        ),
        'saml_acs_url': request.build_absolute_uri(
            reverse('saml_acs', kwargs={'organization_slug': organization.slug})
        ),
        'saml_slo_url': request.build_absolute_uri(
            reverse('saml_logout', kwargs={'organization_slug': organization.slug})
        ),
        'saml_metadata_url': request.build_absolute_uri(
            reverse('saml_metadata', kwargs={'organization_slug': organization.slug})
        ),
        'api_v1_contracts_url': request.build_absolute_uri(reverse('contracts:contracts_api_v1')),
    })


@login_required
def accept_organization_invite(request, token):
    invitation = get_object_or_404(
        OrganizationInvitation.objects.select_related('organization'),
        token=token,
    )

    if invitation.status != OrganizationInvitation.Status.PENDING:
        messages.error(request, 'This invitation is no longer valid.')
        return redirect('dashboard')

    if invitation.expires_at and invitation.expires_at <= timezone.now():
        invitation.status = OrganizationInvitation.Status.EXPIRED
        invitation.save(update_fields=['status'])
        messages.error(request, 'This invitation has expired.')
        return redirect('dashboard')

    user_email = (request.user.email or '').strip().lower()
    if not user_email or user_email != invitation.email.lower():
        messages.error(request, f'This invitation is for {invitation.email}. Please sign in with that email.')
        return redirect('dashboard')

    membership, _ = OrganizationMembership.objects.get_or_create(
        organization=invitation.organization,
        user=request.user,
        defaults={
            'role': invitation.role,
            'is_active': True,
        },
    )
    if membership.role != invitation.role or not membership.is_active:
        membership.role = invitation.role
        membership.is_active = True
        membership.save(update_fields=['role', 'is_active'])

    invitation.status = OrganizationInvitation.Status.ACCEPTED
    invitation.invited_user = request.user
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=['status', 'invited_user', 'accepted_at'])
    log_action(
        request.user,
        AuditLog.Action.APPROVE,
        'OrganizationInvitation',
        object_id=invitation.id,
        object_repr=invitation.email,
        changes={
            'organization_id': invitation.organization_id,
            'event': 'invite_accepted',
            'role': invitation.role,
        },
        request=request,
    )

    request.session['active_organization_id'] = invitation.organization_id
    messages.success(request, f'You joined {invitation.organization.name}.')
    return redirect('dashboard')


@login_required
def reports_dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    org = get_user_organization(request.user)
    case_qs = get_scoped_queryset_for_request(request, Case)
    clients_qs = get_scoped_queryset_for_request(request, Client)
    case_matter_qs = get_scoped_queryset_for_request(request, CaseMatter)
    time_entries_qs = get_scoped_queryset_for_request(request, TimeEntry)
    invoices_qs = get_scoped_queryset_for_request(request, Invoice)
    if org:
        deadlines_qs = Deadline.objects.filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        )
        risks_qs = RiskLog.objects.filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        )
    else:
        deadlines_qs = Deadline.objects.none()
        risks_qs = RiskLog.objects.none()

    case_stats = case_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='ACTIVE')),
        total_value=Coalesce(Sum('value', filter=Q(value__isnull=False)), Decimal('0')),
    )
    total_cases = case_stats['total']
    active_cases = case_stats['active']
    total_case_value = case_stats['total_value']

    client_stats = clients_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='ACTIVE')),
    )
    total_clients = client_stats['total']
    active_clients = client_stats['active']

    case_matter_stats = case_matter_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='ACTIVE')),
    )
    total_case_matters = case_matter_stats['total']
    active_case_matters = case_matter_stats['active']

    monthly_hours = time_entries_qs.filter(
        date__gte=month_start
    ).aggregate(total=Sum('hours'))['total'] or Decimal('0')

    invoice_stats = invoices_qs.aggregate(
        yearly_revenue=Coalesce(Sum('total_amount', filter=Q(status='PAID', issue_date__gte=year_start)), Decimal('0')),
        outstanding=Coalesce(Sum('total_amount', filter=Q(status__in=['SENT', 'OVERDUE'])), Decimal('0')),
    )
    yearly_revenue = invoice_stats['yearly_revenue']
    outstanding = invoice_stats['outstanding']

    deadline_stats = deadlines_qs.aggregate(
        overdue=Count('id', filter=Q(is_completed=False, due_date__lt=today)),
        upcoming=Count('id', filter=Q(is_completed=False, due_date__gte=today, due_date__lte=today + timedelta(days=7))),
    )
    overdue_deadlines = deadline_stats['overdue']
    upcoming_deadlines = deadline_stats['upcoming']

    high_risks = risks_qs.filter(risk_level__in=['HIGH', 'CRITICAL']).count()

    cycle_snapshot = build_executive_cycle_time_snapshot(org) if org else {'average_days': None}
    executive_cycle_time_days = cycle_snapshot.get('average_days')
    executive_bottlenecks = build_executive_bottlenecks(org, limit=5) if org else []
    risk_trend_rows = build_executive_risk_trend(org, months=6) if org else []
    executive_risk_trend = []
    for item in risk_trend_rows:
        raw_month = str(item.get('month') or '')
        executive_risk_trend.append(
            {
                'month': raw_month[:7] if len(raw_month) >= 7 else raw_month,
                'total': item.get('high_or_critical_count', 0),
            }
        )
    executive_saved_dashboards = build_executive_saved_dashboards(org, limit=10) if org else []

    six_months_ago = today.replace(day=1) - timedelta(days=155)
    monthly_rows = (
        invoices_qs
        .filter(issue_date__gte=six_months_ago)
        .annotate(month=TruncMonth('issue_date'))
        .values('month')
        .annotate(total=Coalesce(Sum('total_amount'), Decimal('0')))
        .order_by('month')
    )
    monthly_map = {row['month'].strftime('%b %Y'): float(row['total']) for row in monthly_rows}
    monthly_billing = []
    for i in range(5, -1, -1):
        m = today.replace(day=1) - timedelta(days=30 * i)
        monthly_billing.append({'month': m.strftime('%b %Y'), 'total': monthly_map.get(m.strftime('%b %Y'), 0.0)})

    practice_areas = case_matter_qs.filter(status='ACTIVE').values('practice_area').annotate(
        count=Count('id')).order_by('-count')

    context = {
        'total_cases': total_cases,
        'active_cases': active_cases,
        'total_case_value': total_case_value,
        'total_clients': total_clients,
        'active_clients': active_clients,
        'total_case_matters': total_case_matters,
        'active_case_matters': active_case_matters,
        'case_workload_hours': monthly_hours,
        'yearly_revenue': yearly_revenue,
        'outstanding': outstanding,
        'overdue_deadlines': overdue_deadlines,
        'upcoming_deadlines': upcoming_deadlines,
        'high_risks': high_risks,
        'monthly_billing': json.dumps(monthly_billing),
        'practice_areas': list(practice_areas),
        'case_signals': {
            'overdue_deadlines': overdue_deadlines,
            'upcoming_deadlines': upcoming_deadlines,
            'high_risks': high_risks,
        },
        'total_contracts': total_cases,
        'active_contracts': active_cases,
        'total_contract_value': total_case_value,
        'total_matters': total_case_matters,
        'active_matters': active_case_matters,
        'monthly_hours': monthly_hours,
        'executive_cycle_time_days': executive_cycle_time_days,
        'executive_bottlenecks': executive_bottlenecks,
        'executive_risk_trend': json.dumps(executive_risk_trend),
        'executive_saved_dashboards': executive_saved_dashboards,
    }
    return render(request, 'contracts/reports_dashboard.html', context)


@login_required
def reports_export(request):
    organization = get_user_organization(request.user)
    if not organization:
        messages.error(request, 'No active organization found.')
        return redirect('dashboard')

    today = date.today()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    case_qs = get_scoped_queryset_for_request(request, Case)
    clients_qs = get_scoped_queryset_for_request(request, Client)
    case_matter_qs = get_scoped_queryset_for_request(request, CaseMatter)
    time_entries_qs = get_scoped_queryset_for_request(request, TimeEntry)
    invoices_qs = get_scoped_queryset_for_request(request, Invoice)
    deadlines_qs = Deadline.objects.filter(Q(contract__organization=organization) | Q(matter__organization=organization))
    risks_qs = RiskLog.objects.filter(Q(contract__organization=organization) | Q(matter__organization=organization))

    case_stats = case_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='ACTIVE')),
        total_value=Coalesce(Sum('value', filter=Q(value__isnull=False)), Decimal('0')),
    )
    client_stats = clients_qs.aggregate(total=Count('id'), active=Count('id', filter=Q(status='ACTIVE')))
    matter_stats = case_matter_qs.aggregate(total=Count('id'), active=Count('id', filter=Q(status='ACTIVE')))
    monthly_hours = time_entries_qs.filter(date__gte=month_start).aggregate(total=Sum('hours'))['total'] or Decimal('0')
    invoice_stats = invoices_qs.aggregate(
        yearly_revenue=Coalesce(Sum('total_amount', filter=Q(status='PAID', issue_date__gte=year_start)), Decimal('0')),
        outstanding=Coalesce(Sum('total_amount', filter=Q(status__in=['SENT', 'OVERDUE'])), Decimal('0')),
    )
    deadline_stats = deadlines_qs.aggregate(
        overdue=Count('id', filter=Q(is_completed=False, due_date__lt=today)),
        upcoming=Count('id', filter=Q(is_completed=False, due_date__gte=today, due_date__lte=today + timedelta(days=7))),
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="reports-export-{organization.slug}-{date.today().isoformat()}.csv"'
    writer = csv.writer(response)
    writer.writerow(['category', 'metric', 'value'])
    writer.writerow(['summary', 'total_clients', client_stats['total']])
    writer.writerow(['summary', 'active_clients', client_stats['active']])
    writer.writerow(['summary', 'total_matters', matter_stats['total']])
    writer.writerow(['summary', 'active_matters', matter_stats['active']])
    writer.writerow(['summary', 'total_contracts', case_stats['total']])
    writer.writerow(['summary', 'active_contracts', case_stats['active']])
    writer.writerow(['summary', 'total_contract_value', case_stats['total_value']])
    writer.writerow(['summary', 'case_workload_hours', monthly_hours])
    writer.writerow(['summary', 'yearly_revenue', invoice_stats['yearly_revenue']])
    writer.writerow(['summary', 'outstanding', invoice_stats['outstanding']])
    writer.writerow(['summary', 'overdue_deadlines', deadline_stats['overdue']])
    writer.writerow(['summary', 'upcoming_deadlines', deadline_stats['upcoming']])
    writer.writerow(['summary', 'high_risks', risks_qs.filter(risk_level__in=['HIGH', 'CRITICAL']).count()])
    for item in build_executive_bottlenecks(organization, limit=5):
        writer.writerow(['bottleneck', item['stage'], item['count']])
    for item in build_executive_risk_trend(organization, months=6):
        writer.writerow(['risk_trend', item['month'], item['high_or_critical_count']])
    for preset in build_executive_saved_dashboards(organization, limit=10):
        writer.writerow(['saved_dashboard', preset['name'], preset['updated_at'] or ''])
    return response
