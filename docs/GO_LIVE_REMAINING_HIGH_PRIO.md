# Remaining High-Priority Launch Work

This board only tracks the items that still matter for go-live after the local code, audit, and migration checks passed.

## Status Summary

- Code, deploy checks, and tenant isolation are green.
- Dependency audits are green.
- The Postgres rehearsal is green end to end.
- Remaining blockers are only the real production cutover steps.

## Board

| # | Item | Status | Why It Matters | Finish Line |
|---|---|---|---|---|
| 1 | Release gate evidence | Done in rehearsal | This is the canonical go/no-go check for launch | `generate_release_gate_report --fail-on-no-go` returns `GO` on production target |
| 2 | Salesforce sync evidence | Done in rehearsal | Release gate needs a recent successful sync | `generate_sprint3_integration_report` returns `GO` on live data |
| 3 | Webhook delivery evidence | Done in rehearsal | Release gate and integration report need sent webhook evidence | A `SENT` webhook exists in the production window |
| 4 | E-sign evidence | Done in rehearsal | Go-live evidence now includes e-sign integration proof | `generate_esign_integration_report` returns `GO` on live data |
| 5 | Staging smoke | Done in rehearsal | Validates tenant isolation in a real operator flow | Manual smoke checklist passes in staging or production-like env |
| 6 | Backup artifact | Done in rehearsal | Needed before any rollback-safe cutover | Fresh backup exists and is retained |
| 7 | Restore rehearsal | Done in rehearsal | Proves rollback path before production cutover | Backup restores cleanly and checks re-pass |
| 8 | Postgres cutover verification | Done in rehearsal | Confirms target DB engine and migration state | `verify_postgres_cutover` returns ready |
| 9 | Production deploy | Pending | The actual cutover step | Deploy completes and the app comes back clean |
| 10 | Post-deploy smoke | Pending | Final safety check before traffic fully returns | Live smoke passes and traffic is reopened |
