# Observability Alert Policy (Implemented)

Last updated: 2026-04-13

## Alert IDs

- `OBS-P1-5XX-RATE`: 5xx rate >= 2.0%
- `OBS-P1-SCHEDULER-STALLED`: reminder scheduler stale heartbeat
- `OBS-P1-DB-DOWN`: database health probe reports `down`
- `OBS-P2-5XX-RATE`: 5xx rate >= 0.8% and < 2.0%
- `OBS-P2-DB-SLOW`: database health probe reports `slow`

## Evaluation Source

Alert policy is evaluated from in-app telemetry:

- request metrics snapshot (`contracts.observability.request_metrics_snapshot`)
- scheduler heartbeat snapshot (`contracts.observability.scheduler_health_snapshot`)
- DB probe snapshot (`contracts.observability.db_health_snapshot`)

## Commands

- Evaluate current alert state:
  - `.venv/bin/python manage.py evaluate_observability_alerts --json`
- Run fire drill scenarios:
  - `.venv/bin/python manage.py run_observability_fire_drill --scenario scheduler_stale`
  - `.venv/bin/python manage.py run_observability_fire_drill --scenario error_rate_spike`

## Escalation

- `P1`: page primary on-call immediately, open incident channel, execute rollback/smoke decision tree.
- `P2`: create incident ticket and notify engineering channel within 15 minutes.
