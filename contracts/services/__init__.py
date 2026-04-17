
"""Service accessors for contract operations.

Keep imports lazy so package consumers can import individual service modules
without triggering unrelated service initialization and circular imports.
"""

def get_repository_service(user=None):
    """Get repository service using the Django-backed implementation."""
    from .repository import DjangoRepositoryService

    if user is None:
        raise ValueError("user is required for repository service")
    return DjangoRepositoryService(user)


def get_template_service(organization=None):
    """Get persisted template service."""
    from .templates import get_template_service as _get

    return _get(organization=organization)


def get_clause_service(organization=None):
    """Get persisted clause service."""
    from .clauses import get_clause_service as _get

    return _get(organization=organization)


def get_obligation_service(organization=None):
    """Get persisted obligation service."""
    from .obligations import get_obligation_service as _get

    return _get(organization=organization)


def get_default_salesforce_field_map():
    """Get default Salesforce-to-contract canonical field mappings."""
    from .salesforce import default_field_map_records

    return default_field_map_records()

# Export services for easy import
__all__ = [
    'get_repository_service',
    'get_template_service',
    'get_clause_service',
    'get_obligation_service',
    'get_default_salesforce_field_map',
]
