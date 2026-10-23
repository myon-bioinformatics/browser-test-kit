import {createServer} from "node:http";
import {createRequire} from "node:module";
import {spawn, spawnSync} from "node:child_process";
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


test("Node survey blocks other ports, page resources and redirects", async ({}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one CLI boundary integration");
  test.setTimeout(120000);
  const hits = [];
  const forbidden = createServer((req, res) => {hits.push(req.url); res.end("outside");});
  const listen = (server, port) => new Promise((resolve, reject) => {server.once("error", reject); server.listen(port, "127.0.0.1", resolve);});
  await listen(forbidden, 0);
  const other = `http://127.0.0.1:${forbidden.address().port}/outside`;
  const allowed = createServer((req, res) => {
    if (req.url === "/redirect") {res.writeHead(302, {Location: other}); res.end();}
    else {res.setHeader("Content-Type", "text/html"); res.end(`<button id="safe">Safe</button><img src="${other}"><script>fetch("${other}").catch(()=>{})</script>`);}
  });
  const close = server => new Promise(resolve => server.close(resolve));
  try {
    await listen(allowed, 8080);
    for (const [path, expected] of [["/", 0], ["/redirect", 2]]) {
      const result = await new Promise((resolve, reject) => {
        const child = spawn(process.execPath, ["scripts/page_inspect.mjs", "survey", `http://127.0.0.1:8080${path}`, "--browser", "chromium", "--json"]);
        let stdout = "", stderr = "";
        child.stdout.on("data", data => {stdout += data;}); child.stderr.on("data", data => {stderr += data;});
        child.on("error", reject); child.on("close", code => resolve({code, stdout, stderr}));
      });
      expect(result.code, result.stdout + result.stderr).toBe(expected);
      const body = JSON.parse(result.stdout);
      if (expected === 0) expect(body.elements.some(e => e.address === "id:safe")).toBe(true);
      else expect(body.stage).toBe("navigate");
      expect(hits).toEqual([]);
    }
  } finally {await close(allowed); await close(forbidden);}
});
