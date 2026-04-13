# Careon – Copilot Instructions (Compact)

## Project Essentials

- Stack: Django 5.2.5, Python 3.15, Tailwind; SQLite (dev), PostgreSQL (prod)
- Core app: `contracts/`
- URL namespace: `careon:` (mounted at `/care/`)
- Templates: `theme/templates/`; CSS source: `theme/static_src/src/`
- Dev run: `bash scripts/dev_up.sh`
- Tests: `python manage.py test tests/`
- Terminology check: `python scripts/terminology_guard.py`

## Authoritative Domain Map

- Case: `CareCase` (root object)
- Intake process: `CaseIntakeProcess`
- Assessment: `CaseAssessment`
- Indication/placement request: `PlacementRequest`
- Tasks: `Deadline`, `CareTask`
- Provider: `Client` (+ `ProviderProfile`)
- Case signals: `CareSignal`, `CaseRiskSignal`
- Budget: `Budget`, `BudgetExpense`
- Workflow: `Workflow`, `WorkflowStep`
- Tenant root: `Organization`, `OrganizationMembership`
- Config entities (not cases): `MunicipalityConfiguration`, `RegionalConfiguration`

Legacy technical debt (`TrustAccount`, `CareConfiguration`) should not drive new UX flows.

## Mandatory Care Flow

`CASE -> INTAKE -> ASSESSMENT -> MATCHING -> INDICATION -> PLACEMENT -> FOLLOW-UP`

Views/forms/urls/templates must reinforce this linear flow and always offer navigation back to parent case.

## Non-Negotiables

- Preserve existing UI system (dark shell, sidebar, cards, hierarchy).
- Use care-native terminology only in user-facing text.
- Never route case UX to config models.
- In templates, always use `careon:` namespace.
- After Python/template edits, run `python scripts/terminology_guard.py`.

## Vocabulary Rules

- Preferred terms: case/casus, intake, assessment/beoordeling, matching, indication, placement, follow-up/opvolging, providers, municipalities, regions, wait times, capacity, budget, coordination, privacy.
- Banned user-facing legacy terms include: contract, matter, legal, filing, counterparty, trust account, billing, attorney, court name.

## UX Expectations

- Next action must be obvious on every screen.
- Empty states must direct the user clearly.
- Keep one clear “Nieuwe casus” entry point.
- Intake/assessment/indication/placement are subflows inside a case, not top-level sidebar sections.

## Execution Protocol

For implementation requests:

1. Inspect relevant files first.
2. Restate objective and acceptance criteria.
3. Apply the smallest coherent patch.
4. Validate and summarize key command output.
5. Report PASS/FAIL per acceptance criterion.

Reference artifacts:

- `.github/prompts/deterministic-execution.prompt.md`
- `docs/COPILOT_EXECUTION_CONTRACT.md`

Definition of done: acceptance criteria pass, validations are reported, and terminology guard passes when applicable.
