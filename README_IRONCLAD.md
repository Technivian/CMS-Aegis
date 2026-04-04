
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
```

Azure Entra quick setup (recommended):

```bash
export SSO_ENABLED=true
export OIDC_RP_CLIENT_ID="<CLIENT_ID>"
export OIDC_RP_CLIENT_SECRET="<CLIENT_SECRET>"
export OIDC_OP_DISCOVERY_ENDPOINT="https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration"
```

Behavior:

- Password login remains available.
- When `SSO_ENABLED=true`, the login page shows a **Sign in with SSO** button.
- Users are matched by email. If no user exists, one is provisioned automatically.

Detailed provider guide:

- `docs/SSO_AZURE_SETUP.md`

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

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

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

- `76` tests pass
- `manage.py check` is clean

## Canonical Docs

- `README_IRONCLAD.md`: current operational overview
- `DECISIONS.md`: implemented architectural and product decisions

Old Replit-era handover notes and duplicate decision logs have been removed to keep the docs aligned with the codebase.
