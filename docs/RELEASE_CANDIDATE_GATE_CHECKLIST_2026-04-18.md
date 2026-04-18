# Release Candidate Gate Checklist (2026-04-18)

Use this checklist for every production release candidate.

## A. CI and Security Gates

1. `platform-guardrails` workflow green.
2. `security-scans` workflow green.
3. `verify-ui` workflow green.
4. `pip-audit --disable-pip --no-deps -r requirements/runtime.txt` clean.
5. `npm --prefix client audit --audit-level=high` clean.
6. `npm --prefix theme/static_src audit --audit-level=high` clean.

## B. Database and Cutover Gates

1. `python manage.py migrate --check` clean in target environment.
2. `postgres-cutover-check` workflow succeeded.
3. `postgres-cutover-evidence` artifact attached to release notes.
4. `cutover_ready=true` in evidence payload.

## C. Salesforce and Integration Ops Gates

1. Active Salesforce connection present in target organization.
2. At least one successful sync run in `/contracts/api/integrations/salesforce/sync-runs/`.
3. Scheduler workflow `.github/workflows/salesforce-sync-scheduler.yml` last run succeeded.
4. Webhook diagnostics endpoint `/contracts/api/integrations/webhooks/deliveries/` checked:
   - no stuck `PENDING` items beyond expected window
   - failed deliveries either retrying or dead-lettered with traceable error.

## D. Functional Smoke Gates

1. Org admin login and dashboard load.
2. Contract list/search load.
3. Salesforce sync manual trigger (`dry_run` and live) verified.
4. Workflow approval transition smoke.
5. Export/download permission checks for owner/admin/member role boundaries.

## E. Rollback and Evidence Gates

1. Rollback command path verified against [`docs/ROLLBACK_RUNBOOK.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/ROLLBACK_RUNBOOK.md).
2. Manual smoke checklist executed after rollback rehearsal.
3. Drill entry recorded in [`docs/DRILL_LOG.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/DRILL_LOG.md).
4. All artifact links attached in PR and release notes.

## Go/No-Go Rule

- `GO` only if sections A-E are fully complete.
- Any failed item => `NO-GO`, open remediation ticket, re-run checklist.
