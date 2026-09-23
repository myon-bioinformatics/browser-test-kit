import { test, expect } from '@playwright/test';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const fixture = pathToFileURL(path.resolve('fixtures/index.html')).href;

test('shared fixture interaction and screenshot', async ({ page }, testInfo) => {
  await page.goto(fixture);
  await expect(page.locator('#unicode')).toContainText('日本語');
  await page.locator('#name').fill('Node');
  await page.locator('#submit').click();
  await expect(page.locator('#result')).toHaveText('Hello, Node!');
  await page.screenshot({ path: testInfo.outputPath('evidence.png'), fullPage: true });
});
