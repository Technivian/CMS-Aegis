# Security Vulnerability SLA Policy

## Purpose

Define a repeatable operating policy for vulnerability triage, remediation timelines, escalation, and evidence capture.

## Severity Windows

- `P0`: remediate or mitigate within `24 hours`
- `P1`: remediate or mitigate within `7 days`
- `P2`: remediate or mitigate within `30 days`

## Scope

- Python runtime dependency vulnerabilities (`pip-audit` on `requirements/runtime.txt`)
- JavaScript dependency vulnerabilities (`npm audit --audit-level=high` for `client` and `theme/static_src`)
- High-severity static findings (`bandit -lll`)

## Enforcement

- Pull-request merge gates enforce high-severity checks via `platform-guardrails`.
- Weekly governance cycle is automated via:
  - `.github/workflows/security-sla-watch.yml`
- On breach, workflow opens or updates issue:
  - Title: `[Security] SLA Breach Detected`
  - Labels: `security`, `governance`, `sla`

## Triage Flow

1. Identify failing scanner and vulnerable package/code path.
2. Assign owner and classify severity (`P0/P1/P2`).
3. Record due date based on SLA window.
4. Apply fix or temporary mitigation.
5. Re-run scanner and attach evidence.
6. Close issue only after scanner passes and remediation evidence is attached.

## Evidence Requirements

- Scanner command outputs.
- Timestamped summary of pass/fail status.
- Linked PR/commit implementing remediation.
- Exception record with expiry date for any temporary suppression.
