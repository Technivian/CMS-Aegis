"""Workflow template versioning and migration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.db import transaction

from contracts.models import Workflow, WorkflowTemplate, WorkflowTemplateStep


@dataclass(frozen=True)
class WorkflowTemplateMigrationResult:
    source_template_id: int
    new_template_id: int
    migrated_workflow_count: int


@dataclass(frozen=True)
class WorkflowTemplateComparison:
    left_template: WorkflowTemplate
    right_template: WorkflowTemplate
    field_diffs: list[tuple[str, str, str]]
    step_diffs: list[str]
    preset: str


COMPARISON_PRESETS = {
    'full': {
        'label': 'Full comparison',
        'fields': ['name', 'description', 'category', 'version', 'is_active'],
    },
    'legal_ops': {
        'label': 'Legal ops review',
        'fields': ['name', 'category', 'is_active'],
    },
    'steps_only': {
        'label': 'Steps only',
        'fields': [],
    },
}


def list_template_versions(template: WorkflowTemplate) -> list[WorkflowTemplate]:
    if not template:
        return []
    root = template
    while root.parent_template_id:
        root = root.parent_template
    return list(
        WorkflowTemplate.objects.filter(
            name=root.name,
            category=root.category,
        ).order_by('-version', '-created_at', '-pk')
    )


def _next_version_number(template: WorkflowTemplate) -> int:
    versions = list_template_versions(template)
    if versions:
        return versions[0].version + 1
    return (template.version or 1) + 1


@transaction.atomic
def clone_template_version(
    template: WorkflowTemplate,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    is_active: bool = True,
    copy_steps: bool = True,
) -> WorkflowTemplate:
    next_version = _next_version_number(template)
    clone = WorkflowTemplate.objects.create(
        name=name or template.name,
        description=description if description is not None else template.description,
        category=category or template.category,
        version=next_version,
        parent_template=template,
        is_active=is_active,
    )

    if copy_steps:
        for step in template.steps.order_by('order', 'pk'):
            WorkflowTemplateStep.objects.create(
                template=clone,
                name=step.name,
                description=step.description,
                order=step.order,
                estimated_duration=step.estimated_duration,
            )

    return clone


@transaction.atomic
def migrate_workflows_to_template(
    source_template: WorkflowTemplate,
    target_template: WorkflowTemplate,
    workflows: Optional[Iterable[Workflow]] = None,
) -> WorkflowTemplateMigrationResult:
    queryset = Workflow.objects.filter(template=source_template)
    if workflows is not None:
        workflow_ids = [workflow.pk for workflow in workflows if workflow and workflow.pk]
        queryset = queryset.filter(pk__in=workflow_ids)
    migrated_count = queryset.update(template=target_template)
    return WorkflowTemplateMigrationResult(
        source_template_id=source_template.pk,
        new_template_id=target_template.pk,
        migrated_workflow_count=migrated_count,
    )


def compare_template_versions(
    left_template: WorkflowTemplate,
    right_template: WorkflowTemplate,
    *,
    preset: str = 'full',
) -> WorkflowTemplateComparison:
    left_steps = list(left_template.steps.order_by('order', 'pk'))
    right_steps = list(right_template.steps.order_by('order', 'pk'))

    field_diffs: list[tuple[str, str, str]] = []
    preset_config = COMPARISON_PRESETS.get(preset, COMPARISON_PRESETS['full'])
    for field_name in preset_config['fields']:
        left_value = getattr(left_template, field_name)
        right_value = getattr(right_template, field_name)
        if left_value != right_value:
            field_diffs.append((field_name, str(left_value), str(right_value)))

    step_diffs: list[str] = []
    max_length = max(len(left_steps), len(right_steps))
    for index in range(max_length):
        left_step = left_steps[index] if index < len(left_steps) else None
        right_step = right_steps[index] if index < len(right_steps) else None
        if left_step and right_step:
            if (
                left_step.name != right_step.name
                or left_step.description != right_step.description
                or left_step.order != right_step.order
            ):
                step_diffs.append(
                    f"Step {index + 1}: {left_step.order}. {left_step.name} -> {right_step.order}. {right_step.name}"
                )
        elif left_step and not right_step:
            step_diffs.append(f"Step {index + 1}: removed {left_step.order}. {left_step.name}")
        elif right_step and not left_step:
            step_diffs.append(f"Step {index + 1}: added {right_step.order}. {right_step.name}")

    return WorkflowTemplateComparison(
        left_template=left_template,
        right_template=right_template,
        field_diffs=field_diffs,
        step_diffs=step_diffs,
        preset=preset if preset in COMPARISON_PRESETS else 'full',
    )
