# CMS Aegis - Legal Practice Management System

## Overview
A production-grade Django-based legal CLM/CMS platform with comprehensive features for law firm operations, GDPR compliance, contract lifecycle management, and AI-ready architecture. EU + US jurisdiction aware.

## Tech Stack
- **Backend**: Django 5.2.5, Python 3.12
- **Database**: SQLite (dev), PostgreSQL-ready
- **Frontend**: Tailwind CSS (CDN), Alpine.js
- **Server**: Django dev server on port 5000

## Project Structure
```
config/           - Django settings, URLs, feature flags
contracts/        - Main app: models, views, forms, middleware, URLs
  models.py       - 30+ models covering full legal CLM/CMS
  views.py        - All CRUD views + dashboards
  forms.py        - All Django ModelForms with Tailwind styling
  urls.py         - All URL patterns (app_name: 'contracts')
  middleware.py   - Audit trail middleware
  api/            - API endpoints
  management/commands/seed_data.py - Database seeder
theme/templates/  - All HTML templates
  base.html       - Main layout with sidebar navigation (dark/light mode)
  base_fullscreen.html - Fullscreen layout (login/register/landing)
  dashboard.html  - Analytics dashboard
  landing.html    - Premium landing page
  registration/   - Login, register, logout
  contracts/      - All feature templates (60+ templates)
media/            - Uploaded files (documents)
```

## Core Modules (PRD Aligned)

### Identity & Access Management (4.1)
- RBAC: Admin, Partner, Senior Associate, Associate, Paralegal, Legal Assistant, Client roles
- Session management, login/register/logout
- Ethical walls with restricted user lists

### Client / Matter / Entity Management (4.2)
- Client: Corporate/Individual with attorneys, contacts, industry
- Matter: Practice areas, billing types, budgets, opposing counsel
- Counterparty: Entity registry with jurisdiction tracking

### Contract Repository (4.3)
- Contract types: NDA, MSA, SOW, Employment, Lease, License, Vendor, etc.
- Full metadata: governing law, jurisdiction, language, risk level, currency
- Data transfer flags, DPA/SCC attachment tracking
- Lifecycle stages: Drafting → Archived (9 stages)
- Auto-renewal, notice periods, termination dates

### Document Lifecycle Management (4.4)
- Upload with versioning (parent_document chain)
- Status workflow: Draft → Review → Approved → Final → Archived
- Privileged/confidential flags
- Tags, MIME type tracking

### Approval Workflow Engine (4.5)
- Conditional approval rules (value, jurisdiction, contract type, risk level, data transfer)
- Multi-step approvals (Legal, Finance, Privacy, Executive, Compliance)
- SLA tracking and escalation timers
- Role-based and specific-approver assignment

### Clause Library & Template Engine (4.6)
- Clause categories with ordering
- Clause templates with jurisdiction scope (EU, US, UK, Global)
- Mandatory clause flagging
- Fallback positions for negotiation
- Playbook notes for each clause
- Version tracking, approval status

### Obligation & Deadline Tracking (4.7)
- Deadline types: Court Filing, Regulatory, Contract Renewal, Statute of Limitations
- Priority levels with reminder days
- Completion tracking

### Search & Discovery (4.8)
- Global search across contracts, clients, matters, documents, clauses, counterparties
- Search bar in top navigation
- Metadata filtering per module

### Audit Logging & Compliance (4.9)
- Middleware-based action logging (create, update, delete, view, login, logout)
- User, IP address, user agent tracking
- JSON diff of changes
- Exportable audit trail

### E-Signature Integration (4.10)
- Signature request tracking (Pending → Sent → Viewed → Signed/Declined)
- Multi-signer support with ordering
- External provider reference ID
- Execution certificate URL tracking

### Privacy & GDPR Module (4.11)
- **Privacy Dashboard**: Centralized compliance center
- **Data Inventory (RoPA)**: Lawful basis, retention, DPIA tracking
- **DSAR Workflows**: Access, Rectification, Erasure, Restrict, Portability, Objection
- **Subprocessor Registry**: DPA/SCC/DPF status, risk assessment
- **Transfer Records**: Cross-border data transfers with mechanisms (SCC, BCR, DPF, adequacy)
- **Retention Policies**: Per-category retention with auto-delete
- **Legal Holds**: Active hold management with custodians and scope
- **Ethical Walls**: Conflict restrictions with user access control

### Additional Modules
- **Time Tracking**: Billable hours by activity type with rate tracking
- **Invoicing**: Draft/Sent/Paid/Overdue with tax support
- **Trust Accounts (IOLTA)**: Deposits, withdrawals, disbursements with balance tracking
- **Budgets**: Department/matter budgets with expense tracking
- **Due Diligence**: Multi-task processes with risk assessment
- **Compliance Checklists**: Regulation-type checklists with item tracking
- **Legal Tasks**: Kanban-style task management
- **Risk Logs**: Contract/operational risk tracking with mitigation
- **Trademarks**: IP filing request tracking
- **Workflows**: Template-based multi-step workflow engine
- **Notifications**: In-app notification system
- **Reports/Analytics**: Dashboard with KPIs

## Authentication
- Login: `/login/`
- Register: `/register/`
- Logout: `/logout/`
- Default admin: `admin` / `admin123`
- Other users: `jsmith/password123`, `sjones/password123`, `mwilson/password123`
- LOGIN_URL = `/login/`
- LOGIN_REDIRECT_URL = `/dashboard/`

## URL Structure
- `/` - Landing page (or redirects to dashboard if authenticated)
- `/dashboard/` - Main analytics dashboard
- `/contracts/` - Contract list
- `/contracts/clients/` - Client management
- `/contracts/matters/` - Matter management
- `/contracts/documents/` - Document management
- `/contracts/counterparties/` - Counterparty registry
- `/contracts/clause-library/` - Clause templates
- `/contracts/clause-categories/` - Clause categories
- `/contracts/signatures/` - E-signature requests
- `/contracts/approvals/` - Approval requests
- `/contracts/approval-rules/` - Approval workflow rules
- `/contracts/ethical-walls/` - Ethical wall restrictions
- `/contracts/privacy/` - Privacy & GDPR dashboard
- `/contracts/privacy/data-inventory/` - Data inventory (RoPA)
- `/contracts/privacy/dsar/` - DSAR requests
- `/contracts/privacy/subprocessors/` - Subprocessor registry
- `/contracts/privacy/transfers/` - Data transfer records
- `/contracts/privacy/retention/` - Retention policies
- `/contracts/privacy/legal-holds/` - Legal holds
- `/contracts/time/` - Time entries
- `/contracts/invoices/` - Invoicing
- `/contracts/trust-accounts/` - Trust/IOLTA accounts
- `/contracts/deadlines/` - Deadline tracking
- `/contracts/conflicts/` - Conflict checks
- `/contracts/search/` - Global search
- `/contracts/audit-log/` - Audit trail
- `/contracts/notifications/` - Notifications
- `/contracts/reports/` - Reports dashboard
- `/contracts/workflows/` - Workflow management
- `/contracts/compliance/` - Compliance checklists
- `/contracts/due-diligence/` - Due diligence
- `/contracts/risks/` - Risk logs
- `/contracts/trademarks/` - Trademark requests
- `/contracts/budgets/` - Budget management
- `/contracts/legal-tasks/` - Legal task board
- `/profile/` - User profile

## Design System
- Dark theme: `#0B0F19` bg, `#111827` surface, `#2563EB` primary, `#22C55E` accent
- Light/dark toggle with localStorage persistence
- CSS custom properties for theming
- Tailwind CDN with inline style overrides for dark mode compatibility

## Running
```bash
python manage.py migrate
python manage.py seed_data   # Creates sample data
python manage.py runserver 0.0.0.0:5000
```

## Workflow
- **Django Server**: `python manage.py migrate && python manage.py runserver 0.0.0.0:5000`
- **Local Orchestration (server + reminders)**:
  - `bash scripts/dev_up.sh` (default 60-minute reminder interval)
  - `bash scripts/dev_up.sh 15` (run reminders every 15 minutes)
  - `bash scripts/dev_down.sh`
