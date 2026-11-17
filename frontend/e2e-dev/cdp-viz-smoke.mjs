import { chromium } from '@playwright/test';

const endpoint = process.env.PLAYWRIGHT_CDP_URL;
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173';
const presets = [
  'pending', 'kafka-40', 'spark-active', 'spark-unknown', 'hdfs-writing',
  'succeeded', 'failed-spark', 'fault-injected', 'fault-recovering',
  'fault-recovered', 'streaming-lag', 'cancelled',
];

if (!endpoint) throw new Error('PLAYWRIGHT_CDP_URL is required');

const browser = await chromium.connectOverCDP(endpoint);
const context = browser.contexts()[0] ?? await browser.newContext();
const page = await context.newPage();

try {
  await page.goto(`${baseURL}/dev/viz`);
  await page.locator('[data-testid="viz-playground"]').waitFor({ state: 'visible' });

  for (const preset of presets) {
    await page.getByTestId(`preset-${preset}`).click();
    await page.waitForTimeout(300);
    const textEquivalent = page.getByTestId('viz-text-equivalent');
    if (await textEquivalent.locator('li').count() !== 4) {
      throw new Error(`${preset} did not expose four text-equivalent stations`);
    }
    await page.getByTestId('viz').waitFor({ state: 'visible' });
    await page.getByTestId('viz-quality').getByRole('button', { name: '2D' }).click();
    console.log(`PASS preset ${preset}`);
  }

  await page.goto(`${baseURL}/dev/viz`);
  await page.getByTestId('viz-playground').waitFor({ state: 'visible' });
  await page.getByTestId('preset-spark-active').click();
  await page.waitForTimeout(600);
  const canvas = (await page.locator('canvas').count()) > 0
    ? page.locator('canvas').first()
    : page.getByTestId('viz-canvas');
  const frame1 = await canvas.screenshot();
  await page.waitForTimeout(600);
  const frame2 = await canvas.screenshot();
  if (frame1.equals(frame2)) throw new Error('active visualization did not animate');
  const pause = page.getByTestId('viz-pause');
  await pause.click();
  await page.waitForTimeout(1000);
  const pausedFrame1 = await canvas.screenshot();
  await page.waitForTimeout(600);
  const pausedFrame2 = await canvas.screenshot();
  if (!pausedFrame1.equals(pausedFrame2)) throw new Error('paused visualization continued animating');
  console.log('PASS animation pause behavior');

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseURL}/dev/viz`);
  await page.getByTestId('viz-playground').waitFor({ state: 'visible' });
  if (await page.getByTestId('viz-mode').textContent() !== '2d') {
    throw new Error('reduced-motion mode was not 2d');
  }
  console.log('PASS reduced-motion fallback');
} finally {
  await page.close();
  await browser.close();
}
