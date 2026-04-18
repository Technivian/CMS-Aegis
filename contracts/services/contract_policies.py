from django.conf import settings

from contracts.models import Contract


DEFAULT_CONTRACT_REQUIRED_FIELD_POLICIES = {
    Contract.ContractType.NDA: ('counterparty', 'governing_law', 'jurisdiction'),
    Contract.ContractType.MSA: ('counterparty', 'governing_law', 'jurisdiction'),
    Contract.ContractType.SOW: ('counterparty', 'governing_law', 'jurisdiction'),
    Contract.ContractType.EMPLOYMENT: ('counterparty', 'governing_law', 'jurisdiction', 'start_date', 'end_date'),
    Contract.ContractType.LEASE: ('counterparty', 'governing_law', 'jurisdiction', 'start_date', 'end_date'),
    Contract.ContractType.LICENSE: ('counterparty', 'governing_law', 'jurisdiction'),
    Contract.ContractType.VENDOR: ('counterparty', 'governing_law', 'jurisdiction'),
    Contract.ContractType.PARTNERSHIP: ('counterparty', 'governing_law', 'jurisdiction'),
    Contract.ContractType.SETTLEMENT: ('counterparty', 'governing_law', 'jurisdiction'),
    Contract.ContractType.AMENDMENT: ('counterparty', 'governing_law', 'jurisdiction', 'content'),
}


def get_contract_required_field_policies():
    configured_policies = getattr(settings, 'CONTRACT_REQUIRED_FIELD_POLICIES', None) or {}
    merged_policies = dict(DEFAULT_CONTRACT_REQUIRED_FIELD_POLICIES)

    for contract_type, required_fields in configured_policies.items():
        merged_policies[contract_type] = tuple(required_fields)

    return merged_policies


def get_required_fields_for_contract_type(contract_type):
    policies = get_contract_required_field_policies()
    return policies.get(contract_type, ())
