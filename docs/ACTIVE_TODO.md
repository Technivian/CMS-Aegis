# Active Todo

Last updated: 2026-04-18

Canonical remaining worklist:
- [`docs/COMPLETE_REMAINING_WORKLIST.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/COMPLETE_REMAINING_WORKLIST.md)
- [`docs/SPRINT3_BOARD_2026-04-18.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/SPRINT3_BOARD_2026-04-18.md)

## In Progress

- `SPR3-001` Release candidate gate execution (staging to production)
- `SPR3-002` Salesforce + webhook production e2e validation
- `SPR3-003` Postgres cutover evidence automation adoption

## Completed

- Public API versioning and token scoping
- Clause variant resolver and playbook model
- Workflow escalation timers and delegation UX
- Search relevance and semantic filters
- Operational dashboards and drill automation
- Identity telemetry dashboards and recovery-code handling
- SAML attribute reconciliation and SLO/error telemetry
- SCIM PATCH/query edge cases and IdP reconciliation
- Admin MFA enrollment flow and second-factor verification
- Device/session policy controls and audit/export views
- Redlining and version-compare UI
- Bulk record-operation hardening and audit coverage
- Deterministic workflow routing, approvals, and escalation
- SAML telemetry follow-up: logout error handling and attr mapping hardening
- Clause policy edge cases and fallback playbook reconciliation
- `TKT-003` Manual smoke checklist for two-org validation
- `TKT-004` Centralize scoped form/query helpers
- `TKT-005` Structured request logging and correlation IDs
- `TKT-006` Overdue work and deadline health reporting
- `TKT-007` Formalize production env contract
- `TKT-008` Export/download permission tests
- `TKT-009` Split `contracts/views.py` by domain
- `TKT-010` Add staging rollback and migration drill evidence
- Salesforce Sprint 1 foundation (OAuth, mapping, control evidence)
- Salesforce Sprint 2 ingestion and reconciliation (API/CLI)
- Salesforce sync run tracking + sync history API
- Scheduled Salesforce sync with overlap lock protection
- Background retry/dead-letter handling for sync jobs
- Webhook queue/dispatch retries + dead-letter diagnostics
- Sprint 3 integration evidence command (`generate_sprint3_integration_report`)
- E-sign integration evidence command (`generate_esign_integration_report`)
- NetSuite authenticated sync command baseline (`sync_netsuite_contracts`)
- E-sign webhook reconciliation command baseline (`reconcile_esign_events`)
- E-sign provider webhook callback endpoint baseline (`/contracts/api/integrations/esign/webhook/`)
- Retention job runner with immutable retention audit traces (`run_retention_jobs`)
- Retention scheduled execution workflow + evidence artifact export (`retention-jobs-scheduler.yml`)
- Tamper-evident compliance evidence bundle export/verify commands
- Executive analytics and saved dashboard preset APIs
- Reports dashboard executive analytics panel integration
- Multi-org executive analytics evidence snapshot command
- Postgres cutover verification command + scheduled CI workflow
- Optional observability HTTP sink transport
- NetSuite ingestion adapter/command baseline
- Runtime vulnerability hardening (`cryptography==46.0.7`, pip-audit clean)
- Release gate security checks fail-closed (`pip-audit` + `npm` required)
- Semantic clause search mode with tenant-safe ACL scoping (`search_mode=semantic|hybrid|keyword`)
- AI prompt-injection controls + output policy on contract assistant endpoint
- Agentic AI actions with approval gates + rollback trace logs on contract assistant endpoint
- Sprint 3 go-live evidence orchestration workflow (`sprint3-go-live-evidence.yml`)
- Sprint 1 + Sprint 2 closeout verification bundle (`docs/SPRINT_1_2_COMPLETION_2026-04-18.md`)

## Next Up

1. Complete Sprint 3 release gate checklist for staging/prod cutover (`SPR3-001`)
2. Execute live Salesforce + webhook E2E evidence run in staging/prod-like env (`SPR3-002`)
3. Run target-environment Postgres cutover evidence workflow with `cutover_ready=true` (`SPR3-003`)
4. Run NetSuite and e-sign live provider evidence in staging/prod-like env (`SPR3-004`, `SPR3-005`)
5. Attach first scheduled retention evidence artifact from target environment (`SPR3-006`)
6. Attach staging-produced executive analytics evidence artifact (`SPR3-008`)
7. Expand AI extraction provenance to include clause text-span citations and confidence calibration thresholds

## Source Of Truth

- Broader remaining worklist: `docs/COMPLETE_REMAINING_WORKLIST.md`
- Parity tracker: `docs/MASTER_TODO_CMS_AEGIS_PARITY.md`
