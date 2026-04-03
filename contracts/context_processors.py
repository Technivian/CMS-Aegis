
from config.feature_flags import (
    is_feature_redesign_enabled,
    is_ironclad_mode_enabled,
    is_mochadocs_mode_enabled,
    is_test_mode_enabled
)
from .models import OrganizationMembership

def feature_flags(request):
    """Add feature flags to template context"""
    return {
        'FEATURE_REDESIGN': is_feature_redesign_enabled(),
        'IRONCLAD_MODE': is_ironclad_mode_enabled(),
        'MOCHADOCS_MODE': is_mochadocs_mode_enabled(),
        'TEST_MODE': is_test_mode_enabled(),
        'CURRENT_ORGANIZATION': getattr(request, 'organization', None),
        'USER_ORGANIZATION_MEMBERSHIPS': (
            OrganizationMembership.objects.filter(user=request.user, is_active=True).select_related('organization')
            if getattr(request, 'user', None) and request.user.is_authenticated
            else OrganizationMembership.objects.none()
        ),
    }
