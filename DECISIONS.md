# CMS Aegis Decisions

## Canonical Documentation

- `README_CMS_AEGIS.md` is the single operational overview for setup, running, auth, reminders, and tests.
- `DECISIONS.md` is the single decisions log.
- Duplicate or stale handover docs are removed instead of being kept as parallel sources of truth.

## Multi-Tenant Authorization

- Organization membership is the basis of tenant access.
- Roles are `OWNER`, `ADMIN`, and `MEMBER`.
- Contract permission logic is centralized in `contracts/permissions.py`.
- `VIEW`, `COMMENT`, and `AI` actions are allowed for any active organization member.
- `EDIT` is restricted to owners/admins and the contract creator.

## Reminder Execution Model

- Renewal and expiration reminders run through management commands, not cron-specific code.
- `send_contract_reminders` performs one-off creation.
- `run_reminder_scheduler` runs the same logic in a long-lived loop.
- The web server and reminder scheduler are intentionally separate processes.

## Local Development Workflow

- Default local app URL is `http://127.0.0.1:8060`.
- `scripts/dev_up.sh` starts or adopts the dev server on port `8060` and starts the reminder scheduler.
- `scripts/dev_down.sh` stops both processes using pid files under `logs/`.

## Auth and Routing

- Login route is `/login/`, not `/accounts/login/`.
- Register route is `/register/`.
- Post-login redirect is `/dashboard/`.

## UI and Test Compatibility

- The redesign contract list and dashboard markers covered by the test suite are part of the supported UI surface.
- Template changes should preserve tested user-facing markers unless the tests are intentionally updated in the same change.
- Light/dark mode on auth pages is implemented with CSS variables rather than hardcoded colors.
