"""Clause service backed by persisted Django models."""

from dataclasses import dataclass, field
from typing import List, Optional

from django.db.models import QuerySet
from django.db.models import Q

from contracts.models import ClauseCategory, ClauseTemplate, Organization


@dataclass
class Clause:
    id: str
    title: str
    content: str
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    version: str = "1"
    created_by: str = ""
    created_at: str = ""


class ClauseService:
    """Persisted clause library service."""

    def __init__(self, organization: Optional[Organization] = None):
        self.organization = organization

    def _base_queryset(self) -> QuerySet[ClauseTemplate]:
        qs = ClauseTemplate.objects.select_related("category")
        if self.organization is not None:
            qs = qs.filter(organization=self.organization)
        return qs

    @staticmethod
    def _parse_tags(tags: str) -> List[str]:
        return [token.strip() for token in (tags or "").split(",") if token.strip()]

    @staticmethod
    def _to_dto(clause: ClauseTemplate) -> Clause:
        return Clause(
            id=str(clause.pk),
            title=clause.title,
            content=clause.content,
            category=clause.category.name if clause.category else "general",
            tags=ClauseService._parse_tags(clause.tags),
            version=str(clause.version),
            created_by=clause.created_by.username if clause.created_by else "",
            created_at=clause.created_at.isoformat() if clause.created_at else "",
        )

    def search_clauses(
        self,
        query: str = "",
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Clause]:
        """Search persisted clauses by text/category/tags."""
        qs = self._base_queryset().order_by("-created_at")

        if query:
            qs = qs.filter(Q(title__icontains=query) | Q(content__icontains=query))

        if category:
            qs = qs.filter(category__name__iexact=category)

        clauses = [self._to_dto(item) for item in qs]
        if tags:
            normalized = {tag.strip().lower() for tag in tags if tag and tag.strip()}
            if normalized:
                clauses = [
                    item for item in clauses
                    if normalized.intersection({tag.lower() for tag in item.tags})
                ]
        return clauses

    def get_clause(self, clause_id: str) -> Optional[Clause]:
        clause = self._base_queryset().filter(pk=clause_id).first()
        return self._to_dto(clause) if clause else None

    def create_clause(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
    ) -> Clause:
        category_obj = None
        category_name = (category or "general").strip() or "general"
        if category_name:
            category_obj, _ = ClauseCategory.objects.get_or_create(
                organization=self.organization,
                name=category_name,
                defaults={"description": "", "order": 0},
            )

        clause = ClauseTemplate.objects.create(
            organization=self.organization,
            title=title,
            category=category_obj,
            content=content,
            tags=", ".join([tag.strip() for tag in (tags or []) if tag and tag.strip()]),
        )
        return self._to_dto(clause)

    def get_categories(self) -> List[str]:
        qs = ClauseCategory.objects.all()
        if self.organization is not None:
            qs = qs.filter(organization=self.organization)
        return list(qs.order_by("name").values_list("name", flat=True))

    def get_all_tags(self) -> List[str]:
        tags: set[str] = set()
        for item in self._base_queryset().values_list("tags", flat=True):
            tags.update(self._parse_tags(item))
        return sorted(tags)


def get_clause_service(organization: Optional[Organization] = None) -> ClauseService:
    return ClauseService(organization=organization)
