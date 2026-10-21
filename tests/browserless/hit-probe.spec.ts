import {test, expect} from '@playwright/test';
import {spawnSync} from 'node:child_process';

test('Node hit probe unit tests and Python parity', () => {
  test.setTimeout(120000);
  const run = spawnSync(process.execPath, ['--test', 'tests/node-unit/hit_probe.test.mjs'], {
    encoding: 'utf8', timeout: 110000, maxBuffer: 4 * 1024 * 1024,
  });
  expect(run.status, `${run.error ?? ''}\n${run.stdout}\n${run.stderr}`).toBe(0);
});
