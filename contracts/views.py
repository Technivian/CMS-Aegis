from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, Q, Avg, F
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta, date
from decimal import Decimal
import csv
import json
import logging
import re

from .forms import (
    ChecklistItemForm, WorkflowForm, WorkflowTemplateForm,
    BudgetForm, TrademarkRequestForm, LegalTaskForm, RiskLogForm, ComplianceChecklistForm,
    DueDiligenceProcessForm, DueDiligenceTaskForm, DueDiligenceRiskForm, BudgetExpenseForm,
    ClientForm, MatterForm, DocumentForm, TimeEntryForm, InvoiceForm,
    TrustAccountForm, TrustTransactionForm, DeadlineForm, UserProfileForm,
    ConflictCheckForm, ContractForm, RegistrationForm,
    CounterpartyForm, ClauseCategoryForm, ClauseTemplateForm, EthicalWallForm,
    SignatureRequestForm, DataInventoryForm, DSARRequestForm, SubprocessorForm,
    TransferRecordForm, RetentionPolicyForm, LegalHoldForm, ApprovalRuleForm,
    ApprovalRequestForm,
    OrganizationInvitationForm,
)
from .models import (
    Organization, OrganizationMembership, OrganizationInvitation,
    Contract, NegotiationThread, TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist, ChecklistItem,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk, Budget, BudgetExpense,
    Client, Matter, Document, TimeEntry, Invoice, TrustAccount, TrustTransaction,
    Deadline, AuditLog, Notification, UserProfile, ConflictCheck,
    Counterparty, ClauseCategory, ClauseTemplate, EthicalWall, SignatureRequest,
    DataInventoryRecord, DSARRequest, Subprocessor, TransferRecord, RetentionPolicy,
    LegalHold, ApprovalRule, ApprovalRequest,
)
from .middleware import log_action
from .permissions import (
    ContractAction,
    can_access_contract_action,
    can_manage_organization,
    get_active_org_membership,
    is_organization_owner,
)
from .tenancy import get_user_organization, scope_queryset_for_organization, set_organization_on_instance
from config.feature_flags import get_feature_flag, is_feature_redesign_enabled

logger = logging.getLogger(__name__)


def get_or_create_profile(user):
    profile, created = UserProfile.objects.get_or_create(user=user)
    return profile


def index(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def health_check(request):
    return HttpResponse("OK", content_type="text/plain")


class TenantScopedQuerysetMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        org = get_user_organization(self.request.user)
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
            qs = qs.filter(status=status)
        if client_type:
            qs = qs.filter(client_type=client_type)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_clients = scope_queryset_for_organization(Client.objects.all(), org)
        ctx['total_clients'] = tenant_clients.count()
        ctx['active_clients'] = tenant_clients.filter(status='ACTIVE').count()
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
        ctx['matters'] = self.object.matters.all()[:10]
        ctx['contracts'] = self.object.contracts.all()[:10]
        ctx['invoices'] = self.object.invoices.all()[:10]
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
        messages.success(self.request, f'Client "{self.object.name}" created successfully.')
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
        messages.success(self.request, f'Client "{self.object.name}" updated successfully.')
        return response


# ==================== MATTER VIEWS ====================

class MatterListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Matter
    template_name = 'contracts/matter_list.html'
    context_object_name = 'matters'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        qs = scope_queryset_for_organization(Matter.objects.select_related('client', 'responsible_attorney'), org)
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        practice_area = self.request.GET.get('practice_area')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(matter_number__icontains=q) | Q(client__name__icontains=q))
        if status:
            qs = qs.filter(status=status)
        if practice_area:
            qs = qs.filter(practice_area=practice_area)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_matters = scope_queryset_for_organization(Matter.objects.all(), org)
        ctx['total_matters'] = tenant_matters.count()
        ctx['active_matters'] = tenant_matters.filter(status='ACTIVE').count()
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class MatterDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Matter
    template_name = 'contracts/matter_detail.html'
    context_object_name = 'matter'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Matter.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['contracts'] = self.object.contracts.all()
        ctx['documents'] = self.object.documents.all()[:10]
        ctx['time_entries'] = self.object.time_entries.all()[:10]
        ctx['tasks'] = self.object.tasks.all()[:10]
        ctx['deadlines'] = self.object.deadlines.filter(is_completed=False)[:10]
        ctx['risks'] = self.object.risks.all()[:10]
        return ctx


class MatterCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Matter
    form_class = MatterForm
    template_name = 'contracts/matter_form.html'

    def get_success_url(self):
        return reverse('contracts:matter_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Matter', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Matter "{self.object.title}" created.')
        return response


class MatterUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Matter
    form_class = MatterForm
    template_name = 'contracts/matter_form.html'

    def get_success_url(self):
        return reverse('contracts:matter_detail', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Matter.objects.all(), org)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Matter', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Matter "{self.object.title}" updated.')
        return response


# ==================== DOCUMENT VIEWS ====================

class DocumentListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Document
    template_name = 'contracts/document_list.html'
    context_object_name = 'documents'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
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
        org = get_user_organization(self.request.user)
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
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to upload documents for this contract.')
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Document', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Document "{self.object.title}" uploaded.')
        return response


class DocumentUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Document
    form_class = DocumentForm
    template_name = 'contracts/document_form.html'
    success_url = reverse_lazy('contracts:document_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Document.objects.all(), org)

    def dispatch(self, request, *args, **kwargs):
        document = self.get_object()
        if document.contract and not can_access_contract_action(request.user, document.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit documents for this contract.')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Document', self.object.id, str(self.object), request=self.request)
        return response


# ==================== TIME ENTRY VIEWS ====================

class TimeEntryListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = TimeEntry
    template_name = 'contracts/time_entry_list.html'
    context_object_name = 'time_entries'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        qs = scope_queryset_for_organization(
            TimeEntry.objects.select_related('matter', 'matter__client', 'user'),
            org,
        )
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(description__icontains=q) | Q(matter__title__icontains=q))
        billable = self.request.GET.get('billable')
        if billable == 'yes':
            qs = qs.filter(is_billable=True)
        elif billable == 'no':
            qs = qs.filter(is_billable=False)
        return qs.order_by('-date', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        org = get_user_organization(self.request.user)
        my_entries = scope_queryset_for_organization(TimeEntry.objects.filter(user=self.request.user), org)
        ctx['today_hours'] = my_entries.filter(date=today).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        ctx['week_hours'] = my_entries.filter(date__gte=week_start).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        ctx['month_hours'] = my_entries.filter(date__month=today.month, date__year=today.year).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        return ctx


class TimeEntryCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = TimeEntry
    form_class = TimeEntryForm
    template_name = 'contracts/time_entry_form.html'
    success_url = reverse_lazy('contracts:time_entry_list')

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.user = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'TimeEntry', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, 'Time entry recorded.')
        return response


class TimeEntryUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = TimeEntry
    form_class = TimeEntryForm
    template_name = 'contracts/time_entry_form.html'
    success_url = reverse_lazy('contracts:time_entry_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(TimeEntry.objects.all(), org)


# ==================== INVOICE VIEWS ====================

class InvoiceListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'contracts/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        qs = scope_queryset_for_organization(Invoice.objects.select_related('client', 'matter'), org)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-issue_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_invoices = scope_queryset_for_organization(Invoice.objects.all(), org)
        ctx['total_outstanding'] = tenant_invoices.filter(status__in=['SENT', 'OVERDUE']).aggregate(
            total=Sum('total_amount'))['total'] or Decimal('0')
        ctx['total_paid'] = tenant_invoices.filter(status='PAID').aggregate(
            total=Sum('total_amount'))['total'] or Decimal('0')
        ctx['overdue_count'] = tenant_invoices.filter(status='OVERDUE').count()
        overdue_sent = tenant_invoices.filter(status='SENT', due_date__lt=date.today())
        overdue_sent.update(status='OVERDUE')
        return ctx


class InvoiceDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'contracts/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Invoice.objects.all(), org)


class InvoiceCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'contracts/invoice_form.html'

    def get_success_url(self):
        return reverse('contracts:invoice_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Invoice', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Invoice #{self.object.invoice_number} created.')
        return response


class InvoiceUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'contracts/invoice_form.html'

    def get_success_url(self):
        return reverse('contracts:invoice_detail', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Invoice.objects.all(), org)


# ==================== TRUST ACCOUNT VIEWS ====================

class TrustAccountListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = TrustAccount
    template_name = 'contracts/trust_account_list.html'
    context_object_name = 'accounts'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_balance'] = TrustAccount.objects.aggregate(total=Sum('balance'))['total'] or Decimal('0')
        return ctx


class TrustAccountDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = TrustAccount
    template_name = 'contracts/trust_account_detail.html'
    context_object_name = 'account'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['transactions'] = self.object.transactions.all()[:20]
        ctx['transaction_form'] = TrustTransactionForm()
        return ctx


class TrustAccountCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = TrustAccount
    form_class = TrustAccountForm
    template_name = 'contracts/trust_account_form.html'
    success_url = reverse_lazy('contracts:trust_account_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'TrustAccount', self.object.id, str(self.object), request=self.request)
        return response


class AddTrustTransactionView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = TrustTransaction
    form_class = TrustTransactionForm
    template_name = 'contracts/trust_transaction_form.html'

    def form_valid(self, form):
        form.instance.account_id = self.kwargs['account_pk']
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'TrustTransaction', self.object.id, str(self.object), request=self.request)
        return response

    def get_success_url(self):
        return reverse('contracts:trust_account_detail', kwargs={'pk': self.kwargs['account_pk']})


# ==================== DEADLINE VIEWS ====================

class DeadlineListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Deadline
    template_name = 'contracts/deadline_list.html'
    context_object_name = 'deadlines'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if org:
            q_org = Q(contract__organization=org) | Q(matter__organization=org)
            qs = Deadline.objects.select_related('matter', 'contract', 'assigned_to').filter(q_org)
        else:
            qs = Deadline.objects.none()
        show = self.request.GET.get('show', 'upcoming')
        if show == 'overdue':
            qs = qs.filter(is_completed=False, due_date__lt=date.today())
        elif show == 'completed':
            qs = qs.filter(is_completed=True)
        elif show == 'all':
            pass
        else:
            qs = qs.filter(is_completed=False, due_date__gte=date.today())
        return qs.order_by('due_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        if org:
            q_org = Q(contract__organization=org) | Q(matter__organization=org)
            org_deadlines = Deadline.objects.filter(q_org)
        else:
            org_deadlines = Deadline.objects.none()
        ctx['overdue_count'] = org_deadlines.filter(is_completed=False, due_date__lt=date.today()).count()
        ctx['upcoming_count'] = org_deadlines.filter(is_completed=False, due_date__gte=date.today()).count()
        ctx['show'] = self.request.GET.get('show', 'upcoming')
        return ctx


class DeadlineCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('contracts:deadline_list')

    def form_valid(self, form):
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create deadlines for this contract.')
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Deadline', self.object.id, str(self.object), request=self.request)
        return response


class DeadlineUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('contracts:deadline_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return Deadline.objects.none()
        return Deadline.objects.filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        )

    def dispatch(self, request, *args, **kwargs):
        deadline = self.get_object()
        if deadline.contract and not can_access_contract_action(request.user, deadline.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit this contract deadline.')
        return super().dispatch(request, *args, **kwargs)


@login_required
@require_POST
def deadline_complete(request, pk):
    organization = get_user_organization(request.user)
    if organization:
        deadline_qs = Deadline.objects.filter(
            Q(contract__organization=organization) | Q(matter__organization=organization)
        )
    else:
        deadline_qs = Deadline.objects.none()
    deadline = get_object_or_404(deadline_qs, pk=pk)
    if deadline.contract and not can_access_contract_action(request.user, deadline.contract, ContractAction.EDIT):
        return HttpResponseForbidden('You do not have permission to complete this contract deadline.')
    deadline.is_completed = True
    deadline.completed_at = timezone.now()
    deadline.completed_by = request.user
    deadline.save()
    log_action(request.user, 'UPDATE', 'Deadline', deadline.id, str(deadline), request=request)
    messages.success(request, f'Deadline "{deadline.title}" marked as complete.')
    return redirect('contracts:deadline_list')


# ==================== CONFLICT CHECK VIEWS ====================

class ConflictCheckListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ConflictCheck
    template_name = 'contracts/conflict_check_list.html'
    context_object_name = 'conflict_checks'
    paginate_by = 25


class ConflictCheckCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ConflictCheck
    form_class = ConflictCheckForm
    template_name = 'contracts/conflict_check_form.html'
    success_url = reverse_lazy('contracts:conflict_check_list')

    def form_valid(self, form):
        form.instance.checked_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'ConflictCheck', self.object.id, str(self.object), request=self.request)
        return response


class ConflictCheckUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ConflictCheck
    form_class = ConflictCheckForm
    template_name = 'contracts/conflict_check_form.html'
    success_url = reverse_lazy('contracts:conflict_check_list')


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
        messages.success(request, f'Switched to {membership.organization.name}.')
    else:
        messages.error(request, 'You do not have access to that organization.')
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))



def _extract_valid_mentions(raw_text, organization, author_user_id):
    if not raw_text or not organization:
        return []

    mention_candidates = {m.lower() for m in re.findall(r'@([A-Za-z0-9_.-]{3,150})', raw_text)}
    if not mention_candidates:
        return []

    memberships = (
        OrganizationMembership.objects
        .filter(organization=organization, is_active=True)
        .select_related('user')
    )
    valid_users = []
    seen_user_ids = set()
    for membership in memberships:
        username = (membership.user.username or '').lower()
        if username in mention_candidates and membership.user_id != author_user_id and membership.user_id not in seen_user_ids:
            valid_users.append(membership.user)
            seen_user_ids.add(membership.user_id)
    return valid_users


def _build_contract_ai_response(contract, prompt):
    today = timezone.localdate()
    normalized_prompt = (prompt or '').strip().lower()

    risks = []
    if contract.risk_level in [Contract.RiskLevel.HIGH, Contract.RiskLevel.CRITICAL]:
        risks.append(f'Risk level is {contract.get_risk_level_display()}; prioritize legal review.')
    if contract.data_transfer_flag and not contract.dpa_attached:
        risks.append('Cross-border data transfer is enabled but no DPA is attached.')
    if contract.data_transfer_flag and not contract.scc_attached:
        risks.append('Cross-border transfer is enabled but SCCs are not marked as attached.')

    timeline = []
    if contract.end_date:
        days_to_end = (contract.end_date - today).days
        timeline.append(f'End date is in {days_to_end} day(s) on {contract.end_date.isoformat()}.')
    if contract.renewal_date:
        days_to_renewal = (contract.renewal_date - today).days
        timeline.append(f'Renewal date is in {days_to_renewal} day(s) on {contract.renewal_date.isoformat()}.')
    if contract.notice_period_days and contract.end_date:
        timeline.append(f'Notice period is {contract.notice_period_days} day(s).')

    recommendations = [
        'Verify business owner and legal owner are assigned for renewal decisions.',
        'Confirm required documents and amendment history are attached before approval.',
    ]
    if contract.auto_renew:
        recommendations.append('Auto-renew is enabled; set a cancellation checkpoint before notice deadline.')
    if 'renew' in normalized_prompt or 'expiry' in normalized_prompt or 'expire' in normalized_prompt:
        recommendations.append('Generate a renewal decision memo and circulate it to stakeholders now.')
    if 'risk' in normalized_prompt:
        recommendations.append('Run a clause-by-clause risk check and capture findings in negotiation notes.')

    return {
        'summary': {
            'title': contract.title,
            'status': contract.get_status_display(),
            'contract_type': contract.get_contract_type_display(),
            'lifecycle_stage': contract.lifecycle_stage,
            'counterparty': contract.counterparty,
        },
        'timeline': timeline,
        'risks': risks,
        'recommendations': recommendations,
        'mode': 'internal-rules-engine',
    }


def _build_invite_url(request, invitation):
    return request.build_absolute_uri(
        reverse('contracts:accept_organization_invite', kwargs={'token': invitation.token})
    )


def _send_invitation_email(invitation, invite_url):
    subject = f"You're invited to join {invitation.organization.name}"
    body = (
        f"You have been invited to join {invitation.organization.name} as {invitation.get_role_display()}.\n\n"
        f"Accept invitation: {invite_url}\n\n"
        "This link expires in 7 days."
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


# ==================== REPORTS VIEW ====================

@login_required
def reports_dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    org = get_user_organization(request.user)
    contracts_qs = scope_queryset_for_organization(Contract.objects.all(), org)
    clients_qs = scope_queryset_for_organization(Client.objects.all(), org)
    matters_qs = scope_queryset_for_organization(Matter.objects.all(), org)
    time_entries_qs = scope_queryset_for_organization(TimeEntry.objects.all(), org)
    invoices_qs = scope_queryset_for_organization(Invoice.objects.all(), org)
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

    total_contracts = contracts_qs.count()
    active_contracts = contracts_qs.filter(status='ACTIVE').count()
    total_contract_value = contracts_qs.filter(value__isnull=False).aggregate(total=Sum('value'))['total'] or Decimal('0')

    total_clients = clients_qs.count()
    active_clients = clients_qs.filter(status='ACTIVE').count()

    total_matters = matters_qs.count()
    active_matters = matters_qs.filter(status='ACTIVE').count()

    monthly_hours = time_entries_qs.filter(
        date__gte=month_start
    ).aggregate(total=Sum('hours'))['total'] or Decimal('0')

    yearly_revenue = invoices_qs.filter(
        status='PAID', issue_date__gte=year_start
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    outstanding = invoices_qs.filter(
        status__in=['SENT', 'OVERDUE']
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    overdue_deadlines = deadlines_qs.filter(is_completed=False, due_date__lt=today).count()
    upcoming_deadlines = deadlines_qs.filter(
        is_completed=False, due_date__gte=today, due_date__lte=today + timedelta(days=7)
    ).count()

    high_risks = risks_qs.filter(risk_level__in=['HIGH', 'CRITICAL']).count()

    monthly_billing = []
    for i in range(6):
        m = today.replace(day=1) - timedelta(days=30 * i)
        month_total = invoices_qs.filter(
            issue_date__month=m.month, issue_date__year=m.year
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        monthly_billing.append({
            'month': m.strftime('%b %Y'),
            'total': float(month_total)
        })
    monthly_billing.reverse()

    practice_areas = matters_qs.filter(status='ACTIVE').values('practice_area').annotate(
        count=Count('id')).order_by('-count')

    context = {
        'total_contracts': total_contracts,
        'active_contracts': active_contracts,
        'total_contract_value': total_contract_value,
        'total_clients': total_clients,
        'active_clients': active_clients,
        'total_matters': total_matters,
        'active_matters': active_matters,
        'monthly_hours': monthly_hours,
        'yearly_revenue': yearly_revenue,
        'outstanding': outstanding,
        'overdue_deadlines': overdue_deadlines,
        'upcoming_deadlines': upcoming_deadlines,
        'high_risks': high_risks,
        'monthly_billing': json.dumps(monthly_billing),
        'practice_areas': list(practice_areas),
    }
    return render(request, 'contracts/reports_dashboard.html', context)


# ==================== CONTRACT VIEWS ====================

class ContractListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/contract_list.html'
    context_object_name = 'contracts'
    paginate_by = 25

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        qs = scope_queryset_for_organization(Contract.objects.select_related('client', 'matter', 'created_by'), org)
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        contract_type = self.request.GET.get('type')
        sort = self.request.GET.get('sort', '-created_at')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(counterparty__icontains=q))
        if status:
            qs = qs.filter(status=status)
        if contract_type:
            qs = qs.filter(contract_type=contract_type)

        # Restrict sorting to known fields only.
        allowed_sort_fields = {
            'title', '-title',
            'status', '-status',
            'end_date', '-end_date',
            'created_at', '-created_at',
            'value', '-value',
        }
        if sort not in allowed_sort_fields:
            sort = '-created_at'

        return qs.order_by(sort)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_contracts = scope_queryset_for_organization(Contract.objects.all(), org)
        context['FEATURE_REDESIGN'] = is_feature_redesign_enabled()
        context['search_query'] = self.request.GET.get('q', '')
        context['sort'] = self.request.GET.get('sort', '-created_at')
        context['status_tabs'] = [
            ('All', ''),
            ('Active', 'ACTIVE'),
            ('Draft', 'DRAFT'),
            ('Pending', 'PENDING'),
            ('Expired', 'EXPIRED'),
        ]
        context['total_contracts'] = tenant_contracts.count()
        context['active_contracts'] = tenant_contracts.filter(status='ACTIVE').count()
        _expiring_qs = tenant_contracts.filter(
            end_date__lte=date.today() + timedelta(days=30),
            end_date__gte=date.today(),
            status='ACTIVE'
        )
        context['expiring_soon'] = _expiring_qs.count()
        context['expiring_contract_ids'] = set(_expiring_qs.values_list('id', flat=True))

        if context['FEATURE_REDESIGN']:
            contracts_data = []
            for contract in self.get_queryset():
                contracts_data.append({
                    'id': contract.id,
                    'title': contract.title,
                    'status': contract.status,
                    'status_display': contract.get_status_display(),
                    'contract_type': contract.get_contract_type_display(),
                    'start_date': contract.start_date.strftime('%b %d, %Y') if contract.start_date else None,
                    'end_date': contract.end_date.strftime('%b %d, %Y') if contract.end_date else None,
                    'value': float(contract.value) if contract.value else None,
                    'counterparty': contract.counterparty or '',
                    'client': contract.client.name if contract.client else '',
                    'owner': contract.created_by.get_full_name() if contract.created_by else 'System',
                    'updated_at': contract.updated_at.strftime('%b %d, %Y'),
                })
            context['contracts_json'] = json.dumps(contracts_data)
        return context


class ContractDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Contract
    template_name = 'contracts/contract_detail.html'
    context_object_name = 'contract'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Contract.objects.all(), org)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['documents'] = self.object.documents.all()[:10]
        ctx['deadlines'] = self.object.deadlines.filter(is_completed=False)[:5]
        ctx['negotiation_threads'] = self.object.negotiation_threads.all()[:10]
        return ctx


class ContractCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Contract
    form_class = ContractForm
    template_name = 'contracts/contract_form.html'
    success_url = reverse_lazy('contracts:contract_list')

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Contract', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Contract "{self.object.title}" created.')
        return response


class ContractUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Contract
    form_class = ContractForm
    template_name = 'contracts/contract_form.html'
    success_url = reverse_lazy('contracts:contract_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Contract.objects.all(), org)

    def dispatch(self, request, *args, **kwargs):
        contract = self.get_object()
        if not can_access_contract_action(request.user, contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit this contract.')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Contract', self.object.id, str(self.object), request=self.request)
        return response


# ==================== WORKFLOW VIEWS ====================

class WorkflowTemplateListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_list.html'
    context_object_name = 'workflow_templates'


class WorkflowTemplateDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_detail.html'
    context_object_name = 'workflow_template'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['steps'] = WorkflowTemplateStep.objects.filter(template=self.object).order_by('order')
        return context


class WorkflowTemplateCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = WorkflowTemplate
    form_class = WorkflowTemplateForm
    template_name = 'contracts/workflow_template_form.html'
    success_url = reverse_lazy('contracts:workflow_template_list')


class WorkflowTemplateUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = WorkflowTemplate
    form_class = WorkflowTemplateForm
    template_name = 'contracts/workflow_template_form.html'
    success_url = reverse_lazy('contracts:workflow_template_list')


class WorkflowListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Workflow
    template_name = 'contracts/workflow_template_list.html'
    context_object_name = 'workflows'

    def get_queryset(self):
        queryset = Workflow.objects.all()
        contract_pk = self.request.GET.get('contract_pk')
        if contract_pk:
            queryset = queryset.filter(contract=contract_pk)
        return queryset.order_by('-created_at')


class WorkflowDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Workflow
    template_name = 'contracts/workflow_detail.html'
    context_object_name = 'workflow'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['steps'] = WorkflowStep.objects.filter(workflow=self.object).order_by('order')
        context['step_form'] = WorkflowForm()
        return context


class WorkflowCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Workflow
    form_class = WorkflowForm
    template_name = 'contracts/workflow_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class WorkflowUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Workflow
    form_class = WorkflowForm
    template_name = 'contracts/workflow_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.pk})


# ==================== LEGAL TASK VIEWS ====================

class LegalTaskKanbanView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = LegalTask
    template_name = 'contracts/legal_task_board.html'
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
    template_name = 'contracts/legal_task_form.html'
    success_url = reverse_lazy('contracts:legal_task_kanban')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        org = get_user_organization(self.request.user)
        if org:
            form.fields['contract'].queryset = scope_queryset_for_organization(Contract.objects.all(), org)
            form.fields['matter'].queryset = scope_queryset_for_organization(Matter.objects.all(), org)
        else:
            form.fields['contract'].queryset = Contract.objects.none()
            form.fields['matter'].queryset = Matter.objects.none()
        return form

    def form_valid(self, form):
        org = get_user_organization(self.request.user)
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create tasks for this contract.')
        if form.instance.matter and org and form.instance.matter.organization_id != org.id:
            return HttpResponseForbidden('You do not have permission to create tasks for this matter.')
        return super().form_valid(form)


class LegalTaskUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/legal_task_form.html'
    success_url = reverse_lazy('contracts:legal_task_kanban')

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
            form.fields['contract'].queryset = scope_queryset_for_organization(Contract.objects.all(), org)
            form.fields['matter'].queryset = scope_queryset_for_organization(Matter.objects.all(), org)
        else:
            form.fields['contract'].queryset = Contract.objects.none()
            form.fields['matter'].queryset = Matter.objects.none()
        return form

    def dispatch(self, request, *args, **kwargs):
        task = self.get_object()
        if task.contract and not can_access_contract_action(request.user, task.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit tasks for this contract.')
        org = get_user_organization(request.user)
        if task.matter and org and task.matter.organization_id != org.id:
            return HttpResponseForbidden('You do not have permission to edit tasks for this matter.')
        return super().dispatch(request, *args, **kwargs)


# ==================== TRADEMARK VIEWS ====================

class TrademarkRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_list.html'
    context_object_name = 'trademark_requests'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if org:
            qs = TrademarkRequest.objects.select_related('client', 'matter').filter(
                Q(client__organization=org) | Q(matter__organization=org)
            )
        else:
            qs = TrademarkRequest.objects.none()
        search_query = (self.request.GET.get('q') or '').strip()
        status = (self.request.GET.get('status') or '').strip()

        if search_query:
            qs = qs.filter(
                Q(mark_text__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(client__name__icontains=search_query)
                | Q(matter__title__icontains=search_query)
            )

        if status:
            qs = qs.filter(status=status)

        return qs.order_by('-updated_at', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        if org:
            tenant_requests = TrademarkRequest.objects.filter(
                Q(client__organization=org) | Q(matter__organization=org)
            )
        else:
            tenant_requests = TrademarkRequest.objects.none()
        ctx['search_query'] = (self.request.GET.get('q') or '').strip()
        ctx['selected_status'] = (self.request.GET.get('status') or '').strip()
        ctx['status_choices'] = TrademarkRequest.Status.choices
        ctx['total_requests'] = tenant_requests.count()
        ctx['pending_requests'] = tenant_requests.filter(status=TrademarkRequest.Status.PENDING).count()
        ctx['approved_requests'] = tenant_requests.filter(status=TrademarkRequest.Status.APPROVED).count()
        ctx['request_tabs'] = [
            ('All Requests', ''),
            ('Pending', TrademarkRequest.Status.PENDING),
            ('Approved', TrademarkRequest.Status.APPROVED),
        ]
        return ctx


class TrademarkRequestDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_detail.html'
    context_object_name = 'trademark_request'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return TrademarkRequest.objects.none()
        return TrademarkRequest.objects.filter(
            Q(client__organization=org) | Q(matter__organization=org)
        )


class TrademarkRequestCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = TrademarkRequest
    form_class = TrademarkRequestForm
    template_name = 'contracts/trademark_request_form.html'
    success_url = reverse_lazy('contracts:trademark_request_list')


class TrademarkRequestUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = TrademarkRequest
    form_class = TrademarkRequestForm
    template_name = 'contracts/trademark_request_form.html'
    success_url = reverse_lazy('contracts:trademark_request_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return TrademarkRequest.objects.none()
        return TrademarkRequest.objects.filter(
            Q(client__organization=org) | Q(matter__organization=org)
        )


# ==================== RISK MANAGEMENT VIEWS ====================

class RiskLogListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = RiskLog
    template_name = 'contracts/risk_log_list.html'
    context_object_name = 'risk_logs'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if org:
            qs = RiskLog.objects.select_related('contract', 'matter', 'created_by').filter(
                Q(contract__organization=org) | Q(matter__organization=org)
            )
        else:
            qs = RiskLog.objects.none()
        search_query = (self.request.GET.get('q') or '').strip()
        risk_level = (self.request.GET.get('risk_level') or '').strip()

        if search_query:
            qs = qs.filter(
                Q(title__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(contract__title__icontains=search_query)
                | Q(matter__title__icontains=search_query)
            )

        if risk_level:
            qs = qs.filter(risk_level=risk_level)

        risk_order = models.Case(
            models.When(risk_level=RiskLog.RiskLevel.CRITICAL, then=models.Value(0)),
            models.When(risk_level=RiskLog.RiskLevel.HIGH, then=models.Value(1)),
            models.When(risk_level=RiskLog.RiskLevel.MEDIUM, then=models.Value(2)),
            default=models.Value(3),
            output_field=models.IntegerField(),
        )
        return qs.annotate(risk_sort=risk_order).order_by('risk_sort', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        if org:
            tenant_risks = RiskLog.objects.filter(
                Q(contract__organization=org) | Q(matter__organization=org)
            )
        else:
            tenant_risks = RiskLog.objects.none()
        ctx['search_query'] = (self.request.GET.get('q') or '').strip()
        ctx['selected_risk_level'] = (self.request.GET.get('risk_level') or '').strip()
        ctx['total_risks'] = tenant_risks.count()
        ctx['high_risk_count'] = tenant_risks.filter(risk_level=RiskLog.RiskLevel.HIGH).count()
        ctx['critical_risk_count'] = tenant_risks.filter(risk_level=RiskLog.RiskLevel.CRITICAL).count()
        ctx['risk_tabs'] = [
            ('All Risks', ''),
            ('High Risk', RiskLog.RiskLevel.HIGH),
            ('Critical Risk', RiskLog.RiskLevel.CRITICAL),
        ]
        return ctx


class RiskLogCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = RiskLog
    form_class = RiskLogForm
    template_name = 'contracts/risk_log_form.html'
    success_url = reverse_lazy('contracts:risk_log_list')

    def form_valid(self, form):
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create risk logs for this contract.')
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class RiskLogUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = RiskLog
    form_class = RiskLogForm
    template_name = 'contracts/risk_log_form.html'
    success_url = reverse_lazy('contracts:risk_log_list')

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return RiskLog.objects.none()
        return RiskLog.objects.filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        )

    def dispatch(self, request, *args, **kwargs):
        risk_log = self.get_object()
        if risk_log.contract and not can_access_contract_action(request.user, risk_log.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit risk logs for this contract.')
        return super().dispatch(request, *args, **kwargs)


# ==================== COMPLIANCE VIEWS ====================

class ComplianceChecklistListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_list.html'
    context_object_name = 'compliance_checklists'


class ComplianceChecklistDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_detail.html'
    context_object_name = 'compliance_checklist'


class ComplianceChecklistCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ComplianceChecklist
    form_class = ComplianceChecklistForm
    template_name = 'contracts/compliance_checklist_form.html'
    success_url = reverse_lazy('contracts:compliance_checklist_list')

    def form_valid(self, form):
        if form.instance.contract and not can_access_contract_action(self.request.user, form.instance.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create checklists for this contract.')
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ComplianceChecklistUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ComplianceChecklist
    form_class = ComplianceChecklistForm
    template_name = 'contracts/compliance_checklist_form.html'
    success_url = reverse_lazy('contracts:compliance_checklist_list')

    def dispatch(self, request, *args, **kwargs):
        checklist = self.get_object()
        if checklist.contract and not can_access_contract_action(request.user, checklist.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to edit this contract checklist.')
        return super().dispatch(request, *args, **kwargs)


# ==================== DUE DILIGENCE VIEWS ====================

class DueDiligenceListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_list.html'
    context_object_name = 'processes'


class DueDiligenceCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')


class DueDiligenceDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_detail.html'
    context_object_name = 'process'


class DueDiligenceUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')


# ==================== BUDGET VIEWS ====================

class BudgetListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'contracts/budget_list.html'
    context_object_name = 'budgets'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        qs = scope_queryset_for_organization(Budget.objects.all(), org)
        search_query = (self.request.GET.get('q') or '').strip()
        year = (self.request.GET.get('year') or '').strip()

        if search_query:
            qs = qs.filter(Q(department__icontains=search_query) | Q(description__icontains=search_query))

        if year and year.isdigit():
            qs = qs.filter(year=int(year))

        return qs.order_by('-year', 'quarter', 'department')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_budgets = scope_queryset_for_organization(Budget.objects.all(), org)
        current_year = timezone.localdate().year
        ctx['search_query'] = (self.request.GET.get('q') or '').strip()
        ctx['selected_year'] = (self.request.GET.get('year') or '').strip()
        ctx['current_year'] = current_year
        ctx['total_budgets'] = tenant_budgets.count()
        ctx['current_year_budgets'] = tenant_budgets.filter(year=current_year).count()
        ctx['total_allocated'] = tenant_budgets.aggregate(total=Coalesce(Sum('allocated_amount'), Decimal('0')))['total']
        ctx['budget_tabs'] = [
            ('All Budgets', ''),
            (str(current_year), str(current_year)),
        ]
        return ctx


class BudgetCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')


class BudgetDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Budget
    template_name = 'contracts/budget_detail.html'
    context_object_name = 'budget'


class BudgetUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')


# ==================== HELPER / REPOSITORY VIEWS ====================

class RepositoryView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/repository.html'
    context_object_name = 'contracts'

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        return scope_queryset_for_organization(Contract.objects.select_related('created_by'), org).order_by('-updated_at', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_user_organization(self.request.user)
        tenant_contracts = scope_queryset_for_organization(Contract.objects.all(), org)
        ctx['total_documents'] = tenant_contracts.count()
        ctx['active_documents'] = tenant_contracts.filter(status=Contract.Status.ACTIVE).count()
        ctx['draft_documents'] = tenant_contracts.filter(status=Contract.Status.DRAFT).count()
        ctx['expiring_documents'] = tenant_contracts.filter(end_date__isnull=False, end_date__lte=timezone.localdate() + timedelta(days=30)).count()
        return ctx


class ProfileView(LoginRequiredMixin, View):
    def get(self, request):
        profile = get_or_create_profile(request.user)
        form = UserProfileForm(instance=profile, initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
        })
        return render(request, 'profile.html', {'form': form, 'profile': profile})

    def post(self, request):
        profile = get_or_create_profile(request.user)
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            request.user.first_name = form.cleaned_data.get('first_name', '')
            request.user.last_name = form.cleaned_data.get('last_name', '')
            request.user.email = form.cleaned_data.get('email', '')
            request.user.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
        return render(request, 'profile.html', {'form': form, 'profile': profile})


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

        login(self.request, self.object)
        return response


# ==================== NEGOTIATION VIEWS ====================

class AddNegotiationNoteView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = NegotiationThread
    fields = ['title', 'content']
    template_name = 'contracts/negotiation_note_form.html'

    def form_valid(self, form):
        organization = get_user_organization(self.request.user)
        contract = get_object_or_404(
            scope_queryset_for_organization(Contract.objects.all(), organization),
            id=self.kwargs['pk'],
        )
        if not can_access_contract_action(self.request.user, contract, ContractAction.COMMENT):
            return HttpResponseForbidden('You do not have permission to comment on this contract.')
        form.instance.contract = contract
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        mentioned_users = _extract_valid_mentions(form.instance.content, contract.organization, self.request.user.id)
        for user in mentioned_users:
            Notification.objects.create(
                recipient=user,
                notification_type=Notification.NotificationType.CONTRACT,
                title=f'Mentioned in contract note: {contract.title}',
                message=(
                    f'{self.request.user.get_full_name() or self.request.user.username} '
                    f'mentioned you in note "{form.instance.title}".'
                ),
                link=reverse('contracts:contract_detail', kwargs={'pk': contract.id}),
            )

        log_action(
            self.request.user,
            AuditLog.Action.CREATE,
            'NegotiationThread',
            object_id=self.object.id,
            object_repr=str(self.object),
            changes={
                'organization_id': contract.organization_id,
                'event': 'negotiation_note_created',
                'mentions_count': len(mentioned_users),
            },
            request=self.request,
        )
        if mentioned_users:
            messages.success(self.request, f'Note saved and {len(mentioned_users)} mention notification(s) sent.')
        else:
            messages.success(self.request, 'Negotiation note saved.')
        return response

    def get_success_url(self):
        return reverse_lazy('contracts:contract_detail', kwargs={'pk': self.kwargs['pk']})


# ==================== ACTION VIEWS ====================

class ToggleChecklistItemView(LoginRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(ChecklistItem, pk=pk)
        linked_contract = item.checklist.contract
        if linked_contract and not can_access_contract_action(request.user, linked_contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to update this contract checklist item.')
        item.is_completed = not item.is_completed
        item.completed_by = request.user if item.is_completed else None
        item.completed_at = timezone.now() if item.is_completed else None
        item.save()
        return redirect('contracts:compliance_checklist_detail', pk=item.checklist.pk)


class AddChecklistItemView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ChecklistItem
    form_class = ChecklistItemForm
    template_name = 'contracts/checklist_item_form.html'

    def form_valid(self, form):
        checklist_pk = self.kwargs.get('checklist_pk') or self.kwargs.get('pk')
        checklist = get_object_or_404(ComplianceChecklist, pk=checklist_pk)
        if checklist.contract and not can_access_contract_action(self.request.user, checklist.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to add items to this contract checklist.')
        form.instance.checklist = checklist
        return super().form_valid(form)

    def get_success_url(self):
        checklist_pk = self.kwargs.get('checklist_pk') or self.kwargs.get('pk')
        return reverse_lazy('contracts:compliance_checklist_detail', kwargs={'pk': checklist_pk})


class AddDueDiligenceItemView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = DueDiligenceTask
    form_class = DueDiligenceTaskForm
    template_name = 'contracts/dd_task_form.html'

    def form_valid(self, form):
        form.instance.process_id = self.kwargs['process_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.kwargs['process_pk']})


class AddDueDiligenceRiskView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = DueDiligenceRisk
    form_class = DueDiligenceRiskForm
    template_name = 'contracts/dd_risk_form.html'

    def form_valid(self, form):
        form.instance.process_id = self.kwargs['process_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.kwargs['process_pk']})


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


@login_required
@require_POST
def contract_ai_assistant(request, pk):
    organization = get_user_organization(request.user)
    contract = get_object_or_404(scope_queryset_for_organization(Contract.objects.all(), organization), id=pk)
    if not can_access_contract_action(request.user, contract, ContractAction.COMMENT):
        return HttpResponseForbidden('You do not have access to this contract organization.')

    prompt = ''
    content_type = (request.content_type or '').lower()
    if 'application/json' in content_type:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            prompt = (payload.get('prompt') or '').strip()
        except (ValueError, UnicodeDecodeError):
            prompt = ''
    else:
        prompt = (request.POST.get('prompt') or '').strip()

    if not prompt:
        prompt = 'Give me a risk and renewal summary for this contract.'

    ai_response = _build_contract_ai_response(contract, prompt)
    log_action(
        request.user,
        AuditLog.Action.EXPORT,
        'ContractAI',
        object_id=contract.id,
        object_repr=contract.title,
        changes={
            'organization_id': contract.organization_id,
            'event': 'contract_ai_assistant_invoked',
            'prompt_length': len(prompt),
            'mode': ai_response.get('mode'),
        },
        request=request,
    )
    return JsonResponse({'ok': True, 'response': ai_response})


class WorkflowStepUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = WorkflowStep
    fields = ['status', 'assigned_to', 'due_date']
    template_name = 'contracts/workflow_step_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.workflow.pk})


class WorkflowStepCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        step = get_object_or_404(WorkflowStep, pk=pk)
        step.status = 'COMPLETED'
        step.save()
        return redirect('contracts:workflow_detail', pk=step.workflow.pk)


class AddWorkflowStepView(LoginRequiredMixin, View):
    def post(self, request, pk):
        workflow = get_object_or_404(Workflow, pk=pk)
        form = WorkflowForm(request.POST)
        if form.is_valid():
            step = form.save(commit=False)
            step.workflow = workflow
            step.save()
        return redirect('contracts:workflow_detail', pk=workflow.pk)


class AddWorkflowTemplateStepView(LoginRequiredMixin, View):
    def post(self, request, pk):
        template = get_object_or_404(WorkflowTemplate, pk=pk)
        return redirect('contracts:workflow_template_detail', pk=template.pk)


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


def workflow_dashboard(request):
    workflows = Workflow.objects.all()
    context = {'workflows': workflows}
    return render(request, 'contracts/workflow_dashboard.html', context)


def toggle_dd_item(request, pk):
    task = get_object_or_404(DueDiligenceTask, pk=pk)
    if task.status == 'COMPLETED':
        task.status = 'PENDING'
    else:
        task.status = 'COMPLETED'
    task.save()
    return redirect('contracts:due_diligence_detail', pk=task.process.pk)


def profile(request):
    profile_obj = get_or_create_profile(request.user) if request.user.is_authenticated else None
    form = UserProfileForm(instance=profile_obj) if profile_obj else None
    return render(request, 'profile.html', {'form': form, 'profile': profile_obj})


@login_required
def workflow_create(request):
    if request.method == 'POST':
        form = WorkflowForm(request.POST)
        if form.is_valid():
            workflow = form.save(commit=False)
            if workflow.contract and not can_access_contract_action(request.user, workflow.contract, ContractAction.EDIT):
                return HttpResponseForbidden('You do not have permission to create workflows for this contract.')
            workflow.created_by = request.user
            workflow.save()
            return redirect('contracts:workflow_detail', pk=workflow.pk)
    else:
        form = WorkflowForm()
    return render(request, 'contracts/workflow_form.html', {'form': form})


@login_required
def workflow_detail(request, pk):
    workflow = get_object_or_404(Workflow, pk=pk)
    if workflow.contract and not can_access_contract_action(request.user, workflow.contract, ContractAction.COMMENT):
        return HttpResponseForbidden('You do not have access to this contract workflow.')
    steps = WorkflowStep.objects.filter(workflow=workflow).order_by('order')
    return render(request, 'contracts/workflow_detail.html', {'workflow': workflow, 'steps': steps})


@login_required
def update_workflow_step(request, pk):
    step = get_object_or_404(WorkflowStep, pk=pk)
    linked_contract = step.workflow.contract
    if linked_contract and not can_access_contract_action(request.user, linked_contract, ContractAction.EDIT):
        return HttpResponseForbidden('You do not have permission to update this contract workflow step.')
    if request.method == 'POST':
        new_status = request.POST.get('status', step.status)
        step.status = new_status
        if new_status == 'COMPLETED':
            step.completed_at = timezone.now()
        step.save()
        return redirect('contracts:workflow_detail', pk=step.workflow.pk)
    return redirect('contracts:workflow_detail', pk=step.workflow.pk)


def workflow_template_create(request):
    if request.method == 'POST':
        form = WorkflowTemplateForm(request.POST)
        if form.is_valid():
            template = form.save()
            return redirect('contracts:workflow_template_detail', pk=template.pk)
    else:
        form = WorkflowTemplateForm()
    return render(request, 'contracts/workflow_template_form.html', {'form': form})


def workflow_template_detail(request, pk):
    template = get_object_or_404(WorkflowTemplate, pk=pk)
    steps = WorkflowTemplateStep.objects.filter(template=template).order_by('order')
    return render(request, 'contracts/workflow_template_detail.html', {'workflow_template': template, 'steps': steps})


def workflow_template_list(request):
    templates = WorkflowTemplate.objects.all()
    return render(request, 'contracts/workflow_template_list.html', {'workflow_templates': templates})


# ==================== DASHBOARD VIEW ====================

def dashboard(request):
    today = date.today()
    now = timezone.now()
    thirty_days = today + timedelta(days=30)
    seven_days = today + timedelta(days=7)

    org = get_user_organization(request.user)
    contracts_qs = scope_queryset_for_organization(Contract.objects.all(), org)
    clients_qs = scope_queryset_for_organization(Client.objects.all(), org)
    matters_qs = scope_queryset_for_organization(Matter.objects.all(), org)
    if org:
        legal_tasks_qs = LegalTask.objects.filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        )
        risks_qs = RiskLog.objects.filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        )
        deadlines_qs = Deadline.objects.filter(
            Q(contract__organization=org) | Q(matter__organization=org)
        )
    else:
        legal_tasks_qs = LegalTask.objects.none()
        risks_qs = RiskLog.objects.none()
        deadlines_qs = Deadline.objects.none()
    workflows_qs = scope_queryset_for_organization(Workflow.objects.all(), org)
    invoices_qs = scope_queryset_for_organization(Invoice.objects.all(), org)
    documents_qs = scope_queryset_for_organization(Document.objects.all(), org)
    approvals_qs = scope_queryset_for_organization(ApprovalRequest.objects.all(), org)
    signatures_qs = scope_queryset_for_organization(SignatureRequest.objects.all(), org)
    dsars_qs = scope_queryset_for_organization(DSARRequest.objects.all(), org)
    time_entries_qs = scope_queryset_for_organization(TimeEntry.objects.all(), org)
    trust_accounts_qs = scope_queryset_for_organization(TrustAccount.objects.all(), org)

    def _safe(fn, default=0):
        try:
            return fn()
        except Exception:
            return default

    total_contracts = _safe(lambda: contracts_qs.count())
    active_contracts = _safe(lambda: contracts_qs.filter(status='ACTIVE').count())
    draft_contracts = _safe(lambda: contracts_qs.filter(status='DRAFT').count())
    pending_contracts = _safe(lambda: contracts_qs.filter(status='PENDING').count())
    expiring_soon_count = _safe(lambda: contracts_qs.filter(
        end_date__lte=thirty_days, end_date__gte=today, status='ACTIVE').count())

    total_clients = _safe(lambda: clients_qs.count())
    active_matters = _safe(lambda: matters_qs.filter(status='ACTIVE').count())
    total_matters = _safe(lambda: matters_qs.count())

    pending_tasks = _safe(lambda: legal_tasks_qs.filter(status='PENDING').count())
    active_workflows = _safe(lambda: workflows_qs.filter(status='ACTIVE').count())
    risk_count = _safe(lambda: risks_qs.filter(risk_level__in=['HIGH', 'CRITICAL']).count())

    overdue_deadlines = _safe(lambda: deadlines_qs.filter(is_completed=False, due_date__lt=today).count())
    upcoming_deadline_count = _safe(lambda: deadlines_qs.filter(
        is_completed=False, due_date__gte=today, due_date__lte=seven_days).count())

    outstanding_invoices = _safe(lambda: invoices_qs.filter(
        status__in=['SENT', 'OVERDUE']).aggregate(
        total=Sum('total_amount'))['total'] or Decimal('0'), Decimal('0'))
    overdue_invoices = _safe(lambda: invoices_qs.filter(status='OVERDUE').aggregate(
        total=Sum('total_amount'))['total'] or Decimal('0'), Decimal('0'))
    paid_this_month = _safe(lambda: invoices_qs.filter(
        status='PAID', updated_at__month=today.month, updated_at__year=today.year).aggregate(
        total=Sum('total_amount'))['total'] or Decimal('0'), Decimal('0'))

    total_documents = _safe(lambda: documents_qs.count())

    pending_approvals = _safe(lambda: approvals_qs.filter(status='PENDING').count())
    pending_signatures = _safe(lambda: signatures_qs.filter(status='PENDING').count())
    open_dsars = _safe(lambda: dsars_qs.filter(status__in=['RECEIVED', 'IN_PROGRESS']).count())

    unread_notifications = 0
    if request.user.is_authenticated:
        unread_notifications = _safe(lambda: Notification.objects.filter(
            recipient=request.user, is_read=False).count())

    recent_contracts = _safe(lambda: list(contracts_qs.order_by('-created_at')[:6]), [])
    upcoming_deadlines = _safe(lambda: list(deadlines_qs.filter(
        is_completed=False, due_date__gte=today).order_by('due_date')[:6]), [])
    upcoming_tasks = _safe(lambda: list(legal_tasks_qs.filter(
        status='PENDING', due_date__gte=today).order_by('due_date')[:5]), [])
    recent_audit = _safe(lambda: list(AuditLog.objects.select_related('user').order_by('-timestamp')[:8]), [])

    contract_status_data = []
    for status_code, status_label in [('ACTIVE', 'Active'), ('DRAFT', 'Draft'), ('PENDING', 'In Review'), ('EXPIRED', 'Expired'), ('TERMINATED', 'Terminated')]:
        cnt = _safe(lambda sc=status_code: contracts_qs.filter(status=sc).count())
        if cnt > 0:
            contract_status_data.append({'label': status_label, 'count': cnt})

    billable_this_month = _safe(lambda: time_entries_qs.filter(
        date__month=today.month, date__year=today.year).aggregate(
        total=Sum('hours'))['total'] or Decimal('0'), Decimal('0'))

    trust_balance = _safe(lambda: trust_accounts_qs.aggregate(
        total=Sum('balance'))['total'] or Decimal('0'), Decimal('0'))

    context = {
        'total_contracts': total_contracts,
        'active_contracts': active_contracts,
        'draft_contracts': draft_contracts,
        'pending_contracts': pending_contracts,
        'expiring_soon_count': expiring_soon_count,
        'total_clients': total_clients,
        'active_matters': active_matters,
        'total_matters': total_matters,
        'pending_tasks': pending_tasks,
        'active_workflows': active_workflows,
        'risk_count': risk_count,
        'overdue_deadlines': overdue_deadlines,
        'upcoming_deadline_count': upcoming_deadline_count,
        'outstanding_invoices': outstanding_invoices,
        'overdue_invoices': overdue_invoices,
        'paid_this_month': paid_this_month,
        'total_documents': total_documents,
        'pending_approvals': pending_approvals,
        'pending_signatures': pending_signatures,
        'open_dsars': open_dsars,
        'unread_notifications': unread_notifications,
        'recent_contracts': recent_contracts,
        'upcoming_deadlines': upcoming_deadlines,
        'upcoming_tasks': upcoming_tasks,
        'recent_audit': recent_audit,
        'contract_status_data': contract_status_data,
        'billable_this_month': billable_this_month,
        'trust_balance': trust_balance,
        'today': today,
        'FEATURE_REDESIGN': is_feature_redesign_enabled(),
    }
    return render(request, 'dashboard.html', context)


class CounterpartyListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Counterparty
    template_name = 'contracts/counterparty_list.html'
    context_object_name = 'counterparties'

    def get_queryset(self):
        qs = Counterparty.objects.all()
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(jurisdiction__icontains=q))
        return qs


class CounterpartyCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Counterparty
    form_class = CounterpartyForm
    template_name = 'contracts/counterparty_form.html'
    success_url = reverse_lazy('contracts:counterparty_list')


class CounterpartyDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Counterparty
    template_name = 'contracts/counterparty_detail.html'


class CounterpartyUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Counterparty
    form_class = CounterpartyForm
    template_name = 'contracts/counterparty_form.html'
    success_url = reverse_lazy('contracts:counterparty_list')


class ClauseCategoryListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ClauseCategory
    template_name = 'contracts/clause_category_list.html'
    context_object_name = 'categories'


class ClauseCategoryCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ClauseCategory
    form_class = ClauseCategoryForm
    template_name = 'contracts/clause_category_form.html'
    success_url = reverse_lazy('contracts:clause_category_list')


class ClauseCategoryUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ClauseCategory
    form_class = ClauseCategoryForm
    template_name = 'contracts/clause_category_form.html'
    success_url = reverse_lazy('contracts:clause_category_list')


class ClauseTemplateListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ClauseTemplate
    template_name = 'contracts/clause_template_list.html'
    context_object_name = 'clauses'

    def get_queryset(self):
        qs = ClauseTemplate.objects.select_related('category').all()
        cat = self.request.GET.get('category')
        scope = self.request.GET.get('scope')
        q = self.request.GET.get('q', '')
        if cat:
            qs = qs.filter(category_id=cat)
        if scope:
            qs = qs.filter(jurisdiction_scope=scope)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q) | Q(tags__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = ClauseCategory.objects.all()
        return ctx


class ClauseTemplateCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ClauseTemplate
    form_class = ClauseTemplateForm
    template_name = 'contracts/clause_template_form.html'
    success_url = reverse_lazy('contracts:clause_template_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ClauseTemplateDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = ClauseTemplate
    template_name = 'contracts/clause_template_detail.html'


class ClauseTemplateUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ClauseTemplate
    form_class = ClauseTemplateForm
    template_name = 'contracts/clause_template_form.html'
    success_url = reverse_lazy('contracts:clause_template_list')


class EthicalWallListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = EthicalWall
    template_name = 'contracts/ethical_wall_list.html'
    context_object_name = 'walls'


class EthicalWallCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = EthicalWall
    form_class = EthicalWallForm
    template_name = 'contracts/ethical_wall_form.html'
    success_url = reverse_lazy('contracts:ethical_wall_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class EthicalWallUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = EthicalWall
    form_class = EthicalWallForm
    template_name = 'contracts/ethical_wall_form.html'
    success_url = reverse_lazy('contracts:ethical_wall_list')


class SignatureRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = SignatureRequest
    template_name = 'contracts/signature_request_list.html'
    context_object_name = 'signatures'

    def get_queryset(self):
        qs = SignatureRequest.objects.select_related('contract').all()
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class SignatureRequestCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = SignatureRequest
    form_class = SignatureRequestForm
    template_name = 'contracts/signature_request_form.html'
    success_url = reverse_lazy('contracts:signature_request_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class SignatureRequestDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = SignatureRequest
    template_name = 'contracts/signature_request_detail.html'


class SignatureRequestUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = SignatureRequest
    form_class = SignatureRequestForm
    template_name = 'contracts/signature_request_form.html'
    success_url = reverse_lazy('contracts:signature_request_list')


class DataInventoryListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = DataInventoryRecord
    template_name = 'contracts/data_inventory_list.html'
    context_object_name = 'records'


class DataInventoryCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = DataInventoryRecord
    form_class = DataInventoryForm
    template_name = 'contracts/data_inventory_form.html'
    success_url = reverse_lazy('contracts:data_inventory_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class DataInventoryDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = DataInventoryRecord
    template_name = 'contracts/data_inventory_detail.html'


class DataInventoryUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = DataInventoryRecord
    form_class = DataInventoryForm
    template_name = 'contracts/data_inventory_form.html'
    success_url = reverse_lazy('contracts:data_inventory_list')


class DSARRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = DSARRequest
    template_name = 'contracts/dsar_list.html'
    context_object_name = 'requests'

    def get_queryset(self):
        qs = DSARRequest.objects.all().order_by('-received_date')
        status = self.request.GET.get('status')
        rtype = self.request.GET.get('type')
        if status:
            qs = qs.filter(status=status)
        if rtype:
            qs = qs.filter(request_type=rtype)
        return qs


class DSARRequestCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = DSARRequest
    form_class = DSARRequestForm
    template_name = 'contracts/dsar_form.html'
    success_url = reverse_lazy('contracts:dsar_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class DSARRequestDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = DSARRequest
    template_name = 'contracts/dsar_detail.html'


class DSARRequestUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = DSARRequest
    form_class = DSARRequestForm
    template_name = 'contracts/dsar_form.html'
    success_url = reverse_lazy('contracts:dsar_list')


class SubprocessorListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Subprocessor
    template_name = 'contracts/subprocessor_list.html'
    context_object_name = 'subprocessors'


class SubprocessorCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = Subprocessor
    form_class = SubprocessorForm
    template_name = 'contracts/subprocessor_form.html'
    success_url = reverse_lazy('contracts:subprocessor_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class SubprocessorDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Subprocessor
    template_name = 'contracts/subprocessor_detail.html'


class SubprocessorUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Subprocessor
    form_class = SubprocessorForm
    template_name = 'contracts/subprocessor_form.html'
    success_url = reverse_lazy('contracts:subprocessor_list')


class TransferRecordListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = TransferRecord
    template_name = 'contracts/transfer_record_list.html'
    context_object_name = 'transfers'


class TransferRecordCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = TransferRecord
    form_class = TransferRecordForm
    template_name = 'contracts/transfer_record_form.html'
    success_url = reverse_lazy('contracts:transfer_record_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class TransferRecordUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = TransferRecord
    form_class = TransferRecordForm
    template_name = 'contracts/transfer_record_form.html'
    success_url = reverse_lazy('contracts:transfer_record_list')


class RetentionPolicyListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = RetentionPolicy
    template_name = 'contracts/retention_policy_list.html'
    context_object_name = 'policies'


class RetentionPolicyCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = RetentionPolicy
    form_class = RetentionPolicyForm
    template_name = 'contracts/retention_policy_form.html'
    success_url = reverse_lazy('contracts:retention_policy_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class RetentionPolicyUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = RetentionPolicy
    form_class = RetentionPolicyForm
    template_name = 'contracts/retention_policy_form.html'
    success_url = reverse_lazy('contracts:retention_policy_list')


class LegalHoldListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = LegalHold
    template_name = 'contracts/legal_hold_list.html'
    context_object_name = 'holds'


class LegalHoldCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = LegalHold
    form_class = LegalHoldForm
    template_name = 'contracts/legal_hold_form.html'
    success_url = reverse_lazy('contracts:legal_hold_list')

    def form_valid(self, form):
        form.instance.issued_by = self.request.user
        return super().form_valid(form)


class LegalHoldDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = LegalHold
    template_name = 'contracts/legal_hold_detail.html'


class LegalHoldUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = LegalHold
    form_class = LegalHoldForm
    template_name = 'contracts/legal_hold_form.html'
    success_url = reverse_lazy('contracts:legal_hold_list')


class ApprovalRuleListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ApprovalRule
    template_name = 'contracts/approval_rule_list.html'
    context_object_name = 'rules'


class ApprovalRuleCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ApprovalRule
    form_class = ApprovalRuleForm
    template_name = 'contracts/approval_rule_form.html'
    success_url = reverse_lazy('contracts:approval_rule_list')


class ApprovalRuleUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ApprovalRule
    form_class = ApprovalRuleForm
    template_name = 'contracts/approval_rule_form.html'
    success_url = reverse_lazy('contracts:approval_rule_list')


class ApprovalRequestListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = ApprovalRequest
    template_name = 'contracts/approval_request_list.html'
    context_object_name = 'approvals'

    def get_queryset(self):
        qs = ApprovalRequest.objects.select_related('contract', 'assigned_to').all().order_by('-created_at')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class ApprovalRequestCreateView(TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ApprovalRequest
    form_class = ApprovalRequestForm
    template_name = 'contracts/approval_request_form.html'
    success_url = reverse_lazy('contracts:approval_request_list')


class ApprovalRequestUpdateView(TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ApprovalRequest
    form_class = ApprovalRequestForm
    template_name = 'contracts/approval_request_form.html'
    success_url = reverse_lazy('contracts:approval_request_list')


@login_required
def privacy_dashboard(request):
    data_inventory_count = DataInventoryRecord.objects.count()
    dsar_pending = DSARRequest.objects.filter(status__in=['RECEIVED', 'VERIFIED', 'IN_PROGRESS']).count()
    dsar_overdue = DSARRequest.objects.filter(
        status__in=['RECEIVED', 'VERIFIED', 'IN_PROGRESS'],
        due_date__lt=date.today()
    ).count()
    subprocessor_count = Subprocessor.objects.filter(is_active=True).count()
    transfer_count = TransferRecord.objects.filter(is_active=True).count()
    retention_count = RetentionPolicy.objects.filter(is_active=True).count()
    legal_hold_count = LegalHold.objects.filter(status='ACTIVE').count()
    recent_dsars = DSARRequest.objects.order_by('-received_date')[:5]
    context = {
        'data_inventory_count': data_inventory_count,
        'dsar_pending': dsar_pending,
        'dsar_overdue': dsar_overdue,
        'subprocessor_count': subprocessor_count,
        'transfer_count': transfer_count,
        'retention_count': retention_count,
        'legal_hold_count': legal_hold_count,
        'recent_dsars': recent_dsars,
    }
    return render(request, 'contracts/privacy_dashboard.html', context)


@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    results = {}
    if q:
        results['contracts'] = Contract.objects.filter(
            Q(title__icontains=q) | Q(counterparty__icontains=q) | Q(content__icontains=q)
        )[:10]
        results['clients'] = Client.objects.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(industry__icontains=q)
        )[:10]
        results['matters'] = Matter.objects.filter(
            Q(title__icontains=q) | Q(matter_number__icontains=q) | Q(description__icontains=q)
        )[:10]
        results['documents'] = Document.objects.filter(
            Q(title__icontains=q) | Q(description__icontains=q) | Q(tags__icontains=q)
        )[:10]
        results['clauses'] = ClauseTemplate.objects.filter(
            Q(title__icontains=q) | Q(content__icontains=q) | Q(tags__icontains=q)
        )[:10]
        results['counterparties'] = Counterparty.objects.filter(
            Q(name__icontains=q) | Q(jurisdiction__icontains=q)
        )[:10]
    return render(request, 'contracts/search_results.html', {'q': q, 'results': results})
