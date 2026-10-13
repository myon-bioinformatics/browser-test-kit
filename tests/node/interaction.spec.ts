import {test, expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
let press, watch;
test.beforeAll(async () => {
  // Native import avoids the CommonJS test runner transforming the ESM asset.
  ({press, watch} = await new Function('url', 'return import(url)')(
    pathToFileURL(resolve('scripts/interaction.mjs')).href));
});
const url = pathToFileURL(resolve('fixtures/interaction.html')).href;

test('press uses real input where the DOM node is not the hit target', async ({page}, testInfo) => {
  const touch = !!testInfo.project.use.hasTouch;
  await page.goto(url);
  const target = page.locator('#target');
  await expect(target.click({timeout: 500})).rejects.toThrow();
  const record = await press(page, target, {touch});
  // Annotation for CI when this fails (job logs may be unreadable from agents).
  console.log(`::notice title=interaction ${testInfo.project.name}::press ${JSON.stringify(record)} log=${await page.locator('#log').innerText()}`);
  await expect(page.locator('#log')).toHaveText(`pressed 1 ${touch ? 'touch' : 'mouse'}`);
  expect(record).toMatchObject({schema: 'pointer-press/1', input: touch ? 'touch' : 'mouse',
    input_source: 'explicit', visible_ratio: 1, hit: {tag: 'div', self: false}});
  expect(Number.isInteger(record.x) && Number.isInteger(record.y)).toBe(true);
  await target.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator('#log')).toHaveText('synthetic');
  const path = testInfo.outputPath('interaction-records.json');
  writeFileSync(path, JSON.stringify([record]));
  const check = spawnSync('python', ['-S', 'scripts/interaction.py', 'check', path], {encoding: 'utf8'});
  expect(check.status, check.stderr).toBe(0);
});

test('touch is detected from navigator.maxTouchPoints in Chromium profiles', async ({page, browserName}, testInfo) => {
  test.skip(browserName !== 'chromium', 'detection is only asserted where it was measured');
  await page.goto(url);
  const record = await press(page, page.locator('#target'));
  expect(record.input_source).toBe('navigator.maxTouchPoints');
  expect(record.input).toBe(testInfo.project.use.hasTouch ? 'touch' : 'mouse');
});

test('watch records requests, dialogs, errors and storage while input is handled', async ({page}, testInfo) => {
  await page.goto(url);
  let w = await watch(page);
  await page.locator('#quiet').click();
  expect((await w.stop()).quiet).toBe(true);
  w = await watch(page);
  await page.locator('#noisy').click();
  await page.waitForTimeout(200);
  const report = await w.stop();
  console.log(`::notice title=interaction ${testInfo.project.name}::watch ${JSON.stringify(report)}`);
  expect(report.quiet).toBe(false);
  expect(report.dialogs).toEqual([{type: 'alert', message: 'noisy'}]);
  expect(report.requests).toContain('http://side-effect.invalid/beacon');
  expect(report.page_errors).toHaveLength(1);
  expect(report.page_errors[0]).toContain('noisy error');
});

test('watch detects an overwrite of an existing storage key (same key count and length)', async ({page}) => {
  await page.goto(url);
  const w = await watch(page);
  await page.locator('#overwrite').click();
  const report = await w.stop();
  const {before, after} = report.storage;
  expect(before.local).not.toBeNull();
  expect(after.local.keys).toBe(before.local.keys);
  expect(after.local.fingerprint).not.toBe(before.local.fingerprint);
  expect(after.session).toEqual(before.session);
  expect(report.quiet).toBe(false);
  expect(JSON.stringify(report)).not.toContain('bbbb');
});
