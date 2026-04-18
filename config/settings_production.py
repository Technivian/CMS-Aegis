import os

from django.core.exceptions import ImproperlyConfigured

from . import settings_base as base
from .settings_base import *  # noqa: F401,F403


DEBUG = base._bool_env('DJANGO_DEBUG', default=False)

if DEBUG:
    raise ImproperlyConfigured('DJANGO_DEBUG must be false in production settings.')

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must be set in production.')
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured('CSRF_TRUSTED_ORIGINS must be set in production.')
if DEFAULT_FROM_EMAIL == 'noreply@cms-aegis.local':
    raise ImproperlyConfigured('DEFAULT_FROM_EMAIL must be set in production.')

ALLOW_SQLITE_IN_PRODUCTION = base._bool_env('ALLOW_SQLITE_IN_PRODUCTION', default=False)
if not ALLOW_SQLITE_IN_PRODUCTION:
    db_engine = DATABASES.get('default', {}).get('ENGINE', '')
    if db_engine != 'django.db.backends.postgresql':
        raise ImproperlyConfigured(
            'Production requires PostgreSQL. Set DATABASE_URL=postgresql://... '
            'or explicitly set ALLOW_SQLITE_IN_PRODUCTION=true for temporary emergency use.'
        )

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = base._bool_env('SECURE_SSL_REDIRECT', default=True)
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '3600'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = base._bool_env('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
SECURE_HSTS_PRELOAD = base._bool_env('SECURE_HSTS_PRELOAD', default=True)
SECURE_REFERRER_POLICY = os.getenv('SECURE_REFERRER_POLICY', 'same-origin')
