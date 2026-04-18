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
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, get_user_model
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
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
    LegalHold, ApprovalRule, ApprovalRequest, Case, CaseMatter, CaseSignal,
)
from .middleware import log_action
from .observability import db_health_snapshot, request_metrics_snapshot, scheduler_health_snapshot
from .permissions import (
    ContractAction,
    can_access_contract_action,
    can_manage_organization,
    get_active_org_membership,
    is_organization_owner,
)
from .tenancy import get_user_organization, scope_queryset_for_organization, set_organization_on_instance
from .services.starter_content import ensure_org_starter_content
from .view_support import (
    OrganizationContextMixin,
    TenantAssignCreateMixin,
    TenantScopedFormMixin,
    TenantScopedQuerysetMixin,
    apply_form_queryset_scopes as _apply_form_queryset_scopes,
    configure_workflow_form as _configure_workflow_form,
    organization_user_queryset as _organization_user_queryset,
    scope_budgets_for_organization as _scope_budgets_for_organization,
    scope_checklist_items_for_organization as _scope_checklist_items_for_organization,
    scope_checklists_for_organization as _scope_checklists_for_organization,
    scope_due_diligence_processes_for_organization as _scope_due_diligence_processes_for_organization,
    scope_due_diligence_tasks_for_organization as _scope_due_diligence_tasks_for_organization,
    scope_workflow_steps_for_organization as _scope_workflow_steps_for_organization,
    scope_workflows_for_organization as _scope_workflows_for_organization,
)
from .views_domains.privacy_approvals import (
    ApprovalRequestCreateView,
    ApprovalRequestListView,
    ApprovalRequestUpdateView,
    ApprovalRuleCreateView,
    ApprovalRuleListView,
    ApprovalRuleUpdateView,
    DSARRequestCreateView,
    DSARRequestDetailView,
    DSARRequestListView,
    DSARRequestUpdateView,
    DataInventoryCreateView,
    DataInventoryDetailView,
    DataInventoryListView,
    DataInventoryUpdateView,
    LegalHoldCreateView,
    LegalHoldDetailView,
    LegalHoldListView,
    LegalHoldUpdateView,
    RetentionPolicyCreateView,
    RetentionPolicyListView,
    RetentionPolicyUpdateView,
    SignatureRequestCreateView,
    SignatureRequestDetailView,
    SignatureRequestListView,
    SignatureRequestUpdateView,
    SubprocessorCreateView,
    SubprocessorDetailView,
    SubprocessorListView,
    SubprocessorUpdateView,
    TransferRecordCreateView,
    TransferRecordListView,
    TransferRecordUpdateView,
    privacy_dashboard,
    privacy_evidence_export,
)
from .views_domains.organization_admin import (
    accept_organization_invite,
    deactivate_organization_member,
    organization_identity_settings,
    organization_activity,
    organization_activity_export,
    organization_team,
    revoke_member_sessions,
    reactivate_organization_member,
    reports_dashboard,
    resend_organization_invite,
    revoke_organization_invite,
    update_membership_role,
)
from .views_domains.saml import (
    saml_acs,
    saml_login,
    saml_metadata,
    saml_logout,
    saml_select,
)
from .views_domains.deadlines import (
    DeadlineCreateView,
    DeadlineListView,
    DeadlineUpdateView,
    deadline_complete,
)
from .views_domains.contracts import (
    ContractCreateView,
    ContractDetailView,
    ContractListView,
    ContractUpdateView,
    RepositoryView,
    contract_ai_assistant,
    dashboard,
)
from .views_domains.matter_ops import (
    ComplianceChecklistCreateView,
    ComplianceChecklistDetailView,
    ComplianceChecklistListView,
    ComplianceChecklistUpdateView,
    DueDiligenceCreateView,
    DueDiligenceDetailView,
    DueDiligenceListView,
    DueDiligenceUpdateView,
    LegalTaskCreateView,
    LegalTaskKanbanView,
    LegalTaskUpdateView,
    BudgetCreateView,
    BudgetDetailView,
    BudgetListView,
    BudgetUpdateView,
    RiskLogCreateView,
    RiskLogListView,
    RiskLogUpdateView,
    TrademarkRequestCreateView,
    TrademarkRequestDetailView,
    TrademarkRequestListView,
    TrademarkRequestUpdateView,
)
from .views_domains.actions import (
    AddChecklistItemView,
    AddDueDiligenceItemView,
    AddDueDiligenceRiskView,
    AddExpenseView,
    AddNegotiationNoteView,
    ToggleChecklistItemView,
    identity_telemetry_dashboard,
    organization_security_settings,
    organization_security_export,
    organization_session_audit,
    organization_session_audit_export,
    profile,
    settings_hub,
    toggle_dd_item,
    toggle_redesign,
)
from .views_domains.core import (
    health_check,
    index,
    operations_dashboard,
    SignUpView,
    switch_organization,
)
from .views_domains.activity import (
    AuditLogListView,
    mark_all_notifications_read,
    mark_notification_read,
    notification_list,
)
from .views_domains.client_matter_document import (
    ClientCreateView,
    ClientDetailView,
    ClientListView,
    ClientUpdateView,
    DocumentCreateView,
    DocumentDetailView,
    DocumentCompareView,
    DocumentListView,
    DocumentUpdateView,
    DocumentOCRQueueView,
    DocumentOCRReviewUpdateView,
    MatterCreateView,
    MatterDetailView,
    MatterListView,
    MatterUpdateView,
)
from .views_domains.billing import (
    InvoiceCreateView,
    InvoiceDetailView,
    InvoiceListView,
    InvoiceUpdateView,
    TimeEntryCreateView,
    TimeEntryListView,
    TimeEntryUpdateView,
)
from .views_domains.trust_conflict import (
    AddTrustTransactionView,
    ConflictCheckCreateView,
    ConflictCheckListView,
    ConflictCheckUpdateView,
    TrustAccountCreateView,
    TrustAccountDetailView,
    TrustAccountListView,
)
from .views_domains.repository_management import (
    ClauseCategoryCreateView,
    ClauseCategoryListView,
    ClauseCategoryUpdateView,
    ClauseTemplateCreateView,
    ClauseTemplateDetailView,
    ClauseTemplateListView,
    ClauseTemplateUpdateView,
    CounterpartyCreateView,
    CounterpartyDetailView,
    CounterpartyListView,
    CounterpartyUpdateView,
    EthicalWallCreateView,
    EthicalWallListView,
    EthicalWallUpdateView,
    global_search,
)
from .views_domains.workflow_management import (
    AddWorkflowStepView,
    AddWorkflowTemplateStepView,
    WorkflowCreateView,
    WorkflowDetailView,
    WorkflowListView,
    WorkflowStepCompleteView,
    WorkflowStepUpdateView,
    WorkflowTemplateCreateView,
    WorkflowTemplateDetailView,
    WorkflowTemplateListView,
    WorkflowTemplateUpdateView,
    WorkflowUpdateView,
    update_workflow_step,
    workflow_create,
    workflow_dashboard,
    workflow_detail,
    workflow_template_create,
    workflow_template_clone_version,
    workflow_template_restore_version,
    workflow_template_compare,
    workflow_template_detail,
    workflow_template_list,
)
from config.feature_flags import get_feature_flag, is_feature_redesign_enabled

logger = logging.getLogger(__name__)
User = get_user_model()


# ==================== ACTION / FUNCTION-BASED VIEWS ====================
