# Staging PostgreSQL Rehearsal (ICL-002)

Last updated: 2026-04-13

Use this once on staging to complete `ICL-002` evidence:
- Postgres runtime verified
- migration executed
- rollback point created
- restore path validated
- timings captured

## 1) Preconditions

Run from repo root on staging host:

```bash
cd /opt/cms-aegis
source .venv/bin/activate
```

Required environment:

```bash
export DJANGO_ENV=production
export DJANGO_SECRET_KEY='<staging-secret>'
export ALLOWED_HOSTS='staging.example.com'
export CSRF_TRUSTED_ORIGINS='https://staging.example.com'
export DEFAULT_FROM_EMAIL='ops@example.com'
export DATABASE_URL='postgresql://<user>:<password>@<host>:5432/<db>?sslmode=require'
```

Optional tuning:

```bash
export DB_CONN_MAX_AGE=60
export DB_SSL_REQUIRE=true
```

## 2) Fast Fail Checks

```bash
python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
python manage.py check --deploy --fail-level WARNING
python manage.py showmigrations contracts
```

Expected:
- DB engine output: `django.db.backends.postgresql`
- deploy check: no failures

## 3) Create Rollback Point Backup

```bash
export BACKUP_DIR=/backups/cms-aegis
export TS=$(date +%Y%m%dT%H%M%S)
mkdir -p "$BACKUP_DIR"
export BACKUP_FILE="$BACKUP_DIR/pre-cutover-$TS.dump"

time pg_dump -Fc "$PGDATABASE" > "$BACKUP_FILE"
ls -lh "$BACKUP_FILE"
```

## 4) Migration Rehearsal + Guardrail Verification

```bash
time python manage.py migrate --noinput
python manage.py audit_null_organizations
python manage.py test tests.test_cross_tenant_isolation -v 1
```

Expected:
- migrations complete successfully
- `audit_null_organizations` reports no null-organization violations
- cross-tenant isolation test suite passes

## 5) Restore Rehearsal (Rollback Validation)

Stop app traffic first if needed by your staging topology.

```bash
export RESTORE_TS=$(date +%Y%m%dT%H%M%S)

time dropdb "$PGDATABASE"
time createdb "$PGDATABASE"
time pg_restore -Fc -d "$PGDATABASE" "$BACKUP_FILE"

python manage.py migrate --noinput
python manage.py audit_null_organizations
python manage.py test tests.test_cross_tenant_isolation -v 1
```

Expected:
- database restore succeeds
- app schema and tenant checks return to green state

## 6) DRILL_LOG Entry Template

Paste and complete in `docs/DRILL_LOG.md`:

```md
## YYYY-MM-DD: Staging PostgreSQL Rehearsal (ICL-002)

- Environment: staging, PostgreSQL
- Operator: <name>
- Start time: <timestamp>
- End time: <timestamp>
- Backup file: <path>

### Command Results

- DB engine check: PASS (`django.db.backends.postgresql`)
- `manage.py check --deploy --fail-level WARNING`: PASS/FAIL
- `manage.py migrate --noinput`: PASS/FAIL
- `manage.py audit_null_organizations`: PASS/FAIL
- `tests.test_cross_tenant_isolation`: PASS/FAIL
- Restore rehearsal (`dropdb/createdb/pg_restore`): PASS/FAIL

### Timings

- Backup duration: <duration>
- Migrate duration: <duration>
- Restore duration: <duration>

### Issues Observed

- <none or details>

### Conclusion

- Rehearsal status: PASS/FAIL
- Ready for production cutover: YES/NO
```

## 7) Completion Criteria for ICL-002

`ICL-002` is complete only when:
1. This staging rehearsal is executed successfully.
2. Timings and outputs are recorded in `docs/DRILL_LOG.md`.
3. Backup artifact path is retained and accessible.
