# CMS Aegis Ironclad Execution Plan (30/60/90)

## Baseline Snapshot (captured 2026-04-10)

- Runtime: Django 5.2.5 monolith (`config/`, `contracts/`, `theme/`)
- Database in repo default: SQLite (`db.sqlite3`)
- Existing CI: one workflow ([`.github/workflows/ui-verification.yml`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.github/workflows/ui-verification.yml))
- Tenancy controls: middleware + role model present, cross-tenant test suite exists
- Logging: request context and `X-Request-ID` present
- Deploy posture check (`manage.py check --deploy` in dev config): warnings remain for HTTPS/cookies/DEBUG/secret policy
- Dependency posture: `requirements.txt` is normalized to UTF-8 and split into `requirements/runtime.txt` and `requirements/dev.txt` (completed 2026-04-10)

## Target Dates

- Day 30 target: **2026-05-10**
- Day 60 target: **2026-06-09**
- Day 90 target: **2026-07-09**

## Owners

- `TL` = Tech Lead
- `BE` = Backend Engineer
- `FE` = Frontend Engineer
- `SRE` = DevOps/SRE
- `QA` = QA Engineer
- `SEC` = Security Engineer
- `PO` = Product Owner

## SLO Targets (must be instrumented by Day 60, enforced by Day 90)

- Availability: `99.9%` monthly for authenticated app routes
- API latency: `p95 < 500ms` for dashboard, contract list, contract detail
- Error rate: `5xx < 0.5%` across total requests
- Change failure rate: `< 15%`
- MTTR: `< 60 minutes`

## 30-Day Plan (2026-04-10 to 2026-05-10): Stabilize + Enforce Guardrails

### Workstream A: Git/PR controls

- Owner: `TL`, `SRE`
- Tasks:
1. Enforce branch protection on `main`: required checks, linear history, no force push.
2. Require CODEOWNERS review for `config/`, `contracts/`, and `.github/`.
3. Require PR template completion before merge.
- Deliverables:
1. [`.github/CODEOWNERS`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.github/CODEOWNERS)
2. [`.github/pull_request_template.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.github/pull_request_template.md)

### Workstream B: CI hardening gates

- Owner: `SRE`, `BE`, `QA`
- Tasks:
1. Add platform guardrail workflow for deploy checks, tenancy audit, cross-tenant tests, and request-log tests.
2. Add dependency and static analysis scans (Python + Node) on every PR and `main` push.
3. Mark new workflow as required status check in GitHub settings.
- Deliverables:
1. [`.github/workflows/platform-guardrails.yml`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.github/workflows/platform-guardrails.yml)

### Workstream C: Security posture closure

- Owner: `SEC`, `BE`
- Tasks:
1. Rotate all production credentials and secrets; move to managed secrets store.
2. Define and enforce production env contract (HTTPS + secure cookies + host/origin lock).
3. Remove any dev defaults from production deployment manifests.
- Exit evidence:
1. `manage.py check --deploy` clean in production config.
2. Secrets inventory updated with owner + rotation cadence.

### Workstream D: Tenancy and RBAC confidence

- Owner: `BE`, `QA`
- Tasks:
1. Expand role-action tests for create/update/delete/export endpoints.
2. Add negative tests for every file/document download endpoint.
3. Add two-org manual smoke run before each release.
- Exit evidence:
1. CI green for tenancy and permission suites.
2. Smoke checklist run artifact attached per release.

## 60-Day Plan (2026-05-11 to 2026-06-09): Operate Reliably

### Workstream E: Observability + incident readiness

- Owner: `SRE`, `BE`
- Tasks:
1. Ship structured logs to centralized sink (Datadog/ELK/Cloud logging).
2. Build dashboards for request rate, 5xx, latency p95, auth failures, job failures.
3. Add alerts tied to SLO symptoms and define on-call escalation.
- Exit evidence:
1. Dashboard links documented.
2. Alert test fired and acknowledged by on-call.

### Workstream F: Release safety

- Owner: `TL`, `SRE`, `QA`
- Tasks:
1. Introduce staging promotion gate requiring smoke + rollback drill checkboxes.
2. Implement release checklist with explicit migration risk section.
3. Add post-deploy verification commands and rollback command bundle.
- Exit evidence:
1. One successful staged release rehearsal.
2. One successful rollback rehearsal with timings.

### Workstream G: Data safety and compliance

- Owner: `SEC`, `BE`, `PO`
- Tasks:
1. Classify data fields (PII, confidential, operational).
2. Confirm retention + deletion flows for DSAR/privacy models.
3. Enforce audit logs for privileged actions (role changes, exports, deletions).
- Exit evidence:
1. Data classification table published.
2. DSAR/delete flow tested end-to-end.

## 90-Day Plan (2026-06-10 to 2026-07-09): Scale + Governance

### Workstream H: Performance and capacity

- Owner: `BE`, `SRE`
- Tasks:
1. Profile slowest endpoints and remove N+1 hotspots.
2. Add/adjust indexes from measured query plans.
3. Run load test at 2x expected peak and document bottlenecks.
- Exit evidence:
1. p95 target met on top routes under load.
2. Query plan diff and index changes documented.

### Workstream I: Dependency governance

- Owner: `SEC`, `BE`
- Tasks:
1. [COMPLETED 2026-04-10] Convert `requirements.txt` to UTF-8 and split runtime vs dev/test tooling.
2. Introduce scheduled dependency update PR cadence (weekly security, monthly minor updates).
3. Enforce vulnerability SLA: P0 24h, P1 7d, P2 30d.
- Exit evidence:
1. Dependency file normalization merged.
2. Vulnerability backlog with due dates and owners.

### Workstream J: Platform operating model

- Owner: `TL`, `PO`, `QA`, `SRE`
- Tasks:
1. Formalize definition-of-done with tests, telemetry, docs, rollback impact.
2. Run monthly game day (auth outage, db lock, failed migration).
3. Publish quarterly architecture/risk review notes.
- Exit evidence:
1. DoD policy adopted in PR process.
2. At least one game-day report completed.

## Weekly Execution Cadence

- Monday: risk review and sprint re-prioritization (`TL`, `SEC`, `SRE`)
- Wednesday: defect + incident review (`QA`, `BE`, `FE`)
- Friday: release readiness and KPI snapshot (`PO`, `TL`, `SRE`)

## Reporting Template (use weekly)

- Planned this week:
- Completed this week:
- SLO status:
- Open P0/P1 risks:
- Blockers needing decision:
- Next week commitments:

## Definition of Ironclad for This Repo

All criteria below must be true by **2026-07-09**:

1. Branch protection + required checks active; no direct merge to `main`.
2. CI runs deploy checks, tenancy/RBAC checks, and security scans on every PR.
3. Production deploy checklist + rollback drill evidence exists and is current.
4. SLO dashboards and paging alerts are in use by on-call.
5. No open critical vulnerabilities outside SLA.
6. Core user journeys are covered by automated tests and manual two-org smoke.
