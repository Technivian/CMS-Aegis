
"""
Feature flags for enabling/disabling functionality
"""
import os
from django.conf import settings

class FeatureFlags:
    """Feature flag management"""
    
    @staticmethod
    def is_enabled(flag_name: str) -> bool:
        """Check if a feature flag is enabled"""
        return getattr(settings, flag_name, False) or os.getenv(flag_name, '').lower() == 'true'
    
    @staticmethod
    def ironclad_mode() -> bool:
        """Check if Ironclad mode is enabled"""
        return FeatureFlags.is_enabled('IRONCLAD_MODE')

# Convenience function
def ironclad_mode():
    return FeatureFlags.ironclad_mode()
"""
Feature flags for enabling new functionality while preserving existing behavior
"""

# Feature flags - set these to enable new behaviors
IRONCLAD_MODE = True          # enables advanced repo UX (filters, bulk actions, drawer)
MOCHADOCS_MODE = True         # enables templates/clauses/obligations flows  
TEST_MODE = True              # makes e2e safe (uses mocks, no real API calls)

def is_ironclad_enabled():
    """Check if Ironclad-style repository features are enabled"""
    return IRONCLAD_MODE

def is_mochadocs_enabled():
    """Check if template/clause/obligations features are enabled"""
    return MOCHADOCS_MODE

def is_test_mode():
    """Check if test mode is enabled (uses mocks)"""
    return TEST_MODE
