"""Clause variant and playbook resolution helpers."""

from dataclasses import dataclass
from typing import Optional

from contracts.models import ClauseTemplate, ClauseVariant, Contract


@dataclass
class ResolvedClauseVariant:
    variant: Optional[ClauseVariant]
    playbook_name: str
    fallback_content: str
    playbook_notes: str
    score: int


def _normalized(value):
    return (value or '').strip().upper()


def _matches_scope(variant: ClauseVariant, contract: Contract) -> bool:
    if not contract:
        return True
    variant_scope = _normalized(variant.jurisdiction_scope)
    if variant_scope == _normalized(ClauseTemplate.JurisdictionScope.GLOBAL):
        return True
    jurisdiction_text = ' '.join(
        part for part in [
            _normalized(contract.jurisdiction),
            _normalized(contract.governing_law),
        ] if part
    )
    return variant_scope in jurisdiction_text


def resolve_clause_variant(template: ClauseTemplate, contract: Optional[Contract] = None) -> ResolvedClauseVariant:
    if not template:
        return ResolvedClauseVariant(None, '', '', '', 0)

    candidates = template.variants.select_related('playbook').filter(is_active=True)
    scored_candidates = []
    for variant in candidates:
        score = 0
        if contract:
            if variant.contract_type and _normalized(variant.contract_type) == _normalized(contract.contract_type):
                score += 4
            if variant.risk_level and _normalized(variant.risk_level) == _normalized(contract.risk_level):
                score += 3
            if _matches_scope(variant, contract):
                score += 2
        else:
            score += 1
        score += int(variant.priority)
        scored_candidates.append((score, variant))

    scored_candidates.sort(key=lambda item: (-item[0], item[1].priority, item[1].created_at))
    if scored_candidates:
        score, variant = scored_candidates[0]
        return ResolvedClauseVariant(
            variant=variant,
            playbook_name=variant.playbook.name if variant.playbook else '',
            fallback_content=variant.fallback_content or template.fallback_content,
            playbook_notes=variant.playbook_notes or template.playbook_notes,
            score=score,
        )

    return ResolvedClauseVariant(
        variant=None,
        playbook_name='',
        fallback_content=template.fallback_content,
        playbook_notes=template.playbook_notes,
        score=0,
    )
