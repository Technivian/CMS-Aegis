import time

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone


SCHEDULER_LAST_SUCCESS_EPOCH_KEY = 'reminder_scheduler.last_success_epoch'
SCHEDULER_LAST_SUCCESS_ISO_KEY = 'reminder_scheduler.last_success_iso'
SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY = 'reminder_scheduler.expected_interval_seconds'
SCHEDULER_LAST_CREATED_COUNT_KEY = 'reminder_scheduler.last_created_count'
REQUEST_COUNT_KEY = 'http.requests.count'
REQUEST_LATENCY_SUM_KEY = 'http.requests.latency_ms.sum'
REQUEST_LAST_SEEN_EPOCH_KEY = 'http.requests.last_seen_epoch'


def _cache_incr(key, amount=1):
    if cache.add(key, 0, timeout=None):
        pass
    cache.incr(key, amount)


def _status_bucket(status_code):
    return f'{status_code // 100}xx'


def _route_bucket(path):
    if path.startswith('/dashboard'):
        return 'dashboard'
    if path.startswith('/contracts'):
        return 'contracts'
    if path.startswith('/_health'):
        return 'health'
    if path.startswith('/login'):
        return 'login'
    return 'other'


def record_request_metric(path, status_code, latency_ms):
    if not getattr(settings, 'REQUEST_METRICS_ENABLED', True):
        return
    _cache_incr(REQUEST_COUNT_KEY, 1)
    _cache_incr(REQUEST_LATENCY_SUM_KEY, max(0, int(latency_ms)))
    _cache_incr(f'http.requests.status.{_status_bucket(status_code)}', 1)
    _cache_incr(f'http.requests.route.{_route_bucket(path)}', 1)
    cache.set(REQUEST_LAST_SEEN_EPOCH_KEY, int(time.time()), timeout=None)


def request_metrics_snapshot():
    total = int(cache.get(REQUEST_COUNT_KEY, 0))
    latency_sum = int(cache.get(REQUEST_LATENCY_SUM_KEY, 0))
    avg_latency_ms = round(latency_sum / total, 2) if total else 0.0
    return {
        'total_requests': total,
        'avg_latency_ms': avg_latency_ms,
        'status_counts': {
            '2xx': int(cache.get('http.requests.status.2xx', 0)),
            '3xx': int(cache.get('http.requests.status.3xx', 0)),
            '4xx': int(cache.get('http.requests.status.4xx', 0)),
            '5xx': int(cache.get('http.requests.status.5xx', 0)),
        },
        'route_counts': {
            'dashboard': int(cache.get('http.requests.route.dashboard', 0)),
            'contracts': int(cache.get('http.requests.route.contracts', 0)),
            'health': int(cache.get('http.requests.route.health', 0)),
            'login': int(cache.get('http.requests.route.login', 0)),
            'other': int(cache.get('http.requests.route.other', 0)),
        },
        'last_seen_epoch': cache.get(REQUEST_LAST_SEEN_EPOCH_KEY),
    }


def db_health_snapshot():
    warn_ms = int(getattr(settings, 'HEALTH_DB_LATENCY_WARN_MS', 250))
    fail_ms = int(getattr(settings, 'HEALTH_DB_LATENCY_FAIL_MS', 1500))
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            'status': 'down',
            'latency_ms': latency_ms,
            'error': str(exc),
            'warn_ms': warn_ms,
            'fail_ms': fail_ms,
        }
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    if latency_ms > fail_ms:
        status = 'down'
    elif latency_ms > warn_ms:
        status = 'slow'
    else:
        status = 'healthy'
    return {
        'status': status,
        'latency_ms': latency_ms,
        'warn_ms': warn_ms,
        'fail_ms': fail_ms,
    }


def evaluate_alert_policy():
    request_metrics = request_metrics_snapshot()
    scheduler = scheduler_health_snapshot()
    database = db_health_snapshot()

    total_requests = max(1, int(request_metrics.get('total_requests', 0)))
    total_5xx = int(request_metrics.get('status_counts', {}).get('5xx', 0))
    five_xx_rate_pct = (total_5xx / total_requests) * 100

    p1_alerts = []
    p2_alerts = []

    fail_threshold = float(getattr(settings, 'SLO_5XX_RATE_FAIL_PCT', 2.0))
    warn_threshold = float(getattr(settings, 'SLO_5XX_RATE_WARN_PCT', 0.8))

    if five_xx_rate_pct >= fail_threshold:
        p1_alerts.append('OBS-P1-5XX-RATE')
    elif five_xx_rate_pct >= warn_threshold:
        p2_alerts.append('OBS-P2-5XX-RATE')

    if scheduler.get('status') == 'stale':
        p1_alerts.append('OBS-P1-SCHEDULER-STALLED')

    db_status = database.get('status')
    if db_status == 'down':
        p1_alerts.append('OBS-P1-DB-DOWN')
    elif db_status == 'slow':
        p2_alerts.append('OBS-P2-DB-SLOW')

    return {
        'alert_status': 'P1' if p1_alerts else ('P2' if p2_alerts else 'OK'),
        'p1_alerts': p1_alerts,
        'p2_alerts': p2_alerts,
        'five_xx_rate_pct': round(five_xx_rate_pct, 3),
        'inputs': {
            'request_metrics': request_metrics,
            'scheduler': scheduler,
            'database': database,
            'slo_thresholds': {
                'five_xx_warn_pct': warn_threshold,
                'five_xx_fail_pct': fail_threshold,
                'api_p95_ms': int(getattr(settings, 'SLO_API_P95_MS', 500)),
            },
        },
    }


def record_scheduler_heartbeat(created_count=0, interval_minutes=None):
    interval = interval_minutes or getattr(settings, 'REMINDER_SCHEDULER_EXPECTED_INTERVAL_MINUTES', 60)
    interval_seconds = max(60, int(interval) * 60)
    now_epoch = int(time.time())
    now_iso = timezone.now().isoformat()

    cache.set(SCHEDULER_LAST_SUCCESS_EPOCH_KEY, now_epoch, timeout=None)
    cache.set(SCHEDULER_LAST_SUCCESS_ISO_KEY, now_iso, timeout=None)
    cache.set(SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY, interval_seconds, timeout=None)
    cache.set(SCHEDULER_LAST_CREATED_COUNT_KEY, int(created_count), timeout=None)


def scheduler_health_snapshot():
    now_epoch = int(time.time())
    last_success_epoch = cache.get(SCHEDULER_LAST_SUCCESS_EPOCH_KEY)
    last_success_iso = cache.get(SCHEDULER_LAST_SUCCESS_ISO_KEY)
    expected_interval_seconds = int(
        cache.get(
            SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY,
            max(60, int(getattr(settings, 'REMINDER_SCHEDULER_EXPECTED_INTERVAL_MINUTES', 60)) * 60),
        )
    )
    stale_multiplier = max(1, int(getattr(settings, 'REMINDER_SCHEDULER_STALE_MULTIPLIER', 2)))
    stale_after_seconds = expected_interval_seconds * stale_multiplier

    if not last_success_epoch:
        return {
            'status': 'unknown',
            'last_success_epoch': None,
            'last_success_iso': None,
            'seconds_since_success': None,
            'expected_interval_seconds': expected_interval_seconds,
            'stale_after_seconds': stale_after_seconds,
            'last_created_count': None,
        }

    seconds_since_success = max(0, now_epoch - int(last_success_epoch))
    status = 'healthy' if seconds_since_success <= stale_after_seconds else 'stale'

    return {
        'status': status,
        'last_success_epoch': int(last_success_epoch),
        'last_success_iso': last_success_iso,
        'seconds_since_success': seconds_since_success,
        'expected_interval_seconds': expected_interval_seconds,
        'stale_after_seconds': stale_after_seconds,
        'last_created_count': cache.get(SCHEDULER_LAST_CREATED_COUNT_KEY),
    }
