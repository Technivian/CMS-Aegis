# CMS Aegis QA Checklist

Last updated: 2026-04-25

## Smoke Test Checklist

- [ ] Open `/` and confirm the CMS Aegis landing page renders.
- [ ] Open `/register/` and create a fresh user.
- [ ] Log in with the new user.
- [ ] Confirm `/dashboard/` renders and stays authenticated.
- [ ] Create a new contract.
- [ ] Edit the contract and verify the save persists.
- [ ] Open `/contracts/search/` and run a search.
- [ ] Open `/contracts/workflows/` and verify workflow pages load.
- [ ] Open `/contracts/privacy/` and verify privacy dashboards load.
- [ ] Open `/contracts/repository/` and verify the repository list loads.
- [ ] Open `/contracts/reports/` and verify the analytics dashboard loads.
- [ ] Log out and confirm the public homepage returns.
- [ ] Confirm `/dashboard/` redirects to `/login/?next=/dashboard/` when logged out.
- [ ] Confirm `/admin/` redirects to admin login.
- [ ] Confirm `/documents/` returns `404`.

## Regression Checklist

- [ ] Tenant isolation: Org A data is not visible in Org B.
- [ ] Role checks: member / admin / owner behavior matches the permission matrix.
- [ ] Workflow execution: materialization, completion, escalation, and reminder behavior.
- [ ] Clause library: create, version, compare, playbook, and variant flows.
- [ ] Document versioning: compare and OCR review behavior.
- [ ] Signature request transitions: sent / viewed / signed / declined / expired / cancelled.
- [ ] Approval requests: create, transition, and actor authorization.
- [ ] Search presets: save, load, delete, and scoped filtering.
- [ ] Privacy records: DSAR, subprocessor, transfer, retention, and legal hold flows.
- [ ] Salesforce sync: status, ingest preview, sync, and sync-run history.
- [ ] NetSuite sync: ingest and dry-run behavior.
- [ ] Webhook delivery: queue, retry, and dead-letter handling.
- [ ] Release gate: database, integrations, and security checks.

## Automated Check Checklist

### Django

- [ ] `./.venv/bin/python manage.py check`
- [ ] `./.venv/bin/python manage.py migrate --noinput`
- [ ] `./.venv/bin/python manage.py audit_null_organizations`
- [ ] `./.venv/bin/python manage.py generate_release_gate_report --fail-on-no-go`
- [ ] Run focused regression suites relevant to the change

### Frontend / Node

- [ ] `npm --prefix client audit --audit-level=high`
- [ ] `npm --prefix theme/static_src audit --audit-level=high`
- [ ] `npm --prefix client run test:e2e` with a known-good test user

### Focused Python Suites

- [ ] `tests.test_cross_tenant_isolation`
- [ ] `tests.test_workflow_execution`
- [ ] `tests.test_workflow_transition_guardrails`
- [ ] `tests.test_api_versions_clauses_operations_search`
- [ ] `tests.test_contract_required_fields`
- [ ] `tests.test_release_gate_report`
- [ ] `tests.test_sprint3_integration_report`
- [ ] `tests.test_observability_guardrails`
- [ ] `tests.test_retention_jobs`
- [ ] `tests.test_performance_guardrails`

## Manual Browser Checklist

- [ ] Desktop login flow
- [ ] Mobile-width navigation
- [ ] Long form create/edit flows
- [ ] Clause compare page
- [ ] Workflow detail page
- [ ] Signature detail page
- [ ] Privacy dashboard
- [ ] Reports export action
- [ ] Error states for missing records
- [ ] Empty states for new orgs

## Production Readiness Checklist

- [ ] No unapplied migrations
- [ ] `generate_release_gate_report` returns `GO`
- [ ] Live Salesforce sync evidence exists
- [ ] Live webhook evidence exists
- [ ] Backup / restore rehearsal completed
- [ ] Rollback rehearsal completed
- [ ] Post-deploy live smoke completed
- [ ] Security audits pass at the chosen threshold
- [ ] Release evidence is attached to the change record

## Stop Conditions

- [ ] Any 500 during core create / edit / list flows
- [ ] Any cross-tenant data leak
- [ ] Any missing permission check on org-scoped data
- [ ] Any missing release evidence for the production cutover
- [ ] Any failing migration or unapplied schema change on the target environment
