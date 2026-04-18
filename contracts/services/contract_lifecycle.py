from datetime import date
from decimal import Decimal


CONTRACT_LIFECYCLE_TRANSITIONS = {
    'DRAFTING': {'INTERNAL_REVIEW', 'ARCHIVED'},
    'INTERNAL_REVIEW': {'NEGOTIATION', 'ARCHIVED'},
    'NEGOTIATION': {'APPROVAL', 'ARCHIVED'},
    'APPROVAL': {'SIGNATURE', 'ARCHIVED'},
    'SIGNATURE': {'EXECUTED', 'ARCHIVED'},
    'EXECUTED': {'OBLIGATION_TRACKING', 'ARCHIVED'},
    'OBLIGATION_TRACKING': {'RENEWAL', 'ARCHIVED'},
    'RENEWAL': {'DRAFTING', 'ARCHIVED'},
    'ARCHIVED': set(),
}

TRACKED_CONTRACT_FIELDS = (
    'status',
    'lifecycle_stage',
    'contract_type',
    'counterparty',
    'value',
    'currency',
    'governing_law',
    'jurisdiction',
    'risk_level',
    'data_transfer_flag',
    'dpa_attached',
    'scc_attached',
    'start_date',
    'end_date',
    'renewal_date',
    'auto_renew',
    'notice_period_days',
    'termination_notice_date',
    'client_id',
    'matter_id',
)


def get_allowed_lifecycle_stages(current_stage):
    return CONTRACT_LIFECYCLE_TRANSITIONS.get(current_stage, set())


def can_transition_lifecycle_stage(contract, new_stage):
    if contract is None or not new_stage:
        return False

    current_stage = getattr(contract, 'lifecycle_stage', None)
    if new_stage == current_stage:
        return True
    return new_stage in get_allowed_lifecycle_stages(current_stage)


def _normalize_audit_value(value):
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'pk'):
        return value.pk
    return value


def build_contract_audit_changes(before_contract, after_contract, tracked_fields=TRACKED_CONTRACT_FIELDS):
    if before_contract is None or after_contract is None:
        return {}

    changes = {}
    for field_name in tracked_fields:
        before_value = _normalize_audit_value(getattr(before_contract, field_name, None))
        after_value = _normalize_audit_value(getattr(after_contract, field_name, None))
        if before_value != after_value:
            changes[field_name] = {
                'before': before_value,
                'after': after_value,
            }
    return changes
