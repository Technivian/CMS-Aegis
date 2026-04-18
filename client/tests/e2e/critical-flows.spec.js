const { test, expect } = require('@playwright/test');

const username = process.env.E2E_USERNAME || 'e2e_owner';
const password = process.env.E2E_PASSWORD || 'e2e_pass_123';

async function login(page) {
  await page.goto('/login/');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.goto('/dashboard/');
  await expect(page).not.toHaveURL(/\/login\/?$/);
}

async function submitOwningForm(page, fieldSelector) {
  await page.$eval(fieldSelector, (el) => {
    if (!el.form) {
      throw new Error(`No owning form for selector: ${fieldSelector}`);
    }
    el.form.requestSubmit();
  });
}

test('critical contract create and edit flow works', async ({ page }) => {
  await login(page);

  const suffix = Date.now().toString().slice(-6);
  const title = `E2E Contract ${suffix}`;

  await page.goto('/contracts/new/');
  await page.fill('input[name="title"]', title);
  await page.selectOption('select[name="contract_type"]', 'MSA');
  await page.fill('textarea[name="content"]', 'Automated E2E contract body');
  await page.selectOption('select[name="status"]', 'DRAFT');
  await page.fill('input[name="counterparty"]', 'E2E Counterparty');
  await page.fill('input[name="value"]', '10000');
  await page.selectOption('select[name="currency"]', 'USD');
  await page.selectOption('select[name="risk_level"]', 'LOW');
  await page.fill('input[name="start_date"]', '2026-04-12');
  await page.fill('input[name="end_date"]', '2026-12-31');
  await page.selectOption('select[name="lifecycle_stage"]', 'DRAFTING');
  await submitOwningForm(page, 'input[name="title"]');

  await expect(page).toHaveURL(/\/contracts\/?(\?.*)?$/);
  await expect(page.getByRole('link', { name: title })).toBeVisible();

  await page.getByRole('link', { name: title }).click();
  await expect(page).toHaveURL(/\/contracts\/\d+\/?$/);
  const detailUrl = page.url().replace(/\/$/, '');
  await page.goto(`${detailUrl}/edit/`);
  await expect(page).toHaveURL(/\/contracts\/\d+\/edit\/?$/);

  await page.selectOption('select[name="status"]', 'ACTIVE');
  await submitOwningForm(page, 'select[name="status"]');
  await expect(page).toHaveURL(/\/contracts\/?(\?.*)?$/);
});

test('critical invoice and time-entry submissions accept valid precision', async ({ page }) => {
  await login(page);

  await page.goto('/contracts/invoices/new/');
  await page.selectOption('select[name="client"]', { index: 1 });
  await page.selectOption('select[name="matter"]', { index: 1 });
  await page.fill('input[name="issue_date"]', '2026-04-12');
  await page.fill('input[name="due_date"]', '2026-05-12');
  await page.fill('input[name="subtotal"]', '1200.00');
  await page.fill('input[name="tax_rate"]', '10.00');
  await page.fill('input[name="payment_terms"]', 'Net 30');
  await submitOwningForm(page, 'input[name="tax_rate"]');
  await expect(page).toHaveURL(/\/contracts\/invoices\/\d+\/?$/);

  await page.goto('/contracts/time/new/');
  await page.selectOption('select[name="matter"]', { index: 1 });
  await page.fill('input[name="date"]', '2026-04-12');
  await page.fill('input[name="hours"]', '2.50');
  await page.fill('textarea[name="description"]', 'E2E time entry');
  await page.selectOption('select[name="activity_type"]', 'REVIEW');
  await page.fill('input[name="rate"]', '250.00');
  await page.check('input[name="is_billable"]');
  await page.getByRole('button', { name: 'Log Time' }).click({ force: true });

  await expect(page).toHaveURL(/\/contracts\/time\/?$/);
});
