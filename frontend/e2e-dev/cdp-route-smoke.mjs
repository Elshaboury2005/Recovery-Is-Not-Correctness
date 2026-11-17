import { chromium } from '@playwright/test';

const endpoint = process.env.PLAYWRIGHT_CDP_URL;
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173';
const backendOrigin = 'http://127.0.0.1:8000';

if (!endpoint) {
  throw new Error('PLAYWRIGHT_CDP_URL is required');
}

const browser = await chromium.connectOverCDP(endpoint);
const context = browser.contexts()[0] ?? await browser.newContext();
const page = await context.newPage();

await page.route('**/api/**', async (route) => {
  const requestURL = new URL(route.request().url());
  if (!requestURL.pathname.startsWith('/api/')) {
    await route.continue();
    return;
  }
  const target = `${backendOrigin}${requestURL.pathname}${requestURL.search}`;
  const response = await route.fetch({ url: target });
  await route.fulfill({ response });
});

try {
  await page.goto(`${baseURL}/login`);
  await page.waitForLoadState('domcontentloaded');
  await page.locator('#username').fill(process.env.E2E_USERNAME ?? '');
  await page.locator('#password').fill(process.env.E2E_PASSWORD ?? '');
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL(/\/$/);

  for (const route of ['/datasets', '/benchmarks', '/advisor', '/hive', '/infrastructure', '/reconfigurations']) {
    await page.evaluate((pathname) => {
      window.history.pushState({}, '', pathname);
      window.dispatchEvent(new PopStateEvent('popstate'));
    }, route);
    const pageMarker = page.locator('[data-testid$="-page"]');
    try {
      await pageMarker.waitFor({ state: 'visible', timeout: 15_000 });
    } catch (error) {
      console.error(`FAILED ${route}`, page.url(), (await page.locator('body').innerText()).slice(0, 1000));
      throw error;
    }
    if ((await page.locator('main').textContent())?.includes('Page encountered an error')) {
      throw new Error(`${route} rendered an application error`);
    }
    console.log(`PASS ${route}`);
  }
} finally {
  await page.close();
  await browser.close();
}
