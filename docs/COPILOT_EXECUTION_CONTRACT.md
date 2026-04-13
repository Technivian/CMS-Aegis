# Copilot Execution Contract

Use this contract for all implementation requests to reduce rework and ensure verifiable outcomes.

## 1) Request Format
Include these five blocks in your prompt:

- Objective: one sentence describing desired end state.
- Scope: exact files/routes/components allowed to change.
- Acceptance criteria: 3-7 testable statements.
- Validation commands: exact commands to run.
- Evidence required: what proof to include in final response.

Example:

Objective: Fix new-case form layout and accessibility label links.
Scope: theme/templates/contracts/intake_form.html, contracts/forms.py, tests/test_ui_click_integrity.py
Acceptance criteria:
1. New-case page renders updated subtitle text.
2. All labels on new-case page map to existing element ids.
3. Targeted tests pass.
Validation commands:
1. .venv/bin/python manage.py test tests.test_ui_click_integrity
2. .venv/bin/python scripts/terminology_guard.py
Evidence required:
1. Served subtitle value from /care/casussen/new/
2. Test summary lines

## 2) Copilot Must Follow
For each task, Copilot must:

1. Restate objective + acceptance criteria before edits.
2. Implement smallest coherent patch.
3. Run validation commands.
4. Report pass/fail against each acceptance criterion.
5. Include concrete evidence (key command output and affected file links).

## 3) Stop Conditions
Copilot must stop and ask for direction only when:

1. A blocker prevents satisfying acceptance criteria.
2. Required environment/tool is unavailable.
3. Request conflicts with repository policy constraints.

## 4) Definition of Done
A task is done only when all are true:

1. Acceptance criteria are all marked PASS.
2. Required validation commands were run and reported.
3. Terminology guard passes for template/python changes.
4. Final response includes changed files and residual risks.

## 5) Recommended Prompt Shortcut
Use:
- .github/prompts/deterministic-execution.prompt.md

This enforces consistent task input and consistent evidence output.
