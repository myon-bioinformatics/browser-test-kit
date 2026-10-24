import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
const require = createRequire(import.meta.url);
const {test, expect} = require(String.fromCharCode(64) + 'playwright/test');
test('platform fixture state machines and Node runtime contract', () => {
  const result = spawnSync(process.execPath, ['--test', 'tests/node-unit/page_inspect_scenario_fixture.test.mjs'], {
    encoding: 'utf8', timeout: 30000
  });
  expect(result.status, result.stdout + result.stderr).toBe(0);
});
