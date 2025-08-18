from django.contrib import admin
from .models import (
    TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist,
    Workflow, WorkflowTemplate, WorkflowTemplateStep, WorkflowStep, ChecklistItem,
    DueDiligenceProcess, DueDiligenceTask, DueDiligenceRisk, Budget, BudgetExpense
)

@admin.register(RiskLog)
class RiskLogAdmin(admin.ModelAdmin):
    list_display = ('title', 'risk_level', 'created_at')
    list_filter = ('risk_level',)
    search_fields = ('title', 'description')

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
    list_display = ('description', 'budget', 'category', 'amount', 'date')
    list_filter = ('category', 'date', 'budget')
    search_fields = ('description',)

class WorkflowStepInline(admin.TabularInline):
    model = WorkflowStep
    extra = 1
    ordering = ['-created_at']

@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at',)

@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at',)

@admin.register(WorkflowTemplateStep)
class WorkflowTemplateStepAdmin(admin.ModelAdmin):
    list_display = ('template', 'title', 'order')
    list_filter = ('template',)
    search_fields = ('title', 'description')

@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'title', 'assigned_to', 'status', 'due_date')
    list_filter = ('status', 'assigned_to')
    search_fields = ('workflow__title', 'title')