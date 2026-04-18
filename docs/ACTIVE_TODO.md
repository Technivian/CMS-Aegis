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
- Postgres cutover verification command + scheduled CI workflow
- Optional observability HTTP sink transport
- NetSuite ingestion adapter/command baseline
- Runtime vulnerability hardening (`cryptography==46.0.7`, pip-audit clean)

## Next Up

1. Complete Sprint 3 release gate checklist for staging/prod cutover
2. Ship authenticated NetSuite API pull adapter (beyond file-based ingest)
3. Implement e-sign provider integration and webhook reconciliation
4. Finalize retention execution jobs + immutable compliance logs
5. Build tamper-evident compliance evidence bundle export
6. Deliver executive analytics and saved-team dashboards
7. Implement semantic clause search with ACL filtering
8. Add prompt-injection controls and output policy engine
9. Add AI summarization/risk extraction with citation guarantees
10. Add agentic AI actions with approvals and rollback logs

## Source Of Truth

- Broader remaining worklist: `docs/COMPLETE_REMAINING_WORKLIST.md`
- Parity tracker: `docs/MASTER_TODO_IRONCLAD_PARITY.md`
