import {createRequire} from "node:module";
import {spawnSync} from "node:child_process";

const require = createRequire(import.meta.url);
const {test, expect} = require(String.fromCharCode(64) + "playwright/test");

test("Node page-inspect unit tests and Python parity", () => {
  test.setTimeout(120000);
  const run = spawnSync(process.execPath, ["--test", "tests/node-unit/page_inspect.test.mjs"], {
    encoding: "utf8", timeout: 110000, maxBuffer: 8 * 1024 * 1024,
  });
  expect(run.status, `${run.error ?? ""}\n${run.stdout}\n${run.stderr}`).toBe(0);
});
