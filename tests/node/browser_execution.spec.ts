import { test, expect } from '@playwright/test';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

let explore, choice;
test.beforeAll(async () => {
  ({ explore, choice } = await new Function('url', 'return import(url)')(
    pathToFileURL(resolve('scripts/browser_execution.mjs')).href));
});
const seedFor = (index: number) => {
  for (let seed = 0; seed < 1000; seed++) {
    if (choice(String(seed), '/sample', 0, 5) === index) return String(seed);
  }
  throw new Error('No seed for fixture action');
};

test.beforeEach(async ({ page }) => {
  await page.setContent('<meta name="viewport" content="width=device-width,initial-scale=1"><label>Name <input></label><button onclick="this.textContent=\'pressed\'">Run</button>');
});

test('shared exploration sends real pointer input and returns its receipt', async ({ page }) => {
  const receipt = await explore(page, { route: '/sample', seed: seedFor(4), steps: 1,
    buttonName: /^Run$/, ready: async () => expect(page.getByRole('button')).toHaveText('pressed') });
  expect(receipt.ok).toBe(true);
  expect(receipt.actions[0]).toMatchObject({ kind: 'press', label: 'Run' });
  await expect(page.getByRole('button')).toHaveText('pressed');
});

test('shared exploration fills supplied Unicode values without redefining emoji identity', async ({ page }) => {
  const receipt = await explore(page, { route: '/sample', seed: seedFor(3), steps: 1,
    buttonName: /^Run$/, values: ['日本語👩🏽‍💻'] });
  expect(receipt.actions[0]).toMatchObject({ kind: 'fill', value: '日本語👩🏽‍💻' });
  await expect(page.getByRole('textbox')).toHaveValue('日本語👩🏽‍💻');
});
