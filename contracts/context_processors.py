from django.conf import settings
from .models import Contract, WorkflowStep
from config.feature_flags import is_feature_redesign_enabled


def feature_flags(request):
    """Add feature flags to template context"""
    return {
        'ironclad_mode': getattr(settings, 'IRONCLAD_MODE', False),
        'feature_redesign': is_feature_redesign_enabled(),
    }