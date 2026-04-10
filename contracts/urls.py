from django.urls import path
from . import views
from .api import views as api_views

app_name = 'contracts'

urlpatterns = [
    # API
    path('api/cases/', api_views.contracts_api, name='cases_api'),
    path('api/cases/bulk-update/', api_views.cases_bulk_update_api, name='cases_bulk_update_api'),
    path('api/cases/<str:case_id>/', api_views.case_detail_api, name='case_detail_api'),

    # Care core
    path('clients/', views.ClientListView.as_view(), name='client_list'),
    path('clients/new/', views.ClientCreateView.as_view(), name='client_create'),
    path('clients/<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('clients/<int:pk>/edit/', views.ClientUpdateView.as_view(), name='client_update'),

    # Municipality & Regional Configurations
    path('gemeenten/', views.MunicipalityConfigurationListView.as_view(), name='municipality_list'),
    path('gemeenten/new/', views.MunicipalityConfigurationCreateView.as_view(), name='municipality_create'),
    path('gemeenten/<int:pk>/', views.MunicipalityConfigurationDetailView.as_view(), name='municipality_detail'),
    path('gemeenten/<int:pk>/edit/', views.MunicipalityConfigurationUpdateView.as_view(), name='municipality_update'),

    path("regio's/", views.RegionalConfigurationListView.as_view(), name='regional_list'),
    path("regio's/new/", views.RegionalConfigurationCreateView.as_view(), name='regional_create'),
    path("regio's/<int:pk>/", views.RegionalConfigurationDetailView.as_view(), name='regional_detail'),
    path("regio's/<int:pk>/edit/", views.RegionalConfigurationUpdateView.as_view(), name='regional_update'),

    path('configuraties/', views.legacy_configuration_list_redirect, name='configuration_list'),
    path('configuraties/new/', views.legacy_configuration_create_redirect, name='configuration_create'),
    path('configuraties/<int:pk>/', views.CareConfigurationDetailView.as_view(), name='configuration_detail'),
    path('configuraties/<int:pk>/edit/', views.CareConfigurationUpdateView.as_view(), name='configuration_update'),

    path('documents/', views.DocumentListView.as_view(), name='document_list'),
    path('documents/new/', views.DocumentCreateView.as_view(), name='document_create'),
    path('documents/<int:pk>/', views.DocumentDetailView.as_view(), name='document_detail'),
    path('documents/<int:pk>/edit/', views.DocumentUpdateView.as_view(), name='document_update'),

    path('deadlines/', views.DeadlineListView.as_view(), name='deadline_list'),
    path('deadlines/new/', views.DeadlineCreateView.as_view(), name='deadline_create'),
    path('deadlines/<int:pk>/edit/', views.DeadlineUpdateView.as_view(), name='deadline_update'),
    path('deadlines/<int:pk>/complete/', views.deadline_complete, name='deadline_complete'),

    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/new/', views.BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/<int:pk>/', views.BudgetDetailView.as_view(), name='budget_detail'),
    path('budgets/<int:pk>/edit/', views.BudgetUpdateView.as_view(), name='budget_update'),
    path('budgets/<int:budget_pk>/add-expense/', views.AddExpenseView.as_view(), name='add_expense'),

    path('taken/', views.DeadlineListView.as_view(), name='task_list'),
    path('taken/', views.DeadlineListView.as_view(), name='task_kanban'),
    path('taken/new/', views.DeadlineCreateView.as_view(), name='task_create'),
    path('taken/<int:pk>/edit/', views.DeadlineUpdateView.as_view(), name='task_update'),
    path('tasks/', views.LegalTaskKanbanView.as_view(), name='legal_task_kanban'),
    path('tasks/new/', views.LegalTaskCreateView.as_view(), name='legal_task_create'),
    path('tasks/<int:pk>/edit/', views.LegalTaskUpdateView.as_view(), name='legal_task_update'),

    path('audit-log/', views.AuditLogListView.as_view(), name='audit_log_list'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),

    path('organizations/switch/', views.switch_organization, name='switch_organization'),
    path('organizations/team/', views.organization_team, name='organization_team'),
    path('organizations/invitations/<uuid:token>/accept/', views.accept_organization_invite, name='accept_organization_invite'),
    path('organizations/invitations/<int:invite_id>/revoke/', views.revoke_organization_invite, name='revoke_organization_invite'),
    path('organizations/invitations/<int:invite_id>/resend/', views.resend_organization_invite, name='resend_organization_invite'),
    path('organizations/members/<int:membership_id>/role/', views.update_membership_role, name='update_membership_role'),
    path('organizations/members/<int:membership_id>/deactivate/', views.deactivate_organization_member, name='deactivate_organization_member'),
    path('organizations/members/<int:membership_id>/reactivate/', views.reactivate_organization_member, name='reactivate_organization_member'),
    path('organizations/activity/', views.organization_activity, name='organization_activity'),
    path('organizations/activity/export/', views.organization_activity_export, name='organization_activity_export'),

    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('search/', views.global_search, name='global_search'),

    path('wachttijden/', views.DeadlineListView.as_view(), name='waittime_list'),
    path('wachttijden/new/', views.DeadlineCreateView.as_view(), name='waittime_create'),
    path('wachttijden/<int:pk>/', views.DeadlineUpdateView.as_view(), name='waittime_detail'),
    path('wachttijden/<int:pk>/edit/', views.DeadlineUpdateView.as_view(), name='waittime_update'),

    path('intakes/', views.case_flow_list_redirect, {'step': 'intake'}, name='intake_list'),
    path('intakes/new/', views.case_flow_create_redirect, {'step': 'intake'}, name='intake_create'),
    path('intakes/<int:pk>/', views.case_flow_detail_redirect, name='intake_detail'),
    path('intakes/<int:pk>/edit/', views.case_flow_update_redirect, name='intake_update'),

    path('matching/', views.matching_dashboard, name='matching_dashboard'),
    path('workflows/', views.reports_dashboard, name='workflow_dashboard'),
    path('workflows/<int:pk>/', views.MatterDetailView.as_view(), name='workflow_detail'),
    path('workflows/step/<int:pk>/update/', views.MatterUpdateView.as_view(), name='update_workflow_step'),


    path('plaatsingen/', views.case_flow_list_redirect, {'step': 'placement'}, name='placement_list'),
    path('plaatsingen/new/', views.case_flow_create_redirect, {'step': 'placement'}, name='placement_create'),
    path('plaatsingen/<int:pk>/', views.MatterDetailView.as_view(), name='placement_detail'),
    path('plaatsingen/<int:pk>/edit/', views.MatterUpdateView.as_view(), name='placement_update'),

    path('signalen/', views.MatterListView.as_view(), name='signal_list'),
    path('signalen/new/', views.MatterCreateView.as_view(), name='signal_create'),
    path('signalen/<int:pk>/edit/', views.MatterUpdateView.as_view(), name='signal_update'),
    path('risks/', views.MatterListView.as_view(), name='risk_log_list'),
    path('risks/new/', views.MatterCreateView.as_view(), name='risk_log_create'),
    path('risks/<int:pk>/edit/', views.MatterUpdateView.as_view(), name='risk_log_update'),

    path('casussen/', views.DueDiligenceProcessListView.as_view(), name='case_list'),
    path('casussen/new/', views.DueDiligenceProcessCreateView.as_view(), name='case_create'),
    path('casussen/<int:pk>/', views.DueDiligenceProcessDetailView.as_view(), name='case_detail'),
    path('casussen/<int:pk>/edit/', views.DueDiligenceProcessUpdateView.as_view(), name='case_update'),

    # Assessments (Beoordelingen)
    path('beoordelingen/', views.CaseAssessmentListView.as_view(), name='assessment_list'),
    path('beoordelingen/new/', views.CaseAssessmentCreateView.as_view(), name='assessment_create'),
    path('beoordelingen/<int:pk>/', views.CaseAssessmentDetailView.as_view(), name='assessment_detail'),
    path('beoordelingen/<int:pk>/edit/', views.CaseAssessmentUpdateView.as_view(), name='assessment_update'),

    path('', views.CareConfigurationListView.as_view(), name='home'),
]
