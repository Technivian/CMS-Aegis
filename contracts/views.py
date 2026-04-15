from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, Q, Avg, Min
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.conf import settings
from django.db import models, connection, DatabaseError
from django.utils.dateparse import parse_date
from django.utils.cache import patch_cache_control
from django.utils.http import url_has_allowed_host_and_scheme
from datetime import timedelta, date
from decimal import Decimal
import csv
import logging

from .forms import (
    BudgetForm, CareTaskForm, BudgetExpenseForm,
    ClientForm, CareConfigurationForm, DocumentForm,
    DeadlineForm, UserProfileForm,
    RegistrationForm,
    OrganizationInvitationForm,
    MunicipalityConfigurationForm, RegionalConfigurationForm,
    CaseAssessmentForm, CaseIntakeProcessForm,
    TrustAccountForm, CareSignalForm, PlacementRequestForm,
    CaseOutcomeUpdateForm,
)
from .models import (
    Organization, OrganizationMembership, OrganizationInvitation,
    CareCase, PlacementRequest, CareTask, CareSignal,
    Workflow,
    CaseIntakeProcess, Budget, BudgetExpense,
    Client, CareConfiguration, Document, TrustAccount, ProviderProfile,
    Deadline, AuditLog, Notification, UserProfile, CaseAssessment,
    MunicipalityConfiguration, RegionalConfiguration, OutcomeReasonCode,
)
from .middleware import log_action
from .permissions import (
    CaseAction,
    can_access_case_action,
    can_manage_organization,
    is_organization_owner,
)
from .tenancy import get_user_organization, scope_queryset_for_organization, set_organization_on_instance
from config.feature_flags import is_feature_redesign_enabled
from .case_intelligence import evaluate_case_intelligence

logger = logging.getLogger(__name__)
User = get_user_model()


AUTO_INTAKE_TASKS = {
    CaseIntakeProcess.ProcessStatus.INTAKE: {
        'title': 'Intake afronden',
        'task_type': Deadline.TaskType.INTAKE_COMPLETE,
        'priority': Deadline.Priority.HIGH,
        'source': Deadline.GenerationSource.INTAKE,
    },
    CaseIntakeProcess.ProcessStatus.ASSESSMENT: {
        'title': 'Beoordeling uitvoeren',
        'task_type': Deadline.TaskType.ASSESSMENT_PERFORM,
        'priority': Deadline.Priority.HIGH,
        'source': Deadline.GenerationSource.ASSESSMENT,
    },
    CaseIntakeProcess.ProcessStatus.MATCHING: {
        'title': 'Match selecteren',
        'task_type': Deadline.TaskType.SELECT_MATCH,
        'priority': Deadline.Priority.URGENT,
        'source': Deadline.GenerationSource.MATCHING,
    },
}


def _resolve_deadline_case(deadline):
    if getattr(deadline, 'case_record_id', None):
        return deadline.case_record
    process = getattr(deadline, 'due_diligence_process', None)
    if process and getattr(process, 'contract_id', None):
        return process.case_record
    return None


def _resolve_signal_case(signal):
    if getattr(signal, 'case_record_id', None):
        return signal.case_record
    process = getattr(signal, 'due_diligence_process', None)
    if process and getattr(process, 'contract_id', None):
        return process.case_record
    return None


def _redirect_to_safe_next_or_default(request, fallback_url):
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(fallback_url)


def _case_detail_tab_href(intake_id, tab):
    return f"{reverse('careon:case_detail', kwargs={'pk': intake_id})}?tab={tab}"


def _reason_code_label(reason_code):
    if not reason_code or reason_code == OutcomeReasonCode.NONE:
        return ''
    return OutcomeReasonCode(reason_code).label


def _serialize_outcome_section(*, key, title, status_label, reason_code, notes, recorded_at, recorded_by, form):
    return {
        'key': key,
        'title': title,
        'status_label': status_label,
        'reason_label': _reason_code_label(reason_code),
        'notes': notes,
        'recorded_at': recorded_at,
        'recorded_by': recorded_by,
        'form': form,
    }


def _build_case_outcome_forms(intake, placement):
    sections = [
        _serialize_outcome_section(
            key='intake',
            title='Intake-uitkomst',
            status_label=intake.get_intake_outcome_status_display(),
            reason_code=intake.intake_outcome_reason_code,
            notes=intake.intake_outcome_notes,
            recorded_at=intake.intake_outcome_recorded_at,
            recorded_by=intake.intake_outcome_recorded_by,
            form=CaseOutcomeUpdateForm(
                initial={
                    'outcome_type': CaseOutcomeUpdateForm.OUTCOME_TYPE_INTAKE,
                    'status': intake.intake_outcome_status,
                    'reason_code': intake.intake_outcome_reason_code,
                    'notes': intake.intake_outcome_notes,
                }
            ),
        )
    ]

    if placement:
        sections.append(
            _serialize_outcome_section(
                key='provider_response',
                title='Reactie aanbieder',
                status_label=placement.get_provider_response_status_display(),
                reason_code=placement.provider_response_reason_code,
                notes=placement.provider_response_notes,
                recorded_at=placement.provider_response_recorded_at,
                recorded_by=placement.provider_response_recorded_by,
                form=CaseOutcomeUpdateForm(
                    initial={
                        'outcome_type': CaseOutcomeUpdateForm.OUTCOME_TYPE_PROVIDER_RESPONSE,
                        'status': placement.provider_response_status,
                        'reason_code': placement.provider_response_reason_code,
                        'notes': placement.provider_response_notes,
                    }
                ),
            )
        )
        sections.append(
            _serialize_outcome_section(
                key='placement_quality',
                title='Plaatsingskwaliteit',
                status_label=placement.get_placement_quality_status_display(),
                reason_code=placement.placement_quality_reason_code,
                notes=placement.placement_quality_notes,
                recorded_at=placement.placement_quality_recorded_at,
                recorded_by=placement.placement_quality_recorded_by,
                form=CaseOutcomeUpdateForm(
                    initial={
                        'outcome_type': CaseOutcomeUpdateForm.OUTCOME_TYPE_PLACEMENT_QUALITY,
                        'status': placement.placement_quality_status,
                        'reason_code': placement.placement_quality_reason_code,
                        'notes': placement.placement_quality_notes,
                    }
                ),
            )
        )

    return sections


def _get_outcome_timeline_events(intake):
    outcome_logs = AuditLog.objects.filter(
        model_name__in=['CaseIntakeProcess', 'PlacementRequest'],
        changes__event_category='outcome',
        changes__intake_id=intake.pk,
    ).select_related('user').order_by('-timestamp')[:12]

    events = []
    for item in outcome_logs:
        changes = item.changes or {}
        events.append(
            {
                'title': changes.get('title') or changes.get('outcome_type_label') or 'Uitkomstupdate',
                'status_label': changes.get('status_label') or changes.get('status') or '',
                'reason_label': changes.get('reason_label') or '',
                'note': changes.get('note') or '',
                'timestamp': item.timestamp,
                'user': item.user,
            }
        )
    return events


def _apply_case_outcome_update(*, intake, placement, outcome_type, status, reason_code, notes, user):
    recorded_at = timezone.now()

    if outcome_type == CaseOutcomeUpdateForm.OUTCOME_TYPE_INTAKE:
        intake.intake_outcome_status = status
        intake.intake_outcome_reason_code = reason_code
        intake.intake_outcome_notes = notes
        intake.intake_outcome_recorded_at = recorded_at
        intake.intake_outcome_recorded_by = user
        intake.save(
            update_fields=[
                'intake_outcome_status',
                'intake_outcome_reason_code',
                'intake_outcome_notes',
                'intake_outcome_recorded_at',
                'intake_outcome_recorded_by',
                'updated_at',
            ]
        )
        status_label = intake.get_intake_outcome_status_display()
        title = 'Intake-uitkomst bijgewerkt'
        log_action(
            user,
            AuditLog.Action.UPDATE,
            'CaseIntakeProcess',
            object_id=intake.id,
            object_repr=str(intake),
            changes={
                'event_category': 'outcome',
                'intake_id': intake.pk,
                'outcome_type': outcome_type,
                'outcome_type_label': 'Intake-uitkomst',
                'title': title,
                'status': status,
                'status_label': status_label,
                'reason_code': reason_code,
                'reason_label': _reason_code_label(reason_code),
                'note': notes,
                'recorded_at': recorded_at.isoformat(),
            },
        )
        return title, status_label

    if not placement:
        raise ValueError('Plaatsing ontbreekt voor deze uitkomstupdate.')

    if outcome_type == CaseOutcomeUpdateForm.OUTCOME_TYPE_PROVIDER_RESPONSE:
        placement.provider_response_status = status
        placement.provider_response_reason_code = reason_code
        placement.provider_response_notes = notes
        placement.provider_response_recorded_at = recorded_at
        placement.provider_response_recorded_by = user
        placement.save(
            update_fields=[
                'provider_response_status',
                'provider_response_reason_code',
                'provider_response_notes',
                'provider_response_recorded_at',
                'provider_response_recorded_by',
                'updated_at',
            ]
        )
        status_label = placement.get_provider_response_status_display()
        title = 'Reactie aanbieder bijgewerkt'
    else:
        placement.placement_quality_status = status
        placement.placement_quality_reason_code = reason_code
        placement.placement_quality_notes = notes
        placement.placement_quality_recorded_at = recorded_at
        placement.placement_quality_recorded_by = user
        placement.save(
            update_fields=[
                'placement_quality_status',
                'placement_quality_reason_code',
                'placement_quality_notes',
                'placement_quality_recorded_at',
                'placement_quality_recorded_by',
                'updated_at',
            ]
        )
        status_label = placement.get_placement_quality_status_display()
        title = 'Plaatsingskwaliteit bijgewerkt'

    log_action(
        user,
        AuditLog.Action.UPDATE,
        'PlacementRequest',
        object_id=placement.id,
        object_repr=str(placement),
        changes={
            'event_category': 'outcome',
            'intake_id': intake.pk,
            'placement_id': placement.pk,
            'outcome_type': outcome_type,
            'outcome_type_label': 'Reactie aanbieder' if outcome_type == CaseOutcomeUpdateForm.OUTCOME_TYPE_PROVIDER_RESPONSE else 'Plaatsingskwaliteit',
            'title': title,
            'status': status,
            'status_label': status_label,
            'reason_code': reason_code,
            'reason_label': _reason_code_label(reason_code),
            'note': notes,
            'recorded_at': recorded_at.isoformat(),
        },
    )
    return title, status_label


def _provider_response_due_days_for_intake(intake):
    if intake.urgency == CaseIntakeProcess.Urgency.CRISIS:
        return 1
    if intake.urgency == CaseIntakeProcess.Urgency.HIGH:
        return 2
    if intake.urgency == CaseIntakeProcess.Urgency.MEDIUM:
        return 3
    return 5


def _provider_response_reference_timestamp(placement):
    return (
        placement.provider_response_requested_at
        or placement.provider_response_recorded_at
        or placement.updated_at
        or placement.created_at
    )


def _normalize_provider_response_status_value(raw_status):
    status = str(raw_status or '').strip().upper()
    if status == 'DECLINED':
        return PlacementRequest.ProviderResponseStatus.REJECTED
    if status == 'NO_RESPONSE':
        return PlacementRequest.ProviderResponseStatus.PENDING
    if status in {choice[0] for choice in PlacementRequest.ProviderResponseStatus.choices}:
        return status
    return PlacementRequest.ProviderResponseStatus.PENDING


def _provider_response_summary(intake, placement):
    if not placement:
        return None

    now = timezone.now()
    normalized_status = _normalize_provider_response_status_value(placement.provider_response_status)
    requested_at = _provider_response_reference_timestamp(placement)
    due_days = _provider_response_due_days_for_intake(intake)
    deadline_at = placement.provider_response_deadline_at
    if not deadline_at and requested_at:
        deadline_at = requested_at + timedelta(days=due_days)

    age_days = 0
    if requested_at:
        age_days = max((now.date() - requested_at.date()).days, 0)

    is_open_response = normalized_status in {
        PlacementRequest.ProviderResponseStatus.PENDING,
        PlacementRequest.ProviderResponseStatus.NEEDS_INFO,
        PlacementRequest.ProviderResponseStatus.WAITLIST,
    }
    is_overdue = bool(deadline_at and now > deadline_at and is_open_response)

    provider_response_labels = {
        str(key): value for key, value in PlacementRequest.ProviderResponseStatus.choices
    }

    return {
        'status': normalized_status,
        'status_label': provider_response_labels.get(str(normalized_status), str(normalized_status)),
        'requested_at': requested_at,
        'recorded_at': placement.provider_response_recorded_at,
        'deadline_at': deadline_at,
        'age_days': age_days,
        'is_overdue': is_overdue,
        'is_open_response': is_open_response,
    }


def _provider_response_monitor_flags(summary):
    status = summary['status']
    is_waiting = status in {
        PlacementRequest.ProviderResponseStatus.PENDING,
        PlacementRequest.ProviderResponseStatus.NEEDS_INFO,
    }
    is_waitlist_or_no_capacity = status in {
        PlacementRequest.ProviderResponseStatus.WAITLIST,
        PlacementRequest.ProviderResponseStatus.NO_CAPACITY,
    }
    is_rematch_recommended = status in {
        PlacementRequest.ProviderResponseStatus.REJECTED,
        PlacementRequest.ProviderResponseStatus.WAITLIST,
        PlacementRequest.ProviderResponseStatus.NO_CAPACITY,
    }
    return {
        'is_waiting': is_waiting,
        'is_overdue': bool(summary['is_overdue']),
        'is_waitlist_or_no_capacity': is_waitlist_or_no_capacity,
        'is_rematch_recommended': is_rematch_recommended,
    }


def _provider_response_monitor_row(intake, placement, summary):
    flags = _provider_response_monitor_flags(summary)
    provider = placement.selected_provider or placement.proposed_provider
    provider_name = provider.name if provider else 'Nog geen aanbieder geselecteerd'

    return {
        'case_id': intake.pk,
        'case_title': intake.title,
        'phase_label': intake.get_status_display(),
        'urgency_label': intake.get_urgency_display(),
        'urgency_code': intake.urgency,
        'provider_name': provider_name,
        'status': summary['status'],
        'status_label': summary['status_label'],
        'age_days': summary['age_days'],
        'deadline_at': summary['deadline_at'],
        'requested_at': summary['requested_at'],
        'flags': flags,
        'case_href': _case_detail_tab_href(intake.pk, 'plaatsing'),
    }


def build_provider_response_monitor(org):
    if not org:
        return {
            'summary': {
                'waiting_count': 0,
                'overdue_count': 0,
                'rematch_recommended_count': 0,
                'waitlist_no_capacity_count': 0,
                'avg_age_days': 0,
                'total_cases': 0,
            },
            'queue_rows': [],
        }

    active_statuses = {
        CaseIntakeProcess.ProcessStatus.INTAKE,
        CaseIntakeProcess.ProcessStatus.ASSESSMENT,
        CaseIntakeProcess.ProcessStatus.MATCHING,
        CaseIntakeProcess.ProcessStatus.DECISION,
        CaseIntakeProcess.ProcessStatus.ON_HOLD,
    }
    monitored_statuses = {
        PlacementRequest.ProviderResponseStatus.PENDING,
        PlacementRequest.ProviderResponseStatus.NEEDS_INFO,
        PlacementRequest.ProviderResponseStatus.WAITLIST,
        PlacementRequest.ProviderResponseStatus.NO_CAPACITY,
        PlacementRequest.ProviderResponseStatus.REJECTED,
    }

    placements = (
        PlacementRequest.objects
        .filter(due_diligence_process__organization=org)
        .select_related('due_diligence_process', 'selected_provider', 'proposed_provider')
        .order_by('due_diligence_process_id', '-updated_at')
    )

    latest_by_intake = {}
    for placement in placements:
        intake_id = placement.due_diligence_process_id
        if not intake_id or intake_id in latest_by_intake:
            continue
        latest_by_intake[intake_id] = placement

    queue_rows = []
    for placement in latest_by_intake.values():
        intake = placement.due_diligence_process
        if not intake or intake.status not in active_statuses:
            continue

        summary = _provider_response_summary(intake, placement)
        if not summary or summary['status'] not in monitored_statuses:
            continue

        queue_rows.append(_provider_response_monitor_row(intake, placement, summary))

    queue_rows.sort(
        key=lambda row: (
            not row['flags']['is_overdue'],
            not row['flags']['is_rematch_recommended'],
            not row['flags']['is_waitlist_or_no_capacity'],
            -row['age_days'],
            str(row['case_title']).lower(),
        )
    )

    waiting_rows = [row for row in queue_rows if row['flags']['is_waiting']]
    waiting_count = len(waiting_rows)
    overdue_count = sum(1 for row in queue_rows if row['flags']['is_overdue'])
    rematch_recommended_count = sum(1 for row in queue_rows if row['flags']['is_rematch_recommended'])
    waitlist_no_capacity_count = sum(1 for row in queue_rows if row['flags']['is_waitlist_or_no_capacity'])
    avg_age_days = round(sum(row['age_days'] for row in waiting_rows) / waiting_count, 1) if waiting_count else 0

    return {
        'summary': {
            'waiting_count': waiting_count,
            'overdue_count': overdue_count,
            'rematch_recommended_count': rematch_recommended_count,
            'waitlist_no_capacity_count': waitlist_no_capacity_count,
            'avg_age_days': avg_age_days,
            'total_cases': len(queue_rows),
        },
        'queue_rows': queue_rows,
    }


def _split_csv_tags(raw_tags):
    if not raw_tags:
        return []
    return [part.strip() for part in raw_tags.split(',') if part.strip()]


def _extract_document_phase_event(tags):
    phase = ''
    event = ''
    for part in _split_csv_tags(tags):
        if part.startswith('phase:') and not phase:
            phase = part.split(':', 1)[1].strip()
        if part.startswith('event:') and not event:
            event = part.split(':', 1)[1].strip()
    return phase, event


def _merge_document_context_tags(existing_tags, *, phase='', event=''):
    tags = _split_csv_tags(existing_tags)
    context_tokens = []
    if phase:
        context_tokens.append(f'phase:{phase}')
    if event:
        context_tokens.append(f'event:{event}')

    for token in context_tokens:
        if token not in tags:
            tags.append(token)

    return ','.join(tags)


def _flow_stage_for_intake_status(intake_status):
    flow_stage_map = {
        CaseIntakeProcess.ProcessStatus.INTAKE: 'aanvraag',
        CaseIntakeProcess.ProcessStatus.ASSESSMENT: 'beoordeling',
        CaseIntakeProcess.ProcessStatus.MATCHING: 'matching',
        CaseIntakeProcess.ProcessStatus.DECISION: 'intake_aanbieder',
        CaseIntakeProcess.ProcessStatus.COMPLETED: 'plaatsing',
        CaseIntakeProcess.ProcessStatus.ON_HOLD: 'aanvraag',
    }
    return flow_stage_map.get(intake_status, 'aanvraag')


def _provider_form_match(profile, intake):
    return {
        CaseIntakeProcess.CareForm.OUTPATIENT: profile.offers_outpatient,
        CaseIntakeProcess.CareForm.DAY_TREATMENT: profile.offers_day_treatment,
        CaseIntakeProcess.CareForm.RESIDENTIAL: profile.offers_residential,
        CaseIntakeProcess.CareForm.CRISIS: profile.offers_crisis,
    }.get(intake.preferred_care_form, False)


def _provider_urgency_match(profile, intake):
    return {
        CaseIntakeProcess.Urgency.LOW: profile.handles_low_urgency,
        CaseIntakeProcess.Urgency.MEDIUM: profile.handles_medium_urgency,
        CaseIntakeProcess.Urgency.HIGH: profile.handles_high_urgency,
        CaseIntakeProcess.Urgency.CRISIS: profile.handles_crisis_urgency,
    }.get(intake.urgency, False)


def _compute_match_confidence(score, factors_complete):
    """
    Compute confidence level based on score and data completeness.
    
    - High: score >= 80 with complete factor data
    - Medium: score >= 60 or partial data
    - Low: score < 60 or significant data gaps
    """
    factor_completeness = len([f for f in factors_complete.values() if f]) / len(factors_complete) if factors_complete else 0
    
    if score >= 80 and factor_completeness >= 0.8:
        return 'high', 'Sterke match bevestigd op meerdere factoren — volledig profiel beschikbaar'
    elif score >= 60 and factor_completeness >= 0.5:
        return 'medium', 'Acceptabele match — niet alle factoren volledig bevestigd'
    else:
        return 'low', 'Lagere betrouwbaarheid — ontbrekende of zwakke matchfactoren'


def _build_matching_suggestions_for_intake(intake, provider_profiles, *, limit=5):
    suggestions = []

    for profile in provider_profiles:
        score = 0
        reasons = []
        
        # Track which factors contributed data for confidence calculation
        factors_complete = {
            'specialization': False,
            'urgency': False,
            'care_form': False,
            'region': False,
            'capacity': False,
            'wait_time': False,
        }
        
        # Build structured factors explanation
        factors = {
            'specialization': {'score': 0, 'status': 'no_match', 'detail': ''},
            'urgency': {'score': 0, 'status': 'no_match', 'detail': ''},
            'care_form': {'score': 0, 'status': 'no_match', 'detail': ''},
            'region': {'score': 0, 'status': 'no_match', 'detail': ''},
            'capacity': {'score': 0, 'status': 'full', 'detail': ''},
            'performance': {'score': 0, 'status': 'unknown', 'detail': ''},
        }
        
        trade_offs = []

        # 1. SPECIALIZATION / CATEGORY MATCH (40 pts)
        category_match = False
        if intake.care_category_main_id:
            category_match = profile.target_care_categories.filter(id=intake.care_category_main_id).exists()
            if category_match:
                score += 40
                reasons.append('Categorie match')
                factors['specialization']['score'] = 40
                factors['specialization']['status'] = 'match'
                factors['specialization']['detail'] = f"Aanbieder is gespecialiseerd in {getattr(intake.care_category_main, 'name', str(intake.care_category_main_id))} — exact de gevraagde categorie"
                factors_complete['specialization'] = True
            else:
                factors['specialization']['detail'] = f"Aanbieder biedt {getattr(intake.care_category_main, 'name', str(intake.care_category_main_id))} niet aan — specialisatiematch ontbreekt"
                factors_complete['specialization'] = True
        else:
            factors['specialization']['detail'] = 'Geen zorgcategorie opgegeven in de intake — kan niet worden gematcht'

        # 2. URGENCY MATCH (20 pts)
        urgency_match = _provider_urgency_match(profile, intake)
        if urgency_match:
            score += 20
            reasons.append('Urgentie match')
            factors['urgency']['score'] = 20
            factors['urgency']['status'] = 'match'
            factors['urgency']['detail'] = f"Aanbieder kan {intake.get_urgency_display().lower()} urgentie aan — overeenkomst bevestigd"
            factors_complete['urgency'] = True
        else:
            factors['urgency']['status'] = 'no_match'
            factors['urgency']['detail'] = f"Aanbieder biedt geen ondersteuning voor {intake.get_urgency_display().lower()} urgentie"
            factors_complete['urgency'] = True

        # 3. CARE FORM MATCH (20 pts)
        care_form_match = _provider_form_match(profile, intake)
        if care_form_match:
            score += 20
            reasons.append('Zorgvorm match')
            factors['care_form']['score'] = 20
            factors['care_form']['status'] = 'match'
            factors['care_form']['detail'] = f"Aanbieder biedt {intake.get_preferred_care_form_display().lower()} aan — conform zorgvraag"
            factors_complete['care_form'] = True
        else:
            factors['care_form']['status'] = 'no_match'
            factors['care_form']['detail'] = f"Aanbieder biedt {intake.get_preferred_care_form_display().lower()} niet aan — zorgvorm mismatch"
            factors_complete['care_form'] = True

        # 4. REGION MATCH (15 pts exact / 8 pts type)
        region_match = False
        region_match_type = None
        if intake.preferred_region_id:
            region_match = profile.served_regions.filter(id=intake.preferred_region_id).exists()
            if region_match:
                score += 15
                reasons.append('Voorkeursregio match')
                factors['region']['score'] = 15
                factors['region']['status'] = 'exact'
                factors['region']['detail'] = f"Aanbieder actief in voorkeurregio {intake.preferred_region.region_name if intake.preferred_region_id else 'voorkeurregio'} — exacte geografische match"
                region_match_type = 'exact'
                factors_complete['region'] = True
        
        if not region_match and intake.preferred_region_type:
            if profile.served_regions.filter(region_type=intake.preferred_region_type).exists():
                score += 8
                reasons.append('Regiotype match')
                factors['region']['score'] = 8
                factors['region']['status'] = 'compatible'
                factors['region']['detail'] = f"Aanbieder werkt in regiotype {intake.preferred_region_type} — gedeeltelijke geografische match"
                region_match_type = 'type'
                factors_complete['region'] = True
        
        if not region_match and not region_match_type:
            factors['region']['status'] = 'no_match'
            factors['region']['detail'] = 'Aanbieder actief buiten voorkeurregio van deze casus'
            if intake.preferred_region_id or intake.preferred_region_type:
                factors_complete['region'] = True

        # 5. CAPACITY MATCH (up to 20 pts)
        free_slots = max(profile.max_capacity - profile.current_capacity, 0)
        capacity_points = 0
        capacity_status = 'full'
        
        if free_slots > 0:
            capacity_points = min(free_slots * 4, 20)
            score += capacity_points
            reasons.append(f'{free_slots} vrije plekken')
            capacity_status = 'available' if free_slots > 3 else 'limited'
            if capacity_status == 'available':
                factors['capacity']['detail'] = f"{free_slots} plekken direct beschikbaar — ruimte voor nieuwe cliënt"
            else:
                factors['capacity']['detail'] = f"Beperkte beschikbaarheid: nog {free_slots} plek{'ken' if free_slots != 1 else ''} — tijdig bevestigen aanbevolen"
        else:
            capacity_status = 'full'
            factors['capacity']['detail'] = 'Aanbieder momenteel vol — geen directe plaatsing mogelijk'
            trade_offs.append('Aanbieder momenteel vol — overleg noodzakelijk voor plaatsingstermijn')
        
        factors['capacity']['score'] = capacity_points
        factors['capacity']['status'] = capacity_status
        factors_complete['capacity'] = True

        # 6. WAIT TIME PERFORMANCE (5-10 pts)
        wait_score = 0
        wait_status = 'unknown'
        wait_detail = f"Verwachte wachttijd: {profile.average_wait_days} dagen"
        
        if profile.average_wait_days <= 14:
            wait_score = 10
            reasons.append('Korte wachttijd')
            wait_status = 'good'
            wait_detail = f"Wachttijd {profile.average_wait_days} dagen — snel beschikbaar"
        elif profile.average_wait_days <= 28:
            wait_score = 5
            reasons.append('Acceptabele wachttijd')
            wait_status = 'acceptable'
            wait_detail = f"Wachttijd {profile.average_wait_days} dagen — binnen de acceptabele marge"
        else:
            wait_status = 'long'
            wait_detail = f"Wachttijd {profile.average_wait_days} dagen — overschrijdt streefnorm van 28 dagen"
            trade_offs.append(f"Wachttijd van {profile.average_wait_days} dagen overschrijdt streefnorm — risico op plaatsingsvertraging")
        
        score += wait_score
        factors['performance']['score'] = wait_score
        factors['performance']['status'] = wait_status
        factors['performance']['detail'] = wait_detail
        factors_complete['wait_time'] = True

        # Build confidence indicator — context-aware reason derived from confirmed factors
        confidence, _base_confidence_reason = _compute_match_confidence(score, factors_complete)
        _confirmed = [f for f, ok in [
            ('specialisatie', category_match),
            ('urgentie', urgency_match),
            ('zorgvorm', care_form_match),
            ('regio', region_match or bool(region_match_type)),
        ] if ok]
        if confidence == 'high':
            _cf_str = ' en '.join(_confirmed) if _confirmed else 'meerdere factoren'
            confidence_reason = f"Sterke match bevestigd op {_cf_str} — volledig profiel beschikbaar"
        elif confidence == 'medium':
            if capacity_status == 'full':
                confidence_reason = 'Acceptabele match — aanbieder momenteel zonder beschikbare capaciteit'
            elif wait_status == 'long':
                confidence_reason = f"Acceptabele match — wachttijd van {profile.average_wait_days} dagen is voornaamste beperking"
            elif _confirmed:
                _cf_str = ' en '.join(_confirmed[:2])
                confidence_reason = f"Acceptabele match op {_cf_str} — niet alle factoren volledig bevestigd"
            else:
                confidence_reason = 'Acceptabele match — profiel onvolledig of gedeeltelijk bevestigd'
        else:
            if not _confirmed:
                confidence_reason = 'Lage betrouwbaarheid — geen kernfactoren bevestigd'
            elif capacity_status == 'full':
                confidence_reason = 'Lage betrouwbaarheid — geen beschikbare capaciteit bij deze aanbieder'
            else:
                confidence_reason = 'Lage betrouwbaarheid — onvoldoende matchfactoren bevestigd'

        # Add general trade-offs if not already captured
        if score < 70 and len(trade_offs) == 0:
            trade_offs.append('Minder matchfactoren bevestigd dan beste optie — extra verificatie aanbevolen')
        
        # Build fit summary — contextual 1-sentence description referencing at least 2 factors
        _fit_strong = []
        if category_match:
            _fit_strong.append('specialisatie')
        if urgency_match:
            _fit_strong.append('urgentie')
        if care_form_match:
            _fit_strong.append('zorgvorm')
        if region_match or region_match_type:
            _fit_strong.append('regio')

        if score >= 80 and len(_fit_strong) >= 2:
            _factors_str = ', '.join(_fit_strong[:3])
            if capacity_status == 'available':
                fit_summary = f"Sterke match op {_factors_str} — directe plaatsing mogelijk"
            elif capacity_status == 'limited':
                fit_summary = f"Sterke match op {_factors_str} — let op beperkte beschikbaarheid"
            else:
                fit_summary = f"Sterke match op {_factors_str} — overleg vereist voor capaciteit"
        elif score >= 60 and len(_fit_strong) >= 1:
            _factors_str = ' en '.join(_fit_strong[:2])
            if trade_offs:
                fit_summary = f"Goede aansluiting op {_factors_str} — {trade_offs[0].lower()}"
            elif wait_status == 'good':
                fit_summary = f"Goede aansluiting op {_factors_str} — snel beschikbaar"
            else:
                fit_summary = f"Goede aansluiting op {_factors_str} — handmatige bevestiging nodig"
        elif len(_fit_strong) >= 1:
            _factors_str = _fit_strong[0]
            if trade_offs:
                fit_summary = f"Gedeeltelijke match op {_factors_str} — {trade_offs[0].lower()}"
            else:
                fit_summary = f"Gedeeltelijke match op {_factors_str} — overige factoren sluiten minder goed aan"
        else:
            fit_summary = "Onvoldoende matchfactoren bevestigd — handmatige beoordeling vereist"
        
        # Determine what user should verify manually (2–4 actionable items, no repetition)
        verify_manually = []
        if capacity_status in ('limited', 'full'):
            verify_manually.append('Bevestig actuele beschikbaarheid bij aanbieder voor definitieve plaatsing')
        if wait_status == 'long':
            verify_manually.append(f"Verifieer of wachttijd van {profile.average_wait_days} dagen nog actueel is")
        elif wait_status == 'unknown':
            verify_manually.append('Vraag aanbieder naar verwachte doorlooptijd en wachttijd')
        if not urgency_match or not care_form_match:
            verify_manually.append('Bevestig of aanbieder afwijkende zorgvorm of urgentie kan ondersteunen')
        if confidence == 'low':
            verify_manually.append('Vraag aanbieder naar aanvullende informatie — profiel bevat mogelijk onvolledige gegevens')
        # Standard check always included unless list already has 4 items
        if len(verify_manually) < 4:
            verify_manually.append('Controleer of intakeplanning bij aanbieder nog actueel is')

        tradeoff_text = trade_offs[0] if trade_offs else 'Handmatige afweging nodig'

        suggestions.append(
            {
                # Keep existing fields for backward compatibility
                'provider_id': profile.client_id,
                'provider_name': profile.client.name,
                'match_score': min(score, 100),
                'fit_score': min(score, 100),
                'category_match': category_match,
                'urgency_match': urgency_match,
                'care_form_match': care_form_match,
                'region_match': region_match,
                'free_slots': free_slots,
                'avg_wait_days': profile.average_wait_days,
                'reason': reasons[0] if reasons else 'Handmatige beoordeling nodig',
                'reasons': reasons,
                'tradeoff': tradeoff_text,
                
                # NEW: Structured explanation for explainability
                'explanation': {
                    'fit_summary': fit_summary,
                    'factors': factors,
                    'confidence': confidence,
                    'confidence_reason': confidence_reason,
                    'trade_offs': trade_offs,
                    'verify_manually': verify_manually,
                }
            }
        )

    suggestions.sort(key=lambda row: row['match_score'], reverse=True)
    if limit:
        return suggestions[:limit]
    return suggestions


def _provider_outcome_context_for_candidates(*, intake, candidates):
    provider_ids = [row.get('provider_id') for row in candidates if row.get('provider_id')]
    if not provider_ids:
        return {}

    stats = {
        provider_id: {
            'sample_size': 0,
            'response_total': 0,
            'accepted_count': 0,
            'quality_total': 0,
            'quality_negative_count': 0,
            'recent_quality': [],
        }
        for provider_id in provider_ids
    }

    history_qs = (
        PlacementRequest.objects.filter(
            due_diligence_process__organization_id=intake.organization_id,
            selected_provider_id__in=provider_ids,
        )
        .select_related('due_diligence_process')
        .order_by('selected_provider_id', '-updated_at')
    )

    per_provider_seen = {provider_id: 0 for provider_id in provider_ids}
    max_samples_per_provider = 12

    for placement in history_qs:
        provider_id = placement.selected_provider_id
        if not provider_id or provider_id not in stats:
            continue

        if per_provider_seen[provider_id] >= max_samples_per_provider:
            continue

        source_intake = placement.due_diligence_process
        if intake.care_category_main_id and source_intake and source_intake.care_category_main_id:
            if source_intake.care_category_main_id != intake.care_category_main_id:
                continue

        per_provider_seen[provider_id] += 1
        row = stats[provider_id]
        row['sample_size'] += 1

        response_status = placement.provider_response_status
        if response_status != PlacementRequest.ProviderResponseStatus.PENDING:
            row['response_total'] += 1
            if response_status == PlacementRequest.ProviderResponseStatus.ACCEPTED:
                row['accepted_count'] += 1

        quality_status = placement.placement_quality_status
        if quality_status != PlacementRequest.PlacementQualityStatus.PENDING:
            is_negative_quality = quality_status in {
                PlacementRequest.PlacementQualityStatus.AT_RISK,
                PlacementRequest.PlacementQualityStatus.BROKEN_DOWN,
            }
            row['quality_total'] += 1
            if is_negative_quality:
                row['quality_negative_count'] += 1
            if len(row['recent_quality']) < 3:
                row['recent_quality'].append(is_negative_quality)

    context = {}
    for provider_id in provider_ids:
        row = stats.get(provider_id) or {}
        sample_size = row.get('sample_size', 0)
        if sample_size <= 0:
            context[provider_id] = {
                'evidence_level': 'none',
                'evidence_label': 'Geen historie',
                'summary': 'Nog geen vergelijkbare uitkomsthistorie voor deze aanbieder.',
                'acceptance_label': '',
                'quality_label': '',
                'warning': '',
            }
            continue

        evidence_level = 'sufficient' if sample_size >= 3 else 'limited'
        evidence_label = 'Voldoende historie' if evidence_level == 'sufficient' else 'Beperkte historie'

        response_total = row.get('response_total', 0)
        accepted_count = row.get('accepted_count', 0)
        acceptance_label = ''
        acceptance_rate = None
        if response_total > 0:
            acceptance_rate = round((accepted_count / response_total) * 100)
            acceptance_label = f"Acceptatiegraad: {acceptance_rate}% ({accepted_count}/{response_total})"

        quality_total = row.get('quality_total', 0)
        quality_negative_count = row.get('quality_negative_count', 0)
        quality_label = ''
        quality_risk_rate = None
        if quality_total > 0:
            quality_risk_rate = round((quality_negative_count / quality_total) * 100)
            quality_label = f"Risico op uitval: {quality_risk_rate}% ({quality_negative_count}/{quality_total})"

        warning = ''
        recent_negative_count = sum(1 for value in row.get('recent_quality', []) if value)
        if quality_risk_rate is not None and quality_risk_rate >= 50 and quality_total >= 2:
            warning = 'Recente plaatsingen tonen verhoogd uitvalrisico.'
        elif acceptance_rate is not None and acceptance_rate < 50 and response_total >= 2:
            warning = 'Aanbieder reageert relatief vaak zonder acceptatie.'
        elif recent_negative_count >= 2:
            warning = 'Meerdere recente negatieve plaatsingsuitkomsten gedetecteerd.'

        if evidence_level == 'limited':
            summary = 'Beperkte historie beschikbaar; signalen zijn indicatief en vereisen handmatige verificatie.'
        elif warning:
            summary = 'Historische signalen vragen extra aandacht naast actuele matchfactoren.'
        else:
            summary = 'Historische uitkomsten ondersteunen de actuele matchbeoordeling.'

        context[provider_id] = {
            'evidence_level': evidence_level,
            'evidence_label': evidence_label,
            'summary': summary,
            'acceptance_label': acceptance_label,
            'quality_label': quality_label,
            'warning': warning,
        }

    return context


def _get_rejection_reason_for_provider(intake, provider, suggestions):
    """
    Determine structured rejection reason for a provider.
    
    Analyzes why a provider was not selected:
    - no_capacity: no free slots
    - wrong_specialization: care category mismatch
    - region_mismatch: geographic mismatch
    - lower_ranking: other providers ranked higher
    - manual_rejection: user manually rejected
    - unknown: no clear reason
    """
    
    # Check if provider is in current suggestions
    provider_suggestion = next((s for s in suggestions if s['provider_id'] == provider.client_id), None)
    
    if not provider_suggestion:
        # Provider not in suggestions - determine why
        if provider.max_capacity - provider.current_capacity <= 0:
            return {
                'code': 'no_capacity',
                'label': 'Geen beschikbare capaciteit',
                'detail': 'Aanbieder heeft momenteel geen vrije plekken — geen directe plaatsing mogelijk',
            }
        
        if intake.care_category_main_id and not provider.target_care_categories.filter(id=intake.care_category_main_id).exists():
            return {
                'code': 'wrong_specialization',
                'label': 'Specialisatie niet aangeboden',
                'detail': f"Aanbieder biedt zorgcategorie '{getattr(intake.care_category_main, 'name', '')}' niet aan",
            }
        
        if intake.preferred_region_id and not provider.served_regions.filter(id=intake.preferred_region_id).exists():
            if intake.preferred_region_type and not provider.served_regions.filter(region_type=intake.preferred_region_type).exists():
                return {
                    'code': 'region_mismatch',
                    'label': 'Buiten voorkeurregio',
                    'detail': 'Aanbieder werkt niet in de voorkeurregio van deze casus',
                }
        
        return {
            'code': 'unknown',
            'label': 'Niet geschikt bevonden',
            'detail': 'Reden niet automatisch bepaalbaar — controleer handmatig',
        }
    
    # Provider is in suggestions - likely ranked lower than other options
    top_suggestion = suggestions[0] if suggestions else None
    top_score = top_suggestion['match_score'] if top_suggestion else 0
    provider_score = provider_suggestion['match_score']
    
    if provider_score < top_score:
        return {
            'code': 'lower_ranking',
            'label': 'Lagere matchscore',
            'detail': f"Lagere matchscore dan geselecteerde aanbieder ({provider_score}% vs {top_score}%)",
        }
    
    return {
        'code': 'unknown',
        'label': 'Niet geselecteerd',
        'detail': 'Geen duidelijke reden vastgesteld — controleer handmatig',
    }


def _build_missing_information_alerts(intake, assessment):
    alerts = []

    if not intake.care_category_main_id:
        alerts.append(
            {
                'code': 'missing_care_category',
                'label': 'Hoofdcategorie ontbreekt',
                'message': 'Hoofdcategorie zorgvraag ontbreekt — matching kan niet gericht worden uitgevoerd.',
                'action': 'Vul hoofdcategorie in de casussamenvatting aan.',
            }
        )
    if not intake.preferred_region_id:
        alerts.append(
            {
                'code': 'missing_region',
                'label': 'Voorkeursregio ontbreekt',
                'message': 'Voorkeursregio ontbreekt — regiomatch kan niet betrouwbaar worden bepaald.',
                'action': 'Kies een voorkeursregio in de intake.',
            }
        )
    if not (intake.assessment_summary or '').strip():
        alerts.append(
            {
                'code': 'missing_assessment_summary',
                'label': 'Intake samenvatting ontbreekt',
                'message': 'Intake samenvatting ontbreekt — belangrijke context voor beoordeling mist.',
                'action': 'Vul de intake samenvatting aan met hulpvraag en aandachtspunten.',
            }
        )
    if not intake.client_age_category:
        alerts.append(
            {
                'code': 'missing_age_category',
                'label': 'Leeftijdscategorie ontbreekt',
                'message': 'Leeftijdscategorie ontbreekt — doelgroepmatch met aanbieders is onvolledig.',
                'action': 'Selecteer de leeftijdscategorie van de client.',
            }
        )

    if assessment:
        if assessment.assessment_status == CaseAssessment.AssessmentStatus.NEEDS_INFO:
            alerts.append(
                {
                    'code': 'assessment_needs_info',
                    'label': 'Beoordeling vraagt aanvullende informatie',
                    'message': 'Beoordeling staat op aanvullende informatie nodig.',
                    'action': assessment.reason_not_ready or 'Werk ontbrekende beoordelingsinformatie bij.',
                }
            )
        if not assessment.matching_ready:
            alerts.append(
                {
                    'code': 'assessment_not_ready',
                    'label': 'Beoordeling nog niet matching-klaar',
                    'message': 'Beoordeling is nog niet als klaar voor matching gemarkeerd.',
                    'action': assessment.reason_not_ready or 'Markeer beoordeling als matching-klaar zodra compleet.',
                }
            )
    else:
        alerts.append(
            {
                'code': 'missing_assessment',
                'label': 'Beoordeling ontbreekt',
                'message': 'Nog geen beoordeling beschikbaar voor deze casus.',
                'action': 'Start de beoordeling om door te gaan naar matching.',
            }
        )

    return alerts


def _decision_guidance_hint(candidate, *, index, top_candidate):
    confidence = (candidate.get('explanation') or {}).get('confidence')
    if index == 0:
        if confidence in ('high', 'medium'):
            return 'Beste optie op basis van huidige gegevens.'
        return 'Geen sterke match gevonden — extra verificatie nodig.'

    top_free_slots = top_candidate.get('free_slots', 0) if top_candidate else 0
    if candidate.get('free_slots', 0) > top_free_slots and top_free_slots <= 1:
        return 'Overweeg deze optie als alternatief vanwege betere beschikbare capaciteit.'
    if confidence == 'high':
        return 'Sterk alternatief als eerste keuze niet haalbaar blijkt.'
    return 'Alternatieve optie met aanvullende verificatie.'


_MISSING_INFORMATION_PRIORITY = {
    'missing_care_category': 10,
    'missing_phase': 15,
    'missing_urgency': 20,
    'missing_region': 30,
    'missing_assessment_summary': 40,
    'missing_age_category': 50,
    'assessment_needs_info': 60,
    'assessment_not_ready': 70,
    'missing_assessment': 80,
    'missing_selected_provider': 90,
    'missing_top_match_confidence': 100,
}


_RISK_SIGNAL_PRIORITY = {
    'open_signals': 10,
    'repeated_rejections': 20,
    'weak_matching_quality': 30,
    'capacity_risk': 40,
    'long_wait_risk': 50,
    'provider_response_delayed': 60,
    'provider_not_responding': 65,
    'high_urgency_response_delay': 68,
    'provider_no_capacity': 70,
    'rematch_recommended': 72,
    'placement_stalled': 75,
    'matching_outdated': 80,
    'stale_case': 85,
    'task_backlog': 90,
}


def _ordered_missing_information(alerts):
    return sorted(
        alerts,
        key=lambda item: (
            _MISSING_INFORMATION_PRIORITY.get(item.get('code'), 999),
            item.get('label', ''),
        ),
    )


def _ordered_risk_signals(signals):
    return sorted(
        signals,
        key=lambda item: (
            _RISK_SIGNAL_PRIORITY.get(item.get('code'), 999),
            item.get('label', ''),
        ),
    )


def _next_action_severity(action_code):
    critical_codes = {
        'fill_missing_information',
        'complete_assessment',
        'review_matching_quality',
        'validate_capacity_wait',
        'resolve_placement_stall',
    }
    warning_codes = {'run_matching'}

    if action_code in critical_codes:
        return 'critical'
    if action_code in warning_codes:
        return 'warning'
    return 'normal'


def _build_intelligence_flags_from_signals(signals):
    signal_codes = {item.get('code') for item in signals}
    return {
        'no_strong_match': 'weak_matching_quality' in signal_codes,
        'long_wait_risk': 'long_wait_risk' in signal_codes,
        'repeated_rejections': 'repeated_rejections' in signal_codes,
        'placement_stalled': 'placement_stalled' in signal_codes,
        'capacity_risk': 'capacity_risk' in signal_codes,
        'stagnating_case': 'stale_case' in signal_codes,
        'matching_outdated': 'matching_outdated' in signal_codes,
        'provider_response_delayed': 'provider_response_delayed' in signal_codes,
        'provider_not_responding': 'provider_not_responding' in signal_codes,
        'rematch_recommended': 'rematch_recommended' in signal_codes,
    }


def _build_case_data_for_intelligence(
    *,
    intake,
    assessment,
    placement,
    matching_preview_candidates,
    rejected_options,
    latest_assignment,
    open_signals_count,
    open_tasks_count,
):
    top_candidate = matching_preview_candidates[0] if matching_preview_candidates else None
    candidate_suggestions = []
    for row in matching_preview_candidates:
        explanation = row.get('explanation') or {}
        factors = explanation.get('factors') or {}
        region_status = (factors.get('region') or {}).get('status')
        candidate_suggestions.append(
            {
                'provider_id': row.get('provider_id'),
                'confidence': explanation.get('confidence'),
                'has_capacity_issue': (row.get('free_slots') or 0) <= 0,
                'wait_days': row.get('avg_wait_days') or 0,
                'has_region_mismatch': region_status not in {'exact', 'compatible'},
            }
        )

    return {
        'phase': intake.status,
        'care_category': getattr(intake.care_category_main, 'name', None),
        'urgency': intake.urgency,
        'assessment_complete': bool(
            assessment
            and assessment.matching_ready
            and assessment.assessment_status == CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING
        ),
        'matching_run_exists': bool(matching_preview_candidates),
        'top_match_confidence': ((top_candidate or {}).get('explanation') or {}).get('confidence'),
        'top_match_has_capacity_issue': ((top_candidate or {}).get('free_slots') or 0) <= 0 if top_candidate else False,
        'top_match_wait_days': (top_candidate or {}).get('avg_wait_days') if top_candidate else 0,
        'selected_provider_id': placement.selected_provider_id if placement else None,
        'placement_status': placement.status if placement else None,
        'placement_updated_at': placement.updated_at if placement else None,
        'rejected_provider_count': len(rejected_options),
        'open_signal_count': open_signals_count,
        'open_task_count': open_tasks_count,
        'case_updated_at': intake.updated_at,
        'candidate_suggestions': candidate_suggestions,
        'has_preferred_region': bool(intake.preferred_region_id),
        'has_assessment_summary': bool((intake.assessment_summary or '').strip()),
        'has_client_age_category': bool(intake.client_age_category),
        'assessment_status': assessment.assessment_status if assessment else None,
        'assessment_matching_ready': assessment.matching_ready if assessment else None,
        'matching_updated_at': latest_assignment.updated_at if latest_assignment else None,
        'provider_response_status': _normalize_provider_response_status_value(placement.provider_response_status) if placement else None,
        'provider_response_recorded_at': placement.provider_response_recorded_at if placement else None,
        'provider_response_requested_at': placement.provider_response_requested_at if placement else None,
        'provider_response_deadline_at': placement.provider_response_deadline_at if placement else None,
    }


def _map_rule_action_to_ui(
    *,
    can_edit_case,
    rule_action,
    assessment_href,
    matching_href,
    placement_href,
    case_update_href,
    monitor_href,
):
    if not can_edit_case:
        return {
            'label': 'Alleen-lezen toegang',
            'href': reverse('careon:case_list'),
            'help': 'Je kunt deze casus bekijken, maar niet wijzigen. Neem contact op met een beheerder.',
            'severity': 'normal',
            'state_label': 'Informatie',
            'code': 'read_only',
        }

    mapping = {
        'fill_missing_information': {
            'label': 'Vul ontbrekende gegevens aan',
            'href': case_update_href,
        },
        'complete_assessment': {
            'label': 'Rond beoordeling af',
            'href': assessment_href,
        },
        'run_matching': {
            'label': 'Start of herstart matching',
            'href': matching_href,
        },
        'follow_up_provider_response': {
            'label': 'Volg providerreactie op',
            'href': f'{monitor_href}?tab=plaatsing',
        },
        'review_matching_quality': {
            'label': 'Herbeoordeel matchkwaliteit',
            'href': matching_href,
        },
        'validate_capacity_wait': {
            'label': 'Valideer capaciteit en wachttijd',
            'href': matching_href,
        },
        'resolve_placement_stall': {
            'label': 'Doorbreek plaatsingsblokkade',
            'href': placement_href,
        },
        'monitor': {
            'label': 'Monitor voortgang',
            'href': monitor_href,
        },
    }
    base = mapping.get(rule_action.get('code'), mapping['monitor'])
    severity = _next_action_severity(rule_action.get('code'))
    state_label = {
        'critical': 'Kritiek',
        'warning': 'Waarschuwing',
        'normal': 'Stabiel',
    }[severity]
    return {
        'label': base['label'],
        'href': base['href'],
        'help': rule_action.get('reason') or '',
        'severity': severity,
        'state_label': state_label,
        'code': rule_action.get('code'),
    }


def _build_system_intelligence_signals(
    *,
    intake,
    placement,
    matching_preview_candidates,
    rejected_options,
    latest_assignment,
):
    now = timezone.now()
    signals = []
    flags = {
        'no_strong_match': False,
        'long_wait_risk': False,
        'repeated_rejections': False,
        'placement_stalled': False,
        'capacity_risk': False,
        'stagnating_case': False,
        'matching_outdated': False,
    }

    top_candidates = matching_preview_candidates[:3]
    if top_candidates:
        has_acceptable_confidence = any(
            (row.get('explanation') or {}).get('confidence') in ('high', 'medium') for row in top_candidates
        )
        if not has_acceptable_confidence:
            flags['no_strong_match'] = True
            signals.append(
                {
                    'code': 'no_strong_match',
                    'label': 'Geen sterke match',
                    'message': 'Geen aanbieder met hoge of redelijke confidence in topmatches.',
                    'action': 'Herzie selectiecriteria en controleer alternatieve aanbieders.',
                }
            )

        if all((row.get('free_slots') or 0) <= 0 for row in top_candidates):
            flags['capacity_risk'] = True
            signals.append(
                {
                    'code': 'capacity_risk',
                    'label': 'Capaciteitsrisico',
                    'message': 'Topmatches hebben geen directe capaciteit beschikbaar.',
                    'action': 'Bevestig beschikbaarheid bij aanbieders of overweeg tweede lijn opties.',
                }
            )

        top_wait = top_candidates[0].get('avg_wait_days') or 0
        if top_wait > 28:
            flags['long_wait_risk'] = True
            signals.append(
                {
                    'code': 'long_wait_risk',
                    'label': 'Lange wachttijd',
                    'message': f'Beste match heeft een wachttijd van {top_wait} dagen.',
                    'action': 'Controleer wachttijd en bespreek versnelde intakeopties met aanbieder.',
                }
            )

    if len(rejected_options) >= 2:
        flags['repeated_rejections'] = True
        signals.append(
            {
                'code': 'repeated_rejections',
                'label': 'Herhaalde afwijzingen',
                'message': f'{len(rejected_options)} aanbieders recent afgewezen in deze casus.',
                'action': 'Controleer of selectiecriteria moeten worden aangescherpt of verbreed.',
            }
        )

    if placement and placement.status in [PlacementRequest.Status.IN_REVIEW, PlacementRequest.Status.NEEDS_INFO]:
        pending_days = max((now.date() - placement.updated_at.date()).days, 0)
        if pending_days >= 7:
            flags['placement_stalled'] = True
            signals.append(
                {
                    'code': 'placement_stalled',
                    'label': 'Plaatsing stagneert',
                    'message': f'Plaatsing staat al {pending_days} dagen op {placement.get_status_display().lower()}.',
                    'action': 'Controleer status met aanbieder en actualiseer plaatsingsbesluit.',
                }
            )

    stale_days = max((now.date() - intake.updated_at.date()).days, 0)
    if stale_days >= 10:
        flags['stagnating_case'] = True
        signals.append(
            {
                'code': 'stagnating_case',
                'label': 'Casus verouderd',
                'message': f'Casus is {stale_days} dagen niet bijgewerkt.',
                'action': 'Werk casusgegevens en voortgang bij om stagnatie te voorkomen.',
            }
        )

    if latest_assignment and intake.updated_at.date() > latest_assignment.updated_at.date():
        flags['matching_outdated'] = True
        signals.append(
            {
                'code': 'matching_outdated',
                'label': 'Matching mogelijk verouderd',
                'message': 'Casusgegevens zijn gewijzigd na de laatste matchingselectie.',
                'action': 'Herstart matching om aanbevelingen te herbeoordelen met actuele data.',
            }
        )

    return signals, flags


def _build_enhanced_next_action(
    *,
    can_edit_case,
    intake,
    assessment,
    placement,
    matching_preview_candidates,
    missing_information_alerts,
    intelligence_flags,
    assessment_href,
    matching_href,
    placement_href,
    case_update_href,
):
    if not can_edit_case:
        return {
            'label': 'Alleen-lezen toegang',
            'href': reverse('careon:case_list'),
            'help': 'Je kunt deze casus bekijken, maar niet wijzigen. Neem contact op met een beheerder.',
        }

    if missing_information_alerts:
        return {
            'label': 'Vul ontbrekende gegevens aan',
            'href': case_update_href,
            'help': missing_information_alerts[0]['message'],
        }

    if not assessment:
        return {
            'label': 'Start beoordeling',
            'href': assessment_href,
            'help': 'Deze casus heeft nog geen beoordeling. Start met beoordelen.',
        }

    if assessment.assessment_status != CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING or not assessment.matching_ready:
        return {
            'label': 'Voltooi beoordeling',
            'href': assessment_href,
            'help': 'Beoordeling is nog niet volledig gereed voor matching.',
        }

    if not matching_preview_candidates:
        return {
            'label': 'Start matching',
            'href': matching_href,
            'help': 'Nog geen matchresultaten beschikbaar. Start matching voor aanbevelingen.',
        }

    top_candidate = matching_preview_candidates[0]
    top_confidence = (top_candidate.get('explanation') or {}).get('confidence')
    if top_confidence == 'low' or intelligence_flags.get('no_strong_match'):
        return {
            'label': 'Herzie selectie',
            'href': matching_href,
            'help': 'Topmatch heeft lage confidence. Controleer alternatieven en matchfactoren.',
        }

    if intelligence_flags.get('capacity_risk'):
        return {
            'label': 'Bevestig beschikbaarheid',
            'href': matching_href,
            'help': 'Topaanbieders hebben beperkte capaciteit. Bevestig beschikbaarheid voordat je beslist.',
        }

    if placement and intelligence_flags.get('placement_stalled'):
        return {
            'label': 'Controleer status plaatsing',
            'href': placement_href,
            'help': 'Plaatsing staat te lang open. Werk status en vervolgstap bij.',
        }

    if not placement:
        return {
            'label': 'Start matching',
            'href': matching_href,
            'help': 'Koppel een aanbieder op basis van huidige aanbevelingen.',
        }

    return {
        'label': 'Bevestig plaatsing',
        'href': placement_href,
        'help': 'Werk de plaatsingsbeslissing af en start opvolging.',
    }


def _assign_provider_to_intake(*, request, intake, provider, source):
    placement, created = PlacementRequest.objects.get_or_create(
        due_diligence_process=intake,
        defaults={
            'status': PlacementRequest.Status.IN_REVIEW,
            'proposed_provider': provider,
            'selected_provider': provider,
            'care_form': intake.preferred_care_form,
            'decision_notes': 'Automatisch toegewezen vanuit matching.',
        },
    )
    if not created:
        placement.proposed_provider = provider
        placement.selected_provider = provider
        if not placement.care_form:
            placement.care_form = intake.preferred_care_form
        placement.status = PlacementRequest.Status.IN_REVIEW
        placement.save(update_fields=['proposed_provider', 'selected_provider', 'care_form', 'status', 'updated_at'])

    if intake.status != CaseIntakeProcess.ProcessStatus.MATCHING:
        intake.status = CaseIntakeProcess.ProcessStatus.MATCHING
        intake.save(update_fields=['status', 'updated_at'])

    log_action(
        request.user,
        AuditLog.Action.APPROVE,
        'MatchingAssignment',
        object_id=placement.id,
        object_repr=f'{intake.title} -> {provider.name}',
        changes={
            'intake_id': intake.id,
            'provider_id': provider.id,
            'provider_name': provider.name,
            'source': source,
        },
        request=request,
    )

    return placement


def _matching_history_for_intake(intake, *, limit=10):
    history_qs = AuditLog.objects.filter(
        model_name__in=['MatchingAssignment', 'MatchingRecommendation'],
        changes__intake_id=intake.id,
    ).order_by('-timestamp')
    return list(history_qs[:limit])


def _can_edit_intake(user, intake):
    if intake is None:
        return False

    linked_case = intake.case_record
    if linked_case is not None:
        return can_access_case_action(user, linked_case, CaseAction.EDIT)

    if intake.organization and can_manage_organization(user, intake.organization):
        return True

    return bool(intake.case_coordinator_id and intake.case_coordinator_id == user.id)


def _disable_response_caching(response):
    patch_cache_control(
        response,
        no_cache=True,
        no_store=True,
        must_revalidate=True,
        private=True,
        max_age=0,
    )
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def _can_edit_assessment(user, assessment):
    if assessment is None:
        return False

    if _can_edit_intake(user, assessment.intake):
        return True

    return bool(assessment.assessed_by_id and assessment.assessed_by_id == user.id)


def _log_pilot_issue(request, *, category, detail, level='warning'):
    user = getattr(request, 'user', None)
    user_label = getattr(user, 'username', 'anonymous') if user and getattr(user, 'is_authenticated', False) else 'anonymous'
    log_method = getattr(logger, level, logger.warning)
    log_method(
        'pilot.%s user=%s path=%s detail=%s',
        category,
        user_label,
        getattr(request, 'path', '-'),
        detail,
    )


def _resolve_task_due_date(*, base_date=None, fallback_days=2):
    if base_date:
        return base_date
    return date.today() + timedelta(days=fallback_days)


def sync_intake_auto_tasks(process, user=None):
    task_config = AUTO_INTAKE_TASKS.get(process.status)
    auto_tasks = Deadline.objects.filter(due_diligence_process=process, auto_generated=True)

    if not task_config:
        auto_tasks.filter(is_completed=False).update(
            is_completed=True,
            completed_at=timezone.now(),
            completed_by=user,
        )
        return

    due_date = _resolve_task_due_date(
        base_date=process.target_completion_date,
        fallback_days=3,
    )

    current_task, created = Deadline.objects.get_or_create(
        due_diligence_process=process,
        auto_generated=True,
        generation_source=task_config['source'],
        task_type=task_config['task_type'],
        defaults={
            'title': task_config['title'],
            'description': f'Automatisch aangemaakt vanuit {task_config["source"].lower()} voor {process.title}.',
            'priority': task_config['priority'],
            'due_date': due_date,
            'assigned_to': process.case_coordinator,
            'created_by': user,
        },
    )

    update_fields = []
    if current_task.title != task_config['title']:
        current_task.title = task_config['title']
        update_fields.append('title')
    if current_task.priority != task_config['priority']:
        current_task.priority = task_config['priority']
        update_fields.append('priority')
    if current_task.due_date != due_date:
        current_task.due_date = due_date
        update_fields.append('due_date')
    if current_task.assigned_to_id != process.case_coordinator_id:
        current_task.assigned_to = process.case_coordinator
        update_fields.append('assigned_to')
    if update_fields:
        current_task.save(update_fields=update_fields)

    auto_tasks.exclude(pk=current_task.pk).filter(is_completed=False).update(
        is_completed=True,
        completed_at=timezone.now(),
        completed_by=user,
    )


def sync_case_phase_auto_tasks(case, user=None):
    phase_task = None
    if case.case_phase == CareCase.CasePhase.PLAATSING:
        phase_task = {
            'title': 'Plaatsing bevestigen',
            'task_type': Deadline.TaskType.CONFIRM_PLACEMENT,
            'priority': Deadline.Priority.URGENT,
            'source': Deadline.GenerationSource.PLACEMENT,
        }

    auto_tasks = Deadline.objects.filter(case_record=case, auto_generated=True)

    if not phase_task:
        auto_tasks.filter(is_completed=False).update(
            is_completed=True,
            completed_at=timezone.now(),
            completed_by=user,
        )
        return

    due_date = _resolve_task_due_date(fallback_days=1)
    current_task, created = Deadline.objects.get_or_create(
        case_record=case,
        auto_generated=True,
        generation_source=phase_task['source'],
        task_type=phase_task['task_type'],
        defaults={
            'title': phase_task['title'],
            'description': f'Automatisch aangemaakt vanuit plaatsing voor {case.title}.',
            'priority': phase_task['priority'],
            'due_date': due_date,
            'assigned_to': case.created_by,
            'created_by': user,
        },
    )

    update_fields = []
    if current_task.title != phase_task['title']:
        current_task.title = phase_task['title']
        update_fields.append('title')
    if current_task.priority != phase_task['priority']:
        current_task.priority = phase_task['priority']
        update_fields.append('priority')
    if current_task.due_date != due_date:
        current_task.due_date = due_date
        update_fields.append('due_date')
    if current_task.assigned_to_id != case.created_by_id:
        current_task.assigned_to = case.created_by
        update_fields.append('assigned_to')
    if update_fields:
        current_task.save(update_fields=update_fields)

    auto_tasks.exclude(pk=current_task.pk).filter(is_completed=False).update(
        is_completed=True,
        completed_at=timezone.now(),
        completed_by=user,
    )


def sync_automatic_deadlines_for_organization(org, user=None):
    if not org:
        return
    for process in CaseIntakeProcess.objects.filter(organization=org).select_related('case_coordinator'):
        sync_intake_auto_tasks(process, user=user)
    for case in CareCase.objects.filter(organization=org):
        sync_case_phase_auto_tasks(case, user=user)


PHASE_TO_PROCESS_STATUS = {
    CareCase.CasePhase.INTAKE: CaseIntakeProcess.ProcessStatus.INTAKE,
    CareCase.CasePhase.BEOORDELING: CaseIntakeProcess.ProcessStatus.ASSESSMENT,
    CareCase.CasePhase.MATCHING: CaseIntakeProcess.ProcessStatus.MATCHING,
    CareCase.CasePhase.PLAATSING: CaseIntakeProcess.ProcessStatus.DECISION,
    CareCase.CasePhase.ACTIEF: CaseIntakeProcess.ProcessStatus.COMPLETED,
    CareCase.CasePhase.AFGEROND: CaseIntakeProcess.ProcessStatus.COMPLETED,
}


def get_case_section_url(case, section=None):
    url = reverse('careon:case_detail', kwargs={'pk': case.pk})
    if section:
        return f'{url}#{section}'
    return url


def _coerce_case_process_defaults(case):
    start_date = case.start_date or case.created_at.date() or date.today()
    target_date = case.end_date or start_date + timedelta(days=14)
    return {
        'organization': case.organization,
        'contract': case,
        'title': case.title,
        'status': PHASE_TO_PROCESS_STATUS.get(case.case_phase, CaseIntakeProcess.ProcessStatus.INTAKE),
        'case_coordinator': case.created_by if case.created_by_id else None,
        'start_date': start_date,
        'target_completion_date': target_date,
        'assessment_summary': case.content or '',
        'description': case.content or '',
    }


def ensure_case_flow(case, user=None):
    process = getattr(case, 'due_diligence_process', None)
    if not process:
        process = CaseIntakeProcess.objects.filter(contract=case).select_related('case_assessment').first()
    if not process:
        process = CaseIntakeProcess.objects.filter(
            organization=case.organization,
            contract__isnull=True,
            title=case.title,
        ).order_by('-updated_at').first()

    process_defaults = _coerce_case_process_defaults(case)
    if process is None:
        process = CaseIntakeProcess.objects.create(**process_defaults)
    else:
        update_fields = []
        for field_name, field_value in process_defaults.items():
            current_value = getattr(process, field_name)
            if field_name in {'assessment_summary', 'description'}:
                if current_value or not field_value:
                    continue
            elif field_name in {'case_coordinator', 'start_date', 'target_completion_date'}:
                if current_value:
                    continue
            if current_value != field_value:
                setattr(process, field_name, field_value)
                update_fields.append(field_name)
        if update_fields:
            process.save(update_fields=update_fields)

    assessment_defaults = {'assessed_by': user} if user else {}
    assessment, _ = CaseAssessment.objects.get_or_create(
        due_diligence_process=process,
        defaults=assessment_defaults,
    )

    workflow = Workflow.objects.filter(contract=case).order_by('created_at').first()
    if workflow is None:
        Workflow.objects.create(
            title=f'Matching {case.title}',
            description='Automatisch overzicht voor de casusflow.',
            contract=case,
            created_by=user or case.created_by,
        )

    return process, assessment


def sync_case_flow_state(case, user=None):
    process, assessment = ensure_case_flow(case, user=user)

    desired_process_status = PHASE_TO_PROCESS_STATUS.get(case.case_phase, CaseIntakeProcess.ProcessStatus.INTAKE)
    if process.status != desired_process_status:
        process.status = desired_process_status
        process.save(update_fields=['status'])

    assessment_changed = False
    if case.case_phase in [CareCase.CasePhase.MATCHING, CareCase.CasePhase.PLAATSING, CareCase.CasePhase.ACTIEF, CareCase.CasePhase.AFGEROND]:
        if not assessment.matching_ready:
            assessment.matching_ready = True
            assessment_changed = True
        if assessment.assessment_status == CaseAssessment.AssessmentStatus.DRAFT:
            assessment.assessment_status = CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING
            assessment_changed = True
    elif case.case_phase == CareCase.CasePhase.BEOORDELING and assessment.assessment_status == CaseAssessment.AssessmentStatus.DRAFT:
        assessment.assessment_status = CaseAssessment.AssessmentStatus.UNDER_REVIEW
        assessment_changed = True
    if assessment_changed:
        assessment.save(update_fields=['matching_ready', 'assessment_status'])

    placement = process.indications.order_by('-updated_at', '-created_at').first()
    if case.client_id:
        if placement is None:
            placement = PlacementRequest.objects.create(
                due_diligence_process=process,
                proposed_provider=case.client,
                selected_provider=case.client,
                status=PlacementRequest.Status.APPROVED,
                care_form=process.preferred_care_form,
                start_date=case.start_date,
                decision_notes='Automatisch gekoppeld vanuit de casusflow.',
            )
        else:
            placement_updates = []
            if placement.proposed_provider_id != case.client_id:
                placement.proposed_provider = case.client
                placement_updates.append('proposed_provider')
            if placement.selected_provider_id != case.client_id:
                placement.selected_provider = case.client
                placement_updates.append('selected_provider')
            if placement.status != PlacementRequest.Status.APPROVED:
                placement.status = PlacementRequest.Status.APPROVED
                placement_updates.append('status')
            if not placement.care_form and process.preferred_care_form:
                placement.care_form = process.preferred_care_form
                placement_updates.append('care_form')
            if not placement.start_date and case.start_date:
                placement.start_date = case.start_date
                placement_updates.append('start_date')
            if placement_updates:
                placement.save(update_fields=placement_updates)

    sync_intake_auto_tasks(process, user=user)
    return process, assessment, placement


sync_contract_phase_auto_tasks = sync_case_phase_auto_tasks
get_contract_section_url = get_case_section_url
_coerce_contract_process_defaults = _coerce_case_process_defaults
ensure_contract_flow = ensure_case_flow
sync_contract_flow_state = sync_case_flow_state


def get_or_create_profile(user):
    profile, created = UserProfile.objects.get_or_create(user=user)
    return profile


def index(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return HttpResponse('DATABASE ERROR', status=503, content_type='text/plain')
    return HttpResponse("OK", content_type="text/plain")


def favicon(request):
    """Serve favicon.ico to avoid 404 errors. Returns 204 No Content."""
    return HttpResponse(status=204)


class TenantScopedQuerysetMixin:
    """Mixin to automatically scope querysets to the user's organization.

    Caches organization in request to avoid repeated lookups.
    Use self.get_organization() to access cached org in any view method.
    """
    def get_organization(self):
        """Get organization for current user, cached on request."""
        if not hasattr(self.request, '_cached_organization'):
            self.request._cached_organization = get_user_organization(self.request.user)
        return self.request._cached_organization

    def get_queryset(self):
        queryset = super().get_queryset()
        org = self.get_organization()
        return scope_queryset_for_organization(queryset, org)


class TenantAssignCreateMixin:
    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        return super().form_valid(form)


# ==================== CLIENT VIEWS ====================

class ClientListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Client
    template_name = 'contracts/client_list.html'
    context_object_name = 'clients'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        qs = scope_queryset_for_organization(Client.objects.all(), org)
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        client_type = self.request.GET.get('type')
        region_type = self.request.GET.get('region_type')
        region_id = self.request.GET.get('region')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(industry__icontains=q))
        if status:
            if status == 'REJECTED_OR_INFO':
                qs = qs.filter(status__in=[PlacementRequest.Status.REJECTED, PlacementRequest.Status.NEEDS_INFO])
            else:
                qs = qs.filter(status=status)
        if client_type:
            qs = qs.filter(client_type=client_type)
        if region_type:
            qs = qs.filter(provider_profile__served_regions__region_type=region_type)
        if region_id and region_id.isdigit():
            qs = qs.filter(provider_profile__served_regions__id=int(region_id))
        return qs.distinct().order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_clients = scope_queryset_for_organization(Client.objects.all(), org)
        client_stats = tenant_clients.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
        )
        ctx['total_clients'] = client_stats['total']
        ctx['active_clients'] = client_stats['active']
        ctx['search_query'] = self.request.GET.get('q', '')
        selected_region_type = self.request.GET.get('region_type', '')
        region_qs = RegionalConfiguration.objects.filter(organization=org)
        if selected_region_type:
            region_qs = region_qs.filter(region_type=selected_region_type)
        ctx['region_type_choices'] = RegionalConfiguration._meta.get_field('region_type').choices
        ctx['selected_region_type'] = selected_region_type
        ctx['selected_region'] = self.request.GET.get('region', '')
        ctx['region_choices'] = region_qs.order_by('region_name')
        return ctx


class ClientDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'contracts/client_detail.html'
    context_object_name = 'client'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Client.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        configurations = self.object.matters.all()[:10]
        case_records = self.object.contracts.all()[:10]
        ctx['configurations'] = configurations
        ctx['case_records'] = case_records
        ctx['documents'] = self.object.documents.all()[:10]

        profile = getattr(self.object, 'provider_profile', None)
        free_slots = 0
        waiting_days = 0
        capacity_status_label = 'Beperkt'
        capacity_status_badge = 'badge-capacity-limited'
        intake_timing_label = 'Intake op korte termijn'
        operational_status_line = 'Controleer capaciteit en casusfit voor toewijzing.'

        capability_rows = []
        why_passing = []
        constraints = []
        risk_signals = []

        case_fit_summary = {
            'label': 'Geen casus geselecteerd',
            'score': None,
            'details': ['Open matching met een casuscontext om fit direct te beoordelen.'],
        }
        selected_intake = None

        if profile:
            free_slots = max(profile.max_capacity - profile.current_capacity, 0)
            waiting_days = profile.average_wait_days or 0

            if free_slots <= 0 and profile.max_capacity > 0:
                capacity_status_label = 'Vol'
                capacity_status_badge = 'badge-capacity-full'
                intake_timing_label = 'Intake tijdelijk niet beschikbaar'
                operational_status_line = 'Geen vrije plek; alternatieve aanbieder nodig.'
            elif free_slots <= 2:
                capacity_status_label = 'Beperkt'
                capacity_status_badge = 'badge-capacity-limited'
                intake_timing_label = 'Intake beperkt beschikbaar'
                operational_status_line = 'Beperkte ruimte; snel beslissen aanbevolen.'
            else:
                capacity_status_label = 'Actief'
                capacity_status_badge = 'badge-capacity-open'
                intake_timing_label = 'Intake direct mogelijk'
                operational_status_line = 'Capaciteit beschikbaar voor directe plaatsing.'

            if waiting_days > 21:
                intake_timing_label = 'Intake met wachttijd'

            offered_forms = []
            if profile.offers_outpatient:
                offered_forms.append('Ambulant')
            if profile.offers_day_treatment:
                offered_forms.append('Dagbehandeling')
            if profile.offers_residential:
                offered_forms.append('Residentieel')
            if profile.offers_crisis:
                offered_forms.append('Crisisopvang')

            supported_urgency = []
            if profile.handles_low_urgency:
                supported_urgency.append('Laag')
            if profile.handles_medium_urgency:
                supported_urgency.append('Middel')
            if profile.handles_high_urgency:
                supported_urgency.append('Hoog')
            if profile.handles_crisis_urgency:
                supported_urgency.append('Crisis')

            complexity_support = []
            if profile.handles_simple:
                complexity_support.append('Enkelvoudig')
            if profile.handles_multiple:
                complexity_support.append('Meervoudig')
            if profile.handles_severe:
                complexity_support.append('Zwaar')

            ages = []
            if profile.target_age_0_4:
                ages.append('0-4')
            if profile.target_age_4_12:
                ages.append('4-12')
            if profile.target_age_12_18:
                ages.append('12-18')
            if profile.target_age_18_plus:
                ages.append('18+')

            capability_rows = [
                ('Zorgvormen', ', '.join(offered_forms) if offered_forms else 'Niet gespecificeerd'),
                ('Urgentie', ', '.join(supported_urgency) if supported_urgency else 'Niet gespecificeerd'),
                ('Complexiteit', ', '.join(complexity_support) if complexity_support else 'Niet gespecificeerd'),
                ('Doelgroep leeftijd', ', '.join(ages) if ages else 'Niet gespecificeerd'),
                ('Dienstgebied', profile.service_area or self.object.city or 'Niet gespecificeerd'),
            ]

            why_passing = [
                f'{free_slots} vrije plek(ken) beschikbaar' if free_slots > 0 else 'Capaciteit momenteel vol',
                f'Gemiddelde wachttijd: {waiting_days} dagen',
                'Profiel matchbaar op zorgvorm en urgentie',
            ]

            if profile.special_facilities:
                why_passing.append('Beschikt over aanvullende faciliteiten')

            if free_slots <= 0:
                constraints.append('Geen vrije plekken beschikbaar')
                risk_signals.append('Capaciteit is volledig benut')
            if waiting_days > 28:
                constraints.append('Wachttijd boven 4 weken')
                risk_signals.append('Verhoogde wachttijd voor intake')
            if not profile.offers_crisis:
                constraints.append('Geen crisisopvang in profiel')
            if not profile.special_facilities:
                constraints.append('Speciale faciliteiten niet gespecificeerd')

            intake_raw = (self.request.GET.get('intake') or '').strip()
            if intake_raw.isdigit():
                selected_intake = CaseIntakeProcess.objects.filter(
                    organization=self.object.organization,
                    pk=int(intake_raw),
                ).first()

            if selected_intake:
                form_fit = {
                    str(CaseIntakeProcess.CareForm.OUTPATIENT): profile.offers_outpatient,
                    str(CaseIntakeProcess.CareForm.DAY_TREATMENT): profile.offers_day_treatment,
                    str(CaseIntakeProcess.CareForm.RESIDENTIAL): profile.offers_residential,
                    str(CaseIntakeProcess.CareForm.CRISIS): profile.offers_crisis,
                }.get(str(selected_intake.preferred_care_form), False)
                urgency_fit = {
                    str(CaseIntakeProcess.Urgency.LOW): profile.handles_low_urgency,
                    str(CaseIntakeProcess.Urgency.MEDIUM): profile.handles_medium_urgency,
                    str(CaseIntakeProcess.Urgency.HIGH): profile.handles_high_urgency,
                    str(CaseIntakeProcess.Urgency.CRISIS): profile.handles_crisis_urgency,
                }.get(str(selected_intake.urgency), False)

                category_fit = False
                if selected_intake.care_category_main_id:
                    category_fit = profile.target_care_categories.filter(id=selected_intake.care_category_main_id).exists()

                fit_points = [form_fit, urgency_fit, category_fit]
                fit_score = int((sum(1 for p in fit_points if p) / 3) * 100)
                case_fit_summary = {
                    'label': f'Casus {selected_intake.pk}: {selected_intake.title}',
                    'score': fit_score,
                    'details': [
                        f'Zorgvorm fit: {'Ja' if form_fit else 'Nee'}',
                        f'Urgentie fit: {'Ja' if urgency_fit else 'Nee'}',
                        f'Categorie fit: {'Ja' if category_fit else 'Nee'}',
                    ],
                }
            else:
                case_fit_summary = {
                    'label': 'Geen casus geselecteerd',
                    'score': None,
                    'details': [
                        'Open deze aanbieder vanuit matching voor directe casusfit.',
                        'Gebruik Wijs toe om terug te gaan naar casusgerichte toewijzing.',
                    ],
                }

        track_record = {
            'active_cases': int(self.object.total_billed),
            'open_cases': int(self.object.outstanding_balance),
            'active_configurations': self.object.active_matters_count,
        }

        ctx['provider_profile'] = profile
        ctx['provider_free_slots'] = free_slots
        ctx['provider_wait_days'] = waiting_days
        ctx['provider_capacity_status_label'] = capacity_status_label
        ctx['provider_capacity_status_badge'] = capacity_status_badge
        ctx['provider_intake_timing_label'] = intake_timing_label
        ctx['provider_operational_status_line'] = operational_status_line
        ctx['provider_capability_rows'] = capability_rows
        ctx['provider_why_passing'] = why_passing
        ctx['provider_constraints'] = constraints
        ctx['provider_risk_signals'] = risk_signals
        ctx['selected_intake'] = selected_intake
        ctx['case_fit_summary'] = case_fit_summary
        ctx['provider_track_record'] = track_record
        return ctx


class ClientCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'contracts/client_form.html'
    success_url = reverse_lazy('careon:client_list')

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        profile, _ = ProviderProfile.objects.get_or_create(client=self.object)
        profile.served_regions.set(form.cleaned_data.get('served_regions', []))
        log_action(self.request.user, 'CREATE', 'Client', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Aanbieder "{self.object.name}" is aangemaakt.')
        return response

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        form.fields['served_regions'].queryset = RegionalConfiguration.objects.filter(organization=org).order_by('region_type', 'region_name')
        return form


class ClientUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'contracts/client_form.html'
    success_url = reverse_lazy('careon:client_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Client.objects.all(), org)

    def form_valid(self, form):
        response = super().form_valid(form)
        profile, _ = ProviderProfile.objects.get_or_create(client=self.object)
        profile.served_regions.set(form.cleaned_data.get('served_regions', []))
        log_action(self.request.user, 'UPDATE', 'Client', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Aanbieder "{self.object.name}" is bijgewerkt.')
        return response

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        form.fields['served_regions'].queryset = RegionalConfiguration.objects.filter(organization=org).order_by('region_type', 'region_name')
        return form


# ==================== CONFIGURATION VIEWS ====================

def get_configuration_scope_content(scope):
    if scope == CareConfiguration.Scope.REGIO:
        return {
            'entity_label': 'Regioconfiguratie',
            'entity_label_lower': 'regioconfiguratie',
            'page_title': 'Regioconfiguratie',
            'page_subtitle': 'Beheer regionale capaciteit, aanbieders en wachtnormen.',
            'create_label': 'Nieuwe regioconfiguratie',
            'search_placeholder': 'Zoek regioconfiguratie...',
            'empty_label': 'Geen regioconfiguraties gevonden.',
            'detail_title': 'Regioconfiguratie',
            'detail_subtitle': 'Regionale afspraken over capaciteit, wachttijd en aanbieders.',
            'form_title_create': 'Nieuwe regioconfiguratie',
            'form_title_update': 'Bewerk regioconfiguratie',
            'submit_label_create': 'Aanmaken regioconfiguratie',
            'submit_label_update': 'Bijwerken regioconfiguratie',
        }
    return {
        'entity_label': 'Gemeenteconfiguratie',
        'entity_label_lower': 'gemeenteconfiguratie',
        'page_title': 'Gemeenteconfiguratie',
        'page_subtitle': 'Beheer gemeentelijke capaciteit, aanbieders en wachtnormen.',
        'create_label': 'Nieuwe gemeenteconfiguratie',
        'search_placeholder': 'Zoek gemeenteconfiguratie...',
        'empty_label': 'Geen gemeenteconfiguraties gevonden.',
        'detail_title': 'Gemeenteconfiguratie',
        'detail_subtitle': 'Lokale afspraken over capaciteit, wachttijd en aanbieders.',
        'form_title_create': 'Nieuwe gemeenteconfiguratie',
        'form_title_update': 'Bewerk gemeenteconfiguratie',
        'submit_label_create': 'Aanmaken gemeenteconfiguratie',
        'submit_label_update': 'Bijwerken gemeenteconfiguratie',
    }

_SCOPE_QUERY_ALIASES = {
    'gemeente': CareConfiguration.Scope.GEMEENTE,
    'gemeenten': CareConfiguration.Scope.GEMEENTE,
    CareConfiguration.Scope.GEMEENTE: CareConfiguration.Scope.GEMEENTE,
    'regio': CareConfiguration.Scope.REGIO,
    'regios': CareConfiguration.Scope.REGIO,
    "regio's": CareConfiguration.Scope.REGIO,
    CareConfiguration.Scope.REGIO: CareConfiguration.Scope.REGIO,
}


class CareConfigurationDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = CareConfiguration
    template_name = 'contracts/configuration_detail.html'
    context_object_name = 'configuration'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(CareConfiguration.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        case_records = self.object.contracts.all()
        ctx['case_records'] = case_records
        ctx['linked_providers'] = self.object.linked_providers.all().order_by('name')
        ctx['documents'] = self.object.documents.all()[:10]
        ctx['time_entries'] = []
        ctx['tasks'] = self.object.tasks.all()[:10]
        ctx['deadlines'] = self.object.deadlines.filter(is_completed=False)[:10]
        ctx['risks'] = self.object.risks.all()[:10]
        ctx.update(get_configuration_scope_content(self.object.scope))
        return ctx


class CareConfigurationCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = CareConfiguration
    form_class = CareConfigurationForm
    template_name = 'contracts/configuration_form.html'

    def get_initial(self):
        initial = super().get_initial()
        raw_scope = (self.request.GET.get('scope') or '').strip()
        normalized_scope = _SCOPE_QUERY_ALIASES.get(raw_scope, _SCOPE_QUERY_ALIASES.get(raw_scope.upper()))
        if normalized_scope:
            initial['scope'] = normalized_scope
        client_id = (self.request.GET.get('client') or '').strip()
        if client_id.isdigit():
            org = get_user_organization(self.request.user)
            client = scope_queryset_for_organization(Client.objects.all(), org).filter(pk=int(client_id)).first()
            if client:
                initial['linked_providers'] = [client.pk]
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        scope = ctx['form'].initial.get('scope') or CareConfiguration.Scope.GEMEENTE
        ctx.update(get_configuration_scope_content(scope))
        ctx['cancel_url'] = reverse('careon:regional_list') if scope == CareConfiguration.Scope.REGIO else reverse('careon:municipality_list')
        ctx['is_edit'] = False
        selected_provider_ids = ctx['form'].initial.get('linked_providers') or []
        ctx['prefilled_provider'] = ctx['form'].fields['linked_providers'].queryset.filter(pk__in=selected_provider_ids).first()
        return ctx

    def get_success_url(self):
        return reverse('careon:configuration_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        form.instance.status = CareConfiguration.Status.ACTIVE if form.cleaned_data.get('is_active') else CareConfiguration.Status.ON_HOLD
        response = super().form_valid(form)
        if not self.object.client_id and self.object.linked_providers.exists():
            self.object.client = self.object.linked_providers.first()
            self.object.save(update_fields=['client'])
        log_action(self.request.user, 'CREATE', 'CareConfiguration', self.object.id, str(self.object), request=self.request)
        scope_content = get_configuration_scope_content(self.object.scope)
        messages.success(self.request, f'{scope_content["entity_label"]} "{self.object.title}" aangemaakt.')
        return response


class CareConfigurationUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = CareConfiguration
    form_class = CareConfigurationForm
    template_name = 'contracts/configuration_form.html'

    def get_success_url(self):
        return reverse('careon:configuration_detail', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(CareConfiguration.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_configuration_scope_content(self.object.scope))
        ctx['cancel_url'] = reverse('careon:regional_list') if self.object.scope == CareConfiguration.Scope.REGIO else reverse('careon:municipality_list')
        ctx['is_edit'] = True
        return ctx

    def form_valid(self, form):
        form.instance.status = CareConfiguration.Status.ACTIVE if form.cleaned_data.get('is_active') else CareConfiguration.Status.ON_HOLD
        response = super().form_valid(form)
        if not self.object.client_id and self.object.linked_providers.exists():
            self.object.client = self.object.linked_providers.first()
            self.object.save(update_fields=['client'])
        log_action(self.request.user, 'UPDATE', 'CareConfiguration', self.object.id, str(self.object), request=self.request)
        scope_content = get_configuration_scope_content(self.object.scope)
        messages.success(self.request, f'{scope_content["entity_label"]} "{self.object.title}" bijgewerkt.')
        return response


# ==================== DOCUMENT VIEWS ====================

class DocumentListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Document
    template_name = 'contracts/document_list.html'
    context_object_name = 'documents'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            Document.objects.select_related('contract', 'matter', 'client', 'uploaded_by'),
            org,
        )
        q = self.request.GET.get('q')
        doc_type = self.request.GET.get('type')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(tags__icontains=q))
        if doc_type:
            qs = qs.filter(document_type=doc_type)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        all_docs = scope_queryset_for_organization(Document.objects.all(), org)
        editable_document_ids = set()
        document_rows = []
        for doc in ctx['documents']:
            case_href = None
            intake = None
            if doc.contract:
                intake = getattr(doc.contract, 'due_diligence_process', None)
                if intake:
                    case_href = _case_detail_tab_href(intake.pk, 'documenten')

            if not doc.contract or can_access_case_action(self.request.user, doc.contract, CaseAction.EDIT):
                editable_document_ids.add(doc.pk)

            document_rows.append({
                'document': doc,
                'case_href': case_href,
                'can_edit': doc.pk in editable_document_ids,
            })

        ctx.update({
            'total_documents': all_docs.count(),
            'review_documents': all_docs.filter(status=Document.Status.REVIEW).count(),
            'draft_documents': all_docs.filter(status=Document.Status.DRAFT).count(),
            'editable_document_ids': editable_document_ids,
            'document_rows': document_rows,
        })
        return ctx


class DocumentDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Document
    template_name = 'contracts/document_detail.html'
    context_object_name = 'document'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(Document.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['versions'] = Document.objects.filter(parent_document=self.object).order_by('-version')
        ctx['can_edit_document'] = (not self.object.contract) or can_access_case_action(
            self.request.user,
            self.object.contract,
            CaseAction.EDIT,
        )
        return ctx


class DocumentCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = 'contracts/document_form.html'
    success_url = reverse_lazy('careon:document_list')

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        if form.instance.contract and not can_access_case_action(self.request.user, form.instance.contract, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om documenten aan deze casus toe te voegen.')
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Document', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Document "{self.object.title}" is toegevoegd.')
        return response


class DocumentUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Document
    form_class = DocumentForm
    template_name = 'contracts/document_form.html'
    success_url = reverse_lazy('careon:document_list')

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(Document.objects.all(), org)

    def dispatch(self, request, *args, **kwargs):
        document = self.get_object()
        if document.contract and not can_access_case_action(request.user, document.contract, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om documenten van deze casus te bewerken.')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Document', self.object.id, str(self.object), request=self.request)
        return response


# ==================== DEADLINE VIEWS ====================

class DeadlineListView(LoginRequiredMixin, ListView):
    model = Deadline
    template_name = 'contracts/deadline_list.html'
    context_object_name = 'deadlines'
    paginate_by = 25

    def get_organization(self):
        """Get organization for current user, cached on request."""
        if not hasattr(self.request, '_cached_organization'):
            self.request._cached_organization = get_user_organization(self.request.user)
        return self.request._cached_organization

    def get_queryset(self):
        org = self.get_organization()
        sync_automatic_deadlines_for_organization(org, user=self.request.user)
        qs = Deadline.objects.select_related('due_diligence_process', 'assigned_to', 'case_record').for_organization(org)
        show = self.request.GET.get('show', 'mine')
        if show == 'mine':
            qs = qs.filter(assigned_to=self.request.user, is_completed=False)
        elif show == 'today':
            qs = qs.filter(is_completed=False, due_date=date.today())
        elif show == 'overdue':
            qs = qs.filter(is_completed=False, due_date__lt=date.today())
        elif show == 'high':
            qs = qs.filter(is_completed=False, priority__in=[Deadline.Priority.HIGH, Deadline.Priority.URGENT])
        elif show == 'all':
            pass
        else:
            qs = qs.filter(assigned_to=self.request.user, is_completed=False)

        owner = self.request.GET.get('owner', 'all')
        if owner == 'mine':
            qs = qs.filter(assigned_to=self.request.user)

        priority_rank = models.Case(
            models.When(priority=Deadline.Priority.URGENT, then=models.Value(0)),
            models.When(priority=Deadline.Priority.HIGH, then=models.Value(1)),
            models.When(priority=Deadline.Priority.MEDIUM, then=models.Value(2)),
            default=models.Value(3),
            output_field=models.IntegerField(),
        )
        return qs.annotate(priority_rank=priority_rank).order_by('is_completed', 'priority_rank', 'due_date', 'due_time')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        org_deadlines = Deadline.objects.for_organization(org)
        owner = self.request.GET.get('owner', 'all')
        stats_qs = org_deadlines
        if owner == 'mine':
            stats_qs = stats_qs.filter(assigned_to=self.request.user)

        today_value = date.today()
        ctx['today_count'] = stats_qs.filter(is_completed=False, due_date=today_value).count()
        ctx['overdue_count'] = stats_qs.filter(is_completed=False, due_date__lt=today_value).count()
        ctx['high_priority_count'] = stats_qs.filter(is_completed=False, priority__in=[Deadline.Priority.HIGH, Deadline.Priority.URGENT]).count()
        ctx['my_open_count'] = org_deadlines.filter(assigned_to=self.request.user, is_completed=False).count()
        ctx['all_count'] = stats_qs.count()
        ctx['completed_count'] = stats_qs.filter(is_completed=True).count()
        ctx['show'] = self.request.GET.get('show', 'mine')
        ctx['owner'] = owner
        ctx['today'] = today_value
        task_rows = []
        for deadline in ctx['deadlines']:
            if deadline.is_completed:
                row_status = 'Afgerond'
                row_status_class = 'bg-green-100 text-green-800'
            elif deadline.is_overdue:
                row_status = 'Te laat'
                row_status_class = 'bg-red-100 text-red-800'
            elif deadline.due_date == today_value:
                row_status = 'Vandaag'
                row_status_class = 'bg-orange-100 text-orange-800'
            else:
                row_status = 'Open'
                row_status_class = 'bg-blue-100 text-blue-800'

            linked_case = None
            if deadline.intake:
                linked_case = getattr(deadline.intake, 'contract', None)
                open_href = _case_detail_tab_href(deadline.intake.pk, 'taken')
                case_title = deadline.intake.title
            elif deadline.case_record:
                linked_case = deadline.case_record
                open_href = reverse('careon:case_detail', kwargs={'pk': deadline.case_record.pk})
                case_title = deadline.case_record.title
            else:
                open_href = None
                case_title = 'Niet gekoppeld'

            if deadline.priority == Deadline.Priority.URGENT:
                priority_class = 'bg-red-100 text-red-800'
            elif deadline.priority == Deadline.Priority.HIGH:
                priority_class = 'bg-orange-100 text-orange-800'
            elif deadline.priority == Deadline.Priority.MEDIUM:
                priority_class = 'bg-yellow-100 text-yellow-800'
            else:
                priority_class = 'bg-gray-100 text-gray-600'

            task_rows.append({
                'deadline': deadline,
                'case_title': case_title,
                'open_href': open_href,
                'row_status': row_status,
                'row_status_class': row_status_class,
                'priority_class': priority_class,
                'can_edit': (linked_case is None) or can_access_case_action(self.request.user, linked_case, CaseAction.EDIT),
            })

        ctx['task_rows'] = task_rows
        return ctx


class DeadlineCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('careon:deadline_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['due_diligence_process'].queryset = CaseIntakeProcess.objects.filter(
                organization=org
            ).order_by('-updated_at')
            form.fields['assigned_to'].queryset = User.objects.filter(
                organization_memberships__organization=org,
                organization_memberships__is_active=True,
            ).distinct().order_by('first_name', 'last_name', 'username')
        else:
            form.fields['due_diligence_process'].queryset = CaseIntakeProcess.objects.none()
            form.fields['assigned_to'].queryset = User.objects.none()

        selected_case = self.request.GET.get('case')
        if selected_case and selected_case.isdigit():
            form.initial['due_diligence_process'] = int(selected_case)
        return form

    def form_valid(self, form):
        intake = form.instance.intake
        if intake and not _can_edit_intake(self.request.user, intake):
            return HttpResponseForbidden('Je hebt geen rechten om opvolgtaken voor deze casus toe te voegen.')
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        if self.object.generation_source == Deadline.GenerationSource.MANUAL:
            self.object.generation_source = Deadline.GenerationSource.MANUAL
            self.object.save(update_fields=['generation_source'])
        log_action(self.request.user, 'CREATE', 'OpvolgingTaak', self.object.id, str(self.object), request=self.request)
        return response


class DeadlineUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('careon:deadline_list')

    def get_queryset(self):
        org = self.get_organization()
        if not org:
            return Deadline.objects.none()
        return Deadline.objects.for_organization(org)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['due_diligence_process'].queryset = CaseIntakeProcess.objects.filter(
                organization=org
            ).order_by('-updated_at')
            form.fields['assigned_to'].queryset = User.objects.filter(
                organization_memberships__organization=org,
                organization_memberships__is_active=True,
            ).distinct().order_by('first_name', 'last_name', 'username')
        else:
            form.fields['due_diligence_process'].queryset = CaseIntakeProcess.objects.none()
            form.fields['assigned_to'].queryset = User.objects.none()
        return form

    def dispatch(self, request, *args, **kwargs):
        deadline = self.get_object()
        linked_case = _resolve_deadline_case(deadline)
        if linked_case and not can_access_case_action(request.user, linked_case, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om opvolgtaken van deze casus te bewerken.')
        return super().dispatch(request, *args, **kwargs)


@login_required
@require_POST
def deadline_complete(request, pk):
    # Cache org on request for consistency
    if not hasattr(request, '_cached_organization'):
        request._cached_organization = get_user_organization(request.user)
    organization = request._cached_organization

    deadline_qs = Deadline.objects.for_organization(organization)
    deadline = get_object_or_404(deadline_qs, pk=pk)
    linked_case = _resolve_deadline_case(deadline)
    if linked_case and not can_access_case_action(request.user, linked_case, CaseAction.EDIT):
        return HttpResponseForbidden('Je hebt geen rechten om opvolgtaken van deze casus af te ronden.')
    deadline.is_completed = True
    deadline.completed_at = timezone.now()
    deadline.completed_by = request.user
    deadline.save()
    log_action(request.user, 'UPDATE', 'OpvolgingTaak', deadline.id, str(deadline), request=request)
    messages.success(request, f'Taak "{deadline.title}" gemarkeerd als afgerond.')
    return _redirect_to_safe_next_or_default(request, reverse('careon:deadline_list'))


@login_required
@require_POST
def signal_update_status(request, pk):
    if not hasattr(request, '_cached_organization'):
        request._cached_organization = get_user_organization(request.user)
    organization = request._cached_organization

    signal_qs = CareSignal.objects.for_organization(organization).select_related('due_diligence_process', 'case_record')
    signal = get_object_or_404(signal_qs, pk=pk)

    linked_case = _resolve_signal_case(signal)
    if linked_case and not can_access_case_action(request.user, linked_case, CaseAction.EDIT):
        return HttpResponseForbidden('Je hebt geen rechten om signalen van deze casus te wijzigen.')

    status = request.POST.get('status')
    valid_statuses = {
        CareSignal.SignalStatus.OPEN,
        CareSignal.SignalStatus.IN_PROGRESS,
        CareSignal.SignalStatus.RESOLVED,
    }
    if status not in valid_statuses:
        messages.error(request, 'Ongeldige signaalstatus.')
        fallback_url = reverse('careon:signal_detail', kwargs={'pk': signal.pk})
        if signal.due_diligence_process_id:
            fallback_url = f"{reverse('careon:case_detail', kwargs={'pk': signal.due_diligence_process_id})}?tab=signalen"
        return _redirect_to_safe_next_or_default(request, fallback_url)

    if signal.status != status:
        signal.status = status
        signal.save(update_fields=['status', 'updated_at'])
        log_action(
            request.user,
            'UPDATE',
            'CareSignal',
            signal.id,
            str(signal),
            changes={'status': status},
            request=request,
        )
        messages.success(request, 'Signaalstatus bijgewerkt.')
    else:
        messages.info(request, 'Signaalstatus was al up-to-date.')

    fallback_url = reverse('careon:signal_detail', kwargs={'pk': signal.pk})
    if signal.due_diligence_process_id:
        fallback_url = f"{reverse('careon:case_detail', kwargs={'pk': signal.due_diligence_process_id})}?tab=signalen"
    return _redirect_to_safe_next_or_default(request, fallback_url)


# ==================== AUDIT LOG VIEW ====================

class AuditLogListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = AuditLog
    template_name = 'contracts/audit_log_list.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related('user')
        action = self.request.GET.get('action')
        model = self.request.GET.get('model')
        if action:
            qs = qs.filter(action=action)
        if model:
            qs = qs.filter(model_name=model)
        return qs.order_by('-timestamp')


# ==================== NOTIFICATION VIEWS ====================

@login_required
def notification_list(request):
    all_notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    unread_count = all_notifications.filter(is_read=False).count()
    notifications = all_notifications[:50]
    return render(request, 'contracts/notification_list.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save()
    if notification.link:
        return redirect(notification.link)
    return redirect('careon:notification_list')


@login_required
@require_POST
def mark_all_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect('careon:notification_list')


@login_required
@require_POST
def switch_organization(request):
    org_id = request.POST.get('organization_id')
    membership = (
        OrganizationMembership.objects
        .filter(
            user=request.user,
            is_active=True,
            organization__is_active=True,
            organization_id=org_id,
        )
        .select_related('organization')
        .first()
    )
    if membership:
        request.session['active_organization_id'] = membership.organization_id
        log_action(
            request.user,
            AuditLog.Action.UPDATE,
            'OrganizationMembership',
            object_id=membership.id,
            object_repr=str(membership),
            changes={'event': 'switch_organization', 'organization_id': membership.organization_id},
            request=request,
        )
        messages.success(request, f'Overgeschakeld naar {membership.organization.name}.')
    else:
        messages.error(request, 'Je hebt geen toegang tot die organisatie.')
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))



def _build_invite_url(request, invitation):
    return request.build_absolute_uri(
        reverse('careon:accept_organization_invite', kwargs={'token': invitation.token})
    )


def _send_invitation_email(invitation, invite_url):
    subject = f"Uitnodiging voor {invitation.organization.name}"
    body = (
        f"Je bent uitgenodigd om deel te nemen aan {invitation.organization.name} als {invitation.get_role_display()}.\n\n"
        f"Accepteer uitnodiging: {invite_url}\n\n"
        "Deze link verloopt over 7 dagen."
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
        messages.error(request, 'Geen actieve organisatie gevonden.')
        return redirect('dashboard')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Alleen organisatie-eigenaren of beheerders kunnen teamuitnodigingen beheren.')

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
                messages.warning(request, f'{email} is al een actief lid van deze organisatie.')
                return redirect('careon:organization_team')

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
                messages.info(request, f'Er bestaat al een actieve uitnodiging voor {email}: {invite_url}')
                return redirect('careon:organization_team')

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
                messages.success(request, f'Uitnodiging aangemaakt en verzonden naar {email}. Link: {invite_url}')
            except Exception:
                messages.warning(request, f'Uitnodiging aangemaakt voor {email}, maar e-mailbezorging mislukte. Deel deze link handmatig: {invite_url}')
            return redirect('careon:organization_team')
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
        return HttpResponseForbidden('Onvoldoende rechten.')

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
        messages.success(request, f'Uitnodiging voor {invitation.email} is ingetrokken.')
    else:
        messages.info(request, 'Alleen openstaande uitnodigingen kunnen worden ingetrokken.')
    return redirect('careon:organization_team')


@login_required
@require_POST
def resend_organization_invite(request, invite_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Onvoldoende rechten.')

    invitation = get_object_or_404(OrganizationInvitation, id=invite_id, organization=organization)
    if invitation.status != OrganizationInvitation.Status.PENDING:
        messages.info(request, 'Alleen openstaande uitnodigingen kunnen opnieuw worden verzonden.')
        return redirect('careon:organization_team')

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
        messages.success(request, f'Uitnodiging opnieuw verzonden naar {new_invitation.email}.')
    except Exception:
        messages.warning(request, f'Nieuwe uitnodiging aangemaakt, maar e-mailbezorging mislukte. Deel deze link handmatig: {invite_url}')
    return redirect('careon:organization_team')


@login_required
@require_POST
def update_membership_role(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Onvoldoende rechten.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization, is_active=True)
    requested_role = request.POST.get('role')
    allowed_roles = {choice[0] for choice in OrganizationMembership.Role.choices}
    if requested_role not in allowed_roles:
        messages.error(request, 'Ongeldige rolselectie.')
        return redirect('careon:organization_team')

    actor_is_owner = is_organization_owner(request.user, organization)
    if requested_role == OrganizationMembership.Role.OWNER and not actor_is_owner:
        messages.error(request, 'Alleen organisatie-eigenaren kunnen de rol Eigenaar toekennen.')
        return redirect('careon:organization_team')

    if membership.user_id == request.user.id and membership.role == OrganizationMembership.Role.OWNER and requested_role != OrganizationMembership.Role.OWNER:
        owner_count = OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
        ).count()
        if owner_count <= 1:
            messages.error(request, 'Er moet minimaal een actieve eigenaar in de organisatie overblijven.')
            return redirect('careon:organization_team')

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
    messages.success(request, f'Rol bijgewerkt voor {membership.user.email or membership.user.username}.')
    return redirect('careon:organization_team')


@login_required
@require_POST
def deactivate_organization_member(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Onvoldoende rechten.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization, is_active=True)
    if membership.user_id == request.user.id:
        messages.error(request, 'Je kunt je eigen lidmaatschap niet deactiveren.')
        return redirect('careon:organization_team')

    if membership.role == OrganizationMembership.Role.OWNER:
        owner_count = OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
        ).count()
        if owner_count <= 1:
            messages.error(request, 'Er moet minimaal een actieve eigenaar in de organisatie overblijven.')
            return redirect('careon:organization_team')

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
    messages.success(request, f'Lidmaatschap gedeactiveerd voor {membership.user.email or membership.user.username}.')
    return redirect('careon:organization_team')


@login_required
@require_POST
def reactivate_organization_member(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Onvoldoende rechten.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization)
    if membership.is_active:
        messages.info(request, 'Dit lidmaatschap is al actief.')
        return redirect('careon:organization_team')

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
    messages.success(request, f'Lidmaatschap opnieuw geactiveerd voor {membership.user.email or membership.user.username}.')
    return redirect('careon:organization_team')


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
        messages.error(request, 'Geen actieve organisatie gevonden.')
        return redirect('dashboard')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Alleen organisatie-eigenaren of beheerders kunnen organisatieactiviteit bekijken.')

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
        messages.error(request, 'Geen actieve organisatie gevonden.')
        return redirect('dashboard')

    if not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Alleen organisatie-eigenaren of beheerders kunnen organisatieactiviteit exporteren.')

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
def accept_organization_invite(request, token):
    invitation = get_object_or_404(
        OrganizationInvitation.objects.select_related('organization'),
        token=token,
    )

    if invitation.status != OrganizationInvitation.Status.PENDING:
        messages.error(request, 'Deze uitnodiging is niet meer geldig.')
        return redirect('dashboard')

    if invitation.expires_at and invitation.expires_at <= timezone.now():
        invitation.status = OrganizationInvitation.Status.EXPIRED
        invitation.save(update_fields=['status'])
        messages.error(request, 'Deze uitnodiging is verlopen.')
        return redirect('dashboard')

    user_email = (request.user.email or '').strip().lower()
    if not user_email or user_email != invitation.email.lower():
        messages.error(request, f'Deze uitnodiging is voor {invitation.email}. Log in met dat e-mailadres.')
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
    messages.success(request, f'Je bent toegevoegd aan {invitation.organization.name}.')
    return redirect('dashboard')


# ==================== REPORTS VIEW ====================

@login_required
def reports_dashboard(request):
    today = date.today()
    org = get_user_organization(request.user)

    # UI filters
    attention_filter = request.GET.get('attention', 'all')
    domain_filter = request.GET.get('domain', '')
    region_type_filter = request.GET.get('region_type', '')
    region_filter = request.GET.get('region', '')
    try:
        stagnation_days = int(request.GET.get('stagnation_days', 21))
    except (TypeError, ValueError):
        stagnation_days = 21
    stagnation_days = max(7, min(stagnation_days, 120))

    case_records_qs = scope_queryset_for_organization(CareCase.objects.all(), org)
    clients_qs = scope_queryset_for_organization(Client.objects.all(), org)
    configurations_qs = scope_queryset_for_organization(CareConfiguration.objects.all(), org)

    if org:
        cases_qs = CaseIntakeProcess.objects.filter(organization=org)
        indications_qs = PlacementRequest.objects.filter(due_diligence_process__organization=org)
        risks_qs = CareSignal.objects.for_organization(org)
        provider_profiles_qs = ProviderProfile.objects.filter(client__organization=org)
        waittime_qs = TrustAccount.objects.filter(provider__organization=org).select_related('provider')
    else:
        cases_qs = CaseIntakeProcess.objects.none()
        indications_qs = PlacementRequest.objects.none()
        risks_qs = CareSignal.objects.none()
        provider_profiles_qs = ProviderProfile.objects.none()
        waittime_qs = TrustAccount.objects.none()

    if domain_filter:
        configurations_qs = configurations_qs.filter(care_domains__id=domain_filter)
        case_records_qs = case_records_qs.filter(matter__care_domains__id=domain_filter)

    if region_type_filter:
        cases_qs = cases_qs.filter(preferred_region_type=region_type_filter)
    if region_filter.isdigit():
        cases_qs = cases_qs.filter(preferred_region_id=int(region_filter))

    # KPI 1: Casussen zonder match
    matched_case_ids = indications_qs.filter(selected_provider__isnull=False).values_list('due_diligence_process_id', flat=True)
    unmatched_cases_qs = (
        cases_qs
        .filter(status__in=[CaseIntakeProcess.ProcessStatus.MATCHING, CaseIntakeProcess.ProcessStatus.DECISION])
        .exclude(id__in=matched_case_ids)
        .select_related('case_coordinator', 'care_category_main')
        .order_by('target_completion_date', '-updated_at')
    )
    cases_without_match_count = unmatched_cases_qs.count()

    # KPI 2: Gemiddelde wachttijd (dagen)
    avg_wait_days = waittime_qs.aggregate(avg=Avg('wait_days'))['avg']
    if avg_wait_days is None:
        avg_wait_days = provider_profiles_qs.aggregate(avg=Avg('average_wait_days'))['avg'] or 0

    # KPI 3: Stagnaties (> X dagen)
    stagnation_limit_date = today - timedelta(days=stagnation_days)
    stagnated_cases_qs = (
        cases_qs
        .filter(
            status__in=[
                CaseIntakeProcess.ProcessStatus.INTAKE,
                CaseIntakeProcess.ProcessStatus.ASSESSMENT,
                CaseIntakeProcess.ProcessStatus.MATCHING,
                CaseIntakeProcess.ProcessStatus.DECISION,
            ],
            start_date__lt=stagnation_limit_date,
        )
        .select_related('case_coordinator', 'care_category_main')
        .order_by('start_date')
    )
    stagnation_count = stagnated_cases_qs.count()

    # KPI 4: Escalaties
    escalation_qs = (
        risks_qs
        .filter(status__in=[CareSignal.SignalStatus.OPEN, CareSignal.SignalStatus.IN_PROGRESS])
        .filter(Q(signal_type=CareSignal.SignalType.ESCALATION) | Q(risk_level__in=[CareSignal.RiskLevel.HIGH, CareSignal.RiskLevel.CRITICAL]))
        .select_related('due_diligence_process', 'assigned_to')
        .order_by('-updated_at')
    )
    escalation_count = escalation_qs.count()

    # Aanbieders zonder capaciteit
    no_capacity_qs = waittime_qs.filter(open_slots__lte=0).order_by('-waiting_list_size', '-wait_days')

    # AANDACHT NODIG (filterbaar)
    attention_rows = []
    if attention_filter in ['all', 'unmatched']:
        for case in unmatched_cases_qs[:6]:
            attention_rows.append({
                'kind': 'unmatched',
                'kind_label': 'Casus zonder match',
                'title': case.title,
                'meta': f"{case.get_status_display()} · {case.get_urgency_display()} · doel {case.target_completion_date:%d-%m-%Y}",
                'href': reverse('careon:intake_detail', kwargs={'pk': case.pk}),
            })
    if attention_filter in ['all', 'stagnation']:
        for case in stagnated_cases_qs[:6]:
            days_open = (today - case.start_date).days
            attention_rows.append({
                'kind': 'stagnation',
                'kind_label': 'Stagnatie',
                'title': case.title,
                'meta': f"{days_open} dagen in traject · {case.get_status_display()}",
                'href': reverse('careon:intake_detail', kwargs={'pk': case.pk}),
            })
    if attention_filter in ['all', 'capacity']:
        for wt in no_capacity_qs[:6]:
            provider_name = wt.provider.name if wt.provider else 'Onbekende aanbieder'
            attention_rows.append({
                'kind': 'capacity',
                'kind_label': 'Geen capaciteit',
                'title': provider_name,
                'meta': f"{wt.region} · wachtlijst {wt.waiting_list_size} · wachttijd {wt.wait_days} dagen",
                'href': reverse('careon:waittime_detail', kwargs={'pk': wt.pk}),
            })
    if attention_filter in ['all', 'escalation']:
        for signal in escalation_qs[:6]:
            case_title = signal.intake.title if signal.intake else 'Niet gekoppelde casus'
            attention_rows.append({
                'kind': 'escalation',
                'kind_label': 'Escalatie',
                'title': case_title,
                'meta': f"{signal.get_signal_type_display()} · {signal.get_risk_level_display()} · {signal.get_status_display()}",
                'href': reverse('careon:signal_update', kwargs={'pk': signal.pk}),
            })

    # Doorstroomtrend op basis van het centrale zorgproces
    flow_counts = {
        'case': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.INTAKE).count(),
        'assessment': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.ASSESSMENT).count(),
        'matching': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.MATCHING).count(),
        'placement': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.DECISION).count(),
        'follow_up': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.COMPLETED).count(),
    }
    max_flow = max(max(flow_counts.values()), 1)
    flow_stages = [
        {'key': 'case', 'label': 'Intake', 'count': flow_counts['case'], 'width': int((flow_counts['case'] / max_flow) * 100)},
        {'key': 'assessment', 'label': 'Beoordeling', 'count': flow_counts['assessment'], 'width': int((flow_counts['assessment'] / max_flow) * 100)},
        {'key': 'matching', 'label': 'Matching', 'count': flow_counts['matching'], 'width': int((flow_counts['matching'] / max_flow) * 100)},
        {'key': 'placement', 'label': 'Plaatsing', 'count': flow_counts['placement'], 'width': int((flow_counts['placement'] / max_flow) * 100)},
        {'key': 'follow_up', 'label': 'Opvolging', 'count': flow_counts['follow_up'], 'width': int((flow_counts['follow_up'] / max_flow) * 100)},
    ]
    flow_drops = [
        ('Intake -> Beoordeling', max(flow_counts['case'] - flow_counts['assessment'], 0)),
        ('Beoordeling -> Matching', max(flow_counts['assessment'] - flow_counts['matching'], 0)),
        ('Matching -> Plaatsing', max(flow_counts['matching'] - flow_counts['placement'], 0)),
        ('Plaatsing -> Opvolging', max(flow_counts['placement'] - flow_counts['follow_up'], 0)),
    ]
    bottleneck_label, bottleneck_value = max(flow_drops, key=lambda x: x[1])

    # Verdeling (klikbaar filter)
    active_configurations = configurations_qs.filter(is_active=True).prefetch_related('care_domains')
    total_active_configurations = active_configurations.count()
    domain_counts = {}
    for config in active_configurations:
        for domain in config.care_domains.all():
            domain_counts[domain.id] = {
                'id': domain.id,
                'name': domain.name,
                'count': domain_counts.get(domain.id, {}).get('count', 0) + 1,
            }
    practice_area_rows = []
    for row in sorted(domain_counts.values(), key=lambda item: item['count'], reverse=True):
        code = str(row['id'])
        label = row['name']
        width = int((row['count'] / max(total_active_configurations, 1)) * 100)
        practice_area_rows.append({
            'code': code,
            'label': label,
            'count': row['count'],
            'width': width,
            'is_active': code == domain_filter,
        })

    # Aanbevelingen (optioneel)
    recommendations = []
    if cases_without_match_count > 0:
        recommendations.append({
            'title': 'Herverdeel casussen zonder match naar matchingteam',
            'detail': f'{cases_without_match_count} casussen wachten op aanbiederkeuze.',
            'href': reverse('careon:matching_dashboard'),
            'action': 'Open matchingoverzicht',
        })
    if no_capacity_qs.count() > 0:
        recommendations.append({
            'title': 'Optimaliseer capaciteit bij aanbieders zonder vrije plekken',
            'detail': f'{no_capacity_qs.count()} aanbieders hebben geen open plekken.',
            'href': reverse('careon:waittime_list'),
            'action': 'Bekijk wachttijden',
        })
    if float(avg_wait_days) > 28:
        recommendations.append({
            'title': 'Wachttijdwaarschuwing: gemiddelde boven 28 dagen',
            'detail': f'Huidig gemiddelde is {avg_wait_days:.1f} dagen.',
            'href': reverse('careon:client_list'),
            'action': 'Open aanbieders',
        })

    region_scope_qs = RegionalConfiguration.objects.filter(organization=org) if org else RegionalConfiguration.objects.none()
    if region_type_filter:
        region_scope_qs = region_scope_qs.filter(region_type=region_type_filter)

    matched_case_ids_set = set(matched_case_ids)
    region_rows = []
    for region in region_scope_qs.order_by('region_name')[:50]:
        region_cases_qs = cases_qs.filter(preferred_region=region)
        region_total = region_cases_qs.count()
        if not region_total:
            continue
        region_matching = region_cases_qs.filter(status__in=[
            CaseIntakeProcess.ProcessStatus.MATCHING,
            CaseIntakeProcess.ProcessStatus.DECISION,
        ]).count()
        region_unmatched = region_cases_qs.filter(
            status__in=[CaseIntakeProcess.ProcessStatus.MATCHING, CaseIntakeProcess.ProcessStatus.DECISION]
        ).exclude(id__in=matched_case_ids_set).count()
        region_rows.append({
            'name': region.region_name,
            'region_type': region.get_region_type_display(),
            'total': region_total,
            'matching': region_matching,
            'unmatched': region_unmatched,
        })

    total_clients = clients_qs.count()
    active_clients = clients_qs.filter(status='ACTIVE').count()
    total_configurations = configurations_qs.count()
    active_cases = case_records_qs.filter(status='ACTIVE').count()
    total_case_value = case_records_qs.aggregate(total=Coalesce(Sum('value'), Decimal('0')))['total']
    high_risk_cases = case_records_qs.filter(risk_level__in=['HIGH', 'CRITICAL']).count()

    context = {
        'total_clients': total_clients,
        'active_clients': active_clients,
        'active_cases': active_cases,
        'active_contracts': active_cases,
        'total_case_value': total_case_value,
        'total_contract_value': total_case_value,
        'total_configurations': total_configurations,
        'active_configurations': total_active_configurations,
        'overdue_deadlines': 0,
        'upcoming_deadlines': 0,
        'high_risks': high_risk_cases,
        'cases_without_match_count': cases_without_match_count,
        'avg_wait_days': avg_wait_days,
        'stagnation_count': stagnation_count,
        'stagnation_days': stagnation_days,
        'escalation_count': escalation_count,
        'attention_rows': attention_rows,
        'attention_filter': attention_filter,
        'flow_stages': flow_stages,
        'bottleneck_label': bottleneck_label,
        'bottleneck_value': bottleneck_value,
        'practice_areas': practice_area_rows,
        'domain_filter': domain_filter,
        'recommendations': recommendations,
        'region_rows': region_rows,
        'region_type_filter': region_type_filter,
        'region_filter': region_filter,
        'region_type_choices': RegionalConfiguration._meta.get_field('region_type').choices,
        'region_choices': region_scope_qs.order_by('region_name'),
    }
    return render(request, 'contracts/reports_dashboard.html', context)


@login_required
def provider_response_monitor(request):
    org = get_user_organization(request.user)
    monitor = build_provider_response_monitor(org)

    context = {
        'monitor_updated_at': timezone.now(),
        'monitor_summary': monitor['summary'],
        'monitor_queue_rows': monitor['queue_rows'],
    }
    return render(request, 'contracts/provider_response_monitor.html', context)


# ==================== TASK VIEWS ====================

class CareTaskKanbanView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = CareTask
    template_name = 'contracts/task_board.html'
    context_object_name = 'care_tasks'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return CareTask.objects.none()
        return CareTask.objects.select_related('case_record', 'configuration', 'assigned_to').filter(
            Q(case_record__organization=org) | Q(configuration__organization=org)
        ).order_by('-updated_at', '-created_at')


@login_required
def task_board_redirect(request):
    return redirect('careon:care_task_kanban')


class CareTaskCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = CareTask
    form_class = CareTaskForm
    template_name = 'contracts/task_form.html'
    success_url = reverse_lazy('careon:task_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['case_record'].queryset = scope_queryset_for_organization(CareCase.objects.all(), org)
            form.fields['configuration'].queryset = scope_queryset_for_organization(CareConfiguration.objects.all(), org)
        else:
            form.fields['case_record'].queryset = CareCase.objects.none()
            form.fields['configuration'].queryset = CareConfiguration.objects.none()
        return form

    def form_valid(self, form):
        org = get_user_organization(self.request.user)
        if form.instance.case_record and not can_access_case_action(self.request.user, form.instance.case_record, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om taken voor deze casus aan te maken.')
        if form.instance.configuration and org and form.instance.configuration.organization_id != org.id:
            return HttpResponseForbidden('Je hebt geen rechten om taken voor deze configuratie aan te maken.')
        return super().form_valid(form)


class CareTaskUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = CareTask
    form_class = CareTaskForm
    template_name = 'contracts/task_form.html'
    success_url = reverse_lazy('careon:task_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return CareTask.objects.none()
        return CareTask.objects.filter(
            Q(case_record__organization=org) | Q(configuration__organization=org)
        )

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['case_record'].queryset = scope_queryset_for_organization(CareCase.objects.all(), org)
            form.fields['configuration'].queryset = scope_queryset_for_organization(CareConfiguration.objects.all(), org)
        else:
            form.fields['case_record'].queryset = CareCase.objects.none()
            form.fields['configuration'].queryset = CareConfiguration.objects.none()
        return form

    def dispatch(self, request, *args, **kwargs):
        task = self.get_object()
        if task.case_record and not can_access_case_action(request.user, task.case_record, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om taken voor deze casus te bewerken.')
        org = get_user_organization(request.user)
        if task.configuration and org and task.configuration.organization_id != org.id:
            return HttpResponseForbidden('Je hebt geen rechten om taken voor deze configuratie te bewerken.')
        return super().dispatch(request, *args, **kwargs)


# ==================== BUDGET VIEWS ====================

class BudgetListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'contracts/budget_list.html'
    context_object_name = 'budgets'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        qs = scope_queryset_for_organization(
            Budget.objects.prefetch_related('linked_cases', 'linked_placements'),
            org,
        )
        search_query = (self.request.GET.get('q') or '').strip()
        year = (self.request.GET.get('year') or '').strip()

        if search_query:
            qs = qs.filter(
                Q(scope_name__icontains=search_query)
                | Q(target_group__icontains=search_query)
                | Q(care_type__icontains=search_query)
                | Q(description__icontains=search_query)
            )

        if year and year.isdigit():
            qs = qs.filter(year=int(year))

        return qs.order_by('-year', 'scope_type', 'scope_name', 'target_group')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_budgets = scope_queryset_for_organization(Budget.objects.all(), org)
        tenant_configs = scope_queryset_for_organization(CareConfiguration.objects.all(), org)
        current_year = timezone.localdate().year
        ctx['search_query'] = (self.request.GET.get('q') or '').strip()
        ctx['selected_year'] = (self.request.GET.get('year') or '').strip()
        ctx['current_year'] = current_year
        budget_stats = tenant_budgets.aggregate(
            total=Count('id'),
            current_year=Count('id', filter=Q(year=current_year)),
            total_allocated=Coalesce(Sum('allocated_amount'), Decimal('0')),
        )

        total_spent = Decimal('0')
        total_remaining = Decimal('0')
        pressure_count = 0
        for budget in tenant_budgets.prefetch_related('expenses').all():
            spent = budget.spent_amount
            remaining = budget.remaining_amount
            total_spent += spent
            total_remaining += remaining
            if budget.utilization_percentage >= 80:
                pressure_count += 1

        ctx['total_budgets'] = budget_stats['total']
        ctx['current_year_budgets'] = budget_stats['current_year']
        ctx['total_allocated'] = budget_stats['total_allocated']
        ctx['total_spent'] = total_spent
        ctx['total_remaining'] = total_remaining
        ctx['budget_under_pressure'] = pressure_count
        ctx['budget_tabs'] = [
            ('Alle budgetten', ''),
            (str(current_year), str(current_year)),
        ]
        configured_scope_labels = {
            item.title.strip().lower(): f'Gebaseerd op {get_configuration_scope_content(item.scope)["entity_label_lower"]}'
            for item in tenant_configs.only('title', 'scope')
        }
        budget_rows = []
        for budget in ctx['budgets']:
            budget_rows.append({
                'budget': budget,
                'configuration_hint': configured_scope_labels.get((budget.scope_name or '').strip().lower(), ''),
            })

        ctx['budget_rows'] = budget_rows
        return ctx


class BudgetCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('careon:budget_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['linked_providers'].queryset = Client.objects.filter(
                organization=org,
                provider_profile__isnull=False,
                status='ACTIVE',
            ).order_by('name')
            form.fields['linked_cases'].queryset = CaseIntakeProcess.objects.filter(organization=org).order_by('-updated_at')
            form.fields['linked_placements'].queryset = PlacementRequest.objects.filter(
                due_diligence_process__organization=org
            ).order_by('-updated_at')
        else:
            form.fields['linked_providers'].queryset = Client.objects.none()
            form.fields['linked_cases'].queryset = CaseIntakeProcess.objects.none()
            form.fields['linked_placements'].queryset = PlacementRequest.objects.none()
        return form

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class BudgetDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Budget
    template_name = 'contracts/budget_detail.html'
    context_object_name = 'budget'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['linked_cases'] = self.object.linked_cases.all()[:20]
        ctx['linked_placements'] = self.object.linked_placements.all()[:20]
        return ctx


class BudgetUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('careon:budget_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['linked_providers'].queryset = Client.objects.filter(
                organization=org,
                provider_profile__isnull=False,
                status='ACTIVE',
            ).order_by('name')
            form.fields['linked_cases'].queryset = CaseIntakeProcess.objects.filter(organization=org).order_by('-updated_at')
            form.fields['linked_placements'].queryset = PlacementRequest.objects.filter(
                due_diligence_process__organization=org
            ).order_by('-updated_at')
        return form


class SignUpView(CreateView):
    form_class = RegistrationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/register.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        UserProfile.objects.get_or_create(user=self.object)

        # Bootstrap a tenant for each newly registered account.
        base_slug = slugify(self.object.username) or f'user-{self.object.id}'
        org_slug = base_slug
        n = 2
        while Organization.objects.filter(slug=org_slug).exists():
            org_slug = f'{base_slug}-{n}'
            n += 1

        org_name = f"{self.object.get_full_name().strip() or self.object.username}'s Regie"
        organization = Organization.objects.create(name=org_name, slug=org_slug)
        OrganizationMembership.objects.create(
            organization=organization,
            user=self.object,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

        login(self.request, self.object, backend='django.contrib.auth.backends.ModelBackend')
        return response


# ==================== ACTION VIEWS ====================


class AddExpenseView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = BudgetExpense
    form_class = BudgetExpenseForm
    template_name = 'contracts/expense_form.html'

    def form_valid(self, form):
        form.instance.budget_id = self.kwargs['budget_pk']
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('careon:budget_detail', kwargs={'pk': self.kwargs['budget_pk']})


# ==================== FUNCTION-BASED VIEWS ====================

@login_required
def toggle_redesign(request):
    if request.method == 'POST':
        import os
        current_value = os.environ.get('FEATURE_REDESIGN', 'false').lower()
        new_value = 'false' if current_value == 'true' else 'true'
        os.environ['FEATURE_REDESIGN'] = new_value
        from config.feature_flags import cache
        cache.clear()
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
    return redirect('dashboard')


def profile(request):
    profile_obj = get_or_create_profile(request.user) if request.user.is_authenticated else None
    form = UserProfileForm(instance=profile_obj) if profile_obj else None
    return render(request, 'profile.html', {'form': form, 'profile': profile_obj})


@login_required
def settings_hub(request):
    return render(request, 'settings_hub.html')


@login_required
def case_flow_list_redirect(request, step=None):
    """Route legacy list entry points to the case-first workspace."""
    target = reverse('careon:case_list')
    if step:
        target = f'{target}?flow={step}'
    return redirect(target)


@login_required
def case_flow_create_redirect(request, step=None):
    """Route legacy create entry points to case creation as single start object."""
    target = reverse('careon:case_create')
    if step:
        target = f'{target}?flow={step}'
    return redirect(target)


@login_required
def case_flow_detail_redirect(request, pk):
    """Route legacy intake detail URLs to the canonical case detail page."""
    return redirect('careon:case_detail', pk=pk)


@login_required
def case_flow_update_redirect(request, pk):
    """Route legacy intake edit URLs to the canonical case edit page."""
    return redirect('careon:case_update', pk=pk)


@login_required
def matching_dashboard(request):
    """Show actionable assessment-to-provider matching suggestions and assignments."""
    org = get_user_organization(request.user)
    if not org:
        messages.error(request, 'Geen actieve organisatie gevonden voor matching.')
        return render(request, 'contracts/matching_dashboard.html', {'rows': [], 'total_ready': 0})

    approved_assessments_qs = (
        CaseAssessment.objects.filter(
            due_diligence_process__organization=org,
            assessment_status=CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING,
        )
        .select_related('due_diligence_process', 'due_diligence_process__care_category_main', 'assessed_by')
        .order_by('-updated_at')
    )

    selected_intake = None
    selected_intake_raw = (request.GET.get('intake') or '').strip()
    if selected_intake_raw.isdigit():
        selected_intake = CaseIntakeProcess.objects.filter(organization=org, pk=int(selected_intake_raw)).first()
        if selected_intake:
            approved_assessments_qs = approved_assessments_qs.filter(due_diligence_process=selected_intake)
        else:
            messages.warning(request, 'De gekozen casus is niet gevonden. Alle matchingitems worden getoond.')
            _log_pilot_issue(
                request,
                category='matching_invalid_intake_filter',
                detail=f'intake={selected_intake_raw}',
            )

    if request.method == 'POST' and request.POST.get('action') == 'assign':
        assessment = get_object_or_404(approved_assessments_qs, pk=request.POST.get('assessment_id'))
        intake = assessment.intake
        if not _can_edit_intake(request.user, intake):
            _log_pilot_issue(
                request,
                category='matching_forbidden',
                detail=f'intake={getattr(intake, "pk", "-")}',
            )
            return HttpResponseForbidden('Je hebt geen rechten om matching voor deze casus bij te werken.')

        messages.info(request, 'Toewijzen verloopt vanuit de casuswerkruimte.')
        return redirect(f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=matching")

    provider_profiles = (
        ProviderProfile.objects.filter(client__organization=org, client__status='ACTIVE')
        .select_related('client')
        .prefetch_related('target_care_categories', 'served_regions')
    )

    assessments = list(approved_assessments_qs)
    assessments_by_intake = {assessment.due_diligence_process_id: assessment for assessment in assessments}
    assigned_by_intake = {
        placement.due_diligence_process_id: placement
        for placement in PlacementRequest.objects.filter(
            due_diligence_process_id__in=assessments_by_intake.keys(),
            selected_provider__isnull=False,
        ).select_related('selected_provider')
    }

    rows = []
    for assessment in assessments:
        intake = assessment.intake
        can_assign = _can_edit_intake(request.user, intake)
        suggestions = _build_matching_suggestions_for_intake(intake, provider_profiles, limit=5)
        _assignment = assigned_by_intake.get(intake.id)
        rows.append(
            {
                'assessment': assessment,
                'intake': intake,
                'can_assign': can_assign,
                'assigned_provider': _assignment.selected_provider if _assignment else None,
                'placement_pk': _assignment.pk if _assignment else None,
                'suggestions': suggestions[:5],
            }
        )

    context = {
        'rows': rows,
        'total_ready': len(rows),
        'assigned_count': len(assigned_by_intake),
        'selected_intake': selected_intake,
    }
    return render(request, 'contracts/matching_dashboard.html', context)


@login_required
@require_POST
def case_matching_action(request, pk):
    org = get_user_organization(request.user)
    intake = get_object_or_404(
        scope_queryset_for_organization(CaseIntakeProcess.objects.select_related('contract'), org),
        pk=pk,
    )

    if not _can_edit_intake(request.user, intake):
        return HttpResponseForbidden('Je hebt geen rechten om matching voor deze casus bij te werken.')

    action = (request.POST.get('action') or '').strip()
    phase = (request.POST.get('phase') or '').strip()
    next_fallback = f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=matching"
    if phase:
        next_fallback += f'&phase={phase}'

    if action == 'assign':
        provider = get_object_or_404(
            Client.objects.filter(organization=org, status='ACTIVE'),
            pk=request.POST.get('provider_id'),
        )
        _assign_provider_to_intake(request=request, intake=intake, provider=provider, source='case_detail')
        messages.success(request, f'Aanbieder {provider.name} gekoppeld aan casus "{intake.title}".')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    if action == 'reject':
        provider = get_object_or_404(
            Client.objects.filter(organization=org, status='ACTIVE'),
            pk=request.POST.get('provider_id'),
        )
        rejection_reason = (request.POST.get('reason') or '').strip() or 'Afgewezen in casusdetail.'
        log_action(
            request.user,
            AuditLog.Action.REJECT,
            'MatchingRecommendation',
            object_id=provider.id,
            object_repr=f'{intake.title} -> {provider.name}',
            changes={
                'intake_id': intake.id,
                'provider_id': provider.id,
                'provider_name': provider.name,
                'reason': rejection_reason,
                'phase': phase,
                'source': 'case_detail',
            },
            request=request,
        )
        messages.success(request, f'Aanbieder {provider.name} gemarkeerd als afgewezen voor deze casus.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    messages.error(request, 'Onbekende matching-actie.')
    return _redirect_to_safe_next_or_default(request, next_fallback)


@login_required
@require_POST
def case_placement_action(request, pk):
    org = get_user_organization(request.user)
    intake = get_object_or_404(
        scope_queryset_for_organization(CaseIntakeProcess.objects.select_related('contract'), org),
        pk=pk,
    )

    if not _can_edit_intake(request.user, intake):
        return HttpResponseForbidden('Je hebt geen rechten om plaatsing voor deze casus te wijzigen.')

    placement = PlacementRequest.objects.filter(
        due_diligence_process=intake,
    ).select_related('selected_provider', 'proposed_provider').order_by('-updated_at').first()

    next_fallback = f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=plaatsing"

    if not placement:
        messages.error(request, 'Nog geen plaatsing beschikbaar. Start eerst via matching.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    status = (request.POST.get('status') or '').strip()
    valid_statuses = {choice[0] for choice in PlacementRequest.Status.choices}
    if status not in valid_statuses:
        messages.error(request, 'Ongeldige plaatsingsstatus.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    update_fields = ['updated_at']
    changes = {'status': status}

    if placement.status != status:
        placement.status = status
        update_fields.append('status')

    note = (request.POST.get('note') or '').strip()
    if note:
        existing = placement.decision_notes or ''
        stamped_note = f"[{timezone.now().strftime('%d-%m-%Y %H:%M')}] {note}"
        placement.decision_notes = f"{existing}\n{stamped_note}".strip()
        update_fields.append('decision_notes')
        changes['note'] = note

    if placement.status == PlacementRequest.Status.APPROVED and not placement.start_date:
        start_date = date.today()
        placement.start_date = start_date
        update_fields.append('start_date')
        changes['start_date'] = start_date.isoformat()

    placement.save(update_fields=list(dict.fromkeys(update_fields)))
    log_action(
        request.user,
        AuditLog.Action.UPDATE,
        'PlacementRequest',
        object_id=placement.id,
        object_repr=str(placement),
        changes=changes,
        request=request,
    )
    messages.success(request, 'Plaatsing bijgewerkt vanuit de casuswerkruimte.')
    return _redirect_to_safe_next_or_default(request, next_fallback)


@login_required
@require_POST
def case_provider_response_action(request, pk):
    org = get_user_organization(request.user)
    intake = get_object_or_404(
        scope_queryset_for_organization(CaseIntakeProcess.objects.select_related('contract'), org),
        pk=pk,
    )

    if not _can_edit_intake(request.user, intake):
        return HttpResponseForbidden('Je hebt geen rechten om providerreactie voor deze casus te wijzigen.')

    placement = PlacementRequest.objects.filter(
        due_diligence_process=intake,
    ).select_related('selected_provider', 'proposed_provider').order_by('-updated_at').first()

    next_fallback = f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=plaatsing"
    if not placement:
        messages.error(request, 'Nog geen plaatsing beschikbaar. Start eerst via matching.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    action = (request.POST.get('action') or '').strip()
    action_aliases = {
        'resend': 'resend_request',
        'resend_request': 'resend_request',
        'provide_info': 'provide_missing_info',
        'provide_missing_info': 'provide_missing_info',
        'rematch': 'trigger_rematch',
        'trigger_rematch': 'trigger_rematch',
    }
    normalized_action = action_aliases.get(action)
    now = timezone.now()
    due_days = _provider_response_due_days_for_intake(intake)
    due_at = now + timedelta(days=due_days)
    response_status = _normalize_provider_response_status_value(placement.provider_response_status)

    if response_status != placement.provider_response_status:
        placement.provider_response_status = response_status
        placement.save(update_fields=['provider_response_status', 'updated_at'])

    if normalized_action == 'resend_request':
        if response_status not in {
            PlacementRequest.ProviderResponseStatus.PENDING,
            PlacementRequest.ProviderResponseStatus.NEEDS_INFO,
            PlacementRequest.ProviderResponseStatus.WAITLIST,
        }:
            messages.error(request, 'Herinnering is alleen toegestaan voor open providerreacties.')
            return _redirect_to_safe_next_or_default(request, next_fallback)

        update_fields = [
            'provider_response_requested_at',
            'provider_response_last_reminder_at',
            'provider_response_deadline_at',
            'updated_at',
        ]
        changes = {
            'provider_response_action': 'resend_request',
            'provider_response_due_days': due_days,
            'provider_response_deadline_at': due_at.isoformat(),
        }

        placement.provider_response_requested_at = now
        placement.provider_response_last_reminder_at = now
        placement.provider_response_deadline_at = due_at
        if response_status != PlacementRequest.ProviderResponseStatus.PENDING:
            placement.provider_response_status = PlacementRequest.ProviderResponseStatus.PENDING
            update_fields.append('provider_response_status')
            changes['provider_response_status'] = PlacementRequest.ProviderResponseStatus.PENDING

        placement.save(update_fields=list(dict.fromkeys(update_fields)))
        log_action(
            request.user,
            AuditLog.Action.UPDATE,
            'PlacementRequest',
            object_id=placement.id,
            object_repr=str(placement),
            changes=changes,
            request=request,
        )
        messages.success(request, 'Verzoek opnieuw verstuurd naar aanbieder en reactietermijn bijgewerkt.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    if normalized_action == 'provide_missing_info':
        if response_status != PlacementRequest.ProviderResponseStatus.NEEDS_INFO:
            messages.error(request, 'Aanvullende informatie kan alleen worden geregistreerd bij status "Aanvullende info nodig".')
            return _redirect_to_safe_next_or_default(request, next_fallback)

        update_fields = [
            'provider_response_status',
            'provider_response_requested_at',
            'provider_response_deadline_at',
            'provider_response_notes',
            'updated_at',
        ]
        placement.provider_response_status = PlacementRequest.ProviderResponseStatus.PENDING
        placement.provider_response_requested_at = now
        placement.provider_response_deadline_at = due_at
        info_note = f"[{now.strftime('%d-%m-%Y %H:%M')}] Aanvullende informatie aangeleverd; reactie opnieuw aangevraagd."
        existing_notes = placement.provider_response_notes or ''
        placement.provider_response_notes = f"{existing_notes}\n{info_note}".strip()
        placement.save(update_fields=list(dict.fromkeys(update_fields)))
        log_action(
            request.user,
            AuditLog.Action.UPDATE,
            'PlacementRequest',
            object_id=placement.id,
            object_repr=str(placement),
            changes={
                'provider_response_action': 'provide_missing_info',
                'provider_response_status': PlacementRequest.ProviderResponseStatus.PENDING,
                'provider_response_deadline_at': due_at.isoformat(),
            },
            request=request,
        )
        messages.success(request, 'Aanvullende informatie geregistreerd en providerreactie opnieuw opengezet.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    if normalized_action == 'trigger_rematch':
        if response_status not in {
            PlacementRequest.ProviderResponseStatus.REJECTED,
            PlacementRequest.ProviderResponseStatus.NO_CAPACITY,
            PlacementRequest.ProviderResponseStatus.WAITLIST,
        }:
            messages.error(request, 'Her-match is alleen toegestaan na afwijzing, geen capaciteit of wachtlijstreactie.')
            return _redirect_to_safe_next_or_default(request, next_fallback)

        update_fields = ['status', 'decision_notes', 'updated_at']
        placement.status = PlacementRequest.Status.REJECTED
        rematch_note = f"[{now.strftime('%d-%m-%Y %H:%M')}] Her-match gestart vanuit providerreactie-orchestratie."
        existing_notes = placement.decision_notes or ''
        placement.decision_notes = f"{existing_notes}\n{rematch_note}".strip()
        placement.save(update_fields=list(dict.fromkeys(update_fields)))

        if intake.status != CaseIntakeProcess.ProcessStatus.MATCHING:
            intake.status = CaseIntakeProcess.ProcessStatus.MATCHING
            intake.save(update_fields=['status', 'updated_at'])

        log_action(
            request.user,
            AuditLog.Action.UPDATE,
            'PlacementRequest',
            object_id=placement.id,
            object_repr=str(placement),
            changes={
                'provider_response_action': 'trigger_rematch',
                'placement_status': placement.status,
                'intake_status': intake.status,
            },
            request=request,
        )
        messages.success(request, 'Her-match geactiveerd. Casus staat weer in matchingfase.')
        return _redirect_to_safe_next_or_default(
            request,
            f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=matching",
        )

    messages.error(request, 'Onbekende providerreactie-actie.')
    return _redirect_to_safe_next_or_default(request, next_fallback)


@login_required
@require_POST
def case_outcome_action(request, pk):
    org = get_user_organization(request.user)
    intake = get_object_or_404(
        scope_queryset_for_organization(CaseIntakeProcess.objects.select_related('contract'), org),
        pk=pk,
    )

    if not _can_edit_intake(request.user, intake):
        return HttpResponseForbidden('Je hebt geen rechten om uitkomsten voor deze casus te wijzigen.')

    placement = PlacementRequest.objects.filter(
        due_diligence_process=intake,
    ).select_related('selected_provider', 'proposed_provider').order_by('-updated_at').first()

    next_fallback = f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=plaatsing"
    form = CaseOutcomeUpdateForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Ongeldige uitkomstupdate.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    cleaned = form.cleaned_data
    outcome_type = cleaned['outcome_type']
    if outcome_type in {
        CaseOutcomeUpdateForm.OUTCOME_TYPE_PROVIDER_RESPONSE,
        CaseOutcomeUpdateForm.OUTCOME_TYPE_PLACEMENT_QUALITY,
    } and not placement:
        messages.error(request, 'Voor deze uitkomst is eerst een plaatsing nodig.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    try:
        title, status_label = _apply_case_outcome_update(
            intake=intake,
            placement=placement,
            outcome_type=outcome_type,
            status=cleaned['status'],
            reason_code=cleaned['reason_code'],
            notes=cleaned['notes'].strip(),
            user=request.user,
        )
    except ValueError:
        messages.error(request, 'Voor deze uitkomst is eerst een plaatsing nodig.')
        return _redirect_to_safe_next_or_default(request, next_fallback)

    messages.success(request, f'{title}: {status_label}.')
    return _redirect_to_safe_next_or_default(request, next_fallback)


# ==================== DASHBOARD VIEW ====================

def dashboard(request):
    today = date.today()
    now = timezone.now()
    org = get_user_organization(request.user)
    waiting_threshold_days = 7
    region_overload_threshold = 5

    intakes_qs = scope_queryset_for_organization(
        CaseIntakeProcess.objects.select_related(
            'organization',
            'case_coordinator',
            'preferred_region',
            'case_assessment',
        ),
        org,
    )

    active_intakes = list(
        intakes_qs.exclude(status=CaseIntakeProcess.ProcessStatus.COMPLETED)
        .order_by('-updated_at')
    )

    placements = PlacementRequest.objects.filter(
        due_diligence_process__organization=org
    ).select_related('selected_provider', 'due_diligence_process') if org else PlacementRequest.objects.none()
    placement_by_intake = {}
    for placement in placements.order_by('due_diligence_process_id', '-updated_at'):
        intake_id = placement.due_diligence_process_id
        if intake_id and intake_id not in placement_by_intake:
            placement_by_intake[intake_id] = placement

    signals_qs = CareSignal.objects.for_organization(org).filter(
        status__in=[CareSignal.SignalStatus.OPEN, CareSignal.SignalStatus.IN_PROGRESS]
    )
    signals_by_intake = {}
    for signal in signals_qs.select_related('due_diligence_process').order_by('-updated_at'):
        intake_id = signal.due_diligence_process_id
        if not intake_id:
            continue
        signals_by_intake.setdefault(intake_id, []).append(signal)

    def _phase_rank(status):
        ranking = {
            CaseIntakeProcess.ProcessStatus.INTAKE: 1,
            CaseIntakeProcess.ProcessStatus.ASSESSMENT: 2,
            CaseIntakeProcess.ProcessStatus.MATCHING: 3,
            CaseIntakeProcess.ProcessStatus.DECISION: 4,
            CaseIntakeProcess.ProcessStatus.ON_HOLD: 5,
            CaseIntakeProcess.ProcessStatus.COMPLETED: 6,
        }
        return ranking.get(status, 99)

    def _next_best_action(intake, assessment, placement):
        if intake.status == CaseIntakeProcess.ProcessStatus.INTAKE:
            return {
                'label': 'Start beoordeling',
                'href': reverse('careon:assessment_create') + f'?intake={intake.pk}',
                'type': 'review',
            }
        if intake.status == CaseIntakeProcess.ProcessStatus.ASSESSMENT:
            if assessment:
                return {
                    'label': 'Complete beoordeling',
                    'href': reverse('careon:assessment_update', args=[assessment.pk]),
                    'type': 'review',
                }
            return {
                'label': 'Start beoordeling',
                'href': reverse('careon:assessment_create') + f'?intake={intake.pk}',
                'type': 'review',
            }
        if intake.status in [CaseIntakeProcess.ProcessStatus.MATCHING, CaseIntakeProcess.ProcessStatus.DECISION]:
            return {
                'label': 'Assign provider',
                'href': reverse('careon:matching_dashboard') + f'?intake={intake.pk}',
                'type': 'assign',
            }
        if intake.status == CaseIntakeProcess.ProcessStatus.ON_HOLD:
            return {
                'label': 'Escaleer blokkade',
                'href': reverse('careon:case_signal_create', args=[intake.pk]),
                'type': 'escalate',
            }
        return {
            'label': 'Monitor progress',
            'href': reverse('careon:case_detail', args=[intake.pk]),
            'type': 'monitor',
        }

    urgency_weight = {
        CaseIntakeProcess.Urgency.CRISIS: 400,
        CaseIntakeProcess.Urgency.HIGH: 300,
        CaseIntakeProcess.Urgency.MEDIUM: 200,
        CaseIntakeProcess.Urgency.LOW: 100,
    }

    priority_queue = []
    no_match_count = 0
    waiting_long_count = 0
    missing_assessment_count = 0
    urgent_count = 0

    for intake in active_intakes:
        assessment = getattr(intake, 'case_assessment', None)
        placement = placement_by_intake.get(intake.pk)
        open_signals = signals_by_intake.get(intake.pk, [])
        high_signal = next((s for s in open_signals if s.risk_level in [CareSignal.RiskLevel.CRITICAL, CareSignal.RiskLevel.HIGH]), None)

        waiting_days = max((today - intake.updated_at.date()).days, 0)
        missing_assessment = (
            assessment is None
            or assessment.assessment_status in [
                CaseAssessment.AssessmentStatus.DRAFT,
                CaseAssessment.AssessmentStatus.UNDER_REVIEW,
                CaseAssessment.AssessmentStatus.NEEDS_INFO,
            ]
        )
        no_match = intake.status in [
            CaseIntakeProcess.ProcessStatus.MATCHING,
            CaseIntakeProcess.ProcessStatus.DECISION,
        ] and placement is None
        waiting_long = waiting_days >= waiting_threshold_days
        is_urgent = intake.urgency in [CaseIntakeProcess.Urgency.HIGH, CaseIntakeProcess.Urgency.CRISIS]

        blockers = []
        if no_match:
            blockers.append({'key': 'no_match', 'label': 'Geen match', 'score': 120})
            no_match_count += 1
        if waiting_long:
            blockers.append({'key': 'waiting_long', 'label': 'Wacht te lang', 'score': 90})
            waiting_long_count += 1
        if missing_assessment:
            blockers.append({'key': 'missing_assessment', 'label': 'Beoordeling ontbreekt', 'score': 100})
            missing_assessment_count += 1
        if high_signal:
            blockers.append({'key': 'risk_signal', 'label': high_signal.get_signal_type_display(), 'score': 95})
        if is_urgent:
            urgent_count += 1

        blocker = max(blockers, key=lambda item: item['score']) if blockers else None
        next_action = _next_best_action(intake, assessment, placement)

        priority_score = urgency_weight.get(intake.urgency, 0) + min(waiting_days, 30) * 5
        if blocker:
            priority_score += blocker['score']
        if intake.status in [CaseIntakeProcess.ProcessStatus.MATCHING, CaseIntakeProcess.ProcessStatus.DECISION]:
            priority_score += 35

        queue_item = {
            'id': intake.pk,
            'title': intake.title,
            'phase': intake.get_status_display(),
            'phase_rank': _phase_rank(intake.status),
            'urgency': intake.get_urgency_display(),
            'urgency_code': intake.urgency,
            'waiting_days': waiting_days,
            'waiting_label': f'{waiting_days} dagen',
            'blocker': blocker['label'] if blocker else 'Geen directe blokkade',
            'blocker_key': blocker['key'] if blocker else None,
            'next_action': next_action,
            'case_href': reverse('careon:case_detail', args=[intake.pk]),
            'quick_assign_href': reverse('careon:matching_dashboard') + f'?intake={intake.pk}',
            'quick_escalate_href': reverse('careon:case_signal_create', args=[intake.pk]),
            'quick_review_href': (
                reverse('careon:assessment_update', args=[assessment.pk])
                if assessment else reverse('careon:assessment_create') + f'?intake={intake.pk}'
            ),
            'assessment_status': assessment.get_assessment_status_display() if assessment else 'Niet gestart',
            'placement_status': placement.get_status_display() if placement else 'Niet gestart',
            'priority_score': priority_score,
        }
        priority_queue.append(queue_item)

    priority_queue.sort(
        key=lambda row: (
            -row['priority_score'],
            row['phase_rank'],
            -row['waiting_days'],
        )
    )

    selected_case_id = request.GET.get('case')
    try:
        selected_case_id = int(selected_case_id) if selected_case_id else None
    except (TypeError, ValueError):
        selected_case_id = None

    active_case = None
    if priority_queue:
        selected_row = next((item for item in priority_queue if item['id'] == selected_case_id), priority_queue[0])
        intake = next((obj for obj in active_intakes if obj.pk == selected_row['id']), None)
        assessment = getattr(intake, 'case_assessment', None) if intake else None
        placement = placement_by_intake.get(intake.pk) if intake else None
        signals = signals_by_intake.get(intake.pk, []) if intake else []

        timeline = []
        if intake:
            timeline.append({'label': 'Intake gestart', 'value': intake.start_date})
            timeline.append({'label': 'Laatste update', 'value': intake.updated_at.date()})
        if assessment:
            timeline.append({'label': 'Beoordeling', 'value': assessment.updated_at.date()})
        if placement:
            timeline.append({'label': 'Plaatsing', 'value': placement.updated_at.date()})
        if signals:
            timeline.append({'label': 'Laatste signaal', 'value': signals[0].updated_at.date()})

        if intake and intake.status in [CaseIntakeProcess.ProcessStatus.MATCHING, CaseIntakeProcess.ProcessStatus.DECISION]:
            if placement and placement.selected_provider:
                match_status = f'Toegewezen aan {placement.selected_provider.name}'
            elif assessment and assessment.assessment_status == CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING:
                match_status = 'Klaar voor toewijzing'
            else:
                match_status = 'Wacht op beoordeling'
        else:
            match_status = 'Nog niet in matchingfase'

        active_case = {
            'id': selected_row['id'],
            'title': selected_row['title'],
            'phase': selected_row['phase'],
            'urgency': selected_row['urgency'],
            'waiting_label': selected_row['waiting_label'],
            'blocker': selected_row['blocker'],
            'next_action': selected_row['next_action'],
            'assessment_status': selected_row['assessment_status'],
            'placement_status': selected_row['placement_status'],
            'match_status': match_status,
            'region': intake.preferred_region.region_name if intake and intake.preferred_region else 'Niet gespecificeerd',
            'coordinator': intake.case_coordinator.get_full_name() if intake and intake.case_coordinator else 'Niet toegewezen',
            'timeline': timeline,
            'case_href': selected_row['case_href'],
        }

    alert_strip = [
        {
            'icon': '🚨',
            'label': 'Cases without match',
            'count': no_match_count,
            'href': reverse('careon:case_list') + '?attention=no_match',
        },
        {
            'icon': '⏳',
            'label': 'Cases waiting too long',
            'count': waiting_long_count,
            'href': reverse('careon:case_list') + '?attention=waiting_long',
        },
        {
            'icon': '⚠️',
            'label': 'Missing beoordeling',
            'count': missing_assessment_count,
            'href': reverse('careon:case_list') + '?attention=missing_assessment',
        },
        {
            'icon': '🔴',
            'label': 'Urgent cases',
            'count': urgent_count,
            'href': reverse('careon:case_list') + '?attention=urgent',
        },
    ]

    bottleneck_bucket = {}
    for row in priority_queue:
        key = row['blocker_key']
        if not key:
            continue
        bucket = bottleneck_bucket.setdefault(key, {'count': 0, 'days': []})
        bucket['count'] += 1
        bucket['days'].append(row['waiting_days'])

    bottleneck_meta = {
        'no_match': ('Geen match', reverse('careon:case_list') + '?attention=no_match'),
        'waiting_long': ('Wachttijd overschreden', reverse('careon:case_list') + '?attention=waiting_long'),
        'missing_assessment': ('Beoordeling ontbreekt', reverse('careon:case_list') + '?attention=missing_assessment'),
        'risk_signal': ('Kritische signalen', reverse('careon:case_list') + '?attention=urgent'),
    }
    bottleneck_signals = []
    for key, data in sorted(bottleneck_bucket.items(), key=lambda item: item[1]['count'], reverse=True)[:3]:
        label, href = bottleneck_meta.get(key, (key, reverse('careon:case_list')))
        avg_delay = round(sum(data['days']) / len(data['days']), 1) if data['days'] else 0
        bottleneck_signals.append({
            'label': label,
            'count': data['count'],
            'avg_delay': avg_delay,
            'href': href,
        })

    provider_profiles = ProviderProfile.objects.filter(client__organization=org).select_related('client') if org else ProviderProfile.objects.none()
    no_capacity_profiles = []
    for profile in provider_profiles:
        free_slots = max((profile.max_capacity or 0) - (profile.current_capacity or 0), 0)
        if free_slots <= 0:
            no_capacity_profiles.append(profile)

    capacity_signals = []
    for profile in no_capacity_profiles[:3]:
        capacity_signals.append({
            'label': f'{profile.client.name} heeft geen capaciteit',
            'detail': f'Bezetting {profile.current_capacity}/{profile.max_capacity}',
            'href': reverse('careon:case_list') + '?attention=capacity_none',
        })

    region_counts = {}
    for intake in active_intakes:
        if intake.preferred_region_id:
            region_counts[intake.preferred_region_id] = region_counts.get(intake.preferred_region_id, 0) + 1
    overloaded_regions = sorted(region_counts.items(), key=lambda item: item[1], reverse=True)
    for region_id, count in overloaded_regions[:3]:
        if count < region_overload_threshold:
            continue
        region_obj = next((i.preferred_region for i in active_intakes if i.preferred_region_id == region_id), None)
        if not region_obj:
            continue
        capacity_signals.append({
            'label': f'Regio overbelast: {region_obj.region_name}',
            'detail': f'{count} actieve casussen in deze regio',
            'href': reverse('careon:case_list') + f'?region={region_id}',
        })

    context = {
        'dashboard_updated_at': now,
        'alert_strip': alert_strip,
        'priority_queue': priority_queue,
        'active_case': active_case,
        'selected_case_id': active_case['id'] if active_case else None,
        'bottleneck_signals': bottleneck_signals,
        'capacity_signals': capacity_signals,
        'total_active_cases': len(priority_queue),
        'FEATURE_REDESIGN': is_feature_redesign_enabled(),
    }
    return render(request, 'dashboard.html', context)


@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    results = {}
    org = get_user_organization(request.user)
    if q:
        case_qs = scope_queryset_for_organization(CareCase.objects.all(), org) if org else CareCase.objects.none()
        client_qs = scope_queryset_for_organization(Client.objects.all(), org) if org else Client.objects.none()
        configuration_qs = scope_queryset_for_organization(CareConfiguration.objects.all(), org) if org else CareConfiguration.objects.none()
        document_qs = scope_queryset_for_organization(Document.objects.all(), org) if org else Document.objects.none()

        case_records = case_qs.filter(
            Q(title__icontains=q) | Q(preferred_provider__icontains=q) | Q(content__icontains=q)
        )[:10]
        configurations = configuration_qs.filter(
            Q(title__icontains=q) | Q(configuration_id__icontains=q) | Q(description__icontains=q)
        )[:10]

        results['case_records'] = case_records
        results['clients'] = client_qs.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(industry__icontains=q)
        )[:10]
        results['configurations'] = configurations
        results['documents'] = document_qs.filter(
            Q(title__icontains=q) | Q(description__icontains=q) | Q(tags__icontains=q)
        )[:10]
    return render(request, 'contracts/search_results.html', {'q': q, 'results': results})


# ============================================
# MUNICIPALITY CONFIGURATION VIEWS
# ============================================

class MunicipalityConfigurationListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = MunicipalityConfiguration
    template_name = 'contracts/municipality_list.html'
    context_object_name = 'municipalities'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            MunicipalityConfiguration.objects.prefetch_related('care_domains', 'linked_providers', 'responsible_coordinator'),
            org,
        )
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        if q:
            qs = qs.filter(
                Q(municipality_name__icontains=q)
                | Q(municipality_code__icontains=q)
            ).distinct()
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('municipality_name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        municipality_qs = scope_queryset_for_organization(MunicipalityConfiguration.objects.all(), org)
        municipality_stats = municipality_qs.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
        )
        ctx['total_municipalities'] = municipality_stats['total']
        ctx['active_municipalities'] = municipality_stats['active']
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class MunicipalityConfigurationDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = MunicipalityConfiguration
    template_name = 'contracts/municipality_detail.html'
    context_object_name = 'municipality'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(MunicipalityConfiguration.objects.all(), org)


class MunicipalityConfigurationCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = MunicipalityConfiguration
    form_class = MunicipalityConfigurationForm
    template_name = 'contracts/municipality_form.html'

    def get_success_url(self):
        return reverse('careon:municipality_detail', kwargs={'pk': self.object.pk})


class MunicipalityConfigurationUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = MunicipalityConfiguration
    form_class = MunicipalityConfigurationForm
    template_name = 'contracts/municipality_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(MunicipalityConfiguration.objects.all(), org)

    def get_success_url(self):
        return reverse('careon:municipality_detail', kwargs={'pk': self.object.pk})


# ============================================
# REGIONAL CONFIGURATION VIEWS
# ============================================

class RegionalConfigurationListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = RegionalConfiguration
    template_name = 'contracts/regional_list.html'
    context_object_name = 'regions'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            RegionalConfiguration.objects.prefetch_related('care_domains', 'linked_providers', 'served_municipalities', 'responsible_coordinator'),
            org,
        )
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        region_type = self.request.GET.get('region_type')
        if q:
            qs = qs.filter(
                Q(region_name__icontains=q)
                | Q(region_code__icontains=q)
            ).distinct()
        if status:
            qs = qs.filter(status=status)
        if region_type:
            qs = qs.filter(region_type=region_type)
        return qs.order_by('region_name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        regional_qs = scope_queryset_for_organization(RegionalConfiguration.objects.all(), org)
        regional_stats = regional_qs.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
        )
        ctx['total_regions'] = regional_stats['total']
        ctx['active_regions'] = regional_stats['active']
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['region_type_choices'] = RegionalConfiguration._meta.get_field('region_type').choices
        ctx['selected_region_type'] = self.request.GET.get('region_type', '')
        return ctx


class RegionalConfigurationDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = RegionalConfiguration
    template_name = 'contracts/regional_detail.html'
    context_object_name = 'region'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(RegionalConfiguration.objects.all(), org)


class RegionalConfigurationCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = RegionalConfiguration
    form_class = RegionalConfigurationForm
    template_name = 'contracts/regional_form.html'

    def get_success_url(self):
        return reverse('careon:regional_detail', kwargs={'pk': self.object.pk})


class RegionalConfigurationUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = RegionalConfiguration
    form_class = RegionalConfigurationForm
    template_name = 'contracts/regional_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(RegionalConfiguration.objects.all(), org)

    def get_success_url(self):
        return reverse('careon:regional_detail', kwargs={'pk': self.object.pk})


# ==================== CARE INTAKE VIEWS ====================

class CaseIntakeListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    """List all care intakes for the organization."""
    model = CaseIntakeProcess
    template_name = 'contracts/intake_list.html'
    context_object_name = 'intakes'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            CaseIntakeProcess.objects.select_related(
                'organization', 'case_coordinator', 'care_category_main', 'contract'
            ).prefetch_related('risk_factors'),
            org,
        )
        today = date.today()
        waiting_threshold_days = 7

        # Search by title, case ID, or case coordinator
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(case_coordinator__first_name__icontains=q)
                | Q(case_coordinator__last_name__icontains=q)
                | Q(contract__id__icontains=q)
            ).distinct()

        # Filter by status
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        # flow=intake is a dashboard shortcut — filters to INTAKE-phase cases only
        flow = self.request.GET.get('flow')
        if flow == 'intake':
            qs = qs.filter(status=CaseIntakeProcess.ProcessStatus.INTAKE)
        elif flow == 'assessment':
            qs = qs.filter(status=CaseIntakeProcess.ProcessStatus.ASSESSMENT)
        elif flow == 'matching':
            qs = qs.filter(status__in=[
                CaseIntakeProcess.ProcessStatus.MATCHING,
                CaseIntakeProcess.ProcessStatus.DECISION,
            ])

        attention = self.request.GET.get('attention')
        if attention == 'no_match':
            qs = qs.filter(status__in=[
                CaseIntakeProcess.ProcessStatus.MATCHING,
                CaseIntakeProcess.ProcessStatus.DECISION,
            ])
        elif attention == 'waiting_long':
            qs = qs.filter(updated_at__date__lt=today - timedelta(days=waiting_threshold_days))
        elif attention == 'missing_assessment':
            qs = qs.filter(
                Q(case_assessment__isnull=True)
                | Q(case_assessment__assessment_status__in=[
                    CaseAssessment.AssessmentStatus.DRAFT,
                    CaseAssessment.AssessmentStatus.UNDER_REVIEW,
                    CaseAssessment.AssessmentStatus.NEEDS_INFO,
                ])
            )
        elif attention == 'urgent':
            qs = qs.filter(urgency__in=[CaseIntakeProcess.Urgency.HIGH, CaseIntakeProcess.Urgency.CRISIS])
        elif attention == 'capacity_none':
            qs = qs.filter(status__in=[
                CaseIntakeProcess.ProcessStatus.MATCHING,
                CaseIntakeProcess.ProcessStatus.DECISION,
            ])

        # Filter by urgency
        urgency = self.request.GET.get('urgency')
        if urgency:
            qs = qs.filter(urgency=urgency)

        region_type = self.request.GET.get('region_type')
        if region_type:
            qs = qs.filter(preferred_region_type=region_type)

        region = self.request.GET.get('region')
        if region and region.isdigit():
            qs = qs.filter(preferred_region_id=int(region))

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()

        # Statistics
        org_intakes = scope_queryset_for_organization(CaseIntakeProcess.objects.all(), org)
        ctx.update({
            'total_intakes': org_intakes.count(),
            'active_intakes': org_intakes.exclude(status=CaseIntakeProcess.ProcessStatus.COMPLETED).count(),
            'urgent_intakes': org_intakes.filter(urgency__in=[CaseIntakeProcess.Urgency.HIGH, CaseIntakeProcess.Urgency.CRISIS]).count(),
            'search_query': self.request.GET.get('q', ''),
            'status_choices': CaseIntakeProcess.ProcessStatus.choices,
            'urgency_choices': CaseIntakeProcess.Urgency.choices,
            'region_type_choices': RegionalConfiguration._meta.get_field('region_type').choices,
            'selected_region_type': self.request.GET.get('region_type', ''),
            'selected_region': self.request.GET.get('region', ''),
            'region_choices': RegionalConfiguration.objects.filter(organization=org).order_by('region_name'),
        })

        # Build intake rows for display
        intake_rows = []
        for intake in ctx['intakes']:
            intake_rows.append({
                'obj': intake,
                'title': intake.title,
                'status': intake.get_status_display(),
                'urgency': intake.get_urgency_display(),
                'lead': intake.case_coordinator.get_full_name() if intake.case_coordinator else '—',
                'category': intake.care_category_main.name if intake.care_category_main else '—',
                'region': intake.preferred_region.region_name if intake.preferred_region else '—',
                'created': intake.start_date,
            })

        ctx['intake_rows'] = intake_rows
        return ctx


class CaseIntakeDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    """Show details of a specific care intake."""
    model = CaseIntakeProcess
    template_name = 'contracts/intake_detail.html'
    context_object_name = 'intake'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(
            CaseIntakeProcess.objects.select_related(
                'organization', 'case_coordinator', 'care_category_main', 'care_category_sub', 'contract'
            ).prefetch_related('risk_factors'),
            org,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        intake = self.object

        assessment = CaseAssessment.objects.filter(due_diligence_process=intake).select_related('assessed_by').first()
        placement = PlacementRequest.objects.filter(due_diligence_process=intake).select_related('selected_provider').order_by('-updated_at').first()
        case_record = intake.case_record
        can_edit_case = _can_edit_intake(self.request.user, intake)

        open_tasks = Deadline.objects.for_organization(self.get_organization()).filter(
            due_diligence_process=intake,
            is_completed=False,
        ).select_related('assigned_to').order_by('due_date')[:5]
        open_signals = CareSignal.objects.for_organization(self.get_organization()).filter(
            due_diligence_process=intake,
            status__in=[CareSignal.SignalStatus.OPEN, CareSignal.SignalStatus.IN_PROGRESS],
        ).select_related('assigned_to').order_by('-updated_at')[:5]
        documents = Document.objects.filter(contract=case_record).order_by('-created_at')[:5] if case_record else Document.objects.none()

        assessment_href = reverse('careon:assessment_detail', kwargs={'pk': assessment.pk}) if assessment else f"{reverse('careon:assessment_create')}?intake={intake.pk}"
        assessment_action_label = 'Open beoordeling' if assessment else 'Beoordeling starten'
        assessment_status_label = assessment.get_assessment_status_display() if assessment else 'Nog niet gestart'

        matching_href = f"{reverse('careon:matching_dashboard')}?intake={intake.pk}"
        matching_status_label = 'Klaar voor matching' if assessment and assessment.assessment_status == CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING else 'Wacht op beoordeling'

        placement_href = reverse('careon:placement_detail', kwargs={'pk': placement.pk}) if placement else reverse('careon:matching_dashboard')
        placement_action_label = 'Open plaatsing' if placement else 'Start via matching'
        placement_status_label = placement.get_status_display() if placement else 'Nog niet gestart'

        if not placement:
            placement_phase_label = 'Nog niet gestart'
        elif placement.status == PlacementRequest.Status.APPROVED:
            placement_phase_label = 'Plaatsing bevestigd'
        elif placement.status == PlacementRequest.Status.IN_REVIEW:
            placement_phase_label = 'Aanbieder beoordeelt'
        elif placement.status == PlacementRequest.Status.REJECTED:
            placement_phase_label = 'Opnieuw matchen'
        else:
            placement_phase_label = 'Indicatie voorbereiding'

        if not can_edit_case:
            next_action = {
                'label': 'Alleen-lezen toegang',
                'href': reverse('careon:case_list'),
                'help': 'Je kunt deze casus bekijken, maar niet wijzigen. Neem contact op met een beheerder.',
            }
        elif not assessment:
            next_action = {
                'label': 'Start beoordeling',
                'href': assessment_href,
                'help': 'Deze casus heeft nog geen beoordeling. Rond eerst de beoordeling af.',
            }
        elif assessment.assessment_status != CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING:
            next_action = {
                'label': 'Werk beoordeling bij',
                'href': assessment_href,
                'help': 'De beoordeling is nog niet gereed voor matching.',
            }
        elif not placement:
            next_action = {
                'label': 'Koppel aanbieder',
                'href': matching_href,
                'help': 'Koppel nu een passende aanbieder via matching.',
            }
        else:
            next_action = {
                'label': 'Bevestig plaatsing',
                'href': placement_href,
                'help': 'Werk de plaatsingsbeslissing af en start opvolging.',
            }

        matching_requirements = [
            {
                'label': 'Beoordeling bestaat',
                'ok': bool(assessment),
            },
            {
                'label': 'Beoordelingstatus is Gereed voor matching',
                'ok': bool(assessment and assessment.assessment_status == CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING),
            },
            {
                'label': 'Beoordeling staat op klaar voor matching',
                'ok': bool(assessment and assessment.matching_ready),
            },
        ]
        ready_for_matching = all(item['ok'] for item in matching_requirements)
        matching_missing = [item['label'] for item in matching_requirements if not item['ok']]

        placement_requirements = [
            {
                'label': 'Aanbieder is toegewezen in matching',
                'ok': bool(placement and placement.selected_provider_id),
            },
            {
                'label': 'Plaatsing staat in beoordeling of bevestigd',
                'ok': bool(placement and placement.status in [PlacementRequest.Status.IN_REVIEW, PlacementRequest.Status.APPROVED]),
            },
        ]
        ready_for_placement = all(item['ok'] for item in placement_requirements)
        placement_missing = [item['label'] for item in placement_requirements if not item['ok']]

        active_flow_stage = _flow_stage_for_intake_status(intake.status)
        flow_order = ['aanvraag', 'beoordeling', 'matching', 'intake_aanbieder', 'plaatsing']
        flow_labels = {
            'aanvraag': 'Aanvraag',
            'beoordeling': 'Beoordeling',
            'matching': 'Matching',
            'intake_aanbieder': 'Intake aanbieder',
            'plaatsing': 'Plaatsing',
        }
        active_index = flow_order.index(active_flow_stage)
        flow_rail = []
        for idx, key in enumerate(flow_order):
            flow_rail.append(
                {
                    'key': key,
                    'label': flow_labels[key],
                    'active': key == active_flow_stage,
                    'completed': idx < active_index,
                }
            )

        if not can_edit_case:
            blocker_label = 'Geen bewerkrechten voor deze casus'
        elif not ready_for_matching:
            blocker_label = f"Niet gereed voor matching: {', '.join(matching_missing)}"
        elif not ready_for_placement:
            blocker_label = f"Niet gereed voor plaatsing: {', '.join(placement_missing)}"
        else:
            blocker_label = 'Geen blokkades; casus kan door naar de volgende stap'

        progress_label = (
            f"{open_tasks.count()} open taken · {open_signals.count()} open signalen"
            if (open_tasks.count() or open_signals.count())
            else 'Geen open taken of signalen'
        )

        placement_selected_provider = None
        if placement and placement.selected_provider:
            placement_selected_provider = placement.selected_provider
        elif placement and placement.proposed_provider:
            placement_selected_provider = placement.proposed_provider

        placement_action_href = reverse('careon:case_placement_action', kwargs={'pk': intake.pk})
        provider_response_action_href = reverse('careon:case_provider_response_action', kwargs={'pk': intake.pk})
        outcome_action_href = reverse('careon:case_outcome_action', kwargs={'pk': intake.pk})
        placement_status_actions = []
        if placement and can_edit_case:
            action_specs = [
                (PlacementRequest.Status.IN_REVIEW, 'Markeer: in beoordeling', 'Overdracht loopt, aanbieder beoordeelt intake.'),
                (PlacementRequest.Status.NEEDS_INFO, 'Markeer: info nodig', 'Aanvullende informatie opgevraagd bij ketenpartner.'),
                (PlacementRequest.Status.APPROVED, 'Bevestig plaatsing', 'Plaatsing bevestigd en overdracht afgerond.'),
                (PlacementRequest.Status.REJECTED, 'Markeer: afgewezen', 'Plaatsing afgewezen, terug naar matching.'),
            ]
            for status_code, label, note in action_specs:
                if placement.status != status_code:
                    placement_status_actions.append(
                        {
                            'status': status_code,
                            'label': label,
                            'note': note,
                        }
                    )

        handoff_docs_qs = Document.objects.none()
        if case_record:
            handoff_docs_qs = Document.objects.filter(
                contract=case_record,
                tags__icontains='event:provider_handoff',
            ).order_by('-created_at')
        latest_handoff_doc = handoff_docs_qs.first()

        placement_notification_qs = Notification.objects.filter(recipient=self.request.user)
        if placement:
            placement_notification_qs = placement_notification_qs.filter(
                Q(link__icontains=f'/care/plaatsingen/{placement.pk}/')
                | Q(link__icontains=f'/care/casussen/{intake.pk}/')
            )
        else:
            placement_notification_qs = placement_notification_qs.filter(link__icontains=f'/care/casussen/{intake.pk}/')
        latest_placement_notification = placement_notification_qs.order_by('-created_at').first()

        matching_preview_candidates = []
        if ready_for_matching:
            provider_profiles = (
                ProviderProfile.objects.filter(client__organization=self.get_organization(), client__status='ACTIVE')
                .select_related('client')
                .prefetch_related('target_care_categories')
            )
            matching_preview_candidates = _build_matching_suggestions_for_intake(intake, provider_profiles, limit=5)
            for idx, row in enumerate(matching_preview_candidates):
                row['capacity'] = f"{row['free_slots']} plekken beschikbaar" if row['free_slots'] > 0 else 'Beperkte capaciteit'
                row['cta_href'] = matching_href
                row['cta_label'] = 'Open matching'
        provider_outcome_context = _provider_outcome_context_for_candidates(
            intake=intake,
            candidates=matching_preview_candidates,
        )

        latest_assignment = PlacementRequest.objects.filter(
            due_diligence_process=intake,
            selected_provider__isnull=False,
        ).select_related('selected_provider').order_by('-updated_at').first()

        outcome_sections = _build_case_outcome_forms(intake, placement)
        outcome_timeline_events = _get_outcome_timeline_events(intake)

        matching_history = _matching_history_for_intake(intake, limit=8)
        rejected_options = [entry for entry in matching_history if entry.action == AuditLog.Action.REJECT]

        case_data = _build_case_data_for_intelligence(
            intake=intake,
            assessment=assessment,
            placement=placement,
            matching_preview_candidates=matching_preview_candidates,
            rejected_options=rejected_options,
            latest_assignment=latest_assignment,
            open_signals_count=open_signals.count(),
            open_tasks_count=open_tasks.count(),
        )
        intelligence_output = evaluate_case_intelligence(case_data)
        missing_information_alerts = _ordered_missing_information(intelligence_output['missing_information'])
        system_signals = _ordered_risk_signals(intelligence_output['risk_signals'])
        intelligence_flags = _build_intelligence_flags_from_signals(system_signals)
        safe_to_proceed = intelligence_output['safe_to_proceed']
        stop_reasons = intelligence_output['stop_reasons']

        provider_response_summary = _provider_response_summary(intake, placement)
        provider_response_actions = []
        if placement and can_edit_case:
            response_status = _normalize_provider_response_status_value(placement.provider_response_status)
            if response_status in {
                PlacementRequest.ProviderResponseStatus.PENDING,
                PlacementRequest.ProviderResponseStatus.NEEDS_INFO,
                PlacementRequest.ProviderResponseStatus.WAITLIST,
            }:
                provider_response_actions.append(
                    {
                        'action': 'resend_request',
                        'label': 'Stuur herinnering',
                        'note': 'Vraag de aanbieder opnieuw om reactie met een nieuwe reactietermijn.',
                    }
                )

            if response_status in {
                PlacementRequest.ProviderResponseStatus.PENDING,
                PlacementRequest.ProviderResponseStatus.NEEDS_INFO,
            }:
                provider_response_actions.append(
                    {
                        'action': 'provide_missing_info',
                        'label': 'Aanvullende info aangeleverd',
                        'note': 'Registreer dat ontbrekende informatie is aangevuld en zet reactie opnieuw open.',
                    }
                )

            if (
                response_status
                in {
                    PlacementRequest.ProviderResponseStatus.REJECTED,
                    PlacementRequest.ProviderResponseStatus.NO_CAPACITY,
                    PlacementRequest.ProviderResponseStatus.WAITLIST,
                }
                or intelligence_flags.get('provider_not_responding')
                or intelligence_flags.get('rematch_recommended')
            ):
                provider_response_actions.append(
                    {
                        'action': 'trigger_rematch',
                        'label': 'Start her-match',
                        'note': 'Zet casus terug naar matching en kies een alternatief.',
                    }
                )

        hint_map = {str(item.get('provider_id')): item for item in intelligence_output['candidate_hints']}
        top_candidate = matching_preview_candidates[0] if matching_preview_candidates else None
        for idx, row in enumerate(matching_preview_candidates):
            rule_hint = hint_map.get(str(row.get('provider_id')))
            if rule_hint:
                row['decision_hint'] = rule_hint.get('hint')
                row['decision_hint_code'] = rule_hint.get('hint_code')
                row['decision_trade_offs'] = rule_hint.get('trade_offs') or []
                row['decision_comparison_to_top'] = rule_hint.get('comparison_to_top') or ''
            else:
                row['decision_hint'] = _decision_guidance_hint(row, index=idx, top_candidate=top_candidate)
                row['decision_hint_code'] = 'fallback_hint'
                row['decision_trade_offs'] = []
                row['decision_comparison_to_top'] = ''

            outcome_context = provider_outcome_context.get(row.get('provider_id'))
            if not outcome_context:
                outcome_context = {
                    'evidence_level': 'none',
                    'evidence_label': 'Geen historie',
                    'summary': 'Nog geen vergelijkbare uitkomsthistorie voor deze aanbieder.',
                    'acceptance_label': '',
                    'quality_label': '',
                    'warning': '',
                }
            row['outcome_context'] = outcome_context

            if outcome_context.get('warning'):
                combined_trade_offs = list(row.get('decision_trade_offs') or [])
                if outcome_context['warning'] not in combined_trade_offs:
                    combined_trade_offs.append(outcome_context['warning'])
                row['decision_trade_offs'] = combined_trade_offs

        next_action = _map_rule_action_to_ui(
            can_edit_case=can_edit_case,
            rule_action=intelligence_output['next_best_action'],
            assessment_href=assessment_href,
            matching_href=matching_href,
            placement_href=placement_href,
            case_update_href=reverse('careon:case_update', kwargs={'pk': intake.pk}),
            monitor_href=reverse('careon:case_detail', kwargs={'pk': intake.pk}),
        )
        enhanced_next_action = next_action

        if system_signals:
            progress_label = f"{progress_label} · {len(system_signals)} systeemsignalen"

        has_placement = bool(placement)
        can_execute_matching_actions = can_edit_case and safe_to_proceed
        can_execute_placement_actions = has_placement and can_edit_case and safe_to_proceed

        matching_action_href = reverse('careon:case_matching_action', kwargs={'pk': intake.pk})
        matching_archive_href = f"{reverse('careon:matching_dashboard')}?intake={intake.pk}"

        selected_tab = (self.request.GET.get('tab') or 'tijdlijn').lower()
        tab_options = {'tijdlijn', 'documenten', 'taken', 'signalen', 'matching', 'plaatsing'}
        if selected_tab not in tab_options:
            selected_tab = 'tijdlijn'

        anonymized_title = intake.title
        if len(anonymized_title) > 42:
            anonymized_title = f'{anonymized_title[:39]}...'

        region_municipality_label = case_record.service_region if case_record and case_record.service_region else 'Niet ingevuld'

        if assessment and assessment.assessment_status == CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING:
            assessment_interpretation = 'Beoordeling staat op gereed voor matching.'
        elif assessment and assessment.assessment_status == CaseAssessment.AssessmentStatus.NEEDS_INFO:
            assessment_interpretation = 'Aanvullende informatie nodig voordat matching kan starten.'
        elif assessment:
            assessment_interpretation = 'Beoordeling loopt; werk status bij om volgende stap vrij te maken.'
        else:
            assessment_interpretation = 'Start de beoordeling om door te gaan naar matching.'

        can_create_case_document = bool(case_record) and can_edit_case
        case_document_href = reverse('careon:case_document_create', kwargs={'pk': intake.pk}) if can_create_case_document else reverse('careon:case_update', kwargs={'pk': intake.pk})
        if can_create_case_document:
            case_document_action_label = 'Document toevoegen'
        elif not case_record:
            case_document_action_label = 'Koppel eerst een casus'
        else:
            case_document_action_label = 'Geen bewerkrechten'

        upload_event = self.request.GET.get('event', 'documenten').strip() or 'documenten'
        case_document_context_href = case_document_href
        if can_create_case_document:
            case_document_context_href = f'{case_document_href}?phase={active_flow_stage}&event={upload_event}'

        flow_label_map = {
            'aanvraag': 'Aanvraag',
            'beoordeling': 'Beoordeling',
            'matching': 'Matching',
            'intake_aanbieder': 'Intake aanbieder',
            'plaatsing': 'Plaatsing',
        }

        case_document_rows = []
        for document in documents:
            linked_phase_key, linked_event = _extract_document_phase_event(document.tags)
            case_document_rows.append(
                {
                    'document': document,
                    'linked_phase': flow_label_map.get(linked_phase_key, linked_phase_key),
                    'linked_event': linked_event,
                }
            )

        overview_links = {
            'documents': reverse('careon:document_list'),
            'tasks': reverse('careon:task_list'),
            'signals': reverse('careon:signal_list'),
            'placements': reverse('careon:placement_list'),
        }

        ctx.update({
            'assessment_list': CaseAssessment.objects.filter(due_diligence_process=intake),
            'has_assessment': bool(assessment),
            'assessment_status': assessment_status_label if assessment else None,
            'assessment_status_label': assessment_status_label,
            'assessment_href': assessment_href,
            'assessment_action_label': assessment_action_label,
            'risk_factors_list': intake.risk_factors.all(),
            'case_record': case_record,
            'can_edit_case': can_edit_case,
            'matching_status_label': matching_status_label,
            'matching_href': matching_href,
            'placement_status_label': placement_status_label,
            'placement_phase_label': placement_phase_label,
            'placement_href': placement_href,
            'placement_action_label': placement_action_label,
            'has_placement': has_placement,
            'placement_selected_provider': placement_selected_provider,
            'placement_action_href': placement_action_href,
            'provider_response_action_href': provider_response_action_href,
            'provider_response_summary': provider_response_summary,
            'provider_response_actions': provider_response_actions,
            'outcome_action_href': outcome_action_href,
            'placement_status_actions': placement_status_actions,
            'can_execute_placement_actions': can_execute_placement_actions,
            'outcome_sections': outcome_sections,
            'outcome_timeline_events': outcome_timeline_events,
            'placement_handoff_docs_count': handoff_docs_qs.count() if case_record else 0,
            'latest_handoff_doc': latest_handoff_doc,
            'placement_notifications_count': placement_notification_qs.count(),
            'latest_placement_notification': latest_placement_notification,
            'open_tasks': open_tasks,
            'open_tasks_count': open_tasks.count(),
            'open_signals': open_signals,
            'open_signals_count': open_signals.count(),
            'documents': documents,
            'documents_count': documents.count(),
            'overview_links': overview_links,
            'next_action': next_action,
            'enhanced_next_action': enhanced_next_action,
            'next_action_severity': next_action['severity'],
            'next_action_state_label': next_action['state_label'],
            'safe_to_proceed': safe_to_proceed,
            'stop_reasons': stop_reasons,
            'system_signals': system_signals,
            'intelligence_flags': intelligence_flags,
            'missing_information_alerts': missing_information_alerts,
            'can_create_case_document': can_create_case_document,
            'can_create_case_task': can_edit_case,
            'can_create_case_signal': can_edit_case,
            'can_execute_matching_actions': can_execute_matching_actions,
            'case_document_href': case_document_href,
            'case_document_context_href': case_document_context_href,
            'case_document_action_label': case_document_action_label,
            'case_document_rows': case_document_rows,
            'matching_requirements': matching_requirements,
            'ready_for_matching': ready_for_matching,
            'matching_missing': matching_missing,
            'placement_requirements': placement_requirements,
            'ready_for_placement': ready_for_placement,
            'placement_missing': placement_missing,
            'flow_rail': flow_rail,
            'active_flow_stage': active_flow_stage,
            'blocker_label': blocker_label,
            'progress_label': progress_label,
            'matching_preview_candidates': matching_preview_candidates,
            'matching_action_href': matching_action_href,
            'matching_archive_href': matching_archive_href,
            'latest_assignment': latest_assignment,
            'matching_history': matching_history,
            'rejected_options': rejected_options,
            'selected_tab': selected_tab,
            'anonymized_title': anonymized_title,
            'region_municipality_label': region_municipality_label,
            'assessment_interpretation': assessment_interpretation,
        })

        return ctx


class CaseIntakeCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    """Create a new care intake."""
    model = CaseIntakeProcess
    form_class = CaseIntakeProcessForm
    template_name = 'contracts/intake_form.html'

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response['X-Careon-Template-Version'] = 'intake_form'
        return _disable_response_caching(response)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'is_edit': False,
            'page_title': 'Nieuwe casus',
            'button_text': 'Casus aanmaken',
        })
        return ctx

    def form_valid(self, form):
        org = get_user_organization(self.request.user)
        set_organization_on_instance(form.instance, org)
        if not form.instance.start_date:
            form.instance.start_date = date.today()
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'CaseIntakeProcess', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Casus "{self.object.title}" aangemaakt. Volgende stap: ga verder met de intakefase.')
        return response

    def get_success_url(self):
        return reverse('careon:case_detail', kwargs={'pk': self.object.pk})


class CaseIntakeUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    """Update an existing care intake."""
    model = CaseIntakeProcess
    form_class = CaseIntakeProcessForm
    template_name = 'contracts/intake_form.html'

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response['X-Careon-Template-Version'] = 'intake_form'
        return _disable_response_caching(response)

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(CaseIntakeProcess.objects.all(), org)

    def dispatch(self, request, *args, **kwargs):
        intake = self.get_object()
        if not _can_edit_intake(request.user, intake):
            _log_pilot_issue(
                request,
                category='case_update_forbidden',
                detail=f'intake={intake.pk}',
            )
            return HttpResponseForbidden('Je hebt geen rechten om deze casus te bewerken.')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'is_edit': True,
            'page_title': f'Casus bewerken: {self.object.title}',
            'button_text': 'Wijzigingen opslaan',
        })
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'CaseIntakeProcess', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Casus "{self.object.title}" bijgewerkt.')
        return response

    def get_success_url(self):
        return reverse('careon:case_detail', kwargs={'pk': self.object.pk})


# ==================== CASE ASSESSMENT VIEWS ====================
# FIX #2: Wire CaseAssessment into care workflow

class CaseAssessmentListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    """List all case assessments (beoordelingen) for matching."""
    model = CaseAssessment
    template_name = 'contracts/assessment_list.html'
    context_object_name = 'assessments'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = CaseAssessment.objects.filter(
            due_diligence_process__organization=org,
        ).select_related(
            'due_diligence_process', 'assessed_by'
        )

        # Filter by status
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(assessment_status=status)

        # Search by case title/ID
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(due_diligence_process__title__icontains=q)
            ).distinct()

        return qs.order_by('-updated_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        org_assessments = CaseAssessment.objects.filter(due_diligence_process__organization=org)

        ctx.update({
            'total_assessments': org_assessments.count(),
            'pending_assessments': org_assessments.filter(
                assessment_status=CaseAssessment.AssessmentStatus.DRAFT
            ).count(),
            'ready_for_matching': org_assessments.filter(
                assessment_status=CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING
            ).count(),
            'status_choices': CaseAssessment.AssessmentStatus.choices,
            'search_query': self.request.GET.get('q', ''),
        })

        return ctx


class CaseAssessmentDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    """Show details of a specific assessment."""
    model = CaseAssessment
    template_name = 'contracts/assessment_detail.html'
    context_object_name = 'assessment'

    def get_queryset(self):
        org = self.get_organization()
        return CaseAssessment.objects.filter(
            due_diligence_process__organization=org,
        ).select_related(
            'due_diligence_process', 'assessed_by'
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        assessment = self.object
        intake = assessment.intake
        can_edit_assessment = _can_edit_assessment(self.request.user, assessment)
        matching_href = f"{reverse('careon:matching_dashboard')}?intake={intake.pk}"

        matching_requirements = [
            {
                'label': 'Status op Gereed voor matching',
                'ok': assessment.assessment_status == CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING,
            },
            {
                'label': 'Klaar voor matching staat op Ja',
                'ok': bool(assessment.matching_ready),
            },
            {
                'label': 'Minimaal 1 signaal beoordeeld',
                'ok': bool((assessment.risk_signals or '').strip()),
            },
        ]
        matching_ready = all(item['ok'] for item in matching_requirements)
        matching_missing = [item['label'] for item in matching_requirements if not item['ok']]

        ctx.update({
            'intake': intake,
            'can_edit_assessment': can_edit_assessment,
            'matching_href': matching_href,
            'matching_requirements': matching_requirements,
            'matching_ready': matching_ready,
            'matching_missing': matching_missing,
        })

        return ctx


class CaseAssessmentCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    """Create a new assessment for a care intake."""
    model = CaseAssessment
    form_class = CaseAssessmentForm
    template_name = 'contracts/assessment_form.html'

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill if linked from intake detail page
        intake_id = self.request.GET.get('intake')
        if intake_id:
            try:
                org = self.get_organization()
                intake = scope_queryset_for_organization(
                    CaseIntakeProcess.objects.all(), org
                ).get(pk=intake_id)
                initial['due_diligence_process'] = intake
            except CaseIntakeProcess.DoesNotExist:
                pass
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'is_edit': False,
            'page_title': 'Nieuwe beoordeling',
            'button_text': 'Beoordeling aanmaken',
        })
        return ctx

    def form_valid(self, form):
        org = get_user_organization(self.request.user)
        set_organization_on_instance(form.instance, org)
        if form.instance.intake and not _can_edit_intake(self.request.user, form.instance.intake):
            _log_pilot_issue(
                self.request,
                category='assessment_create_forbidden',
                detail=f'intake={form.instance.intake.pk}',
            )
            return HttpResponseForbidden('Je hebt geen rechten om voor deze casus een beoordeling aan te maken.')
        form.instance.assessed_by = self.request.user
        if not form.instance.assessment_status:
            form.instance.assessment_status = CaseAssessment.AssessmentStatus.DRAFT
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'CaseAssessment', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, 'Beoordeling aangemaakt. Volgende stap: matching.')
        return response

    def get_success_url(self):
        return reverse('careon:assessment_detail', kwargs={'pk': self.object.pk})


class CaseAssessmentUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    """Update an existing assessment."""
    model = CaseAssessment
    form_class = CaseAssessmentForm
    template_name = 'contracts/assessment_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return CaseAssessment.objects.filter(due_diligence_process__organization=org)

    def dispatch(self, request, *args, **kwargs):
        assessment = self.get_object()
        if not _can_edit_assessment(request.user, assessment):
            _log_pilot_issue(
                request,
                category='assessment_update_forbidden',
                detail=f'assessment={assessment.pk}',
            )
            return HttpResponseForbidden('Je hebt geen rechten om deze beoordeling te bewerken.')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'is_edit': True,
            'page_title': 'Beoordeling bewerken',
            'button_text': 'Wijzigingen opslaan',
        })
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'CaseAssessment', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, 'Beoordeling bijgewerkt.')
        return response

    def get_success_url(self):
        return reverse('careon:assessment_detail', kwargs={'pk': self.object.pk})


# ==================== WAIT TIME VIEWS (Wachttijden) ====================

class WaitTimeListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = TrustAccount
    template_name = 'contracts/waittime_list.html'
    context_object_name = 'waittimes'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = TrustAccount.objects.filter(provider__organization=org).select_related('provider').order_by('provider__name', 'region')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(provider__name__icontains=q) | Q(region__icontains=q) | Q(care_type__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        qs = TrustAccount.objects.filter(provider__organization=org)
        ctx.update({
            'total_count': qs.count(),
            'no_capacity_count': qs.filter(open_slots__lte=0).count(),
            'avg_wait_days': round(qs.aggregate(avg=Avg('wait_days'))['avg'] or 0),
            'search_query': self.request.GET.get('q', ''),
        })
        return ctx


class WaitTimeDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = TrustAccount
    template_name = 'contracts/waittime_detail.html'
    context_object_name = 'waittime'

    def get_queryset(self):
        org = self.get_organization()
        return TrustAccount.objects.filter(provider__organization=org).select_related('provider')


class WaitTimeCreateView(TenantScopedQuerysetMixin, LoginRequiredMixin, CreateView):
    model = TrustAccount
    form_class = TrustAccountForm
    template_name = 'contracts/waittime_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_edit'] = False
        ctx['page_title'] = 'Wachttijd registreren'
        return ctx

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Wachttijd geregistreerd.')
        return response

    def get_success_url(self):
        return reverse('careon:waittime_detail', kwargs={'pk': self.object.pk})


class WaitTimeUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = TrustAccount
    form_class = TrustAccountForm
    template_name = 'contracts/waittime_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return TrustAccount.objects.filter(provider__organization=org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_edit'] = True
        ctx['page_title'] = 'Wachttijd bijwerken'
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Wachttijd bijgewerkt.')
        return response

    def get_success_url(self):
        return reverse('careon:waittime_detail', kwargs={'pk': self.object.pk})


# ==================== CARE SIGNAL VIEWS (Signalen) ====================

class CareSignalListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = CareSignal
    template_name = 'contracts/signal_list.html'
    context_object_name = 'signals'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = CareSignal.objects.for_organization(org).select_related('due_diligence_process', 'assigned_to', 'case_record').order_by('-created_at')

        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(due_diligence_process__title__icontains=q)
                | Q(description__icontains=q)
            ).distinct()

        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        risk_level = self.request.GET.get('risk_level')
        if risk_level:
            qs = qs.filter(risk_level=risk_level)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        all_qs = CareSignal.objects.for_organization(org)
        editable_signal_ids = set()
        signal_rows = []
        for signal in ctx['signals']:
            linked_case = signal.case_record or (signal.intake.case_record if signal.intake else None)
            if linked_case is None or can_access_case_action(self.request.user, linked_case, CaseAction.EDIT):
                editable_signal_ids.add(signal.pk)

            case_href = None
            intake_id = getattr(signal, 'due_diligence_process_id', None)
            if intake_id:
                case_href = _case_detail_tab_href(intake_id, 'signalen')

            signal_rows.append({
                'signal': signal,
                'case_href': case_href,
                'can_edit': signal.pk in editable_signal_ids,
            })

        ctx.update({
            'total_count': all_qs.count(),
            'open_count': all_qs.filter(status=CareSignal.SignalStatus.OPEN).count(),
            'critical_count': all_qs.filter(
                risk_level=CareSignal.RiskLevel.CRITICAL,
                status__in=[CareSignal.SignalStatus.OPEN, CareSignal.SignalStatus.IN_PROGRESS],
            ).count(),
            'status_choices': CareSignal.SignalStatus.choices,
            'risk_level_choices': CareSignal.RiskLevel.choices,
            'search_query': self.request.GET.get('q', ''),
            'editable_signal_ids': editable_signal_ids,
            'signal_rows': signal_rows,
        })
        return ctx


class CareSignalDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = CareSignal
    template_name = 'contracts/signal_detail.html'
    context_object_name = 'signal'

    def get_queryset(self):
        org = self.get_organization()
        return CareSignal.objects.for_organization(org).select_related('due_diligence_process', 'assigned_to', 'case_record', 'created_by')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        linked_case = _resolve_signal_case(self.object)
        ctx['can_edit_signal'] = (linked_case is None) or can_access_case_action(
            self.request.user,
            linked_case,
            CaseAction.EDIT,
        )
        return ctx


class CareSignalCreateView(TenantScopedQuerysetMixin, LoginRequiredMixin, CreateView):
    model = CareSignal
    form_class = CareSignalForm
    template_name = 'contracts/signal_form.html'

    def get_initial(self):
        initial = super().get_initial()
        intake_id = self.request.GET.get('intake')
        if intake_id:
            try:
                org = self.get_organization()
                intake = scope_queryset_for_organization(CaseIntakeProcess.objects.all(), org).get(pk=intake_id)
                initial['due_diligence_process'] = intake
            except CaseIntakeProcess.DoesNotExist:
                pass
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_edit'] = False
        ctx['page_title'] = 'Nieuw signaal'
        return ctx

    def form_valid(self, form):
        intake = form.cleaned_data.get('due_diligence_process')
        if intake and intake.case_record and not can_access_case_action(self.request.user, intake.case_record, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om signalen voor deze casus toe te voegen.')
        form.instance.created_by = self.request.user
        if intake and intake.contract_id and not form.instance.case_record_id:
            form.instance.case_record = intake.case_record
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'CareSignal', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, 'Signaal aangemaakt.')
        return response

    def get_success_url(self):
        return reverse('careon:signal_detail', kwargs={'pk': self.object.pk})


class CareSignalUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = CareSignal
    form_class = CareSignalForm
    template_name = 'contracts/signal_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return CareSignal.objects.for_organization(org)

    def dispatch(self, request, *args, **kwargs):
        signal = self.get_object()
        linked_case = _resolve_signal_case(signal)
        if linked_case and not can_access_case_action(request.user, linked_case, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om signalen van deze casus te bewerken.')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_edit'] = True
        ctx['page_title'] = 'Signaal bewerken'
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'CareSignal', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, 'Signaal bijgewerkt.')
        return response

    def get_success_url(self):
        return reverse('careon:signal_detail', kwargs={'pk': self.object.pk})


# ==================== PLACEMENT REQUEST VIEWS (Plaatsingen) ====================

def _placement_phase_label(placement):
    if placement.status == PlacementRequest.Status.APPROVED:
        return 'Plaatsing bevestigd'
    if placement.status == PlacementRequest.Status.IN_REVIEW:
        return 'Aanbieder beoordeelt'
    if placement.status == PlacementRequest.Status.NEEDS_INFO:
        return 'Aanvullende informatie nodig'
    if placement.status == PlacementRequest.Status.REJECTED:
        return 'Opnieuw matchen'
    return 'Indicatie voorbereiding'


class PlacementRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = PlacementRequest
    template_name = 'contracts/placement_list.html'
    context_object_name = 'placements'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = PlacementRequest.objects.filter(due_diligence_process__organization=org).select_related(
            'due_diligence_process', 'proposed_provider', 'selected_provider'
        ).order_by('-updated_at')

        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(due_diligence_process__title__icontains=q)
                | Q(proposed_provider__name__icontains=q)
                | Q(selected_provider__name__icontains=q)
            ).distinct()

        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        all_qs = PlacementRequest.objects.filter(due_diligence_process__organization=org)
        editable_placement_ids = set()
        for placement in ctx['placements']:
            linked_case = placement.intake.case_record if placement.intake else None
            if linked_case is None or can_access_case_action(self.request.user, linked_case, CaseAction.EDIT):
                editable_placement_ids.add(placement.pk)
        ctx.update({
            'total_count': all_qs.count(),
            'approved_count': all_qs.filter(status=PlacementRequest.Status.APPROVED).count(),
            'in_review_count': all_qs.filter(status=PlacementRequest.Status.IN_REVIEW).count(),
            'status_choices': PlacementRequest.Status.choices,
            'search_query': self.request.GET.get('q', ''),
            'editable_placement_ids': editable_placement_ids,
            'placement_rows': [
                {
                    'placement': placement,
                    'phase_label': _placement_phase_label(placement),
                }
                for placement in ctx['placements']
            ],
        })
        return ctx


class PlacementRequestDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = PlacementRequest
    template_name = 'contracts/placement_detail.html'
    context_object_name = 'placement'

    def get_queryset(self):
        org = self.get_organization()
        return PlacementRequest.objects.filter(due_diligence_process__organization=org).select_related(
            'due_diligence_process', 'proposed_provider', 'selected_provider'
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['placement_phase_label'] = _placement_phase_label(self.object)
        linked_case = self.object.intake.case_record if self.object.intake else None
        ctx['can_edit_placement'] = (linked_case is not None) and can_access_case_action(
            self.request.user,
            linked_case,
            CaseAction.EDIT,
        )
        return ctx


class PlacementRequestUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = PlacementRequest
    form_class = PlacementRequestForm
    template_name = 'contracts/placement_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return PlacementRequest.objects.filter(due_diligence_process__organization=org)

    def dispatch(self, request, *args, **kwargs):
        placement = self.get_object()
        if not placement.due_diligence_process_id:
            return HttpResponseForbidden('Plaatsing zonder gekoppelde casus is alleen inspecteerbaar.')
        linked_case = placement.intake.case_record if placement.intake else None
        if linked_case is None:
            return HttpResponseForbidden('Plaatsing zonder gekoppelde casus is alleen inspecteerbaar.')
        if not can_access_case_action(request.user, linked_case, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om plaatsing voor deze casus te wijzigen.')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_edit'] = True
        ctx['page_title'] = 'Plaatsing bewerken'
        ctx['intake'] = self.object.intake
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'PlacementRequest', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, 'Plaatsing bijgewerkt.')
        return response

    def get_success_url(self):
        return reverse('careon:placement_detail', kwargs={'pk': self.object.pk})


# ==================== CASE-SCOPED CREATE VIEWS ====================

class _CaseScopedIntakeMixin(TenantScopedQuerysetMixin):
    intake = None

    def _load_intake(self):
        if self.intake is None:
            org = get_user_organization(self.request.user)
            self.intake = get_object_or_404(
                scope_queryset_for_organization(CaseIntakeProcess.objects.select_related('contract'), org),
                pk=self.kwargs['pk'],
            )
        return self.intake

    def dispatch(self, request, *args, **kwargs):
        intake = self._load_intake()
        if not _can_edit_intake(request.user, intake):
            _log_pilot_issue(
                request,
                category='case_scoped_create_forbidden',
                detail=f'intake={intake.pk}',
            )
            return HttpResponseForbidden('Je hebt geen rechten om deze casus bij te werken.')
        return super().dispatch(request, *args, **kwargs)


class CaseScopedDeadlineCreateView(_CaseScopedIntakeMixin, DeadlineCreateView):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            data = kwargs.get('data', self.request.POST).copy()
            data['due_diligence_process'] = str(self._load_intake().pk)
            kwargs['data'] = data
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial['due_diligence_process'] = self._load_intake()
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        intake = self._load_intake()
        form.initial['due_diligence_process'] = intake.pk
        return form

    def form_valid(self, form):
        intake = self._load_intake()
        form.instance.due_diligence_process = intake
        if intake.contract_id:
            form.instance.case_record = intake.case_record
        response = super().form_valid(form)
        messages.success(self.request, f'Taak toegevoegd aan casus "{intake.title}".')
        return response

    def get_success_url(self):
        return f"{reverse('careon:case_detail', kwargs={'pk': self._load_intake().pk})}?tab=taken"


class CaseScopedCareSignalCreateView(_CaseScopedIntakeMixin, CareSignalCreateView):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            data = kwargs.get('data', self.request.POST).copy()
            data['due_diligence_process'] = str(self._load_intake().pk)
            kwargs['data'] = data
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial['due_diligence_process'] = self._load_intake()
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        intake = self._load_intake()
        form.initial['due_diligence_process'] = intake.pk
        return form

    def form_valid(self, form):
        intake = self._load_intake()
        form.instance.due_diligence_process = intake
        if intake.contract_id:
            form.instance.case_record = intake.case_record
        response = super().form_valid(form)
        messages.success(self.request, f'Signaal toegevoegd aan casus "{intake.title}".')
        return response

    def get_success_url(self):
        return f"{reverse('careon:case_detail', kwargs={'pk': self._load_intake().pk})}?tab=signalen"


class CaseScopedDocumentCreateView(_CaseScopedIntakeMixin, DocumentCreateView):
    def dispatch(self, request, *args, **kwargs):
        intake = self._load_intake()
        if not intake.contract_id:
            messages.error(request, 'Koppel eerst een casusrecord voordat je documenten toevoegt.')
            return redirect('careon:case_detail', pk=intake.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        intake = self._load_intake()
        phase = (self.request.GET.get('phase') or '').strip()
        event = (self.request.GET.get('event') or '').strip()
        if intake.contract_id:
            initial['contract'] = intake.case_record
        if phase or event:
            initial['tags'] = _merge_document_context_tags(initial.get('tags', ''), phase=phase, event=event)
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        intake = self._load_intake()
        phase = (self.request.GET.get('phase') or '').strip()
        event = (self.request.GET.get('event') or '').strip()
        phase_label = {
            'aanvraag': 'Aanvraag',
            'beoordeling': 'Beoordeling',
            'matching': 'Matching',
            'intake_aanbieder': 'Intake aanbieder',
            'plaatsing': 'Plaatsing',
        }.get(phase, phase)
        ctx['intake'] = intake
        ctx['document_context_phase'] = phase_label
        ctx['document_context_event'] = event
        ctx['cancel_href'] = f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=documenten"
        return ctx

    def form_valid(self, form):
        intake = self._load_intake()
        phase = (self.request.GET.get('phase') or '').strip()
        event = (self.request.GET.get('event') or '').strip()
        form.instance.contract = intake.case_record
        if phase or event:
            form.instance.tags = _merge_document_context_tags(form.instance.tags, phase=phase, event=event)
        response = super().form_valid(form)
        messages.success(self.request, f'Document toegevoegd aan casus "{intake.title}".')
        return response

    def get_success_url(self):
        intake = self._load_intake()
        phase = (self.request.GET.get('phase') or '').strip()
        event = (self.request.GET.get('event') or '').strip()
        url = f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=documenten"
        if phase:
            url += f'&phase={phase}'
        if event:
            url += f'&event={event}'
        return url
