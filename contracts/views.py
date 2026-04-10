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
from datetime import timedelta, date
from decimal import Decimal
import csv
import logging

from .forms import (
    BudgetForm, LegalTaskForm, BudgetExpenseForm,
    ClientForm, CareConfigurationForm, DocumentForm,
    DeadlineForm, UserProfileForm,
    RegistrationForm,
    OrganizationInvitationForm,
    MunicipalityConfigurationForm, RegionalConfigurationForm,
    CaseAssessmentForm, DueDiligenceProcessForm,
)
from .models import (
    Organization, OrganizationMembership, OrganizationInvitation,
    CareCase, PlacementRequest, ProviderResponseRequest, LegalTask, RiskLog,
    Workflow,
    CaseIntakeProcess, Budget, BudgetExpense,
    Client, CareConfiguration, Document, TrustAccount, ProviderProfile,
    Deadline, AuditLog, Notification, UserProfile, CaseAssessment,
    DSARRequest, RetentionPolicy, ApprovalRequest,
    MunicipalityConfiguration, RegionalConfiguration,
    DueDiligenceProcess,
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


def _resolve_deadline_contract(deadline):
    if getattr(deadline, 'contract_id', None):
        return deadline.contract
    process = getattr(deadline, 'due_diligence_process', None)
    if process and getattr(process, 'contract_id', None):
        return process.contract
    return None


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
            'assigned_to': process.lead_attorney,
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
    if current_task.assigned_to_id != process.lead_attorney_id:
        current_task.assigned_to = process.lead_attorney
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

    auto_tasks = Deadline.objects.filter(contract=case, auto_generated=True)

    if not phase_task:
        auto_tasks.filter(is_completed=False).update(
            is_completed=True,
            completed_at=timezone.now(),
            completed_by=user,
        )
        return

    due_date = _resolve_task_due_date(fallback_days=1)
    current_task, created = Deadline.objects.get_or_create(
        contract=case,
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
    for process in CaseIntakeProcess.objects.filter(organization=org).select_related('lead_attorney'):
        sync_intake_auto_tasks(process, user=user)
    for case in CareCase.objects.filter(organization=org):
        sync_case_phase_auto_tasks(case, user=user)


# Backward-compatible aliases for older call sites.
AUTO_DUE_DILIGENCE_TASKS = AUTO_INTAKE_TASKS
sync_due_diligence_auto_tasks = sync_intake_auto_tasks


PHASE_TO_PROCESS_STATUS = {
    CareCase.CasePhase.INTAKE: CaseIntakeProcess.ProcessStatus.INTAKE,
    CareCase.CasePhase.BEOORDELING: CaseIntakeProcess.ProcessStatus.ASSESSMENT,
    CareCase.CasePhase.MATCHING: CaseIntakeProcess.ProcessStatus.MATCHING,
    CareCase.CasePhase.PLAATSING: CaseIntakeProcess.ProcessStatus.DECISION,
    CareCase.CasePhase.ACTIEF: CaseIntakeProcess.ProcessStatus.COMPLETED,
    CareCase.CasePhase.AFGEROND: CaseIntakeProcess.ProcessStatus.COMPLETED,
}


def get_case_section_url(case, section=None):
    url = reverse('contracts:case_detail', kwargs={'pk': case.pk})
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
        'lead_attorney': case.created_by if case.created_by_id else None,
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
            elif field_name in {'lead_attorney', 'start_date', 'target_completion_date'}:
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

    sync_due_diligence_auto_tasks(process, user=user)
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
        ctx['matters'] = configurations
        ctx['case_records'] = case_records
        ctx['contracts'] = case_records
        ctx['documents'] = self.object.documents.all()[:10]
        return ctx


class ClientCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'contracts/client_form.html'
    success_url = reverse_lazy('contracts:client_list')

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
    success_url = reverse_lazy('contracts:client_list')

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

class CareConfigurationListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = CareConfiguration
    template_name = 'contracts/matter_list.html'
    context_object_name = 'configurations'
    paginate_by = 25

    SCOPE_QUERY_ALIASES = {
        'gemeente': CareConfiguration.Scope.GEMEENTE,
        'gemeenten': CareConfiguration.Scope.GEMEENTE,
        CareConfiguration.Scope.GEMEENTE: CareConfiguration.Scope.GEMEENTE,
        'regio': CareConfiguration.Scope.REGIO,
        'regios': CareConfiguration.Scope.REGIO,
        "regio's": CareConfiguration.Scope.REGIO,
        CareConfiguration.Scope.REGIO: CareConfiguration.Scope.REGIO,
    }

    def _get_scope_filter(self):
        raw_scope = (self.request.GET.get('scope') or '').strip()
        if not raw_scope:
            return ''
        return self.SCOPE_QUERY_ALIASES.get(raw_scope, self.SCOPE_QUERY_ALIASES.get(raw_scope.upper(), ''))

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            CareConfiguration.objects.select_related('client', 'responsible_care_coordinator').prefetch_related('care_domains', 'linked_providers'),
            org,
        )
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        care_domain_id = self.request.GET.get('care_domain')
        scope_filter = self._get_scope_filter()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(configuration_id__icontains=q)
                | Q(client__name__icontains=q)
                | Q(linked_providers__name__icontains=q)
            ).distinct()
        if status:
            qs = qs.filter(status=status)
        if care_domain_id:
            qs = qs.filter(care_domains__id=care_domain_id)
        if scope_filter:
            qs = qs.filter(scope=scope_filter)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['matters'] = ctx.get('configurations', [])
        org = self.get_organization()
        current_scope = self._get_scope_filter()
        tenant_configurations = scope_queryset_for_organization(CareConfiguration.objects.all(), org)
        if current_scope:
            tenant_configurations = tenant_configurations.filter(scope=current_scope)
        configuration_stats = tenant_configurations.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
        )
        configuration_rows = []
        for configuration in ctx['configurations']:
            configuration_rows.append({
                'obj': configuration,
                'provider_total': configuration.provider_total,
                'domains': list(configuration.care_domains.values_list('name', flat=True)),
                'avg_wait_days': configuration.average_wait_days,
                'case_total': configuration.case_total,
                'capacity_status': configuration.capacity_status,
            })

        ctx['total_configurations'] = configuration_stats['total']
        ctx['active_configurations'] = configuration_stats['active']
        ctx['total_matters'] = ctx['total_configurations']
        ctx['active_matters'] = ctx['active_configurations']
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['current_scope'] = current_scope
        ctx.update(get_configuration_scope_content(current_scope))
        ctx['configuration_rows'] = configuration_rows
        ctx['matter_rows'] = configuration_rows
        return ctx


class CareConfigurationDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = CareConfiguration
    template_name = 'contracts/matter_detail.html'
    context_object_name = 'configuration'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(CareConfiguration.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['matter'] = self.object
        case_records = self.object.contracts.all()
        ctx['case_records'] = case_records
        ctx['contracts'] = case_records
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
    template_name = 'contracts/matter_form.html'

    def get_initial(self):
        initial = super().get_initial()
        raw_scope = (self.request.GET.get('scope') or '').strip()
        normalized_scope = CareConfigurationListView.SCOPE_QUERY_ALIASES.get(raw_scope, CareConfigurationListView.SCOPE_QUERY_ALIASES.get(raw_scope.upper()))
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
        ctx['cancel_url'] = f"{reverse('contracts:configuration_list')}?scope={scope}"
        ctx['is_edit'] = False
        selected_provider_ids = ctx['form'].initial.get('linked_providers') or []
        ctx['prefilled_provider'] = ctx['form'].fields['linked_providers'].queryset.filter(pk__in=selected_provider_ids).first()
        return ctx

    def get_success_url(self):
        return reverse('contracts:configuration_detail', kwargs={'pk': self.object.pk})

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
    template_name = 'contracts/matter_form.html'

    def get_success_url(self):
        return reverse('contracts:configuration_detail', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(CareConfiguration.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_configuration_scope_content(self.object.scope))
        ctx['cancel_url'] = f"{reverse('contracts:configuration_list')}?scope={self.object.scope}"
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


get_matter_scope_content = get_configuration_scope_content
MatterListView = CareConfigurationListView
MatterDetailView = CareConfigurationDetailView
MatterCreateView = CareConfigurationCreateView
MatterUpdateView = CareConfigurationUpdateView


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
        return ctx


class DocumentCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = 'contracts/document_form.html'
    success_url = reverse_lazy('contracts:document_list')

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
    success_url = reverse_lazy('contracts:document_list')

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
        qs = Deadline.objects.select_related('due_diligence_process', 'assigned_to', 'contract').for_organization(org)
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

            if deadline.due_diligence_process:
                if deadline.due_diligence_process.contract_id:
                    open_href = get_contract_section_url(deadline.due_diligence_process.contract, 'intake-section')
                else:
                    open_href = reverse('contracts:intake_detail', kwargs={'pk': deadline.due_diligence_process.pk})
                case_title = deadline.due_diligence_process.title
            elif deadline.contract:
                open_href = reverse('contracts:case_detail', kwargs={'pk': deadline.contract.pk})
                case_title = deadline.contract.title
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
            })

        ctx['task_rows'] = task_rows
        return ctx


class DeadlineCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('contracts:deadline_list')

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
    success_url = reverse_lazy('contracts:deadline_list')

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
        linked_contract = _resolve_deadline_contract(deadline)
        if linked_contract and not can_access_case_action(request.user, linked_contract, CaseAction.EDIT):
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
    linked_contract = _resolve_deadline_contract(deadline)
    if linked_contract and not can_access_case_action(request.user, linked_contract, CaseAction.EDIT):
        return HttpResponseForbidden('Je hebt geen rechten om opvolgtaken van deze casus af te ronden.')
    deadline.is_completed = True
    deadline.completed_at = timezone.now()
    deadline.completed_by = request.user
    deadline.save()
    log_action(request.user, 'UPDATE', 'OpvolgingTaak', deadline.id, str(deadline), request=request)
    messages.success(request, f'Taak "{deadline.title}" gemarkeerd als afgerond.')
    return redirect('contracts:deadline_list')


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
    return redirect('contracts:notification_list')


@login_required
@require_POST
def mark_all_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect('contracts:notification_list')


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
        reverse('contracts:accept_organization_invite', kwargs={'token': invitation.token})
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
                messages.info(request, f'Er bestaat al een actieve uitnodiging voor {email}: {invite_url}')
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
                messages.success(request, f'Uitnodiging aangemaakt en verzonden naar {email}. Link: {invite_url}')
            except Exception:
                messages.warning(request, f'Uitnodiging aangemaakt voor {email}, maar e-mailbezorging mislukte. Deel deze link handmatig: {invite_url}')
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
    return redirect('contracts:organization_team')


@login_required
@require_POST
def resend_organization_invite(request, invite_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Onvoldoende rechten.')

    invitation = get_object_or_404(OrganizationInvitation, id=invite_id, organization=organization)
    if invitation.status != OrganizationInvitation.Status.PENDING:
        messages.info(request, 'Alleen openstaande uitnodigingen kunnen opnieuw worden verzonden.')
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
        messages.success(request, f'Uitnodiging opnieuw verzonden naar {new_invitation.email}.')
    except Exception:
        messages.warning(request, f'Nieuwe uitnodiging aangemaakt, maar e-mailbezorging mislukte. Deel deze link handmatig: {invite_url}')
    return redirect('contracts:organization_team')


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
        return redirect('contracts:organization_team')

    actor_is_owner = is_organization_owner(request.user, organization)
    if requested_role == OrganizationMembership.Role.OWNER and not actor_is_owner:
        messages.error(request, 'Alleen organisatie-eigenaren kunnen de rol Eigenaar toekennen.')
        return redirect('contracts:organization_team')

    if membership.user_id == request.user.id and membership.role == OrganizationMembership.Role.OWNER and requested_role != OrganizationMembership.Role.OWNER:
        owner_count = OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
        ).count()
        if owner_count <= 1:
            messages.error(request, 'Er moet minimaal een actieve eigenaar in de organisatie overblijven.')
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
    messages.success(request, f'Rol bijgewerkt voor {membership.user.email or membership.user.username}.')
    return redirect('contracts:organization_team')


@login_required
@require_POST
def deactivate_organization_member(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Onvoldoende rechten.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization, is_active=True)
    if membership.user_id == request.user.id:
        messages.error(request, 'Je kunt je eigen lidmaatschap niet deactiveren.')
        return redirect('contracts:organization_team')

    if membership.role == OrganizationMembership.Role.OWNER:
        owner_count = OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
        ).count()
        if owner_count <= 1:
            messages.error(request, 'Er moet minimaal een actieve eigenaar in de organisatie overblijven.')
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
    messages.success(request, f'Lidmaatschap gedeactiveerd voor {membership.user.email or membership.user.username}.')
    return redirect('contracts:organization_team')


@login_required
@require_POST
def reactivate_organization_member(request, membership_id):
    organization = getattr(request, 'organization', None) or get_user_organization(request.user)
    if not organization or not can_manage_organization(request.user, organization):
        return HttpResponseForbidden('Onvoldoende rechten.')

    membership = get_object_or_404(OrganizationMembership, id=membership_id, organization=organization)
    if membership.is_active:
        messages.info(request, 'Dit lidmaatschap is al actief.')
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
    messages.success(request, f'Lidmaatschap opnieuw geactiveerd voor {membership.user.email or membership.user.username}.')
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
        risks_qs = RiskLog.objects.for_organization(org)
        provider_profiles_qs = ProviderProfile.objects.filter(client__organization=org)
        waittime_qs = TrustAccount.objects.filter(provider__organization=org).select_related('provider')
    else:
        cases_qs = CaseIntakeProcess.objects.none()
        indications_qs = PlacementRequest.objects.none()
        risks_qs = RiskLog.objects.none()
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
        .select_related('lead_attorney', 'care_category_main')
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
        .select_related('lead_attorney', 'care_category_main')
        .order_by('start_date')
    )
    stagnation_count = stagnated_cases_qs.count()

    # KPI 4: Escalaties
    escalation_qs = (
        risks_qs
        .filter(status__in=[RiskLog.SignalStatus.OPEN, RiskLog.SignalStatus.IN_PROGRESS])
        .filter(Q(signal_type=RiskLog.SignalType.ESCALATION) | Q(risk_level__in=[RiskLog.RiskLevel.HIGH, RiskLog.RiskLevel.CRITICAL]))
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
                'href': reverse('contracts:intake_detail', kwargs={'pk': case.pk}),
            })
    if attention_filter in ['all', 'stagnation']:
        for case in stagnated_cases_qs[:6]:
            days_open = (today - case.start_date).days
            attention_rows.append({
                'kind': 'stagnation',
                'kind_label': 'Stagnatie',
                'title': case.title,
                'meta': f"{days_open} dagen in traject · {case.get_status_display()}",
                'href': reverse('contracts:intake_detail', kwargs={'pk': case.pk}),
            })
    if attention_filter in ['all', 'capacity']:
        for wt in no_capacity_qs[:6]:
            provider_name = wt.provider.name if wt.provider else 'Onbekende aanbieder'
            attention_rows.append({
                'kind': 'capacity',
                'kind_label': 'Geen capaciteit',
                'title': provider_name,
                'meta': f"{wt.region} · wachtlijst {wt.waiting_list_size} · wachttijd {wt.wait_days} dagen",
                'href': reverse('contracts:waittime_detail', kwargs={'pk': wt.pk}),
            })
    if attention_filter in ['all', 'escalation']:
        for signal in escalation_qs[:6]:
            case_title = signal.due_diligence_process.title if signal.due_diligence_process else 'Niet gekoppelde casus'
            attention_rows.append({
                'kind': 'escalation',
                'kind_label': 'Escalatie',
                'title': case_title,
                'meta': f"{signal.get_signal_type_display()} · {signal.get_risk_level_display()} · {signal.get_status_display()}",
                'href': reverse('contracts:risk_log_update', kwargs={'pk': signal.pk}),
            })

    # Doorstroomtrend start aanvraag → casus → beoordeling → matching → intake → plaatsing
    flow_counts = {
        'start_request': case_records_qs.filter(status=CareCase.Status.DRAFT).count(),
        'case_profile': case_records_qs.filter(status=CareCase.Status.IN_REVIEW).count(),
        'assessment': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.ASSESSMENT).count(),
        'matching': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.MATCHING).count(),
        'intake': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.INTAKE).count(),
        'placement': cases_qs.filter(status=CaseIntakeProcess.ProcessStatus.DECISION).count(),
    }
    max_flow = max(max(flow_counts.values()), 1)
    flow_stages = [
        {'key': 'start_request', 'label': 'Start aanvraag', 'count': flow_counts['start_request'], 'width': int((flow_counts['start_request'] / max_flow) * 100)},
        {'key': 'case_profile', 'label': 'Casus (persoonsbeeld, diagnoses, indicatie)', 'count': flow_counts['case_profile'], 'width': int((flow_counts['case_profile'] / max_flow) * 100)},
        {'key': 'assessment', 'label': 'Beoordeling', 'count': flow_counts['assessment'], 'width': int((flow_counts['assessment'] / max_flow) * 100)},
        {'key': 'matching', 'label': 'Matching', 'count': flow_counts['matching'], 'width': int((flow_counts['matching'] / max_flow) * 100)},
        {'key': 'intake', 'label': 'Intake', 'count': flow_counts['intake'], 'width': int((flow_counts['intake'] / max_flow) * 100)},
        {'key': 'placement', 'label': 'Plaatsing', 'count': flow_counts['placement'], 'width': int((flow_counts['placement'] / max_flow) * 100)},
    ]
    flow_drops = [
        ('Start aanvraag → Casus', max(flow_counts['start_request'] - flow_counts['case_profile'], 0)),
        ('Casus → Beoordeling', max(flow_counts['case_profile'] - flow_counts['assessment'], 0)),
        ('Beoordeling → Matching', max(flow_counts['assessment'] - flow_counts['matching'], 0)),
        ('Matching → Intake', max(flow_counts['matching'] - flow_counts['intake'], 0)),
        ('Intake → Plaatsing', max(flow_counts['intake'] - flow_counts['placement'], 0)),
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
            'href': reverse('contracts:matching_dashboard'),
            'action': 'Open matchingoverzicht',
        })
    if no_capacity_qs.count() > 0:
        recommendations.append({
            'title': 'Optimaliseer capaciteit bij aanbieders zonder vrije plekken',
            'detail': f'{no_capacity_qs.count()} aanbieders hebben geen open plekken.',
            'href': reverse('contracts:waittime_list'),
            'action': 'Bekijk wachttijden',
        })
    if float(avg_wait_days) > 28:
        recommendations.append({
            'title': 'Wachttijdwaarschuwing: gemiddelde boven 28 dagen',
            'detail': f'Huidig gemiddelde is {avg_wait_days:.1f} dagen.',
            'href': reverse('contracts:client_list'),
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
        'total_matters': total_configurations,
        'active_matters': total_active_configurations,
        'monthly_hours': 0,
        'yearly_revenue': 0,
        'outstanding': 0,
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

class LegalTaskKanbanView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = LegalTask
    template_name = 'contracts/task_board.html'
    context_object_name = 'legal_tasks'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return LegalTask.objects.none()
        return LegalTask.objects.select_related('contract', 'matter', 'assigned_to').filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        ).order_by('-updated_at', '-created_at')


class LegalTaskCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/task_form.html'
    success_url = reverse_lazy('contracts:task_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['contract'].queryset = scope_queryset_for_organization(CareCase.objects.all(), org)
            form.fields['matter'].queryset = scope_queryset_for_organization(CareConfiguration.objects.all(), org)
        else:
            form.fields['contract'].queryset = CareCase.objects.none()
            form.fields['matter'].queryset = CareConfiguration.objects.none()
        return form

    def form_valid(self, form):
        org = get_user_organization(self.request.user)
        if form.instance.contract and not can_access_case_action(self.request.user, form.instance.contract, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om taken voor deze casus aan te maken.')
        if form.instance.matter and org and form.instance.matter.organization_id != org.id:
            return HttpResponseForbidden('Je hebt geen rechten om taken voor deze configuratie aan te maken.')
        return super().form_valid(form)


class LegalTaskUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/task_form.html'
    success_url = reverse_lazy('contracts:task_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return LegalTask.objects.none()
        return LegalTask.objects.filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        )

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['contract'].queryset = scope_queryset_for_organization(CareCase.objects.all(), org)
            form.fields['matter'].queryset = scope_queryset_for_organization(CareConfiguration.objects.all(), org)
        else:
            form.fields['contract'].queryset = CareCase.objects.none()
            form.fields['matter'].queryset = CareConfiguration.objects.none()
        return form

    def dispatch(self, request, *args, **kwargs):
        task = self.get_object()
        if task.contract and not can_access_case_action(request.user, task.contract, CaseAction.EDIT):
            return HttpResponseForbidden('Je hebt geen rechten om taken voor deze casus te bewerken.')
        org = get_user_organization(request.user)
        if task.matter and org and task.matter.organization_id != org.id:
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
            item.title.strip().lower(): f'Gebaseerd op {get_matter_scope_content(item.scope)["entity_label_lower"]}'
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
    success_url = reverse_lazy('contracts:budget_list')

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
    success_url = reverse_lazy('contracts:budget_list')

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

        org_name = f"{self.object.get_full_name().strip() or self.object.username}'s Firm"
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
        return reverse_lazy('contracts:budget_detail', kwargs={'pk': self.kwargs['budget_pk']})


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
    target = reverse('contracts:case_list')
    if step:
        target = f'{target}?flow={step}'
    return redirect(target)


@login_required
def case_flow_create_redirect(request, step=None):
    """Route legacy create entry points to case creation as single start object."""
    target = reverse('contracts:case_create')
    if step:
        target = f'{target}?flow={step}'
    return redirect(target)


@login_required
def case_flow_detail_redirect(request, pk):
    """Route legacy intake detail URLs to the canonical case detail page."""
    return redirect('contracts:case_detail', pk=pk)


@login_required
def case_flow_update_redirect(request, pk):
    """Route legacy intake edit URLs to the canonical case edit page."""
    return redirect('contracts:case_update', pk=pk)


@login_required
def legacy_configuration_list_redirect(request):
    """Route old configuration list URL to municipality/regional entry points."""
    scope = (request.GET.get('scope') or '').strip().upper()
    if scope == CareConfiguration.Scope.REGIO:
        return redirect('contracts:regional_list')
    return redirect('contracts:municipality_list')


@login_required
def legacy_configuration_create_redirect(request):
    """Route old configuration create URL to municipality/regional create pages."""
    scope = (request.GET.get('scope') or '').strip().upper()
    if scope == CareConfiguration.Scope.REGIO:
        return redirect('contracts:regional_create')
    return redirect('contracts:municipality_create')


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

    if request.method == 'POST' and request.POST.get('action') == 'assign':
        assessment = get_object_or_404(approved_assessments_qs, pk=request.POST.get('assessment_id'))
        provider = get_object_or_404(
            Client.objects.filter(organization=org, status='ACTIVE'),
            pk=request.POST.get('provider_id'),
        )

        placement, created = PlacementRequest.objects.get_or_create(
            due_diligence_process=assessment.due_diligence_process,
            defaults={
                'status': PlacementRequest.Status.IN_REVIEW,
                'proposed_provider': provider,
                'selected_provider': provider,
                'care_form': assessment.due_diligence_process.preferred_care_form,
                'decision_notes': 'Automatisch toegewezen vanuit matching-dashboard.',
            },
        )
        if not created:
            placement.proposed_provider = provider
            placement.selected_provider = provider
            if not placement.care_form:
                placement.care_form = assessment.due_diligence_process.preferred_care_form
            placement.status = PlacementRequest.Status.IN_REVIEW
            placement.save(update_fields=['proposed_provider', 'selected_provider', 'care_form', 'status', 'updated_at'])

        if assessment.due_diligence_process.status != DueDiligenceProcess.ProcessStatus.MATCHING:
            assessment.due_diligence_process.status = DueDiligenceProcess.ProcessStatus.MATCHING
            assessment.due_diligence_process.save(update_fields=['status', 'updated_at'])

        messages.success(
            request,
            f'Aanbieder {provider.name} gekoppeld aan casus "{assessment.due_diligence_process.title}".',
        )
        return redirect('contracts:matching_dashboard')

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
            DueDiligenceProcess.CareForm.OUTPATIENT: profile.offers_outpatient,
            DueDiligenceProcess.CareForm.DAY_TREATMENT: profile.offers_day_treatment,
            DueDiligenceProcess.CareForm.RESIDENTIAL: profile.offers_residential,
            DueDiligenceProcess.CareForm.CRISIS: profile.offers_crisis,
        }.get(intake.preferred_care_form, False)

    def _urgency_match(profile, intake):
        return {
            DueDiligenceProcess.Urgency.LOW: profile.handles_low_urgency,
            DueDiligenceProcess.Urgency.MEDIUM: profile.handles_medium_urgency,
            DueDiligenceProcess.Urgency.HIGH: profile.handles_high_urgency,
            DueDiligenceProcess.Urgency.CRISIS: profile.handles_crisis_urgency,
        }.get(intake.urgency, False)

    rows = []
    for assessment in assessments:
        intake = assessment.due_diligence_process
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
        rows.append(
            {
                'assessment': assessment,
                'intake': intake,
                'assigned_provider': assigned_by_intake.get(intake.id).selected_provider if intake.id in assigned_by_intake else None,
                'suggestions': suggestions[:5],
            }
        )

    context = {
        'rows': rows,
        'total_ready': len(rows),
        'assigned_count': len(assigned_by_intake),
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

    tasks_qs = LegalTask.objects.for_organization(org) if org else LegalTask.objects.none()
    risks_qs = RiskLog.objects.for_organization(org) if org else RiskLog.objects.none()
    deadlines_qs = Deadline.objects.for_organization(org)
    approvals_qs = (
        ApprovalRequest.objects.filter(contract__organization=org).select_related('contract', 'assigned_to')
        if org else ApprovalRequest.objects.none()
    )
    signatures_qs = (
        ProviderResponseRequest.objects.filter(contract__organization=org).select_related('contract')
        if org else ProviderResponseRequest.objects.none()
    )
    dsars_qs = (
        DSARRequest.objects.filter(client__organization=org).select_related('client', 'assigned_to')
        if org else DSARRequest.objects.none()
    )
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

    approval_stats = approvals_qs.aggregate(
        pending=Count('id', filter=Q(status='PENDING')),
    )
    signature_stats = signatures_qs.aggregate(
        pending=Count('id', filter=Q(status__in=['PENDING', 'SENT', 'VIEWED'])),
    )
    dsar_stats = dsars_qs.aggregate(
        open=Count('id', filter=Q(status__in=['RECEIVED', 'IN_PROGRESS'])),
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
        {'label': 'Start aanvraag', 'count': status_counts_dict.get(CareCase.Status.DRAFT, 0), 'tone': 'pf-draft'},
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

    intake_phase_count = intake_cases + (intake_stats['in_progress'] or 0)
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

    pending_approvals = approval_stats['pending'] or 0
    pending_signatures = signature_stats['pending'] or 0
    open_dsars = dsar_stats['open'] or 0

    stale_cutoff = now - timedelta(days=stagnation_days)
    provider_response_cutoff = now - timedelta(days=provider_response_days)

    urgent_case_ids = set(
        contract_id for contract_id in case_records_qs.filter(risk_level__in=['HIGH', 'CRITICAL']).values_list('id', flat=True)
        if contract_id
    )
    urgent_case_ids.update(
        contract_id for contract_id in deadlines_qs.filter(
            is_completed=False,
            due_date__lt=today,
            contract__isnull=False,
        ).values_list('contract_id', flat=True)
        if contract_id
    )
    urgent_case_ids.update(
        contract_id for contract_id in tasks_qs.filter(
            status='PENDING',
            priority__in=['HIGH', 'URGENT'],
            contract__isnull=False,
        ).values_list('contract_id', flat=True)
        if contract_id
    )
    urgent_case_ids.update(
        contract_id for contract_id in signatures_qs.filter(
            status__in=['PENDING', 'SENT', 'VIEWED'],
            created_at__lt=provider_response_cutoff,
        ).values_list('contract_id', flat=True)
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
    pending_provider_responses = list(
        signatures_qs.filter(status__in=['PENDING', 'SENT', 'VIEWED'], created_at__lt=provider_response_cutoff)
        .order_by('created_at')[:4]
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
                'href': reverse('contracts:case_detail', args=[case_record.pk]),
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
                'href': reverse('contracts:case_detail', args=[case_record.pk]),
            },
        )

    for review in pending_reviews:
        subject = review.due_diligence_process.title
        days_waiting = max((today - review.created_at.date()).days, 0)
        add_action(
            f'review-{review.id}',
            {
                'title': subject,
                'meta': f'Wacht op beoordeling ({review.get_assessment_status_display()}) • {days_waiting} dagen open',
                'badge': 'Beoordeling',
                'badge_class': 'badge-yellow',
                'href': reverse('contracts:conflict_check_update', args=[review.pk]),
            },
        )

    for signature in pending_provider_responses:
        days_waiting = max((today - signature.created_at.date()).days, 0)
        add_action(
            f'signature-{signature.id}',
            {
                'title': signature.contract.title,
                'meta': f'Wacht op aanbiederreactie van {signature.signer_name} • {days_waiting} dagen',
                'badge': 'Aanbiederreactie',
                'badge_class': 'badge-blue',
                'href': reverse('contracts:signature_request_list'),
            },
        )

    action_required_total = (
        cases_without_match
        + len(stale_cases)
        + len(pending_reviews)
        + len(pending_provider_responses)
        + risk_count
    )

    provider_capacity_qs = clients_qs.filter(status='ACTIVE').annotate(
        active_case_load=Count(
            'contracts',
            filter=Q(contracts__status__in=['ACTIVE', 'PENDING', 'IN_REVIEW', 'APPROVED']),
            distinct=True,
        ),
        active_matter_load=Count('matters', filter=Q(matters__status='ACTIVE'), distinct=True),
        pending_reactions=Count(
            'contracts__signature_requests',
            filter=Q(contracts__signature_requests__status__in=['PENDING', 'SENT', 'VIEWED']),
            distinct=True,
        ),
        open_match_decisions=Count(
            'contracts__approval_requests',
            filter=Q(contracts__approval_requests__status='PENDING'),
            distinct=True,
        ),
    ).order_by('-active_case_load', '-pending_reactions', 'name')

    provider_candidates = list(provider_capacity_qs.order_by('active_case_load', 'pending_reactions', 'name')[:6])
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
        case_domain_ids = set()
        if case_record.matter_id:
            case_domain_ids = set(case_record.matter.care_domains.values_list('id', flat=True))

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
                'contract': case_record,
                'href': reverse('contracts:case_detail', args=[case_record.pk]),
                'days_open': max((today - case_record.created_at.date()).days, 0),
                'action_href': f"{reverse('contracts:case_detail', args=[case_record.pk])}?flow=matching",
                'suggestions': suggestions,
            })

    provider_capacity_signals = []
    provider_capacity_critical_count = 0
    providers_with_capacity = 0
    for provider in provider_capacity_qs[:8]:
        max_load = max(provider.active_case_load, provider.active_matter_load)
        signal = None
        if max_load >= overload_threshold:
            signal = {
                'name': provider.name,
                'signal': 'Overbelasting',
                'detail': f'{max_load} lopende casussen of dossiers',
                'badge_class': 'badge-red',
            }
            provider_capacity_critical_count += 1
        elif provider.pending_reactions >= wait_threshold or provider.open_match_decisions >= wait_threshold:
            signal = {
                'name': provider.name,
                'signal': 'Wachttijd boven drempel',
                'detail': f'{provider.pending_reactions + provider.open_match_decisions} open reacties of besluiten',
                'badge_class': 'badge-yellow',
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

    placement_cases = case_records_qs.annotate(
        first_approval_decision=Min('approval_requests__decided_at', filter=Q(approval_requests__status='APPROVED')),
        first_signature=Min('signature_requests__signed_at', filter=Q(signature_requests__status='SIGNED')),
    ).filter(
        Q(approved_at__isnull=False)
        | Q(first_approval_decision__isnull=False)
        | Q(first_signature__isnull=False)
        | Q(start_date__isnull=False)
    )

    placement_durations = []
    for case_record in placement_cases:
        placement_dates = []
        if case_record.approved_at:
            placement_dates.append(case_record.approved_at.date())
        if case_record.first_approval_decision:
            placement_dates.append(case_record.first_approval_decision.date())
        if case_record.first_signature:
            placement_dates.append(case_record.first_signature.date())
        if case_record.start_date:
            placement_dates.append(case_record.start_date)
        if placement_dates:
            placement_days = (min(placement_dates) - case_record.created_at.date()).days
            if placement_days >= 0:
                placement_durations.append(placement_days)
    avg_intake_to_placement_days = round(sum(placement_durations) / len(placement_durations), 1) if placement_durations else 0

    context = {
        'total_cases': total_cases,
        'active_cases': active_cases,
        'intake_cases': intake_cases,
        'cases_without_match': cases_without_match,
        'completed_cases': completed_cases,
        'total_contracts': total_cases,
        'active_contracts': active_cases,
        'draft_contracts': intake_cases,
        'pending_contracts': cases_without_match,
        'completed_contracts': completed_cases,
        'total_clients': total_clients,
        'active_clients': active_clients,
        'active_configurations': active_configurations,
        'total_configurations': total_configurations,
        'active_matters': active_configurations,
        'total_matters': total_configurations,
        'pending_tasks': pending_tasks,
        'urgent_task_count': urgent_task_count,
        'active_workflows': active_workflows,
        'risk_count': risk_count,
        'recent_signals': recent_signals,
        'followup_tasks': followup_tasks,
        'overdue_deadlines': overdue_deadlines,
        'upcoming_deadline_count': upcoming_deadline_count,
        'total_documents': total_documents,
        'pending_approvals': pending_approvals,
        'pending_signatures': pending_signatures,
        'open_dsars': open_dsars,
        'unread_notifications': unread_notifications,
        'recent_audit': recent_audit,
        'case_status_data': case_status_data_values,
        'contract_status_data': case_status_data_values,
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
        'intake_phase_count': intake_phase_count,
        'avg_intake_to_placement_days': avg_intake_to_placement_days,
        'action_required': action_required,
        'action_required_total': action_required_total,
        'match_recommendations': match_recommendations,
        'matching_focus_case': matching_focus_case,
        'provider_capacity_signals': provider_capacity_signals,
        'provider_capacity_critical_count': provider_capacity_critical_count,
        'providers_with_capacity': providers_with_capacity,
        'has_cases': total_cases > 0,
        'has_providers': total_clients > 0,
        'today': today,
        'FEATURE_REDESIGN': is_feature_redesign_enabled(),
    }
    return render(request, 'dashboard.html', context)


@login_required
def privacy_dashboard(request):
    org = get_user_organization(request.user)
    is_privacy_admin = can_manage_organization(request.user, org)

    dsars_qs = (
        DSARRequest.objects.filter(client__organization=org)
        if org else DSARRequest.objects.none()
    )
    case_records_qs = (
        CareCase.objects.filter(organization=org)
        if org else CareCase.objects.none()
    )

    dsar_open_count = dsars_qs.filter(status__in=['RECEIVED', 'VERIFIED', 'IN_PROGRESS']).count()
    dsar_overdue_count = dsars_qs.filter(
        status__in=['RECEIVED', 'VERIFIED', 'IN_PROGRESS'],
        due_date__lt=date.today(),
    ).count()
    active_retention_count = RetentionPolicy.objects.filter(is_active=True).count()
    sensitive_cases_count = sum(
        1
        for case_record in case_records_qs.only('data_transfer_flag')
        if getattr(case_record, 'is_confidential', False) or case_record.data_transfer_flag
    )

    if is_privacy_admin and org:
        member_ids = OrganizationMembership.objects.filter(
            organization=org,
            is_active=True,
        ).values_list('user_id', flat=True)
        audit_events_count = AuditLog.objects.filter(user_id__in=member_ids).count()
        recent_audit_events = AuditLog.objects.filter(user_id__in=member_ids).select_related('user').order_by('-timestamp')[:8]
    else:
        audit_events_count = AuditLog.objects.filter(user=request.user).count()
        recent_audit_events = AuditLog.objects.filter(user=request.user).select_related('user').order_by('-timestamp')[:8]

    recent_dsars = dsars_qs.select_related('assigned_to', 'client').order_by('-received_date')[:6]

    context = {
        'is_privacy_admin': is_privacy_admin,
        'dsar_open_count': dsar_open_count,
        'dsar_overdue_count': dsar_overdue_count,
        'active_retention_count': active_retention_count,
        'sensitive_cases_count': sensitive_cases_count,
        'audit_events_count': audit_events_count,
        'recent_dsars': recent_dsars,
        'recent_audit_events': recent_audit_events,
    }
    return render(request, 'contracts/privacy_dashboard.html', context)


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
        results['contracts'] = case_records
        results['clients'] = client_qs.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(industry__icontains=q)
        )[:10]
        results['configurations'] = configurations
        results['matters'] = configurations
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
            MunicipalityConfiguration.objects.prefetch_related('care_domains', 'linked_providers', 'responsible_attorney'),
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
        return reverse('contracts:municipality_detail', kwargs={'pk': self.object.pk})


class MunicipalityConfigurationUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = MunicipalityConfiguration
    form_class = MunicipalityConfigurationForm
    template_name = 'contracts/municipality_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(MunicipalityConfiguration.objects.all(), org)

    def get_success_url(self):
        return reverse('contracts:municipality_detail', kwargs={'pk': self.object.pk})


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
            RegionalConfiguration.objects.prefetch_related('care_domains', 'linked_providers', 'served_municipalities', 'responsible_attorney'),
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
        return reverse('contracts:regional_detail', kwargs={'pk': self.object.pk})


class RegionalConfigurationUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = RegionalConfiguration
    form_class = RegionalConfigurationForm
    template_name = 'contracts/regional_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(RegionalConfiguration.objects.all(), org)

    def get_success_url(self):
        return reverse('contracts:regional_detail', kwargs={'pk': self.object.pk})


# ==================== CARE INTAKE (DueDiligence) VIEWS ====================
# FIX #1: Reroute /casussen/ to DueDiligenceProcess model

class DueDiligenceProcessListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    """List all care intakes (DueDiligenceProcess) for the organization."""
    model = DueDiligenceProcess
    template_name = 'contracts/duediligence_list.html'
    context_object_name = 'intakes'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(
            DueDiligenceProcess.objects.select_related(
                'organization', 'lead_attorney', 'care_category_main', 'contract'
            ).prefetch_related('risk_factors'),
            org,
        )
        
        # Search by title, case ID (contract FK), or lead attorney
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(lead_attorney__first_name__icontains=q)
                | Q(lead_attorney__last_name__icontains=q)
                | Q(contract__id__icontains=q)
            ).distinct()
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        
        # Filter by urgency
        urgency = self.request.GET.get('urgency')
        if urgency:
            qs = qs.filter(urgency=urgency)
        
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        
        # Statistics
        org_intakes = scope_queryset_for_organization(DueDiligenceProcess.objects.all(), org)
        ctx.update({
            'total_intakes': org_intakes.count(),
            'active_intakes': org_intakes.exclude(status=DueDiligenceProcess.ProcessStatus.COMPLETED).count(),
            'urgent_intakes': org_intakes.filter(urgency__in=[DueDiligenceProcess.Urgency.HIGH, DueDiligenceProcess.Urgency.CRISIS]).count(),
            'search_query': self.request.GET.get('q', ''),
            'status_choices': DueDiligenceProcess.ProcessStatus.choices,
            'urgency_choices': DueDiligenceProcess.Urgency.choices,
        })
        
        # Build intake rows for display
        intake_rows = []
        for intake in ctx['intakes']:
            intake_rows.append({
                'obj': intake,
                'title': intake.title,
                'status': intake.get_status_display(),
                'urgency': intake.get_urgency_display(),
                'lead': intake.lead_attorney.get_full_name() if intake.lead_attorney else '—',
                'category': intake.care_category_main.name if intake.care_category_main else '—',
                'created': intake.start_date,
            })
        
        ctx['intake_rows'] = intake_rows
        return ctx


class DueDiligenceProcessDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    """Show details of a specific care intake."""
    model = DueDiligenceProcess
    template_name = 'contracts/duediligence_detail.html'
    context_object_name = 'intake'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(
            DueDiligenceProcess.objects.select_related(
                'organization', 'lead_attorney', 'care_category_main', 'care_category_sub', 'contract'
            ).prefetch_related('risk_factors'),
            org,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        intake = self.object
        
        # Assessment records linked to this intake
        from django.db.models import Q
        assessments = CaseAssessment.objects.filter(due_diligence_process=intake)
        
        ctx.update({
            'assessment_list': assessments,
            'has_assessment': assessments.exists(),
            'assessment_status': assessments.first().get_assessment_status_display() if assessments.exists() else None,
            'risk_factors_list': intake.risk_factors.all(),
            'next_action': 'assessment' if not assessments.exists() else 'matching',
            'contract': intake.contract,
        })
        
        return ctx


class DueDiligenceProcessCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    """Create a new care intake."""
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/duediligence_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'is_edit': False,
            'page_title': 'Nieuwe intake',
            'button_text': 'Intake aanmaken',
        })
        return ctx

    def form_valid(self, form):
        org = get_user_organization(self.request.user)
        set_organization_on_instance(form.instance, org)
        if not form.instance.start_date:
            form.instance.start_date = date.today()
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'DueDiligenceProcess', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Intake "{self.object.title}" aangemaakt. Volgende stap: beoordeling.')
        return response

    def get_success_url(self):
        return reverse('contracts:case_detail', kwargs={'pk': self.object.pk})


class DueDiligenceProcessUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    """Update an existing care intake."""
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/duediligence_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(DueDiligenceProcess.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'is_edit': True,
            'page_title': f'Intake bewerken: {self.object.title}',
            'button_text': 'Wijzigingen opslaan',
        })
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'DueDiligenceProcess', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Intake "{self.object.title}" bijgewerkt.')
        return response

    def get_success_url(self):
        return reverse('contracts:case_detail', kwargs={'pk': self.object.pk})


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
        
        ctx.update({
            'intake': assessment.due_diligence_process,
            'next_action': 'matching',
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
                    DueDiligenceProcess.objects.all(), org
                ).get(pk=intake_id)
                initial['due_diligence_process'] = intake
            except DueDiligenceProcess.DoesNotExist:
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
        form.instance.assessed_by = self.request.user
        if not form.instance.assessment_status:
            form.instance.assessment_status = CaseAssessment.AssessmentStatus.DRAFT
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'CaseAssessment', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, 'Beoordeling aangemaakt. Volgende stap: matching.')
        return response

    def get_success_url(self):
        return reverse('contracts:assessment_detail', kwargs={'pk': self.object.pk})


class CaseAssessmentUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    """Update an existing assessment."""
    model = CaseAssessment
    form_class = CaseAssessmentForm
    template_name = 'contracts/assessment_form.html'

    def get_queryset(self):
        org = self.get_organization()
        return CaseAssessment.objects.filter(due_diligence_process__organization=org)

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
        return reverse('contracts:assessment_detail', kwargs={'pk': self.object.pk})
