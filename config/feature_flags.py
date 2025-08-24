import os
from functools import lru_cache

# Feature flags cache for performance
cache = {}

@lru_cache(maxsize=128)
def get_feature_flag(flag_name, default=False):
    """Get feature flag value with caching"""
    if flag_name in cache:
        return cache[flag_name]

    value = os.environ.get(flag_name, str(default)).lower() in ('true', '1', 'yes', 'on')
    cache[flag_name] = value
    return value

def is_feature_redesign_enabled():
    """Check if the redesign feature is enabled"""
    return get_feature_flag('FEATURE_REDESIGN', False)

def clear_cache():
    """Clear the feature flags cache"""
    global cache
    cache.clear()
    get_feature_flag.cache_clear()