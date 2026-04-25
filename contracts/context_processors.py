
from django.conf import settings

from config.feature_flags import (
    is_feature_redesign_enabled,
    is_cms_aegis_mode_enabled,
    is_mochadocs_mode_enabled,
    is_test_mode_enabled
)
from .models import Notification, OrganizationMembership

def feature_flags(request):
    """Add feature flags to template context"""
    unread_notifications = 0
    if getattr(request, 'user', None) and request.user.is_authenticated:
        unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return {
        'FEATURE_REDESIGN': is_feature_redesign_enabled(),
        'CMS_AEGIS_MODE': is_cms_aegis_mode_enabled(),
        'MOCHADOCS_MODE': is_mochadocs_mode_enabled(),
        'TEST_MODE': is_test_mode_enabled(),
        'SSO_ENABLED': getattr(settings, 'SSO_ENABLED', False),
        'BUILD_SHA': getattr(settings, 'BUILD_SHA', 'unknown'),
        'BUILD_LABEL': getattr(settings, 'BUILD_LABEL', 'commit unknown'),
        'CURRENT_ORGANIZATION': getattr(request, 'organization', None),
        'UNREAD_NOTIFICATIONS': unread_notifications,
        'USER_ORGANIZATION_MEMBERSHIPS': (
            OrganizationMembership.objects.filter(user=request.user, is_active=True).select_related('organization')
            if getattr(request, 'user', None) and request.user.is_authenticated
            else OrganizationMembership.objects.none()
        ),
    }
