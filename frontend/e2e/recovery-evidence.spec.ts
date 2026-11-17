import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

test('Layered recovery evidence matches the real fault report and JSON export', async ({ page, request }, testInfo) => {
  const experimentId = process.env.PHASE2_EXPERIMENT_ID;
  test.skip(!experimentId, 'Select an existing completed fault pilot with PHASE2_EXPERIMENT_ID');
  test.setTimeout(90_000);
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  expect(username).toBeTruthy();
  expect(password).toBeTruthy();
  const login = await request.post('http://localhost:8000/api/auth/login', {
    form: { username: username!, password: password! },
  });
  expect(login.ok()).toBeTruthy();
  const { access_token } = await login.json();
  const headers = { Authorization: `Bearer ${access_token}` };
  const response = await request.get('http://localhost:8000/api/reports?limit=100', { headers });
  expect(response.ok()).toBeTruthy();
  const list = await response.json();
  const report = (list.items || list).find((item: { experimentId: string }) => item.experimentId === experimentId);
  expect(report, 'The selected pilot must have a persisted report').toBeTruthy();
  const detailResponse = await request.get(`http://localhost:8000/api/reports/${report.id}`, { headers });
  expect(detailResponse.ok()).toBeTruthy();
  const detail = await detailResponse.json();
  expect(detail.recoveryEvidence?.metrics).toBeTruthy();
  await testInfo.attach('api-report', { body: JSON.stringify(detail, null, 2), contentType: 'application/json' });

  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto('/login');
  await page.locator('#username').fill(username!);
  await page.locator('#password').fill(password!);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL('/');
  await page.locator('aside nav a').filter({ hasText: 'Reports' }).first().click();
  const link = page.locator(`a[href="/reports/${report.id}"]`).first();
  await expect(link).toBeVisible();
  await link.click();
  const table = page.getByTestId('report-recovery-evidence');
  await expect(table).toBeVisible();
  await expect(page.getByText('Recovery Time (legacy)', { exact: true })).toBeVisible();
  const metrics = detail.recoveryEvidence.metrics;
  const service = metrics.service_readiness_recovery;
  expect(service.status).toBe('interval');
  await expect(table.getByRole('row').filter({ hasText: 'Dispatch to target service readiness' }))
    .toContainText(`${service.lower_seconds.toFixed(3)}–${service.upper_seconds.toFixed(3)} s`);
  const independent = metrics.validated_output_completion;
  expect(independent.status).toBe('unobservable');
  await expect(table.getByRole('row').filter({ hasText: 'Pipeline start to independent validation' }))
    .toContainText('Not observable');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export JSON' }).click();
  const download = await downloadEvent;
  const destination = testInfo.outputPath('exported-report.json');
  await download.saveAs(destination);
  const exported = JSON.parse(await fs.readFile(destination, 'utf8'));
  expect(exported.recoveryEvidence).toEqual(detail.recoveryEvidence);
  expect(exported.recoveryTimeScope).toEqual(detail.recoveryTimeScope);
  await page.screenshot({ path: testInfo.outputPath('layered-report.png'), fullPage: true });
  expect(pageErrors).toEqual([]);
});

test('A valid failed DataNode write fault remains visibly unvalidated', async ({ page, request }, testInfo) => {
  const experimentId = process.env.PHASE2_SIGKILL_EXPERIMENT_ID;
  test.skip(!experimentId, 'Select the completed bounded DataNode SIGKILL pilot');
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  const login = await request.post('http://localhost:8000/api/auth/login', {
    form: { username: username!, password: password! },
  });
  expect(login.ok()).toBeTruthy();
  const { access_token } = await login.json();
  const headers = { Authorization: `Bearer ${access_token}` };
  const reports = await request.get('http://localhost:8000/api/reports?limit=100', { headers });
  expect(reports.ok()).toBeTruthy();
  const list = await reports.json();
  const report = (list.items || list).find((item: { experimentId: string }) => item.experimentId === experimentId);
  expect(report).toBeTruthy();
  const detailResponse = await request.get(`http://localhost:8000/api/reports/${report.id}`, { headers });
  expect(detailResponse.ok()).toBeTruthy();
  const detail = await detailResponse.json();
  expect(detail.result).toBe('FAIL');
  expect(detail.results.output_correct ?? detail.results.outputCorrect).not.toBe(true);
  expect(detail.recoveryEvidence.metrics.service_readiness_recovery.status).toBe('unobservable');
  expect(detail.recoveryEvidence.metrics.validated_output_completion.status).toBe('unobservable');

  await page.goto('/login');
  await page.locator('#username').fill(username!);
  await page.locator('#password').fill(password!);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.locator('aside nav a').filter({ hasText: 'Reports' }).first().click();
  await page.locator(`a[href="/reports/${report.id}"]`).first().click();
  const table = page.getByTestId('report-recovery-evidence');
  await expect(table.getByRole('row').filter({ hasText: 'Dispatch to target service readiness' }))
    .toContainText('Not observable');
  await expect(table.getByRole('row').filter({ hasText: 'Pipeline start to independent validation' }))
    .toContainText('Not observable');
  await expect(page.getByText('Recovery Time (legacy)', { exact: true })).toBeVisible();
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export JSON' }).click();
  const download = await downloadEvent;
  const destination = testInfo.outputPath('failed-datanode-report.json');
  await download.saveAs(destination);
  expect(JSON.parse(await fs.readFile(destination, 'utf8')).recoveryEvidence).toEqual(detail.recoveryEvidence);
});
