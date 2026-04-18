from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.urls import reverse_lazy, reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import ConflictCheckForm, TrustAccountForm, TrustTransactionForm
from contracts.middleware import log_action
from contracts.models import ConflictCheck, TrustAccount, TrustTransaction
from contracts.view_support import TenantAssignCreateMixin, TenantScopedQuerysetMixin


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
