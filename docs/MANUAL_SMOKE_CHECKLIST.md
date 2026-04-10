# CMS Aegis Manual Smoke Checklist

## Purpose

Use this checklist before a release, after a migration, or after a rollback. It validates the highest-risk tenant and permission flows with two organizations and multiple roles.

## Test Accounts

Create or confirm these accounts in staging or a staging-like environment:

- `org-a-owner`: `OWNER` in Org A
- `org-a-admin`: `ADMIN` in Org A
- `org-a-member`: `MEMBER` in Org A
- `org-b-owner`: `OWNER` in Org B

## Required Seed Data

Before starting, confirm each organization has at least:

- one contract
- one workflow linked to a contract
- one clause template
- one counterparty
- one privacy data inventory record
- one approval request
- one legal hold

Use distinct names so records are easy to identify, for example `Org A Contract` and `Org B Contract`.

## Pass Criteria

- Every allowed action succeeds and shows only in-org data.
- Every denied action returns `403`, `404`, redirect to login, or a clear in-product denial message.
- No Org A page reveals Org B object names, counts, CSV rows, or linked records.
- No anonymous route exposes authenticated dashboard data.

## 1. Authentication And Session Baseline

1. Open `/dashboard/` while logged out.
Expected: redirect to `/login/`.

2. Log in as `org-a-owner`.
Expected: login succeeds and dashboard loads.

3. Log out, then log in as `org-b-owner`.
Expected: login succeeds and only Org B data is visible.

## 2. Dashboard Isolation

1. As `org-a-owner`, open `/dashboard/`.
Expected: cards, recent items, workflow counts, privacy counts, and search suggestions reference only Org A records.

2. As `org-b-owner`, open `/dashboard/`.
Expected: no Org A contract, workflow, or privacy names appear anywhere on the page.

## 3. Contract Permissions

1. As `org-a-member`, open `/contracts/`.
Expected: Org A contracts are visible.

2. As `org-a-member`, open `/contracts/<org-a-contract-id>/`.
Expected: detail page loads.

3. As `org-a-member`, open `/contracts/<org-a-contract-id>/edit/` for a contract created by someone else.
Expected: access denied.

4. As `org-a-owner`, open `/contracts/<org-a-contract-id>/edit/`.
Expected: edit page loads.

5. As `org-b-owner`, open `/contracts/<org-a-contract-id>/`.
Expected: `404` or equivalent hidden-object response.

## 4. Workflow Isolation

1. As `org-a-owner`, open `/contracts/workflows/`.
Expected: only Org A workflows appear.

2. Open `/contracts/workflows/<org-a-workflow-id>/`.
Expected: detail page loads and step list matches Org A only.

3. As `org-a-member`, try to create a workflow for a contract they did not create via `/contracts/workflows/create/`.
Expected: access denied if the route requires contract edit permission.

4. As `org-b-owner`, open `/contracts/workflows/<org-a-workflow-id>/`.
Expected: `404`.

5. As `org-b-owner`, try to update `/contracts/workflows/step/<org-a-step-id>/update/`.
Expected: `404` or `403`; the step must not update.

## 5. Clause And Counterparty Isolation

1. As `org-a-owner`, open `/contracts/counterparties/`.
Expected: only Org A counterparties appear.

2. As `org-a-owner`, open `/contracts/clause-library/`.
Expected: only Org A clause templates appear.

3. Create a new clause template in Org A and assign it to an Org A category.
Expected: save succeeds.

4. Attempt to submit the clause template form with an Org B category ID.
Expected: validation error or denial; no cross-org linkage is saved.

5. As `org-b-owner`, confirm the newly created Org A clause template is not visible.

## 6. Privacy Isolation

1. As `org-a-owner`, open `/contracts/privacy/`.
Expected: privacy dashboard counts reflect only Org A data.

2. Open `/contracts/privacy/data-inventory/`, `/contracts/privacy/dsar/`, `/contracts/privacy/subprocessors/`, and `/contracts/privacy/legal-holds/`.
Expected: only Org A records appear.

3. Edit one Org A privacy record.
Expected: update succeeds.

4. As `org-b-owner`, open the Org A privacy record detail or edit route directly.
Expected: `404`.

5. Attempt a POST from Org A that references an Org B foreign key, such as subprocessor or client.
Expected: form rejection; no cross-org save.

## 7. Approval Isolation

1. As `org-a-owner`, open `/contracts/approvals/` and `/contracts/approval-rules/`.
Expected: only Org A requests and rules appear.

2. As `org-a-admin`, edit an Org A approval rule.
Expected: update succeeds if the route allows org admins to manage it.

3. As `org-b-owner`, try to open the Org A approval request edit page directly.
Expected: `404`.

4. Attempt to submit an approval request in Org A using an Org B rule ID.
Expected: form rejection; no cross-org link.

## 8. Organization Administration Matrix

1. As `org-a-member`, open `/contracts/organizations/team/`.
Expected: `403`.

2. As `org-a-admin`, open `/contracts/organizations/team/`.
Expected: page loads.

3. As `org-a-admin`, invite a new user as `MEMBER`.
Expected: invitation is created.

4. As `org-a-admin`, try to promote an existing member to `OWNER`.
Expected: blocked; role remains unchanged.

5. As `org-a-owner`, promote a member to `ADMIN`.
Expected: role update succeeds.

6. As `org-a-member`, open `/contracts/organizations/activity/` and `/contracts/organizations/activity/export/`.
Expected: `403`.

7. As `org-a-admin`, open both organization activity pages.
Expected: page load and CSV export succeed.

## 9. Search Isolation

1. As `org-a-owner`, search for a unique Org A contract or clause name in `/contracts/search/?q=<term>`.
Expected: matching Org A results appear.

2. Search for a unique Org B object name while still logged in as `org-a-owner`.
Expected: no Org B results appear.

## 10. Post-Check Signoff

Record:

- environment tested
- app commit SHA
- migration state from `python manage.py showmigrations contracts`
- tester name
- date and time
- failures or anomalies

Release signoff should not proceed with any unexplained cross-org visibility, failed deny case, or unexpected anonymous access.
