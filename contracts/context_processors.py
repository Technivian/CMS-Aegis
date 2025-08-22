
from config.feature_flags import is_feature_enabled

def feature_flags(request):
    """Add feature flags to template context"""
    return {
        'FEATURE_REDESIGN': is_feature_enabled('FEATURE_REDESIGN'),
    }
