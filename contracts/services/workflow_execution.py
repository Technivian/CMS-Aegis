from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from contracts.models import Notification, OrganizationMembership, WorkflowStep


_CONDITION_PATTERN = re.compile(r'^\s*(?P<field>[a-zA-Z0-9_]+)\s*(?P<op>>=|<=|!=|=|>|<|~)\s*(?P<value>.+?)\s*$')
_BOOL_TRUE = {'1', 'true', 't', 'yes', 'y', 'on'}
_BOOL_FALSE = {'0', 'false', 'f', 'no', 'n', 'off'}

_FIELD_ALIASES = {
    'type': 'contract_type',
    'contract_type': 'contract_type',
    'value': 'value',
    'risk': 'risk_level',
    'risk_level': 'risk_level',
    'jurisdiction': 'jurisdiction',
    'governing_law': 'governing_law',
    'data_transfer': 'data_transfer_flag',
    'data_transfer_flag': 'data_transfer_flag',
    'status': 'status',
    'counterparty': 'counterparty',
}


def _normalized_text(value):
    return (value or '').strip().upper()


def _contract_field_value(contract, field_name):
    if contract is None:
        return None
    normalized = _FIELD_ALIASES.get(field_name.strip().lower(), field_name.strip().lower())
    return getattr(contract, normalized, None)


def _coerce_boolean(raw_value):
    normalized = _normalized_text(raw_value)
    if normalized in _BOOL_TRUE:
        return True
    if normalized in _BOOL_FALSE:
        return False
    raise ValueError(f'Unsupported boolean value: {raw_value}')


def _coerce_decimal(raw_value):
    normalized = str(raw_value or '').strip().replace(',', '')
    normalized = normalized.lstrip('$€£')
    return Decimal(normalized)


def evaluate_condition_expression(contract, expression):
    expression = (expression or '').strip()
    if not expression:
        return True

    match = _CONDITION_PATTERN.match(expression)
    if not match:
        return False

    field_name = match.group('field')
    operator = match.group('op')
    expected_value = match.group('value').strip()
    actual_value = _contract_field_value(contract, field_name)

    try:
        if isinstance(actual_value, bool):
            actual_bool = bool(actual_value)
            expected_bool = _coerce_boolean(expected_value)
            if operator == '=':
                return actual_bool == expected_bool
            if operator == '!=':
                return actual_bool != expected_bool
            return False

        if isinstance(actual_value, (int, float, Decimal)):
            actual_decimal = Decimal(str(actual_value))
            expected_decimal = _coerce_decimal(expected_value)
            if operator == '=':
                return actual_decimal == expected_decimal
            if operator == '!=':
                return actual_decimal != expected_decimal
            if operator == '>':
                return actual_decimal > expected_decimal
            if operator == '>=':
                return actual_decimal >= expected_decimal
            if operator == '<':
                return actual_decimal < expected_decimal
            if operator == '<=':
                return actual_decimal <= expected_decimal
            return False

        actual_text = _normalized_text(actual_value)
        expected_text = _normalized_text(expected_value)
        if operator == '=':
            return actual_text == expected_text
        if operator == '!=':
            return actual_text != expected_text
        if operator == '~':
            return expected_text in actual_text
        if operator in {'>', '>=', '<', '<='}:
            return False
        return False
    except (InvalidOperation, ValueError):
        return False


@transaction.atomic
def materialize_workflow_from_template(workflow, *, refresh: bool = False):
    if not workflow or not workflow.template_id:
        return []

    existing_steps = list(workflow.steps.all())
    if existing_steps and not refresh:
        return existing_steps

    if refresh and existing_steps:
        workflow.steps.all().delete()

    now = timezone.now()
    created_steps = []
    first_actionable = True
    for template_step in workflow.template.steps.order_by('order', 'pk'):
        applies = template_step.applies_to_contract(workflow.contract)
        due_date = None
        if template_step.sla_hours:
            due_date = now + timedelta(hours=int(template_step.sla_hours))

        status = WorkflowStep.Status.PENDING
        blocked_reason = ''
        completed_at = None
        if not applies:
            status = WorkflowStep.Status.SKIPPED
            blocked_reason = (
                f"Condition '{template_step.condition_expression}' was not met for this contract."
                if template_step.condition_expression
                else 'Step skipped for this contract.'
            )
            due_date = None
        elif template_step.step_kind == template_step.StepKind.AUTOMATIC:
            status = WorkflowStep.Status.COMPLETED
            completed_at = now
        elif first_actionable:
            status = WorkflowStep.Status.IN_PROGRESS
            first_actionable = False
        else:
            first_actionable = False

        created_steps.append(
            WorkflowStep.objects.create(
                workflow=workflow,
                template_step=template_step,
                name=template_step.name,
                description=template_step.description,
                status=status,
                assigned_to=template_step.resolve_assignee(workflow.contract),
                due_date=due_date,
                completed_at=completed_at,
                order=template_step.order,
                blocked_reason=blocked_reason,
            )
        )

    if created_steps and all(step.status in {WorkflowStep.Status.COMPLETED, WorkflowStep.Status.SKIPPED} for step in created_steps):
        workflow.status = workflow.Status.COMPLETED
        workflow.save(update_fields=['status'])
    return created_steps


@transaction.atomic
def advance_workflow_after_completion(step):
    workflow = step.workflow
    next_step = (
        workflow.steps
        .filter(order__gt=step.order)
        .exclude(status__in=[WorkflowStep.Status.COMPLETED, WorkflowStep.Status.SKIPPED])
        .order_by('order', 'pk')
        .first()
    )
    if next_step and next_step.status == WorkflowStep.Status.PENDING:
        next_step.status = WorkflowStep.Status.IN_PROGRESS
        if next_step.due_date is None and next_step.template_step and next_step.template_step.sla_hours:
            next_step.due_date = timezone.now() + timedelta(hours=int(next_step.template_step.sla_hours))
        next_step.save(update_fields=['status', 'due_date'])
        return next_step

    if not workflow.steps.exclude(status__in=[WorkflowStep.Status.COMPLETED, WorkflowStep.Status.SKIPPED]).exists():
        workflow.status = workflow.Status.COMPLETED
        workflow.save(update_fields=['status'])
    return None


def _workflow_reminder_recipients(step):
    recipients = set()
    if step.assigned_to_id:
        recipients.add(step.assigned_to)
    if step.workflow and step.workflow.created_by_id:
        recipients.add(step.workflow.created_by)
    organization = step.workflow.organization
    if organization:
        for membership in OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role__in=[OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN],
        ).select_related('user'):
            recipients.add(membership.user)
    return recipients


@transaction.atomic
def escalate_overdue_workflow_steps(now=None):
    now = now or timezone.now()
    overdue_steps = WorkflowStep.objects.select_related('workflow', 'workflow__organization', 'workflow__created_by', 'assigned_to').filter(
        status__in=[WorkflowStep.Status.PENDING, WorkflowStep.Status.IN_PROGRESS],
        due_date__isnull=False,
        due_date__lt=now,
        escalated_at__isnull=True,
    )
    notifications = 0
    for step in overdue_steps:
        recipients = _workflow_reminder_recipients(step)
        link = reverse('contracts:workflow_detail', kwargs={'pk': step.workflow_id})
        title = f'Workflow overdue: {step.workflow.title} ({step.name})'
        for recipient in recipients:
            if Notification.objects.filter(
                recipient=recipient,
                notification_type=Notification.NotificationType.TASK,
                title=title,
                link=link,
                created_at__date=timezone.localdate(now),
            ).exists():
                continue
            Notification.objects.create(
                recipient=recipient,
                notification_type=Notification.NotificationType.TASK,
                title=title,
                message=(
                    f'{step.workflow.title} is waiting on "{step.name}" and it was due '
                    f'on {step.due_date.isoformat()}.'
                ),
                link=link,
            )
            notifications += 1

        step.status = WorkflowStep.Status.ESCALATED
        step.escalated_at = now
        step.save(update_fields=['status', 'escalated_at'])

    return {
        'escalated_count': overdue_steps.count(),
        'notification_count': notifications,
    }
