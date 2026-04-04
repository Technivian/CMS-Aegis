# CMS Aegis 30-60-90 Day Takeover Plan

## Objective

Deliver a secure, reliable, and scalable CMS/CLM platform with measurable operational maturity, while protecting current production behavior.

## Scope and Assumptions

- Scope includes security, tenancy and RBAC correctness, core workflow reliability, observability, delivery process, and performance.
- Scope excludes net-new major product modules unless they are required to close critical reliability or compliance gaps.
- Existing production behavior is considered canonical unless explicitly changed through approved decisions.

## Roles and Ownership

- Product Owner: prioritization, acceptance criteria, and release decisions.
- Tech Lead: architecture, risk management, and technical sign-off.
- Backend Engineer: Django app logic, RBAC, migrations, APIs.
- Frontend Engineer: UX consistency, accessibility, and interaction reliability.
- QA Engineer: test strategy, E2E and regression suites, release validation.
- DevOps/SRE: CI/CD, observability, runbooks, backup and recovery drills.

## Day 0 to Day 30: Stabilize and Secure

### Outcomes

- Main branch and release process are protected.
- Tenant isolation and permission model are validated on critical actions.
- Core login, contract, workflow, and document journeys are test-gated.

### Workstreams

1. Platform safety baseline
- Enforce branch protection, required checks, PR review policy.
- Define rollback procedure and test one rollback in staging.
- Inventory all runtime dependencies, secrets, and scheduled jobs.

2. Security and identity
- Rotate exposed credentials and centralize secret management.
- Validate SSO and local auth fallback behavior.
- Create role-action matrix for OWNER, ADMIN, MEMBER and verify against endpoints.

3. Tenant and data boundary validation
- Execute cross-tenant negative tests across list, detail, edit, and export actions.
- Verify object lookups are consistently organization-scoped.
- Confirm file/document access cannot cross organizations.

4. Critical flow reliability
- Lock in core smoke suite for:
  - login/logout/SSO entry
  - dashboard load
  - contract list/detail/create/edit
  - repository and workflow pages
- Expand route-target integrity checks for interactive controls.

### Exit Criteria (Day 30)

- No P0 security findings open.
- All critical flow tests green in CI on default branch.
- Tenant-isolation negative tests pass.
- Rollback procedure documented and exercised once.

## Day 31 to Day 60: Operational Excellence and Quality

### Outcomes

- Production issues are quickly diagnosable.
- Release confidence increases through stronger regression coverage.
- UI behavior is consistent across major modules.

### Workstreams

1. Observability and incident readiness
- Add request correlation IDs across app logs.
- Add metrics and alerts for:
  - 5xx error rate
  - login/SSO failures
  - slow endpoints p95
  - failed scheduled jobs
- Publish incident runbooks for top 5 failure scenarios.

2. Quality engineering and test depth
- Add E2E coverage for high-risk workflows:
  - approval and workflow transitions
  - deadline completion
  - document create/edit
  - legal tasks and risk logs
- Add API permission contract tests for role-specific behaviors.

3. UX and accessibility hardening
- Standardize primary/secondary/destructive button behavior and loading states.
- Ensure keyboard navigation and visible focus on all primary pages.
- Add accessibility checks for key templates and forms.

4. Data and migration reliability
- Validate migration forward/rollback paths in staging.
- Add pre-deploy data safety checklist.
- Add idempotent scripts for any required backfills.

### Exit Criteria (Day 60)

- Alerting and runbooks in use with test incidents completed.
- E2E suite covers all core legal operations journeys.
- No unresolved high-severity accessibility defects on critical flows.
- Migration process validated in staging with recovery evidence.

## Day 61 to Day 90: Scale, Performance, and Governance

### Outcomes

- System performance is predictable under realistic load.
- Delivery process supports safe, frequent releases.
- Team has durable governance for ongoing quality.

### Workstreams

1. Performance and scalability
- Profile top slow endpoints and eliminate N+1 queries.
- Add or tune indexes based on query plans.
- Introduce targeted caching for high-read pages.

2. Release engineering maturity
- Add staged rollout checks and post-release verification checklist.
- Add nightly full regression including browser smoke and role matrix checks.
- Define SLOs and publish dashboards.

3. Governance and maintainability
- Enforce definition of done with security/test/docs requirements.
- Require PR template fields for tenant impact, RBAC impact, and migration impact.
- Establish monthly dependency update and vulnerability remediation cadence.

### Exit Criteria (Day 90)

- p95 latency and error-rate targets are defined and tracked.
- Release checklist and rollback are routine and documented.
- Governance controls are active in PR workflow and CI policy.

## KPI Scorecard

- Reliability: 5xx rate, p95 latency on top endpoints, failed job count.
- Security: open P0/P1 findings, secrets rotation compliance, auth anomaly count.
- Quality: test pass rate, flaky test rate, escaped defect count.
- Delivery: deployment frequency, change failure rate, mean time to restore.
- Product trust: completion rate of core user journeys, support ticket volume by module.

## Weekly Cadence

- Monday: risk review and sprint planning.
- Wednesday: quality and incident review.
- Friday: release readiness review and KPI snapshot.

## Immediate Next 7 Days

1. Confirm production/staging inventories and branch protection.
2. Run full verification suite and establish baseline results artifact.
3. Complete credential rotation and secrets inventory sign-off.
4. Execute tenant and RBAC negative test pass and log evidence.
5. Publish rollback runbook and perform one staging drill.
