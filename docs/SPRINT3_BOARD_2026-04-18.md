# Sprint 3 Board (2026-04-18)

Goal: complete production go-live gates and close remaining integration/compliance blockers.

## Scope Window

- Start: 2026-04-18
- End target: 2026-05-12

## Tickets

### SPR3-001: Release Candidate Gate Execution

- Owner: `TL` + `QA`
- Priority: `P0`
- Deliverables:
  - execute full release gate checklist
  - attach evidence links in PR/release notes
  - produce go/no-go decision record
- Acceptance tests:
  - all required CI checks green
  - release evidence artifacts linked and verified
  - rollback path validated in staging
- Current status (2026-04-18):
  - `IN PROGRESS`
  - executable release gate command added: `python manage.py generate_release_gate_report`
  - security checks now fail-closed in gate report (`pip-audit` and `npm` must execute and pass)
  - `pip-audit` added to dev dependencies to ensure workflow parity
  - CI evidence workflow now runs:
    - `python manage.py verify_postgres_cutover`
    - `python manage.py generate_release_gate_report --fail-on-no-go`

### SPR3-002: Salesforce + Webhook Production E2E

- Owner: `BE` + `SRE`
- Priority: `P0`
- Deliverables:
  - run live Salesforce sync in staging/prod-like environment
  - verify webhook delivery success path and dead-letter behavior
  - confirm scheduler cadence and overlap lock behavior
- Acceptance tests:
  - at least one successful sync run with `created/updated` > 0
  - webhook delivery status includes at least one `SENT` event
  - forced webhook failure reaches `DEAD_LETTER` after max attempts
- Current status (2026-04-18):
  - `IN PROGRESS`
  - local coverage in place for sync and dead-letter behavior (`tests.test_salesforce_sprint2_ingestion`)
  - integration evidence command added: `python manage.py generate_sprint3_integration_report`
  - go-live evidence workflow automation added:
    - `.github/workflows/sprint3-go-live-evidence.yml`
    - supports optional live sync execution before evidence capture
  - production/staging execution evidence still required

### SPR3-003: Postgres Cutover Evidence Automation Adoption

- Owner: `SRE`
- Priority: `P0`
- Deliverables:
  - enable and run `postgres-cutover-check` workflow against target env
  - publish weekly cutover evidence artifact links
- Acceptance tests:
  - workflow succeeds with `cutover_ready=true`
  - no unapplied migrations in evidence payload
- Current status (2026-04-18):
  - `IN PROGRESS`
  - workflow exists: `.github/workflows/postgres-cutover-check.yml`
  - release evidence workflow now collects `postgres-cutover-evidence.json`
  - target-environment run evidence still required

### SPR3-004: NetSuite Authenticated Adapter

- Owner: `BE`
- Priority: `P1`
- Deliverables:
  - replace file-only ingest path with authenticated NetSuite pull adapter
  - normalize mapping controls similar to Salesforce
- Acceptance tests:
  - command/API can fetch records from sandbox credentials
  - deterministic upsert by `(organization, source_system, source_system_id)`
- Current status (2026-04-18):
  - `IN PROGRESS`
  - authenticated adapter + command implemented: `python manage.py sync_netsuite_contracts`
  - authenticated API endpoint implemented: `POST /contracts/api/integrations/netsuite/sync/`
  - deterministic upsert key preserved in `contracts/services/netsuite.py`
  - remaining: execute against real sandbox credentials and attach run evidence

### SPR3-005: E-sign Integration + Reconciliation

- Owner: `BE` + `PO`
- Priority: `P1`
- Deliverables:
  - provider integration for signature status updates
  - reconciliation handler for out-of-order webhook events
- Acceptance tests:
  - signature request lifecycle updates correctly from provider callbacks
  - replayed webhook event does not create inconsistent state
- Current status (2026-04-18):
  - `IN PROGRESS`
  - reconciliation engine + command implemented:
    - `python manage.py reconcile_esign_events --path <events.json>`
  - provider callback endpoint implemented:
    - `POST /contracts/api/integrations/esign/webhook/`
    - secured via `ESIGN_WEBHOOK_SECRET`
  - dedupe + out-of-order handling covered in automated tests
  - e-sign evidence command added:
    - `python manage.py generate_esign_integration_report --organization-slug <slug>`
  - release-candidate evidence workflow now captures `esign-integration-report.json`
  - go-live evidence workflow now evaluates e-sign `GO/NO-GO` as a required gate
  - remaining: live provider evidence run in staging/prod-like environment

### SPR3-006: Retention Jobs + Immutable Compliance Logs

- Owner: `BE` + `SEC`
- Priority: `P1`
- Deliverables:
  - retention execution jobs and immutable action log trail
  - audit export for retention actions
- Acceptance tests:
  - retention jobs execute on schedule and record immutable entries
  - compliance export includes retention actions with traceable IDs
- Current status (2026-04-18):
  - `IN PROGRESS`
  - retention execution command implemented: `python manage.py run_retention_jobs`
  - immutable retention action trail recorded via `AuditLog` with `trace_id`
  - retention audit export implemented: `python manage.py export_retention_audit_actions`
  - scheduled automation implemented: `.github/workflows/retention-jobs-scheduler.yml`
  - scheduled workflow now uploads retention execution evidence artifacts
  - remaining: run scheduled workflow in target environment and attach first successful evidence artifact

### SPR3-007: Tamper-Evident Evidence Bundle Export

- Owner: `SEC` + `QA`
- Priority: `P1`
- Deliverables:
  - signed/hash-based evidence bundle export
  - verification script/check for bundle integrity
- Acceptance tests:
  - bundle verification passes for unchanged artifact
  - bundle verification fails on altered artifact
- Current status (2026-04-18):
  - `IN PROGRESS`
  - export + verify commands implemented:
    - `python manage.py export_compliance_evidence_bundle`
    - `python manage.py verify_compliance_evidence_bundle`
  - release evidence workflow now exports and verifies a compliance bundle artifact
  - compliance bundle inputs now include retention audit and executive analytics evidence snapshots
  - automated tests cover pass/fail tamper detection paths
  - remaining: attach signed bundle artifacts in release workflow evidence

### SPR3-008: Executive Analytics + Saved Dashboards

- Owner: `BE` + `FE`
- Priority: `P2`
- Deliverables:
  - cycle time, bottleneck, risk trend views
  - saved team dashboard presets
- Acceptance tests:
  - metrics render for multi-org sample data
  - saved dashboard state persists and loads correctly
- Current status (2026-04-18):
  - `IN PROGRESS`
  - executive analytics APIs implemented:
    - `GET /contracts/api/analytics/executive/`
    - `GET|POST /contracts/api/analytics/executive/presets/`
    - `DELETE /contracts/api/analytics/executive/presets/<id>/`
  - org-scoped saved preset persistence implemented (`ExecutiveDashboardPreset`)
  - reports dashboard UI integrated with executive metrics + saved presets
  - evidence automation implemented:
    - `python manage.py generate_executive_analytics_evidence`
    - release workflow captures `executive-analytics-evidence.json`
  - API/UI tests cover scoping, persistence, role permissions, and rendering
  - remaining: staging evidence on multi-org sample data

## Exit Criteria

1. `SPR3-001`, `SPR3-002`, `SPR3-003` complete.
2. No high vulnerabilities in runtime/client/theme scans.
3. Staging release candidate passes with rollback evidence attached.
