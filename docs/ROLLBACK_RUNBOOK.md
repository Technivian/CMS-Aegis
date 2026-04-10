# CMS-Aegis Rollback Runbook

> **Purpose** — Authoritative step-by-step guide for reverting the application
> to a known-good state. Use this when a deployment introduces a regression,
> data corruption, or security incident. All commands assume the production or
> staging server; adapt paths for other environments.

---

## 0. Before You Start

| Prerequisite | Command |
|---|---|
| SSH onto the app server | `ssh deploy@<host>` |
| Activate the virtualenv | `source /opt/cms-aegis/.venv/bin/activate` |
| Confirm current HEAD | `git -C /opt/cms-aegis log -1 --oneline` |
| Check migration state | `python manage.py showmigrations` |
| Verify backup exists | `ls -lth /backups/cms-aegis/ \| head -5` |

> **Never roll back without a database backup confirmed within the last hour.**

---

## 1. Classification

Determine the rollback level needed before acting:

| Level | Symptoms | Action |
|---|---|---|
| **L1 – Config only** | Wrong env var, bad feature flag | Update `.env`, restart Gunicorn |
| **L2 – Code only** | Python/template bug, no schema change | `git revert` or `git checkout`, restart |
| **L3 – Code + migrations** | Data shape changed; migration was applied | Reverse migration then code rollback |
| **L4 – Data corruption** | Rows deleted/corrupted | Restore from DB backup |

---

## 2. L1 — Config / Feature Flag Rollback

```bash
# 1. Edit the env file
nano /opt/cms-aegis/.env

# 2. Restart the application server
sudo systemctl restart gunicorn-cms-aegis

# 3. Smoke-test
curl -s -o /dev/null -w "%{http_code}" https://<host>/dashboard/
```

**Feature flags** (toggle without a restart when using database flags):

```bash
# Disable the redesign flag immediately
python manage.py shell -c "
from config.feature_flags import set_flag
set_flag('FEATURE_REDESIGN', False)
"
```

---

## 3. L2 — Code-Only Rollback

```bash
cd /opt/cms-aegis

# 1. Identify the last good commit
git log --oneline -10

# 2. Revert to it (keeps history)
git revert <bad-commit-sha> --no-edit
# OR hard-reset to a tag / known SHA (destructive — confirm with team):
# git reset --hard <good-sha>

# 3. Install any dependency changes
pip install -r requirements/runtime.txt

# 4. Collect static assets
python manage.py collectstatic --noinput

# 5. Restart
sudo systemctl restart gunicorn-cms-aegis

# 6. Verify health
curl -s -o /dev/null -w "%{http_code}" https://<host>/dashboard/
```

---

## 4. L3 — Migration Rollback

### 4.1 Current migration state (as of 2026-04-10)

| App | Latest applied migration |
|---|---|
| `contracts` | `0006_approvalrequest_organization_and_more` |
| `auth` | `0012_alter_user_first_name_max_length` |
| `admin` | `0003_logentry_add_action_flag_choices` |
| `sessions` | `0001_initial` |

### 4.2 Reverting a migration

```bash
cd /opt/cms-aegis

# 1. Back up the database FIRST
pg_dump -Fc cms_aegis > /backups/cms-aegis/pre-rollback-$(date +%Y%m%dT%H%M%S).dump
# SQLite equivalent:
cp db.sqlite3 /backups/cms-aegis/db-pre-rollback-$(date +%Y%m%dT%H%M%S).sqlite3

# 2. Identify the migration to revert to
python manage.py showmigrations contracts

# 3. Migrate backwards (replace 0003 with the target state)
python manage.py migrate contracts 0003_organization_client_organization_and_more

# 4. Check the state
python manage.py showmigrations contracts

# 5. Roll back the code
git revert <migration-commit-sha> --no-edit
pip install -r requirements/runtime.txt

# 6. Restart
sudo systemctl restart gunicorn-cms-aegis
```

> **Data warning**: reversing a migration that adds columns is usually safe.
> Reversing one that removes columns or tables may silently discard data.
> Always verify the migration's `reverse_sql` / `operations` before running.

### 4.4 Drill Evidence (2026-04-10)

Successful scratch-db rehearsal on a clean SQLite file:

```bash
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate contracts 0005_add_org_fk_to_budget_and_due_diligence --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate contracts 0006_approvalrequest_organization_and_more --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py audit_null_organizations
```

Observed result:

- clean scratch DB migrated forward successfully
- reverse from `0006` to `0005` succeeded
- re-apply to `0006` succeeded
- `audit_null_organizations` reported no `NULL organization` rows

Production-like caveat discovered on a populated copy:

```bash
cp db.sqlite3 /tmp/cms-aegis-drill.sqlite3
SQLITE_PATH=/tmp/cms-aegis-drill.sqlite3 python manage.py migrate contracts 0005_add_org_fk_to_budget_and_due_diligence --noinput
```

Observed failure:

- reverse migration failed with `UNIQUE constraint failed: new__contracts_clausecategory.name`
- root cause: after starter content was duplicated per organization, reversing `0006` attempts to collapse org-owned `ClauseCategory` rows back into a globally unique `name`

Operational conclusion:

- forward migration to `0006` is validated
- reverse migration on clean scratch data is validated
- reverse migration on populated tenant-owned starter-content data is **not** currently safe without a bespoke downgrade/data-collapse step
- do not run a live rollback from `0006` to `0005` on populated environments without additional migration work

### 4.3 Reverting all contracts migrations to zero (emergency only)

```bash
python manage.py migrate contracts zero
# This drops ALL contracts tables — only for staging/test environments
```

---

## 5. L4 — Database Restore

```bash
# --- PostgreSQL ---
# 1. Stop the application
sudo systemctl stop gunicorn-cms-aegis

# 2. Drop and recreate the database
psql -U postgres -c "DROP DATABASE cms_aegis;"
psql -U postgres -c "CREATE DATABASE cms_aegis OWNER cms_user;"

# 3. Restore from backup
pg_restore -Fc -d cms_aegis /backups/cms-aegis/<backup-file>.dump

# 4. Re-run any migrations added after the backup was taken
python manage.py migrate --run-syncdb

# 5. Restart
sudo systemctl restart gunicorn-cms-aegis

# --- SQLite (development / small deployments) ---
sudo systemctl stop gunicorn-cms-aegis
cp /backups/cms-aegis/<backup>.sqlite3 db.sqlite3
sudo systemctl start gunicorn-cms-aegis
```

---

## 6. Post-Rollback Verification Checklist

Run this after every rollback before declaring it complete.

```bash
# 1. Django system check
python manage.py check --deploy

# 2. Unit + integration tests
python manage.py test tests/ --verbosity=2

# 3. Cross-tenant isolation
python manage.py test tests.test_cross_tenant_isolation -v 2

# 4. Playwright smoke suite (requires Node + Playwright installed)
cd client && E2E_BASE_URL=https://<host> npx playwright test tests/e2e/

# 5. Manual smoke pass
#   Follow docs/MANUAL_SMOKE_CHECKLIST.md
```

For release and rollback verification, use the full two-org checklist in
[`docs/MANUAL_SMOKE_CHECKLIST.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MANUAL_SMOKE_CHECKLIST.md).

---

## 7. Comms Template

> **TO:** eng-alerts channel  
> **SUBJECT:** [CMS-Aegis] Rollback executed — \<date\>  
>
> **Incident summary:** \<one-line description\>  
> **Rollback level:** L\<1-4\>  
> **Rolled back to commit/migration:** \<sha or migration name\>  
> **Data impact:** None / \<describe\>  
> **All-clear time:** \<timestamp\>  
> **Follow-up action:** \<owner\> to create a post-mortem issue within 24 h

---

## 8. Drill Schedule

| Frequency | Drill |
|---|---|
| Monthly | L2 code rollback on staging |
| Quarterly | L3 migration rollback on staging with synthetic data |
| Semi-annually | L4 full DB restore on staging |

Drill results should be recorded in `docs/DRILL_LOG.md`.

---

*Last updated: 2026-04-10*
