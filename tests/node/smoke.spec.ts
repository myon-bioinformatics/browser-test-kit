import { test, expect } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const fixture = pathToFileURL(path.resolve('fixtures/index.html')).href;

test('shared fixture interaction and screenshot', async ({ page, browserName }, testInfo) => {
  await page.goto(fixture);
  await expect(page.locator('#unicode')).toHaveText('日本語 / Unicode ✓ / 🧪');
  await page.locator('#name').fill('Node');
  await page.locator('#submit').click();
  await expect(page.locator('#result')).toHaveText('Hello, Node!');
  const artifact = testInfo.outputPath('evidence.png');
  await page.screenshot({ path: artifact, fullPage: true });
  fs.writeFileSync(testInfo.outputPath('evidence.json'), JSON.stringify({
    runtime: 'node', browser: browserName, project: testInfo.project.name,
    stage: 'complete', artifact: path.basename(artifact),
    viewport: testInfo.project.use.viewport ?? null,
  }) + '\n');
});
