
import os
from django.conf import settings

def get_feature_flag(flag_name, default=False):
    """Get feature flag value from environment or settings"""
    # First check environment variables
    env_value = os.environ.get(flag_name)
    if env_value is not None:
        return env_value.lower() in ('true', '1', 'yes', 'on')
    
    # Then check Django settings
    return getattr(settings, flag_name, default)

def is_feature_redesign_enabled():
    """Check if FEATURE_REDESIGN flag is enabled"""
    return get_feature_flag('FEATURE_REDESIGN', False)

def is_ironclad_mode_enabled():
    """Check if IRONCLAD_MODE flag is enabled"""
    return get_feature_flag('IRONCLAD_MODE', False)

def is_mochadocs_mode_enabled():
    """Check if MOCHADOCS_MODE flag is enabled"""
    return get_feature_flag('MOCHADOCS_MODE', False)

def is_test_mode_enabled():
    """Check if TEST_MODE flag is enabled"""
    return get_feature_flag('TEST_MODE', False)

# Cache for feature flags to avoid repeated lookups
cache = {}

def clear_cache():
    """Clear the feature flags cache"""
    global cache
    cache.clear()
