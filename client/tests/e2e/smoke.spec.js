const { test, expect } = require('@playwright/test');

const username = process.env.E2E_USERNAME || 'e2e_owner';
const password = process.env.E2E_PASSWORD || 'e2e_pass_123';

test('login page renders and SSO entry is wired', async ({ page }) => {
  await page.goto('/login/');

  await expect(page.locator('input[name="username"]')).toBeVisible();
  await expect(page.locator('input[name="password"]')).toBeVisible();

  const ssoLink = page.locator('a[href*="/oidc/authenticate/"]');
  if (await ssoLink.count()) {
    await expect(ssoLink.first()).toBeVisible();
  }
});

test('local login works and key pages load', async ({ page }) => {
  await page.goto('/login/');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');

  // Some deployments keep /login in history; assert authenticated access directly.
  const dashboardResponse = await page.goto('/dashboard/');
  expect(dashboardResponse).not.toBeNull();
  expect(dashboardResponse.status()).toBeLessThan(400);
  await expect(page).not.toHaveURL(/\/login\/?$/);

  const paths = ['/dashboard/', '/contracts/', '/contracts/repository/'];
  for (const path of paths) {
    const response = await page.goto(path);
    expect(response).not.toBeNull();
    expect(response.status()).toBeLessThan(400);
  }
});
