from django.urls import path
from .views import (
    ContractListView, TrademarkRequestListView, TrademarkRequestCreateView,
    TrademarkRequestDetailView, TrademarkRequestUpdateView, RiskLogListView,
    RiskLogCreateView, RiskLogUpdateView, LegalTaskKanbanView,
    LegalTaskCreateView, LegalTaskUpdateView, ComplianceChecklistListView,
    ComplianceChecklistCreateView, ComplianceChecklistDetailView,
    ComplianceChecklistUpdateView, ToggleChecklistItemView, AddChecklistItemView,

    RepositoryView,

    ContractDetailView, ContractCreateView, ContractUpdateView,
    AddNegotiationNoteView, WorkflowDashboardView, WorkflowDetailView,
    WorkflowCreateView, WorkflowStepUpdateView, WorkflowStepCompleteView,
    WorkflowTemplateListView
)

app_name = 'contracts'

urlpatterns = [
    path('', ContractListView.as_view(), name='contract_list'),
    path('repository/', RepositoryView.as_view(), name='repository'),
    path('trademarks/', TrademarkRequestListView.as_view(), name='trademark_request_list'),
    path('trademarks/new/', TrademarkRequestCreateView.as_view(), name='trademark_request_create'),
    path('trademarks/<int:pk>/', TrademarkRequestDetailView.as_view(), name='trademark_request_detail'),
    path('trademarks/<int:pk>/edit/', TrademarkRequestUpdateView.as_view(), name='trademark_request_update'),

    # Risk Logs
    path('risks/', RiskLogListView.as_view(), name='risk_log_list'),
    path('risks/new/', RiskLogCreateView.as_view(), name='risk_log_create'),
    path('risks/<int:pk>/edit/', RiskLogUpdateView.as_view(), name='risk_log_update'),

    # Legal Tasks
    path('legal-tasks/', LegalTaskKanbanView.as_view(), name='legal_task_board'),
    path('legal-tasks/new/', LegalTaskCreateView.as_view(), name='legal_task_create'),
    path('legal-tasks/<int:pk>/edit/', LegalTaskUpdateView.as_view(), name='legal_task_update'),

    # Compliance Checklists
    path('compliance/', ComplianceChecklistListView.as_view(), name='compliance_checklist_list'),
    path('compliance/create/', ComplianceChecklistCreateView.as_view(), name='compliance_checklist_create'),
    path('compliance/<int:pk>/', ComplianceChecklistDetailView.as_view(), name='compliance_checklist_detail'),
    path('compliance/<int:pk>/toggle-item/<int:item_pk>/', ToggleChecklistItemView.as_view(), name='toggle_checklist_item'),

    # Workflow URLs
    path('workflow-dashboard/', WorkflowDashboardView.as_view(), name='workflow_dashboard'),
    path('workflows/<int:pk>/', WorkflowDetailView.as_view(), name='workflow_detail'),
    path('workflows/create/', WorkflowCreateView.as_view(), name='workflow_create'),
    path('workflows/step/<int:pk>/update/', WorkflowStepUpdateView.as_view(), name='update_workflow_step'),
    path('workflows/step/<int:pk>/complete/', WorkflowStepCompleteView.as_view(), name='complete_workflow_step'),
    path('workflow-templates/', WorkflowTemplateListView.as_view(), name='workflow_template_list'),

    # Contracts
    path('', ContractListView.as_view(), name='contract_list'),
    path('<int:pk>/', ContractDetailView.as_view(), name='contract_detail'),
    path('new/', ContractCreateView.as_view(), name='contract_create'),
    path('<int:pk>/edit/', ContractUpdateView.as_view(), name='contract_update'),
    path('<int:pk>/add_note/', AddNegotiationNoteView.as_view(), name='add_negotiation_note'),
]