"""Action planning and execution for contract AI assistant flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

from django.utils import timezone

from contracts.models import ApprovalRequest, Contract, LegalTask, Organization, User, Workflow


@dataclass
class PlannedAction:
    action_type: str
    description: str
    payload: dict[str, Any]
    requires_approval: bool = True


def _normalize_prompt(prompt: str) -> str:
    return (prompt or "").strip().lower()


def build_action_plan(contract: Contract, prompt: str) -> list[PlannedAction]:
    normalized = _normalize_prompt(prompt)
    planned: list[PlannedAction] = []

    if any(token in normalized for token in ("workflow", "route", "approval flow")):
        planned.append(
            PlannedAction(
                action_type="create_workflow",
                description="Start an active workflow for this contract.",
                payload={
                    "title": f"AI Workflow - {contract.title}",
                    "description": "Generated from AI assistant action plan.",
                },
            )
        )

    if any(token in normalized for token in ("approval", "approve", "signoff", "legal review")):
        planned.append(
            PlannedAction(
                action_type="create_approval_request",
                description="Create a legal approval request assigned for review.",
                payload={
                    "approval_step": "LEGAL",
                    "comments": "AI-generated approval request from assistant.",
                },
            )
        )

    if any(token in normalized for token in ("task", "follow up", "follow-up", "renew", "renewal", "expiry", "expire")):
        planned.append(
            PlannedAction(
                action_type="create_legal_task",
                description="Create a high-priority legal follow-up task.",
                payload={
                    "title": f"AI Follow-up - {contract.title}",
                    "description": "Generated from AI assistant action plan.",
                    "priority": LegalTask.Priority.HIGH,
                    "due_in_days": 7,
                },
            )
        )

    return planned


def execute_action_plan(
    *,
    organization: Organization,
    contract: Contract,
    actor: User,
    plan: list[PlannedAction],
) -> dict[str, Any]:
    trace_id = str(uuid4())
    executed: list[dict[str, Any]] = []
    rollback_steps: list[dict[str, Any]] = []

    for action in plan:
        if action.action_type == "create_workflow":
            workflow = Workflow.objects.create(
                organization=organization,
                contract=contract,
                title=action.payload["title"],
                description=action.payload["description"],
                status=Workflow.Status.ACTIVE,
                created_by=actor,
            )
            executed.append(
                {
                    "action_type": action.action_type,
                    "object_type": "Workflow",
                    "object_id": workflow.id,
                    "description": action.description,
                }
            )
            rollback_steps.append({"operation": "delete", "object_type": "Workflow", "object_id": workflow.id})
            continue

        if action.action_type == "create_approval_request":
            approval = ApprovalRequest.objects.create(
                organization=organization,
                contract=contract,
                approval_step=action.payload["approval_step"],
                status=ApprovalRequest.Status.PENDING,
                assigned_to=actor,
                comments=action.payload["comments"],
                due_date=timezone.now() + timedelta(hours=48),
            )
            executed.append(
                {
                    "action_type": action.action_type,
                    "object_type": "ApprovalRequest",
                    "object_id": approval.id,
                    "description": action.description,
                }
            )
            rollback_steps.append({"operation": "delete", "object_type": "ApprovalRequest", "object_id": approval.id})
            continue

        if action.action_type == "create_legal_task":
            due_in_days = int(action.payload.get("due_in_days", 7))
            task = LegalTask.objects.create(
                title=action.payload["title"],
                description=action.payload["description"],
                priority=action.payload["priority"],
                status=LegalTask.Status.PENDING,
                assigned_to=actor,
                contract=contract,
                due_date=timezone.localdate() + timedelta(days=due_in_days),
            )
            executed.append(
                {
                    "action_type": action.action_type,
                    "object_type": "LegalTask",
                    "object_id": task.id,
                    "description": action.description,
                }
            )
            rollback_steps.append({"operation": "delete", "object_type": "LegalTask", "object_id": task.id})

    return {
        "trace_id": trace_id,
        "executed": executed,
        "rollback_plan": rollback_steps,
        "status": "executed",
    }
