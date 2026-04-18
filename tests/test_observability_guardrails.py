import time

from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from contracts.observability import (
    SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY,
    SCHEDULER_LAST_CREATED_COUNT_KEY,
    SCHEDULER_LAST_SUCCESS_EPOCH_KEY,
    evaluate_alert_policy,
    record_request_metric,
    request_metrics_snapshot,
)


class ObservabilityGuardrailsTests(TestCase):
    def setUp(self):
        self.client = Client()
        cache.clear()

    def test_health_json_reports_unknown_scheduler_without_heartbeat(self):
        response = self.client.get(reverse('health_check') + '?format=json')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['scheduler']['status'], 'unknown')
        self.assertIn(payload['database']['status'], {'healthy', 'slow', 'down'})
        self.assertIn('request_metrics', payload)

    def test_send_contract_reminders_records_scheduler_heartbeat(self):
        call_command('send_contract_reminders', scheduler_interval_minutes=15)

        self.assertIsNotNone(cache.get(SCHEDULER_LAST_SUCCESS_EPOCH_KEY))
        self.assertEqual(cache.get(SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY), 900)
        self.assertEqual(cache.get(SCHEDULER_LAST_CREATED_COUNT_KEY), 0)

    def test_health_json_reports_stale_scheduler(self):
        cache.set(SCHEDULER_LAST_SUCCESS_EPOCH_KEY, int(time.time()) - 200, timeout=None)
        cache.set(SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY, 60, timeout=None)

        response = self.client.get(reverse('health_check') + '?format=json')
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload['status'], 'degraded')
        self.assertEqual(payload['scheduler']['status'], 'stale')

    def test_request_metric_snapshot_tracks_status_and_routes(self):
        record_request_metric('/contracts/', 200, 120.6)
        record_request_metric('/login/', 429, 42.1)
        snapshot = request_metrics_snapshot()

        self.assertEqual(snapshot['total_requests'], 2)
        self.assertEqual(snapshot['status_counts']['2xx'], 1)
        self.assertEqual(snapshot['status_counts']['4xx'], 1)
        self.assertEqual(snapshot['route_counts']['contracts'], 1)
        self.assertEqual(snapshot['route_counts']['login'], 1)

    def test_alert_policy_reports_scheduler_stale_as_p1(self):
        cache.set(SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY, 60, timeout=None)
        cache.set(SCHEDULER_LAST_SUCCESS_EPOCH_KEY, int(time.time()) - 240, timeout=None)
        evaluation = evaluate_alert_policy()
        self.assertEqual(evaluation['alert_status'], 'P1')
        self.assertIn('OBS-P1-SCHEDULER-STALLED', evaluation['p1_alerts'])
