# CMS Aegis Master To-Do for CMS Aegis-Level CLM/CMS

Last updated: 2026-04-14

Legend:
- `DONE` = implemented and discoverable in code/docs
- `PARTIAL` = present but missing enterprise depth/reliability
- `MISSING` = not implemented or not production-grade

---

## Execution Progress Log

2026-04-14:
- Completed the first five items of the current queue:
  - added versioned API v1 contract endpoints with scoped bearer tokens.
  - added clause playbooks/variants and resolver UI on clause detail pages.
  - added approval delegation fields, reminder escalation timing, and delegation logging.
  - improved search relevance ranking and semantic filter controls.
  - added an operations dashboard plus a drill command for queue/alert evidence.
  - verification: `python manage.py test tests.test_api_versions_clauses_operations_search tests.test_mfa_policy tests.test_identity_telemetry_and_exports tests.test_repository_saved_views tests.test_document_versioning tests.test_workflow_routing tests.test_saml_and_scim_groups tests.test_identity_settings_and_scim -v 1`.
- Completed the identity telemetry / recovery-code / async queue slice:
  - added MFA recovery-code generation and one-time verification.
  - added the identity telemetry dashboard with MFA/SAML/SCIM event counters and recovery-code inventory.
  - added privacy evidence CSV export for DSAR, subprocessor, transfer, retention, and audit evidence.
  - moved reminder/OCR work into background jobs and added a job processor/queue command.
  - added CSV import/mapping reconciliation for contracts.
  - verification: `python manage.py test tests.test_mfa_policy tests.test_identity_telemetry_and_exports tests.test_repository_saved_views tests.test_document_versioning -v 1`.
- Completed the redlining / version-compare slice:
  - added document comparison service and compare UI.
  - document updates now create immutable versions and queue OCR review records.
  - verification: `python manage.py test tests.test_document_versioning tests.test_cms_aegis_features -v 1`.
- Completed bulk record-operation hardening:
  - bulk contract updates now validate lifecycle transitions and emit audit events.
  - verification: `python manage.py test tests.test_cms_aegis_features -v 1`.
- Completed deterministic workflow routing:
  - approval routing now matches value / jurisdiction / contract type rules and auto-creates approval requests.
  - verification: `python manage.py test tests.test_workflow_routing tests.test_workflow_transition_guardrails -v 1`.
- Completed SAML follow-up:
  - attribute reconciliation now handles nested group-like values and display-name aliases.
  - logout errors fall back to local sign-out with telemetry.
  - verification: `python manage.py test tests.test_saml_and_scim_groups -v 1`.
- Completed clause policy reconciliation:
  - mandatory clause forms now reject missing fallback/playbook guidance.
  - clause detail surfaces fallback summaries and policy issues.
  - verification: `python manage.py test tests.test_contract_required_fields -v 1`.

2026-04-13:
- Completed validation for bulk API hardening (`ICL-001`) in current tree.
- Verified focused test suites pass:
  - `tests.test_cms_aegis_features` (8 tests)
  - `tests.test_security_guardrails` + `tests.test_cross_tenant_mutation_guardrails` (5 tests)
- Verified export/download permissions currently covered for organization activity export:
  - `tests.test_organization_invitations` (27 tests), including owner/admin allow, member deny, anonymous redirect, and tenant scoping checks.
- Implemented `ICL-002` configuration layer:
  - `DATABASE_URL` parsing in base settings with Postgres/SQLite support.
  - production guard now fails fast unless DB engine is PostgreSQL (or explicit emergency override).
  - updated `.env.example`, `README_CMS_AEGIS.md`, and `docs/ROLLBACK_RUNBOOK.md` with Postgres contract and rehearsal template.
- Validation results:
  - `python manage.py check` (development profile) passes.
  - production profile without `DATABASE_URL` correctly fails with `ImproperlyConfigured`.
  - full production-profile startup with PostgreSQL DSN is blocked in this local venv because `psycopg2-binary==2.9.10` cannot build on the current local Python `3.15.0a6` runtime.
- Next execution target: install production runtime deps in this environment, run staging-style Postgres rehearsal commands, and record evidence in `docs/DRILL_LOG.md`.
- Implemented `ICL-004` runtime alignment:
  - replaced project `.venv` with Python `3.12.13` via `uv`.
  - added repo Python pin file: `.python-version`.
  - added reproducible bootstrap script: `scripts/bootstrap_python312.sh`.
  - fixed local dev dependency gap by adding `django-debug-toolbar` to `requirements/dev.txt`.
  - added `Pillow` to runtime requirements so Django checks pass on clean envs.
  - updated CI scanner commands to improve reliability and signal quality:
    - `pip-audit --disable-pip --no-deps -r requirements/runtime.txt`
    - `bandit -q -r contracts config -lll` (high-severity gate)
- Validation evidence (2026-04-13):
  - `.venv` now runs `Python 3.12.13`.
  - `python manage.py check` passes on the new env.
  - `pip-audit --disable-pip --no-deps -r requirements/runtime.txt` reports no known vulnerabilities.
  - `bandit -q -r contracts config -lll` passes (no high-severity findings).
  - focused regression tests pass: `tests.test_cms_aegis_features` + `tests.test_security_guardrails`.
- Completed `ICL-003` dependency vulnerability verification for Node stacks:
  - `npm --prefix client audit --audit-level=high --json` reports zero high/critical vulnerabilities.
  - `npm --prefix theme/static_src audit --audit-level=high --json` reports zero high/critical vulnerabilities.
  - current package locks are already in a compliant state for the high-severity gate.
- Added staging execution artifact for `ICL-002` completion:
  - `docs/STAGING_POSTGRES_REHEARSAL.md` with exact commands, expected outputs, and `DRILL_LOG` template.
- Executed `ICL-002` staging-style rehearsal on PostgreSQL and captured evidence:
  - full backup -> migrate -> tenant checks -> restore -> post-restore checks cycle completed.
  - evidence recorded in `docs/DRILL_LOG.md` (2026-04-13 entry).
- Implemented `ICL-006` persisted service migration:
  - replaced in-memory mock-first `TemplateService`, `ClauseService`, and `ObligationService` with Django model-backed implementations.
  - removed singleton in-memory service usage from `contracts/services/__init__.py`.
  - added regression coverage in `tests/test_persisted_services.py`.
  - verification: `python manage.py test tests.test_persisted_services tests.test_cms_aegis_features tests.test_security_guardrails`.
- Implemented `ICL-007` workflow hardening:
  - added explicit status transition guards for `SignatureRequest` and `ApprovalRequest`.
  - enforced actor authorization for transition actions in update form flows.
  - added transition regression tests in `tests/test_workflow_transition_guardrails.py`.
  - verification: `python manage.py test tests.test_workflow_transition_guardrails tests.test_cms_aegis_features tests.test_security_guardrails tests.test_persisted_services`.
- Implemented `ICL-008` observability slice (scheduler heartbeat):
  - added heartbeat metric persistence for reminder scheduler success runs.
  - extended `/_health/` with JSON mode (`?format=json`) including scheduler stale/healthy/unknown status.
  - added regression tests in `tests/test_observability_guardrails.py`.
  - verification: `python manage.py test tests.test_observability_guardrails`.
- Implemented `ICL-009` release evidence gate (PR-level):
  - added a required PR checklist validation job in `.github/workflows/platform-guardrails.yml`.
  - updated `.github/pull_request_template.md` to capture smoke and rollback evidence fields.
  - this enforces release evidence hygiene before merge on pull requests targeting `main`.
- Extended `ICL-008` observability implementation:
  - added lightweight HTTP request metrics counters (status class, route bucket, average latency) via middleware.
  - added DB probe health signal with latency thresholds in `/_health/?format=json`.
  - verification: `python manage.py test tests.test_observability_guardrails tests.test_workflow_transition_guardrails -v 2`.
- Closed out `ICL-008` observability operations:
  - added alert evaluator and fire-drill commands (`evaluate_observability_alerts`, `run_observability_fire_drill`).
  - added automated observability watch workflow with incident issue escalation (`.github/workflows/observability-watch.yml`).
  - documented dashboard IDs and alert policy (`docs/OBSERVABILITY_DASHBOARD_IDS.md`, `docs/OBSERVABILITY_ALERT_POLICY.md`).
  - recorded fire-drill evidence in `docs/DRILL_LOG.md` (2026-04-13 entry).
- Started `ICL-010` performance hardening:
  - added query-scaling regression tests in `tests/test_performance_guardrails.py`.
  - detected and fixed an N+1-style query growth in contracts API listing by selecting `created_by` in repository service list query.
  - added repeatable core route latency profiler command (`manage.py profile_core_routes`) and generated baseline at `docs/PERFORMANCE_BASELINE_2026-04-13.json`.
  - added CI enforcement step for performance guardrails in `.github/workflows/platform-guardrails.yml`.
  - added contract list/repository index set with query plan evidence in `docs/QUERY_PLAN_2026-04-13.md`.
  - completed top-10 authenticated route profiling evidence in `docs/AUTH_ROUTE_PROFILE_2026-04-13.json` and `docs/AUTH_ROUTE_PROFILE_2026-04-13.md`.
  - completed 2x peak load harness and evidence in `docs/LOAD_TEST_2X_2026-04-13.json` and `docs/LOAD_TEST_2X_2026-04-13.md`.
  - added bundle command `manage.py run_performance_evidence_bundle` and wired RC artifact workflow to include full performance evidence set.
  - verification: `python manage.py test tests.test_performance_guardrails tests.test_cms_aegis_features -v 1`.
- Started `ICL-011` monolith split:
  - extracted privacy/approval/signature views into `contracts/views_domains/privacy_approvals.py`.
  - extracted organization invitation/membership/activity/reporting views into `contracts/views_domains/organization_admin.py`.
  - extracted repository management/search views into `contracts/views_domains/repository_management.py`.
  - extracted workflow template/workflow/step views and function handlers into `contracts/views_domains/workflow_management.py`.
  - preserved route names and templates through import re-export in `contracts/views.py`.
  - verification: `python manage.py test contracts tests -v 1` (`183` tests passed).
  - closeout: `contracts/views.py` reduced from `2935` lines to `2049` lines with high-risk domains split into dedicated modules.
- Completed `ICL-012` governance/compliance operating model artifacts:
  - added vulnerability SLA policy: `docs/SECURITY_SLA_POLICY.md`.
  - added weekly governance automation: `.github/workflows/security-sla-watch.yml`.
  - recorded SLA cycle evidence: `docs/SECURITY_SLA_CYCLE_2026-04-13.md`.
  - recorded game-day and SLA rehearsal in `docs/DRILL_LOG.md` (2026-04-13 entry).
  - added data classification/retention controls evidence: `docs/DATA_CLASSIFICATION_RETENTION_CONTROLS.md`.

---

## 1) Platform, Tenancy, and Identity

1. Multi-tenant organization model and scoped access
- Status: `DONE`
- Evidence: `contracts/models.py` (`Organization`, `OrganizationMembership`), `contracts/views.py` tenant-scoped mixins/queries
- Next: keep adding deny-path tests for every new route.

2. Centralized contract permission policy
- Status: `DONE`
- Evidence: `contracts/permissions.py`, usage in `contracts/views.py`
- Next: extend policy matrix to download/export endpoints.

3. SSO via OIDC
- Status: `DONE`
- Evidence: `contracts/auth_backends.py`, `config/settings_base.py`, `docs/SSO_AZURE_SETUP.md`, `docs/SSO_GOOGLE_SETUP.md`
- Next: add enterprise SSO admin UI for self-service configuration.

4. SAML support
- Status: `PARTIAL`
- Evidence: identity-provider settings plus SAML login, ACS, logout, metadata, assertion freshness checks, signature/audience checks, nested attribute reconciliation, logout fallback telemetry, and organization selector flow in `contracts/models.py`, `contracts/forms.py`, `contracts/saml.py`, `contracts/views_domains/saml.py`, `config/urls.py`, and `theme/templates/contracts/saml_select.html`.
- Next: add SAML IdP-initiated SLO handling and stronger telemetry dashboards.

5. SCIM user/group provisioning
- Status: `PARTIAL`
- Evidence: SCIM bearer-token users/groups APIs, group nesting, role mapping, query filtering/pagination, externalId reconciliation, string-safe PATCH handling, nested group sync, and deprovision hooks in `contracts/api/views.py`, `contracts/models.py`, `contracts/views_domains/organization_admin.py`, and `theme/templates/contracts/organization_identity_settings.html`.
- Next: add richer SCIM group PATCH/query semantics and IdP attribute mapping dashboards.

6. MFA enforcement (especially admin)
- Status: `PARTIAL`
- Evidence: org-level `require_mfa` policy, profile-level `mfa_enabled`, enrollment-code verification flow, recovery-code generation/consumption, identity telemetry dashboard, and middleware enforcement in `contracts/models.py`, `contracts/middleware.py`, `contracts/forms.py`, and `contracts/views_domains/actions.py`.
- Next: add device-bound second-factor options and stronger recovery-code policy controls.

7. Session security controls (device/session revoke, idle timeout policy)
- Status: `PARTIAL`
- Evidence: base Django sessions, org-level session revocation helper, per-member revocation control, org-level idle timeout policy, org security export, session audit view/export, and organization security settings UI in `contracts/session_security.py`, `contracts/views_domains/actions.py`, `contracts/views_domains/organization_admin.py`, `contracts/middleware.py`, and `theme/templates/contracts/organization_security_settings.html`.
- Next: add finer-grained device-binding controls and session fingerprinting.

8. Ethical walls / conflict restrictions
- Status: `DONE`
- Evidence: `EthicalWall` model/forms/views in `contracts/models.py` and `contracts/views.py`
- Next: add automated enforcement checks across search/export/API surfaces.

---

## 2) Contract Repository and Lifecycle Core

9. Contract metadata model (type/parties/law/jurisdiction/status/dates/value/risk)
- Status: `DONE`
- Evidence: `Contract` model in `contracts/models.py`
- Evidence extended: configurable required-field policies now enforced in `contracts/forms.py`.

10. End-to-end lifecycle states (draft -> review -> negotiation -> approval -> signature -> execution -> renewal/termination -> archive)
- Status: `PARTIAL`
- Evidence: workflows + approvals + signatures exist; contract lifecycle transitions now enforce hard guards and audit diffs on update.
- Next: finish document immutability and end-to-end archive/renewal automation.

11. Versioned documents and immutable history
- Status: `DONE`
- Evidence: `Document` version lineage, append-only version creation, file hash verification, OCR queueing, and document compare UI now exist in `contracts/models.py`, `contracts/views_domains/client_matter_document.py`, `contracts/services/document_versions.py`, `contracts/services/document_ocr.py`, and `theme/templates/contracts/document_compare.html`.
- Next: add richer redline diffing and editor-side compare presets.

12. Upload + OCR pipeline
- Status: `PARTIAL`
- Evidence: OCR queue model, upload-triggered review records, and human verification workflow exist.
- Next: add richer document OCR extraction and reviewer assignment automation.

13. Redlining / version compare UI
- Status: `DONE`
- Evidence: document compare view, document compare template, compare links, and version history context in `contracts/views_domains/client_matter_document.py`, `contracts/services/document_versions.py`, `contracts/urls.py`, `theme/templates/contracts/document_detail.html`, and `theme/templates/contracts/document_compare.html`.
- Next: expand clause-level redlining and semantic change summaries.

14. Negotiation comments/threads
- Status: `DONE`
- Evidence: `NegotiationThread` model + forms/views
- Next: add @mention assignment and SLA timers.

15. Bulk operations on repository records
- Status: `PARTIAL`
- Evidence: bulk endpoint allowlists lifecycle/status fields, validates lifecycle transitions, and emits audit events in `contracts/services/repository.py` and `contracts/api/views.py`.
- Next: add bulk filter-preserving review UI and per-field change previews.

---

## 3) Workflow and Approval Engine

16. Workflow templates and per-contract workflows
- Status: `DONE`
- Evidence: `WorkflowTemplate`, `Workflow`, `WorkflowStep` models + views; versioned template helpers in `contracts/services/workflow_templates.py`; migration and restore commands in `contracts/management/commands/migrate_workflow_template.py`; lineage/history + comparison UI in `theme/templates/contracts/workflow_template_detail.html` and `theme/templates/contracts/workflow_template_compare.html`; workflow editor template summaries in `theme/templates/contracts/workflow_form.html`; legal-ops compare presets in `contracts/services/workflow_templates.py`; regression tests in `tests/test_workflow_template_versioning.py`.
- Next: add richer template diff summaries and migration/restore guardrails.

17. Conditional workflow routing (value/jurisdiction/type)
- Status: `PARTIAL`
- Evidence: `ApprovalRule` model plus deterministic routing helpers and auto-created approval requests in `contracts/services/workflow_routing.py` and `contracts/views_domains/workflow_management.py`.
- Next: implement visual rule builder with deterministic evaluation engine.

18. Multi-step approvals (legal/finance/privacy)
- Status: `PARTIAL`
- Evidence: `ApprovalRule` and `ApprovalRequest` present with auto-plan creation from workflow routing.
- Next: add parallel/serial approvals, quorum rules, and approver delegation.

19. SLA, escalation, reassignment, delegation
- Status: `PARTIAL`
- Evidence: reminder scheduler escalates overdue approvals and stale signatures in `contracts/management/commands/send_contract_reminders.py`.
- Next: implement deadline timers, escalation ladders, auto-reassignment, and delegation UX.

20. Approval/signature transition guardrails
- Status: `DONE`
- Evidence: `SignatureRequest.can_transition_to`, `ApprovalRequest.can_transition_to` and actor checks in `contracts/models.py`; enforcement in `contracts/forms.py`; regression tests in `tests/test_workflow_transition_guardrails.py`.
- Evidence extended: overdue approval/signature escalation automation runs in `contracts/management/commands/send_contract_reminders.py`.

---

## 4) Clause Library and Template Intelligence

21. Clause category/template management
- Status: `DONE`
- Evidence: `ClauseCategory`, `ClauseTemplate` models + CRUD views
- Next: add clause usage analytics and dependency graph.

22. Jurisdictional clause variants and fallback positions
- Status: `PARTIAL`
- Evidence: clause fallback helpers, fallback summaries, and policy validation now exist in `contracts/services/clause_policy.py`, `contracts/forms.py`, and `contracts/views_domains/repository_management.py`.
- Next: build clause variant resolver (jurisdiction, risk tier, contract type).

23. Mandatory clause enforcement policies
- Status: `PARTIAL`
- Evidence: mandatory clause form validation and fallback guidance checks now exist in `contracts/forms.py` and `contracts/services/clause_policy.py`.
- Next: define workflow-level blocking if required clause absent from a contract playbook/template.

24. Playbooks for negotiation fallback language
- Status: `PARTIAL`
- Evidence: clause fallback resolution and policy summaries now exist; playbook logic not formalized.
- Next: create playbook model and recommendation service in negotiation workflow.

---

## 5) Obligation, Deadlines, and Renewal Intelligence

25. Renewal/expiration reminders
- Status: `DONE`
- Evidence: scheduler commands (`send_contract_reminders`, `run_reminder_scheduler`)
- Next: add configurable cadence by contract type and priority.

26. Obligation tracking (deliverables/compliance/deletion obligations)
- Status: `DONE`
- Evidence: persisted `ObligationService` in `contracts/services/obligations.py` and regression tests in `tests/test_persisted_services.py`.
- Next: expand obligation taxonomy and playbooks for contract-type-specific obligations.

27. Renewal playbooks and auto-generated tasks
- Status: `MISSING`
- Next: generate legal/procurement tasks automatically off key date windows.

---

## 6) Search, Discovery, and Analytics

28. Global search across records
- Status: `DONE`
- Evidence: `global_search` in `contracts/views.py`
- Next: add ranking quality controls and relevance telemetry.

29. Full-text + metadata faceted search
- Status: `PARTIAL`
- Evidence: keyword search exists
- Next: add indexed full-text + saved filters + column-level facets.

30. Semantic/AI search over clauses/contracts
- Status: `PARTIAL`
- Evidence: semantic clause search mode (`search_mode=semantic|hybrid|keyword`) with tenant-scoped ACL filtering in `contracts/views_domains/repository_management.py` and semantic ranking helper in `contracts/services/semantic_search.py`; regression coverage in `tests/test_api_versions_clauses_operations_search.py` and `tests/test_cross_tenant_isolation.py`.
- Next: add embedding-backed retrieval with citations and model-governed relevance telemetry.

31. Repository dashboards and saved views
- Status: `PARTIAL`
- Evidence: dashboard metrics present plus saved views and filter-chip polish in `theme/static/js/cms-aegis-repository.js`.
- Next: build configurable shared-team dashboards and deeper filter persistence.

32. Executive analytics (cycle time, bottlenecks, risk trends)
- Status: `PARTIAL`
- Evidence: baseline aggregates in dashboard
- Next: add historical trend model and cohort analytics.

---

## 7) Privacy, GDPR, and Compliance Ops

33. Data inventory (RoPA-style)
- Status: `DONE`
- Evidence: `DataInventoryRecord` model/views
- Next: add cross-reference to processing systems and subprocessors automatically.

34. DSAR workflows
- Status: `DONE`
- Evidence: `DSARRequest` model/views/dashboard stats
- Next: add SLA countdown and evidence bundle export.

35. Subprocessor registry and transfer tracking
- Status: `DONE`
- Evidence: `Subprocessor`, `TransferRecord` models/views
- Next: add auto-alerts for expired agreements and transfer risk flags.

36. Retention policies and legal hold
- Status: `DONE`
- Evidence: `RetentionPolicy`, `LegalHold` models/views
- Next: enforce retention execution jobs and immutable action logs.

37. Tamper-evident compliance/audit evidence exports
- Status: `PARTIAL`
- Evidence: audit log exists plus privacy evidence CSV export in `contracts/views_domains/privacy_approvals.py`.
- Next: add signed export bundles with integrity hashes and verification receipts.

---

## 8) Integrations and External Ecosystem

38. E-sign provider integration (DocuSign/Adobe Sign-class)
- Status: `PARTIAL`
- Evidence: provider webhook callback endpoint (`/contracts/api/integrations/esign/webhook/`), reconciliation engine (`contracts/services/esign.py`), replay-safe idempotency/out-of-order handling, and e-sign integration evidence command (`generate_esign_integration_report`) are implemented.
- Next: complete direct provider outbound adapter for send/create APIs and capture staging/provider execution proof.

39. Webhook platform (outgoing events + retry/DLQ)
- Status: `MISSING`
- Next: ship event bus, retries, dead-letter queue, delivery diagnostics UI.

40. Public API for contracts/workflows/reports
- Status: `PARTIAL`
- Evidence: versioned contracts API v1 endpoints and scoped bearer tokens in `contracts/api/views.py`, `contracts/models.py`, `contracts/urls.py`, and `contracts/views_domains/organization_admin.py`.
- Next: extend versioning to workflows/reports and add write-scope endpoints plus pagination receipts.

41. CRM/ERP integrations (Salesforce/NetSuite/procurement tools)
- Status: `PARTIAL`
- Evidence: Salesforce sync + webhook lifecycle and NetSuite authenticated sync (`sync_netsuite_contracts`) are implemented.
- Next: add procurement-system connector and complete target-environment execution evidence.

42. Inbound import APIs and mapping tools
- Status: `MISSING`
- Next: build smart import pipeline with field mapping and dedupe.

---

## 9) AI Layer (Enterprise-Hardened)

43. Contract AI assistant scoped by tenancy
- Status: `DONE`
- Evidence: `contract_ai_assistant` endpoint with org checks plus prompt-policy enforcement (`contracts/services/ai_policy.py`), blocked-injection handling, and output policy metadata on responses.
- Next: monitor false-positive/false-negative prompt policy outcomes and tune block patterns.

44. AI summarization/risk extraction with citations
- Status: `PARTIAL`
- Evidence: AI response helper emits grounded contract-field citations, structured extraction schema (`schema_version=1.0`), clause-level findings, and confidence scores for risk/renewal/clause signals.
- Next: add clause text-span provenance citations and confidence calibration policy thresholds.

45. AI-assisted drafting and clause recommendations
- Status: `PARTIAL`
- Evidence: clause infra exists
- Next: add drafting assistant integrated with clause library and playbooks.

46. Agentic AI actions (start workflows, route approvals, create tasks)
- Status: `PARTIAL`
- Evidence: `contract_ai_assistant` now supports action planning and gated execution (`execute_actions`, `approval_confirmed`), creates workflows/approval requests/legal tasks, and records traceable rollback plans in audit log metadata via `contracts/services/ai_actions.py` and `contracts/views_domains/contracts.py`.
- Next: add explicit rollback execution endpoint and dual-approval workflow for high-impact actions.

47. AI governance (policy, audit, model controls, red-team tests)
- Status: `PARTIAL`
- Evidence: basic audit logging exists
- Next: add model registry, safety policies, and adversarial evaluation suite.

---

## 10) Security, Reliability, and Operations

48. Production database posture (Postgres primary)
- Status: `PARTIAL`
- Evidence: SQLite baseline; migration item tracked (ICL-002)
- Next: complete Postgres cutover runbook and staging rehearsal.

49. Async job system (Celery/RQ + Redis) for reminders/OCR/integrations
- Status: `MISSING`
- Next: move long-running/scheduled work to queue workers.

50. Observability (structured logs, dashboards, alerts, SLOs)
- Status: `DONE`
- Evidence: telemetry + health signal (`contracts/observability.py`, `contracts/views.py`), automated watch (`.github/workflows/observability-watch.yml`), dashboard ID mapping (`docs/OBSERVABILITY_DASHBOARD_IDS.md`), fire-drill evidence (`docs/DRILL_LOG.md`).
- Next: connect sink-specific transport in each deployment target (Datadog/CloudWatch/Loki forwarder).

51. Release gates and incident readiness
- Status: `DONE`
- Evidence: PR evidence gate and checklist (`.github/workflows/platform-guardrails.yml`, `.github/pull_request_template.md`), branch protection update on `main` (required `pr-release-evidence` check), release-candidate artifact workflow (`.github/workflows/release-candidate-evidence.yml` + `docs/RELEASE_EVIDENCE_POLICY.md`).
- Next: periodically audit required checks list against workflow/job name changes.

52. Vulnerability management and dependency hygiene
- Status: `PARTIAL`
- Evidence: high vulnerabilities noted in execution plan
- Next: clear high CVEs and enforce scanner gates in CI.

53. Backup/restore + DR drills
- Status: `PARTIAL`
- Evidence: rollback runbook exists
- Next: add recurring restore drills with RTO/RPO evidence.

---

## 11) Product UX and Commercial Readiness

54. Enterprise admin console (org settings, policy controls, integrations)
- Status: `PARTIAL`
- Evidence: org/team management exists
- Next: consolidate into dedicated admin center UX.

55. Permission transparency UI (who can view/edit/approve/export)
- Status: `MISSING`
- Next: add per-record access matrix UI.

56. Self-serve onboarding + guided setup
- Status: `PARTIAL`
- Evidence: seed/setup docs exist
- Next: in-product onboarding wizard and environment health checks.

57. Billing/subscription and usage controls
- Status: `MISSING`
- Next: add plans, entitlements, seat management, and usage metering.

58. Customer-facing trust/compliance portal artifacts
- Status: `MISSING`
- Next: publish security controls, uptime, and compliance evidence pack.

---

## 12) “Go Through All” Execution Sequence

Phase A (Weeks 1-4): close critical production blockers
1. Harden bulk API and all mutation guardrails.
2. Complete Postgres production path and migration rehearsal.
3. Eliminate high vulnerabilities.
4. Align runtime versions and scanner reliability.
5. Complete export/download authorization matrix.

Phase B (Weeks 5-8): CLM engine depth
1. Persisted obligation/template/clauses services.
2. Approval/signature state-machine guardrails.
3. Conditional routing and escalation logic.
4. Start DocuSign-class integration adapter.

Phase C (Weeks 9-12): intelligence + enterprise operations
1. OCR + extraction + verification queue.
2. Semantic search with ACL-safe retrieval.
3. Observability dashboards + paging + drills.
4. API/webhook platform + first external integration.

Phase D (Weeks 13-16): enterprise finish
1. SCIM + MFA + session policy controls.
2. Compliance evidence exports and retention execution automation.
3. Executive analytics/saved views.
4. Commercial readiness: admin center + billing/entitlements.

---

## Definition of “Powerful and Complete” for This Repo

This repo reaches CMS Aegis-level enterprise readiness when all of the following are true:
1. No `P0` security/reliability gaps remain open.
2. Contract lifecycle is enforced by state-machine rules, not only UI/form behavior.
3. At least one production-grade e-sign integration and one business-system integration are live.
4. Search includes full-text + metadata + semantic retrieval with tenant-safe access control.
5. Compliance module can produce defensible, tamper-evident audit/export evidence.
6. Platform operations meet SLOs with alerts, drills, and repeatable release gates.
