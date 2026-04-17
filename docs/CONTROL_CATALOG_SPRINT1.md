# Control Catalog (Sprint 1)

This baseline catalog is captured weekly by `python manage.py collect_control_evidence`.

## Operational Controls
- `ops.request_metrics`: HTTP request counts, route buckets, status buckets, average latency.
- `ops.scheduler_health`: heartbeat freshness, expected interval, stale thresholds.
- `ops.database_health`: DB status and latency probes.
- `ops.alert_policy`: computed P1/P2 alerts and threshold context.

## Schedule
- Automated collection workflow: `.github/workflows/control-evidence-weekly.yml`
- Frequency: every Monday at 08:00 UTC
- Artifact: `control-evidence-weekly`

## Manual Collection
```bash
.venv/bin/python manage.py collect_control_evidence --output-dir docs/evidence
```
