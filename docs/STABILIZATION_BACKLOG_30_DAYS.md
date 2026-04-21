# CMS Aegis 30-Day Stabilization Backlog

## Purpose

This backlog turns the takeover plan into implementation-ready work. It is intentionally biased toward stability, tenant safety, operational readiness, and release confidence rather than new product surface area.

## Priority Scale

- `P0`: Must complete before a production handoff or significant customer rollout.
- `P1`: Should complete within the 30-day window to reduce operational and product risk.
- `P2`: Valuable follow-on work that should start if P0/P1 items are under control.

## Current Baseline

- Tenant-owned support models are in place.
- Legacy `NULL organization` rows have been promoted or cleaned up.
- Production settings are split into environment-driven modules.
- Full test suite passes: `134` tests.

## P0 Backlog

### TKT-001: Add CI guardrail for tenant drift

- Priority: `P0`
- Outcome: CI fails if tenant-owned models ever reintroduce `organization IS NULL` rows.
- Files:
  - [`.github/workflows/ui-verification.yml`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.github/workflows/ui-verification.yml)
  - [`contracts/management/commands/audit_null_organizations.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/management/commands/audit_null_organizations.py)
- Tasks:
  - Add a workflow step that runs `python manage.py audit_null_organizations`.
  - Fail the job on non-zero exit.
  - Make sure the command stays deterministic under test and CI database setup.
- Acceptance criteria:
  - CI runs the audit command on every PR and `main` push.
  - A synthetic `NULL organization` row causes the workflow to fail.

### TKT-002: Add role-action permission matrix tests

- Priority: `P0`
- Outcome: Critical routes are covered by explicit `OWNER`, `ADMIN`, and `MEMBER` expectations.
- Files:
  - [`tests/test_cross_tenant_isolation.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/tests/test_cross_tenant_isolation.py)
  - [`contracts/permissions.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/permissions.py)
  - [`contracts/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/views.py)
- Tasks:
  - Create fixtures for each organization role.
  - Add negative and positive tests for create, edit, approve, delete, and admin-facing actions.
  - Move any ad hoc permission checks into reusable helpers where gaps appear.
- Acceptance criteria:
  - Each critical object type has at least one role-specific allow test and one deny test.
  - Permission behavior is enforced consistently by tests, not just by UI visibility.

### TKT-003: Manual smoke checklist for two-org validation

- Priority: `P0`
- Outcome: The app is validated as a real user, not only through automated tests.
- Files:
  - [`docs/ROLLBACK_RUNBOOK.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/ROLLBACK_RUNBOOK.md)
  - [`README_CMS_AEGIS.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/README_CMS_AEGIS.md)
- Tasks:
  - Write a repeatable smoke checklist using two organizations and at least two roles.
  - Include dashboard, contract create/edit, workflow create/edit, approval flows, privacy records, clause templates, and legal holds.
  - Record expected outcomes for cross-org denial cases.
- Acceptance criteria:
  - A reviewer can follow the checklist without source-code knowledge.
  - The checklist is suitable for staging or pre-release validation.

### TKT-004: Centralize scoped form/query helpers

- Priority: `P0`
- Outcome: Tenant scoping logic is harder to bypass in future features.
- Files:
  - [`contracts/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/views.py)
  - [`contracts/forms.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/forms.py)
  - [`contracts/tenancy.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/tenancy.py)
- Tasks:
  - Extract repeated organization-scoping setup from class-based and function views into shared helpers.
  - Standardize create/update form initialization so scoped querysets are always applied before validation.
  - Remove duplicated inline scoping blocks where practical.
- Acceptance criteria:
  - New create/update views have one obvious pattern for scoped foreign-key handling.
  - At least the high-risk workflow/privacy/approval forms use the shared path.

## P1 Backlog

### TKT-005: Add structured request logging and correlation IDs

- Priority: `P1`
- Outcome: Production failures can be traced across logs and background work.
- Files:
  - [`contracts/middleware.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/middleware.py)
  - [`config/settings_base.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_base.py)
  - [`logs/`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/logs)
- Tasks:
  - Generate or propagate a request ID in middleware.
  - Add structured logging format with request ID, user ID, organization ID, path, and status code.
  - Document local and production logging expectations.
- Acceptance criteria:
  - A single request can be traced across app logs.
  - Error log lines include enough context to identify the user and org boundary involved.

### TKT-006: Create overdue work and deadline health reporting

- Priority: `P1`
- Outcome: Operators can see overdue approvals, expiring contracts, and privacy deadlines without SQL.
- Files:
  - [`contracts/admin.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/admin.py)
  - [`contracts/models.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/models.py)
  - [`contracts/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/views.py)
- Tasks:
  - Add admin filters or views for overdue approvals and open privacy deadlines.
  - Expose at least one dashboard signal or admin list for expiring contracts and pending work.
  - Ensure all report queries remain organization-scoped.
- Acceptance criteria:
  - Admin users can answer “what is overdue” without manual database inspection.
  - Report pages do not leak cross-org data.

### TKT-007: Formalize production env contract

- Priority: `P1`
- Outcome: Deployments fail fast when required configuration is missing or unsafe.
- Files:
  - [`.env.example`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.env.example)
  - [`README_CMS_AEGIS.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/README_CMS_AEGIS.md)
  - [`config/settings_production.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_production.py)
- Tasks:
  - Document required vs optional production variables.
  - Add startup assertions for any missing critical config beyond the current secret/host checks.
  - Document deployment verification commands.
- Acceptance criteria:
  - A new operator can configure production from docs alone.
  - Missing critical configuration produces a clear startup error.

### TKT-008: Add export/download permission tests

- Priority: `P1`
- Outcome: document and file access are covered, not just CRUD screens.
- Files:
  - [`tests/test_cross_tenant_isolation.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/tests/test_cross_tenant_isolation.py)
  - [`contracts/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/views.py)
  - [`contracts/urls.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/urls.py)
- Tasks:
  - Identify all download, export, attachment, and generated-document endpoints.
  - Add cross-org and unauthorized tests.
  - Patch any unscoped file lookups.
- Acceptance criteria:
  - Every export or download route has at least one negative permission test.
  - Downloaded content is inaccessible across organizations.

## P2 Backlog

### TKT-009: Split `contracts/views.py` by domain

- Priority: `P2`
- Outcome: High-risk logic becomes easier to review and maintain.
- Files:
  - [`contracts/views.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/views.py)
  - New modules under [`contracts/`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts)
- Tasks:
  - Break workflow/privacy/approval/reporting views into separate modules.
  - Keep URL names and external behavior stable.
  - Move shared mixins/helpers into a common module.
- Acceptance criteria:
  - View modules are organized by domain, not one monolithic file.
  - Existing route behavior remains unchanged under the test suite.

### TKT-010: Add staging rollback and migration drill evidence

- Priority: `P2`
- Outcome: Migration and rollback safety are demonstrated, not assumed.
- Files:
  - [`docs/ROLLBACK_RUNBOOK.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/ROLLBACK_RUNBOOK.md)
  - [`contracts/migrations/`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/migrations)
- Tasks:
  - Execute one forward migration and rollback drill in staging or a staging-like environment.
  - Capture exact commands, duration, and known caveats.
  - Update the runbook with real evidence rather than generic guidance.
- Acceptance criteria:
  - Rollback procedure includes one recorded successful rehearsal.
  - Migration risk for tenant-owned support models is explicitly documented.

## Suggested 30-Day Sequencing

### Week 1

- TKT-001 Add CI guardrail for tenant drift
- TKT-002 Add role-action permission matrix tests
- TKT-003 Manual smoke checklist for two-org validation

### Week 2

- TKT-004 Centralize scoped form/query helpers
- TKT-008 Add export/download permission tests

### Week 3

- TKT-005 Add structured request logging and correlation IDs
- TKT-006 Create overdue work and deadline health reporting

### Week 4

- TKT-007 Formalize production env contract
- TKT-010 Add staging rollback and migration drill evidence
- Start TKT-009 if earlier work finishes cleanly

## Definition of Done

- Code path is covered by automated tests where applicable.
- Tenant and role implications are documented in the PR description.
- Any migration or operator-facing change is reflected in docs.
- `manage.py check` passes.
- Relevant test suite passes locally and in CI.
