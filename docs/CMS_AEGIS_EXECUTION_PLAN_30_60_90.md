# CMS Aegis CMS Aegis Execution Plan (30/60/90)

## Baseline Snapshot (captured 2026-04-12)

Evidence from current workspace:

- Test status: `154` tests passing (`python manage.py test contracts tests -v 1`).
- Deploy checks: production profile can pass in CI, but local default profile still emits 6 deploy warnings when run in dev defaults.
- Tenancy/RBAC posture: strong route-level isolation coverage and explicit role checks.
- DB posture: base config is SQLite-only in settings.
- API hardening gaps:
  - CSRF disabled on bulk API endpoint.
  - bulk update path allows unrestricted `queryset.update(**updates)`.
  - API returns raw exception text in JSON.
- Service maturity gaps:
  - template/clause/obligation services are in-memory and mock-first.
- Security posture:
  - `npm audit` shows high vulnerabilities in both `client` and `theme/static_src`.
  - `bandit` reported no high findings, but low/medium findings remain.
- Runtime parity gap:
  - local venv is Python `3.15.0a6` while CI runs Python `3.12`.

## Progress Update (captured 2026-04-18)

Recent delivery on branch `codex/cms-aegis-activation` closed the planned Salesforce integration and several reliability/security gaps:

- `9a7d79e`: Sprint 1 Salesforce foundation + control evidence baseline.
- `90d71e6`: token encryption-at-rest + Sprint 2 ingestion/reconciliation.
- `e7dd795`: live Salesforce sync adapter (API + command).
- `8fb53dd`: sync run tracking + sync history API.
- `66b8214`: scheduled sync workflow, overlap lock, retry/dead-letter, settings UI status panel.
- `4a69022`: high-priority closure pass (CVE pin upgrades, Postgres cutover verification workflow, observability sink option, webhook queue/retry/DLQ diagnostics, NetSuite ingest baseline).

Current status against major gates:

- Day-30 critical security/integrity: functionally complete, now in evidence consolidation mode.
- Day-60 reliability/CLM depth: in progress, with observability/sync/retry foundations now shipped.
- Day-90 scale/governance: partially complete; production load-signoff and full compliance export hardening remain.

Sprint 3 execution board:

- [`docs/SPRINT3_BOARD_2026-04-18.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/SPRINT3_BOARD_2026-04-18.md)
- Release gate checklist:
  [`docs/RELEASE_CANDIDATE_GATE_CHECKLIST_2026-04-18.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/RELEASE_CANDIDATE_GATE_CHECKLIST_2026-04-18.md)

## Date Windows (from now)

- Day 30 target: **2026-05-12**
- Day 60 target: **2026-06-11**
- Day 90 target: **2026-07-11**

## Owners

- `TL` = Tech Lead / Delivery owner
- `BE` = Backend owner
- `FE` = Frontend owner
- `SRE` = Platform/DevOps owner
- `SEC` = Security owner
- `QA` = Test and release owner
- `PO` = Product owner

## SLO Targets

- Availability: `99.9%` monthly for authenticated app routes
- Core route latency: `p95 < 500ms` for `/dashboard/`, `/contracts/`, `/contracts/<id>/`
- Error rate: `5xx < 0.5%`
- MTTR: `< 60m`

## Ticket Plan

### Day 0-30 (2026-04-12 to 2026-05-12): Close Critical Security/Integrity Gaps

#### ICL-001: Harden contracts bulk API

- Priority: `P0`
- Owners: `BE` (primary), `SEC` (review), `QA` (verification)
- Scope:
  - Remove `@csrf_exempt` from bulk endpoint.
  - Add strict allowlist for mutable fields in bulk updates.
  - Validate payload schema and type/enum constraints.
  - Return generic API errors with correlation ID, no raw exception strings.
- Files:
  - [`contracts/api/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/api/views.py)
  - [`contracts/services/repository.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/services/repository.py)
  - [`tests/test_cms_aegis_features.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/tests/test_cms_aegis_features.py)
- Exit criteria:
  - CSRF enforced for browser-authenticated POSTs.
  - unauthorized fields rejected with `400`.
  - no endpoint leaks exception internals.

#### ICL-002: Production DB migration path (SQLite -> Postgres)

- Priority: `P0`
- Owners: `SRE` (primary), `BE` (schema/app), `QA` (validation)
- Scope:
  - Add Postgres config path to production settings and env contract.
  - Provide migration playbook for staging and production.
  - Run staging migration rehearsal with rollback point.
- Files:
  - [`config/settings_base.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_base.py)
  - [`config/settings_production.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_production.py)
  - [`docs/ROLLBACK_RUNBOOK.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/ROLLBACK_RUNBOOK.md)
- Exit criteria:
  - staging runs on Postgres successfully.
  - restore and rollback tested once with timings in drill log.

#### ICL-003: Eliminate high dependency vulnerabilities

- Priority: `P0`
- Owners: `FE` (client/theme), `SEC` (triage/signoff)
- Scope:
  - Update vulnerable Node dependencies in `client` and `theme/static_src`.
  - ensure CI audits pass at `--audit-level=high`.
  - pin and document any temporary exceptions with expiration date if needed.
- Files:
  - [`client/package.json`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/client/package.json)
  - [`client/package-lock.json`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/client/package-lock.json)
  - [`theme/static_src/package.json`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/static_src/package.json)
- Exit criteria:
  - `npm audit --audit-level=high` returns zero highs in both trees.

#### ICL-004: Runtime version alignment and scanner reliability

- Priority: `P0`
- Owners: `SRE` (primary), `BE` (runtime compatibility), `SEC` (scanner baseline)
- Scope:
  - move local/dev runtime to Python 3.12.x.
  - regenerate venv and lock compatibility.
  - ensure `pip-audit` runs cleanly in local and CI.
- Exit criteria:
  - same Python minor version in local, CI, staging.
  - security scan commands are stable and documented.

#### ICL-005: Export/download permission matrix completion

- Priority: `P0`
- Owners: `BE`, `QA`
- Scope:
  - inventory all download/export endpoints and add negative/positive tests.
  - ensure all exports are org-scoped and role-gated.
- Files:
  - [`contracts/urls.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/urls.py)
  - [`contracts/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/views.py)
  - [`tests/test_cross_tenant_isolation.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/tests/test_cross_tenant_isolation.py)
- Exit criteria:
  - each export/download route has at least one deny test and one allow test.

### Day 31-60 (2026-05-13 to 2026-06-11): Operational Reliability + CLM Depth

#### ICL-006: Replace mock service layers with persisted domain services

- Priority: `P1`
- Owners: `BE` (primary), `PO` (behavior definition), `QA` (regression)
- Scope:
  - migrate template/clause/obligation service operations to Django model-backed persistence.
  - remove test-mode in-memory behavior from runtime code paths.
  - keep API/UI contract stable.
- Files:
  - [`contracts/services/templates.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/services/templates.py)
  - [`contracts/services/clauses.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/services/clauses.py)
  - [`contracts/services/obligations.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/services/obligations.py)
  - [`contracts/models.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/models.py)
- Exit criteria:
  - no production code path relies on in-memory service state.
  - CRUD and search flows backed by persisted tenant-scoped data.

#### ICL-007: Signature and approval workflow hardening

- Priority: `P1`
- Owners: `BE`, `PO`, `QA`
- Scope:
  - implement explicit state transition guards for approval/signature statuses.
  - enforce actor authorization at transition points.
  - add SLA breach/escalation signaling.
- Files:
  - [`contracts/models.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/models.py)
  - [`contracts/forms.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/forms.py)
  - [`contracts/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/views.py)
  - [`tests/test_workflow_transition_guardrails.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/tests/test_workflow_transition_guardrails.py)
- Exit criteria:
  - invalid transitions rejected by model/service rules.
  - transition tests cover all critical status edges.
- Status update (2026-04-13):
  - completed transition guard implementation and actor authorization enforcement.
  - added regression coverage for invalid transitions and unauthorized actors.

#### ICL-008: Observability implementation (from bootstrap doc)

- Priority: `P1`
- Owners: `SRE` (primary), `BE` (instrumentation)
- Scope:
  - ship structured logs to centralized sink.
  - add dashboard and alerts specified in observability bootstrap.
  - add scheduler heartbeat monitor and paging policy.
- Files:
  - [`docs/OBSERVABILITY_BOOTSTRAP.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/OBSERVABILITY_BOOTSTRAP.md)
  - [`contracts/middleware.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/middleware.py)
- Exit criteria:
  - dashboard URLs and alert IDs documented.
  - one alert fire-drill recorded in drill log.
- Status update (2026-04-13):
  - completed: scheduler heartbeat metric + staleness health signal.
  - completed: in-app HTTP request metrics and DB latency health probe exposed in JSON health response.
  - completed: alert policy + automated watch workflow (`.github/workflows/observability-watch.yml`).
  - completed: dashboard IDs documented and fire-drill evidence recorded in `docs/DRILL_LOG.md`.

#### ICL-009: Incident-ready release gates

- Priority: `P1`
- Owners: `TL`, `SRE`, `QA`
- Scope:
  - enforce required checks on `main`.
  - require smoke and rollback evidence per release candidate.
  - standardize release evidence template in PRs.
- Exit criteria:
  - no merge to `main` without passing required checks and evidence.
- Status update (2026-04-13):
  - completed: PR checklist evidence gate implemented in `platform-guardrails.yml`.
  - completed: branch protection required checks on `main` include `pr-release-evidence`.
  - completed: release-candidate artifact policy and workflow (`.github/workflows/release-candidate-evidence.yml`).

### Day 61-90 (2026-06-12 to 2026-07-11): Performance, Governance, and Auditability

#### ICL-010: Performance and scale validation

- Priority: `P1`
- Owners: `BE`, `SRE`
- Scope:
  - profile top 10 slow routes and remove N+1/query hotspots.
  - run load tests at 2x expected peak.
  - tune indexes and query plans.
- Exit criteria:
  - SLO latency targets met under expected production load profile.
- Status update (2026-04-13):
  - partial completion: added query-scaling regression tests for contract list and contracts API.
  - partial completion: fixed list-path N+1 query growth in `contracts/services/repository.py` by selecting `created_by`.
  - partial completion: added repeatable `profile_core_routes` management command and captured baseline in `docs/PERFORMANCE_BASELINE_2026-04-13.json`.
  - partial completion: wired `tests.test_performance_guardrails` into CI (`platform-guardrails.yml`).
  - partial completion: added contract query indexes and captured explain-plan evidence in `docs/QUERY_PLAN_2026-04-13.md`.
  - completed: top-10 authenticated route profiling report (`docs/AUTH_ROUTE_PROFILE_2026-04-13.json` + `.md`).
  - completed: 2x peak load test harness + evidence (`manage.py run_core_load_test`, `docs/LOAD_TEST_2X_2026-04-13.json` + `.md`).
  - completed: performance evidence bundle command and RC artifact integration (`manage.py run_performance_evidence_bundle`, `.github/workflows/release-candidate-evidence.yml`).
  - remaining: production/staging load execution under production-like infrastructure and SLO acceptance sign-off.

#### ICL-011: Monolith split for high-risk view domains

- Priority: `P2`
- Owners: `BE`, `TL`
- Scope:
  - split `contracts/views.py` by bounded domains (org admin, workflow, privacy, approvals, repository).
  - keep routes and behavior unchanged.
- Exit criteria:
  - reduced blast radius and review scope; full suite remains green.
- Status update (2026-04-13):
  - completed: extracted privacy/approval/signature domain view logic from `contracts/views.py` into `contracts/views_domains/privacy_approvals.py`.
  - completed: extracted organization admin/invitation/activity/reporting view logic into `contracts/views_domains/organization_admin.py`.
  - completed: extracted repository management/search view logic into `contracts/views_domains/repository_management.py`.
  - completed: extracted workflow template/workflow/step class/function view logic into `contracts/views_domains/workflow_management.py`.
  - URL contracts unchanged; behavior verified by full-suite validation (`python manage.py test contracts tests -v 1`, `183` tests passed).
  - residual: continue optional decomposition for remaining non-target domains as maintenance work.

#### ICL-012: Governance and compliance operating model

- Priority: `P1`
- Owners: `TL`, `SEC`, `PO`, `QA`
- Scope:
  - enforce vulnerability SLAs (P0 24h, P1 7d, P2 30d).
  - monthly game day and quarterly risk review.
  - data-classification and retention control evidence.
- Exit criteria:
  - documented evidence of at least one game day and one security SLA cycle.
- Status update (2026-04-13):
  - completed: defined vulnerability SLA policy and enforcement flow in `docs/SECURITY_SLA_POLICY.md`.
  - completed: added weekly automated security SLA cycle workflow (`.github/workflows/security-sla-watch.yml`).
  - completed: captured security SLA cycle evidence in `docs/SECURITY_SLA_CYCLE_2026-04-13.md`.
  - completed: documented game-day + SLA cycle run in `docs/DRILL_LOG.md` (2026-04-13 entry).
  - completed: documented data classification/retention control evidence in `docs/DATA_CLASSIFICATION_RETENTION_CONTROLS.md`.

## Week-by-Week Sequence

### Weeks 1-2 (Apr 12-Apr 26)

- ICL-001, ICL-004 start and complete.

### Weeks 3-4 (Apr 27-May 12)

- ICL-002, ICL-003, ICL-005 complete.
- Day-30 gate review.

### Weeks 5-6 (May 13-May 26)

- ICL-006 implementation.
- ICL-008 instrumentation kickoff.

### Weeks 7-8 (May 27-Jun 11)

- ICL-007 and ICL-009 complete.
- Day-60 gate review.

### Weeks 9-10 (Jun 12-Jun 25)

- ICL-010 performance hardening.

### Weeks 11-13 (Jun 26-Jul 11)

- ICL-011, ICL-012 closeout.
- Day-90 cms-aegis certification review.

## Day-30 Gate (Must Pass)

1. P0 tickets ICL-001 through ICL-005 completed.
2. No high vulnerabilities in client/theme dependency trees.
3. Postgres staging run validated with rollback evidence.
4. Bulk API hardened and covered by tests.

## Day-30 Gate Review (Completed 2026-04-13)

Overall status: `PASS`

1. ICL-001 contracts bulk API hardening: `COMPLETE`
- Evidence:
  - [`contracts/api/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/api/views.py)
  - [`contracts/services/repository.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/services/repository.py)
  - [`tests/test_cms_aegis_features.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/tests/test_cms_aegis_features.py)
- Verification:
  - `python manage.py test tests.test_cms_aegis_features -v 2`

2. ICL-002 PostgreSQL production path and rehearsal evidence: `COMPLETE`
- Evidence:
  - [`config/settings_base.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_base.py)
  - [`config/settings_production.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_production.py)
  - [`docs/STAGING_POSTGRES_REHEARSAL.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/STAGING_POSTGRES_REHEARSAL.md)
  - [`docs/DRILL_LOG.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/DRILL_LOG.md)
- Verification:
  - deploy check, migrate, audit, tenant-isolation, and restore cycle completed on PostgreSQL rehearsal DB.

3. ICL-003 Node vulnerability gate: `COMPLETE`
- Evidence:
  - [`client/package-lock.json`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/client/package-lock.json)
  - [`theme/static_src/package-lock.json`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/static_src/package-lock.json)
- Verification:
  - `npm --prefix client audit --audit-level=high`
  - `npm --prefix theme/static_src audit --audit-level=high`
  - both returned zero vulnerabilities at high threshold.

4. ICL-004 runtime alignment and scanner reliability: `COMPLETE`
- Evidence:
  - [`.python-version`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.python-version)
  - [`scripts/bootstrap_python312.sh`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/scripts/bootstrap_python312.sh)
  - [`requirements/runtime.txt`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/requirements/runtime.txt)
  - [`requirements/dev.txt`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/requirements/dev.txt)
  - [`.github/workflows/platform-guardrails.yml`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.github/workflows/platform-guardrails.yml)
- Verification:
  - `.venv` aligned to Python 3.12.13
  - `pip-audit --disable-pip --no-deps -r requirements/runtime.txt` clean
  - `bandit -q -r contracts config -lll` clean

5. ICL-005 export/download permission matrix: `COMPLETE` (current export surface)
- Evidence:
  - [`contracts/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/views.py)
  - [`tests/test_organization_invitations.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/tests/test_organization_invitations.py)
  - [`tests/test_cross_tenant_isolation.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/tests/test_cross_tenant_isolation.py)
- Verification:
  - owner/admin allow, member deny, anonymous redirect, and tenant scoping tests pass for `organization_activity_export`.

## Day-60 Gate (Must Pass)

1. Mock-first service gaps closed for templates/clauses/obligations.
2. Observability dashboards and paging alerts live.
3. Release process enforces smoke + rollback evidence.

## Day-90 Gate (CMS Aegis Qualification)

1. SLOs met and measured for at least 14 consecutive days.
2. Security vulnerability SLAs operating and current.
3. Performance/load test evidence approved.
4. Incident and rollback drills documented and repeatable.
