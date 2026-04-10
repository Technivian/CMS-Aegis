import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _csv_env(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(default or [])
    return [item.strip() for item in raw.split(',') if item.strip()]


_load_dotenv(BASE_DIR / '.env')

DJANGO_ENV = os.getenv('DJANGO_ENV', 'development').strip().lower()

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY and DJANGO_ENV == 'production':
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set in production.')
if not SECRET_KEY:
    SECRET_KEY = 'django-insecure-dev-only-key-change-me'

ALLOWED_HOSTS = _csv_env('ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = _csv_env('CSRF_TRUSTED_ORIGINS')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'theme',
    'contracts',
]

SSO_ENABLED = _bool_env('SSO_ENABLED', default=False)

try:
    import mozilla_django_oidc  # noqa: F401
    OIDC_PACKAGE_AVAILABLE = True
except Exception:
    OIDC_PACKAGE_AVAILABLE = False

if OIDC_PACKAGE_AVAILABLE:
    INSTALLED_APPS.append('mozilla_django_oidc')

if SSO_ENABLED and not OIDC_PACKAGE_AVAILABLE:
    raise ImportError(
        'SSO_ENABLED is true but mozilla-django-oidc is not installed. '
        'Install it with: pip install mozilla-django-oidc'
    )

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'contracts.middleware.OrganizationMiddleware',
    'contracts.middleware.RequestContextMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'theme/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'contracts.context_processors.feature_flags',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.getenv('SQLITE_PATH', str(BASE_DIR / 'db.sqlite3')),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'theme' / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

IRONCLAD_MODE = False

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend']
if SSO_ENABLED:
    AUTHENTICATION_BACKENDS.insert(0, 'contracts.auth_backends.AegisOIDCAuthenticationBackend')

OIDC_RP_CLIENT_ID = os.getenv('OIDC_RP_CLIENT_ID', '')
OIDC_RP_CLIENT_SECRET = os.getenv('OIDC_RP_CLIENT_SECRET', '')
OIDC_RP_SIGN_ALGO = os.getenv('OIDC_RP_SIGN_ALGO', 'RS256')
OIDC_RP_SCOPES = os.getenv('OIDC_RP_SCOPES', 'openid email profile')
SSO_ALLOWED_EMAIL_DOMAINS = [d.strip().lower() for d in os.getenv('SSO_ALLOWED_EMAIL_DOMAINS', '').split(',') if d.strip()]
OIDC_OP_AUTHORIZATION_ENDPOINT = os.getenv('OIDC_OP_AUTHORIZATION_ENDPOINT', '')
OIDC_OP_TOKEN_ENDPOINT = os.getenv('OIDC_OP_TOKEN_ENDPOINT', '')
OIDC_OP_USER_ENDPOINT = os.getenv('OIDC_OP_USER_ENDPOINT', '')
OIDC_OP_JWKS_ENDPOINT = os.getenv('OIDC_OP_JWKS_ENDPOINT', '')
OIDC_OP_LOGOUT_ENDPOINT = os.getenv('OIDC_OP_LOGOUT_ENDPOINT', '')
OIDC_OP_DISCOVERY_ENDPOINT = os.getenv('OIDC_OP_DISCOVERY_ENDPOINT', '')
OIDC_USE_NONCE = True
OIDC_STORE_ACCESS_TOKEN = False
OIDC_VERIFY_SSL = _bool_env('OIDC_VERIFY_SSL', default=True)

if SSO_ENABLED:
    has_discovery = bool(OIDC_OP_DISCOVERY_ENDPOINT)
    has_explicit_endpoints = all([
        OIDC_OP_AUTHORIZATION_ENDPOINT,
        OIDC_OP_TOKEN_ENDPOINT,
        OIDC_OP_USER_ENDPOINT,
        OIDC_OP_JWKS_ENDPOINT,
    ])
    if not (OIDC_RP_CLIENT_ID and OIDC_RP_CLIENT_SECRET and (has_discovery or has_explicit_endpoints)):
        raise ImportError(
            'SSO_ENABLED is true but required OIDC settings are missing. '
            'Set OIDC_RP_CLIENT_ID and OIDC_RP_CLIENT_SECRET, plus either '
            'OIDC_OP_DISCOVERY_ENDPOINT or all explicit endpoints '
            '(OIDC_OP_AUTHORIZATION_ENDPOINT, OIDC_OP_TOKEN_ENDPOINT, '
            'OIDC_OP_USER_ENDPOINT, OIDC_OP_JWKS_ENDPOINT).'
        )

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

INTERNAL_IPS = _csv_env('INTERNAL_IPS', default=['127.0.0.1'])

DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@cms-aegis.local')
SERVER_EMAIL = os.getenv('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
DJANGO_LOG_LEVEL = os.getenv('DJANGO_LOG_LEVEL', 'INFO').upper()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'request_context': {
            '()': 'contracts.logging_context.RequestContextLogFilter',
        },
    },
    'formatters': {
        'structured': {
            'format': (
                '%(asctime)s %(levelname)s %(name)s '
                'request_id=%(request_id)s user_id=%(request_user_id)s '
                'org_id=%(request_org_id)s path=%(request_path)s %(message)s'
            ),
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['request_context'],
            'formatter': 'structured',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': DJANGO_LOG_LEVEL,
    },
}
