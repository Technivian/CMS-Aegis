"""Template service backed by persisted Django models."""

from dataclasses import dataclass, field
from typing import List, Optional

from django.db.models import QuerySet

from contracts.models import Organization, WorkflowTemplate


@dataclass
class Template:
    id: str
    title: str
    content: str
    category: str = "general"
    version: int = 1
    created_by: str = ""
    created_at: str = ""
    tags: List[str] = field(default_factory=list)


class TemplateService:
    """Persisted template operations over WorkflowTemplate."""

    def __init__(self, organization: Optional[Organization] = None):
        self.organization = organization

    def _base_queryset(self) -> QuerySet[WorkflowTemplate]:
        qs = WorkflowTemplate.objects.all()
        if self.organization is not None:
            # WorkflowTemplate is currently global; keep organization arg for forward compatibility.
            return qs
        return qs

    @staticmethod
    def _to_dto(template: WorkflowTemplate) -> Template:
        return Template(
            id=str(template.pk),
            title=template.name,
            content=template.description,
            category=(template.category or "GENERAL").lower(),
            version=template.version,
            created_at=template.created_at.isoformat() if template.created_at else "",
        )

    def list_templates(self, category: Optional[str] = None, tags: Optional[List[str]] = None) -> List[Template]:
        """List persisted templates with optional category and lightweight tag filtering."""
        qs = self._base_queryset().order_by("-created_at")

        if category:
            qs = qs.filter(category=str(category).upper())

        results = [self._to_dto(item) for item in qs]
        if tags:
            lowered = [tag.strip().lower() for tag in tags if tag and tag.strip()]
            if lowered:
                results = [
                    item for item in results
                    if any(tag in item.title.lower() or tag in item.content.lower() for tag in lowered)
                ]
        return results

    def get_template(self, template_id: str) -> Optional[Template]:
        """Get a specific persisted template by id."""
        template = self._base_queryset().filter(pk=template_id).first()
        return self._to_dto(template) if template else None

    def create_template(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
    ) -> Template:
        """Create a persisted template."""
        template = WorkflowTemplate.objects.create(
            name=title,
            description=content,
            category=str(category or "general").upper(),
            version=1,
            is_active=True,
        )
        dto = self._to_dto(template)
        dto.tags = [tag.strip() for tag in (tags or []) if tag and tag.strip()]
        return dto

    def update_template(self, template_id: str, **kwargs) -> Optional[Template]:
        """Update a persisted template."""
        template = self._base_queryset().filter(pk=template_id).first()
        if not template:
            return None

        if "title" in kwargs:
            template.name = kwargs["title"]
        if "content" in kwargs:
            template.description = kwargs["content"]
        if "category" in kwargs:
            template.category = str(kwargs["category"] or "general").upper()
        template.save(update_fields=["name", "description", "category"])

        dto = self._to_dto(template)
        if "tags" in kwargs:
            dto.tags = [tag.strip() for tag in (kwargs.get("tags") or []) if tag and tag.strip()]
        return dto

    def delete_template(self, template_id: str) -> bool:
        """Delete a persisted template."""
        deleted, _ = self._base_queryset().filter(pk=template_id).delete()
        return deleted > 0


def get_template_service(organization: Optional[Organization] = None) -> TemplateService:
    return TemplateService(organization=organization)
