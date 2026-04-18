# Sprint 3 Execution Todo (2026-04-18)

This list tracks the concrete execution backlog and completion evidence.

## Completed In This Pass

- [x] `SPR3-001/002/005` go-live evidence orchestration automation:
  - added dedicated workflow: `.github/workflows/sprint3-go-live-evidence.yml`
  - workflow captures:
    - `postgres-cutover-evidence.json`
    - `release-gate-report.json`
    - `sprint3-integration-report.json`
    - `esign-integration-report.json`
    - `executive-analytics-evidence.json`
    - `retention-audit-actions.json`
  - workflow supports optional live sync execution:
    - `sync_salesforce_contracts`
    - `sync_netsuite_contracts`
    - `dispatch_webhook_deliveries`
  - workflow exports + verifies tamper-evident compliance bundle and fails on any `NO-GO` report.

- [x] `SPR3-005` e-sign integration evidence command:
  - added command: `python manage.py generate_esign_integration_report`
  - validates:
    - at least one applied `ESignEvent` reconciliation record
    - at least one terminal signature status in the window
  - supports org scoping, output artifact path, and `--fail-on-no-go`.
  - tests:
    - `test_generate_esign_integration_report_is_go_with_applied_event_and_terminal_signature`
    - `test_generate_esign_integration_report_no_go_without_applied_event`
    - `test_generate_esign_integration_report_fail_on_no_go_raises`

- [x] `SPR3-001` release gate security hardening:
  - gate security checks now fail closed (no `skipped` pass-through for required scanners).
  - `pip-audit` execution now falls back to `python -m pip_audit` for deterministic local/CI behavior.
  - pinned `pip-audit` in `requirements/dev.txt` to align with RC evidence workflow installs.
  - updated regression coverage in `tests/test_release_gate_report.py`.

- [x] `SPR3-002` evidence command path (local executable):
  - added command: `python manage.py generate_sprint3_integration_report`.
  - validates:
    - successful Salesforce sync run with `created_count > 0` or `updated_count > 0`
    - webhook `SENT` delivery present
    - optional dead-letter proof requirement (`--require-dead-letter-evidence`)
  - supports `--fail-on-no-go` for CI gate behavior.

- [x] `SPR3-005` reconciliation core path (local executable):
  - added provider-agnostic event reconciler command:
    - `python manage.py reconcile_esign_events --path <events.json>`.
  - added provider webhook callback API endpoint:
    - `POST /contracts/api/integrations/esign/webhook/`
    - secured with `X-Esign-Webhook-Secret` (`ESIGN_WEBHOOK_SECRET`).
  - reconciliation is idempotent (`event_id` dedupe) and handles out-of-order events by status precedence.
  - stale events after terminal status are ignored safely.
  - tests:
    - `test_reconcile_esign_events_applies_out_of_order_events`
    - `test_reconcile_esign_events_is_idempotent_for_duplicate_event_id`
    - `test_reconcile_esign_events_ignores_stale_after_terminal_status`
    - `test_esign_webhook_api_applies_event`
    - `test_esign_webhook_api_is_idempotent_for_duplicate_event_id`
    - `test_esign_webhook_api_rejects_invalid_secret`

- [x] `SPR3-004` NetSuite authenticated adapter:
  - added settings-backed authenticated fetch path (`NETSUITE_*`).
  - added command: `python manage.py sync_netsuite_contracts --organization-slug <slug> --limit 200`.
  - added API endpoint: `POST /contracts/api/integrations/netsuite/sync/`.
  - deterministic upsert key remains `(organization, source_system='netsuite', source_system_id)`.
  - tests:
    - `test_sync_netsuite_contracts_command_fetches_and_upserts`
    - `test_sync_netsuite_contracts_command_supports_dry_run`
    - `test_netsuite_sync_api_returns_summary`
    - `test_netsuite_sync_api_dry_run_does_not_persist`

- [x] `SPR3-006` retention execution + immutable logs (core path):
  - added command: `python manage.py run_retention_jobs [--organization-slug <slug>] [--dry-run]`.
  - archives eligible contracts to lifecycle stage `ARCHIVED`.
  - writes immutable audit entries with traceable `trace_id` via `AuditLog`.
  - added retention action export command:
    - `python manage.py export_retention_audit_actions`.
  - added scheduled retention execution workflow:
    - `.github/workflows/retention-jobs-scheduler.yml`
    - runs daily + manual dispatch
    - uploads `retention-jobs-run.json` and `retention-audit-actions.json` artifacts
  - tests:
    - `test_run_retention_jobs_archives_eligible_contracts_and_writes_audit`
    - `test_run_retention_jobs_dry_run_does_not_mutate_contracts`
    - `test_export_retention_audit_actions_includes_trace_ids`
    - `test_export_retention_audit_actions_writes_output_file`

- [x] `SPR3-007` tamper-evident compliance evidence bundle:
  - added command: `python manage.py export_compliance_evidence_bundle ...`
  - added command: `python manage.py verify_compliance_evidence_bundle ...`
  - bundle includes manifest + file hashes + detached SHA256 + HMAC signature.
  - verification fails on tamper.
  - tests:
    - `test_export_and_verify_compliance_evidence_bundle`
    - `test_verify_compliance_evidence_bundle_fails_when_tampered`
  - release evidence workflow now exports and verifies the bundle.
  - release evidence workflow now includes:
    - `retention-audit-actions.json`
    - `executive-analytics-evidence.json`

- [x] `SPR3-008` executive analytics + saved dashboards (API + persistence):
  - added executive analytics endpoint:
    - `GET /contracts/api/analytics/executive/`
    - includes cycle time, bottlenecks, risk trend, and shared presets.
  - added saved dashboard preset APIs:
    - `GET|POST /contracts/api/analytics/executive/presets/`
    - `DELETE /contracts/api/analytics/executive/presets/<id>/`
  - added org-scoped persistence model: `ExecutiveDashboardPreset`.
  - tests:
    - `test_executive_analytics_api_is_org_scoped`
    - `test_executive_dashboard_presets_persist_and_load`
    - `test_member_cannot_create_or_delete_shared_presets`
  - reports dashboard now surfaces executive cycle time, bottlenecks, risk trend, and saved dashboard presets.
  - UI test:
    - `test_reports_dashboard_renders_executive_sections`
  - evidence command added for multi-org snapshots:
    - `python manage.py generate_executive_analytics_evidence`
  - release evidence workflow now captures `executive-analytics-evidence.json`.

## Still Pending (Env / Operational Evidence)

- [ ] `SPR3-001` run release-gate checklist in staging/prod-like env with attached artifacts.
- [ ] `SPR3-002` execute live Salesforce + webhook E2E evidence run.
- [ ] `SPR3-003` run `postgres-cutover-check` in target environment and attach artifact with `cutover_ready=true`.
- [ ] `SPR3-005` live provider execution evidence run against staging credentials.
- [ ] `SPR3-008` attach staging-produced executive analytics evidence artifact.
