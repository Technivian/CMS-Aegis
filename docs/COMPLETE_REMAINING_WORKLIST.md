# Remaining Worklist

Last updated: 2026-04-14

Source of truth:
- [`docs/MASTER_TODO_CMS_AEGIS_PARITY.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/MASTER_TODO_CMS_AEGIS_PARITY.md)
- [`docs/STABILIZATION_BACKLOG_30_DAYS.md`](/Users/haroonwahed/Documents/Projects/CMS-Aegis/docs/STABILIZATION_BACKLOG_30_DAYS.md)

This list contains every task that is still open, partial, or queued for follow-on work. Completed items are omitted.

## Immediate Queue

- No ticketed items remain in the immediate queue.

## Identity And Access

- `SAML` support
- `SCIM` user/group provisioning
- `MFA` enforcement, especially for admins

## Contract Core

- End-to-end lifecycle states from draft to archive
- Versioned documents and immutable history
- Upload + OCR pipeline

## Workflow Engine

- Conditional workflow routing by value, jurisdiction, and type
- Multi-step approvals for legal, finance, and privacy
- SLA, escalation, reassignment, and delegation flows

## Clause And Playbook Layer

- Jurisdictional clause variants and fallback positions
- Mandatory clause enforcement policies
- Playbooks for negotiation fallback language
- Clause usage analytics and dependency graph

## Obligation And Renewal Operations

- Renewal playbooks and auto-generated tasks
- Configurable reminder cadence by contract type and priority
- Expanded obligation taxonomy and playbooks

## Search, Analytics, And Repository UX

- Full-text plus metadata faceted search
- Semantic/AI search over clauses and contracts
- Repository dashboards and saved views
- Executive analytics for cycle time, bottlenecks, and risk trends
- Ranking quality controls and relevance telemetry

## Privacy And Compliance Ops

- Data inventory cross-references to processing systems and subprocessors
- DSAR SLA countdown and evidence bundle export
- Subprocessor and transfer auto-alerts for expired agreements and risk flags
- Retention execution jobs and immutable action logs
- Tamper-evident compliance/audit evidence exports

## Integrations And Platform

- E-sign provider integration with webhook reconciliation
- Webhook platform with retries, dead-letter queue, and diagnostics UI
- Public API versioning, scoped tokens, and pagination standards
- CRM/ERP integrations
- Inbound import APIs and mapping tools

## AI Governance And Actions

- Prompt-injection controls and output policy engine
- AI summarization/risk extraction with citations
- AI-assisted drafting and clause recommendations
- Agentic AI actions with approval gates and rollback logs
- AI governance with model registry, safety policies, and red-team tests

## Reliability And Operations

- Postgres production cutover completion
- Async job system for reminders, OCR, and integrations
- Sink-specific observability transport
- Clear high CVEs and enforce scanner gates
- Recurring restore drills with RTO/RPO evidence

## Product And Commercial Readiness

- Enterprise admin console for org settings, policy controls, and integrations
- Permission transparency UI for record-level access
- Self-serve onboarding and guided setup
- Billing, subscription, and usage controls
- Customer-facing trust/compliance portal artifacts

## Execution Order

1. Finish the immediate queue.
2. Close identity and access hardening.
3. Complete workflow, clause, and document depth.
4. Add search, analytics, and compliance operability.
5. Finish integrations, AI governance, and commercial readiness.
