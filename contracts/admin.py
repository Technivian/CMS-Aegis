from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from .models import (
    Organization, OrganizationMembership, OrganizationInvitation, Deadline,
    TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep, ChecklistItem,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk, Budget, BudgetExpense, Contract,
    Counterparty, ClauseCategory, ClauseTemplate, SignatureRequest, DataInventoryRecord,
    DSARRequest, Subprocessor, TransferRecord, RetentionPolicy, LegalHold,
    ApprovalRule, ApprovalRequest, EthicalWall, SalesforceOrganizationConnection,
    OrganizationContractFieldMap, SalesforceSyncRun, WebhookEndpoint, WebhookDelivery,
)


class ExpiringContractFilter(admin.SimpleListFilter):
    title = 'contract health'
    parameter_name = 'contract_health'

    def lookups(self, request, model_admin):
        return (
            ('expiring_30', 'Expiring in 30 days'),
            ('expired', 'Expired'),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()
        if self.value() == 'expiring_30':
            return queryset.filter(status='ACTIVE', end_date__gte=today, end_date__lte=today + timedelta(days=30))
        if self.value() == 'expired':
            return queryset.filter(end_date__lt=today)
        return queryset


class OverdueApprovalFilter(admin.SimpleListFilter):
    title = 'approval health'
    parameter_name = 'approval_health'

    def lookups(self, request, model_admin):
        return (
            ('pending', 'Pending'),
            ('overdue', 'Overdue'),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'pending':
            return queryset.filter(status='PENDING')
        if self.value() == 'overdue':
            return queryset.filter(status='PENDING', due_date__lt=now)
        return queryset


class OverdueDSARFilter(admin.SimpleListFilter):
    title = 'dsar health'
    parameter_name = 'dsar_health'

    def lookups(self, request, model_admin):
        return (
            ('open', 'Open'),
            ('overdue', 'Overdue'),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()
        if self.value() == 'open':
            return queryset.exclude(status__in=['COMPLETED', 'DENIED'])
        if self.value() == 'overdue':
            return queryset.exclude(status__in=['COMPLETED', 'DENIED']).filter(due_date__lt=today)
        return queryset


class DeadlineHealthFilter(admin.SimpleListFilter):
    title = 'deadline health'
    parameter_name = 'deadline_health'

    def lookups(self, request, model_admin):
        return (
            ('open', 'Open'),
            ('overdue', 'Overdue'),
            ('completed', 'Completed'),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()
        if self.value() == 'open':
            return queryset.filter(is_completed=False)
        if self.value() == 'overdue':
            return queryset.filter(is_completed=False, due_date__lt=today)
        if self.value() == 'completed':
            return queryset.filter(is_completed=True)
        return queryset


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ('organization', 'user', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('organization__name', 'user__username', 'user__email')


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = ('organization', 'email', 'role', 'status', 'invited_by', 'expires_at', 'created_at')
    list_filter = ('role', 'status')
    search_fields = ('organization__name', 'email', 'invited_by__username')


@admin.register(SalesforceOrganizationConnection)
class SalesforceOrganizationConnectionAdmin(admin.ModelAdmin):
    list_display = (
        'organization',
        'is_active',
        'connected_by',
        'instance_url',
        'token_expires_at',
        'updated_at',
    )
    list_filter = ('is_active',)
    search_fields = ('organization__name', 'organization__slug', 'external_org_id', 'instance_url')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(OrganizationContractFieldMap)
class OrganizationContractFieldMapAdmin(admin.ModelAdmin):
    list_display = (
        'organization',
        'canonical_field',
        'salesforce_object',
        'salesforce_field',
        'is_required',
        'is_active',
    )
    list_filter = ('is_required', 'is_active', 'salesforce_object')
    search_fields = ('organization__name', 'canonical_field', 'salesforce_field')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SalesforceSyncRun)
class SalesforceSyncRunAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'organization',
        'status',
        'trigger_source',
        'dry_run',
        'fetched_records',
        'created_count',
        'updated_count',
        'error_count',
        'started_at',
        'completed_at',
    )
    list_filter = ('status', 'trigger_source', 'dry_run')
    search_fields = ('organization__name', 'organization__slug', 'error_message')
    readonly_fields = ('started_at', 'completed_at')


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ('organization', 'name', 'url', 'status', 'max_attempts', 'updated_at')
    list_filter = ('status',)
    search_fields = ('organization__name', 'name', 'url')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'organization',
        'endpoint',
        'event_type',
        'status',
        'attempt_count',
        'max_attempts',
        'response_status',
        'created_at',
    )
    list_filter = ('status', 'event_type')
    search_fields = ('organization__name', 'endpoint__name', 'event_type', 'error_message')
    readonly_fields = ('created_at', 'updated_at', 'dead_lettered_at', 'sent_at')


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ('title', 'contract', 'matter', 'due_date', 'is_completed', 'is_overdue')
    list_filter = ('is_completed', 'deadline_type', 'priority', DeadlineHealthFilter)
    search_fields = ('title', 'description', 'contract__title', 'matter__title')
    date_hierarchy = 'due_date'

    @admin.display(boolean=True, description='Overdue')
    def is_overdue(self, obj):
        return obj.is_overdue

@admin.register(RiskLog)
class RiskLogAdmin(admin.ModelAdmin):
    list_display = ('title', 'risk_level', 'case_record', 'created_by', 'created_at')
    list_filter = ('risk_level', 'created_at')
    search_fields = ('title', 'description')

    @admin.display(description='Case')
    def case_record(self, obj):
        return obj.contract or obj.matter

class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 1

@admin.register(ComplianceChecklist)
class ComplianceChecklistAdmin(admin.ModelAdmin):
    list_display = ('title', 'regulation_type', 'created_at')
    list_filter = ('regulation_type',)
    search_fields = ('title', 'description')
    inlines = [ChecklistItemInline]

@admin.register(TrademarkRequest)
class TrademarkRequestAdmin(admin.ModelAdmin):
    list_display = ('mark_text', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('mark_text', 'description')

@admin.register(LegalTask)
class LegalTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'priority', 'status', 'due_date', 'assigned_to')
    list_filter = ('priority', 'status')
    search_fields = ('title', 'description')

class DueDiligenceTaskInline(admin.TabularInline):
    model = DueDiligenceTask
    extra = 1

class DueDiligenceRiskInline(admin.TabularInline):
    model = DueDiligenceRisk
    extra = 1

@admin.register(DueDiligenceProcess)
class DueDiligenceProcessAdmin(admin.ModelAdmin):
    list_display = ('title', 'target_company', 'transaction_type', 'status', 'target_completion_date')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('title', 'target_company')
    inlines = [DueDiligenceTaskInline, DueDiligenceRiskInline]

@admin.register(DueDiligenceTask)
class DueDiligenceTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'process', 'category', 'status', 'assigned_to', 'due_date')
    list_filter = ('category', 'status', 'process')
    search_fields = ('title', 'description')

@admin.register(DueDiligenceRisk)
class DueDiligenceRiskAdmin(admin.ModelAdmin):
    list_display = ('title', 'process', 'risk_level', 'category', 'owner')
    list_filter = ('risk_level', 'category', 'process')
    search_fields = ('title', 'description')

class BudgetExpenseInline(admin.TabularInline):
    model = BudgetExpense
    extra = 1

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('department', 'year', 'quarter', 'allocated_amount')
    list_filter = ('year', 'quarter', 'department')
    search_fields = ('department',)
    inlines = [BudgetExpenseInline]

@admin.register(BudgetExpense)
class BudgetExpenseAdmin(admin.ModelAdmin):
    list_display = ['budget', 'description', 'amount', 'category', 'date', 'created_by']
    list_filter = ['category', 'date', 'created_at']
    search_fields = ['description', 'budget__department']
    date_hierarchy = 'date'

class WorkflowStepInline(admin.TabularInline):
    model = WorkflowStep
    extra = 1
    ordering = ['-created_at']

@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at']

@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'category', 'parent_template', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at',)

@admin.register(WorkflowTemplateStep)
class WorkflowTemplateStepAdmin(admin.ModelAdmin):
    list_display = ['template', 'name', 'order']
    list_filter = ['template']
    search_fields = ['template__name', 'name']
    ordering = ['template', 'order']

@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    list_display = ['workflow', 'name', 'status', 'assigned_to', 'due_date']
    list_filter = ['status', 'due_date']
    search_fields = ['workflow__title', 'name']

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['title', 'organization', 'status', 'counterparty', 'value', 'start_date', 'end_date', 'created_at', 'is_expiring_soon']
    list_filter = ['organization', 'status', 'created_at', 'start_date', ExpiringContractFilter]
    search_fields = ['title', 'content', 'counterparty']
    ordering = ['-created_at']

    @admin.display(boolean=True, description='Expiring <=30d')
    def is_expiring_soon(self, obj):
        return bool(
            obj.status == 'ACTIVE' and obj.end_date and timezone.localdate() <= obj.end_date <= timezone.localdate() + timedelta(days=30)
        )


class OrganizationScopedAdmin(admin.ModelAdmin):
    list_filter = ['organization']


@admin.register(Counterparty)
class CounterpartyAdmin(OrganizationScopedAdmin):
    list_display = ['name', 'organization', 'entity_type', 'jurisdiction', 'is_active']
    search_fields = ['name', 'jurisdiction']


@admin.register(ClauseCategory)
class ClauseCategoryAdmin(OrganizationScopedAdmin):
    list_display = ['name', 'organization', 'order']
    search_fields = ['name', 'description']


@admin.register(ClauseTemplate)
class ClauseTemplateAdmin(OrganizationScopedAdmin):
    list_display = ['title', 'organization', 'category', 'jurisdiction_scope', 'is_approved']
    search_fields = ['title', 'content', 'tags']


@admin.register(SignatureRequest)
class SignatureRequestAdmin(OrganizationScopedAdmin):
    list_display = ['signer_email', 'organization', 'case_record', 'status', 'created_at']
    search_fields = ['signer_name', 'signer_email', 'contract__title']

    @admin.display(description='Case')
    def case_record(self, obj):
        return obj.contract


@admin.register(DataInventoryRecord)
class DataInventoryRecordAdmin(OrganizationScopedAdmin):
    list_display = ['title', 'organization', 'client', 'lawful_basis', 'updated_at']
    search_fields = ['title', 'client__name']


@admin.register(DSARRequest)
class DSARRequestAdmin(OrganizationScopedAdmin):
    list_display = ['reference_number', 'organization', 'request_type', 'status', 'due_date', 'is_overdue']
    list_filter = ['organization', 'status', 'request_type', OverdueDSARFilter]
    search_fields = ['reference_number', 'requester_name', 'requester_email']

    @admin.display(boolean=True, description='Overdue')
    def is_overdue(self, obj):
        return obj.is_overdue


@admin.register(Subprocessor)
class SubprocessorAdmin(OrganizationScopedAdmin):
    list_display = ['name', 'organization', 'service_type', 'country', 'risk_level']
    search_fields = ['name', 'service_type', 'country']


@admin.register(TransferRecord)
class TransferRecordAdmin(OrganizationScopedAdmin):
    list_display = ['title', 'organization', 'source_country', 'destination_country', 'transfer_mechanism']
    search_fields = ['title', 'source_country', 'destination_country']


@admin.register(RetentionPolicy)
class RetentionPolicyAdmin(OrganizationScopedAdmin):
    list_display = ['title', 'organization', 'category', 'retention_period_days', 'is_active']
    search_fields = ['title', 'category']


@admin.register(LegalHold)
class LegalHoldAdmin(OrganizationScopedAdmin):
    list_display = ['title', 'organization', 'status', 'case_matter', 'client', 'hold_start_date']
    search_fields = ['title', 'description']

    @admin.display(description='Case matter')
    def case_matter(self, obj):
        return obj.matter


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(OrganizationScopedAdmin):
    list_display = ['name', 'organization', 'trigger_type', 'approval_step', 'approver_role', 'is_active']
    search_fields = ['name', 'trigger_value']


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(OrganizationScopedAdmin):
    list_display = ['case_record', 'organization', 'approval_step', 'status', 'assigned_to', 'created_at', 'due_date', 'is_overdue']
    list_filter = ['organization', 'status', 'approval_step', OverdueApprovalFilter]
    search_fields = ['contract__title', 'approval_step', 'comments']

    @admin.display(description='Case')
    def case_record(self, obj):
        return obj.contract

    @admin.display(boolean=True, description='Overdue')
    def is_overdue(self, obj):
        return bool(obj.status == 'PENDING' and obj.due_date and obj.due_date < timezone.now())


@admin.register(EthicalWall)
class EthicalWallAdmin(OrganizationScopedAdmin):
    list_display = ['name', 'organization', 'case_matter', 'client', 'is_active']
    search_fields = ['name', 'description']

    @admin.display(description='Case matter')
    def case_matter(self, obj):
        return obj.matter
