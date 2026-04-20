# Go-Live Todo

This is the execution board for the next release push. It tracks the ten highest-priority steps, current status, evidence, and the next action.

## Current Snapshot

- Code-level guardrails are in good shape.
- Production deploy checks, migrations, null-org audit, and tenant isolation have passed locally.
- Security audits are now green locally.
- The disposable Postgres rehearsal is green end to end, including integration evidence, browser smoke, backup/restore, and release gate checks.
- The only remaining blocker to a real launch is production cutover itself.

## Todo Board

| # | Step | Status | Evidence / Command | Blocker | Next Action |
|---|---|---|---|---|---|
| 1 | Run release gate in a live, network-enabled environment | Done in rehearsal | `python manage.py generate_release_gate_report --fail-on-no-go` | Production cutover still pending | Re-run on production target during cutover |
| 2 | Get `npm audit` passing for `client` | Done | `npm --prefix client audit --audit-level=high` | None | Already green |
| 3 | Get `npm audit` passing for `theme/static_src` | Done | `npm --prefix theme/static_src audit --audit-level=high` | None | Already green |
| 4 | Get `pip-audit` passing for runtime requirements | Done | `python -m pip_audit --disable-pip --no-deps -r requirements/runtime.txt` | None | Already green |
| 5 | Record recent successful Salesforce sync evidence | Done in rehearsal | `python manage.py generate_sprint3_integration_report` | Production sync evidence still needed | Re-run against production data during launch |
| 6 | Run staging smoke checklist | Done in rehearsal | [docs/MANUAL_SMOKE_CHECKLIST.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MANUAL_SMOKE_CHECKLIST.md) | Production smoke still required | Repeat on production cutover host if needed |
| 7 | Confirm a fresh backup exists | Done in rehearsal | `pg_dump -Fc "$PGDATABASE" > /backups/cms-aegis/pre-cutover-<ts>.dump` | Fresh production backup still required | Take the live backup before cutover |
| 8 | Rehearse restore | Done in rehearsal | `dropdb`, `createdb`, `pg_restore`, then rerun checks | Production restore drill still recommended | Repeat with the live backup on staging if possible |
| 9 | Deploy to production and rerun gates | Pending | `migrate --noinput`, `audit_null_organizations`, release gate report | Must wait for production change window | Deploy only after all gates are green |
| 10 | Verify post-deploy smoke and reopen traffic | Pending | Production smoke / health checks | Must wait for production cutover | Open traffic only after verification |

## What Is Already Done

- `python manage.py check --deploy --fail-level WARNING`
- `python manage.py test tests.test_cross_tenant_isolation -v 1`
- `python manage.py migrate --noinput` in the local workspace context
- `python manage.py audit_null_organizations` in the local workspace context
- `npm --prefix client audit --audit-level=high`
- `npm --prefix theme/static_src audit --audit-level=high`
- `python -m pip_audit --disable-pip --no-deps -r requirements/runtime.txt`
- `python manage.py verify_postgres_cutover`
- `python manage.py generate_sprint3_integration_report`
- `python manage.py generate_esign_integration_report --organization-slug demo-firm`
- Playwright smoke suite against a local Postgres rehearsal server
- Backup/restore rehearsal on the disposable Postgres cluster

## Stop Conditions

Do not proceed to production cutover if any of these remain true:

- release gate is `NO-GO`
- either npm audit fails
- pip-audit fails
- Salesforce sync evidence is missing
- staging smoke fails
- backup or restore validation is incomplete
