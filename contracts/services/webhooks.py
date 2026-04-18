from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from urllib.request import Request, urlopen

from django.db.models import Q
from django.utils import timezone

from contracts.models import WebhookDelivery, WebhookEndpoint


def queue_webhook_event(*, organization, event_type: str, payload: dict):
    endpoints = WebhookEndpoint.objects.filter(
        organization=organization,
        status=WebhookEndpoint.Status.ACTIVE,
    )
    queued = 0
    for endpoint in endpoints:
        configured_events = endpoint.event_types or []
        if configured_events and event_type not in configured_events and '*' not in configured_events:
            continue
        WebhookDelivery.objects.create(
            organization=organization,
            endpoint=endpoint,
            event_type=event_type,
            payload=payload or {},
            max_attempts=max(1, int(endpoint.max_attempts or 5)),
            next_attempt_at=timezone.now(),
        )
        queued += 1
    return queued


def _webhook_headers(delivery: WebhookDelivery, body: bytes):
    headers = {'Content-Type': 'application/json'}
    secret = (delivery.endpoint.secret or '').encode('utf-8')
    if secret:
        signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
        headers['X-CMS-AEGIS-SIGNATURE'] = f'sha256={signature}'
    headers['X-CMS-AEGIS-EVENT'] = delivery.event_type
    headers['X-CMS-AEGIS-DELIVERY-ID'] = str(delivery.id)
    return headers


def dispatch_webhook_delivery(delivery: WebhookDelivery):
    if delivery.status in {WebhookDelivery.Status.SENT, WebhookDelivery.Status.DEAD_LETTER}:
        return delivery

    delivery.attempt_count = int(delivery.attempt_count or 0) + 1
    body = json.dumps(delivery.payload or {}).encode('utf-8')
    request = Request(
        delivery.endpoint.url,
        data=body,
        headers=_webhook_headers(delivery, body),
        method='POST',
    )
    try:
        with urlopen(request, timeout=10) as response:
            response_body = response.read().decode('utf-8', errors='replace')[:4000]
            status_code = int(getattr(response, 'status', 200))
            delivery.response_status = status_code
            delivery.response_body = response_body
            if 200 <= status_code < 300:
                delivery.status = WebhookDelivery.Status.SENT
                delivery.sent_at = timezone.now()
                delivery.error_message = ''
                delivery.next_attempt_at = None
            else:
                raise RuntimeError(f'Unexpected response status {status_code}')
    except Exception as exc:
        max_attempts = max(1, int(delivery.max_attempts or 5))
        delivery.error_message = str(exc)
        if delivery.attempt_count >= max_attempts:
            delivery.status = WebhookDelivery.Status.DEAD_LETTER
            delivery.dead_lettered_at = timezone.now()
            delivery.next_attempt_at = None
        else:
            delay_minutes = min(60, 2 ** max(0, delivery.attempt_count - 1))
            delivery.status = WebhookDelivery.Status.FAILED
            delivery.next_attempt_at = timezone.now() + timedelta(minutes=delay_minutes)
    delivery.save()
    return delivery


def dispatch_pending_webhook_deliveries(limit: int = 100):
    now = timezone.now()
    queued = (
        WebhookDelivery.objects
        .select_related('endpoint', 'organization')
        .filter(status__in=[WebhookDelivery.Status.PENDING, WebhookDelivery.Status.FAILED])
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .order_by('next_attempt_at', 'created_at')[:max(1, int(limit))]
    )
    processed = 0
    for delivery in queued:
        dispatch_webhook_delivery(delivery)
        processed += 1
    return processed
