# Alert Fire Drill - 2026-04-10

## Objective
Validate P1 and P2 routing for CMS Aegis observability bootstrap.

## Drill Scope
- P1 path: high 5xx and stalled scheduler heartbeat
- P2 path: elevated 5xx and p95 latency

## Procedure
1. Deploy monitoring rules from `ops/monitoring/prometheus-alert-rules.yml` to staging monitoring stack.
2. Trigger synthetic 5xx responses in staging (`/contracts/` test endpoint) for >5 minutes.
3. Pause scheduler heartbeat emission for >30 minutes in staging.
4. Verify P1 page and P2 ticket notifications.
5. Restore normal traffic and scheduler job.

## Expected Results
- P1 notifications delivered to on-call channel and paging target.
- P2 notification delivered to ticket queue and engineering channel.
- Alerts auto-resolve after rollback to normal signal levels.

## Evidence Collected
- Rules committed in repo.
- Drill command record attached to change request.
- Alert screenshots and timestamps to be added by SRE after staging run.
