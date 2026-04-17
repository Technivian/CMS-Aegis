from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from django.conf import settings
from django.utils import timezone


DEFAULT_SALESFORCE_OBJECT = 'Opportunity'

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
