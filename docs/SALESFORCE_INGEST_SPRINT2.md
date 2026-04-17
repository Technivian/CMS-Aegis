# Salesforce Ingestion (Sprint 2)

This sprint adds deterministic contract reconciliation for Salesforce imports.

## Reconciliation Keys

- Contract records now persist:
  - `source_system` (set to `salesforce`)
  - `source_system_id` (Salesforce record `Id`)
  - `source_system_url`
  - `source_last_modified_at`
- Upsert matching key: `(organization, source_system, source_system_id)`.

## Ingestion Paths

### API Preview

- Endpoint: `POST /contracts/api/integrations/salesforce/ingest-preview/`
- Authz: organization admin/owner.
- Payload:

```json
{
  "records": [{"Id": "006ABC", "Name": "Example Contract"}],
  "dry_run": true
}
```

### CLI Import

```bash
.venv/bin/python manage.py ingest_salesforce_records \
  --organization-slug <org-slug> \
  --path <records.json> \
  --dry-run
```

`records.json` must contain a top-level list of Salesforce records.

## Token Hardening

- Salesforce access and refresh tokens are now encrypted at rest.
- Backward compatibility: plaintext tokens are still readable and will be rewritten encrypted on next refresh/connect cycle.
