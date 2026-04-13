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
)
from .models import (
    Organization, OrganizationMembership, OrganizationInvitation,
    CareCase, PlacementRequest, CareTask, CareSignal,
    Workflow,
    CaseIntakeProcess, Budget, BudgetExpense,
    Client, CareConfiguration, Document, TrustAccount, ProviderProfile,
    Deadline, AuditLog, Notification, UserProfile, CaseAssessment,
    MunicipalityConfiguration, RegionalConfiguration,
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
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(industry__icontains=q))
        if status:
            if status == 'REJECTED_OR_INFO':
                qs = qs.filter(status__in=[PlacementRequest.Status.REJECTED, PlacementRequest.Status.NEEDS_INFO])
            else:
                qs = qs.filter(status=status)
        if client_type:
            qs = qs.filter(client_type=client_type)
        return qs.order_by('name')

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
        log_action(self.request.user, 'CREATE', 'Client', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Aanbieder "{self.object.name}" is aangemaakt.')
        return response


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
        log_action(self.request.user, 'UPDATE', 'Client', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Aanbieder "{self.object.name}" is bijgewerkt.')
        return response


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
        for doc in ctx['documents']:
            if not doc.contract or can_access_case_action(self.request.user, doc.contract, CaseAction.EDIT):
                editable_document_ids.add(doc.pk)
        ctx.update({
            'total_documents': all_docs.count(),
            'review_documents': all_docs.filter(status=Document.Status.REVIEW).count(),
            'draft_documents': all_docs.filter(status=Document.Status.DRAFT).count(),
            'editable_document_ids': editable_document_ids,
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
                if linked_case:
                    open_href = get_contract_section_url(linked_case, 'intake-section')
                else:
                    open_href = reverse('careon:intake_detail', kwargs={'pk': deadline.intake.pk})
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
    return redirect('careon:deadline_list')


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
    }
    return render(request, 'contracts/reports_dashboard.html', context)


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
        provider = get_object_or_404(
            Client.objects.filter(organization=org, status='ACTIVE'),
            pk=request.POST.get('provider_id'),
        )
        intake = assessment.intake
        if not _can_edit_intake(request.user, intake):
            _log_pilot_issue(
                request,
                category='matching_forbidden',
                detail=f'intake={getattr(intake, "pk", "-")}',
            )
            return HttpResponseForbidden('Je hebt geen rechten om matching voor deze casus bij te werken.')

        placement, created = PlacementRequest.objects.get_or_create(
            due_diligence_process=intake,
            defaults={
                'status': PlacementRequest.Status.IN_REVIEW,
                'proposed_provider': provider,
                'selected_provider': provider,
                'care_form': intake.preferred_care_form,
                'decision_notes': 'Automatisch toegewezen vanuit matching-dashboard.',
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

        messages.success(
            request,
            f'Aanbieder {provider.name} gekoppeld aan casus "{intake.title}".',
        )
        return redirect('careon:matching_dashboard')

    provider_profiles = (
        ProviderProfile.objects.filter(client__organization=org, client__status='ACTIVE')
        .select_related('client')
        .prefetch_related('target_care_categories')
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

    def _form_match(profile, intake):
        return {
            CaseIntakeProcess.CareForm.OUTPATIENT: profile.offers_outpatient,
            CaseIntakeProcess.CareForm.DAY_TREATMENT: profile.offers_day_treatment,
            CaseIntakeProcess.CareForm.RESIDENTIAL: profile.offers_residential,
            CaseIntakeProcess.CareForm.CRISIS: profile.offers_crisis,
        }.get(intake.preferred_care_form, False)

    def _urgency_match(profile, intake):
        return {
            CaseIntakeProcess.Urgency.LOW: profile.handles_low_urgency,
            CaseIntakeProcess.Urgency.MEDIUM: profile.handles_medium_urgency,
            CaseIntakeProcess.Urgency.HIGH: profile.handles_high_urgency,
            CaseIntakeProcess.Urgency.CRISIS: profile.handles_crisis_urgency,
        }.get(intake.urgency, False)

    rows = []
    for assessment in assessments:
        intake = assessment.intake
        can_assign = _can_edit_intake(request.user, intake)
        suggestions = []
        for profile in provider_profiles:
            score = 0
            reasons = []

            category_match = False
            if intake.care_category_main_id:
                category_match = profile.target_care_categories.filter(id=intake.care_category_main_id).exists()
                if category_match:
                    score += 40
                    reasons.append('Categorie match')

            urgency_match = _urgency_match(profile, intake)
            if urgency_match:
                score += 20
                reasons.append('Urgentie match')

            care_form_match = _form_match(profile, intake)
            if care_form_match:
                score += 20
                reasons.append('Zorgvorm match')

            free_slots = max(profile.max_capacity - profile.current_capacity, 0)
            if free_slots > 0:
                score += min(free_slots * 4, 20)
                reasons.append(f'{free_slots} vrije plekken')

            if profile.average_wait_days <= 14:
                score += 10
                reasons.append('Korte wachttijd')
            elif profile.average_wait_days <= 28:
                score += 5
                reasons.append('Acceptabele wachttijd')

            suggestions.append(
                {
                    'provider_id': profile.client_id,
                    'provider_name': profile.client.name,
                    'match_score': min(score, 100),
                    'category_match': category_match,
                    'urgency_match': urgency_match,
                    'care_form_match': care_form_match,
                    'free_slots': free_slots,
                    'avg_wait_days': profile.average_wait_days,
                    'reason': reasons[0] if reasons else 'Handmatige beoordeling nodig',
                }
            )

        suggestions.sort(key=lambda row: row['match_score'], reverse=True)
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


# ==================== DASHBOARD VIEW ====================

def dashboard(request):
    today = date.today()
    now = timezone.now()
    seven_days = today + timedelta(days=7)

    org = get_user_organization(request.user)

    stagnation_days = 7
    provider_response_days = 3
    low_capacity_threshold = 3
    overload_threshold = 5
    wait_threshold = 2

    case_records_qs = scope_queryset_for_organization(CareCase.objects.all(), org)
    clients_qs = scope_queryset_for_organization(Client.objects.all(), org)
    configurations_qs = scope_queryset_for_organization(CareConfiguration.objects.all(), org)
    workflows_qs = scope_queryset_for_organization(Workflow.objects.all(), org)
    documents_qs = scope_queryset_for_organization(Document.objects.all(), org)
    due_diligence_qs = scope_queryset_for_organization(CaseIntakeProcess.objects.all(), org)

    tasks_qs = CareTask.objects.for_organization(org) if org else CareTask.objects.none()
    risks_qs = CareSignal.objects.for_organization(org) if org else CareSignal.objects.none()
    deadlines_qs = Deadline.objects.for_organization(org)
    case_assessments_qs = (
        CaseAssessment.objects.filter(due_diligence_process__organization=org)
        .select_related('due_diligence_process', 'due_diligence_process__contract')
        if org else CaseAssessment.objects.none()
    )

    case_stats = case_records_qs.aggregate(
        total=Count('id'),
        intake=Count('id', filter=Q(status='DRAFT')),
        without_match=Count('id', filter=Q(status__in=['PENDING', 'IN_REVIEW'])),
        active=Count('id', filter=Q(status='ACTIVE')),
        completed=Count('id', filter=Q(status__in=['COMPLETED', 'EXPIRED', 'TERMINATED', 'CANCELLED'])),
    )

    client_stats = clients_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='ACTIVE')),
    )
    configuration_stats = configurations_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
    )

    intake_stats = due_diligence_qs.aggregate(
        in_progress=Count('id', filter=Q(status__in=['PLANNING', 'IN_PROGRESS', 'REVIEW'])),
    )

    task_stats = tasks_qs.aggregate(
        pending=Count('id', filter=Q(status='PENDING')),
        urgent=Count('id', filter=Q(status='PENDING', priority__in=['HIGH', 'URGENT'])),
    )
    workflow_stats = workflows_qs.aggregate(
        active=Count('id', filter=Q(status='ACTIVE')),
    )
    risk_stats = risks_qs.aggregate(
        high_critical=Count('id', filter=Q(risk_level__in=['HIGH', 'CRITICAL'])),
    )

    deadline_stats = deadlines_qs.aggregate(
        overdue=Count('id', filter=Q(is_completed=False, due_date__lt=today)),
        upcoming=Count('id', filter=Q(
            is_completed=False,
            due_date__gte=today,
            due_date__lte=seven_days,
        )),
    )

    unread_notifications = 0
    if request.user.is_authenticated:
        unread_notifications = Notification.objects.filter(
            recipient=request.user, is_read=False).count()

    recent_audit = list(
        AuditLog.objects.select_related('user').order_by('-timestamp')[:8]
    )

    status_counts = case_records_qs.values('status').annotate(count=Count('id'))
    status_counts_dict = {item['status']: item['count'] for item in status_counts}
    phase_counts = case_records_qs.values('case_phase').annotate(count=Count('id'))
    phase_counts_dict = {item['case_phase']: item['count'] for item in phase_counts}
    case_status_data_values = [
        {'label': 'Nieuwe casus', 'count': status_counts_dict.get(CareCase.Status.DRAFT, 0), 'tone': 'pf-draft'},
        {'label': 'Casus (persoonsbeeld, diagnoses, indicatie)', 'count': status_counts_dict.get(CareCase.Status.IN_REVIEW, 0), 'tone': 'pf-review'},
        {'label': 'Beoordeling', 'count': phase_counts_dict.get(CareCase.CasePhase.BEOORDELING, 0), 'tone': 'pf-review'},
        {'label': 'Matching', 'count': phase_counts_dict.get(CareCase.CasePhase.MATCHING, 0), 'tone': 'pf-other'},
        {'label': 'Intake', 'count': phase_counts_dict.get(CareCase.CasePhase.INTAKE, 0), 'tone': 'pf-active'},
        {'label': 'Plaatsing', 'count': phase_counts_dict.get(CareCase.CasePhase.PLAATSING, 0), 'tone': 'pf-expired'},
    ]

    total_documents = documents_qs.count()

    total_cases = case_stats['total'] or 0
    active_cases = case_stats['active'] or 0
    intake_cases = case_stats['intake'] or 0
    cases_without_match = case_stats['without_match'] or 0
    completed_cases = case_stats['completed'] or 0

    total_clients = client_stats['total'] or 0
    active_clients = client_stats['active'] or 0
    total_configurations = configuration_stats['total'] or 0
    active_configurations = configuration_stats['active'] or 0

    case_phase_count = due_diligence_qs.filter(status=CaseIntakeProcess.ProcessStatus.INTAKE).count()
    assessment_phase_count = due_diligence_qs.filter(status=CaseIntakeProcess.ProcessStatus.ASSESSMENT).count()
    matching_phase_count = due_diligence_qs.filter(status=CaseIntakeProcess.ProcessStatus.MATCHING).count()
    placement_phase_count = due_diligence_qs.filter(status=CaseIntakeProcess.ProcessStatus.DECISION).count()
    followup_phase_count = due_diligence_qs.filter(status=CaseIntakeProcess.ProcessStatus.COMPLETED).count()
    intake_phase_count = case_phase_count
    pending_tasks = task_stats['pending'] or 0
    urgent_task_count = task_stats['urgent'] or 0
    active_workflows = workflow_stats['active'] or 0
    risk_count = risk_stats['high_critical'] or 0
    recent_signals = list(
        risks_qs.select_related('due_diligence_process', 'assigned_to')
        .order_by('-created_at')[:6]
    )
    followup_tasks = list(
        deadlines_qs.select_related('due_diligence_process', 'assigned_to')
        .filter(is_completed=False)
        .order_by('due_date', 'due_time')[:8]
    )

    overdue_deadlines = deadline_stats['overdue'] or 0
    upcoming_deadline_count = deadline_stats['upcoming'] or 0

    stale_cutoff = now - timedelta(days=stagnation_days)

    urgent_case_ids = set(
        contract_id for contract_id in case_records_qs.filter(risk_level__in=['HIGH', 'CRITICAL']).values_list('id', flat=True)
        if contract_id
    )
    urgent_case_ids.update(
        contract_id for contract_id in deadlines_qs.filter(
            is_completed=False,
            due_date__lt=today,
            case_record__isnull=False,
        ).values_list('case_record_id', flat=True)
        if contract_id
    )
    urgent_case_ids.update(
        contract_id for contract_id in tasks_qs.filter(
            status='PENDING',
            priority__in=['HIGH', 'URGENT'],
            case_record__isnull=False,
        ).values_list('case_record_id', flat=True)
        if contract_id
    )
    urgent_case_count = len(urgent_case_ids)

    selected_case_id = request.GET.get('case')
    try:
        selected_case_id = int(selected_case_id) if selected_case_id else None
    except (TypeError, ValueError):
        selected_case_id = None

    no_match_cases = list(
        case_records_qs.select_related('client', 'matter')
        .filter(status__in=['PENDING', 'IN_REVIEW'])
        .order_by('created_at')[:4]
    )
    matching_focus_case = None
    if selected_case_id:
        matching_focus_case = (
            case_records_qs.select_related('client', 'matter')
            .filter(pk=selected_case_id)
            .first()
        )
    stale_cases = list(
        case_records_qs.select_related('client', 'matter')
        .filter(status__in=['DRAFT', 'PENDING', 'IN_REVIEW', 'APPROVED'], updated_at__lt=stale_cutoff)
        .exclude(id__in=[case.id for case in no_match_cases])
        .order_by('updated_at')[:4]
    )
    pending_reviews = list(
        case_assessments_qs.filter(
            assessment_status__in=[
                CaseAssessment.AssessmentStatus.DRAFT,
                CaseAssessment.AssessmentStatus.UNDER_REVIEW,
                CaseAssessment.AssessmentStatus.NEEDS_INFO,
            ]
        ).order_by('created_at')[:4]
    )

    action_required = []
    action_seen = set()

    def add_action(item_key, payload):
        if item_key in action_seen or len(action_required) >= 8:
            return
        action_seen.add(item_key)
        action_required.append(payload)

    for case_record in no_match_cases:
        days_open = max((today - case_record.created_at.date()).days, 0)
        add_action(
            f'case-no-match-{case_record.id}',
            {
                'title': case_record.title,
                'meta': f'Geen match gekozen • {days_open} dagen open',
                'badge': 'Zonder match',
                'badge_class': 'badge-purple',
                'href': reverse('careon:case_detail', args=[case_record.pk]),
            },
        )

    for case_record in stale_cases:
        days_stale = max((today - case_record.updated_at.date()).days, 0)
        add_action(
            f'case-stale-{case_record.id}',
            {
                'title': case_record.title,
                'meta': f'Geen update sinds {days_stale} dagen',
                'badge': 'Stagnatie',
                'badge_class': 'badge-red',
                'href': reverse('careon:case_detail', args=[case_record.pk]),
            },
        )

    for review in pending_reviews:
        subject = review.intake.title
        days_waiting = max((today - review.created_at.date()).days, 0)
        add_action(
            f'review-{review.id}',
            {
                'title': subject,
                'meta': f'Wacht op beoordeling ({review.get_assessment_status_display()}) • {days_waiting} dagen open',
                'badge': 'Beoordeling',
                'badge_class': 'badge-yellow',
                'href': reverse('careon:assessment_update', args=[review.pk]),
            },
        )

    action_required_total = (
        cases_without_match
        + len(stale_cases)
        + len(pending_reviews)
        + risk_count
    )

    provider_capacity_qs = clients_qs.filter(status='ACTIVE').annotate(
        active_case_load=Count(
            'contracts',
            filter=Q(contracts__status__in=['ACTIVE', 'PENDING', 'IN_REVIEW', 'APPROVED']),
            distinct=True,
        ),
        active_configuration_load=Count('matters', filter=Q(matters__status='ACTIVE'), distinct=True),
    ).order_by('-active_case_load', '-active_configuration_load', 'name')

    provider_candidates = list(provider_capacity_qs.order_by('active_case_load', 'active_configuration_load', 'name')[:6])
    provider_ids = [provider.id for provider in provider_candidates]
    provider_profiles = ProviderProfile.objects.filter(client_id__in=provider_ids).prefetch_related('target_care_categories')
    profile_by_provider_id = {profile.client_id: profile for profile in provider_profiles}
    waittime_entries = list(
        TrustAccount.objects.filter(provider_id__in=provider_ids)
        .order_by('provider_id', '-updated_at')
    )
    latest_waittime_by_provider = {}
    for waittime in waittime_entries:
        if waittime.provider_id and waittime.provider_id not in latest_waittime_by_provider:
            latest_waittime_by_provider[waittime.provider_id] = waittime

    recommendation_cases = [matching_focus_case] if matching_focus_case else no_match_cases
    match_recommendations = []
    for case_record in recommendation_cases:
        if not case_record:
            continue
        configuration = case_record.configuration
        case_domain_ids = set()
        if configuration is not None:
            case_domain_ids = set(configuration.care_domains.values_list('id', flat=True))

        suggestions = []
        for provider in provider_candidates:
            if case_record.client_id and provider.id == case_record.client_id:
                continue

            provider_profile = profile_by_provider_id.get(provider.id)
            waittime = latest_waittime_by_provider.get(provider.id)

            wait_days = None
            if waittime is not None:
                wait_days = waittime.wait_days
            elif provider_profile is not None:
                wait_days = provider_profile.average_wait_days

            open_slots = None
            if waittime is not None:
                open_slots = waittime.open_slots
            elif provider_profile is not None:
                open_slots = provider_profile.current_capacity

            score = 0
            reasons = []

            if open_slots is not None:
                if open_slots > 2:
                    score += 35
                    reasons.append(f'{open_slots} vrije plekken beschikbaar')
                elif open_slots > 0:
                    score += 20
                    reasons.append(f'Beperkte directe ruimte ({open_slots} plek)')
                else:
                    reasons.append('Op dit moment geen vrije plekken')
            elif provider.active_case_load < low_capacity_threshold:
                score += 20
                reasons.append('Lage casusdruk op basis van huidige belasting')

            if wait_days is not None:
                if wait_days <= 14:
                    score += 25
                    reasons.append(f'Korte wachttijd ({wait_days} dagen)')
                elif wait_days <= 28:
                    score += 15
                    reasons.append(f'Matige wachttijd ({wait_days} dagen)')
                else:
                    score += 5
                    reasons.append(f'Lange wachttijd ({wait_days} dagen)')

            if case_domain_ids and provider_profile is not None:
                provider_domain_ids = set(provider_profile.target_care_categories.values_list('id', flat=True))
                if case_domain_ids.intersection(provider_domain_ids):
                    score += 20
                    reasons.append('Past bij de benodigde zorgdomeinen')

            if case_record.risk_level in ['HIGH', 'CRITICAL'] and provider_profile is not None:
                if provider_profile.handles_high_urgency or provider_profile.handles_crisis_urgency:
                    score += 10
                    reasons.append('Kan omgaan met hoge urgentie')

            if not reasons:
                reasons.append('Beschikbaar als alternatief voor snelle opvolging')

            load_note = 'Ruimte beschikbaar'
            if provider.active_case_load >= overload_threshold:
                load_note = 'Hoge belasting'
            elif provider.active_case_load >= low_capacity_threshold:
                load_note = 'Beperkte ruimte'
            capacity_label = f'{open_slots} plekken' if open_slots is not None else load_note
            suggestions.append(
                {
                    'id': provider.id,
                    'name': provider.name,
                    'note': load_note,
                    'match_score': min(score, 100),
                    'wait_days': wait_days,
                    'capacity': capacity_label,
                    'match_reason': reasons[0],
                }
            )
        suggestions = sorted(suggestions, key=lambda row: row['match_score'], reverse=True)[:3]
        if suggestions:
            match_recommendations.append({
                'case_record': case_record,
                'href': reverse('careon:case_detail', args=[case_record.pk]),
                'days_open': max((today - case_record.created_at.date()).days, 0),
                'action_href': f"{reverse('careon:case_detail', args=[case_record.pk])}?flow=matching",
                'suggestions': suggestions,
            })

    provider_capacity_signals = []
    provider_capacity_critical_count = 0
    providers_with_capacity = 0
    for provider in provider_capacity_qs[:8]:
        max_load = max(provider.active_case_load, provider.active_configuration_load)
        signal = None
        if max_load >= overload_threshold:
            signal = {
                'name': provider.name,
                'signal': 'Overbelasting',
                'detail': f'{max_load} lopende casussen of dossiers',
                'badge_class': 'badge-red',
            }
            provider_capacity_critical_count += 1
        elif max_load >= low_capacity_threshold:
            signal = {
                'name': provider.name,
                'signal': 'Lage capaciteit',
                'detail': f'Nog beperkt inzetbaar bij {max_load} actieve trajecten',
                'badge_class': 'badge-blue',
            }
        else:
            providers_with_capacity += 1

        if signal and len(provider_capacity_signals) < 5:
            provider_capacity_signals.append(signal)

    placement_cases = case_records_qs.filter(
        Q(approved_at__isnull=False)
        | Q(start_date__isnull=False)
    )

    placement_durations = []
    for case_record in placement_cases:
        placement_dates = []
        if case_record.approved_at:
            placement_dates.append(case_record.approved_at.date())
        if case_record.start_date:
            placement_dates.append(case_record.start_date)
        if placement_dates:
            placement_days = (min(placement_dates) - case_record.created_at.date()).days
            if placement_days >= 0:
                placement_durations.append(placement_days)
    avg_intake_to_placement_days = round(sum(placement_durations) / len(placement_durations), 1) if placement_durations else 0

    # Single decision entrypoint for dashboard: one primary action only.
    if total_cases == 0:
        primary_action = {
            'title': 'Nog geen actieve casussen',
            'cta_label': 'Nieuwe casus',
            'cta_href': reverse('careon:case_create'),
            'state': 'stable',
            'tone': 'neutral',
        }
    elif urgent_case_count > 0:
        primary_action = {
            'title': f'{urgent_case_count} casussen vereisen direct aandacht',
            'cta_label': 'Bekijk casussen',
            'cta_href': reverse('careon:case_list'),
            'state': 'attention',
            'tone': 'danger',
        }
    elif cases_without_match > 0:
        primary_action = {
            'title': f'{cases_without_match} casussen wachten op matching',
            'cta_label': 'Start matching',
            'cta_href': f"{reverse('careon:case_list')}?flow=matching",
            'state': 'attention',
            'tone': 'warning',
        }
    elif provider_capacity_critical_count > 0:
        primary_action = {
            'title': 'Capaciteit bijna vol',
            'cta_label': 'Bekijk capaciteit',
            'cta_href': reverse('careon:client_list'),
            'state': 'attention',
            'tone': 'warning',
        }
    else:
        primary_action = {
            'title': 'Alles onder controle',
            'cta_label': 'Bekijk overzicht',
            'cta_href': reverse('careon:case_list'),
            'state': 'stable',
            'tone': 'neutral',
        }

    flow_attention_candidates = {
        'intake': intake_phase_count,
        'beoordeling': assessment_phase_count,
        'matching': matching_phase_count,
        'indicatie': placement_phase_count,
        'opvolging': followup_phase_count,
    }
    flow_attention_stage = max(flow_attention_candidates, key=flow_attention_candidates.get)
    flow_attention_value = flow_attention_candidates[flow_attention_stage]
    if flow_attention_value == 0:
        flow_attention_stage = 'none'
        flow_attention_tone = 'neutral'
    elif flow_attention_stage in {'indicatie', 'opvolging'}:
        flow_attention_tone = 'active'
    else:
        flow_attention_tone = 'warning'

    flow_attention_labels = {
        'intake': 'Intake',
        'beoordeling': 'Beoordeling',
        'matching': 'Matching',
        'indicatie': 'Indicatie',
        'opvolging': 'Opvolging',
        'none': 'Geen knelpunt',
    }

    signal_attention_count = len(recent_signals)
    has_critical_signal = any(signal.risk_level == CareSignal.RiskLevel.CRITICAL for signal in recent_signals)
    signal_card_tone = 'danger' if has_critical_signal else ('warning' if signal_attention_count > 0 else 'neutral')

    flow_order = ['intake', 'beoordeling', 'matching', 'indicatie', 'opvolging']
    flow_counts = {
        'intake': intake_phase_count,
        'beoordeling': assessment_phase_count,
        'matching': matching_phase_count,
        'indicatie': placement_phase_count,
        'opvolging': followup_phase_count,
    }
    flow_states = {step: 'future' for step in flow_order}

    first_active_step = next((step for step in flow_order if flow_counts[step] > 0), None)
    if first_active_step:
        active_idx = flow_order.index(first_active_step)
        for idx, step in enumerate(flow_order):
            if idx < active_idx and flow_counts[step] > 0:
                flow_states[step] = 'completed'
        flow_states[first_active_step] = 'active'

    warning_step = None
    warning_count = 0
    for step in ['intake', 'beoordeling', 'matching', 'indicatie', 'opvolging']:
        if flow_counts[step] > warning_count:
            warning_step = step
            warning_count = flow_counts[step]

    flow_danger_step = None
    if warning_step and warning_count > 0 and flow_states.get(warning_step) != 'active':
        flow_states[warning_step] = 'warning'
        if warning_count >= 5:
            flow_danger_step = warning_step

    context = {
        'total_cases': total_cases,
        'active_cases': active_cases,
        'intake_cases': intake_cases,
        'cases_without_match': cases_without_match,
        'completed_cases': completed_cases,
        'total_clients': total_clients,
        'active_clients': active_clients,
        'active_configurations': active_configurations,
        'total_configurations': total_configurations,
        'pending_tasks': pending_tasks,
        'urgent_task_count': urgent_task_count,
        'active_workflows': active_workflows,
        'risk_count': risk_count,
        'recent_signals': recent_signals,
        'followup_tasks': followup_tasks,
        'overdue_deadlines': overdue_deadlines,
        'upcoming_deadline_count': upcoming_deadline_count,
        'total_documents': total_documents,
        'unread_notifications': unread_notifications,
        'recent_audit': recent_audit,
        'case_status_data': case_status_data_values,
        'flow_total': max(total_cases, 1),
        'open_cases': active_cases,
        'urgent_cases': urgent_case_count,
        'providers_count': total_clients,
        'placements_this_week': active_workflows,
        'cases_without_match': cases_without_match,
        'avg_wait_days': avg_intake_to_placement_days,
        'capacity_available': providers_with_capacity,
        'regional_bottlenecks': provider_capacity_critical_count,
        'urgent_case_count': urgent_case_count,
        'cases_without_match_count': cases_without_match,
        'case_phase_count': case_phase_count,
        'assessment_phase_count': assessment_phase_count,
        'matching_phase_count': matching_phase_count,
        'placement_phase_count': placement_phase_count,
        'followup_phase_count': followup_phase_count,
        'intake_phase_count': intake_phase_count,
        'avg_intake_to_placement_days': avg_intake_to_placement_days,
        'action_required': action_required,
        'action_required_total': action_required_total,
        'match_recommendations': match_recommendations,
        'matching_focus_case': matching_focus_case,
        'provider_capacity_signals': provider_capacity_signals,
        'provider_capacity_critical_count': provider_capacity_critical_count,
        'providers_with_capacity': providers_with_capacity,
        'primary_action': primary_action,
        'has_dashboard_attention': primary_action['state'] == 'attention',
        'flow_attention_stage': flow_attention_stage,
        'flow_attention_value': flow_attention_value,
        'flow_attention_label': flow_attention_labels[flow_attention_stage],
        'flow_attention_tone': flow_attention_tone,
        'signal_attention_count': signal_attention_count,
        'signal_card_tone': signal_card_tone,
        'flow_counts': flow_counts,
        'flow_states': flow_states,
        'flow_danger_step': flow_danger_step,
        'has_cases': total_cases > 0,
        'has_providers': total_clients > 0,
        'today': today,
        'dashboard_updated_at': now,
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
        if q:
            qs = qs.filter(
                Q(region_name__icontains=q)
                | Q(region_code__icontains=q)
            ).distinct()
        if status:
            qs = qs.filter(status=status)
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

        # Filter by urgency
        urgency = self.request.GET.get('urgency')
        if urgency:
            qs = qs.filter(urgency=urgency)

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

        flow_stage_map = {
            CaseIntakeProcess.ProcessStatus.INTAKE: 'aanvraag',
            CaseIntakeProcess.ProcessStatus.ASSESSMENT: 'beoordeling',
            CaseIntakeProcess.ProcessStatus.MATCHING: 'matching',
            CaseIntakeProcess.ProcessStatus.DECISION: 'intake_aanbieder',
            CaseIntakeProcess.ProcessStatus.COMPLETED: 'plaatsing',
            CaseIntakeProcess.ProcessStatus.ON_HOLD: 'aanvraag',
        }
        active_flow_stage = flow_stage_map.get(intake.status, 'aanvraag')
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

        def _form_match(profile, current_intake):
            return {
                CaseIntakeProcess.CareForm.OUTPATIENT: profile.offers_outpatient,
                CaseIntakeProcess.CareForm.DAY_TREATMENT: profile.offers_day_treatment,
                CaseIntakeProcess.CareForm.RESIDENTIAL: profile.offers_residential,
                CaseIntakeProcess.CareForm.CRISIS: profile.offers_crisis,
            }.get(current_intake.preferred_care_form, False)

        def _urgency_match(profile, current_intake):
            return {
                CaseIntakeProcess.Urgency.LOW: profile.handles_low_urgency,
                CaseIntakeProcess.Urgency.MEDIUM: profile.handles_medium_urgency,
                CaseIntakeProcess.Urgency.HIGH: profile.handles_high_urgency,
                CaseIntakeProcess.Urgency.CRISIS: profile.handles_crisis_urgency,
            }.get(current_intake.urgency, False)

        matching_preview_candidates = []
        if ready_for_matching:
            provider_profiles = (
                ProviderProfile.objects.filter(client__organization=self.get_organization(), client__status='ACTIVE')
                .select_related('client')
                .prefetch_related('target_care_categories')
            )

            for profile in provider_profiles:
                score = 0
                reasons = []

                category_match = bool(
                    intake.care_category_main_id
                    and profile.target_care_categories.filter(id=intake.care_category_main_id).exists()
                )
                if category_match:
                    score += 40
                    reasons.append('Categorie match')

                urgency_match = _urgency_match(profile, intake)
                if urgency_match:
                    score += 20
                    reasons.append('Urgentie match')

                care_form_match = _form_match(profile, intake)
                if care_form_match:
                    score += 20
                    reasons.append('Zorgvorm match')

                free_slots = max(profile.max_capacity - profile.current_capacity, 0)
                if free_slots > 0:
                    score += min(free_slots * 4, 20)
                    reasons.append(f'{free_slots} vrije plekken')

                if profile.average_wait_days <= 14:
                    score += 10
                    reasons.append('Korte wachttijd')
                elif profile.average_wait_days <= 28:
                    score += 5
                    reasons.append('Acceptabele wachttijd')

                matching_preview_candidates.append(
                    {
                        'provider_name': profile.client.name,
                        'fit_score': min(score, 100),
                        'capacity': f'{free_slots} plekken beschikbaar' if free_slots > 0 else 'Beperkte capaciteit',
                        'reason': reasons[0] if reasons else 'Handmatige afweging nodig',
                        'cta_href': matching_href,
                        'cta_label': 'Open matching',
                    }
                )

            matching_preview_candidates = sorted(
                matching_preview_candidates,
                key=lambda row: row['fit_score'],
                reverse=True,
            )[:3]

        selected_tab = (self.request.GET.get('tab') or 'tijdlijn').lower()
        tab_options = {'tijdlijn', 'documenten', 'taken', 'signalen', 'plaatsing'}
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
            'open_tasks': open_tasks,
            'open_tasks_count': open_tasks.count(),
            'open_signals': open_signals,
            'open_signals_count': open_signals.count(),
            'documents': documents,
            'documents_count': documents.count(),
            'next_action': next_action,
            'can_create_case_document': can_create_case_document,
            'can_create_case_task': can_edit_case,
            'can_create_case_signal': can_edit_case,
            'case_document_href': case_document_href,
            'case_document_action_label': case_document_action_label,
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
        for signal in ctx['signals']:
            linked_case = signal.case_record or (signal.intake.case_record if signal.intake else None)
            if linked_case is None or can_access_case_action(self.request.user, linked_case, CaseAction.EDIT):
                editable_signal_ids.add(signal.pk)
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
        linked_case = self.object.case_record or (self.object.intake.case_record if self.object.intake else None)
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
        linked_case = signal.case_record or (signal.intake.case_record if signal.intake else None)
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
        ctx['can_edit_placement'] = (linked_case is None) or can_access_case_action(
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
        linked_case = placement.intake.case_record if placement.intake else None
        if linked_case and not can_access_case_action(request.user, linked_case, CaseAction.EDIT):
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
        return reverse('careon:case_detail', kwargs={'pk': self._load_intake().pk})


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
        return reverse('careon:case_detail', kwargs={'pk': self._load_intake().pk})


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
        if intake.contract_id:
            initial['contract'] = intake.case_record
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        intake = self._load_intake()
        ctx['intake'] = intake
        ctx['cancel_href'] = reverse('careon:case_detail', kwargs={'pk': intake.pk})
        return ctx

    def form_valid(self, form):
        intake = self._load_intake()
        form.instance.contract = intake.case_record
        response = super().form_valid(form)
        messages.success(self.request, f'Document toegevoegd aan casus "{intake.title}".')
        return response

    def get_success_url(self):
        return reverse('careon:case_detail', kwargs={'pk': self._load_intake().pk})
