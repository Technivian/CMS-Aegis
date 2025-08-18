
"""
Services package for contract operations
"""
"""
Service factory for switching between mock and real services based on feature flags
"""
from config.feature_flags import is_test_mode
from .repository import MockRepositoryService
from .templates import template_service
from .clauses import clause_service
from .obligations import obligation_service

def get_repository_service():
    """Get repository service - mock in test mode, real service otherwise"""
    if is_test_mode():
        return MockRepositoryService()
    else:
        # TODO: Return real repository service when available
        return MockRepositoryService()

def get_template_service():
    """Get template service"""
    return template_service

def get_clause_service():
    """Get clause service"""
    return clause_service

def get_obligation_service():
    """Get obligation service"""
    return obligation_service

# Export services for easy import
__all__ = [
    'get_repository_service',
    'get_template_service', 
    'get_clause_service',
    'get_obligation_service'
]
