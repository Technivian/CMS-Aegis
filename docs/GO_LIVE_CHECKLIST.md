# CMS Aegis Go-Live Checklist

Use this when you want the fastest safe path from staging to production cutover.

## Current Local Evidence

As of the latest workspace check:

- `manage.py check --deploy --fail-level WARNING` passed with production env values.
- `tests.test_cross_tenant_isolation` passed.
- `manage.py migrate --noinput` found no migrations to apply.
- `manage.py audit_null_organizations` found no NULL organization rows.
- `npm --prefix client audit --audit-level=high` passed.
- `npm --prefix theme/static_src audit --audit-level=high` passed.
- `python -m pip_audit --disable-pip --no-deps -r requirements/runtime.txt` passed.
- `manage.py generate_release_gate_report` returned `NO-GO` locally because:
  - the current workspace DB has no recent successful Salesforce sync.
  - the current workspace DB has no webhook delivery evidence.

Treat that as the stop condition until the same gates are green in a network-enabled staging or production-like environment.

## 1. Set Production-Shape Environment

Run from the repo root on staging or the production host:

```bash
export DJANGO_ENV=production
export DJANGO_SECRET_KEY='<long-random-secret>'
export ALLOWED_HOSTS='staging.example.com'
export CSRF_TRUSTED_ORIGINS='https://staging.example.com'
export DEFAULT_FROM_EMAIL='ops@example.com'
export DATABASE_URL='postgresql://<user>:<password>@<host>:5432/<db>?sslmode=require'
export DB_CONN_MAX_AGE=60
export DB_SSL_REQUIRE=true
export SECURE_SSL_REDIRECT=true
export SECURE_HSTS_PRELOAD=true
```

If SSO is enabled, add the OIDC variables documented in [README_CMS_AEGIS.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/README_CMS_AEGIS.md).

## 2. Preflight Checks

Run these in order:

```bash
python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
python manage.py check --deploy --fail-level WARNING
python manage.py migrate --noinput
python manage.py audit_null_organizations
python manage.py test tests.test_cross_tenant_isolation -v 1
python manage.py generate_release_gate_report --fail-on-no-go
```

Proceed only if:

- DB engine prints `django.db.backends.postgresql`
- deploy check passes
- migrations apply cleanly
- `audit_null_organizations` reports no violations
- cross-tenant isolation passes
- release gate report returns `GO`

## 3. Staging Smoke

Before production cutover, run the manual smoke checklist in [docs/MANUAL_SMOKE_CHECKLIST.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MANUAL_SMOKE_CHECKLIST.md).

Minimum coverage:

- logged-out `/dashboard/` redirects to `/login/`
- Org A and Org B dashboards only show in-org data
- cross-org contract access returns `404` or `403`
- Org-admin team management works
- cross-org search does not leak results

## 4. Production Cutover

Follow [docs/PRODUCTION_CUTOVER_RUNBOOK.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/PRODUCTION_CUTOVER_RUNBOOK.md) for the exact production sequence.

At a minimum, the production operator must:

1. Confirm the backup is fresh.
2. Put the app in maintenance mode if your platform supports it.
3. Deploy the approved commit.
4. Re-run:

```bash
python manage.py migrate --noinput
python manage.py audit_null_organizations
python manage.py generate_release_gate_report --fail-on-no-go
```

5. Bring traffic back only if all checks pass.

## 5. Stop Conditions

Do not cut over if any of these are true:

- deploy check fails
- migrations fail
- `audit_null_organizations` fails
- release gate is `NO-GO`
- smoke checklist shows any cross-tenant leakage

## 6. Rollback

If the post-deploy smoke fails, follow [docs/ROLLBACK_RUNBOOK.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/ROLLBACK_RUNBOOK.md) immediately.

## 7. Action Matrix

Use this as the working board. The percentages are a simple readiness estimate for the item itself, not the whole launch.

| Step | Owner | Command / Action | Pass Criteria | Severity | Est. Time | Item % | If Done, Overall Readiness |
|---|---|---|---|---|---:|---:|---:|
| Production env sanity | Eng | Set `DJANGO_ENV`, secret key, hosts, CSRF, DB URL, secure flags | `manage.py check --deploy --fail-level WARNING` passes | High | 10 min | 100% | no change; already complete |
| DB / migrations | Eng | Run `python manage.py migrate --noinput` on staging/prod target | `audit_null_organizations` shows no violations; no unapplied migrations | High | 15 min | 100% | no change; already complete locally |
| Cross-tenant isolation | Eng | Run `python manage.py test tests.test_cross_tenant_isolation -v 1` | Test suite passes with no leakage or authorization regressions | Critical | 20 min | 100% | no change; already complete locally |
| Security audits | Eng | Run `python manage.py generate_release_gate_report --fail-on-no-go` in a network-enabled environment | `npm audit` and `pip-audit` both pass | Critical | 20-40 min | 100% | about 63% |
| Salesforce / integration evidence | Ops / Eng | Produce a recent successful sync and confirm dead-letter queue is empty | `generate_release_gate_report` shows integrations `pass` | High | 20-60 min | 0% | about 50% |
| Staging smoke | QA / Eng | Follow [docs/MANUAL_SMOKE_CHECKLIST.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MANUAL_SMOKE_CHECKLIST.md) | All allow/deny cases match expected tenant isolation behavior | Critical | 30-60 min | 0% | about 58% |
| Backup + rollback rehearsal | Ops | Capture backup and validate restore path | Fresh backup exists; restore completes; post-restore checks pass | Critical | 30-90 min | 0% | about 53% |
| Production cutover | Ops / Eng | Deploy, rerun checks, restore traffic | All checks green post-deploy; traffic is back on | Critical | 15-30 min | 0% | 100% |

### Fastest Safe Sequence

1. Run security audits in a network-enabled staging environment.
2. Create or verify one successful Salesforce sync.
3. Complete the staging smoke checklist.
4. Do the backup + restore rehearsal.
5. Deploy to production, rerun checks, and only then open traffic.

### Current Bottleneck

The current blocker is not code correctness. It is release evidence:

- recent successful Salesforce sync evidence
- webhook delivery evidence
- staging smoke completion
- rollback rehearsal
