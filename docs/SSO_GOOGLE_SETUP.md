# Google SSO Setup (OIDC)

This project supports Google SSO via OIDC using `mozilla-django-oidc`.

## 1. Google Cloud setup

1. Create/select a project in Google Cloud Console.
2. Configure OAuth consent screen.
3. Create OAuth 2.0 Client ID (Web application).
4. Add Authorized redirect URI:
   - `http://127.0.0.1:8060/oidc/callback/`
   - Add production callback URL when ready.

## 2. Configure environment

Set these before starting Django:

```bash
export SSO_ENABLED=true
export OIDC_RP_CLIENT_ID="<GOOGLE_CLIENT_ID>"
export OIDC_RP_CLIENT_SECRET="<GOOGLE_CLIENT_SECRET>"
export OIDC_OP_DISCOVERY_ENDPOINT="https://accounts.google.com/.well-known/openid-configuration"
export OIDC_RP_SCOPES="openid email profile"
```

Optional restrictions:

```bash
# Comma-separated list. If set, only these email domains can sign in via SSO.
export SSO_ALLOWED_EMAIL_DOMAINS="yourcompany.com"
```

## 3. Install dependency and run

```bash
.venv/bin/pip install mozilla-django-oidc
.venv/bin/python manage.py runserver 127.0.0.1:8060
```

## 4. Test

- Open `/login/`
- Click **Sign in with SSO**

## Notes

- Password login remains available.
- Users are matched by email and auto-provisioned if they do not exist.
- If `SSO_ALLOWED_EMAIL_DOMAINS` is configured, Google users outside those domains are denied.
