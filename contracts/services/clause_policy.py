from __future__ import annotations

from contracts.models import ClauseTemplate, Contract


def normalize_clause_type_list(raw_value: str) -> set[str]:
    tokens = set()
    for token in (raw_value or '').replace(';', ',').split(','):
        cleaned = token.strip().upper()
        if cleaned:
            tokens.add(cleaned)
    return tokens


def clause_applies_to_contract(clause: ClauseTemplate, contract: Contract | None) -> bool:
    if contract is None:
        return True

    if clause.applicable_contract_types:
        allowed_types = normalize_clause_type_list(clause.applicable_contract_types)
        if allowed_types and contract.contract_type not in allowed_types:
            return False

    scope = (clause.jurisdiction_scope or ClauseTemplate.JurisdictionScope.GLOBAL).upper()
    jurisdiction_text = ' '.join(
        part for part in [
            (contract.jurisdiction or '').strip().upper(),
            (contract.governing_law or '').strip().upper(),
        ] if part
    )
    if scope == ClauseTemplate.JurisdictionScope.GLOBAL:
        return True
    if scope == ClauseTemplate.JurisdictionScope.CUSTOM:
        return bool(jurisdiction_text)
    return scope in jurisdiction_text


def resolve_clause_fallback(clause: ClauseTemplate) -> str:
    fallback_candidates = [
        clause.fallback_content,
        clause.playbook_notes,
        clause.content,
    ]
    for candidate in fallback_candidates:
        if candidate and candidate.strip():
            return candidate.strip()
    return ''


def validate_clause_policy(clause: ClauseTemplate) -> list[str]:
    issues: list[str] = []
    if clause.is_mandatory and not ((clause.fallback_content or '').strip() or (clause.playbook_notes or '').strip()):
        issues.append('Mandatory clauses must include fallback language or playbook guidance.')
    if clause.jurisdiction_scope == ClauseTemplate.JurisdictionScope.CUSTOM and not clause.tags.strip():
        issues.append('Custom scope clauses should include tags to explain the fallback playbook context.')
    return issues


def get_clause_fallback_summary(clause: ClauseTemplate) -> dict:
    fallback_text = resolve_clause_fallback(clause)
    return {
        'has_fallback': bool(fallback_text),
        'fallback_text': fallback_text,
        'is_mandatory': clause.is_mandatory,
        'jurisdiction_scope': clause.jurisdiction_scope,
    }
