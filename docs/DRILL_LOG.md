# CMS Aegis Drill Log

## 2026-04-10: Migration Rollback Drill

- Environment: local scratch SQLite databases
- Scope: `contracts` migration rollback and re-apply around `0006_approvalrequest_organization_and_more`

### Clean Scratch DB

Commands:

```bash
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate contracts 0005_add_org_fk_to_budget_and_due_diligence --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate contracts 0006_approvalrequest_organization_and_more --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py audit_null_organizations
```

Result:

- success
- reverse path from `0006` to `0005` completed
- re-apply to `0006` completed
- no `NULL organization` rows remained

### Populated Copy

Commands:

```bash
cp db.sqlite3 /tmp/cms-aegis-drill.sqlite3
SQLITE_PATH=/tmp/cms-aegis-drill.sqlite3 python manage.py migrate contracts 0005_add_org_fk_to_budget_and_due_diligence --noinput
```

Result:

- failed
- error: `UNIQUE constraint failed: new__contracts_clausecategory.name`

Conclusion:

- populated downgrade is not currently safe after tenant-owned starter content was duplicated per org
- rollback from `0006` to `0005` needs a dedicated downgrade/data-collapse strategy before it should be attempted on real data

## 2026-04-10: Migration Rollback Drill Re-Run (Ironclad Activation)

- Environment: local scratch SQLite databases
- Scope: repeatability verification for `contracts` migration rollback and re-apply around `0006_approvalrequest_organization_and_more`

### Clean Scratch DB

Commands:

```bash
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate contracts 0005_add_org_fk_to_budget_and_due_diligence --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py migrate contracts 0006_approvalrequest_organization_and_more --noinput
SQLITE_PATH=/tmp/cms-aegis-drill-clean.sqlite3 python manage.py audit_null_organizations
```

Result:

- success
- reverse path from `0006` to `0005` completed
- re-apply to `0006` completed
- no `NULL organization` rows remained

### Populated Copy

Commands:

```bash
cp db.sqlite3 /tmp/cms-aegis-drill.sqlite3
SQLITE_PATH=/tmp/cms-aegis-drill.sqlite3 python manage.py migrate contracts 0005_add_org_fk_to_budget_and_due_diligence --noinput
```

Result:

- failed
- error: `UNIQUE constraint failed: new__contracts_clausecategory.name`

Conclusion:

- rollback from `0006` to `0005` remains unsafe on populated tenant-owned data without a dedicated downgrade migration
