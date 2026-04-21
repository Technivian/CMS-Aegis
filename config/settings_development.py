from . import settings_base as base
from .settings_base import *  # noqa: F401,F403


DEBUG = base._bool_env('DJANGO_DEBUG', default=True)

if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0', 'testserver']

CSRF_TRUSTED_ORIGINS.extend([
    'https://*.replit.dev',
    'https://*.repl.co',
    'https://*.riker.replit.dev',
    'https://*.riker.replit.dev:8060',
])

INSTALLED_APPS.extend([
    'django_browser_reload',
    'debug_toolbar',
])
MIDDLEWARE.insert(1, 'debug_toolbar.middleware.DebugToolbarMiddleware')
MIDDLEWARE.append('django_browser_reload.middleware.BrowserReloadMiddleware')

STORAGES = {
    **STORAGES,
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
