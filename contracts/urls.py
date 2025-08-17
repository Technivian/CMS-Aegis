from django.urls import path
from . import views

app_name = 'contracts'

urlpatterns = [
    path('', views.ContractListView.as_view(), name='contract_list'),
    path('trademarks/', views.TrademarkRequestListView.as_view(), name='trademark_request_list'),
    path('trademarks/new/', views.TrademarkRequestCreateView.as_view(), name='trademark_request_create'),
    path('trademarks/<int:pk>/', views.TrademarkRequestDetailView.as_view(), name='trademark_request_detail'),
    path('trademarks/<int:pk>/edit/', views.TrademarkRequestUpdateView.as_view(), name='trademark_request_update'),

    # Risk Logs
    path('risks/', views.RiskLogListView.as_view(), name='risk_log_list'),
    path('risks/new/', views.RiskLogCreateView.as_view(), name='risk_log_create'),
    path('risks/<int:pk>/edit/', views.RiskLogUpdateView.as_view(), name='risk_log_update'),

    # Legal Tasks
    path('legal-tasks/', views.LegalTaskKanbanView.as_view(), name='legal_task_board'),
    path('legal-tasks/new/', views.LegalTaskCreateView.as_view(), name='legal_task_create'),
    path('legal-tasks/<int:pk>/edit/', views.LegalTaskUpdateView.as_view(), name='legal_task_update'),

    # Compliance Checklists
    path('compliance/', views.ComplianceChecklistListView.as_view(), name='compliance_checklist_list'),
    path('compliance/new/', views.ComplianceChecklistCreateView.as_view(), name='compliance_checklist_create'),
    path('compliance/<int:pk>/', views.ComplianceChecklistDetailView.as_view(), name='compliance_checklist_detail'),
    path('compliance/<int:pk>/edit/', views.ComplianceChecklistUpdateView.as_view(), name='compliance_checklist_update'),
    path('compliance/item/<int:pk>/toggle/', views.ToggleChecklistItemView.as_view(), name='toggle_checklist_item'),
    path('compliance/<int:pk>/add_item/', views.AddChecklistItemView.as_view(), name='add_checklist_item'),

    # Contracts
    path('<int:pk>/', views.ContractDetailView.as_view(), name='contract_detail'),
    path('new/', views.ContractCreateView.as_view(), name='contract_create'),
    path('<int:pk>/edit/', views.ContractUpdateView.as_view(), name='contract_update'),
    path('<int:pk>/add_note/', views.AddNegotiationNoteView.as_view(), name='add_negotiation_note'),
]
