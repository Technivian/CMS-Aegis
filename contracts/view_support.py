from django.contrib.auth import get_user_model

from .models import (
    Budget,
    ChecklistItem,
    ComplianceChecklist,
    Contract,
    DueDiligenceTask,
    DueDiligenceProcess,
    Matter,
    OrganizationMembership,
    Workflow,
    WorkflowStep,
)
from .tenancy import get_user_organization, scope_queryset_for_organization, set_organization_on_instance

User = get_user_model()


def get_request_organization(request):
    if not hasattr(request, '_cached_organization'):
        request._cached_organization = get_user_organization(request.user)
    return request._cached_organization


class OrganizationContextMixin:
    """Provide a cached organization lookup for the current request."""

    def get_organization(self):
        return get_request_organization(self.request)


class TenantScopedQuerysetMixin(OrganizationContextMixin):
    """Automatically scope querysets to the current organization."""

    def get_queryset(self):
        queryset = super().get_queryset()
        org = self.get_organization()
        return scope_queryset_for_organization(queryset, org)


class TenantAssignCreateMixin(OrganizationContextMixin):
    def form_valid(self, form):
        set_organization_on_instance(form.instance, self.get_organization())
        return super().form_valid(form)


def scope_model_queryset(model_class, organization):
    return scope_queryset_for_organization(model_class.objects.all(), organization)


def apply_form_queryset_scopes(form, organization, scoped_form_fields):
    for field_name, queryset_source in scoped_form_fields.items():
        if field_name not in form.fields:
            continue

        if hasattr(queryset_source, '_meta') and hasattr(queryset_source, 'objects'):
            queryset = scope_model_queryset(queryset_source, organization)
        elif callable(queryset_source):
            queryset = queryset_source(organization)
        else:
            queryset = queryset_source
        form.fields[field_name].queryset = queryset
    return form


class TenantScopedFormMixin(OrganizationContextMixin):
    scoped_form_fields = {}

    def get_scoped_form_fields(self):
        return self.scoped_form_fields

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return apply_form_queryset_scopes(form, self.get_organization(), self.get_scoped_form_fields())


def scope_workflows_for_organization(organization):
    if organization is None:
        return Workflow.objects.none()
    return Workflow.objects.filter(organization=organization)


def scope_workflow_steps_for_organization(organization):
    if organization is None:
        return WorkflowStep.objects.none()
    return WorkflowStep.objects.filter(workflow__organization=organization)


def scope_checklists_for_organization(organization):
    if organization is None:
        return ComplianceChecklist.objects.none()
    return ComplianceChecklist.objects.filter(contract__organization=organization)


def scope_checklist_items_for_organization(organization):
    if organization is None:
        return ChecklistItem.objects.none()
    return ChecklistItem.objects.filter(checklist__contract__organization=organization)


def scope_due_diligence_processes_for_organization(organization):
    if organization is None:
        return DueDiligenceProcess.objects.none()
    return DueDiligenceProcess.objects.filter(organization=organization)


def scope_due_diligence_tasks_for_organization(organization):
    if organization is None:
        return DueDiligenceTask.objects.none()
    return DueDiligenceTask.objects.filter(process__organization=organization)


def scope_budgets_for_organization(organization):
    if organization is None:
        return Budget.objects.none()
    return Budget.objects.filter(organization=organization)


def organization_user_queryset(organization):
    if organization is None:
        return User.objects.none()
    return User.objects.filter(
        organization_memberships__organization=organization,
        organization_memberships__is_active=True,
    ).distinct()


def configure_workflow_form(form, organization):
    return apply_form_queryset_scopes(form, organization, {'contract': Contract})
