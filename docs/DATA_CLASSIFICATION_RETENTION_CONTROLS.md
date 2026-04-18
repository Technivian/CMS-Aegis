# Data Classification and Retention Controls

## Objective

Document current controls for data classification and retention execution evidence required by ICL-012.

## Classification Baseline

- Contract and matter records are tenant-scoped (`organization` boundary).
- Privacy-sensitive workflows are modeled explicitly:
  - `DataInventoryRecord`
  - `DSARRequest`
  - `TransferRecord`
  - `Subprocessor`
  - `RetentionPolicy`
  - `LegalHold`

## Retention and Hold Controls

- Retention policy tracking is available through `RetentionPolicy` CRUD workflows.
- Legal hold issuance and updates are tracked through `LegalHold` workflows.
- Reminder scheduler and observability checks provide operational visibility for timed controls.

## Auditability

- Organization-level activity export provides CSV evidence for governance audits.
- Security and observability drill logs are captured in `docs/DRILL_LOG.md`.
- Release evidence policy and RC artifacts are enforced for deploy gates.

## Evidence Artifacts

- Security SLA cycle report: `docs/SECURITY_SLA_CYCLE_2026-04-13.md`
- Security SLA policy: `docs/SECURITY_SLA_POLICY.md`
- Observability fire-drill entries: `docs/DRILL_LOG.md`

## Next Controls to Implement

1. Automatic retention execution jobs with immutable execution logs.
2. Data-class tags at field/object level for downstream export minimization.
3. Quarterly control attestations with signed reviewer approvals.
