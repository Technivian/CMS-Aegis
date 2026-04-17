import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

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
SAML_ENABLED = _bool_env('SAML_ENABLED', default=False)

try:
    import mozilla_django_oidc  # noqa: F401
    OIDC_PACKAGE_AVAILABLE = True
except Exception:
    OIDC_PACKAGE_AVAILABLE = False

try:
    import onelogin  # noqa: F401
    SAML_PACKAGE_AVAILABLE = True
except Exception:
    SAML_PACKAGE_AVAILABLE = False

if OIDC_PACKAGE_AVAILABLE:
    INSTALLED_APPS.append('mozilla_django_oidc')

if SSO_ENABLED and not OIDC_PACKAGE_AVAILABLE:
    raise ImportError(
        'SSO_ENABLED is true but mozilla-django-oidc is not installed. '
        'Install it with: pip install mozilla-django-oidc'
    )

if SAML_ENABLED and not SAML_PACKAGE_AVAILABLE:
    raise ImportError(
        'SAML_ENABLED is true but python3-saml is not installed. '
        'Install it with: pip install python3-saml'
    )

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'contracts.middleware.AuthRateLimitMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'contracts.middleware.SessionSecurityMiddleware',
    'contracts.middleware.OrganizationMiddleware',
    'contracts.middleware.RequestContextMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'contracts.middleware.SecurityHeadersMiddleware',
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

def _database_config_from_env() -> dict:
    database_url = os.getenv('DATABASE_URL', '').strip()
    if not database_url:
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('SQLITE_PATH', str(BASE_DIR / 'db.sqlite3')),
        }

    parsed = urlparse(database_url)
    scheme = (parsed.scheme or '').lower()
    query_options = dict(parse_qsl(parsed.query, keep_blank_values=True))

    if scheme in {'postgres', 'postgresql'}:
        engine = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
        config = {
            'ENGINE': engine,
            'NAME': unquote(parsed.path.lstrip('/')) if parsed.path else '',
            'USER': unquote(parsed.username) if parsed.username else '',
            'PASSWORD': unquote(parsed.password) if parsed.password else '',
            'HOST': parsed.hostname or '',
            'PORT': str(parsed.port) if parsed.port else '',
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', os.getenv('CMS_DB_CONN_MAX_AGE', '60'))),
        }
        ssl_require = _bool_env('DB_SSL_REQUIRE', _bool_env('CMS_DB_SSL_REQUIRE', default=False))
        if ssl_require:
            config['OPTIONS'] = {'sslmode': 'require'}
        if 'sslmode' in query_options:
            config.setdefault('OPTIONS', {})
            config['OPTIONS']['sslmode'] = query_options['sslmode']
        return config

    if scheme == 'sqlite':
        if parsed.path in {'', '/'}:
            sqlite_name = os.getenv('SQLITE_PATH', str(BASE_DIR / 'db.sqlite3'))
        else:
            sqlite_name = unquote(parsed.path)
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': sqlite_name,
        }

    raise ImproperlyConfigured(
        'Unsupported DATABASE_URL scheme. Use postgresql://... for production or sqlite:///... for local.'
    )


DATABASES = {'default': _database_config_from_env()}

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

# Keep default CSRF cookie name for browser compatibility with form posts.
SESSION_COOKIE_NAME = os.getenv('SESSION_COOKIE_NAME', 'cms_aegis_sessionid')
CSRF_COOKIE_NAME = os.getenv('CSRF_COOKIE_NAME', 'csrftoken')
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv('SESSION_IDLE_TIMEOUT_MINUTES', '120'))

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

SAML_SP_ENTITY_ID = os.getenv('SAML_SP_ENTITY_ID', '')
SAML_SP_X509_CERT = os.getenv('SAML_SP_X509_CERT', '')
SAML_SP_PRIVATE_KEY = os.getenv('SAML_SP_PRIVATE_KEY', '')
SAML_STRICT = _bool_env('SAML_STRICT', default=True)

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

RATELIMIT_ENABLED = _bool_env('RATELIMIT_ENABLED', default=True)
RATELIMIT_PATHS = ('/login/', '/register/')
RATELIMIT_TRUSTED_IPS = tuple(_csv_env('RATELIMIT_TRUSTED_IPS'))
LOGIN_RATE_LIMIT_REQUESTS = int(os.getenv('LOGIN_RATE_LIMIT_REQUESTS', '10'))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv('LOGIN_RATE_LIMIT_WINDOW_SECONDS', '300'))
REGISTER_RATE_LIMIT_REQUESTS = int(os.getenv('REGISTER_RATE_LIMIT_REQUESTS', '10'))
REGISTER_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv('REGISTER_RATE_LIMIT_WINDOW_SECONDS', '300'))

SECURITY_HEADERS_ENABLED = _bool_env('SECURITY_HEADERS_ENABLED', default=True)
CONTENT_SECURITY_POLICY = os.getenv(
    'CONTENT_SECURITY_POLICY',
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
PERMISSIONS_POLICY = os.getenv('PERMISSIONS_POLICY', 'geolocation=(), microphone=(), camera=()')
REMINDER_SCHEDULER_EXPECTED_INTERVAL_MINUTES = int(os.getenv('REMINDER_SCHEDULER_EXPECTED_INTERVAL_MINUTES', '60'))
REMINDER_SCHEDULER_STALE_MULTIPLIER = int(os.getenv('REMINDER_SCHEDULER_STALE_MULTIPLIER', '2'))
REQUEST_METRICS_ENABLED = _bool_env('REQUEST_METRICS_ENABLED', default=True)
HEALTH_DB_LATENCY_WARN_MS = int(os.getenv('HEALTH_DB_LATENCY_WARN_MS', '250'))
HEALTH_DB_LATENCY_FAIL_MS = int(os.getenv('HEALTH_DB_LATENCY_FAIL_MS', '1500'))
SLO_API_P95_MS = int(os.getenv('SLO_API_P95_MS', '500'))
SLO_5XX_RATE_WARN_PCT = float(os.getenv('SLO_5XX_RATE_WARN_PCT', '0.8'))
SLO_5XX_RATE_FAIL_PCT = float(os.getenv('SLO_5XX_RATE_FAIL_PCT', '2.0'))

SALESFORCE_CLIENT_ID = os.getenv('SALESFORCE_CLIENT_ID', '').strip()
SALESFORCE_CLIENT_SECRET = os.getenv('SALESFORCE_CLIENT_SECRET', '').strip()
SALESFORCE_AUTHORIZATION_URL = os.getenv(
    'SALESFORCE_AUTHORIZATION_URL',
    'https://login.salesforce.com/services/oauth2/authorize',
).strip()
SALESFORCE_TOKEN_URL = os.getenv(
    'SALESFORCE_TOKEN_URL',
    'https://login.salesforce.com/services/oauth2/token',
).strip()
SALESFORCE_REDIRECT_URI = os.getenv('SALESFORCE_REDIRECT_URI', '').strip()
SALESFORCE_SCOPES = os.getenv('SALESFORCE_SCOPES', 'api refresh_token offline_access').strip()
SALESFORCE_TOKEN_ENCRYPTION_SALT = os.getenv('SALESFORCE_TOKEN_ENCRYPTION_SALT', 'salesforce-tokens-v1').strip()
SALESFORCE_API_VERSION = os.getenv('SALESFORCE_API_VERSION', '61.0').strip()
SALESFORCE_SYNC_DEFAULT_LIMIT = int(os.getenv('SALESFORCE_SYNC_DEFAULT_LIMIT', '200'))

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
