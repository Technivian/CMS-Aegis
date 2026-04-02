from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, Q, Avg, F
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from datetime import datetime, timedelta, date
from decimal import Decimal
import json
import logging

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
)
from .models import (
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


# ==================== CLIENT VIEWS ====================

class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'contracts/client_list.html'
    context_object_name = 'clients'
    paginate_by = 25

    def get_queryset(self):
        qs = Client.objects.all()
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
        ctx['total_clients'] = Client.objects.count()
        ctx['active_clients'] = Client.objects.filter(status='ACTIVE').count()
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class ClientDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'contracts/client_detail.html'
    context_object_name = 'client'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['matters'] = self.object.matters.all()[:10]
        ctx['contracts'] = self.object.contracts.all()[:10]
        ctx['invoices'] = self.object.invoices.all()[:10]
        ctx['documents'] = self.object.documents.all()[:10]
        return ctx


class ClientCreateView(LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'contracts/client_form.html'
    success_url = reverse_lazy('contracts:client_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Client', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Client "{self.object.name}" created successfully.')
        return response


class ClientUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'contracts/client_form.html'
    success_url = reverse_lazy('contracts:client_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Client', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Client "{self.object.name}" updated successfully.')
        return response


# ==================== MATTER VIEWS ====================

class MatterListView(LoginRequiredMixin, ListView):
    model = Matter
    template_name = 'contracts/matter_list.html'
    context_object_name = 'matters'
    paginate_by = 25

    def get_queryset(self):
        qs = Matter.objects.select_related('client', 'responsible_attorney')
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
        ctx['total_matters'] = Matter.objects.count()
        ctx['active_matters'] = Matter.objects.filter(status='ACTIVE').count()
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class MatterDetailView(LoginRequiredMixin, DetailView):
    model = Matter
    template_name = 'contracts/matter_detail.html'
    context_object_name = 'matter'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['contracts'] = self.object.contracts.all()
        ctx['documents'] = self.object.documents.all()[:10]
        ctx['time_entries'] = self.object.time_entries.all()[:10]
        ctx['tasks'] = self.object.tasks.all()[:10]
        ctx['deadlines'] = self.object.deadlines.filter(is_completed=False)[:10]
        ctx['risks'] = self.object.risks.all()[:10]
        return ctx


class MatterCreateView(LoginRequiredMixin, CreateView):
    model = Matter
    form_class = MatterForm
    template_name = 'contracts/matter_form.html'

    def get_success_url(self):
        return reverse('contracts:matter_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Matter', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Matter "{self.object.title}" created.')
        return response


class MatterUpdateView(LoginRequiredMixin, UpdateView):
    model = Matter
    form_class = MatterForm
    template_name = 'contracts/matter_form.html'

    def get_success_url(self):
        return reverse('contracts:matter_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Matter', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Matter "{self.object.title}" updated.')
        return response


# ==================== DOCUMENT VIEWS ====================

class DocumentListView(LoginRequiredMixin, ListView):
    model = Document
    template_name = 'contracts/document_list.html'
    context_object_name = 'documents'
    paginate_by = 25

    def get_queryset(self):
        qs = Document.objects.select_related('contract', 'matter', 'client', 'uploaded_by')
        q = self.request.GET.get('q')
        doc_type = self.request.GET.get('type')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(tags__icontains=q))
        if doc_type:
            qs = qs.filter(document_type=doc_type)
        return qs.order_by('-created_at')


class DocumentDetailView(LoginRequiredMixin, DetailView):
    model = Document
    template_name = 'contracts/document_detail.html'
    context_object_name = 'document'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['versions'] = Document.objects.filter(parent_document=self.object).order_by('-version')
        return ctx


class DocumentCreateView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = 'contracts/document_form.html'
    success_url = reverse_lazy('contracts:document_list')

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Document', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Document "{self.object.title}" uploaded.')
        return response


class DocumentUpdateView(LoginRequiredMixin, UpdateView):
    model = Document
    form_class = DocumentForm
    template_name = 'contracts/document_form.html'
    success_url = reverse_lazy('contracts:document_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Document', self.object.id, str(self.object), request=self.request)
        return response


# ==================== TIME ENTRY VIEWS ====================

class TimeEntryListView(LoginRequiredMixin, ListView):
    model = TimeEntry
    template_name = 'contracts/time_entry_list.html'
    context_object_name = 'time_entries'
    paginate_by = 25

    def get_queryset(self):
        qs = TimeEntry.objects.select_related('matter', 'matter__client', 'user')
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
        my_entries = TimeEntry.objects.filter(user=self.request.user)
        ctx['today_hours'] = my_entries.filter(date=today).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        ctx['week_hours'] = my_entries.filter(date__gte=week_start).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        ctx['month_hours'] = my_entries.filter(date__month=today.month, date__year=today.year).aggregate(total=Sum('hours'))['total'] or Decimal('0')
        return ctx


class TimeEntryCreateView(LoginRequiredMixin, CreateView):
    model = TimeEntry
    form_class = TimeEntryForm
    template_name = 'contracts/time_entry_form.html'
    success_url = reverse_lazy('contracts:time_entry_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'TimeEntry', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, 'Time entry recorded.')
        return response


class TimeEntryUpdateView(LoginRequiredMixin, UpdateView):
    model = TimeEntry
    form_class = TimeEntryForm
    template_name = 'contracts/time_entry_form.html'
    success_url = reverse_lazy('contracts:time_entry_list')


# ==================== INVOICE VIEWS ====================

class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'contracts/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 25

    def get_queryset(self):
        qs = Invoice.objects.select_related('client', 'matter')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-issue_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_outstanding'] = Invoice.objects.filter(status__in=['SENT', 'OVERDUE']).aggregate(
            total=Sum('total_amount'))['total'] or Decimal('0')
        ctx['total_paid'] = Invoice.objects.filter(status='PAID').aggregate(
            total=Sum('total_amount'))['total'] or Decimal('0')
        ctx['overdue_count'] = Invoice.objects.filter(status='OVERDUE').count()
        overdue_sent = Invoice.objects.filter(status='SENT', due_date__lt=date.today())
        overdue_sent.update(status='OVERDUE')
        return ctx


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'contracts/invoice_detail.html'
    context_object_name = 'invoice'


class InvoiceCreateView(LoginRequiredMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'contracts/invoice_form.html'

    def get_success_url(self):
        return reverse('contracts:invoice_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Invoice', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Invoice #{self.object.invoice_number} created.')
        return response


class InvoiceUpdateView(LoginRequiredMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'contracts/invoice_form.html'

    def get_success_url(self):
        return reverse('contracts:invoice_detail', kwargs={'pk': self.object.pk})


# ==================== TRUST ACCOUNT VIEWS ====================

class TrustAccountListView(LoginRequiredMixin, ListView):
    model = TrustAccount
    template_name = 'contracts/trust_account_list.html'
    context_object_name = 'accounts'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_balance'] = TrustAccount.objects.aggregate(total=Sum('balance'))['total'] or Decimal('0')
        return ctx


class TrustAccountDetailView(LoginRequiredMixin, DetailView):
    model = TrustAccount
    template_name = 'contracts/trust_account_detail.html'
    context_object_name = 'account'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['transactions'] = self.object.transactions.all()[:20]
        ctx['transaction_form'] = TrustTransactionForm()
        return ctx


class TrustAccountCreateView(LoginRequiredMixin, CreateView):
    model = TrustAccount
    form_class = TrustAccountForm
    template_name = 'contracts/trust_account_form.html'
    success_url = reverse_lazy('contracts:trust_account_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'TrustAccount', self.object.id, str(self.object), request=self.request)
        return response


class AddTrustTransactionView(LoginRequiredMixin, CreateView):
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

class DeadlineListView(LoginRequiredMixin, ListView):
    model = Deadline
    template_name = 'contracts/deadline_list.html'
    context_object_name = 'deadlines'
    paginate_by = 25

    def get_queryset(self):
        qs = Deadline.objects.select_related('matter', 'contract', 'assigned_to')
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
        ctx['overdue_count'] = Deadline.objects.filter(is_completed=False, due_date__lt=date.today()).count()
        ctx['upcoming_count'] = Deadline.objects.filter(is_completed=False, due_date__gte=date.today()).count()
        ctx['show'] = self.request.GET.get('show', 'upcoming')
        return ctx


class DeadlineCreateView(LoginRequiredMixin, CreateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('contracts:deadline_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Deadline', self.object.id, str(self.object), request=self.request)
        return response


class DeadlineUpdateView(LoginRequiredMixin, UpdateView):
    model = Deadline
    form_class = DeadlineForm
    template_name = 'contracts/deadline_form.html'
    success_url = reverse_lazy('contracts:deadline_list')


@login_required
@require_POST
def deadline_complete(request, pk):
    deadline = get_object_or_404(Deadline, pk=pk)
    deadline.is_completed = True
    deadline.completed_at = timezone.now()
    deadline.completed_by = request.user
    deadline.save()
    log_action(request.user, 'UPDATE', 'Deadline', deadline.id, str(deadline), request=request)
    messages.success(request, f'Deadline "{deadline.title}" marked as complete.')
    return redirect('contracts:deadline_list')


# ==================== CONFLICT CHECK VIEWS ====================

class ConflictCheckListView(LoginRequiredMixin, ListView):
    model = ConflictCheck
    template_name = 'contracts/conflict_check_list.html'
    context_object_name = 'conflict_checks'
    paginate_by = 25


class ConflictCheckCreateView(LoginRequiredMixin, CreateView):
    model = ConflictCheck
    form_class = ConflictCheckForm
    template_name = 'contracts/conflict_check_form.html'
    success_url = reverse_lazy('contracts:conflict_check_list')

    def form_valid(self, form):
        form.instance.checked_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'ConflictCheck', self.object.id, str(self.object), request=self.request)
        return response


class ConflictCheckUpdateView(LoginRequiredMixin, UpdateView):
    model = ConflictCheck
    form_class = ConflictCheckForm
    template_name = 'contracts/conflict_check_form.html'
    success_url = reverse_lazy('contracts:conflict_check_list')


# ==================== AUDIT LOG VIEW ====================

class AuditLogListView(LoginRequiredMixin, ListView):
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


# ==================== REPORTS VIEW ====================

@login_required
def reports_dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    total_contracts = Contract.objects.count()
    active_contracts = Contract.objects.filter(status='ACTIVE').count()
    total_contract_value = Contract.objects.filter(value__isnull=False).aggregate(total=Sum('value'))['total'] or Decimal('0')

    total_clients = Client.objects.count()
    active_clients = Client.objects.filter(status='ACTIVE').count()

    total_matters = Matter.objects.count()
    active_matters = Matter.objects.filter(status='ACTIVE').count()

    monthly_hours = TimeEntry.objects.filter(
        date__gte=month_start
    ).aggregate(total=Sum('hours'))['total'] or Decimal('0')

    yearly_revenue = Invoice.objects.filter(
        status='PAID', issue_date__gte=year_start
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    outstanding = Invoice.objects.filter(
        status__in=['SENT', 'OVERDUE']
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    overdue_deadlines = Deadline.objects.filter(is_completed=False, due_date__lt=today).count()
    upcoming_deadlines = Deadline.objects.filter(
        is_completed=False, due_date__gte=today, due_date__lte=today + timedelta(days=7)
    ).count()

    high_risks = RiskLog.objects.filter(risk_level__in=['HIGH', 'CRITICAL']).count()

    monthly_billing = []
    for i in range(6):
        m = today.replace(day=1) - timedelta(days=30 * i)
        month_total = Invoice.objects.filter(
            issue_date__month=m.month, issue_date__year=m.year
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        monthly_billing.append({
            'month': m.strftime('%b %Y'),
            'total': float(month_total)
        })
    monthly_billing.reverse()

    practice_areas = Matter.objects.filter(status='ACTIVE').values('practice_area').annotate(
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

class ContractListView(LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/contract_list.html'
    context_object_name = 'contracts'
    paginate_by = 25

    def get_queryset(self):
        qs = Contract.objects.select_related('client', 'matter', 'created_by')
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        contract_type = self.request.GET.get('type')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(counterparty__icontains=q))
        if status:
            qs = qs.filter(status=status)
        if contract_type:
            qs = qs.filter(contract_type=contract_type)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['FEATURE_REDESIGN'] = is_feature_redesign_enabled()
        context['search_query'] = self.request.GET.get('q', '')
        context['total_contracts'] = Contract.objects.count()
        context['active_contracts'] = Contract.objects.filter(status='ACTIVE').count()
        context['expiring_soon'] = Contract.objects.filter(
            end_date__lte=date.today() + timedelta(days=30),
            end_date__gte=date.today(),
            status='ACTIVE'
        ).count()

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


class ContractDetailView(LoginRequiredMixin, DetailView):
    model = Contract
    template_name = 'contracts/contract_detail.html'
    context_object_name = 'contract'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['documents'] = self.object.documents.all()[:10]
        ctx['deadlines'] = self.object.deadlines.filter(is_completed=False)[:5]
        ctx['negotiation_threads'] = self.object.negotiation_threads.all()[:10]
        return ctx


class ContractCreateView(LoginRequiredMixin, CreateView):
    model = Contract
    form_class = ContractForm
    template_name = 'contracts/contract_form.html'
    success_url = reverse_lazy('contracts:contract_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'CREATE', 'Contract', self.object.id, str(self.object), request=self.request)
        messages.success(self.request, f'Contract "{self.object.title}" created.')
        return response


class ContractUpdateView(LoginRequiredMixin, UpdateView):
    model = Contract
    form_class = ContractForm
    template_name = 'contracts/contract_form.html'
    success_url = reverse_lazy('contracts:contract_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'UPDATE', 'Contract', self.object.id, str(self.object), request=self.request)
        return response


# ==================== WORKFLOW VIEWS ====================

class WorkflowTemplateListView(LoginRequiredMixin, ListView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_list.html'
    context_object_name = 'workflow_templates'


class WorkflowTemplateDetailView(LoginRequiredMixin, DetailView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_detail.html'
    context_object_name = 'workflow_template'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['steps'] = WorkflowTemplateStep.objects.filter(template=self.object).order_by('order')
        return context


class WorkflowTemplateCreateView(LoginRequiredMixin, CreateView):
    model = WorkflowTemplate
    form_class = WorkflowTemplateForm
    template_name = 'contracts/workflow_template_form.html'
    success_url = reverse_lazy('contracts:workflow_template_list')


class WorkflowTemplateUpdateView(LoginRequiredMixin, UpdateView):
    model = WorkflowTemplate
    form_class = WorkflowTemplateForm
    template_name = 'contracts/workflow_template_form.html'
    success_url = reverse_lazy('contracts:workflow_template_list')


class WorkflowListView(LoginRequiredMixin, ListView):
    model = Workflow
    template_name = 'contracts/workflow_template_list.html'
    context_object_name = 'workflows'

    def get_queryset(self):
        queryset = Workflow.objects.all()
        contract_pk = self.request.GET.get('contract_pk')
        if contract_pk:
            queryset = queryset.filter(contract=contract_pk)
        return queryset.order_by('-created_at')


class WorkflowDetailView(LoginRequiredMixin, DetailView):
    model = Workflow
    template_name = 'contracts/workflow_detail.html'
    context_object_name = 'workflow'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['steps'] = WorkflowStep.objects.filter(workflow=self.object).order_by('order')
        context['step_form'] = WorkflowForm()
        return context


class WorkflowCreateView(LoginRequiredMixin, CreateView):
    model = Workflow
    form_class = WorkflowForm
    template_name = 'contracts/workflow_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class WorkflowUpdateView(LoginRequiredMixin, UpdateView):
    model = Workflow
    form_class = WorkflowForm
    template_name = 'contracts/workflow_form.html'

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.pk})


# ==================== LEGAL TASK VIEWS ====================

class LegalTaskKanbanView(LoginRequiredMixin, ListView):
    model = LegalTask
    template_name = 'contracts/legal_task_board.html'
    context_object_name = 'legal_tasks'


class LegalTaskCreateView(LoginRequiredMixin, CreateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/legal_task_form.html'
    success_url = reverse_lazy('contracts:legal_task_kanban')


class LegalTaskUpdateView(LoginRequiredMixin, UpdateView):
    model = LegalTask
    form_class = LegalTaskForm
    template_name = 'contracts/legal_task_form.html'
    success_url = reverse_lazy('contracts:legal_task_kanban')


# ==================== TRADEMARK VIEWS ====================

class TrademarkRequestListView(LoginRequiredMixin, ListView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_list.html'
    context_object_name = 'trademark_requests'


class TrademarkRequestDetailView(LoginRequiredMixin, DetailView):
    model = TrademarkRequest
    template_name = 'contracts/trademark_request_detail.html'
    context_object_name = 'trademark_request'


class TrademarkRequestCreateView(LoginRequiredMixin, CreateView):
    model = TrademarkRequest
    form_class = TrademarkRequestForm
    template_name = 'contracts/trademark_request_form.html'
    success_url = reverse_lazy('contracts:trademark_request_list')


class TrademarkRequestUpdateView(LoginRequiredMixin, UpdateView):
    model = TrademarkRequest
    form_class = TrademarkRequestForm
    template_name = 'contracts/trademark_request_form.html'
    success_url = reverse_lazy('contracts:trademark_request_list')


# ==================== RISK MANAGEMENT VIEWS ====================

class RiskLogListView(LoginRequiredMixin, ListView):
    model = RiskLog
    template_name = 'contracts/risk_log_list.html'
    context_object_name = 'risk_logs'


class RiskLogCreateView(LoginRequiredMixin, CreateView):
    model = RiskLog
    form_class = RiskLogForm
    template_name = 'contracts/risk_log_form.html'
    success_url = reverse_lazy('contracts:risk_log_list')


class RiskLogUpdateView(LoginRequiredMixin, UpdateView):
    model = RiskLog
    form_class = RiskLogForm
    template_name = 'contracts/risk_log_form.html'
    success_url = reverse_lazy('contracts:risk_log_list')


# ==================== COMPLIANCE VIEWS ====================

class ComplianceChecklistListView(LoginRequiredMixin, ListView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_list.html'
    context_object_name = 'compliance_checklists'


class ComplianceChecklistDetailView(LoginRequiredMixin, DetailView):
    model = ComplianceChecklist
    template_name = 'contracts/compliance_checklist_detail.html'
    context_object_name = 'compliance_checklist'


class ComplianceChecklistCreateView(LoginRequiredMixin, CreateView):
    model = ComplianceChecklist
    form_class = ComplianceChecklistForm
    template_name = 'contracts/compliance_checklist_form.html'
    success_url = reverse_lazy('contracts:compliance_checklist_list')


class ComplianceChecklistUpdateView(LoginRequiredMixin, UpdateView):
    model = ComplianceChecklist
    form_class = ComplianceChecklistForm
    template_name = 'contracts/compliance_checklist_form.html'
    success_url = reverse_lazy('contracts:compliance_checklist_list')


# ==================== DUE DILIGENCE VIEWS ====================

class DueDiligenceListView(LoginRequiredMixin, ListView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_list.html'
    context_object_name = 'processes'


class DueDiligenceCreateView(LoginRequiredMixin, CreateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')


class DueDiligenceDetailView(LoginRequiredMixin, DetailView):
    model = DueDiligenceProcess
    template_name = 'contracts/due_diligence_detail.html'
    context_object_name = 'process'


class DueDiligenceUpdateView(LoginRequiredMixin, UpdateView):
    model = DueDiligenceProcess
    form_class = DueDiligenceProcessForm
    template_name = 'contracts/due_diligence_form.html'
    success_url = reverse_lazy('contracts:due_diligence_list')


# ==================== BUDGET VIEWS ====================

class BudgetListView(LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'contracts/budget_list.html'
    context_object_name = 'budgets'


class BudgetCreateView(LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')


class BudgetDetailView(LoginRequiredMixin, DetailView):
    model = Budget
    template_name = 'contracts/budget_detail.html'
    context_object_name = 'budget'


class BudgetUpdateView(LoginRequiredMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'contracts/budget_form.html'
    success_url = reverse_lazy('contracts:budget_list')


# ==================== HELPER / REPOSITORY VIEWS ====================

class RepositoryView(LoginRequiredMixin, ListView):
    model = Contract
    template_name = 'contracts/repository.html'
    context_object_name = 'contracts'


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
        login(self.request, self.object)
        return response


# ==================== NEGOTIATION VIEWS ====================

class AddNegotiationNoteView(LoginRequiredMixin, CreateView):
    model = NegotiationThread
    fields = ['title', 'content']
    template_name = 'contracts/negotiation_note_form.html'

    def form_valid(self, form):
        form.instance.contract_id = self.kwargs['pk']
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:contract_detail', kwargs={'pk': self.kwargs['pk']})


# ==================== ACTION VIEWS ====================

class ToggleChecklistItemView(LoginRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(ChecklistItem, pk=pk)
        item.is_completed = not item.is_completed
        item.save()
        return redirect('contracts:compliance_checklist_detail', pk=item.checklist.pk)


class AddChecklistItemView(LoginRequiredMixin, CreateView):
    model = ChecklistItem
    form_class = ChecklistItemForm
    template_name = 'contracts/checklist_item_form.html'

    def form_valid(self, form):
        form.instance.checklist_id = self.kwargs['checklist_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:compliance_checklist_detail', kwargs={'pk': self.kwargs['checklist_pk']})


class AddDueDiligenceItemView(LoginRequiredMixin, CreateView):
    model = DueDiligenceTask
    form_class = DueDiligenceTaskForm
    template_name = 'contracts/dd_task_form.html'

    def form_valid(self, form):
        form.instance.process_id = self.kwargs['process_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.kwargs['process_pk']})


class AddDueDiligenceRiskView(LoginRequiredMixin, CreateView):
    model = DueDiligenceRisk
    form_class = DueDiligenceRiskForm
    template_name = 'contracts/dd_risk_form.html'

    def form_valid(self, form):
        form.instance.process_id = self.kwargs['process_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:due_diligence_detail', kwargs={'pk': self.kwargs['process_pk']})


class AddExpenseView(LoginRequiredMixin, CreateView):
    model = BudgetExpense
    form_class = BudgetExpenseForm
    template_name = 'contracts/expense_form.html'

    def form_valid(self, form):
        form.instance.budget_id = self.kwargs['budget_pk']
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('contracts:budget_detail', kwargs={'pk': self.kwargs['budget_pk']})


class WorkflowStepUpdateView(LoginRequiredMixin, UpdateView):
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


def workflow_create(request):
    if request.method == 'POST':
        form = WorkflowForm(request.POST)
        if form.is_valid():
            workflow = form.save(commit=False)
            workflow.created_by = request.user
            workflow.save()
            return redirect('contracts:workflow_detail', pk=workflow.pk)
    else:
        form = WorkflowForm()
    return render(request, 'contracts/workflow_form.html', {'form': form})


def workflow_detail(request, pk):
    workflow = get_object_or_404(Workflow, pk=pk)
    steps = WorkflowStep.objects.filter(workflow=workflow).order_by('order')
    return render(request, 'contracts/workflow_detail.html', {'workflow': workflow, 'steps': steps})


@login_required
def update_workflow_step(request, pk):
    step = get_object_or_404(WorkflowStep, pk=pk)
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

    def _safe(fn, default=0):
        try:
            return fn()
        except Exception:
            return default

    total_contracts = _safe(lambda: Contract.objects.count())
    active_contracts = _safe(lambda: Contract.objects.filter(status='ACTIVE').count())
    draft_contracts = _safe(lambda: Contract.objects.filter(status='DRAFT').count())
    pending_contracts = _safe(lambda: Contract.objects.filter(status='PENDING').count())
    expiring_soon_count = _safe(lambda: Contract.objects.filter(
        end_date__lte=thirty_days, end_date__gte=today, status='ACTIVE').count())

    total_clients = _safe(lambda: Client.objects.count())
    active_matters = _safe(lambda: Matter.objects.filter(status='ACTIVE').count())
    total_matters = _safe(lambda: Matter.objects.count())

    pending_tasks = _safe(lambda: LegalTask.objects.filter(status='PENDING').count())
    active_workflows = _safe(lambda: Workflow.objects.filter(status='ACTIVE').count())
    risk_count = _safe(lambda: RiskLog.objects.filter(risk_level__in=['HIGH', 'CRITICAL']).count())

    overdue_deadlines = _safe(lambda: Deadline.objects.filter(is_completed=False, due_date__lt=today).count())
    upcoming_deadline_count = _safe(lambda: Deadline.objects.filter(
        is_completed=False, due_date__gte=today, due_date__lte=seven_days).count())

    outstanding_invoices = _safe(lambda: Invoice.objects.filter(
        status__in=['SENT', 'OVERDUE']).aggregate(
        total=Sum('total_amount'))['total'] or Decimal('0'), Decimal('0'))
    overdue_invoices = _safe(lambda: Invoice.objects.filter(status='OVERDUE').aggregate(
        total=Sum('total_amount'))['total'] or Decimal('0'), Decimal('0'))
    paid_this_month = _safe(lambda: Invoice.objects.filter(
        status='PAID', updated_at__month=today.month, updated_at__year=today.year).aggregate(
        total=Sum('total_amount'))['total'] or Decimal('0'), Decimal('0'))

    total_documents = _safe(lambda: Document.objects.count())

    pending_approvals = _safe(lambda: ApprovalRequest.objects.filter(status='PENDING').count())
    pending_signatures = _safe(lambda: SignatureRequest.objects.filter(status='PENDING').count())
    open_dsars = _safe(lambda: DSARRequest.objects.filter(status__in=['RECEIVED', 'IN_PROGRESS']).count())

    unread_notifications = 0
    if request.user.is_authenticated:
        unread_notifications = _safe(lambda: Notification.objects.filter(
            recipient=request.user, is_read=False).count())

    recent_contracts = _safe(lambda: list(Contract.objects.order_by('-created_at')[:6]), [])
    upcoming_deadlines = _safe(lambda: list(Deadline.objects.filter(
        is_completed=False, due_date__gte=today).order_by('due_date')[:6]), [])
    upcoming_tasks = _safe(lambda: list(LegalTask.objects.filter(
        status='PENDING', due_date__gte=today).order_by('due_date')[:5]), [])
    recent_audit = _safe(lambda: list(AuditLog.objects.select_related('user').order_by('-timestamp')[:8]), [])

    contract_status_data = []
    for status_code, status_label in [('ACTIVE', 'Active'), ('DRAFT', 'Draft'), ('PENDING', 'In Review'), ('EXPIRED', 'Expired'), ('TERMINATED', 'Terminated')]:
        cnt = _safe(lambda sc=status_code: Contract.objects.filter(status=sc).count())
        if cnt > 0:
            contract_status_data.append({'label': status_label, 'count': cnt})

    billable_this_month = _safe(lambda: TimeEntry.objects.filter(
        date__month=today.month, date__year=today.year).aggregate(
        total=Sum('hours'))['total'] or Decimal('0'), Decimal('0'))

    trust_balance = _safe(lambda: TrustAccount.objects.aggregate(
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


class CounterpartyListView(LoginRequiredMixin, ListView):
    model = Counterparty
    template_name = 'contracts/counterparty_list.html'
    context_object_name = 'counterparties'

    def get_queryset(self):
        qs = Counterparty.objects.all()
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(jurisdiction__icontains=q))
        return qs


class CounterpartyCreateView(LoginRequiredMixin, CreateView):
    model = Counterparty
    form_class = CounterpartyForm
    template_name = 'contracts/counterparty_form.html'
    success_url = reverse_lazy('contracts:counterparty_list')


class CounterpartyDetailView(LoginRequiredMixin, DetailView):
    model = Counterparty
    template_name = 'contracts/counterparty_detail.html'


class CounterpartyUpdateView(LoginRequiredMixin, UpdateView):
    model = Counterparty
    form_class = CounterpartyForm
    template_name = 'contracts/counterparty_form.html'
    success_url = reverse_lazy('contracts:counterparty_list')


class ClauseCategoryListView(LoginRequiredMixin, ListView):
    model = ClauseCategory
    template_name = 'contracts/clause_category_list.html'
    context_object_name = 'categories'


class ClauseCategoryCreateView(LoginRequiredMixin, CreateView):
    model = ClauseCategory
    form_class = ClauseCategoryForm
    template_name = 'contracts/clause_category_form.html'
    success_url = reverse_lazy('contracts:clause_category_list')


class ClauseCategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = ClauseCategory
    form_class = ClauseCategoryForm
    template_name = 'contracts/clause_category_form.html'
    success_url = reverse_lazy('contracts:clause_category_list')


class ClauseTemplateListView(LoginRequiredMixin, ListView):
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


class ClauseTemplateCreateView(LoginRequiredMixin, CreateView):
    model = ClauseTemplate
    form_class = ClauseTemplateForm
    template_name = 'contracts/clause_template_form.html'
    success_url = reverse_lazy('contracts:clause_template_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ClauseTemplateDetailView(LoginRequiredMixin, DetailView):
    model = ClauseTemplate
    template_name = 'contracts/clause_template_detail.html'


class ClauseTemplateUpdateView(LoginRequiredMixin, UpdateView):
    model = ClauseTemplate
    form_class = ClauseTemplateForm
    template_name = 'contracts/clause_template_form.html'
    success_url = reverse_lazy('contracts:clause_template_list')


class EthicalWallListView(LoginRequiredMixin, ListView):
    model = EthicalWall
    template_name = 'contracts/ethical_wall_list.html'
    context_object_name = 'walls'


class EthicalWallCreateView(LoginRequiredMixin, CreateView):
    model = EthicalWall
    form_class = EthicalWallForm
    template_name = 'contracts/ethical_wall_form.html'
    success_url = reverse_lazy('contracts:ethical_wall_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class EthicalWallUpdateView(LoginRequiredMixin, UpdateView):
    model = EthicalWall
    form_class = EthicalWallForm
    template_name = 'contracts/ethical_wall_form.html'
    success_url = reverse_lazy('contracts:ethical_wall_list')


class SignatureRequestListView(LoginRequiredMixin, ListView):
    model = SignatureRequest
    template_name = 'contracts/signature_request_list.html'
    context_object_name = 'signatures'

    def get_queryset(self):
        qs = SignatureRequest.objects.select_related('contract').all()
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class SignatureRequestCreateView(LoginRequiredMixin, CreateView):
    model = SignatureRequest
    form_class = SignatureRequestForm
    template_name = 'contracts/signature_request_form.html'
    success_url = reverse_lazy('contracts:signature_request_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class SignatureRequestDetailView(LoginRequiredMixin, DetailView):
    model = SignatureRequest
    template_name = 'contracts/signature_request_detail.html'


class SignatureRequestUpdateView(LoginRequiredMixin, UpdateView):
    model = SignatureRequest
    form_class = SignatureRequestForm
    template_name = 'contracts/signature_request_form.html'
    success_url = reverse_lazy('contracts:signature_request_list')


class DataInventoryListView(LoginRequiredMixin, ListView):
    model = DataInventoryRecord
    template_name = 'contracts/data_inventory_list.html'
    context_object_name = 'records'


class DataInventoryCreateView(LoginRequiredMixin, CreateView):
    model = DataInventoryRecord
    form_class = DataInventoryForm
    template_name = 'contracts/data_inventory_form.html'
    success_url = reverse_lazy('contracts:data_inventory_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class DataInventoryDetailView(LoginRequiredMixin, DetailView):
    model = DataInventoryRecord
    template_name = 'contracts/data_inventory_detail.html'


class DataInventoryUpdateView(LoginRequiredMixin, UpdateView):
    model = DataInventoryRecord
    form_class = DataInventoryForm
    template_name = 'contracts/data_inventory_form.html'
    success_url = reverse_lazy('contracts:data_inventory_list')


class DSARRequestListView(LoginRequiredMixin, ListView):
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


class DSARRequestCreateView(LoginRequiredMixin, CreateView):
    model = DSARRequest
    form_class = DSARRequestForm
    template_name = 'contracts/dsar_form.html'
    success_url = reverse_lazy('contracts:dsar_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class DSARRequestDetailView(LoginRequiredMixin, DetailView):
    model = DSARRequest
    template_name = 'contracts/dsar_detail.html'


class DSARRequestUpdateView(LoginRequiredMixin, UpdateView):
    model = DSARRequest
    form_class = DSARRequestForm
    template_name = 'contracts/dsar_form.html'
    success_url = reverse_lazy('contracts:dsar_list')


class SubprocessorListView(LoginRequiredMixin, ListView):
    model = Subprocessor
    template_name = 'contracts/subprocessor_list.html'
    context_object_name = 'subprocessors'


class SubprocessorCreateView(LoginRequiredMixin, CreateView):
    model = Subprocessor
    form_class = SubprocessorForm
    template_name = 'contracts/subprocessor_form.html'
    success_url = reverse_lazy('contracts:subprocessor_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class SubprocessorDetailView(LoginRequiredMixin, DetailView):
    model = Subprocessor
    template_name = 'contracts/subprocessor_detail.html'


class SubprocessorUpdateView(LoginRequiredMixin, UpdateView):
    model = Subprocessor
    form_class = SubprocessorForm
    template_name = 'contracts/subprocessor_form.html'
    success_url = reverse_lazy('contracts:subprocessor_list')


class TransferRecordListView(LoginRequiredMixin, ListView):
    model = TransferRecord
    template_name = 'contracts/transfer_record_list.html'
    context_object_name = 'transfers'


class TransferRecordCreateView(LoginRequiredMixin, CreateView):
    model = TransferRecord
    form_class = TransferRecordForm
    template_name = 'contracts/transfer_record_form.html'
    success_url = reverse_lazy('contracts:transfer_record_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class TransferRecordUpdateView(LoginRequiredMixin, UpdateView):
    model = TransferRecord
    form_class = TransferRecordForm
    template_name = 'contracts/transfer_record_form.html'
    success_url = reverse_lazy('contracts:transfer_record_list')


class RetentionPolicyListView(LoginRequiredMixin, ListView):
    model = RetentionPolicy
    template_name = 'contracts/retention_policy_list.html'
    context_object_name = 'policies'


class RetentionPolicyCreateView(LoginRequiredMixin, CreateView):
    model = RetentionPolicy
    form_class = RetentionPolicyForm
    template_name = 'contracts/retention_policy_form.html'
    success_url = reverse_lazy('contracts:retention_policy_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class RetentionPolicyUpdateView(LoginRequiredMixin, UpdateView):
    model = RetentionPolicy
    form_class = RetentionPolicyForm
    template_name = 'contracts/retention_policy_form.html'
    success_url = reverse_lazy('contracts:retention_policy_list')


class LegalHoldListView(LoginRequiredMixin, ListView):
    model = LegalHold
    template_name = 'contracts/legal_hold_list.html'
    context_object_name = 'holds'


class LegalHoldCreateView(LoginRequiredMixin, CreateView):
    model = LegalHold
    form_class = LegalHoldForm
    template_name = 'contracts/legal_hold_form.html'
    success_url = reverse_lazy('contracts:legal_hold_list')

    def form_valid(self, form):
        form.instance.issued_by = self.request.user
        return super().form_valid(form)


class LegalHoldDetailView(LoginRequiredMixin, DetailView):
    model = LegalHold
    template_name = 'contracts/legal_hold_detail.html'


class LegalHoldUpdateView(LoginRequiredMixin, UpdateView):
    model = LegalHold
    form_class = LegalHoldForm
    template_name = 'contracts/legal_hold_form.html'
    success_url = reverse_lazy('contracts:legal_hold_list')


class ApprovalRuleListView(LoginRequiredMixin, ListView):
    model = ApprovalRule
    template_name = 'contracts/approval_rule_list.html'
    context_object_name = 'rules'


class ApprovalRuleCreateView(LoginRequiredMixin, CreateView):
    model = ApprovalRule
    form_class = ApprovalRuleForm
    template_name = 'contracts/approval_rule_form.html'
    success_url = reverse_lazy('contracts:approval_rule_list')


class ApprovalRuleUpdateView(LoginRequiredMixin, UpdateView):
    model = ApprovalRule
    form_class = ApprovalRuleForm
    template_name = 'contracts/approval_rule_form.html'
    success_url = reverse_lazy('contracts:approval_rule_list')


class ApprovalRequestListView(LoginRequiredMixin, ListView):
    model = ApprovalRequest
    template_name = 'contracts/approval_request_list.html'
    context_object_name = 'approvals'

    def get_queryset(self):
        qs = ApprovalRequest.objects.select_related('contract', 'assigned_to').all().order_by('-created_at')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class ApprovalRequestCreateView(LoginRequiredMixin, CreateView):
    model = ApprovalRequest
    form_class = ApprovalRequestForm
    template_name = 'contracts/approval_request_form.html'
    success_url = reverse_lazy('contracts:approval_request_list')


class ApprovalRequestUpdateView(LoginRequiredMixin, UpdateView):
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
