from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Max
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from contracts.forms import WorkflowForm, WorkflowStepForm, WorkflowTemplateForm, WorkflowTemplateStepForm
from contracts.models import Contract, Workflow, WorkflowStep, WorkflowTemplate, WorkflowTemplateStep
from contracts.permissions import ContractAction, can_access_contract_action
from contracts.tenancy import get_user_organization, scope_queryset_for_organization, set_organization_on_instance
from contracts.services.workflow_routing import build_approval_request_plan_for_contract, suggest_workflow_template_for_contract
from contracts.services.workflow_execution import advance_workflow_after_completion, materialize_workflow_from_template
from contracts.services.workflow_templates import COMPARISON_PRESETS, compare_template_versions, clone_template_version, list_template_versions
from contracts.view_support import (
    TenantAssignCreateMixin,
    apply_form_queryset_scopes,
    TenantScopedFormMixin,
    TenantScopedQuerysetMixin,
    configure_workflow_form as _configure_workflow_form,
    get_scoped_queryset_for_request,
    scope_workflow_steps_for_organization as _scope_workflow_steps_for_organization,
    scope_workflows_for_organization as _scope_workflows_for_organization,
    organization_user_queryset,
)


class WorkflowTemplateListView(TenantScopedQuerysetMixin, LoginRequiredMixin, ListView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_list.html'
    context_object_name = 'workflow_templates'

    def get_queryset(self):
        org = self.get_organization()
        return scope_queryset_for_organization(WorkflowTemplate.objects.prefetch_related('steps'), org)


class WorkflowTemplateDetailView(TenantScopedQuerysetMixin, LoginRequiredMixin, DetailView):
    model = WorkflowTemplate
    template_name = 'contracts/workflow_template_detail.html'
    context_object_name = 'workflow_template'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['steps'] = WorkflowTemplateStep.objects.filter(template=self.object).order_by('order')
        context['template_versions'] = list_template_versions(self.object)
        context['step_form'] = apply_form_queryset_scopes(
            WorkflowTemplateStepForm(),
            self.get_organization(),
            {'specific_assignee': organization_user_queryset},
        )
        return context


class WorkflowTemplateCompareView(TenantScopedQuerysetMixin, LoginRequiredMixin, View):
    template_name = 'contracts/workflow_template_compare.html'

    def get(self, request, pk, other_pk):
        left_template = get_object_or_404(scope_queryset_for_organization(WorkflowTemplate.objects.prefetch_related('steps'), self.get_organization()), pk=pk)
        right_template = get_object_or_404(scope_queryset_for_organization(WorkflowTemplate.objects.prefetch_related('steps'), self.get_organization()), pk=other_pk)
        preset = request.GET.get('preset', 'full')
        comparison = compare_template_versions(left_template, right_template, preset=preset)
        return render(request, self.template_name, {'comparison': comparison, 'comparison_presets': COMPARISON_PRESETS})


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
        org = self.get_organization()
        queryset = scope_queryset_for_organization(Workflow.objects.all(), org)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get('form')
        if form is not None:
            context.update(_build_workflow_editor_context(form, self.get_organization()))
        return context

    def form_valid(self, form):
        set_organization_on_instance(form.instance, get_user_organization(self.request.user))
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        if self.object.contract and not self.object.template_id:
            self.object.template = suggest_workflow_template_for_contract(self.object.contract)
            self.object.save(update_fields=['template'])
        if self.object.contract:
            from contracts.models import ApprovalRequest

            if not ApprovalRequest.objects.filter(contract=self.object.contract, status=ApprovalRequest.Status.PENDING).exists():
                for plan_item in build_approval_request_plan_for_contract(self.object.contract):
                    ApprovalRequest.objects.get_or_create(
                        organization=plan_item['organization'],
                        contract=plan_item['contract'],
                        rule=plan_item['rule'],
                        approval_step=plan_item['approval_step'],
                        defaults={
                            'assigned_to': plan_item['assigned_to'],
                            'due_date': plan_item['due_date'],
                            'status': plan_item['status'],
                        },
                    )
        return response


class WorkflowUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = Workflow
    form_class = WorkflowForm
    template_name = 'contracts/workflow_form.html'
    scoped_form_fields = {'contract': Contract}

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get('form')
        if form is not None:
            context.update(_build_workflow_editor_context(form, self.get_organization()))
        return context


class WorkflowStepUpdateView(TenantScopedFormMixin, TenantScopedQuerysetMixin, LoginRequiredMixin, UpdateView):
    model = WorkflowStep
    form_class = WorkflowStepForm
    template_name = 'contracts/workflow_step_form.html'
    scoped_form_fields = {'assigned_to': organization_user_queryset}

    def get_success_url(self):
        return reverse_lazy('contracts:workflow_detail', kwargs={'pk': self.object.workflow.pk})

    def form_valid(self, form):
        current_step = self.get_object()
        new_status = form.cleaned_data.get('status', current_step.status)
        if not current_step.can_transition_to(new_status):
            form.add_error('status', 'Invalid workflow step transition.')
            return self.form_invalid(form)

        response = super().form_valid(form)
        if new_status == WorkflowStep.Status.COMPLETED:
            self.object.completed_at = timezone.now()
            self.object.save(update_fields=['completed_at'])
            advance_workflow_after_completion(self.object)
        elif new_status == WorkflowStep.Status.ESCALATED:
            self.object.escalated_at = timezone.now()
            self.object.save(update_fields=['escalated_at'])
        return response


class WorkflowStepCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        organization = get_user_organization(request.user)
        step = get_object_or_404(_scope_workflow_steps_for_organization(organization), pk=pk)
        linked_contract = step.workflow.contract
        if linked_contract and not can_access_contract_action(request.user, linked_contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to complete this contract workflow step.')
        step.status = 'COMPLETED'
        step.completed_at = timezone.now()
        step.save()
        advance_workflow_after_completion(step)
        return redirect('contracts:workflow_detail', pk=step.workflow.pk)


class AddWorkflowStepView(LoginRequiredMixin, View):
    def post(self, request, pk):
        organization = get_user_organization(request.user)
        workflow = get_object_or_404(_scope_workflows_for_organization(organization), pk=pk)
        if workflow.contract and not can_access_contract_action(request.user, workflow.contract, ContractAction.EDIT):
            return HttpResponseForbidden('You do not have permission to create workflow steps for this contract.')
        form = apply_form_queryset_scopes(WorkflowStepForm(request.POST), organization, {'assigned_to': organization_user_queryset})
        if form.is_valid():
            step = form.save(commit=False)
            step.workflow = workflow
            if step.order is None:
                max_order = WorkflowStep.objects.filter(workflow=workflow).aggregate(max_order=Max('order'))['max_order'] or 0
                step.order = max_order + 1
            step.save()
            messages.success(request, f"Added step '{step.name}' to {workflow.title}.")
            return redirect('contracts:workflow_detail', pk=workflow.pk)
        return render(request, 'contracts/workflow_detail.html', _workflow_detail_context(workflow, add_step_form=form))


class AddWorkflowTemplateStepView(LoginRequiredMixin, View):
    def post(self, request, pk):
        template = get_object_or_404(WorkflowTemplate, pk=pk)
        organization = get_user_organization(request.user)
        form = apply_form_queryset_scopes(WorkflowTemplateStepForm(request.POST), organization, {'specific_assignee': organization_user_queryset})
        if form.is_valid():
            step = form.save(commit=False)
            step.template = template
            if step.order is None:
                max_order = WorkflowTemplateStep.objects.filter(template=template).aggregate(max_order=Max('order'))['max_order'] or 0
                step.order = max_order + 1
            step.save()
            messages.success(request, f"Added step '{step.name}' to {template.name}.")
            return redirect('contracts:workflow_template_detail', pk=template.pk)

        return render(
            request,
            'contracts/workflow_template_detail.html',
            _workflow_template_detail_context(template, organization, step_form=form),
        )


@login_required
def workflow_dashboard(request):
    workflows = get_scoped_queryset_for_request(request, Workflow).select_related('contract').order_by('-created_at')
    context = {'workflows': workflows}
    return render(request, 'contracts/workflow_dashboard.html', context)


@login_required
def workflow_create(request):
    organization = get_user_organization(request.user)
    if request.method == 'POST':
        form = _configure_workflow_form(WorkflowForm(request.POST), organization)
        if form.is_valid():
            workflow = form.save(commit=False)
            if workflow.contract and not can_access_contract_action(request.user, workflow.contract, ContractAction.EDIT):
                return HttpResponseForbidden('You do not have permission to create workflows for this contract.')
            set_organization_on_instance(workflow, organization)
            workflow.created_by = request.user
            workflow.save()
            if workflow.contract and not workflow.template_id:
                workflow.template = suggest_workflow_template_for_contract(workflow.contract)
                workflow.save(update_fields=['template'])
            materialize_workflow_from_template(workflow)
            if workflow.contract:
                from contracts.models import ApprovalRequest

                if not ApprovalRequest.objects.filter(contract=workflow.contract, status=ApprovalRequest.Status.PENDING).exists():
                    for plan_item in build_approval_request_plan_for_contract(workflow.contract):
                        ApprovalRequest.objects.get_or_create(
                            organization=plan_item['organization'],
                            contract=plan_item['contract'],
                            rule=plan_item['rule'],
                            approval_step=plan_item['approval_step'],
                            defaults={
                                'assigned_to': plan_item['assigned_to'],
                                'due_date': plan_item['due_date'],
                                'status': plan_item['status'],
                            },
                        )
            return redirect('contracts:workflow_detail', pk=workflow.pk)
    else:
        form = _configure_workflow_form(WorkflowForm(), organization)
        contract_pk = request.GET.get('contract_pk')
        template_pk = request.GET.get('template_pk')
        if contract_pk:
            form.initial['contract'] = contract_pk
        if template_pk:
            form.initial['template'] = template_pk
    context = {'form': form}
    context.update(_build_workflow_editor_context(form, organization))
    return render(request, 'contracts/workflow_form.html', context)


@login_required
def workflow_detail(request, pk):
    organization = get_user_organization(request.user)
    workflow = get_object_or_404(_scope_workflows_for_organization(organization), pk=pk)
    if workflow.contract and not can_access_contract_action(request.user, workflow.contract, ContractAction.COMMENT):
        return HttpResponseForbidden('You do not have access to this contract workflow.')
    return render(request, 'contracts/workflow_detail.html', _workflow_detail_context(workflow))


@login_required
def update_workflow_step(request, pk):
    organization = get_user_organization(request.user)
    step = get_object_or_404(_scope_workflow_steps_for_organization(organization), pk=pk)
    linked_contract = step.workflow.contract
    if linked_contract and not can_access_contract_action(request.user, linked_contract, ContractAction.EDIT):
        return HttpResponseForbidden('You do not have permission to update this contract workflow step.')
    if request.method == 'POST':
        new_status = request.POST.get('status', step.status)
        if not step.can_transition_to(new_status):
            messages.error(request, 'Invalid workflow step transition.')
            return redirect('contracts:workflow_detail', pk=step.workflow.pk)

        step.status = new_status
        description = request.POST.get('description', '').strip()
        if description:
            step.description = description
        update_fields = ['status', 'description']
        if new_status == 'COMPLETED':
            step.completed_at = timezone.now()
            update_fields.append('completed_at')
        elif new_status == 'ESCALATED':
            step.escalated_at = timezone.now()
            update_fields.append('escalated_at')
        step.save(update_fields=update_fields)
        if new_status == 'COMPLETED':
            advance_workflow_after_completion(step)
        return redirect('contracts:workflow_detail', pk=step.workflow.pk)
    return redirect('contracts:workflow_detail', pk=step.workflow.pk)


@login_required
def workflow_template_create(request):
    if request.method == 'POST':
        form = WorkflowTemplateForm(request.POST)
        if form.is_valid():
            template = form.save()
            return redirect('contracts:workflow_template_detail', pk=template.pk)
    else:
        form = WorkflowTemplateForm()
    return render(request, 'contracts/workflow_template_form.html', {'form': form})


@login_required
def workflow_template_detail(request, pk):
    template = get_object_or_404(WorkflowTemplate, pk=pk)
    return render(
        request,
        'contracts/workflow_template_detail.html',
        _workflow_template_detail_context(template, get_user_organization(request.user)),
    )


@login_required
def workflow_template_clone_version(request, pk):
    template = get_object_or_404(WorkflowTemplate, pk=pk)
    if request.method != 'POST':
        return redirect('contracts:workflow_template_detail', pk=template.pk)

    cloned_template = clone_template_version(template)
    messages.success(request, f'Created workflow template version {cloned_template.version}.')
    return redirect('contracts:workflow_template_detail', pk=cloned_template.pk)


@login_required
def workflow_template_restore_version(request, pk):
    template = get_object_or_404(WorkflowTemplate, pk=pk)
    if request.method != 'POST':
        return redirect('contracts:workflow_template_detail', pk=template.pk)

    restored_template = clone_template_version(template, is_active=True)
    messages.success(request, f'Restored workflow template version {template.version} as version {restored_template.version}.')
    return redirect('contracts:workflow_template_detail', pk=restored_template.pk)


@login_required
def workflow_template_compare(request, pk, other_pk):
    organization = get_user_organization(request.user)
    left_template = get_object_or_404(scope_queryset_for_organization(WorkflowTemplate.objects.prefetch_related('steps'), organization), pk=pk)
    right_template = get_object_or_404(scope_queryset_for_organization(WorkflowTemplate.objects.prefetch_related('steps'), organization), pk=other_pk)
    preset = request.GET.get('preset', 'full')
    comparison = compare_template_versions(left_template, right_template, preset=preset)
    return render(request, 'contracts/workflow_template_compare.html', {'comparison': comparison, 'comparison_presets': COMPARISON_PRESETS})


def _workflow_detail_context(workflow, add_step_form=None):
    organization = workflow.organization
    steps = WorkflowStep.objects.filter(workflow=workflow).order_by('order')
    max_order = steps.aggregate(max_order=Max('order'))['max_order'] or 0
    form = add_step_form or WorkflowStepForm(initial={'order': max_order + 1})
    form = apply_form_queryset_scopes(form, organization, {'assigned_to': organization_user_queryset})
    return {
        'workflow': workflow,
        'workflow_steps': steps,
        'add_step_form': form,
    }


def _workflow_template_detail_context(template, organization, step_form=None):
    steps = WorkflowTemplateStep.objects.filter(template=template).order_by('order')
    template_versions = list_template_versions(template)
    form = step_form or WorkflowTemplateStepForm()
    form = apply_form_queryset_scopes(form, organization, {'specific_assignee': organization_user_queryset})
    return {
        'workflow_template': template,
        'steps': steps,
        'template_versions': template_versions,
        'step_form': form,
    }


def _build_workflow_editor_context(form, organization):
    contract = None
    contract_value = form.data.get('contract') if form.is_bound else form.initial.get('contract')
    if contract_value:
        contract = Contract.objects.filter(pk=contract_value).first()

    selected_template = None
    template_value = form.data.get('template') if form.is_bound else form.initial.get('template')
    if template_value:
        selected_template = WorkflowTemplate.objects.filter(pk=template_value).first()

    suggested_template = suggest_workflow_template_for_contract(contract) if contract else None
    template_versions = list_template_versions(selected_template or suggested_template) if (selected_template or suggested_template) else []

    comparison = None
    if selected_template and suggested_template and selected_template.pk != suggested_template.pk:
        comparison = compare_template_versions(selected_template, suggested_template)

    return {
        'selected_contract': contract,
        'selected_template': selected_template,
        'suggested_template': suggested_template,
        'template_versions': template_versions,
        'template_comparison': comparison,
    }


@login_required
def workflow_template_list(request):
    templates = WorkflowTemplate.objects.prefetch_related('steps').all()
    return render(request, 'contracts/workflow_template_list.html', {'workflow_templates': templates})
