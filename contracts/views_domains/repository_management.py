from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import (
    ClauseCategoryForm,
    ClauseTemplateForm,
    CounterpartyForm,
    EthicalWallForm,
)
from contracts.models import (
    Case,
    CaseMatter,
    CaseSignal,
    ClauseCategory,
    ClauseTemplate,
    ClausePlaybook,
    ClauseVariant,
    Client,
    Counterparty,
    Document,
    EthicalWall,
    Matter,
)
from contracts.tenancy import get_user_organization, scope_queryset_for_organization
from contracts.view_support import (
    TenantAssignCreateMixin,
    TenantScopedFormMixin,
    TenantScopedQuerysetMixin,
    get_scoped_queryset_for_request,
    organization_user_queryset as _organization_user_queryset,
)
from contracts.services.clause_policy import get_clause_fallback_summary, validate_clause_policy
from contracts.services.clause_variants import resolve_clause_variant
from contracts.services.semantic_search import rank_clause_templates_semantic


def _ranked_queryset(queryset, q, title_field='title', extra_fields=()):
    if not q:
        return queryset
    query = q.lower()

    def score(item):
        fields = [getattr(item, title_field, '')]
        for field in extra_fields:
            fields.append(getattr(item, field, ''))
        best = 999
        for value in fields:
            normalized = (value or '').strip().lower()
            if not normalized:
                continue
            if normalized == query:
                best = min(best, 0)
            elif normalized.startswith(query):
                best = min(best, 1)
            elif query in normalized:
                best = min(best, 2)
        return best

    ranked_items = sorted(list(queryset), key=score)
    return ranked_items


def _merge_ranked_results(primary, secondary, limit=10):
    merged = []
    seen_ids = set()
    for item in list(primary) + list(secondary):
        item_id = getattr(item, 'pk', None)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


class CounterpartyListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = Counterparty
    template_name = 'contracts/counterparty_list.html'
    context_object_name = 'counterparties'

    def get_queryset(self):
        org = self.get_organization()
        qs = scope_queryset_for_organization(Counterparty.objects.all(), org)
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
        org = self.get_organization()
        qs = scope_queryset_for_organization(ClauseTemplate.objects.select_related('category').all(), org)
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
        org = self.get_organization()
        ctx['categories'] = scope_queryset_for_organization(ClauseCategory.objects.all(), org)
        return ctx


class ClauseTemplateCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = ClauseTemplate
    form_class = ClauseTemplateForm
    template_name = 'contracts/clause_template_form.html'
    success_url = reverse_lazy('contracts:clause_template_list')
    scoped_form_fields = {'category': ClauseCategory}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ClauseTemplateDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = ClauseTemplate
    template_name = 'contracts/clause_template_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fallback_summary'] = get_clause_fallback_summary(self.object)
        context['policy_issues'] = validate_clause_policy(self.object)
        context['resolved_variant'] = resolve_clause_variant(self.object)
        context['playbooks'] = ClausePlaybook.objects.filter(
            organization=self.get_organization(),
            is_active=True,
        ).order_by('name')
        context['variants'] = ClauseVariant.objects.filter(template=self.object, is_active=True).select_related('playbook').order_by('priority', '-created_at')
        return context


class ClauseTemplateUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ClauseTemplate
    form_class = ClauseTemplateForm
    template_name = 'contracts/clause_template_form.html'
    success_url = reverse_lazy('contracts:clause_template_list')
    scoped_form_fields = {'category': ClauseCategory}


class EthicalWallListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = EthicalWall
    template_name = 'contracts/ethical_wall_list.html'
    context_object_name = 'walls'


class EthicalWallCreateView(TenantScopedFormMixin, TenantAssignCreateMixin, LoginRequiredMixin, CreateView):
    model = EthicalWall
    form_class = EthicalWallForm
    template_name = 'contracts/ethical_wall_form.html'
    success_url = reverse_lazy('contracts:ethical_wall_list')
    scoped_form_fields = {
        'matter': Matter,
        'client': Client,
        'restricted_users': _organization_user_queryset,
    }

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class EthicalWallUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = EthicalWall
    form_class = EthicalWallForm
    template_name = 'contracts/ethical_wall_form.html'
    success_url = reverse_lazy('contracts:ethical_wall_list')
    scoped_form_fields = {
        'matter': Matter,
        'client': Client,
        'restricted_users': _organization_user_queryset,
    }


@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    org = get_user_organization(request.user)
    result_type = (request.GET.get('type') or '').strip().lower()
    contract_status = (request.GET.get('status') or '').strip().upper()
    jurisdiction = (request.GET.get('jurisdiction') or '').strip()
    search_mode = (request.GET.get('search_mode') or 'hybrid').strip().lower()
    if search_mode not in {'keyword', 'semantic', 'hybrid'}:
        search_mode = 'hybrid'
    results = {}
    if q:
        case_queryset = get_scoped_queryset_for_request(request, Case).filter(
            Q(title__icontains=q) | Q(counterparty__icontains=q) | Q(content__icontains=q)
        )
        if contract_status:
            case_queryset = case_queryset.filter(status=contract_status)
        if result_type and result_type not in {'contract', 'contracts', 'case', 'cases'}:
            case_results = case_queryset.none()
        else:
            case_results = _ranked_queryset(case_queryset, q, title_field='title')[:10]
        results['cases'] = case_results
        results['contracts'] = case_results
        client_queryset = get_scoped_queryset_for_request(request, Client).filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(industry__icontains=q)
        )
        if result_type and result_type not in {'client', 'clients'}:
            results['clients'] = client_queryset.none()
        else:
            results['clients'] = _ranked_queryset(client_queryset, q, title_field='name')[:10]
        case_matter_queryset = get_scoped_queryset_for_request(request, CaseMatter).filter(
            Q(title__icontains=q) | Q(matter_number__icontains=q) | Q(description__icontains=q)
        )
        if result_type and result_type not in {'matter', 'matters', 'case_matter', 'case_matters'}:
            results['case_matters'] = case_matter_queryset.none()
        else:
            results['case_matters'] = _ranked_queryset(case_matter_queryset, q, title_field='title')[:10]
        results['matters'] = results['case_matters']
        document_queryset = get_scoped_queryset_for_request(request, Document).filter(
            Q(title__icontains=q) | Q(description__icontains=q) | Q(tags__icontains=q)
        )
        if result_type and result_type not in {'document', 'documents'}:
            results['documents'] = document_queryset.none()
        else:
            results['documents'] = _ranked_queryset(document_queryset, q, title_field='title')[:10]
        clause_queryset = get_scoped_queryset_for_request(request, ClauseTemplate).filter(
            Q(title__icontains=q) | Q(content__icontains=q) | Q(tags__icontains=q)
        )
        semantic_clause_queryset = get_scoped_queryset_for_request(request, ClauseTemplate).all()
        if jurisdiction:
            clause_queryset = clause_queryset.filter(Q(jurisdiction_scope__iexact=jurisdiction) | Q(fallback_content__icontains=jurisdiction))
            semantic_clause_queryset = semantic_clause_queryset.filter(
                Q(jurisdiction_scope__iexact=jurisdiction) | Q(fallback_content__icontains=jurisdiction)
            )
        if result_type and result_type not in {'clause', 'clauses'}:
            results['clauses'] = clause_queryset.none()
        else:
            keyword_clause_results = _ranked_queryset(
                clause_queryset,
                q,
                title_field='title',
                extra_fields=('tags', 'fallback_content', 'playbook_notes'),
            )
            semantic_clause_results = rank_clause_templates_semantic(semantic_clause_queryset, q, limit=25)

            if search_mode == 'keyword':
                results['clauses'] = keyword_clause_results[:10]
            elif search_mode == 'semantic':
                results['clauses'] = semantic_clause_results[:10]
            else:
                results['clauses'] = _merge_ranked_results(keyword_clause_results, semantic_clause_results, limit=10)
        counterparty_queryset = get_scoped_queryset_for_request(request, Counterparty).filter(
            Q(name__icontains=q) | Q(jurisdiction__icontains=q)
        )
        if jurisdiction:
            counterparty_queryset = counterparty_queryset.filter(jurisdiction__icontains=jurisdiction)
        if result_type and result_type not in {'counterparty', 'counterparties'}:
            results['counterparties'] = counterparty_queryset.none()
        else:
            results['counterparties'] = _ranked_queryset(counterparty_queryset, q, title_field='name')[:10]
        task_signal_queryset = CaseSignal.objects.for_organization(org).filter(
            Q(title__icontains=q) | Q(description__icontains=q)
        )
        if result_type and result_type not in {'task', 'tasks', 'signal', 'signals'}:
            results['task_signals'] = task_signal_queryset.none()
        else:
            results['task_signals'] = _ranked_queryset(task_signal_queryset, q, title_field='title')[:10]
        results['tasks'] = results['task_signals']
    return render(request, 'contracts/search_results.html', {'q': q, 'results': results, 'search_mode': search_mode})
