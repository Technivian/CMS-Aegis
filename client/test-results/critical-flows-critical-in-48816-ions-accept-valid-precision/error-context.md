# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: critical-flows.spec.js >> critical invoice and time-entry submissions accept valid precision
- Location: tests/e2e/critical-flows.spec.js:58:1

# Error details

```
Error: expect(page).toHaveURL(expected) failed

Expected pattern: /\/contracts\/time\/?$/
Received string:  "http://127.0.0.1:8010/contracts/time/new/"
Timeout: 5000ms

Call log:
  - Expect "toHaveURL" with timeout 5000ms
    9 × unexpected value "http://127.0.0.1:8010/contracts/time/new/"

```

# Page snapshot

```yaml
- generic [ref=e1]:
  - generic [ref=e2]:
    - link "CMS Aegis Legal" [ref=e4] [cursor=pointer]:
      - /url: /dashboard/
      - img [ref=e6]
      - generic [ref=e8]: CMS Aegis Legal
    - generic [ref=e9]:
      - generic [ref=e10]: E2E Org
      - link "Search" [ref=e11] [cursor=pointer]:
        - /url: /contracts/search/
        - img [ref=e12]
      - link "Organization team" [ref=e14] [cursor=pointer]:
        - /url: /contracts/organizations/team/
        - img [ref=e15]
      - link "Settings" [ref=e17] [cursor=pointer]:
        - /url: /settings/
        - img [ref=e18]
      - button "Toggle theme" [ref=e21] [cursor=pointer]:
        - img [ref=e22]
      - link "Notifications" [ref=e24] [cursor=pointer]:
        - /url: /contracts/notifications/
        - img [ref=e25]
      - link "New" [ref=e27] [cursor=pointer]:
        - /url: /contracts/new/
        - img [ref=e28]
        - text: New
      - generic [ref=e31]:
        - link "E e2e_owner" [ref=e32] [cursor=pointer]:
          - /url: /profile/
          - generic [ref=e33]: E
          - generic [ref=e34]: e2e_owner
        - button "Logout" [ref=e36] [cursor=pointer]
  - generic [ref=e37]:
    - navigation [ref=e38]:
      - generic [ref=e39]:
        - generic [ref=e40]: Main
        - link "Dashboard" [ref=e41] [cursor=pointer]:
          - /url: /dashboard/
          - img [ref=e42]
          - text: Dashboard
        - link "Settings" [ref=e44] [cursor=pointer]:
          - /url: /settings/
          - img [ref=e45]
          - text: Settings
        - generic [ref=e48]: Client Management
        - link "Clients" [ref=e49] [cursor=pointer]:
          - /url: /contracts/clients/
          - img [ref=e50]
          - text: Clients
        - link "Matters" [ref=e52] [cursor=pointer]:
          - /url: /contracts/matters/
          - img [ref=e53]
          - text: Matters
        - link "Conflict Checks" [ref=e55] [cursor=pointer]:
          - /url: /contracts/conflicts/
          - img [ref=e56]
          - text: Conflict Checks
        - generic [ref=e58]: Contracts & Docs
        - link "Contracts" [ref=e59] [cursor=pointer]:
          - /url: /contracts/
          - img [ref=e60]
          - text: Contracts
        - link "Documents" [ref=e62] [cursor=pointer]:
          - /url: /contracts/documents/
          - img [ref=e63]
          - text: Documents
        - link "Repository" [ref=e65] [cursor=pointer]:
          - /url: /contracts/repository/
          - img [ref=e66]
          - text: Repository
        - generic [ref=e68]: Billing & Finance
        - link "Time Tracking" [ref=e69] [cursor=pointer]:
          - /url: /contracts/time/
          - img [ref=e70]
          - text: Time Tracking
        - link "Invoices" [ref=e72] [cursor=pointer]:
          - /url: /contracts/invoices/
          - img [ref=e73]
          - text: Invoices
        - link "Trust Accounts" [ref=e75] [cursor=pointer]:
          - /url: /contracts/trust-accounts/
          - img [ref=e76]
          - text: Trust Accounts
        - link "Budgets" [ref=e78] [cursor=pointer]:
          - /url: /contracts/budgets/
          - img [ref=e79]
          - text: Budgets
        - generic [ref=e81]: Operations
        - link "Tasks" [ref=e82] [cursor=pointer]:
          - /url: /contracts/legal-tasks/
          - img [ref=e83]
          - text: Tasks
        - link "Deadlines" [ref=e85] [cursor=pointer]:
          - /url: /contracts/deadlines/
          - img [ref=e86]
          - text: Deadlines
        - link "Workflows" [ref=e88] [cursor=pointer]:
          - /url: /contracts/workflows/
          - img [ref=e89]
          - text: Workflows
        - generic [ref=e91]: Risk & Compliance
        - link "Risks" [ref=e92] [cursor=pointer]:
          - /url: /contracts/risks/
          - img [ref=e93]
          - text: Risks
        - link "Compliance" [ref=e95] [cursor=pointer]:
          - /url: /contracts/compliance/
          - img [ref=e96]
          - text: Compliance
        - link "Due Diligence" [ref=e98] [cursor=pointer]:
          - /url: /contracts/due-diligence/
          - img [ref=e99]
          - text: Due Diligence
        - link "Trademarks" [ref=e101] [cursor=pointer]:
          - /url: /contracts/trademarks/
          - img [ref=e102]
          - text: Trademarks
        - generic [ref=e104]: Clause Library
        - link "Clauses" [ref=e105] [cursor=pointer]:
          - /url: /contracts/clause-library/
          - img [ref=e106]
          - text: Clauses
        - link "Counterparties" [ref=e108] [cursor=pointer]:
          - /url: /contracts/counterparties/
          - img [ref=e109]
          - text: Counterparties
        - generic [ref=e111]: Approvals & Signatures
        - link "Approvals" [ref=e112] [cursor=pointer]:
          - /url: /contracts/approvals/
          - img [ref=e113]
          - text: Approvals
        - link "Approval Rules" [ref=e115] [cursor=pointer]:
          - /url: /contracts/approval-rules/
          - img [ref=e116]
          - text: Approval Rules
        - link "E-Signatures" [ref=e119] [cursor=pointer]:
          - /url: /contracts/signatures/
          - img [ref=e120]
          - text: E-Signatures
        - generic [ref=e122]: Privacy & GDPR
        - link "Privacy Center" [ref=e123] [cursor=pointer]:
          - /url: /contracts/privacy/
          - img [ref=e124]
          - text: Privacy Center
        - link "DSAR Requests" [ref=e126] [cursor=pointer]:
          - /url: /contracts/privacy/dsar/
          - img [ref=e127]
          - text: DSAR Requests
        - link "Data Inventory" [ref=e129] [cursor=pointer]:
          - /url: /contracts/privacy/data-inventory/
          - img [ref=e130]
          - text: Data Inventory
        - link "Subprocessors" [ref=e132] [cursor=pointer]:
          - /url: /contracts/privacy/subprocessors/
          - img [ref=e133]
          - text: Subprocessors
        - link "Data Transfers" [ref=e135] [cursor=pointer]:
          - /url: /contracts/privacy/transfers/
          - img [ref=e136]
          - text: Data Transfers
        - link "Retention Policies" [ref=e138] [cursor=pointer]:
          - /url: /contracts/privacy/retention/
          - img [ref=e139]
          - text: Retention Policies
        - link "Legal Holds" [ref=e141] [cursor=pointer]:
          - /url: /contracts/privacy/legal-holds/
          - img [ref=e142]
          - text: Legal Holds
        - link "Ethical Walls" [ref=e144] [cursor=pointer]:
          - /url: /contracts/ethical-walls/
          - img [ref=e145]
          - text: Ethical Walls
        - generic [ref=e147]: Analytics
        - link "Reports" [ref=e148] [cursor=pointer]:
          - /url: /contracts/reports/
          - img [ref=e149]
          - text: Reports
        - link "Audit Log" [ref=e151] [cursor=pointer]:
          - /url: /contracts/audit-log/
          - img [ref=e152]
          - text: Audit Log
        - link "Team Audit" [ref=e154] [cursor=pointer]:
          - /url: /contracts/organizations/activity/
          - img [ref=e155]
          - text: Team Audit
    - generic [ref=e159]:
      - heading "Log Time" [level=1] [ref=e161]
      - generic [ref=e162]:
        - generic [ref=e163]:
          - generic [ref=e164]:
            - generic [ref=e165]: Matter
            - combobox [ref=e166]:
              - option "---------"
              - option "MTR-00001 - Merger Agreement - Acme/TechStart" [selected]
              - option "MTR-00002 - Employment Dispute - Williams"
              - option "MTR-00003 - IP Licensing - Global Industries"
              - option "MTR-QA-0001 - QA Matter"
              - option "MTR-00005 - QA212039 value"
          - generic [ref=e167]:
            - generic [ref=e168]: Date
            - textbox [ref=e169]: 2026-04-12
          - generic [ref=e170]:
            - generic [ref=e171]: Hours
            - spinbutton [active] [ref=e172]: "2.50"
          - generic [ref=e173]:
            - generic [ref=e174]: Description
            - textbox [ref=e175]: E2E time entry
          - generic [ref=e176]:
            - generic [ref=e177]: Activity type
            - combobox [ref=e178]:
              - option "Legal Research"
              - option "Document Drafting"
              - option "Document Review" [selected]
              - option "Meeting/Conference"
              - option "Court Appearance"
              - option "Deposition"
              - option "Negotiation"
              - option "Communication"
              - option "Travel"
              - option "Administrative"
              - option "Other"
          - generic [ref=e179]:
            - generic [ref=e180]: Rate
            - spinbutton [ref=e181]: "250.00"
          - generic [ref=e182]:
            - generic [ref=e183]: Is billable
            - checkbox [checked] [ref=e184]
        - generic [ref=e185]:
          - button "Log Time" [ref=e186]
          - link "Cancel" [ref=e187] [cursor=pointer]:
            - /url: /contracts/time/
  - list [ref=e189]:
    - listitem [ref=e190]:
      - link "Hide »" [ref=e191] [cursor=pointer]:
        - /url: "#"
    - listitem [ref=e192]:
      - link "Toggle Theme" [ref=e193] [cursor=pointer]:
        - /url: "#"
        - text: Toggle Theme
        - img [ref=e194]
    - listitem [ref=e196]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e197]
      - link "History /contracts/time/new/" [ref=e198] [cursor=pointer]:
        - /url: "#"
        - text: History
        - text: /contracts/time/new/
    - listitem [ref=e199]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e200]
      - link "Versions Django 5.2.5" [ref=e201] [cursor=pointer]:
        - /url: "#"
        - text: Versions
        - text: Django 5.2.5
    - listitem [ref=e202]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e203]
      - 'link "Time CPU: 17.04ms (15.18ms)" [ref=e204] [cursor=pointer]':
        - /url: "#"
        - text: Time
        - text: "CPU: 17.04ms (15.18ms)"
    - listitem [ref=e205]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e206]
      - link "Settings" [ref=e207] [cursor=pointer]:
        - /url: "#"
    - listitem [ref=e208]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e209]
      - link "Headers" [ref=e210] [cursor=pointer]:
        - /url: "#"
    - listitem [ref=e211]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e212]
      - link "Request TimeEntryCreateView" [ref=e213] [cursor=pointer]:
        - /url: "#"
        - text: Request
        - text: TimeEntryCreateView
    - listitem [ref=e214]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e215]
      - link "SQL 6 queries in 2.13ms" [ref=e216] [cursor=pointer]:
        - /url: "#"
        - text: SQL
        - text: 6 queries in 2.13ms
    - listitem [ref=e217]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e218]
      - link "Static files 3 files used" [ref=e219] [cursor=pointer]:
        - /url: "#"
        - text: Static files
        - text: 3 files used
    - listitem [ref=e220]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e221]
      - link "Templates contracts/time_entry_form.html" [ref=e222] [cursor=pointer]:
        - /url: "#"
        - text: Templates
        - text: contracts/time_entry_form.html
    - listitem [ref=e223]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e224]
      - link "Alerts" [ref=e225] [cursor=pointer]:
        - /url: "#"
    - listitem [ref=e226]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e227]
      - link "Cache 0 calls in 0.00ms" [ref=e228] [cursor=pointer]:
        - /url: "#"
        - text: Cache
        - text: 0 calls in 0.00ms
    - listitem [ref=e229]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e230]
      - link "Signals 36 receivers of 15 signals" [ref=e231] [cursor=pointer]:
        - /url: "#"
        - text: Signals
        - text: 36 receivers of 15 signals
    - listitem [ref=e232]:
      - checkbox "Disable for next and successive requests" [checked] [ref=e233]
      - link "Community" [ref=e234] [cursor=pointer]:
        - /url: "#"
    - listitem [ref=e235]:
      - checkbox "Enable for next and successive requests" [ref=e236]
      - generic [ref=e237]: Intercept redirects
    - listitem [ref=e238]:
      - checkbox "Enable for next and successive requests" [ref=e239]
      - generic [ref=e240]: Profiling
```

# Test source

```ts
  1  | const { test, expect } = require('@playwright/test');
  2  | 
  3  | const username = process.env.E2E_USERNAME || 'e2e_owner';
  4  | const password = process.env.E2E_PASSWORD || 'e2e_pass_123';
  5  | 
  6  | async function login(page) {
  7  |   await page.goto('/login/');
  8  |   await page.fill('input[name="username"]', username);
  9  |   await page.fill('input[name="password"]', password);
  10 |   await page.click('button[type="submit"]');
  11 |   await page.goto('/dashboard/');
  12 |   await expect(page).not.toHaveURL(/\/login\/?$/);
  13 | }
  14 | 
  15 | async function submitOwningForm(page, fieldSelector) {
  16 |   await page.$eval(fieldSelector, (el) => {
  17 |     if (!el.form) {
  18 |       throw new Error(`No owning form for selector: ${fieldSelector}`);
  19 |     }
  20 |     el.form.requestSubmit();
  21 |   });
  22 | }
  23 | 
  24 | test('critical contract create and edit flow works', async ({ page }) => {
  25 |   await login(page);
  26 | 
  27 |   const suffix = Date.now().toString().slice(-6);
  28 |   const title = `E2E Contract ${suffix}`;
  29 | 
  30 |   await page.goto('/contracts/new/');
  31 |   await page.fill('input[name="title"]', title);
  32 |   await page.selectOption('select[name="contract_type"]', 'MSA');
  33 |   await page.fill('textarea[name="content"]', 'Automated E2E contract body');
  34 |   await page.selectOption('select[name="status"]', 'DRAFT');
  35 |   await page.fill('input[name="counterparty"]', 'E2E Counterparty');
  36 |   await page.fill('input[name="value"]', '10000');
  37 |   await page.selectOption('select[name="currency"]', 'USD');
  38 |   await page.selectOption('select[name="risk_level"]', 'LOW');
  39 |   await page.fill('input[name="start_date"]', '2026-04-12');
  40 |   await page.fill('input[name="end_date"]', '2026-12-31');
  41 |   await page.selectOption('select[name="lifecycle_stage"]', 'DRAFTING');
  42 |   await submitOwningForm(page, 'input[name="title"]');
  43 | 
  44 |   await expect(page).toHaveURL(/\/contracts\/?(\?.*)?$/);
  45 |   await expect(page.getByRole('link', { name: title })).toBeVisible();
  46 | 
  47 |   await page.getByRole('link', { name: title }).click();
  48 |   await expect(page).toHaveURL(/\/contracts\/\d+\/?$/);
  49 |   const detailUrl = page.url().replace(/\/$/, '');
  50 |   await page.goto(`${detailUrl}/edit/`);
  51 |   await expect(page).toHaveURL(/\/contracts\/\d+\/edit\/?$/);
  52 | 
  53 |   await page.selectOption('select[name="status"]', 'ACTIVE');
  54 |   await submitOwningForm(page, 'select[name="status"]');
  55 |   await expect(page).toHaveURL(/\/contracts\/?(\?.*)?$/);
  56 | });
  57 | 
  58 | test('critical invoice and time-entry submissions accept valid precision', async ({ page }) => {
  59 |   await login(page);
  60 | 
  61 |   await page.goto('/contracts/invoices/new/');
  62 |   await page.selectOption('select[name="client"]', { index: 1 });
  63 |   await page.selectOption('select[name="matter"]', { index: 1 });
  64 |   await page.fill('input[name="issue_date"]', '2026-04-12');
  65 |   await page.fill('input[name="due_date"]', '2026-05-12');
  66 |   await page.fill('input[name="subtotal"]', '1200.00');
  67 |   await page.fill('input[name="tax_rate"]', '10.00');
  68 |   await page.fill('input[name="payment_terms"]', 'Net 30');
  69 |   await submitOwningForm(page, 'input[name="tax_rate"]');
  70 |   await expect(page).toHaveURL(/\/contracts\/invoices\/\d+\/?$/);
  71 | 
  72 |   await page.goto('/contracts/time/new/');
  73 |   await page.selectOption('select[name="matter"]', { index: 1 });
  74 |   await page.fill('input[name="date"]', '2026-04-12');
  75 |   await page.fill('input[name="hours"]', '2.50');
  76 |   await page.fill('textarea[name="description"]', 'E2E time entry');
  77 |   await page.selectOption('select[name="activity_type"]', 'REVIEW');
  78 |   await page.fill('input[name="rate"]', '250.00');
  79 |   await page.check('input[name="is_billable"]');
  80 |   await page.getByRole('button', { name: 'Log Time' }).click({ force: true });
  81 | 
> 82 |   await expect(page).toHaveURL(/\/contracts\/time\/?$/);
     |                      ^ Error: expect(page).toHaveURL(expected) failed
  83 | });
  84 | 
```