from __future__ import annotations

from decimal import Decimal
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.dateparse import parse_date, parse_datetime

from contracts.models import Contract


DEFAULT_NETSUITE_FIELD_MAP = {
    'source_system_id': 'id',
    'contract_title': 'title',
    'counterparty_name': 'vendor_name',
    'contract_type': 'contract_type',
    'contract_value': 'value',
    'currency': 'currency',
    'status': 'status',
    'effective_date': 'effective_date',
    'end_date': 'end_date',
    'renewal_date': 'renewal_date',
    'risk_level': 'risk_level',
    'source_system_url': 'record_url',
    'updated_at': 'last_modified_at',
}


class NetSuiteSyncError(RuntimeError):
    pass


def _get(record: dict, key: str):
    return record.get(key)


def _to_decimal(raw):
    if raw in {None, ''}:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _to_date(raw):
    if raw in {None, ''}:
        return None
    parsed = parse_date(str(raw))
    if parsed is not None:
        return parsed
    parsed_dt = parse_datetime(str(raw))
    return parsed_dt.date() if parsed_dt else None


def _normalize_choice(raw, choices, default):
    value = str(raw or '').strip().upper()
    allowed = {code for code, _ in choices}
    return value if value in allowed else default


def netsuite_is_configured() -> bool:
    return bool(
        settings.NETSUITE_CLIENT_ID
        and settings.NETSUITE_CLIENT_SECRET
        and settings.NETSUITE_TOKEN_URL
        and settings.NETSUITE_API_URL
    )


def fetch_netsuite_access_token() -> str:
    if not netsuite_is_configured():
        raise NetSuiteSyncError('NetSuite integration is not configured.')

    payload = urlencode(
        {
            'grant_type': 'client_credentials',
            'client_id': settings.NETSUITE_CLIENT_ID,
            'client_secret': settings.NETSUITE_CLIENT_SECRET,
        }
    ).encode('utf-8')
    request = Request(
        settings.NETSUITE_TOKEN_URL,
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
        method='POST',
    )
    timeout = max(1, int(getattr(settings, 'NETSUITE_TIMEOUT_SECONDS', 30)))
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        raise NetSuiteSyncError(f'NetSuite token fetch failed: {exc}') from exc

    token = str(data.get('access_token', '')).strip()
    if not token:
        raise NetSuiteSyncError('NetSuite token response missing access_token.')
    return token


def fetch_netsuite_records(limit: int = 200) -> list[dict]:
    access_token = fetch_netsuite_access_token()
    url = f'{settings.NETSUITE_API_URL.rstrip("/")}?{urlencode({"limit": max(1, int(limit))})}'
    request = Request(
        url,
        headers={'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'},
        method='GET',
    )
    timeout = max(1, int(getattr(settings, 'NETSUITE_TIMEOUT_SECONDS', 30)))
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        raise NetSuiteSyncError(f'NetSuite record fetch failed: {exc}') from exc

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    records = payload.get('records')
    if isinstance(records, list):
        return [item for item in records if isinstance(item, dict)]
    raise NetSuiteSyncError('NetSuite records response must be a list or contain a "records" list.')


def map_netsuite_record(record: dict, field_map: dict | None = None) -> dict:
    field_map = field_map or DEFAULT_NETSUITE_FIELD_MAP
    return {
        canonical: _get(record, source)
        for canonical, source in field_map.items()
    }


def upsert_contract_from_netsuite(organization, mapped: dict):
    source_id = str(mapped.get('source_system_id', '') or '').strip()
    title = str(mapped.get('contract_title', '') or '').strip()
    if not source_id or not title:
        return None, 'skipped_missing_required'

    contract = Contract.objects.filter(
        organization=organization,
        source_system='netsuite',
        source_system_id=source_id,
    ).first()
    created = contract is None
    if created:
        contract = Contract(
            organization=organization,
            source_system='netsuite',
            source_system_id=source_id,
        )

    contract.title = title
    contract.counterparty = str(mapped.get('counterparty_name', '') or '').strip()
    contract.contract_type = _normalize_choice(mapped.get('contract_type'), Contract.ContractType.choices, Contract.ContractType.OTHER)
    contract.status = _normalize_choice(mapped.get('status'), Contract.Status.choices, Contract.Status.DRAFT)
    contract.risk_level = _normalize_choice(mapped.get('risk_level'), Contract.RiskLevel.choices, Contract.RiskLevel.LOW)
    contract.value = _to_decimal(mapped.get('contract_value'))
    contract.currency = _normalize_choice(mapped.get('currency'), Contract.Currency.choices, Contract.Currency.OTHER)
    contract.start_date = _to_date(mapped.get('effective_date'))
    contract.end_date = _to_date(mapped.get('end_date'))
    contract.renewal_date = _to_date(mapped.get('renewal_date'))
    contract.source_system_url = str(mapped.get('source_system_url', '') or '').strip()
    contract.source_last_modified_at = parse_datetime(str(mapped.get('updated_at', '') or '')) if mapped.get('updated_at') else None
    contract.save()
    return contract, 'created' if created else 'updated'


def ingest_netsuite_records(organization, records: list[dict], field_map: dict | None = None) -> dict:
    summary = {'total_records': len(records), 'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}
    for index, record in enumerate(records):
        try:
            mapped = map_netsuite_record(record, field_map=field_map)
            _, action = upsert_contract_from_netsuite(organization, mapped)
            if action == 'created':
                summary['created'] += 1
            elif action == 'updated':
                summary['updated'] += 1
            else:
                summary['skipped'] += 1
        except Exception as exc:
            summary['errors'].append({'index': index, 'error': str(exc)})
    return summary
