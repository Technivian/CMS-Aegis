# Azure Entra SSO Setup (OIDC)

This project supports OIDC SSO via `mozilla-django-oidc`.

## 1. Register app in Azure Entra ID

1. Go to Azure Portal -> Entra ID -> App registrations -> New registration.
2. Name: `CMS Aegis`.
3. Supported account types: choose what you need (single-tenant is typical).
4. Redirect URI (Web):
   - `http://127.0.0.1:8060/oidc/callback/` (local dev)
   - Add your production callback URL later.

## 2. Create client secret

1. App registration -> Certificates & secrets -> New client secret.
2. Copy the secret value.

## 3. Gather values

- `TENANT_ID` (Directory/tenant ID)
- `CLIENT_ID` (Application/client ID)
- `CLIENT_SECRET` (secret value)

## 4. Configure environment

Set these before running Django:

```bash
export SSO_ENABLED=true
export OIDC_RP_CLIENT_ID="<CLIENT_ID>"
export OIDC_RP_CLIENT_SECRET="<CLIENT_SECRET>"
export OIDC_OP_DISCOVERY_ENDPOINT="https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration"
export OIDC_RP_SCOPES="openid email profile"
```

Optional:

```bash
export OIDC_VERIFY_SSL=true
```

## 5. Install dependency and run

```bash
.venv/bin/pip install mozilla-django-oidc
.venv/bin/python manage.py runserver 127.0.0.1:8060
```

## 6. Test

- Open `/login/`
- Click **Sign in with SSO**

## Notes

- Password login remains available as fallback.
- Users are matched by email and auto-provisioned if they do not exist.
- If you use multi-tenant Azure setup, ensure your app registration allows the selected account type.
