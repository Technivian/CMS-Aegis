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

### Live Sync

- Endpoint: `POST /contracts/api/integrations/salesforce/sync/`
- Authz: organization admin/owner.
- Payload:

```json
{
  "dry_run": false,
  "limit": 200
}
```

### Sync Run History

- Endpoint: `GET /contracts/api/integrations/salesforce/sync-runs/?limit=20`
- Returns most recent sync execution records for audit and troubleshooting.
- Identity settings page now shows recent sync runs and connection status.

### CLI Import

```bash
.venv/bin/python manage.py ingest_salesforce_records \
  --organization-slug <org-slug> \
  --path <records.json> \
  --dry-run
```

`records.json` must contain a top-level list of Salesforce records.

### CLI Live Sync

```bash
.venv/bin/python manage.py sync_salesforce_contracts \
  --organization-slug <org-slug> \
  --limit 200
```

## Scheduler + Retry Operations

- Automated scheduler workflow:
  - `.github/workflows/salesforce-sync-scheduler.yml`
  - queues and processes background jobs every 30 minutes.
- Salesforce sync background jobs use retry with backoff and dead-lettering:
  - first failure: re-queued with delay
  - terminal failure after max attempts: `FAILED` with `dead_lettered_at` populated
- Overlap protection:
  - sync creation is blocked when another run is already `RUNNING` for the organization.

## Token Hardening

- Salesforce access and refresh tokens are now encrypted at rest.
- Backward compatibility: plaintext tokens are still readable and will be rewritten encrypted on next refresh/connect cycle.
