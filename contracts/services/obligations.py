"""Obligations service backed by persisted Django models."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from django.db.models import QuerySet
from django.contrib.auth import get_user_model
from django.utils import timezone

from contracts.models import Contract, Deadline, Organization


@dataclass
class Obligation:
    id: str
    title: str
    description: str
    due_date: str
    contract_id: str
    assigned_to: str = ""
    priority: str = "medium"
    status: str = "pending"
    reminder_days: int = 7
    created_at: str = ""


class ObligationService:
    """Persisted obligation tracking over Deadline."""

    def __init__(self, organization: Optional[Organization] = None):
        self.organization = organization

    def _base_queryset(self) -> QuerySet[Deadline]:
        qs = Deadline.objects.select_related("contract", "assigned_to")
        if self.organization is not None:
            qs = Deadline.objects.for_organization(self.organization).select_related("contract", "assigned_to")
        return qs

    @staticmethod
    def _status_from_deadline(deadline: Deadline) -> str:
        if deadline.is_completed:
            return "completed"
        if deadline.is_overdue:
            return "overdue"
        return "pending"

    @staticmethod
    def _priority_to_api(value: str) -> str:
        return (value or "MEDIUM").lower()

    @staticmethod
    def _priority_to_model(value: str) -> str:
        normalized = (value or "medium").strip().upper()
        if normalized not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            return "MEDIUM"
        return normalized

    @staticmethod
    def _to_dto(deadline: Deadline) -> Obligation:
        return Obligation(
            id=str(deadline.pk),
            title=deadline.title,
            description=deadline.description,
            due_date=deadline.due_date.isoformat(),
            contract_id=str(deadline.contract_id) if deadline.contract_id else "",
            assigned_to=deadline.assigned_to.username if deadline.assigned_to else "",
            priority=ObligationService._priority_to_api(deadline.priority),
            status=ObligationService._status_from_deadline(deadline),
            reminder_days=deadline.reminder_days,
            created_at=deadline.created_at.isoformat() if deadline.created_at else "",
        )

    def list_obligations(
        self,
        contract_id: Optional[str] = None,
        assigned_to: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Obligation]:
        qs = self._base_queryset().order_by("due_date")

        if contract_id:
            qs = qs.filter(contract_id=contract_id)

        if assigned_to:
            qs = qs.filter(assigned_to__username=assigned_to)

        obligations = [self._to_dto(item) for item in qs]
        if status:
            status_lower = status.lower()
            obligations = [item for item in obligations if item.status == status_lower]
        return obligations

    def get_upcoming_obligations(self, days_ahead: int = 30) -> List[Obligation]:
        cutoff = date.today() + timedelta(days=days_ahead)
        qs = self._base_queryset().filter(due_date__gte=date.today(), due_date__lte=cutoff).order_by("due_date")
        return [self._to_dto(item) for item in qs]

    def get_overdue_obligations(self) -> List[Obligation]:
        qs = self._base_queryset().filter(is_completed=False, due_date__lt=date.today()).order_by("due_date")
        return [self._to_dto(item) for item in qs]

    def create_obligation(
        self,
        title: str,
        description: str,
        due_date: str,
        contract_id: str,
        assigned_to: str = "",
        priority: str = "medium",
    ) -> Obligation:
        contract = Contract.objects.get(pk=contract_id)
        assigned_user = None
        if assigned_to:
            user_model = get_user_model()
            assigned_user = user_model.objects.filter(username=assigned_to).first()

        deadline = Deadline.objects.create(
            title=title,
            description=description,
            deadline_type=Deadline.DeadlineType.CONTRACT,
            priority=self._priority_to_model(priority),
            due_date=date.fromisoformat(due_date),
            reminder_days=7,
            contract=contract,
            assigned_to=assigned_user,
            created_by=contract.created_by,
        )
        return self._to_dto(deadline)

    def update_obligation(self, obligation_id: str, **kwargs) -> Optional[Obligation]:
        deadline = self._base_queryset().filter(pk=obligation_id).first()
        if not deadline:
            return None

        update_fields: list[str] = []
        if "title" in kwargs:
            deadline.title = kwargs["title"]
            update_fields.append("title")
        if "description" in kwargs:
            deadline.description = kwargs["description"]
            update_fields.append("description")
        if "due_date" in kwargs:
            deadline.due_date = date.fromisoformat(kwargs["due_date"])
            update_fields.append("due_date")
        if "priority" in kwargs:
            deadline.priority = self._priority_to_model(kwargs["priority"])
            update_fields.append("priority")
        if "status" in kwargs:
            status = str(kwargs["status"]).lower()
            if status == "completed":
                deadline.is_completed = True
                deadline.completed_at = timezone.now()
            elif status in {"pending", "in_progress", "overdue"}:
                deadline.is_completed = False
                deadline.completed_at = None
            update_fields.extend(["is_completed", "completed_at"])

        if update_fields:
            deadline.save(update_fields=sorted(set(update_fields)))
        return self._to_dto(deadline)

    def get_dashboard_timeline(self, days_ahead: int = 60) -> List[Obligation]:
        return self.get_upcoming_obligations(days_ahead)


def get_obligation_service(organization: Optional[Organization] = None) -> ObligationService:
    return ObligationService(organization=organization)
