# CMS Aegis Delivery Roadmap

Last updated: 2026-04-25

## Phase 1: Stabilize The App

The release evidence bundle automation is in place and can drive the current checkout to `GO` when Sprint 3 evidence is seeded. The remaining phase 1 work is about live production proof and cleanup.

| Task | Why It Matters | Affected Files / Modules | Complexity | Dependency | Acceptance Criteria |
|---|---|---|---|---|---|
| Produce live Salesforce sync evidence | The app can already generate synthetic release evidence, but production signoff still needs a real sync in the target org | `contracts/services/salesforce.py`, `contracts/api/views.py`, `contracts/management/commands/*`, release evidence docs | Medium | Valid Salesforce credentials and target org | A successful live sync run is recorded and visible in the release gate report |
| Produce webhook delivery evidence | Release readiness also depends on real delivery activity, not just code paths | `contracts/services/webhooks.py`, `contracts/models.py`, webhook delivery UI / APIs | Medium | A live webhook endpoint | At least one successful live delivery and one diagnostic record exist in the target environment |
| Resolve the moderate PostCSS advisory | Security debt is currently visible in both frontend dependency trees | `client/package-lock.json`, `theme/static_src/package-lock.json`, frontend build tooling | Small | None | `npm audit` no longer reports the PostCSS advisory |
| Keep deploy migrations clean | The app should not ship with unapplied schema changes | `contracts/migrations/*`, deployment scripts, Render config | Small | None | Deploys start with zero unapplied migrations |

## Phase 2: Complete Core User Flows

| Task | Why It Matters | Affected Files / Modules | Complexity | Dependency | Acceptance Criteria |
|---|---|---|---|---|---|
| Replace the `templates_list.html` placeholder JS actions | The template library still contains TODO-style actions that are not real product behavior | `theme/templates/contracts/templates_list.html` | Small | None | Edit / use-template actions perform real navigation or save behavior |
| Harden signature packet routing | Signature lifecycle should feel like an actual execution workflow, not just a status tracker | `contracts/models.py`, `contracts/services/esign.py`, `contracts/views_domains/privacy_approvals.py`, `theme/templates/contracts/signature_request_detail.html` | Medium | Existing signature guardrails | Users can route, follow, and resolve signature requests end to end |
| Improve workflow builder UX | Workflow execution exists, but the authoring experience still needs depth | `contracts/views_domains/workflow_management.py`, `theme/templates/contracts/workflow_*`, `contracts/forms.py` | Medium | Workflow execution model | Users can author, review, and understand workflow branching cleanly |
| Tighten clause navigation and compare flows | Clause versioning is strong, but the reviewer experience can still be improved | `contracts/views_domains/repository_management.py`, `contracts/services/clause_versions.py`, `theme/templates/contracts/clause_template_*` | Small | Clause versioning already exists | Version history, comparison, and source-link navigation are obvious and usable |

## Phase 3: Polish UI / UX

| Task | Why It Matters | Affected Files / Modules | Complexity | Dependency | Acceptance Criteria |
|---|---|---|---|---|---|
| Consolidate alternate shells and demo surfaces | The app has multiple visual shells and demo pages that increase maintenance cost | `theme/templates/base_redesign.html`, `theme/templates/base_fullscreen.html`, `theme/templates/styleguide.html`, `theme/templates/components_demo.html`, `config/urls.py` | Medium | None | The product has a smaller, clearer set of supported shells |
| Add robust empty / loading / error states | Real customers need clarity when lists are empty or requests fail | `theme/templates/contracts/*`, shared base templates | Medium | None | Major pages explain empty states and failures clearly |
| Run a responsive pass on key pages | The app needs to remain usable on smaller screens | `theme/templates/base.html`, `theme/static_src/src/*`, core list/detail templates | Medium | Existing responsive layout | Core create / edit / list flows remain usable on mobile widths |

## Phase 4: Add Missing Business Features

| Task | Why It Matters | Affected Files / Modules | Complexity | Dependency | Acceptance Criteria |
|---|---|---|---|---|---|
| Improve saved searches and advanced filters | Search is useful, but operators need deeper filtering and faster recall | `contracts/views_domains/repository_management.py`, `contracts/models.py`, `theme/templates/contracts/search_results.html` | Medium | Search presets already exist | Users can save, reload, and refine filtered views reliably |
| Expand reporting and exports | Decision-makers need exportable evidence, not just dashboards | `contracts/views_domains/organization_admin.py`, `contracts/views_domains/actions.py`, `theme/templates/contracts/reports_dashboard.html` | Medium | Core analytics already exist | Reports can be exported in a usable format and validated in tests |
| Strengthen integration observability | External integrations are only valuable if failures are explainable | `contracts/services/salesforce.py`, `contracts/services/netsuite.py`, `contracts/services/webhooks.py`, `contracts/api/views.py` | Large | Existing sync and webhook code | Failed syncs / deliveries have clear diagnostics and a visible support trail |
| Improve AI drafting / citation quality | AI helpers should support drafting without becoming opaque or risky | `contracts/services/ai_actions.py`, `contracts/services/ai_policy.py`, `contracts/views_domains/contracts.py` | Medium | Current AI assistant behavior | AI output is citeable, bounded, and easy to reject or audit |

## Phase 5: Production Readiness

| Task | Why It Matters | Affected Files / Modules | Complexity | Dependency | Acceptance Criteria |
|---|---|---|---|---|---|
| Complete a real backup / restore rehearsal | This is rollback proof, not optional polish | `docs/ROLLBACK_RUNBOOK.md`, `docs/STAGING_POSTGRES_REHEARSAL.md`, deploy host / database | Large | Stable PostgreSQL target | Backup, restore, and post-restore verification all complete successfully |
| Complete a rollback rehearsal | A rollback plan is only real if it has been exercised | `docs/ROLLBACK_RUNBOOK.md`, release workflow, deployment target | Medium | Backup/restore proof | Rollback is demonstrated with timing and evidence |
| Automate release evidence capture | Manual evidence is too easy to lose or forget | `docs/RELEASE_EVIDENCE_POLICY.md`, CI workflows, release gate commands | Medium | Stable smoke and integration checks | Evidence is attached to the release in a repeatable way |
| Re-run live smoke on the real deployment target | Local success is not enough for rollout confidence | `docs/MANUAL_SMOKE_CHECKLIST.md`, browser smoke workflow | Medium | Live deployment | Signup, login, contract CRUD, search, workflow, and logout pass live |

## Phase 6: Nice-To-Have Improvements

| Task | Why It Matters | Affected Files / Modules | Complexity | Dependency | Acceptance Criteria |
|---|---|---|---|---|---|
| Tune semantic search relevance | Makes the repository feel smarter without changing the core model | `contracts/services/semantic_search.py`, `contracts/views_domains/repository_management.py` | Small | Search presets already exist | Search results are more relevant and predictable |
| Add admin support tooling | Support teams need better visibility into org health and recovery paths | `contracts/views_domains/organization_admin.py`, `contracts/views_domains/actions.py` | Medium | Identity/security groundwork | Admins can troubleshoot users, sessions, and integrations faster |
| Profile and trim query-heavy paths | The large app should stay fast as data grows | `contracts/views_domains/*`, `contracts/api/views.py`, indexes / migrations | Medium | Stable release flow | Core pages remain responsive under realistic data volume |

## Practical Ordering

1. Close release evidence gaps.
2. Remove the obvious frontend advisory and placeholder actions.
3. Polish the highest-value core flows: signature, workflow, search.
4. Improve reporting and integration diagnostics.
5. Finish rollback and restore proof.
6. Then move to nice-to-have refinements.
