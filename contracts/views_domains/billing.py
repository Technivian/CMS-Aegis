from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import InvoiceForm, TimeEntryForm
from contracts.middleware import log_action
from contracts.models import Invoice, TimeEntry
from contracts.tenancy import get_user_organization, scope_queryset_for_organization, set_organization_on_instance
from contracts.view_support import TenantAssignCreateMixin, TenantScopedQuerysetMixin


class TimeEntryListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = TimeEntry
    template_name = 'contracts/time_entry_list.html'
    context_object_name = 'time_entries'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
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
        org = self.get_organization()
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
        org = self.get_organization()
        return scope_queryset_for_organization(TimeEntry.objects.all(), org)


class InvoiceListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'contracts/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(Invoice.objects.select_related('client', 'matter'), org)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-issue_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.get_organization()
        tenant_invoices = scope_queryset_for_organization(Invoice.objects.all(), org)
        invoice_stats = tenant_invoices.aggregate(
            total_outstanding=Sum('total_amount', filter=Q(status__in=['SENT', 'OVERDUE'])),
            total_paid=Sum('total_amount', filter=Q(status='PAID')),
            overdue_count=Count('id', filter=Q(status='OVERDUE')),
        )
        ctx['total_outstanding'] = invoice_stats['total_outstanding'] or Decimal('0')
        ctx['total_paid'] = invoice_stats['total_paid'] or Decimal('0')
        ctx['overdue_count'] = invoice_stats['overdue_count']
        overdue_sent = tenant_invoices.filter(status='SENT', due_date__lt=date.today())
        overdue_sent.update(status='OVERDUE')
        return ctx


class InvoiceDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'contracts/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        org = self.get_organization()
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
        org = self.get_organization()
        return scope_queryset_for_organization(Invoice.objects.all(), org)
