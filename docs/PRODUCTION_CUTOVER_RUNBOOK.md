# Production Cutover Runbook

Use this only when the app is ready to go live and you have access to the production host, database, and deployment mechanism.

For a compressed operator view, use [docs/PRODUCTION_CUTOVER_OPERATOR_CHECKLIST.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/PRODUCTION_CUTOVER_OPERATOR_CHECKLIST.md).

## Scope

This runbook covers the final production steps:

1. confirm production readiness
2. take a fresh backup
3. deploy the approved commit
4. run production migrations and release gates
5. run live smoke checks
6. reopen traffic only after verification
7. roll back immediately if the post-deploy checks fail

## Preconditions

Do not start unless all of these are true:

- release gate is green in CI
- staging or rehearsal smoke has passed
- backup and restore rehearsal has passed
- you know the current production commit and deployment target
- you have the production database credentials and host access
- you have the rollback path ready

## Required Environment

Set these on the production host or in the deployment environment:

```bash
export DJANGO_ENV=production
export DJANGO_SECRET_KEY='<long-random-secret>'
export DATABASE_URL='postgresql://<user>:<password>@<host>:5432/<db>?sslmode=require'
export ALLOWED_HOSTS='your-production-hostname.example.com'
export CSRF_TRUSTED_ORIGINS='https://your-production-hostname.example.com'
export DEFAULT_FROM_EMAIL='ops@example.com'
export ALLOW_SQLITE_IN_PRODUCTION='false'
export DB_SSL_REQUIRE='true'
export SECURE_SSL_REDIRECT='true'
export SECURE_HSTS_PRELOAD='true'
```

If SSO is enabled, also set the OIDC / SAML variables required by [README_IRONCLAD.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/README_IRONCLAD.md).

## Step 1: Confirm the Target

On the production host:

```bash
git rev-parse HEAD
python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
```

Pass criteria:

- the commit matches the approved release commit
- the DB engine prints `django.db.backends.postgresql`

Stop if:

- the host is not on the expected commit
- the database engine is not PostgreSQL

## Step 2: Take a Fresh Backup

Run the production backup using your platform’s approved mechanism.

Example:

```bash
pg_dump -Fc "$PGDATABASE" > "/backups/cms-aegis/pre-cutover-$(date +%Y%m%dT%H%M%S).dump"
```

Pass criteria:

- backup file is created successfully
- file size is non-zero
- backup location is recorded

Stop if:

- the backup command fails
- the backup file cannot be verified

## Step 3: Put the App in Maintenance Mode

Use your platform’s maintenance or traffic-drain mechanism.

Examples:

- disable the load balancer target
- enable a maintenance page
- pause background traffic to the app

Pass criteria:

- no new user traffic reaches the app during deployment

Stop if:

- traffic cannot be drained cleanly

## Step 4: Deploy the Approved Commit

Deploy the approved `codex/ironclad-activation` commit.

Example:

```bash
git fetch origin codex/ironclad-activation
git checkout <release-commit-sha>
```

Replace the checkout command with your actual deployment process if the platform uses artifacts or a release pipeline.

Pass criteria:

- the production host is on the approved commit
- application services restart cleanly

Stop if:

- the wrong commit is deployed
- the app fails to start

## Step 5: Run Production Database Migration

```bash
python manage.py migrate --noinput
python manage.py audit_null_organizations
python manage.py verify_postgres_cutover
python manage.py generate_release_gate_report --fail-on-no-go
```

Pass criteria:

- migrations complete successfully
- `audit_null_organizations` reports no violations
- `verify_postgres_cutover` reports `cutover_ready: true`
- release gate reports `GO`

Stop if:

- any migration fails
- any audit fails
- release gate is `NO-GO`

## Step 6: Run the Live Smoke Checks

Run the manual smoke checklist in [docs/MANUAL_SMOKE_CHECKLIST.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MANUAL_SMOKE_CHECKLIST.md).

Minimum live coverage:

- anonymous `/dashboard/` redirects to `/login/`
- Org A and Org B data stay isolated
- cross-org contract access returns `403` or `404`
- admin/team flows work
- search does not leak cross-tenant data

Pass criteria:

- every smoke case passes exactly as expected

Stop if:

- any cross-tenant leakage appears
- any protected route is accessible without the right org or role
- any login or session issue blocks verification

## Step 7: Reopen Traffic

Only after the smoke checks are green:

```bash
# replace this with your platform-specific action
echo "Reopen traffic"
```

Pass criteria:

- production traffic is restored
- the app remains healthy under normal routing

Stop if:

- the app degrades when traffic is restored

## Step 8: Post-Deploy Verification

Run a final check sequence:

```bash
python manage.py audit_null_organizations
python manage.py generate_release_gate_report --fail-on-no-go
```

Optionally re-run the live smoke checks if the traffic restore changed anything operationally.

Pass criteria:

- the release gate remains `GO`
- no new violations appear after traffic is restored

## Rollback Trigger

Rollback immediately if any of these happen:

- migrations fail
- release gate is `NO-GO`
- smoke checks fail
- cross-tenant leakage is detected
- the app becomes unstable after traffic is reopened

## Rollback Path

Use [docs/ROLLBACK_RUNBOOK.md](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/ROLLBACK_RUNBOOK.md) if any post-deploy verification fails.

## Final Exit Criteria

Production cutover is complete only when:

- the approved commit is deployed
- migrations are green
- cutover verification is green
- live smoke is green
- traffic is restored
- rollback is no longer required
