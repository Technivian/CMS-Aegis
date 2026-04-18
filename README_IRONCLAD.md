
# CMS Aegis

CMS Aegis is a Django-based contract and legal operations platform with multi-tenant organization support, role-based access control, reminders, audit logging, and a tested redesign layer.

## Current State

- Backend: Django 5.2.5
- Database: SQLite in development
- Auth routes: `/login/`, `/register/`, `/logout/`
- App shell: dashboard + contract-centric SaaS UI with light/dark theme support
- Dev server: `127.0.0.1:8000` or `0.0.0.0:8000`

## Core Capabilities

- Contract repository with create, detail, update, notes, AI assistant, deadlines, documents, workflows, risks, legal tasks, compliance checklists, and reporting
- Multi-tenant organization model using `Organization` and `OrganizationMembership`
- Organization team management: invites, role changes, deactivation/reactivation, activity log, CSV export
- Internal reminder system for contract renewals and expirations
- Internal AI assistant endpoint scoped to contract organization membership
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

SAML support:

- Install dependency: `python3-saml`
- Enable the SAML flow with `SAML_ENABLED=true`
- Configure each organization in the Identity Provider settings page; the login screen includes a SAML organization selector.

Operational takeover guide:

- `docs/TAKEOVER_30_60_90_PLAN.md`

## RBAC Model

Permission policy lives in `contracts/permissions.py`.

Organization roles:

- `OWNER`
- `ADMIN`
- `MEMBER`

Contract actions:

- `VIEW`, `COMMENT`, `AI`: allowed for any active member of the contract's organization
- `EDIT`: allowed for organization owners/admins, plus the contract creator

The centralized policy entry point is `can_access_contract_action(user, contract, action)`.

## Feature Flags

- `IRONCLAD_MODE = False` by default in `config/settings.py`
- `FEATURE_REDESIGN` is used by the redesign tests and UI paths

The redesign and contract list/dashboard markers are covered by the test suite and should be treated as part of the supported UI surface.

## Running Locally

Runtime target:

- Python `3.12.x` (aligned with CI/staging)

Bootstrap local runtime and venv:

```bash
bash scripts/bootstrap_python312.sh
```

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Environment defaults now come from `DJANGO_ENV`:

- `development`: uses [`config/settings_development.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_development.py)
- `production`: uses [`config/settings_production.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_production.py)
- shared base: [`config/settings_base.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_base.py)

Recommended local `.env` values are in [`.env.example`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/.env.example).

## Production Environment Contract

Required in production:

- `DJANGO_ENV=production`
- `DJANGO_SECRET_KEY`
- `DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<db>`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DEFAULT_FROM_EMAIL`

Recommended in production:

- `DJANGO_LOG_LEVEL=INFO`
- `SERVER_EMAIL`
- `DB_CONN_MAX_AGE=60`
- `DB_SSL_REQUIRE=true` (or use `?sslmode=require` in `DATABASE_URL`)
- `SECURE_SSL_REDIRECT=true`
- `SECURE_HSTS_PRELOAD=true`
- `SSO_ENABLED` and the relevant OIDC variables if SSO is in use

Optional local scratch-db override for migration drills:

- `SQLITE_PATH=/tmp/cms-aegis-drill.sqlite3`

Minimum production verification sequence:

```bash
.venv/bin/python manage.py check --deploy --fail-level WARNING
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py audit_null_organizations
.venv/bin/python manage.py test tests.test_cross_tenant_isolation -v 1
```

Quick config sanity check for production DB engine:

```bash
DJANGO_ENV=production \
DJANGO_SECRET_KEY=tmp \
ALLOWED_HOSTS=example.com \
CSRF_TRUSTED_ORIGINS=https://example.com \
DEFAULT_FROM_EMAIL=ops@example.com \
DATABASE_URL=postgresql://user:pass@localhost:5432/cms_aegis \
.venv/bin/python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
```

## Logging

Request logging now includes:

- `request_id`
- `user_id`
- `org_id`
- `path`

Each response also includes an `X-Request-ID` header. Local development logs go to stdout using the structured formatter in [`config/settings_base.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/settings_base.py). Production should ship the same stdout stream to the platform log collector and keep `DJANGO_LOG_LEVEL=INFO` unless active debugging is required.

Or run the dev server and reminder scheduler together:

```bash
bash scripts/dev_up.sh
bash scripts/dev_up.sh 15
bash scripts/dev_down.sh
```

## Seed Data

Optional development seed data:

```bash
.venv/bin/python manage.py seed_data
```

Starter catalog content is now tenant-owned. For existing organizations, promote starter content and clean up legacy global rows with:

```bash
.venv/bin/python manage.py promote_starter_content --cleanup-global
.venv/bin/python manage.py audit_null_organizations
```

For staging and pre-release validation, use the manual two-organization smoke checklist in
[`docs/MANUAL_SMOKE_CHECKLIST.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MANUAL_SMOKE_CHECKLIST.md).

That command creates demo users, including:

- `admin` / `admin123`
- `jsmith` / `password123`
- `sjones` / `password123`
- `mwilson` / `password123`

If you do not run `seed_data`, create your own user with:

```bash
.venv/bin/python manage.py createsuperuser
```

## Reminder Commands

One-off reminder generation:

```bash
.venv/bin/python manage.py send_contract_reminders
```

Long-running scheduler:

```bash
.venv/bin/python manage.py run_reminder_scheduler
.venv/bin/python manage.py run_reminder_scheduler --interval-minutes 15
.venv/bin/python manage.py run_reminder_scheduler --once
```

Reminder recipients currently include the contract creator, responsible attorneys where present, and active organization owners/admins. Notifications are deduplicated per day.

## Tests

Run the full validated suite:

```bash
.venv/bin/python manage.py test contracts tests -v 1
```

As of the latest validation pass:

- `151` tests pass
- `manage.py check` is clean

## Canonical Docs

- `README_IRONCLAD.md`: current operational overview
- `DECISIONS.md`: implemented architectural and product decisions
- `docs/OBSERVABILITY_BOOTSTRAP.md`: SLO, dashboard, and alert bootstrap
- `docs/STAGING_POSTGRES_REHEARSAL.md`: exact `ICL-002` staging runbook and evidence template

Old Replit-era handover notes and duplicate decision logs have been removed to keep the docs aligned with the codebase.
