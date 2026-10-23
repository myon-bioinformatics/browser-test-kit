import test from "node:test";
import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {mkdtempSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import * as inspect from "../../scripts/page_inspect.mjs";

function pythonBin() {
  const candidates = [process.env.PYTHON, "python3", "python"].filter(Boolean);
  for (const bin of candidates) {
    const probe = spawnSync(bin, ["-c", "import sys; print(sys.version)"], {encoding: "utf8"});
    if (probe.status === 0) return bin;
  }
  throw new Error("python is required for the page-inspect oracle");
}

const python = pythonBin();

function oracle(request) {
  const result = spawnSync(python, ["-S", "tests/helpers/page_inspect_oracle.py"], {
    input: JSON.stringify(request), encoding: "utf8", maxBuffer: 8 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr || result.error?.message);
  return JSON.parse(result.stdout);
}

function element(name, extra = {}) {
  return {
    tag: "button", role: "button", name, text: name, id: "", testid: "", href: "",
    visible: true, enabled: true, in_viewport: true, obscured: false,
    box: {x: 1, y: 2, width: 30, height: 16}, parent_tag: "body", css: "button",
    id_unique: false, testid_unique: false, css_unique: false, ...extra,
  };
}

const raw = {
  title: "Fixture", child_frames: 1, shadow_roots: true, shadow_scan: "complete", total: 4, truncated: false,
  elements: [
    element("Save draft", {id: "save-draft", testid: "save-draft", id_unique: true, testid_unique: true, css: "#save-draft", css_unique: true}),
    element("Save draft"),
    element("Cancel"),
    element("Go \u{1F600}", {role: "link", tag: "a"}),
  ],
};
const environment = {
  os: "Linux", browser: "chromium", version: "0", channel: null, headless: true, profile: "desktop",
  viewport: {width: 1280, height: 800},
};

function same(request, actual) {
  const expected = oracle(request);
  if (request.fn === "describe" && request.target === "0x10") {
    assert.equal(expected.ok, false);
    assert.throws(() => actual(), (error) => error instanceof inspect.InspectError && error.error === expected.error && error.hint === expected.hint);
    return;
  }
  assert.equal(expected.ok, true, JSON.stringify(expected));
  const value = typeof actual === "function" ? actual() : actual;
  assert.deepEqual(value, expected.value);
}

test("Python and Node share scores, addresses, pages, and target errors", () => {
  assert.equal(inspect.HARD_CAP, oracle({fn: "hard_cap"}).value);
  assert.equal(inspect.osName(), oracle({fn: "os"}).value);
  for (const [left, right] of [["save drft", "save draft"], ["", "abc"], ["abc", "xyz"], ["a\u{1F600}b", "a\u{1F600}b"], ["\u{1F600}", "x\u{1F600}y"]]) {
    same({fn: "lcs", left, right}, inspect.lcsLength(left, right));
    same({fn: "similarity", left, right}, inspect.similarity(left, right));
  }
  same({fn: "similarity", left: "Save", right: "save draft"}, inspect.similarity("Save", "save draft"));
  const normalized = inspect.normalizeElements(raw, {start: 0, limit: 50});
  same({fn: "normalize", raw, start: 0, limit: 50}, normalized);
  same({fn: "normalize", raw, start: 1, limit: 1}, inspect.normalizeElements(raw, {start: 1, limit: 1}));
  const elements = normalized.elements;
  same({fn: "locate", elements, query: "Save draft", unique: true}, inspect.locate(elements, {query: "Save draft", unique: true}));
  same({fn: "locate", elements, query: "Save", unique: true}, inspect.locate(elements, {query: "Save", unique: true}));
  same({fn: "locate", elements, query: "Save drft"}, inspect.locate(elements, {query: "Save drft"}));
  same({fn: "locate", elements, query: "", start: 1, limit: 1}, inspect.locate(elements, {query: "", start: 1, limit: 1}));
  same({fn: "count", elements, role: "button"}, inspect.countElements(elements, {role: "button"}));
  same({fn: "describe", elements, target: "id:save-draft"}, inspect.describeElement(elements, "id:save-draft"));
  same({fn: "describe", elements, target: elements[3].address}, inspect.describeElement(elements, elements[3].address));
  same({fn: "describe", elements, target: 'button "Cancel"'}, inspect.describeElement(elements, 'button "Cancel"'));
  same({fn: "describe", elements, target: "0x10"}, () => inspect.describeElement(elements, "0x10"));
  same({fn: "operations"}, inspect.operations());
  same({fn: "assemble", raw, environment, url: "file:///fixture.html", start: 0, limit: 50},
    inspect.assembleSurvey(raw, {environment, url: "file:///fixture.html", start: 0, limit: 50}));
  for (const target of ["https://example.test/a", "https://user:secret" + String.fromCharCode(64) + "example.test/a", "javascript:alert(1)"]) {
    let actual;
    let thrown = null;
    try { actual = inspect.targetUrl(target); } catch (error) { thrown = error; }
    const expected = oracle({fn: "target", target});
    if (expected.ok) {
      assert.equal(actual, expected.value);
    } else {
      assert.ok(thrown instanceof inspect.InspectError);
      assert.equal(thrown.error, expected.error);
      assert.equal(thrown.hint, expected.hint);
    }
  }
});

test("Node context options drop isMobile for Firefox only", () => {
  const devices = { "iPhone 13": {isMobile: true, hasTouch: true, viewport: {width: 390, height: 844}, defaultBrowserType: "webkit"} };
  const firefox = inspect.contextOptions(devices, "firefox", "iphone", false);
  const webkit = inspect.contextOptions(devices, "webkit", "iphone", false);
  assert.equal(firefox.isMobile, undefined);
  assert.equal(firefox.hasTouch, true);
  assert.equal(webkit.isMobile, true);
  assert.equal(webkit.defaultBrowserType, undefined);
  assert.deepEqual(inspect.contextOptions(devices, "chromium", "desktop", false).viewport, {width: 1280, height: 800});
});

test("collect source is a function expression and the CLI matches Python", () => {
  const collect = (0, eval)(inspect.COLLECT_JS);
  assert.equal(typeof collect, "function");
  const survey = inspect.assembleSurvey(raw, {environment, url: "file:///fixture.html", start: 0, limit: 50});
  const directory = mkdtempSync(join(tmpdir(), "page-inspect-"));
  const snapshot = join(directory, "survey.json");
  writeFileSync(snapshot, `${JSON.stringify(survey)}\n`);
  const args = ["locate", snapshot, "--query", "Cancel", "--unique", "--json"];
  const node = spawnSync(process.execPath, ["scripts/page_inspect.mjs", ...args], {encoding: "utf8"});
  const py = spawnSync(python, ["-S", "scripts/page_inspect.py", ...args], {encoding: "utf8"});
  assert.equal(node.status, 0, node.stderr);
  assert.equal(py.status, 0, py.stderr);
  assert.deepEqual(JSON.parse(node.stdout), JSON.parse(py.stdout));
  const sharedArgs = ["locate", snapshot, "--query", "Save draft", "--unique", "--json"];
  const sharedNode = spawnSync(process.execPath, ["scripts/page_inspect.mjs", ...sharedArgs], {encoding: "utf8"});
  const sharedPy = spawnSync(python, ["-S", "scripts/page_inspect.py", ...sharedArgs], {encoding: "utf8"});
  assert.equal(sharedNode.status, 1, sharedNode.stderr);
  assert.equal(sharedPy.status, 1, sharedPy.stderr);
  assert.deepEqual(JSON.parse(sharedNode.stdout), JSON.parse(sharedPy.stdout));
  const help = spawnSync(process.execPath, ["scripts/page_inspect.mjs", "--help"], {encoding: "utf8"});
  assert.equal(help.status, 0);
  assert.match(help.stdout, /survey/);
  const abbrev = spawnSync(process.execPath, ["scripts/page_inspect.mjs", "locate", snapshot, "--quer", "Save"], {encoding: "utf8"});
  assert.equal(abbrev.status, 2);
});

test("fixed loopback boundary agrees with Python, including browser URL aliases", async () => {
  const accepted = ["http://127.0.0.1:8080/", "https://[::1]:8080/x?q=1#f"];
  const rejected = ["https://example.com:8080/", "http://192.168.1.2:8080/", "http://10.0.0.1:8080/",
    "http://localhost:8080/", "http://127.0.0.1:8081/", "http://127.0.0.1/", "http://[::1]:80/",
    "http://127.1:8080/", "http://2130706433:8080/", "http://0x7f000001:8080/",
    "http://127.0.0.1.evil.test:8080/", "http://user@127.0.0.1:8080/", "http://127.0.0.1:8080@evil.test/",
    "http://127.0.0.1:08080/", "http://127.0.0.1:8080\\@evil.test/", "http://127.0.0.1:8080\n.evil.test/", "file://remote/tmp/page.html", "file:////remote/share.html", "file:///%2fremote/share.html"];
  for (const target of accepted) {
    assert.equal(inspect.targetUrl(target), target);
    assert.deepEqual(oracle({fn: "target", target}), {ok: true, value: target});
  }
  for (const target of rejected) {
    assert.throws(() => inspect.targetUrl(target), inspect.InspectError);
    assert.equal(oracle({fn: "target", target}).ok, false);
    await assert.rejects(inspect.surveyBrowser({url: target}), inspect.InspectError);
    let blocked = false;
    await inspect.restrictRequest({request: () => ({url: () => target}), abort: async () => {blocked = true;}});
    assert.equal(blocked, true);
  }
  for (const status of [200, 302]) {
    let action;
    const response = {status: () => status};
    await inspect.restrictRequest({request: () => ({url: () => accepted[0]}),
      fetch: async opts => {assert.deepEqual(opts, {maxRedirects: 0}); return response;},
      abort: async () => {action = "abort";}, fulfill: async opts => {assert.equal(opts.response, response); action = "fulfill";}});
    assert.equal(action, status === 302 ? "abort" : "fulfill");
  }
});
