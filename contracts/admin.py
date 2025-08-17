from django.contrib import admin
from .models import (
    Contract, Tag, Note, WorkflowStep, ContractVersion, NegotiationThread,
    TrademarkRequest, LegalTask, RiskLog, ComplianceChecklist, ChecklistItem
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

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('title', 'counterparty', 'status', 'contract_type', 'created_by', 'updated_at')
    list_filter = ('status', 'contract_type', 'jurisdiction')
    search_fields = ('title', 'counterparty')
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    autocomplete_fields = ['tags', 'created_by']
    inlines = [WorkflowStepInline, ContractVersionInline, NegotiationThreadInline]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('contract', 'created_by', 'timestamp')
    list_filter = ('timestamp', 'created_by')
    search_fields = ('text', 'contract__title')
    readonly_fields = ('created_by', 'timestamp')
    autocomplete_fields = ['contract', 'created_by']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('contract', 'created_by')


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
