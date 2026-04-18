import json
import time

from django.core.cache import cache
from django.core.management.base import BaseCommand

from contracts.observability import (
    REQUEST_COUNT_KEY,
    REQUEST_LATENCY_SUM_KEY,
    SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY,
    SCHEDULER_LAST_SUCCESS_EPOCH_KEY,
    evaluate_alert_policy,
)


class Command(BaseCommand):
    help = 'Run an observability fire drill by simulating alert conditions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--scenario',
            choices=['scheduler_stale', 'error_rate_spike'],
            default='scheduler_stale',
            help='Which drill scenario to simulate.',
        )

    def handle(self, *args, **options):
        scenario = options['scenario']

        if scenario == 'scheduler_stale':
            cache.set(SCHEDULER_EXPECTED_INTERVAL_SECONDS_KEY, 60, timeout=None)
            cache.set(SCHEDULER_LAST_SUCCESS_EPOCH_KEY, int(time.time()) - 720, timeout=None)
        elif scenario == 'error_rate_spike':
            cache.set(REQUEST_COUNT_KEY, 200, timeout=None)
            cache.set(REQUEST_LATENCY_SUM_KEY, 200 * 150, timeout=None)
            cache.set('http.requests.status.5xx', 8, timeout=None)
            cache.set('http.requests.status.2xx', 180, timeout=None)
            cache.set('http.requests.status.4xx', 12, timeout=None)
            cache.set('http.requests.status.3xx', 0, timeout=None)

        evaluation = evaluate_alert_policy()
        payload = {
            'scenario': scenario,
            'timestamp_epoch': int(time.time()),
            'evaluation': evaluation,
        }
        self.stdout.write(json.dumps(payload, indent=2))

        if evaluation['alert_status'] == 'OK':
            raise SystemExit('Fire drill failed: no alert condition triggered.')
