from django.urls import path
from .views import (
    ContractListView, ContractDetailView, ContractCreateView, ContractUpdateView, AddNegotiationNoteView,
    TrademarkRequestListView, TrademarkRequestDetailView, TrademarkRequestCreateView, TrademarkRequestUpdateView,
    LegalTaskKanbanView, LegalTaskCreateView, LegalTaskUpdateView,
    RiskLogListView, RiskLogCreateView, RiskLogUpdateView,
    ComplianceChecklistListView, ComplianceChecklistDetailView, ComplianceChecklistCreateView, ComplianceChecklistUpdateView,
    ToggleChecklistItemView, AddChecklistItemView,
    WorkflowDashboardView, WorkflowTemplateListView, WorkflowCreateView, WorkflowTemplateCreateView,
    WorkflowDetailView, WorkflowStepUpdateView, WorkflowStepCompleteView,
    RepositoryView, WorkflowCreateView as WorkflowCreateFormView,
    DueDiligenceListView, DueDiligenceCreateView, DueDiligenceDetailView, DueDiligenceUpdateView, AddDueDiligenceItemView, AddDueDiligenceRiskView,
    BudgetListView, BudgetCreateView, BudgetDetailView, BudgetUpdateView, AddExpenseView,
    workflow_create, workflow_template_create, workflow_template_list, toggle_dd_item
)
from .api import views as api_views
from django.contrib.auth import views as auth_views
from .forms import UserRegistrationForm # Assuming you have this form

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
    path('due-diligence/<int:pk>/add-item/', AddDueDiligenceItemView.as_view(), name='add_dd_item'),
    path('due-diligence/<int:pk>/add-risk/', AddDueDiligenceRiskView.as_view(), name='add_dd_risk'),
    path('dd-item/<int:pk>/toggle/', toggle_dd_item, name='toggle_dd_item'),

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
    path('budgets/<int:pk>/add-expense/', AddExpenseView.as_view(), name='add_expense'),

    # Workflow URLs
    path('workflow-dashboard/', WorkflowDashboardView.as_view(), name='workflow_dashboard'),
    path('workflows/<int:pk>/', WorkflowDetailView.as_view(), name='workflow_detail'),
    path('workflows/create/', WorkflowCreateView.as_view(), name='workflow_create'),
    path('workflows/step/<int:pk>/update/', WorkflowStepUpdateView.as_view(), name='update_workflow_step'),
    path('workflows/step/<int:pk>/complete/', WorkflowStepCompleteView.as_view(), name='complete_workflow_step'),
    path('workflow-templates/', WorkflowTemplateListView.as_view(), name='workflow_template_list'),
    path('workflow-templates/create/', WorkflowTemplateCreateView.as_view(), name='workflow_template_create'),

    # Contracts
    path('', ContractListView.as_view(), name='contract_list'),
    path('<int:pk>/', ContractDetailView.as_view(), name='contract_detail'),
    path('new/', ContractCreateView.as_view(), name='contract_create'),
    path('<int:pk>/edit/', ContractUpdateView.as_view(), name='contract_update'),
    path('<int:pk>/add_note/', AddNegotiationNoteView.as_view(), name='add_negotiation_note'),

    # Authentication URLs
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', views.register_view, name='register'), # Assuming you have a register view function in your views.py
]