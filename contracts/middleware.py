import logging
import time
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect

from .logging_context import (
    request_id_var,
    request_org_id_var,
    request_path_var,
    request_user_id_var,
)
from .models import UserProfile
from .session_security import current_session_timestamp
from .models import AuditLog
from .observability import record_request_metric
from .tenancy import get_user_organization

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """Apply baseline security headers consistently across responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not getattr(settings, 'SECURITY_HEADERS_ENABLED', True):
            return response

        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('Referrer-Policy', getattr(settings, 'SECURE_REFERRER_POLICY', 'same-origin'))
        response.setdefault('Permissions-Policy', getattr(settings, 'PERMISSIONS_POLICY', 'geolocation=(), microphone=(), camera=()'))
        response.setdefault('Content-Security-Policy', getattr(settings, 'CONTENT_SECURITY_POLICY', "default-src 'self'"))
        return response


class AuthRateLimitMiddleware:
    """
    Simple per-IP request throttling for auth-sensitive endpoints.

    This is intentionally lightweight and works without external dependencies.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'RATELIMIT_ENABLED', True):
            return self.get_response(request)

        path = request.path
        if path not in getattr(settings, 'RATELIMIT_PATHS', ('/login/', '/register/')):
            return self.get_response(request)

        if request.method not in {'POST'}:
            return self.get_response(request)

        client_ip = self._client_ip(request)
        if client_ip in getattr(settings, 'RATELIMIT_TRUSTED_IPS', ()):
            return self.get_response(request)

        try:
            limit, window = self._policy_for_path(path)
            key = f'auth-rl:{path}:{client_ip}'
            now = int(time.time())
            bucket = cache.get(key)

            if not bucket or not isinstance(bucket, dict) or now >= bucket.get('reset_at', 0):
                bucket = {'count': 0, 'reset_at': now + window}

            if bucket['count'] >= limit:
                retry_after = max(bucket['reset_at'] - now, 1)
                response = HttpResponse('Too many requests. Please try again later.', status=429)
                response['Retry-After'] = str(retry_after)
                return response

            bucket['count'] += 1
            cache.set(key, bucket, timeout=window)
        except Exception:
            logger.exception('auth_rate_limit_cache_failure', extra={'path': path, 'client_ip': client_ip})
        return self.get_response(request)

    @staticmethod
    def _client_ip(request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '') or 'unknown'

    @staticmethod
    def _policy_for_path(path):
        if path == '/register/':
            return (
                int(getattr(settings, 'REGISTER_RATE_LIMIT_REQUESTS', 10)),
                int(getattr(settings, 'REGISTER_RATE_LIMIT_WINDOW_SECONDS', 300)),
            )
        return (
            int(getattr(settings, 'LOGIN_RATE_LIMIT_REQUESTS', 10)),
            int(getattr(settings, 'LOGIN_RATE_LIMIT_WINDOW_SECONDS', 300)),
        )


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


class SessionSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return self.get_response(request)

        if self._requires_mfa_but_not_enrolled(request):
            return redirect(f"{settings.LOGIN_URL}?next={request.get_full_path()}")

        session = request.session
        profile, _ = UserProfile.objects.get_or_create(user=user)

        current_revocation_counter = profile.session_revocation_counter
        session_revocation_counter = session.get('session_revocation_counter')
        if session_revocation_counter is None:
            session['session_revocation_counter'] = current_revocation_counter
            session_revocation_counter = current_revocation_counter
        elif session_revocation_counter != current_revocation_counter:
            session.flush()
            return redirect(f"{settings.LOGIN_URL}?next={request.get_full_path()}")

        organization = getattr(request, 'organization', None) or get_user_organization(user)
        idle_timeout_minutes = int(
            getattr(organization, 'session_idle_timeout_minutes', None)
            or getattr(settings, 'SESSION_IDLE_TIMEOUT_MINUTES', 120)
        )
        now_ts = current_session_timestamp()
        last_activity = session.get('session_last_activity_at')
        if last_activity is not None:
            try:
                last_activity = int(last_activity)
            except (TypeError, ValueError):
                last_activity = None
        if last_activity is not None and now_ts - last_activity > idle_timeout_minutes * 60:
            session.flush()
            return redirect(f"{settings.LOGIN_URL}?next={request.get_full_path()}")

        session['session_last_activity_at'] = now_ts

        return self.get_response(request)

    @staticmethod
    def _is_exempt_path(path):
        exempt_prefixes = ('/login/', '/logout/', '/register/', '/profile/', '/settings/', '/admin/')
        return any(path.startswith(prefix) for prefix in exempt_prefixes)

    def _requires_mfa_but_not_enrolled(self, request):
        if self._is_exempt_path(request.path):
            return False
        organization = getattr(request, 'organization', None) or get_user_organization(request.user)
        if organization is None or not getattr(organization, 'require_mfa', False):
            return False
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return not profile.mfa_enabled or profile.mfa_verified_at is None
class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
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
            latency_ms = (time.perf_counter() - started) * 1000
            record_request_metric(request.path, response.status_code, latency_ms)

            response['X-Request-ID'] = request_id
            logger.info(
                'request_completed',
                extra={
                    'method': request.method,
                    'path': request.path,
                    'status_code': response.status_code,
                    'latency_ms': round(latency_ms, 2),
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
