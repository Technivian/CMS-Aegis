# Design System Remediation Matrix

## Goal

Converge the UI onto one runtime design system:

1. `theme/static/css/zorgregie-design-system.css` as the canonical semantic layer
2. `theme/static/css/careon-premium-theme.css` as the theme override layer
3. semantic `ds-*` classes in templates as the preferred authoring model

## Current Decisions

### Canonical

- Keep `base.html` as the primary shell.
- Keep `zorgregie-design-system.css` as the source of truth for shared primitives.
- Keep `careon-premium-theme.css` as the premium token and override layer.
- Prefer semantic classes over raw page-local utility bundles for repeated patterns.

### Transitional

- Allow Tailwind utility classes only as a migration bridge inside existing templates.
- Allow page-local layout utilities where no semantic primitive exists yet.
- Keep `theme/static_src/` until the team decides whether to generate and ship real output or remove the dead pipeline.

### Deprecated

- `theme/static/css/theme-careon.css`
- `theme/templates/base_redesign.html`
- inline `style="..."` attributes in templates
- repeated page-local `<style>` blocks for cards, filters, list rows, and detail shells

## Execution Order

### P0: Shared primitives

- Define all documented `ds-*` detail-page primitives in `zorgregie-design-system.css`.
- Remove inline-style dependencies from high-traffic detail pages.
- Verify premium theme coverage against semantic classes rather than page-specific overrides.

### P1: Core workflow detail pages

- `theme/templates/contracts/intake_detail.html`
- `theme/templates/contracts/assessment_detail.html`
- `theme/templates/contracts/matching_dashboard.html`
- `theme/templates/contracts/placement_detail.html`

### P2: Drift-heavy operational pages

- `theme/templates/contracts/budget_detail.html`
- `theme/templates/contracts/configuration_detail.html`
- `theme/templates/contracts/document_detail.html`
- `theme/templates/contracts/search_results.html`

### P3: Form and list shells

- migrate repeated list-shell classes to a real semantic list system
- remove remaining page-local `<style>` blocks
- decide whether `theme/static/css/dist/styles.css` becomes a real build artifact or is removed from the shell

## File Priority Matrix

| File | Current State | Risk | Action |
| --- | --- | --- | --- |
| `theme/templates/contracts/intake_detail.html` | mixed semantic + utility + inline hooks | high | migrate first, remove inline styles, validate flow |
| `theme/templates/contracts/budget_detail.html` | heavy inline colors and layout | high | replace inline styles with semantic cards and token classes |
| `theme/templates/contracts/configuration_detail.html` | heavy inline layout and typography | high | replace with semantic detail card, field list, and info card primitives |
| `theme/templates/contracts/matching_dashboard.html` | mixed systems, important flow | high | align with same detail primitives as intake and client pages |
| `theme/templates/contracts/client_detail.html` | close to target, semantic classes missing runtime definitions until now | medium | keep as reference page and validate after shared CSS changes |
| `theme/templates/base_redesign.html` | dormant alternate shell | medium | confirm no active use, then remove |
| `theme/static/css/theme-careon.css` | legacy theme layer, likely unused | medium | verify zero runtime references, then delete |
| `theme/static/css/dist/styles.css` | empty artifact | medium | either generate it in CI/dev or stop loading it |

## Acceptance Criteria

- no new detail-page work uses inline `style` attributes
- all repeated detail-page structures use documented semantic classes
- premium theme renders semantic classes without page-specific exceptions
- legacy theme files are no longer loaded or referenced
- active shells are reduced to one supported base template

## Progress Log

- 2026-04-14 pass 1: shared `ds-*` detail primitives added in `zorgregie-design-system.css`; `intake_detail.html` migrated.
- 2026-04-14 pass 2: `budget_detail.html` and `configuration_detail.html` migrated to semantic detail patterns; `matching_dashboard.html` moved to semantic card/sidebar wrappers.

## Validation Checklist

- targeted Django route tests for affected detail pages
- shell verification via `bash scripts/dev_up.sh --verify`
- visual spot-check of dashboard, intake, assessment, matching, and placement flows
- grep count for inline `style="` in `theme/templates` trends down after each pass
