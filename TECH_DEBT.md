# CMS Aegis Technical Debt

Last updated: 2026-04-25

## High-Priority Debt

| Debt item | Where | Why it matters | Recommended fix |
|---|---|---|---|
| Release gate still fails without live integration evidence | `contracts/management/commands/generate_release_gate_report.py`, `docs/GO_LIVE_CHECKLIST.md` | Production readiness depends on evidence, not just code passing | Automate and attach a real Salesforce sync + webhook delivery proof set |
| Moderate PostCSS vulnerability | `client/package-lock.json`, `theme/static_src/package-lock.json` | It is not a high-severity blocker, but it is real security debt visible in audits | Update PostCSS and re-lock both frontend dependency trees |
| Placeholder template actions | `theme/templates/contracts/templates_list.html` | The UI shows TODO actions that do not actually perform product work | Wire those actions to real edit / create-from-template behavior or remove them |
| Client test script is a stub | `client/package.json` | `npm test` exits 1 with “Error: no test specified,” which is misleading for future contributors | Replace it with a useful smoke command or remove the script if Playwright is the only path |

## Architecture Debt

| Debt item | Where | Why it matters | Recommended fix |
|---|---|---|---|
| Large monolithic modules | `contracts/api/views.py`, `contracts/models.py`, `contracts/forms.py`, `contracts/views_domains/privacy_approvals.py`, `contracts/views_domains/organization_admin.py` | Large files are harder to reason about, review, and refactor safely | Keep splitting by domain and move shared helpers into smaller service modules |
| Mixed domain layers | `contracts/views_domains/*`, `contracts/services/*`, `contracts/views.py` | Some domain logic still sits close to the views instead of being fully isolated | Continue migrating workflow, e-sign, and integration logic into service layers |
| Mock repository backend still exists | `contracts/services/repository.py` | The abstract interface and `MockRepositoryService` are still present and can confuse intent | Keep only if test seams need it; otherwise tighten the API and remove unused mock paths |
| Duplicate / alternate UI shells | `theme/templates/base_redesign.html`, `theme/templates/base_fullscreen.html`, `theme/templates/styleguide.html`, `theme/templates/components_demo.html`, `toggle-redesign` | Multiple shells increase maintenance and make the supported UX harder to explain | Declare one supported shell, keep demo pages isolated, and retire dead variants |
| Template editing UX is only partially implemented | `theme/templates/contracts/templates_list.html` | The page advertises template interactions that are still placeholder JS | Make template actions first-class or remove them from navigation |

## Integration Debt

| Debt item | Where | Why it matters | Recommended fix |
|---|---|---|---|
| Salesforce live proof is missing | `contracts/services/salesforce.py`, `contracts/api/views.py` | Sync plumbing exists, but the release gate still lacks a recent success | Run and record a real sync run in the target environment |
| NetSuite is only partially proven live | `contracts/services/netsuite.py`, `contracts/api/views.py` | HTTP-backed ingestion exists, but the business reliability story is incomplete | Add live provider evidence and clearer error reporting |
| E-sign provider lifecycle is not fully proven | `contracts/services/esign.py`, `contracts/views_domains/privacy_approvals.py` | Webhook reconciliation exists, but the full external signing loop is not yet enterprise-grade | Capture live signature packet / status / callback evidence |
| Webhook diagnostics are still shallow | `contracts/services/webhooks.py`, `contracts/models.py` | Delivery retries exist, but supportability can still improve | Add a more explicit delivery dashboard and dead-letter UI |

## Test And QA Debt

| Debt item | Where | Why it matters | Recommended fix |
|---|---|---|---|
| Playwright coverage is narrow | `client/tests/e2e/smoke.spec.js`, `client/tests/e2e/critical-flows.spec.js` | The browser suite covers important flows, but not the full app surface | Add auth edge cases, live-provider flows, and mobile responsive checks |
| Live smoke is still partly manual | `docs/MANUAL_SMOKE_CHECKLIST.md`, browser sessions | Manual smoke is effective but easy to skip | Automate the checklist where possible and link results to releases |
| Some release proofs depend on docs instead of code | `docs/GO_LIVE_CHECKLIST.md`, `docs/DRILL_LOG.md` | Operational proof is easy to lose if it lives only in human-written notes | Keep generating structured artifacts alongside the docs |

## Low-Priority / Cosmetic Debt

| Debt item | Where | Why it matters | Recommended fix |
|---|---|---|---|
| Demo and styleguide pages are still present | `theme/templates/components_demo.html`, `theme/templates/styleguide.html` | These are useful for development, but they are not product surfaces | Keep them isolated from customer navigation and label them clearly |
| Shared utility code could still be normalized | `contracts/view_support.py`, `contracts/tenancy.py`, `contracts/middleware.py` | Shared helper sprawl can become hard to maintain over time | Consolidate helper APIs only when it reduces duplication |

## Refactor Candidates

1. Break `contracts/api/views.py` into smaller API domain modules.
2. Continue splitting `contracts/views_domains/organization_admin.py` if it grows further.
3. Replace template-list placeholder JavaScript with server-backed actions.
4. Tighten the repository service interface or remove the mock path.
5. Normalize release evidence generation into a single structured command flow.

## Risk Areas To Watch

- Security / compliance regressions in SAML, SCIM, and MFA flows
- Workflow routing or approval transition bugs
- E-sign transition and webhook reconciliation edge cases
- Release gate and production cutover evidence drift
- Frontend dependency advisories and build-tooling drift
