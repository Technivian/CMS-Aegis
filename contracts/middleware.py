import logging
from uuid import uuid4

from .logging_context import (
    RequestContextLogFilter,
    request_id_var,
    request_org_id_var,
    request_path_var,
    request_user_id_var,
)
from .models import AuditLog
from .tenancy import get_user_organization

logger = logging.getLogger(__name__)


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response


class OrganizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False):
            preferred_org_id = request.session.get('active_organization_id')
            if preferred_org_id:
                user._active_organization_id = preferred_org_id
            organization = get_user_organization(user)
            request.organization = organization
            if organization and request.session.get('active_organization_id') != organization.id:
                request.session['active_organization_id'] = organization.id
        else:
            request.organization = None
        return self.get_response(request)
class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid4())
        request.request_id = request_id
        user = getattr(request, 'user', None)
        organization = getattr(request, 'organization', None)

        request_id_token = request_id_var.set(request_id)
        request_path_token = request_path_var.set(getattr(request, 'path', '-'))
        user_token = request_user_id_var.set(str(user.id) if getattr(user, 'is_authenticated', False) else '-')
        org_token = request_org_id_var.set(str(organization.id) if organization else '-')

        try:
            response = self.get_response(request)

            response['X-Request-ID'] = request_id
            logger.info(
                'request_completed',
                extra={
                    'method': request.method,
                    'path': request.path,
                    'status_code': response.status_code,
                },
            )
            return response
        finally:
            request_id_var.reset(request_id_token)
            request_path_var.reset(request_path_token)
            request_user_id_var.reset(user_token)
            request_org_id_var.reset(org_token)


def log_action(user, action, model_name, object_id=None, object_repr='', changes=None, request=None):
    ip_address = None
    user_agent = ''
    if request:
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ip_address and ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()
        user_agent = request.META.get('HTTP_USER_AGENT', '')

    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        object_repr=object_repr[:300],
        changes=changes,
        ip_address=ip_address,
        user_agent=user_agent[:500],
    )
