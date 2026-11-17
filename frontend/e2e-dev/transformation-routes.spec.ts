import { test, expect } from '@playwright/test';

const BACKEND_ORIGIN = 'http://127.0.0.1:8000';

test.describe('Transformation workflow route smoke coverage', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/**', async (route) => {
      const request = route.request();
      const source = new URL(request.url());
      if (!source.pathname.startsWith('/api/')) {
        await route.continue();
        return;
      }
      const target = `${BACKEND_ORIGIN}${source.pathname}${source.search}`;
      const response = await route.fetch({ url: target });
      await route.fulfill({ response });
    });

    await page.goto('/login');
    await page.locator('#username').fill(process.env.E2E_USERNAME ?? '');
    await page.locator('#password').fill(process.env.E2E_PASSWORD ?? '');
    await page.getByRole('button', { name: 'Sign In' }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  for (const route of ['/datasets', '/benchmarks', '/advisor', '/hive', '/infrastructure', '/reconfigurations']) {
    test(`renders ${route} with live backend data`, async ({ page }) => {
      // Auth tokens are intentionally memory-only, so a full-page navigation
      // would clear the session. Exercise the SPA route transition instead.
      await page.evaluate((pathname) => {
        window.history.pushState({}, '', pathname);
        window.dispatchEvent(new PopStateEvent('popstate'));
      }, route);
      await expect(page.locator('[data-testid$="-page"]')).toBeVisible({ timeout: 15_000 });
      await expect(page.locator('main')).not.toContainText('Page encountered an error');
    });
  }
});
