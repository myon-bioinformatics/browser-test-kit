import {createRequire} from "node:module";
import {spawnSync} from "node:child_process";
import * as inspect from "../../scripts/page_inspect.mjs";

const require = createRequire(import.meta.url);
const {test, expect} = require(String.fromCharCode(64) + "playwright/test");
const fixture = new URL("../../fixtures/page_inspect.html", import.meta.url).href;

test("this engine surveys visible controls and ranks a stable address", async ({page}) => {
  await page.goto(fixture);
  const collect = (0, eval)(inspect.COLLECT_JS);
  const raw = await page.evaluate(collect, {includeHidden: false, role: "", hardCap: inspect.HARD_CAP});
  const survey = inspect.normalizeElements(raw, {start: 0, limit: 50});
  const names = survey.elements.map((element) => element.name);
  expect(names).toContain("Save draft");
  expect(names.filter((name) => name === "Cancel")).toHaveLength(2);
  for (const absent of ["Secret", "Also hidden", "Inside shadow", "Child frame"]) {
    expect(names).not.toContain(absent);
  }
  expect(raw.child_frames).toBeGreaterThanOrEqual(1);
  expect(raw.shadow_roots).toBe(true);
  const ranked = inspect.locate(survey.elements, {query: "Save draft", unique: true});
  expect(ranked.ok).toBe(true);
  expect(ranked.items[0].address).toBe("id:save-draft");
  const ambiguous = inspect.locate(survey.elements, {query: "Cancel", unique: true});
  expect(ambiguous.ok).toBe(false);
});

test("the Node CLI surveys Chromium headless", async ({browserName}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one CLI launch is enough; other projects evaluate the page script");
  test.setTimeout(90000);
  const run = spawnSync(process.execPath, [
    "scripts/page_inspect.mjs", "survey", "fixtures/page_inspect.html", "--browser", browserName, "--json",
  ], {encoding: "utf8", timeout: 80000});
  expect(run.status, run.stderr).toBe(0);
  const payload = JSON.parse(run.stdout);
  expect(payload.schema).toBe("btk-page-survey/1");
  expect(payload.environment.browser).toBe("chromium");
  expect(payload.environment.headless).toBe(true);
  expect(payload.elements.some((element) => element.address === "id:save-draft")).toBe(true);
});
