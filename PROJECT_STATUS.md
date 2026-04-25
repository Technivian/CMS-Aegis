# CMS Aegis Project Status

Last updated: 2026-04-25

Current checkout: `main` at `0262a2a` (`Automate release evidence bundle`)

## Executive Snapshot

CMS Aegis is a multi-tenant Django CLM / legal operations platform with contract lifecycle management, workflow routing, clause governance, privacy/compliance tooling, e-signature handling, search, reporting, and a broad set of admin/integration surfaces.

The app is **demo-ready** and **internally MVP-ready** for a CLM pilot. The current checkout can be taken to a `GO` release-gate state by running the synthetic Sprint 3 evidence seed + release evidence bundle command. The remaining production gap is live integration proof and rollback / restore evidence, not basic code correctness.

## What The App Is For

### Main user roles

- Org owner / admin
- Legal ops / contract manager
- Reviewer / approver
- Privacy / compliance operator
- External signer
- Integration operator / system admin

### Main business flows

- Register / log in / switch organization
- Create and manage contracts
- Draft from clause templates and playbooks
- Route work through workflows and approvals
- Send and reconcile signature requests
- Track privacy/compliance records and deadlines
- Search, save views, and export reports
- Sync from Salesforce / NetSuite and receive webhooks
- Monitor operations and release evidence

### Core modules

- Identity, tenancy, and session security
- Contracts, documents, clients, matters, counterparties
- Clause library, playbooks, variants, and versioning
- Workflow templates, workflow execution, approvals, and reminders
- Signature requests and e-sign reconciliation
- Privacy/GDPR records, DSAR, retention, subprocessors, transfers
- Search, repository, saved searches, and semantic ranking
- Reporting, dashboards, exports, and operational evidence
- Salesforce, NetSuite, SCIM, SAML, and webhook integrations
- AI assistant and AI action planning

## System Map

### Routes and pages

The route surface is large. The two route registries are:

- [`config/urls.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/config/urls.py)
- [`contracts/urls.py`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/contracts/urls.py)

Key route families:

- Public / auth:
  - `/`
  - `/login/`
  - `/register/`
  - `/logout/`
  - `/dashboard/`
  - `/profile/`
  - `/settings/*`
  - `/operations/`
- Identity:
  - `/saml/*`
  - `/oidc/*`
  - `/scim/v2/*`
- Contracts core:
  - `/contracts/`
  - `/contracts/new/`
  - `/contracts/<id>/`
  - `/contracts/<id>/edit/`
  - `/contracts/search/`
  - `/contracts/repository/`
  - `/contracts/notifications/`
- Repository and drafting:
  - `/contracts/clients/*`
  - `/contracts/matters/*`
  - `/contracts/documents/*`
  - `/contracts/clause-categories/*`
  - `/contracts/clause-library/*`
  - `/contracts/counterparties/*`
- Workflow / approvals / signatures:
  - `/contracts/workflows/*`
  - `/contracts/templates/*`
  - `/contracts/approval-rules/*`
  - `/contracts/approvals/*`
  - `/contracts/signatures/*`
- Privacy / compliance:
  - `/contracts/privacy/*`
  - `/contracts/due-diligence/*`
  - `/contracts/legal-tasks/*`
  - `/contracts/trademarks/*`
  - `/contracts/risks/*`
  - `/contracts/compliance/*`
  - `/contracts/budgets/*`
  - `/contracts/deadlines/*`
- APIs:
  - SCIM users / groups
  - contracts API v1 and legacy contracts API
  - Salesforce status / OAuth / field map / sync / sync runs
  - NetSuite sync
  - webhook deliveries
  - e-sign webhook
  - executive analytics / dashboard presets

### Major frontend templates

Templates are primarily server-rendered and live under:

- [`theme/templates/base.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/base.html)
- [`theme/templates/base_fullscreen.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/base_fullscreen.html)
- [`theme/templates/base_redesign.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/base_redesign.html)
- [`theme/templates/dashboard.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/dashboard.html)
- [`theme/templates/landing.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/landing.html)
- [`theme/templates/registration/login.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/registration/login.html)
- [`theme/templates/registration/register.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/registration/register.html)
- [`theme/templates/profile.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/profile.html)
- [`theme/templates/settings_hub.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/settings_hub.html)
- `theme/templates/contracts/*` for the business modules
- [`theme/templates/styleguide.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/styleguide.html)
- [`theme/templates/components_demo.html`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/theme/templates/components_demo.html)

### Backend apps and modules

The codebase is centered on the `contracts` Django app:

- `contracts/models.py`
- `contracts/forms.py`
- `contracts/permissions.py`
- `contracts/middleware.py`
- `contracts/api/views.py`
- `contracts/views.py`
- `contracts/views_domains/*`
- `contracts/services/*`
- `contracts/management/commands/*`
- `contracts/domain/*`
- `config/settings_base.py`
- `config/urls.py`

### Database entities

The main persisted models are:

- Organization / membership / invitation / user profile
- SCIM groups and API tokens
- Salesforce connection / field map / sync run
- Webhook endpoint / delivery
- Executive dashboard preset / search preset
- Client / matter / contract / document / OCR review
- Time entry / invoice / trust account / trust transaction
- Deadline / audit log / notification
- Conflict check / trademark request / legal task / tag / risk log
- Compliance checklist / checklist item
- Workflow template / workflow template step / workflow / workflow step
- Due diligence process / task / risk
- Budget / budget expense
- Negotiation thread
- Counterparty
- Clause category / clause template / clause playbook / clause variant
- Ethical wall
- Signature request
- Data inventory / DSAR / subprocessor / transfer record / retention policy / legal hold
- Approval rule / approval request
- Background job

### APIs and integrations

The app currently includes:

- SCIM provisioning APIs
- SAML login / ACS / logout / metadata
- Salesforce OAuth, status, sync, and sync-run APIs
- NetSuite sync API / command
- E-sign webhook reconciliation API
- Webhook delivery APIs
- Executive analytics APIs
- API v1 contract endpoints
- Legacy contract APIs
- AI assistant contract endpoint
- Background job and evidence bundle commands

## What Works

- Tenant-scoped login / register / logout flows
- Dashboard and main navigation
- Contract create / edit / list / detail
- Clause library create / edit / compare / version history
- Workflow templates and workflow execution
- Signature requests and transition guardrails
- Privacy/compliance pages and records
- Search, semantic search, and saved search presets
- Reporting / executive dashboards / exports
- Client, matter, document, billing, trust, risk, compliance, due diligence, trademark, and ethical wall flows
- Focused Django test suites pass locally
- `manage.py check` passes
- `manage.py migrate --noinput` passes on the current checkout
- `manage.py audit_null_organizations` passes after migrations
- `manage.py generate_release_evidence_bundle` generates a full release evidence pack and reports `GO` when Sprint 3 evidence is seeded

## What Is Partial

- SAML and SCIM are implemented, but external IdP / lifecycle proof is still a deployment concern
- Salesforce, NetSuite, and e-sign integrations exist, but live end-to-end evidence is still the real gate
- Some UI shells and demo templates are still experimental
- Some features are strong enough for internal use but still need enterprise polish and production hardening

## What Is Broken Or Missing

- The repo currently has a moderate `postcss` vulnerability reported by `npm audit`
- `theme/templates/contracts/templates_list.html` still contains placeholder TODO actions for edit/use-template behavior
- `contracts/services/repository.py` still retains a mock service path and abstract interface
- Production proof is not complete without a backup / restore rehearsal and real live cutover evidence
- Live Salesforce / webhook evidence from the target environment is still needed for true rollout confidence

## Current Risks

- Large, high-complexity modules are still easy to regress
- Integrations depend on external systems and live credentials
- Release confidence depends on evidence, not just code passing locally
- The UI contains some experimental/demonstration shells that can confuse scope
- Frontend dependency audit has a moderate PostCSS issue

## Recommendation

Treat the app as:

- **Demo-ready:** yes
- **Internal MVP-ready:** yes, with scope discipline
- **Production-ready:** not yet for a live rollout, because production cutover proof and live integration evidence are still missing

## Next Recommended Actions

1. Capture live Salesforce sync evidence in the target org.
2. Capture webhook delivery evidence from a real endpoint.
3. Finish the backup / restore rehearsal on the real database target.
4. Remove or resolve the remaining frontend TODO actions.
5. Address the moderate PostCSS advisory.
6. Consolidate experimental UI shells and demo templates.
7. Keep release evidence bundle commands attached to the release workflow.
8. Add stronger live E2E coverage for the major user flows.
