from django.contrib import admin
from .models import (
    TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep, ChecklistItem,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk, Budget, BudgetExpense
)

@admin.register(RiskLog)
class RiskLogAdmin(admin.ModelAdmin):
    list_display = ('title', 'risk_level', 'mitigation_status', 'owner', 'linked_contract')
    list_filter = ('risk_level', 'mitigation_status', 'owner')
    search_fields = ('title', 'description', 'mitigation_steps')
    autocomplete_fields = ['owner', 'linked_contract']

class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 1

@admin.register(ComplianceChecklist)
class ComplianceChecklistAdmin(admin.ModelAdmin):
    list_display = ('name', 'regulation', 'status', 'due_date', 'reviewed_by')
    list_filter = ('status', 'due_date', 'reviewed_by')
    search_fields = ('name', 'regulation')
    autocomplete_fields = ['reviewed_by']
    inlines = [ChecklistItemInline]


@admin.register(TrademarkRequest)
class TrademarkRequestAdmin(admin.ModelAdmin):
    list_display = ('region', 'class_number', 'status', 'request_date', 'renewal_deadline', 'owner')
    list_filter = ('status', 'region')
    search_fields = ('region', 'class_number')
    autocomplete_fields = ['owner']

class DueDiligenceItemInline(admin.TabularInline):
    model = DueDiligenceItem
    extra = 1

class DueDiligenceRiskInline(admin.TabularInline):
    model = DueDiligenceRisk
    extra = 1

@admin.register(DueDiligenceProcess)
class DueDiligenceProcessAdmin(admin.ModelAdmin):
    list_display = ('title', 'target_company', 'transaction_type', 'status', 'expected_closing', 'created_by')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('title', 'target_company')
    autocomplete_fields = ['lead_attorney', 'assigned_team', 'created_by']
    inlines = [DueDiligenceItemInline, DueDiligenceRiskInline]

@admin.register(DueDiligenceRisk)
class DueDiligenceRiskAdmin(admin.ModelAdmin):
    list_display = ('title', 'due_diligence', 'risk_level', 'category', 'owner')
    list_filter = ('risk_level', 'category', 'due_diligence')
    search_fields = ('title', 'description')
    autocomplete_fields = ['due_diligence', 'owner']

class ExpenseInline(admin.TabularInline):
    model = BudgetExpense
    extra = 1

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'quarter', 'department', 'total_budget', 'status', 'owner')
    list_filter = ('year', 'quarter', 'status', 'department')
    search_fields = ('name', 'department')
    autocomplete_fields = ['owner', 'created_by']
    inlines = [ExpenseInline]

@admin.register(BudgetExpense)
class BudgetExpenseAdmin(admin.ModelAdmin):
    list_display = ('description', 'budget', 'category', 'amount', 'expense_date', 'created_by')
    list_filter = ('category', 'expense_date', 'budget')
    search_fields = ('description', 'vendor')
    autocomplete_fields = ['budget', 'created_by']

@admin.register(LegalTask)
class LegalTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'task_type', 'priority', 'status', 'assigned_to', 'due_date')
    list_filter = ('status', 'priority', 'is_recurring', 'assigned_to')
    search_fields = ('title', 'subject')
    autocomplete_fields = ['assigned_to']


class WorkflowStepInline(admin.TabularInline):
    model = WorkflowStep
    extra = 1
    autocomplete_fields = ['assigned_to']
    ordering = ['-created_at']

class ContractVersionInline(admin.TabularInline):
    model = ContractVersion
    extra = 0
    readonly_fields = ('timestamp',)
    ordering = ['-version_number']

class NegotiationThreadInline(admin.TabularInline):
    model = NegotiationThread
    extra = 0
    readonly_fields = ('timestamp', 'author')
    autocomplete_fields = ['author']
    ordering = ['-timestamp']

@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'description')
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    autocomplete_fields = ['created_by']

@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_by', 'created_at')
    autocomplete_fields = ['created_by']

@admin.register(WorkflowTemplateStep)
class WorkflowTemplateStepAdmin(admin.ModelAdmin):
    list_display = ('template', 'step_name', 'order')
    list_filter = ('template',)
    search_fields = ('step_name', 'description')
    autocomplete_fields = ['template']

@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    list_display = ('contract', 'step_type', 'assigned_to', 'status', 'due_date')
    list_filter = ('status', 'step_type', 'assigned_to')
    search_fields = ('contract__title', 'notes')
    autocomplete_fields = ['contract', 'assigned_to']


@admin.register(ContractVersion)
class ContractVersionAdmin(admin.ModelAdmin):
    list_display = ('contract', 'version_number', 'approved_by', 'timestamp')
    list_filter = ('timestamp', 'approved_by')
    search_fields = ('contract__title', 'content_snapshot')
    autocomplete_fields = ['contract', 'approved_by']


@admin.register(NegotiationThread)
class NegotiationThreadAdmin(admin.ModelAdmin):
    list_display = ('contract', 'round_number', 'author', 'timestamp')
    list_filter = ('timestamp', 'author')
    search_fields = ('contract__title', 'internal_note', 'external_note')
    autocomplete_fields = ['contract', 'author']