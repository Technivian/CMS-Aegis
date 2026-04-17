from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta, timezone as datetime_timezone
from functools import lru_cache
from typing import Any
import base64
import hashlib
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone


DEFAULT_SALESFORCE_OBJECT = 'Opportunity'
TOKEN_CIPHER_PREFIX = 'enc:v1:'

CANONICAL_CONTRACT_FIELDS: tuple[str, ...] = (
    'contract_title',
    'counterparty_name',
    'contract_type',
    'contract_value',
    'currency',
    'effective_date',
    'end_date',
    'renewal_date',
    'governing_law',
    'jurisdiction',
    'owner_email',
    'owner_name',
    'approver_email',
    'risk_level',
    'status',
    'workflow_template',
    'source_system_id',
    'source_system_url',
    'created_at',
    'updated_at',
)

DEFAULT_FIELD_MAP: tuple[dict[str, Any], ...] = (
    {'canonical_field': 'contract_title', 'salesforce_object': 'Opportunity', 'salesforce_field': 'Name', 'is_required': True},
    {'canonical_field': 'counterparty_name', 'salesforce_object': 'Opportunity', 'salesforce_field': 'Account.Name', 'is_required': True},
    {'canonical_field': 'contract_type', 'salesforce_object': 'Opportunity', 'salesforce_field': 'Type', 'is_required': True},
    {'canonical_field': 'contract_value', 'salesforce_object': 'Opportunity', 'salesforce_field': 'Amount', 'is_required': True},
    {'canonical_field': 'currency', 'salesforce_object': 'Opportunity', 'salesforce_field': 'CurrencyIsoCode', 'is_required': True},
    {'canonical_field': 'effective_date', 'salesforce_object': 'Contract__c', 'salesforce_field': 'Effective_Date__c', 'is_required': False},
    {'canonical_field': 'end_date', 'salesforce_object': 'Contract__c', 'salesforce_field': 'End_Date__c', 'is_required': False},
    {'canonical_field': 'renewal_date', 'salesforce_object': 'Contract__c', 'salesforce_field': 'Renewal_Date__c', 'is_required': False},
    {'canonical_field': 'governing_law', 'salesforce_object': 'Contract__c', 'salesforce_field': 'Governing_Law__c', 'is_required': False},
    {'canonical_field': 'jurisdiction', 'salesforce_object': 'Contract__c', 'salesforce_field': 'Jurisdiction__c', 'is_required': False},
    {'canonical_field': 'owner_email', 'salesforce_object': 'Opportunity', 'salesforce_field': 'Owner.Email', 'is_required': True},
    {'canonical_field': 'owner_name', 'salesforce_object': 'Opportunity', 'salesforce_field': 'Owner.Name', 'is_required': False},
    {'canonical_field': 'approver_email', 'salesforce_object': 'Contract__c', 'salesforce_field': 'Approver_Email__c', 'is_required': False},
    {'canonical_field': 'risk_level', 'salesforce_object': 'Contract__c', 'salesforce_field': 'Risk_Level__c', 'is_required': False},
    {'canonical_field': 'status', 'salesforce_object': 'Contract__c', 'salesforce_field': 'Status__c', 'is_required': True},
    {'canonical_field': 'workflow_template', 'salesforce_object': 'Contract__c', 'salesforce_field': 'Workflow_Template__c', 'is_required': False},
    {'canonical_field': 'source_system_id', 'salesforce_object': 'Opportunity', 'salesforce_field': 'Id', 'is_required': True},
    {'canonical_field': 'source_system_url', 'salesforce_object': 'Opportunity', 'salesforce_field': 'Record_URL__c', 'is_required': False},
    {'canonical_field': 'created_at', 'salesforce_object': 'Opportunity', 'salesforce_field': 'CreatedDate', 'is_required': False},
    {'canonical_field': 'updated_at', 'salesforce_object': 'Opportunity', 'salesforce_field': 'LastModifiedDate', 'is_required': False},
)


@dataclass
class SalesforceTokenPayload:
    access_token: str
    refresh_token: str
    instance_url: str
    external_org_id: str
    scope: str
    token_expires_at: datetime | None


class SalesforceOAuthError(RuntimeError):
    pass


class SalesforceSyncError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _salesforce_token_cipher() -> Fernet:
    secret = f'{settings.SECRET_KEY}:{getattr(settings, "SALESFORCE_TOKEN_ENCRYPTION_SALT", "salesforce-tokens-v1")}'
    digest = hashlib.sha256(secret.encode('utf-8')).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_salesforce_token(raw_token: str) -> str:
    token = str(raw_token or '').strip()
    if not token:
        return ''
    if token.startswith(TOKEN_CIPHER_PREFIX):
        return token
    encrypted = _salesforce_token_cipher().encrypt(token.encode('utf-8')).decode('utf-8')
    return f'{TOKEN_CIPHER_PREFIX}{encrypted}'


def decrypt_salesforce_token(stored_token: str) -> str:
    token = str(stored_token or '').strip()
    if not token:
        return ''
    if not token.startswith(TOKEN_CIPHER_PREFIX):
        return token
    payload = token[len(TOKEN_CIPHER_PREFIX):]
    try:
        return _salesforce_token_cipher().decrypt(payload.encode('utf-8')).decode('utf-8')
    except InvalidToken as exc:
        raise SalesforceOAuthError('Salesforce token decrypt failed.') from exc


def salesforce_oauth_is_configured() -> bool:
    return bool(
        settings.SALESFORCE_CLIENT_ID
        and settings.SALESFORCE_CLIENT_SECRET
        and settings.SALESFORCE_AUTHORIZATION_URL
        and settings.SALESFORCE_TOKEN_URL
        and settings.SALESFORCE_REDIRECT_URI
    )


def build_salesforce_authorize_url(state: str) -> str:
    params = urlencode(
        {
            'response_type': 'code',
            'client_id': settings.SALESFORCE_CLIENT_ID,
            'redirect_uri': settings.SALESFORCE_REDIRECT_URI,
            'scope': settings.SALESFORCE_SCOPES,
            'state': state,
            'prompt': 'consent',
        }
    )
    return f'{settings.SALESFORCE_AUTHORIZATION_URL}?{params}'


def _salesforce_token_request(payload: dict[str, str]) -> dict[str, Any]:
    body = urlencode(payload).encode('utf-8')
    request = Request(
        settings.SALESFORCE_TOKEN_URL,
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except Exception as exc:
        raise SalesforceOAuthError(f'Salesforce token exchange failed: {exc}') from exc


def _salesforce_get_json(url: str, access_token: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        },
        method='GET',
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        raise SalesforceSyncError(f'Salesforce API request failed: {exc}') from exc


def _payload_to_token_data(payload: dict[str, Any]) -> SalesforceTokenPayload:
    access_token = str(payload.get('access_token', '')).strip()
    if not access_token:
        raise SalesforceOAuthError('Salesforce token payload missing access_token.')
    refresh_token = str(payload.get('refresh_token', '')).strip()
    instance_url = str(payload.get('instance_url', '')).strip()
    external_org_id = str(payload.get('id', '')).strip()
    scope = str(payload.get('scope', '')).strip()
    expires_in = payload.get('expires_in')
    expires_at = None
    try:
        if expires_in is not None:
            expires_at = timezone.now() + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        expires_at = None
    return SalesforceTokenPayload(
        access_token=access_token,
        refresh_token=refresh_token,
        instance_url=instance_url,
        external_org_id=external_org_id,
        scope=scope,
        token_expires_at=expires_at,
    )


def exchange_salesforce_code_for_tokens(code: str) -> SalesforceTokenPayload:
    payload = _salesforce_token_request(
        {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': settings.SALESFORCE_CLIENT_ID,
            'client_secret': settings.SALESFORCE_CLIENT_SECRET,
            'redirect_uri': settings.SALESFORCE_REDIRECT_URI,
        }
    )
    return _payload_to_token_data(payload)


def refresh_salesforce_access_token(refresh_token: str) -> SalesforceTokenPayload:
    payload = _salesforce_token_request(
        {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': settings.SALESFORCE_CLIENT_ID,
            'client_secret': settings.SALESFORCE_CLIENT_SECRET,
        }
    )
    if 'refresh_token' not in payload:
        payload['refresh_token'] = refresh_token
    return _payload_to_token_data(payload)


def default_field_map_records() -> list[dict[str, Any]]:
    return [dict(item) for item in DEFAULT_FIELD_MAP]


def _source_object_for_mapping(field_map: list[dict[str, Any]]) -> str:
    for item in field_map:
        if str(item.get('canonical_field', '')).strip() == 'source_system_id':
            value = str(item.get('salesforce_object', '')).strip()
            if value:
                return value
    return DEFAULT_SALESFORCE_OBJECT


def build_salesforce_soql(field_map: list[dict[str, Any]], source_object: str, limit: int = 200) -> str:
    projected_fields: list[str] = []
    for item in field_map:
        object_name = str(item.get('salesforce_object', '')).strip() or DEFAULT_SALESFORCE_OBJECT
        field_name = str(item.get('salesforce_field', '')).strip()
        if object_name != source_object or not field_name:
            continue
        if field_name not in projected_fields:
            projected_fields.append(field_name)
    if 'Id' not in projected_fields:
        projected_fields.append('Id')
    selected = ', '.join(projected_fields)
    return f'SELECT {selected} FROM {source_object} ORDER BY LastModifiedDate DESC LIMIT {max(1, int(limit))}'


def fetch_salesforce_records(instance_url: str, access_token: str, soql: str) -> list[dict[str, Any]]:
    api_version = str(getattr(settings, 'SALESFORCE_API_VERSION', '61.0')).strip() or '61.0'
    base = instance_url.rstrip('/')
    endpoint = f'{base}/services/data/v{api_version}/query?{urlencode({"q": soql})}'
    records: list[dict[str, Any]] = []

    while endpoint:
        payload = _salesforce_get_json(endpoint, access_token)
        chunk = payload.get('records') or []
        if isinstance(chunk, list):
            for row in chunk:
                if isinstance(row, dict):
                    row.pop('attributes', None)
                    records.append(row)
        next_url = payload.get('nextRecordsUrl')
        if next_url:
            endpoint = f'{base}{next_url}'
        else:
            endpoint = ''
    return records


def get_effective_field_map_records(organization) -> list[dict[str, Any]]:
    from contracts.models import OrganizationContractFieldMap

    persisted = list(
        OrganizationContractFieldMap.objects.filter(organization=organization, is_active=True)
        .values('canonical_field', 'salesforce_object', 'salesforce_field', 'is_required', 'transform_rule')
        .order_by('canonical_field')
    )
    return persisted or default_field_map_records()


def _extract_record_value(record: dict[str, Any], dotted_path: str):
    current = record
    for part in str(dotted_path or '').split('.'):
        part = part.strip()
        if not part:
            return None
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _to_contract_type(raw: Any):
    from contracts.models import Contract

    value = str(raw or '').strip().upper()
    allowed = {choice for choice, _ in Contract.ContractType.choices}
    if value in allowed:
        return value
    mapping = {
        'NON-DISCLOSURE AGREEMENT': Contract.ContractType.NDA,
        'MASTER SERVICE AGREEMENT': Contract.ContractType.MSA,
        'STATEMENT OF WORK': Contract.ContractType.SOW,
    }
    return mapping.get(value, Contract.ContractType.OTHER)


def _to_contract_status(raw: Any):
    from contracts.models import Contract

    value = str(raw or '').strip().upper()
    allowed = {choice for choice, _ in Contract.Status.choices}
    if value in allowed:
        return value
    aliases = {
        'OPEN': Contract.Status.DRAFT,
        'NEGOTIATION': Contract.Status.IN_REVIEW,
        'SIGNED': Contract.Status.ACTIVE,
        'CLOSED': Contract.Status.COMPLETED,
    }
    return aliases.get(value, Contract.Status.DRAFT)


def _to_risk_level(raw: Any):
    from contracts.models import Contract

    value = str(raw or '').strip().upper()
    allowed = {choice for choice, _ in Contract.RiskLevel.choices}
    return value if value in allowed else Contract.RiskLevel.LOW


def _to_currency(raw: Any):
    from contracts.models import Contract

    value = str(raw or '').strip().upper()
    allowed = {choice for choice, _ in Contract.Currency.choices}
    return value if value in allowed else Contract.Currency.OTHER


def _to_decimal(raw: Any):
    if raw in {None, ''}:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _to_date(raw: Any):
    if raw in {None, ''}:
        return None
    parsed = parse_date(str(raw))
    if parsed is not None:
        return parsed
    parsed_dt = parse_datetime(str(raw))
    if parsed_dt is not None:
        return parsed_dt.date()
    return None


def _to_datetime(raw: Any):
    if raw in {None, ''}:
        return None
    parsed = parse_datetime(str(raw))
    if parsed is not None:
        return parsed
    parsed_date = parse_date(str(raw))
    if parsed_date is not None:
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=datetime_timezone.utc)
    return None


def map_salesforce_record_to_contract_data(record: dict[str, Any], field_map: list[dict[str, Any]]) -> dict[str, Any]:
    mapped = {}
    for item in field_map:
        canonical = str(item.get('canonical_field', '')).strip()
        sf_field = str(item.get('salesforce_field', '')).strip()
        if not canonical or not sf_field:
            continue
        mapped[canonical] = _extract_record_value(record, sf_field)
    return mapped


def upsert_contract_from_salesforce(organization, mapped: dict[str, Any]):
    from contracts.models import Contract

    source_system_id = str(mapped.get('source_system_id', '') or '').strip()
    title = str(mapped.get('contract_title', '') or '').strip()
    counterparty = str(mapped.get('counterparty_name', '') or '').strip()
    if not source_system_id or not title:
        return None, 'skipped_missing_required'

    queryset = Contract.objects.filter(
        organization=organization,
        source_system='salesforce',
        source_system_id=source_system_id,
    )
    contract = queryset.first()
    created = contract is None
    if created:
        contract = Contract(organization=organization, source_system='salesforce', source_system_id=source_system_id)

    contract.title = title
    contract.counterparty = counterparty
    contract.contract_type = _to_contract_type(mapped.get('contract_type'))
    contract.status = _to_contract_status(mapped.get('status'))
    contract.value = _to_decimal(mapped.get('contract_value'))
    if mapped.get('currency') not in {None, ''}:
        contract.currency = _to_currency(mapped.get('currency'))
    contract.governing_law = str(mapped.get('governing_law', '') or '').strip()
    contract.jurisdiction = str(mapped.get('jurisdiction', '') or '').strip()
    contract.start_date = _to_date(mapped.get('effective_date'))
    contract.end_date = _to_date(mapped.get('end_date'))
    contract.renewal_date = _to_date(mapped.get('renewal_date'))
    if mapped.get('risk_level') not in {None, ''}:
        contract.risk_level = _to_risk_level(mapped.get('risk_level'))
    contract.source_system_url = str(mapped.get('source_system_url', '') or '').strip()
    contract.source_last_modified_at = _to_datetime(mapped.get('updated_at'))
    contract.save()
    return contract, 'created' if created else 'updated'


def ingest_salesforce_records(organization, records: list[dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    field_map = get_effective_field_map_records(organization)
    summary = {
        'total_records': len(records),
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': [],
    }

    for index, record in enumerate(records):
        try:
            mapped = map_salesforce_record_to_contract_data(record, field_map)
            if dry_run:
                source_system_id = str(mapped.get('source_system_id', '') or '').strip()
                title = str(mapped.get('contract_title', '') or '').strip()
                if source_system_id and title:
                    exists = (
                        organization.contracts.filter(
                            source_system='salesforce',
                            source_system_id=source_system_id,
                        ).exists()
                    )
                    if exists:
                        summary['updated'] += 1
                    else:
                        summary['created'] += 1
                else:
                    summary['skipped'] += 1
                continue
            _, action = upsert_contract_from_salesforce(organization, mapped)
            if action == 'created':
                summary['created'] += 1
            elif action == 'updated':
                summary['updated'] += 1
            else:
                summary['skipped'] += 1
        except Exception as exc:
            summary['errors'].append({'index': index, 'error': str(exc)})
    return summary


def sync_salesforce_connection(connection, dry_run: bool = False, limit: int = 200) -> dict[str, Any]:
    from contracts.models import SalesforceOrganizationConnection

    if not connection or not isinstance(connection, SalesforceOrganizationConnection):
        raise SalesforceSyncError('Salesforce connection is required.')
    if not connection.is_active:
        raise SalesforceSyncError('Salesforce connection is inactive.')

    access_token = decrypt_salesforce_token(connection.access_token)
    refresh_token = decrypt_salesforce_token(connection.refresh_token)
    if not access_token:
        raise SalesforceSyncError('Missing Salesforce access token.')
    if not connection.instance_url:
        raise SalesforceSyncError('Missing Salesforce instance URL.')

    if connection.token_expired:
        if not refresh_token:
            raise SalesforceSyncError('Salesforce token expired and no refresh token is available.')
        refreshed = refresh_salesforce_access_token(refresh_token)
        access_token = refreshed.access_token
        connection.access_token = encrypt_salesforce_token(refreshed.access_token)
        if refreshed.refresh_token:
            connection.refresh_token = encrypt_salesforce_token(refreshed.refresh_token)
        connection.instance_url = refreshed.instance_url or connection.instance_url
        connection.scope = refreshed.scope or connection.scope
        connection.token_expires_at = refreshed.token_expires_at
        connection.save(update_fields=['access_token', 'refresh_token', 'instance_url', 'scope', 'token_expires_at', 'updated_at'])

    field_map = get_effective_field_map_records(connection.organization)
    source_object = _source_object_for_mapping(field_map)
    soql = build_salesforce_soql(field_map, source_object=source_object, limit=limit)
    records = fetch_salesforce_records(connection.instance_url, access_token, soql)
    summary = ingest_salesforce_records(connection.organization, records, dry_run=dry_run)
    summary['source_object'] = source_object
    summary['fetched_records'] = len(records)
    summary['soql'] = soql
    if not dry_run:
        connection.last_sync_at = timezone.now()
        connection.save(update_fields=['last_sync_at', 'updated_at'])
    return summary
