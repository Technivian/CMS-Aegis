# Production Cutover Operator Checklist

Use this as the one-page execution sheet during the live window.

## Before You Start

- [ ] Release gate is green in CI
- [ ] Staging or rehearsal smoke passed
- [ ] Backup and restore rehearsal passed
- [ ] Production host, DB, and deployment access are confirmed
- [ ] Rollback path is ready

## 1. Confirm Target

- [ ] On the production host, confirm the deployed commit:

```bash
git rev-parse HEAD
```

- [ ] Confirm PostgreSQL:

```bash
python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
```

Pass if:

- commit is the approved release commit
- output is `django.db.backends.postgresql`

Stop if:

- commit is wrong
- DB engine is not PostgreSQL

## 2. Take Backup

- [ ] Capture a fresh backup:

```bash
pg_dump -Fc "$PGDATABASE" > "/backups/cms-aegis/pre-cutover-$(date +%Y%m%dT%H%M%S).dump"
```

Pass if:

- dump file exists
- dump size is non-zero

Stop if:

- backup fails
- backup cannot be verified

## 3. Drain Traffic

- [ ] Enable maintenance mode or drain the load balancer

Pass if:

- new user traffic is blocked while deployment is in progress

Stop if:

- traffic cannot be drained cleanly

## 4. Deploy

- [ ] Deploy the approved release commit

```bash
git fetch origin codex/cms-aegis-activation
git checkout <release-commit-sha>
```

Pass if:

- the host is on the approved commit
- services restart cleanly

Stop if:

- deployment fails
- wrong commit is deployed

## 5. Run Production Checks

- [ ] Apply migrations

```bash
python manage.py migrate --noinput
```

- [ ] Check null organizations

```bash
python manage.py audit_null_organizations
```

- [ ] Verify cutover readiness

```bash
python manage.py verify_postgres_cutover
```

- [ ] Re-run the release gate

```bash
python manage.py generate_release_gate_report --fail-on-no-go
```

Pass if:

- migrations succeed
- no NULL organization violations are reported
- cutover readiness is `true`
- release gate is `GO`

Stop if:

- any command fails
- release gate is `NO-GO`

## 6. Run Live Smoke

- [ ] Run the manual smoke checklist in [docs/MANUAL_SMOKE_CHECKLIST.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MANUAL_SMOKE_CHECKLIST.md)

Minimum coverage:

- anonymous `/dashboard/` redirects to `/login/`
- Org A and Org B stay isolated
- cross-org contract access is denied
- admin/team flows work
- search does not leak data across orgs

Pass if:

- every smoke case matches expected behavior

Stop if:

- any leakage or auth regression appears

## 7. Reopen Traffic

- [ ] Restore traffic through the platform’s normal path

Pass if:

- the app stays healthy under live routing

Stop if:

- the app becomes unstable after traffic returns

## 8. Final Verify

- [ ] Re-run final checks:

```bash
python manage.py audit_null_organizations
python manage.py generate_release_gate_report --fail-on-no-go
```

Pass if:

- release gate remains `GO`
- no new violations appeared after traffic restoration

## Rollback Trigger

Rollback immediately if any of these happen:

- migrations fail
- release gate is `NO-GO`
- smoke checks fail
- cross-tenant leakage is detected
- the app becomes unstable after traffic is reopened

Use [docs/ROLLBACK_RUNBOOK.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/ROLLBACK_RUNBOOK.md) for the rollback procedure.

