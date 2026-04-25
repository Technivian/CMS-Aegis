from django.urls import path
from . import views
from .api import views as api_views

app_name = 'contracts'

urlpatterns = [
    path('scim/v2/Users', api_views.scim_users_api, name='scim_users_api'),
    path('scim/v2/Users/<str:scim_id>', api_views.scim_user_api, name='scim_user_api'),
    path('scim/v2/Groups', api_views.scim_groups_api, name='scim_groups_api'),
    path('scim/v2/Groups/<str:scim_id>', api_views.scim_group_api, name='scim_group_api'),
    path('saml/', views.saml_select, name='saml_select'),
    path('saml/<slug:organization_slug>/login/', views.saml_login, name='saml_login'),
    path('saml/<slug:organization_slug>/acs/', views.saml_acs, name='saml_acs'),
    path('saml/<slug:organization_slug>/logout/', views.saml_logout, name='saml_logout'),
    path('saml/<slug:organization_slug>/metadata/', views.saml_metadata, name='saml_metadata'),
    path('api/contracts/', api_views.contracts_api, name='contracts_api'),
    path('api/v1/contracts/', api_views.contracts_api_v1, name='contracts_api_v1'),
    path('api/v1/contracts/<str:contract_id>/', api_views.contract_detail_api_v1, name='contract_detail_api_v1'),
    path('api/contracts/bulk-update/', api_views.contracts_bulk_update_api, name='contracts_bulk_update_api'),
    path('api/contracts/<str:contract_id>/', api_views.contract_detail_api, name='contract_detail_api'),
    path('api/integrations/salesforce/status/', api_views.salesforce_connection_status_api, name='salesforce_connection_status_api'),
    path('api/integrations/salesforce/oauth/start/', api_views.salesforce_oauth_start_api, name='salesforce_oauth_start_api'),
    path('api/integrations/salesforce/oauth/callback/', api_views.salesforce_oauth_callback_api, name='salesforce_oauth_callback_api'),
    path('api/integrations/salesforce/disconnect/', api_views.salesforce_disconnect_api, name='salesforce_disconnect_api'),
    path('api/integrations/salesforce/field-map/', api_views.salesforce_field_map_api, name='salesforce_field_map_api'),
    path('api/integrations/salesforce/ingest-preview/', api_views.salesforce_ingest_preview_api, name='salesforce_ingest_preview_api'),
    path('api/integrations/salesforce/sync/', api_views.salesforce_sync_api, name='salesforce_sync_api'),
    path('api/integrations/salesforce/sync-runs/', api_views.salesforce_sync_runs_api, name='salesforce_sync_runs_api'),
    path('api/integrations/netsuite/sync/', api_views.netsuite_sync_api, name='netsuite_sync_api'),
    path('api/integrations/webhooks/deliveries/', api_views.webhook_deliveries_api, name='webhook_deliveries_api'),
    path('api/integrations/esign/webhook/', api_views.esign_webhook_api, name='esign_webhook_api'),
    path('api/analytics/executive/', api_views.executive_analytics_api, name='executive_analytics_api'),
    path('api/analytics/executive/presets/', api_views.executive_dashboard_presets_api, name='executive_dashboard_presets_api'),
    path('api/analytics/executive/presets/<int:preset_id>/', api_views.executive_dashboard_preset_delete_api, name='executive_dashboard_preset_delete_api'),

    # Clients
    path('clients/', views.ClientListView.as_view(), name='client_list'),
    path('clients/new/', views.ClientCreateView.as_view(), name='client_create'),
    path('clients/<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('clients/<int:pk>/edit/', views.ClientUpdateView.as_view(), name='client_update'),

    # Matters
    path('matters/', views.MatterListView.as_view(), name='matter_list'),
    path('matters/new/', views.MatterCreateView.as_view(), name='matter_create'),
    path('matters/<int:pk>/', views.MatterDetailView.as_view(), name='matter_detail'),
    path('matters/<int:pk>/edit/', views.MatterUpdateView.as_view(), name='matter_update'),

    # Documents
    path('documents/', views.DocumentListView.as_view(), name='document_list'),
    path('documents/new/', views.DocumentCreateView.as_view(), name='document_create'),
    path('documents/<int:pk>/', views.DocumentDetailView.as_view(), name='document_detail'),
    path('documents/<int:pk>/edit/', views.DocumentUpdateView.as_view(), name='document_update'),
    path('documents/<int:pk>/compare/<int:other_pk>/', views.DocumentCompareView.as_view(), name='document_compare'),
    path('documents/ocr-queue/', views.DocumentOCRQueueView.as_view(), name='document_ocr_queue'),
    path('documents/ocr-queue/<int:pk>/', views.DocumentOCRReviewUpdateView.as_view(), name='document_ocr_review'),

    # Time Entries
    path('time/', views.TimeEntryListView.as_view(), name='time_entry_list'),
    path('time/new/', views.TimeEntryCreateView.as_view(), name='time_entry_create'),
    path('time/<int:pk>/edit/', views.TimeEntryUpdateView.as_view(), name='time_entry_update'),

    # Invoices
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/new/', views.InvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.InvoiceUpdateView.as_view(), name='invoice_update'),

    # Trust Accounts
    path('trust-accounts/', views.TrustAccountListView.as_view(), name='trust_account_list'),
    path('trust-accounts/new/', views.TrustAccountCreateView.as_view(), name='trust_account_create'),
    path('trust-accounts/<int:pk>/', views.TrustAccountDetailView.as_view(), name='trust_account_detail'),
    path('trust-accounts/<int:account_pk>/add-transaction/', views.AddTrustTransactionView.as_view(), name='add_trust_transaction'),

    # Deadlines
    path('deadlines/', views.DeadlineListView.as_view(), name='deadline_list'),
    path('deadlines/new/', views.DeadlineCreateView.as_view(), name='deadline_create'),
    path('deadlines/<int:pk>/edit/', views.DeadlineUpdateView.as_view(), name='deadline_update'),
    path('deadlines/<int:pk>/complete/', views.deadline_complete, name='deadline_complete'),

    # Conflict Checks
    path('conflicts/', views.ConflictCheckListView.as_view(), name='conflict_check_list'),
    path('conflicts/new/', views.ConflictCheckCreateView.as_view(), name='conflict_check_create'),
    path('conflicts/<int:pk>/edit/', views.ConflictCheckUpdateView.as_view(), name='conflict_check_update'),

    # Audit Log
    path('audit-log/', views.AuditLogListView.as_view(), name='audit_log_list'),

    # Notifications
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
    path('organizations/members/<int:membership_id>/revoke-sessions/', views.revoke_member_sessions, name='revoke_member_sessions'),
    path('organizations/activity/', views.organization_activity, name='organization_activity'),
    path('organizations/activity/export/', views.organization_activity_export, name='organization_activity_export'),
    path('organizations/identity-telemetry/', views.identity_telemetry_dashboard, name='identity_telemetry_dashboard'),
    path('organizations/session-audit/', views.organization_session_audit, name='organization_session_audit'),
    path('organizations/session-audit/export/', views.organization_session_audit_export, name='organization_session_audit_export'),

    # Reports
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/export/', views.reports_export, name='reports_export'),

    # Due Diligence
    path('due-diligence/', views.DueDiligenceListView.as_view(), name='due_diligence_list'),
    path('due-diligence-processes/', views.DueDiligenceListView.as_view(), name='due_diligence_list_legacy'),
    path('due-diligence/new/', views.DueDiligenceCreateView.as_view(), name='due_diligence_create'),
    path('due-diligence/<int:pk>/', views.DueDiligenceDetailView.as_view(), name='due_diligence_detail'),
    path('due-diligence/<int:pk>/edit/', views.DueDiligenceUpdateView.as_view(), name='due_diligence_update'),
    path('due-diligence/<int:process_pk>/add-item/', views.AddDueDiligenceItemView.as_view(), name='add_dd_item'),
    path('due-diligence/<int:process_pk>/add-risk/', views.AddDueDiligenceRiskView.as_view(), name='add_dd_risk'),
    path('dd-item/<int:pk>/toggle/', views.toggle_dd_item, name='toggle_dd_item'),

    # Legal Tasks
    path('legal-tasks/', views.LegalTaskKanbanView.as_view(), name='legal_task_kanban'),
    path('legal-tasks/new/', views.LegalTaskCreateView.as_view(), name='legal_task_create'),
    path('legal-tasks/<int:pk>/edit/', views.LegalTaskUpdateView.as_view(), name='legal_task_update'),

    # Trademarks
    path('trademarks/', views.TrademarkRequestListView.as_view(), name='trademark_request_list'),
    path('trademark-requests/', views.TrademarkRequestListView.as_view(), name='trademark_request_list_legacy'),
    path('trademarks/new/', views.TrademarkRequestCreateView.as_view(), name='trademark_request_create'),
    path('trademarks/<int:pk>/', views.TrademarkRequestDetailView.as_view(), name='trademark_request_detail'),
    path('trademarks/<int:pk>/edit/', views.TrademarkRequestUpdateView.as_view(), name='trademark_request_update'),

    # Risks
    path('risks/', views.RiskLogListView.as_view(), name='risk_log_list'),
    path('risk-log/', views.RiskLogListView.as_view(), name='risk_log_list_legacy'),
    path('risks/new/', views.RiskLogCreateView.as_view(), name='risk_log_create'),
    path('risks/<int:pk>/edit/', views.RiskLogUpdateView.as_view(), name='risk_log_update'),

    # Compliance
    path('compliance/', views.ComplianceChecklistListView.as_view(), name='compliance_checklist_list'),
    path('compliance/new/', views.ComplianceChecklistCreateView.as_view(), name='compliance_checklist_create'),
    path('compliance/<int:pk>/', views.ComplianceChecklistDetailView.as_view(), name='compliance_checklist_detail'),
    path('compliance/<int:pk>/edit/', views.ComplianceChecklistUpdateView.as_view(), name='compliance_checklist_update'),
    path('compliance/<int:pk>/toggle-item/', views.ToggleChecklistItemView.as_view(), name='toggle_checklist_item'),
    path('compliance/<int:pk>/add-item/', views.AddChecklistItemView.as_view(), name='add_checklist_item'),

    # Budgets
    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/new/', views.BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/<int:pk>/', views.BudgetDetailView.as_view(), name='budget_detail'),
    path('budgets/<int:pk>/edit/', views.BudgetUpdateView.as_view(), name='budget_update'),
    path('budgets/<int:budget_pk>/add-expense/', views.AddExpenseView.as_view(), name='add_expense'),

    # Workflows
    path('workflows/', views.workflow_dashboard, name='workflow_dashboard'),
    path('workflow-dashboard/', views.workflow_dashboard, name='workflow_dashboard_legacy'),
    path('workflows/create/', views.workflow_create, name='workflow_create'),
    path('workflows/templates/', views.workflow_template_list, name='workflow_template_list'),
    path('workflows/templates/create/', views.workflow_template_create, name='workflow_template_create'),
    path('workflows/templates/<int:pk>/', views.workflow_template_detail, name='workflow_template_detail'),
    path('workflows/templates/<int:pk>/steps/add/', views.AddWorkflowTemplateStepView.as_view(), name='workflow_template_step_add'),
    path('workflows/templates/<int:pk>/clone-version/', views.workflow_template_clone_version, name='workflow_template_clone_version'),
    path('workflows/templates/<int:pk>/restore-version/', views.workflow_template_restore_version, name='workflow_template_restore_version'),
    path('workflows/templates/<int:pk>/compare/<int:other_pk>/', views.workflow_template_compare, name='workflow_template_compare'),
    path('workflows/<int:pk>/', views.workflow_detail, name='workflow_detail'),
    path('workflows/<int:pk>/steps/add/', views.AddWorkflowStepView.as_view(), name='workflow_step_add'),
    path('workflows/step/<int:pk>/complete/', views.WorkflowStepCompleteView.as_view(), name='workflow_step_complete'),
    path('workflows/step/<int:pk>/update/', views.update_workflow_step, name='update_workflow_step'),
    path('workflows/step/<int:pk>/edit/', views.WorkflowStepUpdateView.as_view(), name='workflow_step_update'),

    # Templates
    path('templates/', views.WorkflowTemplateListView.as_view(), name='templates_list'),

    # Repository
    path('repository/', views.RepositoryView.as_view(), name='repository'),

    # Counterparties
    path('counterparties/', views.CounterpartyListView.as_view(), name='counterparty_list'),
    path('counterparties/new/', views.CounterpartyCreateView.as_view(), name='counterparty_create'),
    path('counterparties/<int:pk>/', views.CounterpartyDetailView.as_view(), name='counterparty_detail'),
    path('counterparties/<int:pk>/edit/', views.CounterpartyUpdateView.as_view(), name='counterparty_update'),

    # Clause Library
    path('clause-categories/', views.ClauseCategoryListView.as_view(), name='clause_category_list'),
    path('clause-categories/new/', views.ClauseCategoryCreateView.as_view(), name='clause_category_create'),
    path('clause-categories/<int:pk>/edit/', views.ClauseCategoryUpdateView.as_view(), name='clause_category_update'),
    path('clause-library/', views.ClauseTemplateListView.as_view(), name='clause_template_list'),
    path('clause-library/new/', views.ClauseTemplateCreateView.as_view(), name='clause_template_create'),
    path('clause-library/<int:pk>/', views.ClauseTemplateDetailView.as_view(), name='clause_template_detail'),
    path('clause-library/<int:pk>/variants/add/', views.clause_variant_create, name='clause_variant_create'),
    path('clause-library/<int:pk>/playbooks/add/', views.clause_playbook_create, name='clause_playbook_create'),
    path('clause-library/<int:pk>/edit/', views.ClauseTemplateUpdateView.as_view(), name='clause_template_update'),
    path('search/save/', views.save_search_preset, name='save_search_preset'),
    path('search/presets/<int:preset_id>/delete/', views.delete_search_preset, name='delete_search_preset'),

    # Ethical Walls
    path('ethical-walls/', views.EthicalWallListView.as_view(), name='ethical_wall_list'),
    path('ethical-walls/new/', views.EthicalWallCreateView.as_view(), name='ethical_wall_create'),
    path('ethical-walls/<int:pk>/edit/', views.EthicalWallUpdateView.as_view(), name='ethical_wall_update'),

    # E-Signatures
    path('signatures/', views.SignatureRequestListView.as_view(), name='signature_request_list'),
    path('signatures/new/', views.SignatureRequestCreateView.as_view(), name='signature_request_create'),
    path('signatures/<int:pk>/', views.SignatureRequestDetailView.as_view(), name='signature_request_detail'),
    path('signatures/<int:pk>/edit/', views.SignatureRequestUpdateView.as_view(), name='signature_request_update'),
    path('signatures/<int:pk>/transition/<str:new_status>/', views.signature_request_transition, name='signature_request_transition'),
    path('signatures/<int:pk>/reminder/', views.signature_request_send_reminder, name='signature_request_send_reminder'),

    # Privacy & GDPR
    path('privacy/', views.privacy_dashboard, name='privacy_dashboard'),
    path('privacy/evidence-export/', views.privacy_evidence_export, name='privacy_evidence_export'),
    path('privacy/data-inventory/', views.DataInventoryListView.as_view(), name='data_inventory_list'),
    path('privacy/data-inventory/new/', views.DataInventoryCreateView.as_view(), name='data_inventory_create'),
    path('privacy/data-inventory/<int:pk>/', views.DataInventoryDetailView.as_view(), name='data_inventory_detail'),
    path('privacy/data-inventory/<int:pk>/edit/', views.DataInventoryUpdateView.as_view(), name='data_inventory_update'),
    path('privacy/dsar/', views.DSARRequestListView.as_view(), name='dsar_list'),
    path('privacy/dsar/new/', views.DSARRequestCreateView.as_view(), name='dsar_create'),
    path('privacy/dsar/<int:pk>/', views.DSARRequestDetailView.as_view(), name='dsar_detail'),
    path('privacy/dsar/<int:pk>/edit/', views.DSARRequestUpdateView.as_view(), name='dsar_update'),
    path('privacy/subprocessors/', views.SubprocessorListView.as_view(), name='subprocessor_list'),
    path('privacy/subprocessors/new/', views.SubprocessorCreateView.as_view(), name='subprocessor_create'),
    path('privacy/subprocessors/<int:pk>/', views.SubprocessorDetailView.as_view(), name='subprocessor_detail'),
    path('privacy/subprocessors/<int:pk>/edit/', views.SubprocessorUpdateView.as_view(), name='subprocessor_update'),
    path('privacy/transfers/', views.TransferRecordListView.as_view(), name='transfer_record_list'),
    path('privacy/transfers/new/', views.TransferRecordCreateView.as_view(), name='transfer_record_create'),
    path('privacy/transfers/<int:pk>/edit/', views.TransferRecordUpdateView.as_view(), name='transfer_record_update'),
    path('privacy/retention/', views.RetentionPolicyListView.as_view(), name='retention_policy_list'),
    path('privacy/retention/new/', views.RetentionPolicyCreateView.as_view(), name='retention_policy_create'),
    path('privacy/retention/<int:pk>/edit/', views.RetentionPolicyUpdateView.as_view(), name='retention_policy_update'),
    path('privacy/legal-holds/', views.LegalHoldListView.as_view(), name='legal_hold_list'),
    path('privacy/legal-holds/new/', views.LegalHoldCreateView.as_view(), name='legal_hold_create'),
    path('privacy/legal-holds/<int:pk>/', views.LegalHoldDetailView.as_view(), name='legal_hold_detail'),
    path('privacy/legal-holds/<int:pk>/edit/', views.LegalHoldUpdateView.as_view(), name='legal_hold_update'),

    # Approval Workflow Engine
    path('approval-rules/', views.ApprovalRuleListView.as_view(), name='approval_rule_list'),
    path('approval-rules/new/', views.ApprovalRuleCreateView.as_view(), name='approval_rule_create'),
    path('approval-rules/<int:pk>/edit/', views.ApprovalRuleUpdateView.as_view(), name='approval_rule_update'),
    path('approvals/', views.ApprovalRequestListView.as_view(), name='approval_request_list'),
    path('approvals/new/', views.ApprovalRequestCreateView.as_view(), name='approval_request_create'),
    path('approvals/<int:pk>/edit/', views.ApprovalRequestUpdateView.as_view(), name='approval_request_update'),

    # Search
    path('search/', views.global_search, name='global_search'),

    # Contracts
    path('', views.ContractListView.as_view(), name='contract_list'),
    path('<int:pk>/', views.ContractDetailView.as_view(), name='contract_detail'),
    path('new/', views.ContractCreateView.as_view(), name='contract_create'),
    path('<int:pk>/edit/', views.ContractUpdateView.as_view(), name='contract_update'),
    path('<int:pk>/add_note/', views.AddNegotiationNoteView.as_view(), name='add_negotiation_note'),
    path('<int:pk>/ai-assistant/', views.contract_ai_assistant, name='contract_ai_assistant'),
]
