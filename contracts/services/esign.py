from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from contracts.models import AuditLog, SignatureRequest


class ESignReconciliationError(RuntimeError):
    pass


PROVIDER_STATUS_MAP = {
    'created': SignatureRequest.Status.PENDING,
    'pending': SignatureRequest.Status.PENDING,
    'sent': SignatureRequest.Status.SENT,
    'delivered': SignatureRequest.Status.SENT,
    'viewed': SignatureRequest.Status.VIEWED,
    'opened': SignatureRequest.Status.VIEWED,
    'signed': SignatureRequest.Status.SIGNED,
    'completed': SignatureRequest.Status.SIGNED,
    'declined': SignatureRequest.Status.DECLINED,
    'rejected': SignatureRequest.Status.DECLINED,
    'expired': SignatureRequest.Status.EXPIRED,
    'cancelled': SignatureRequest.Status.CANCELLED,
    'canceled': SignatureRequest.Status.CANCELLED,
}


STATUS_PRECEDENCE = {
    SignatureRequest.Status.PENDING: 10,
    SignatureRequest.Status.SENT: 20,
    SignatureRequest.Status.VIEWED: 30,
    SignatureRequest.Status.SIGNED: 100,
    SignatureRequest.Status.DECLINED: 100,
    SignatureRequest.Status.EXPIRED: 100,
    SignatureRequest.Status.CANCELLED: 100,
}


def _parse_event_at(raw_value: str | None) -> datetime | None:
    raw = str(raw_value or '').strip()
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.utc)
    return parsed


def _resolve_internal_status(provider_status: str | None) -> str:
    key = str(provider_status or '').strip().lower()
    status = PROVIDER_STATUS_MAP.get(key)
    if not status:
        raise ESignReconciliationError(f'Unsupported provider status: {provider_status}')
    return status


def _is_duplicate_event(signature_request: SignatureRequest, event_id: str) -> bool:
    token = f'event:{event_id}'
    return AuditLog.objects.filter(
        model_name='ESignEvent',
        object_id=signature_request.id,
        object_repr=token,
    ).exists()


def apply_esign_event(signature_request: SignatureRequest, event: dict, *, dry_run: bool = False) -> dict:
    event_id = str(event.get('event_id') or '').strip()
    if not event_id:
        raise ESignReconciliationError('Event is missing event_id.')
    if _is_duplicate_event(signature_request, event_id):
        return {'result': 'duplicate', 'event_id': event_id, 'signature_request_id': signature_request.id}

    target_status = _resolve_internal_status(event.get('status'))
    event_at = _parse_event_at(event.get('event_at'))
    current_score = STATUS_PRECEDENCE.get(signature_request.status, 0)
    target_score = STATUS_PRECEDENCE.get(target_status, 0)
    should_apply = target_score >= current_score
    if signature_request.status in {
        SignatureRequest.Status.SIGNED,
        SignatureRequest.Status.DECLINED,
        SignatureRequest.Status.EXPIRED,
        SignatureRequest.Status.CANCELLED,
    } and target_score < current_score:
        should_apply = False

    change_payload = {
        'event_id': event_id,
        'provider': str(event.get('provider') or '').strip(),
        'external_id': str(event.get('external_id') or '').strip(),
        'from_status': signature_request.status,
        'to_status': target_status,
        'applied': should_apply and not dry_run,
        'dry_run': dry_run,
        'event_at': event_at.isoformat() if event_at else None,
    }

    if should_apply and not dry_run:
        signature_request.status = target_status
        external_id = str(event.get('external_id') or '').strip()
        if external_id:
            signature_request.external_id = external_id
        if event.get('execution_certificate_url'):
            signature_request.execution_certificate_url = str(event.get('execution_certificate_url') or '').strip()
        if event.get('decline_reason'):
            signature_request.decline_reason = str(event.get('decline_reason') or '').strip()
        if event.get('ip_address'):
            signature_request.ip_address = str(event.get('ip_address') or '').strip()
        if target_status == SignatureRequest.Status.SENT:
            signature_request.sent_at = event_at or signature_request.sent_at or timezone.now()
        elif target_status == SignatureRequest.Status.VIEWED:
            signature_request.viewed_at = event_at or signature_request.viewed_at or timezone.now()
        elif target_status == SignatureRequest.Status.SIGNED:
            signature_request.signed_at = event_at or signature_request.signed_at or timezone.now()
        elif target_status == SignatureRequest.Status.DECLINED:
            signature_request.declined_at = event_at or signature_request.declined_at or timezone.now()
        signature_request.save()

    if not dry_run:
        AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            model_name='ESignEvent',
            object_id=signature_request.id,
            object_repr=f'event:{event_id}',
            changes=change_payload,
        )

    if not should_apply:
        return {'result': 'stale', 'event_id': event_id, 'signature_request_id': signature_request.id}
    return {'result': 'applied' if not dry_run else 'would_apply', 'event_id': event_id, 'signature_request_id': signature_request.id}
