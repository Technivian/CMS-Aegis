from django.urls import path
from . import views
from .api import views as api_views
from .views import (
    DueDiligenceListView, DueDiligenceCreateView, DueDiligenceDetailView, 
    DueDiligenceUpdateView, AddDueDiligenceItemView, AddDueDiligenceRiskView,
    LegalTaskKanbanView, LegalTaskCreateView, LegalTaskUpdateView,
    TrademarkRequestListView, TrademarkRequestCreateView, TrademarkRequestDetailView, TrademarkRequestUpdateView,
    RiskLogListView, RiskLogCreateView, RiskLogUpdateView,
    ComplianceChecklistListView, ComplianceChecklistCreateView, ComplianceChecklistDetailView, 
    ComplianceChecklistUpdateView, ToggleChecklistItemView, AddChecklistItemView,
    BudgetListView, BudgetCreateView, BudgetDetailView, BudgetUpdateView, AddExpenseView,
    WorkflowTemplateListView, RepositoryView, ContractListView, ContractDetailView, 
    ContractCreateView, ContractUpdateView, AddNegotiationNoteView
)

app_name = 'contracts'

urlpatterns = [
    # API endpoints
    path('api/contracts/', api_views.contracts_api, name='contracts_api'),
    path('api/contracts/bulk-update/', api_views.bulk_update_contracts, name='bulk_update_contracts'),
    path('api/contracts/<str:contract_id>/', api_views.contract_detail_api, name='contract_detail_api'),

    # Due Diligence URLs
    path('due-diligence/', DueDiligenceListView.as_view(), name='due_diligence_list'),
    path('due-diligence/new/', DueDiligenceCreateView.as_view(), name='due_diligence_create'),
    path('due-diligence/<int:pk>/', DueDiligenceDetailView.as_view(), name='due_diligence_detail'),
    path('due-diligence/<int:pk>/edit/', DueDiligenceUpdateView.as_view(), name='due_diligence_update'),
    path('due-diligence/<int:process_pk>/add-item/', AddDueDiligenceItemView.as_view(), name='add_dd_item'),
    path('due-diligence/<int:process_pk>/add-risk/', AddDueDiligenceRiskView.as_view(), name='add_dd_risk'),
    path('dd-item/<int:pk>/toggle/', views.toggle_dd_item, name='toggle_dd_item'),

    # Legal Task URLs
    path('legal-tasks/', LegalTaskKanbanView.as_view(), name='legal_task_kanban'),
    path('legal-tasks/new/', LegalTaskCreateView.as_view(), name='legal_task_create'),
    path('legal-tasks/<int:pk>/edit/', LegalTaskUpdateView.as_view(), name='legal_task_update'),

    # Trademark Request URLs
    path('trademarks/', TrademarkRequestListView.as_view(), name='trademark_request_list'),
    path('trademarks/new/', TrademarkRequestCreateView.as_view(), name='trademark_request_create'),
    path('trademarks/<int:pk>/', TrademarkRequestDetailView.as_view(), name='trademark_request_detail'),
    path('trademarks/<int:pk>/edit/', TrademarkRequestUpdateView.as_view(), name='trademark_request_update'),

    # Risk Log URLs
    path('risks/', RiskLogListView.as_view(), name='risk_log_list'),
    path('risks/new/', RiskLogCreateView.as_view(), name='risk_log_create'),
    path('risks/<int:pk>/edit/', RiskLogUpdateView.as_view(), name='risk_log_update'),

    # Compliance Checklist URLs
    path('compliance/', ComplianceChecklistListView.as_view(), name='compliance_checklist_list'),
    path('compliance/new/', ComplianceChecklistCreateView.as_view(), name='compliance_checklist_create'),
    path('compliance/<int:pk>/', ComplianceChecklistDetailView.as_view(), name='compliance_checklist_detail'),
    path('compliance/<int:pk>/edit/', ComplianceChecklistUpdateView.as_view(), name='compliance_checklist_update'),
    path('compliance/<int:pk>/toggle-item/', ToggleChecklistItemView.as_view(), name='toggle_checklist_item'),
    path('compliance/<int:pk>/add-item/', AddChecklistItemView.as_view(), name='add_checklist_item'),

    # Budget URLs
    path('budgets/', BudgetListView.as_view(), name='budget_list'),
    path('budgets/new/', BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/<int:pk>/', BudgetDetailView.as_view(), name='budget_detail'),
    path('budgets/<int:pk>/edit/', BudgetUpdateView.as_view(), name='budget_update'),
    path('budgets/<int:budget_pk>/add-expense/', AddExpenseView.as_view(), name='add_expense'),

    # Workflow URLs
    path('workflows/', views.workflow_dashboard, name='workflow_dashboard'),
    path('workflows/create/', views.workflow_create, name='workflow_create'),
    path('workflows/templates/', views.workflow_template_list, name='workflow_template_list'),
    path('workflows/templates/create/', views.workflow_template_create, name='workflow_template_create'),
    path('workflows/templates/<int:pk>/', views.workflow_template_detail, name='workflow_template_detail'),
    path('workflows/<int:pk>/', views.workflow_detail, name='workflow_detail'),

    # Templates
    path('templates/', WorkflowTemplateListView.as_view(), name='templates_list'),

    # Repository
    path('repository/', RepositoryView.as_view(), name='repository'),

    # Contracts
    path('', ContractListView.as_view(), name='contract_list'),
    path('<int:pk>/', ContractDetailView.as_view(), name='contract_detail'),
    path('new/', ContractCreateView.as_view(), name='contract_create'),
    path('<int:pk>/edit/', ContractUpdateView.as_view(), name='contract_update'),
    path('<int:pk>/add_note/', AddNegotiationNoteView.as_view(), name='add_negotiation_note'),
]