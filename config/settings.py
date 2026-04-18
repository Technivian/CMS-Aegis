import os


DJANGO_ENV = os.getenv('DJANGO_ENV', 'development').strip().lower()

if DJANGO_ENV == 'production':
    from .settings_production import *  # noqa: F401,F403
else:
    from .settings_development import *  # noqa: F401,F403
