from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import (
    ClauseCategoryForm,
    ClausePlaybookForm,
    ClauseVariantForm,
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
    SearchPreset,
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
from contracts.services.clause_versions import compare_clause_versions, clone_clause_template_version, list_clause_template_versions
from contracts.services.clause_variants import resolve_clause_variant
from contracts.services.semantic_search import rank_clause_templates_semantic
from contracts.middleware import log_action


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


SEARCH_PRESET_PARAM_KEYS = ('q', 'type', 'status', 'jurisdiction', 'search_mode')


def _search_request_params(request, organization):
    params = {key: (request.GET.get(key) or '').strip() for key in SEARCH_PRESET_PARAM_KEYS}
    active_preset = None
    preset_id = (request.GET.get('preset_id') or '').strip()
    if preset_id and organization is not None:
        active_preset = get_object_or_404(
            SearchPreset,
            pk=preset_id,
            organization=organization,
            created_by=request.user,
        )
        preset_params = active_preset.params or {}
        for key in SEARCH_PRESET_PARAM_KEYS:
            value = preset_params.get(key)
            if value is not None:
                params[key] = str(value)
    params['search_mode'] = (params.get('search_mode') or 'hybrid').strip().lower()
    if params['search_mode'] not in {'keyword', 'semantic', 'hybrid'}:
        params['search_mode'] = 'hybrid'
    params['type'] = (params.get('type') or '').strip().lower()
    params['status'] = (params.get('status') or '').strip().upper()
    params['jurisdiction'] = (params.get('jurisdiction') or '').strip()
    params['q'] = (params.get('q') or '').strip()
    return params, active_preset


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
        return qs.filter(derived_versions__isnull=True).distinct()

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
        return _clause_template_detail_context(self.object, self.get_organization())


class ClauseTemplateUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = ClauseTemplate
    form_class = ClauseTemplateForm
    template_name = 'contracts/clause_template_form.html'
    success_url = reverse_lazy('contracts:clause_template_list')
    scoped_form_fields = {'category': ClauseCategory}

    def form_valid(self, form):
        original_template = self.get_object()
        staged_template = form.save(commit=False)
        self.object = clone_clause_template_version(
            original_template,
            title=staged_template.title,
            category=staged_template.category,
            content=staged_template.content,
            fallback_content=staged_template.fallback_content,
            jurisdiction_scope=staged_template.jurisdiction_scope,
            is_mandatory=staged_template.is_mandatory,
            applicable_contract_types=staged_template.applicable_contract_types,
            playbook_notes=staged_template.playbook_notes,
            tags=staged_template.tags,
            created_by=self.request.user,
            is_approved=False,
            approved_by=None,
            copy_variants=True,
        )
        log_action(
            self.request.user,
            'CREATE',
            'ClauseTemplate',
            self.object.id,
            str(self.object),
            changes={
                'event': 'clause_template_version_created',
                'parent_template_id': original_template.id,
                'version': self.object.version,
            },
            request=self.request,
        )
        messages.success(self.request, f'Created clause template version {self.object.version}.')
        return redirect('contracts:clause_template_detail', pk=self.object.pk)


class ClauseTemplateCompareView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = ClauseTemplate
    template_name = 'contracts/clause_template_compare.html'
    context_object_name = 'clause_template'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(ClauseTemplate.objects.select_related('category', 'parent_template'), org)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        other_template = get_object_or_404(
            scope_queryset_for_organization(ClauseTemplate.objects.select_related('category', 'parent_template'), self.get_organization()),
            pk=self.kwargs['other_pk'],
        )
        context['other_template'] = other_template
        context['comparison'] = compare_clause_versions(self.object, other_template)
        return context


def _clause_template_detail_context(template, organization, variant_form=None, playbook_form=None):
    form = variant_form or ClauseVariantForm()
    form.fields['playbook'].queryset = scope_queryset_for_organization(ClausePlaybook.objects.all(), organization)
    playbook_editor = playbook_form or ClausePlaybookForm()
    version_chain = list_clause_template_versions(template)
    return {
        'object': template,
        'fallback_summary': get_clause_fallback_summary(template),
        'policy_issues': validate_clause_policy(template),
        'resolved_variant': resolve_clause_variant(template),
        'template_versions': version_chain,
        'playbooks': ClausePlaybook.objects.filter(organization=organization, is_active=True).order_by('name'),
        'variants': ClauseVariant.objects.filter(template=template, is_active=True).select_related('playbook').order_by('priority', '-created_at'),
        'variant_form': form,
        'playbook_form': playbook_editor,
    }


@login_required
def clause_variant_create(request, pk):
    organization = get_user_organization(request.user)
    template = get_object_or_404(scope_queryset_for_organization(ClauseTemplate.objects.all(), organization), pk=pk)
    if request.method != 'POST':
        return redirect('contracts:clause_template_detail', pk=template.pk)

    form = ClauseVariantForm(request.POST)
    form.fields['playbook'].queryset = scope_queryset_for_organization(ClausePlaybook.objects.all(), organization)
    if form.is_valid():
        variant = form.save(commit=False)
        variant.template = template
        variant.organization = organization
        variant.save()
        messages.success(request, f"Added variant for {template.title}.")
        return redirect('contracts:clause_template_detail', pk=template.pk)

    return render(
        request,
        'contracts/clause_template_detail.html',
        _clause_template_detail_context(template, organization, variant_form=form),
    )


@login_required
def clause_playbook_create(request, pk):
    organization = get_user_organization(request.user)
    template = get_object_or_404(scope_queryset_for_organization(ClauseTemplate.objects.all(), organization), pk=pk)
    if request.method != 'POST':
        return redirect('contracts:clause_template_detail', pk=template.pk)

    form = ClausePlaybookForm(request.POST)
    if form.is_valid():
        playbook = form.save(commit=False)
        playbook.organization = organization
        playbook.save()
        messages.success(request, f"Added playbook '{playbook.name}'.")
        return redirect('contracts:clause_template_detail', pk=template.pk)

    return render(
        request,
        'contracts/clause_template_detail.html',
        _clause_template_detail_context(template, organization, playbook_form=form),
    )


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
    org = get_user_organization(request.user)
    params, active_preset = _search_request_params(request, org)
    q = params['q']
    result_type = params['type']
    contract_status = params['status']
    jurisdiction = params['jurisdiction']
    search_mode = params['search_mode']
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
    saved_searches = []
    if org:
        saved_searches = SearchPreset.objects.filter(organization=org, created_by=request.user).order_by('name')
    return render(
        request,
        'contracts/search_results.html',
        {
            'q': q,
            'results': results,
            'search_mode': search_mode,
            'saved_searches': saved_searches,
            'active_preset': active_preset,
            'current_search_params': params,
        },
    )


@login_required
@require_POST
def save_search_preset(request):
    organization = get_user_organization(request.user)
    if organization is None:
        messages.error(request, 'No active organization found.')
        return redirect('contracts:global_search')

    name = (request.POST.get('name') or '').strip()
    if not name:
        messages.error(request, 'Enter a name for this saved search.')
        return redirect(request.META.get('HTTP_REFERER', reverse('contracts:global_search')))

    params = {key: (request.POST.get(key) or '').strip() for key in SEARCH_PRESET_PARAM_KEYS}
    if params['search_mode'] not in {'keyword', 'semantic', 'hybrid'}:
        params['search_mode'] = 'hybrid'

    preset, created = SearchPreset.objects.update_or_create(
        organization=organization,
        created_by=request.user,
        name=name,
        defaults={'params': params},
    )
    messages.success(request, f"{'Saved' if created else 'Updated'} search preset '{preset.name}'.")
    return redirect(f"{reverse('contracts:global_search')}?preset_id={preset.pk}")


@login_required
@require_POST
def delete_search_preset(request, preset_id):
    organization = get_user_organization(request.user)
    if organization is None:
        messages.error(request, 'No active organization found.')
        return redirect('contracts:global_search')

    preset = get_object_or_404(
        SearchPreset,
        pk=preset_id,
        organization=organization,
        created_by=request.user,
    )
    preset.delete()
    messages.success(request, f"Deleted search preset '{preset.name}'.")
    return redirect(request.META.get('HTTP_REFERER', reverse('contracts:global_search')))
