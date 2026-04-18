# Observability Dashboard IDs

Last updated: 2026-04-13

## Canonical Dashboard UIDs

- `cms-aegis-core-routes`
- `cms-aegis-auth-scheduler`
- `cms-aegis-db-health`

## Suggested URLs

- `https://grafana.example.com/d/cms-aegis-core-routes`
- `https://grafana.example.com/d/cms-aegis-auth-scheduler`
- `https://grafana.example.com/d/cms-aegis-db-health`

## Panel Mapping

- Request volume by route: `cms-aegis-core-routes`
- Error rate by status class: `cms-aegis-core-routes`
- p50/p95/p99 latency by route: `cms-aegis-core-routes`
- Login successes vs failures: `cms-aegis-auth-scheduler`
- Scheduler last success timestamp: `cms-aegis-auth-scheduler`
- DB latency and DB down events: `cms-aegis-db-health`
