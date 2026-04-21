# CMS Aegis

CMS Aegis is a Django-based contract lifecycle management platform with multi-tenant organization support, role-based access control, reminders, audit logging, and a tested UI layer.

## Current State

- Backend: Django 5.2.5
- Database: SQLite in development
- Auth routes: `/login/`, `/register/`, `/logout/`
- App shell: dashboard + CLM SaaS UI with light/dark theme support
- Dev server: `127.0.0.1:8060` or `0.0.0.0:8060`

## Local HTTPS (Chrome/Safari)

Use the helper script to generate/refresh local certificates, trust the local CA in your login keychain, and run Django over HTTPS.

```bash
scripts/dev_https.sh up
```

Open:

```text
https://127.0.0.1:8060/
```

Useful commands:

```bash
scripts/dev_https.sh up --background
scripts/dev_https.sh down
```

## Core Capabilities

- Contract management with create, detail, update, notes, AI assistant, deadlines, documents, tasks, and reporting
- Multi-tenant organization model using `Organization` and `OrganizationMembership`
- Organization team management: invites, role changes, deactivation/reactivation, activity log, CSV export
- Internal reminder system for matter deadlines and follow-ups
- Internal AI assistant endpoint scoped to organization membership
- Audit logging across key actions
- Optional enterprise SSO via OpenID Connect (OIDC)

## SSO (OIDC)

CMS Aegis supports optional SSO using OIDC (for example: Azure AD / Entra ID, Okta, Auth0, Keycloak).

Install dependency:

```bash
.venv/bin/pip install mozilla-django-oidc
```

Set environment variables before starting Django:

```bash
export SSO_ENABLED=true
export OIDC_RP_CLIENT_ID="your-client-id"
export OIDC_RP_CLIENT_SECRET="your-client-secret"
export OIDC_OP_AUTHORIZATION_ENDPOINT="https://issuer.example.com/oauth2/v1/authorize"
export OIDC_OP_TOKEN_ENDPOINT="https://issuer.example.com/oauth2/v1/token"
export OIDC_OP_USER_ENDPOINT="https://issuer.example.com/oauth2/v1/userinfo"
export OIDC_OP_JWKS_ENDPOINT="https://issuer.example.com/oauth2/v1/keys"
```

Optional:

```bash
export OIDC_OP_LOGOUT_ENDPOINT="https://issuer.example.com/logout"
export OIDC_RP_SCOPES="openid email profile"
export OIDC_VERIFY_SSL=true
export SSO_ALLOWED_EMAIL_DOMAINS="yourcompany.com"
```

Azure Entra quick setup (recommended):

```bash
export SSO_ENABLED=true
export OIDC_RP_CLIENT_ID="<CLIENT_ID>"
export OIDC_RP_CLIENT_SECRET="<CLIENT_SECRET>"
export OIDC_OP_DISCOVERY_ENDPOINT="https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration"
```

Google quick setup:

```bash
export SSO_ENABLED=true
export OIDC_RP_CLIENT_ID="<GOOGLE_CLIENT_ID>"
export OIDC_RP_CLIENT_SECRET="<GOOGLE_CLIENT_SECRET>"
export OIDC_OP_DISCOVERY_ENDPOINT="https://accounts.google.com/.well-known/openid-configuration"
```

Behavior:

- Password login remains available.
- When `SSO_ENABLED=true`, the login page shows a **Sign in with SSO** button.
- Users are matched by email. If no user exists, one is provisioned automatically.

Detailed provider guide:

- `docs/SSO_AZURE_SETUP.md`
- `docs/SSO_GOOGLE_SETUP.md`

Operational takeover guide:

- `docs/TAKEOVER_30_60_90_PLAN.md`

## RBAC Model

Permission policy lives in `contracts/permissions.py`.

Organization roles:

- `OWNER`
- `ADMIN`
- `MEMBER`

Matter actions:

- `VIEW`, `COMMENT`, `AI`: allowed for any active member of the matter's organization
- `EDIT`: restricted to `OWNER` and `ADMIN` roles, or the matter creator
