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

### SPR3-003: Postgres Cutover Evidence Automation Adoption

- Owner: `SRE`
- Priority: `P0`
- Deliverables:
  - enable and run `postgres-cutover-check` workflow against target env
  - publish weekly cutover evidence artifact links
- Acceptance tests:
  - workflow succeeds with `cutover_ready=true`
  - no unapplied migrations in evidence payload

### SPR3-004: NetSuite Authenticated Adapter

- Owner: `BE`
- Priority: `P1`
- Deliverables:
  - replace file-only ingest path with authenticated NetSuite pull adapter
  - normalize mapping controls similar to Salesforce
- Acceptance tests:
  - command/API can fetch records from sandbox credentials
  - deterministic upsert by `(organization, source_system, source_system_id)`

### SPR3-005: E-sign Integration + Reconciliation

- Owner: `BE` + `PO`
- Priority: `P1`
- Deliverables:
  - provider integration for signature status updates
  - reconciliation handler for out-of-order webhook events
- Acceptance tests:
  - signature request lifecycle updates correctly from provider callbacks
  - replayed webhook event does not create inconsistent state

### SPR3-006: Retention Jobs + Immutable Compliance Logs

- Owner: `BE` + `SEC`
- Priority: `P1`
- Deliverables:
  - retention execution jobs and immutable action log trail
  - audit export for retention actions
- Acceptance tests:
  - retention jobs execute on schedule and record immutable entries
  - compliance export includes retention actions with traceable IDs

### SPR3-007: Tamper-Evident Evidence Bundle Export

- Owner: `SEC` + `QA`
- Priority: `P1`
- Deliverables:
  - signed/hash-based evidence bundle export
  - verification script/check for bundle integrity
- Acceptance tests:
  - bundle verification passes for unchanged artifact
  - bundle verification fails on altered artifact

### SPR3-008: Executive Analytics + Saved Dashboards

- Owner: `BE` + `FE`
- Priority: `P2`
- Deliverables:
  - cycle time, bottleneck, risk trend views
  - saved team dashboard presets
- Acceptance tests:
  - metrics render for multi-org sample data
  - saved dashboard state persists and loads correctly

## Exit Criteria

1. `SPR3-001`, `SPR3-002`, `SPR3-003` complete.
2. No high vulnerabilities in runtime/client/theme scans.
3. Staging release candidate passes with rollback evidence attached.
