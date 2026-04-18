from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentVersionComparison:
    left_document_id: int
    right_document_id: int
    field_diffs: list[tuple[str, str, str]]


COMPARABLE_DOCUMENT_FIELDS = (
    'title',
    'document_type',
    'status',
    'description',
    'contract_id',
    'matter_id',
    'client_id',
    'tags',
    'is_privileged',
    'is_confidential',
    'file_hash',
)


def _normalize_value(value):
    if value is None:
        return ''
    return str(value)


def compare_document_versions(left_document, right_document) -> DocumentVersionComparison:
    field_diffs: list[tuple[str, str, str]] = []
    for field_name in COMPARABLE_DOCUMENT_FIELDS:
        left_value = _normalize_value(getattr(left_document, field_name, ''))
        right_value = _normalize_value(getattr(right_document, field_name, ''))
        if left_value != right_value:
            field_diffs.append((field_name, left_value, right_value))

    return DocumentVersionComparison(
        left_document_id=left_document.id,
        right_document_id=right_document.id,
        field_diffs=field_diffs,
    )
