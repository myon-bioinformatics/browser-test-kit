import {test, expect} from '@playwright/test';
import {spawnSync} from 'node:child_process';

test('Vendored Python launcher discovery and signal regressions', () => {
  test.setTimeout(120000);
  // Playwright sets FORCE_COLOR; ambient NO_COLOR otherwise adds Node warnings to stderr.
  const env = {...process.env};
  delete env.FORCE_COLOR;
  delete env.NO_COLOR;
  const run = spawnSync(process.execPath, ['--test', 'tests/node-unit/py_launch.test.cjs'], {
    env, encoding: 'utf8', timeout: 110000, maxBuffer: 4 * 1024 * 1024,
  });
  expect(run.status, `${run.error ?? ''}\n${run.stdout}\n${run.stderr}`).toBe(0);
});
