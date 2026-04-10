# Grafana Dashboard Spec: CMS Aegis SLO

Panels:
1. Requests per second by route (`rate(http_requests_total[5m])`)
2. 5xx ratio (`sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))`)
3. p50/p95/p99 latency for `/dashboard/`, `/contracts/`, `/contracts/:id`
4. Login success vs failure
5. Reminder scheduler heartbeat age (`time() - reminder_scheduler_last_success_epoch`)
6. Top exceptions by count over 1h

Template variables:
- `environment` (prod, staging)
- `route`

SLO widgets:
- Availability burn rate (1h and 6h windows)
- Error budget remaining this month
