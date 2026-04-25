"""Clause template versioning helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from contracts.models import ClauseTemplate, ClauseVariant, Organization, User


@dataclass(frozen=True)
class ClauseTemplateComparison:
    left_template: ClauseTemplate
    right_template: ClauseTemplate
    field_diffs: list[tuple[str, str, str]]
    variant_diffs: list[str]


COMPARABLE_CLAUSE_FIELDS = (
    'title',
    'category_id',
    'content',
    'fallback_content',
    'jurisdiction_scope',
    'is_mandatory',
    'applicable_contract_types',
    'playbook_notes',
    'tags',
    'version',
)


def _normalize_value(value) -> str:
    if value is None:
        return ''
    return str(value)


def _root_clause_template(template: ClauseTemplate) -> ClauseTemplate:
    root = template
    seen: set[int] = set()
    while root.parent_template_id and root.parent_template_id not in seen:
        seen.add(root.id)
        root = root.parent_template
    return root


def _collect_descendants(template: ClauseTemplate) -> list[ClauseTemplate]:
    queue = [template]
    collected: list[ClauseTemplate] = []
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if current.pk in seen:
            continue
        seen.add(current.pk)
        collected.append(current)
        queue.extend(list(current.derived_versions.all()))
    return collected


def list_clause_template_versions(template: ClauseTemplate) -> list[ClauseTemplate]:
    if not template:
        return []
    root = _root_clause_template(template)
    versions = _collect_descendants(root)
    return sorted(versions, key=lambda item: (-item.version, -item.created_at.timestamp(), -item.pk))


def _next_version_number(template: ClauseTemplate) -> int:
    versions = list_clause_template_versions(template)
    if versions:
        return versions[0].version + 1
    return (template.version or 1) + 1


@transaction.atomic
def clone_clause_template_version(
    template: ClauseTemplate,
    *,
    title: Optional[str] = None,
    category=None,
    content: Optional[str] = None,
    fallback_content: Optional[str] = None,
    jurisdiction_scope: Optional[str] = None,
    is_mandatory: Optional[bool] = None,
    applicable_contract_types: Optional[str] = None,
    playbook_notes: Optional[str] = None,
    tags: Optional[str] = None,
    is_approved: bool = False,
    approved_by: Optional[User] = None,
    created_by: Optional[User] = None,
    copy_variants: bool = True,
) -> ClauseTemplate:
    next_version = _next_version_number(template)
    clone = ClauseTemplate.objects.create(
        organization=template.organization,
        title=title if title is not None else template.title,
        category=category if category is not None else template.category,
        content=content if content is not None else template.content,
        fallback_content=fallback_content if fallback_content is not None else template.fallback_content,
        jurisdiction_scope=jurisdiction_scope if jurisdiction_scope is not None else template.jurisdiction_scope,
        is_mandatory=template.is_mandatory if is_mandatory is None else is_mandatory,
        applicable_contract_types=(
            applicable_contract_types if applicable_contract_types is not None else template.applicable_contract_types
        ),
        version=next_version,
        parent_template=template,
        is_approved=is_approved,
        approved_by=approved_by if is_approved else None,
        approved_at=None if not is_approved else template.approved_at,
        playbook_notes=playbook_notes if playbook_notes is not None else template.playbook_notes,
        tags=tags if tags is not None else template.tags,
        created_by=created_by if created_by is not None else template.created_by,
    )

    if copy_variants:
        for variant in template.variants.select_related('playbook').filter(is_active=True).order_by('priority', '-created_at', 'pk'):
            ClauseVariant.objects.create(
                organization=clone.organization,
                template=clone,
                playbook=variant.playbook,
                jurisdiction_scope=variant.jurisdiction_scope,
                contract_type=variant.contract_type,
                risk_level=variant.risk_level,
                fallback_content=variant.fallback_content,
                playbook_notes=variant.playbook_notes,
                priority=variant.priority,
                is_active=variant.is_active,
            )

    return clone


def compare_clause_versions(left_template: ClauseTemplate, right_template: ClauseTemplate) -> ClauseTemplateComparison:
    field_diffs: list[tuple[str, str, str]] = []
    for field_name in COMPARABLE_CLAUSE_FIELDS:
        left_value = _normalize_value(getattr(left_template, field_name, ''))
        right_value = _normalize_value(getattr(right_template, field_name, ''))
        if left_value != right_value:
            field_diffs.append((field_name, left_value, right_value))

    left_variants = list(left_template.variants.select_related('playbook').filter(is_active=True).order_by('priority', 'pk'))
    right_variants = list(right_template.variants.select_related('playbook').filter(is_active=True).order_by('priority', 'pk'))
    variant_diffs: list[str] = []
    max_length = max(len(left_variants), len(right_variants))
    for index in range(max_length):
        left_variant = left_variants[index] if index < len(left_variants) else None
        right_variant = right_variants[index] if index < len(right_variants) else None
        if left_variant and right_variant:
            if (
                left_variant.playbook_id != right_variant.playbook_id
                or left_variant.fallback_content != right_variant.fallback_content
                or left_variant.playbook_notes != right_variant.playbook_notes
                or left_variant.priority != right_variant.priority
                or left_variant.jurisdiction_scope != right_variant.jurisdiction_scope
                or left_variant.contract_type != right_variant.contract_type
                or left_variant.risk_level != right_variant.risk_level
            ):
                variant_diffs.append(
                    f"Variant {index + 1}: {left_variant.playbook or 'No playbook'} -> {right_variant.playbook or 'No playbook'}"
                )
        elif left_variant and not right_variant:
            variant_diffs.append(f"Variant {index + 1}: removed {left_variant.playbook or 'No playbook'}")
        elif right_variant and not left_variant:
            variant_diffs.append(f"Variant {index + 1}: added {right_variant.playbook or 'No playbook'}")

    return ClauseTemplateComparison(
        left_template=left_template,
        right_template=right_template,
        field_diffs=field_diffs,
        variant_diffs=variant_diffs,
    )
