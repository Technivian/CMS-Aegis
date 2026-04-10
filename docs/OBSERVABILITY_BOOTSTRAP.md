# Observability Bootstrap (SLO + Alerting)

This document defines the minimum monitoring baseline for CMS Aegis.

## Scope

- HTTP application traffic
- Auth and SSO health
- Background reminder scheduler health
- Database latency and error signals

## SLOs (initial)

- Availability SLO: `99.9%` monthly for authenticated routes
- API latency SLO: `p95 < 500ms` for `/dashboard/`, `/contracts/`, `/contracts/<id>/`
- Error-rate SLO: `5xx < 0.5%` of total requests

## Required Telemetry Streams

1. Structured application logs (already include `request_id`, `user_id`, `org_id`, `path`).
2. Request/response metrics (count, status code class, latency histogram).
3. Scheduler heartbeat metric (`reminder_scheduler.last_success_epoch`).
4. DB query time and error count.

## Alert Policy (P1/P2)

### P1 alerts (page on-call)

- `5xx rate >= 2% for 5m` on production
- `p95 latency > 1500ms for 10m` on core routes
- `auth login failure spike >= 5x baseline for 10m`
- `reminder scheduler no successful run for > 2 intervals`

### P2 alerts (ticket + Slack)

- `5xx rate >= 0.8% for 15m`
- `p95 latency > 800ms for 15m`
- `db error count > 0 for 10m`

## Dashboard Panels (minimum)

1. Request volume by route
2. Error rate by status class
3. p50/p95/p99 latency by route
4. Login successes vs failures
5. Scheduler last success timestamp
6. Top exceptions with count and first_seen/last_seen

## Runbook Links

- Rollback: [`docs/ROLLBACK_RUNBOOK.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/ROLLBACK_RUNBOOK.md)
- Manual smoke: [`docs/MANUAL_SMOKE_CHECKLIST.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MANUAL_SMOKE_CHECKLIST.md)

## Implementation Checklist

- [ ] Ship stdout logs to centralized sink (Datadog/ELK/CloudWatch/Loki)
- [ ] Add metric exporter (OpenTelemetry or platform-native)
- [ ] Create production dashboard with panels above
- [ ] Configure P1/P2 alerts and escalation policy
- [ ] Execute one alert fire-drill and attach evidence to `docs/DRILL_LOG.md`
