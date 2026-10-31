// btk.py の Node 入口（vendor/py_launch.cjs と scripts/page_inspect.cjs）を確かめる。ブラウザは使わない。
import test from "node:test";
import {createRequire} from "node:module";
import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {mkdtempSync, writeFileSync, copyFileSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

function pythonBin() {
  const candidates = [process.env.BTK_PYTHON, process.env.PYTHON, "python3", "python"].filter(Boolean);
  for (const bin of candidates) {
    const probe = spawnSync(bin, ["-c", "import sys; print(sys.version)"], {encoding: "utf8"});
    if (probe.status === 0) return bin;
  }
  throw new Error("python is required for btk.py");
}

const python = pythonBin();
const env = {...process.env, BTK_PYTHON: python};
const LAUNCH = ["vendor/py_launch.cjs", "--env-var", "BTK_PYTHON", "--site", "scripts/btk.py"];
const ENTRIES = [["btk.cjs", ["scripts/btk.cjs"]], ["py_launch", LAUNCH], ["page_inspect.cjs", ["scripts/page_inspect.cjs"]]];

test("help remains available through all Node entries", () => {
  for (const [label, prefix] of ENTRIES) {
    const help = spawnSync(process.execPath, [...prefix, "--help"], {encoding: "utf8", env});
    assert.equal(help.status, 0, `${label}: ${help.stderr}`);
    assert.match(help.stdout, /observe/);
  }
});

test("locate through Node matches python -S scripts/btk.py", () => {
  const directory = mkdtempSync(join(tmpdir(), "page-inspect-"));
  const snapshot = join(directory, "observe.json");
  const body = {
    schema: "btk-page-observe/1", ok: true, elements: [{
      handle: "h:0", index: 0, address: "id:save-draft", tag: "button", role: "button", name: "Save draft",
      text: "Save draft", id: "save-draft", testid: "", visible: true, enabled: true, locators: [],
    }],
  };
  writeFileSync(snapshot, `${JSON.stringify(body)}\n`);
  const args = ["locate", snapshot, "--query", "Save draft", "--unique", "--json"];
  const py = spawnSync(python, ["-S", "scripts/btk.py", ...args], {encoding: "utf8"});
  assert.equal(py.status, 0, py.stderr);
  for (const [label, prefix] of ENTRIES) {
    const node = spawnSync(process.execPath, [...prefix, ...args], {encoding: "utf8", env});
    assert.equal(node.status, 0, `${label}: ${node.stderr}`);
    assert.deepEqual(JSON.parse(node.stdout), JSON.parse(py.stdout));
  }
});

test("BTK_PYTHON is strict: a missing interpreter exits 2 and names the variable", () => {
  const bad = {...process.env, BTK_PYTHON: join(tmpdir(), "no-such-python-btk")};
  for (const [label, prefix] of ENTRIES) {
    const done = spawnSync(process.execPath, [...prefix, "locate", "/nonexistent/observe.json", "--query", "x"], {encoding: "utf8", env: bad});
    assert.equal(done.status, 2, label);
    assert.match(done.stderr, /BTK_PYTHON/, label);
  }
});

test("exit codes from btk.py pass through unchanged", () => {
  for (const [label, prefix] of ENTRIES) {
    const done = spawnSync(process.execPath, [...prefix, "locate", "/nonexistent/observe.json", "--query", "x", "--json"], {encoding: "utf8", env});
    assert.equal(done.status, 2, `${label}: ${done.stdout}${done.stderr}`);
  }
});

test("legacy require APIs retain synchronous exports and helper behavior", () => {
  const require = createRequire(import.meta.url);
  const btk = require("../../scripts/btk.cjs");
  const legacy = require("../../scripts/page_inspect.cjs");
  assert.equal(legacy, btk);
  assert.deepEqual(Object.keys(btk).sort(), [
    "evidenceRelation", "lcsLength", "loopbackTarget", "main", "similarity", "storageFingerprint",
  ]);
  assert.equal(btk.similarity("Save", "save draft"), 1);
  assert.equal(btk.lcsLength("save", "SAVE draft"), 4);
  assert.equal(btk.storageFingerprint("secret").fingerprint_version, 2);
  assert.equal(btk.evidenceRelation({}, {}), "unknown");
  assert.equal(btk.loopbackTarget("http://127.0.0.1:9/"), "http://127.0.0.1:9/");
  assert.throws(() => btk.loopbackTarget("http://localhost:9/"));
});

test("legacy main(argv) remains synchronous with local help and usage status", () => {
  for (const module of ["./scripts/btk.cjs", "./scripts/page_inspect.cjs"]) {
    for (const [args, expected] of [[["--help"], 0], [[], 2]]) {
      const source = `const result = require(${JSON.stringify(module)}).main(${JSON.stringify(args)}); if (result !== ${expected}) process.exit(99);`;
      const done = spawnSync(process.execPath, ["-e", source], {
        encoding: "utf8", env: {...process.env, BTK_PYTHON: "/nonexistent/python"},
      });
      assert.equal(done.status, 0, done.stderr);
      assert.match(done.stdout, /observe/);
    }
  }
});

test("distributed legacy helpers load without the optional CLI launcher", () => {
  const directory = mkdtempSync(join(tmpdir(), "btk-helper-only-"));
  try {
    for (const file of ["btk.cjs", "page_inspect.cjs"]) {
      copyFileSync(new URL(`../../scripts/${file}`, import.meta.url), join(directory, file));
    }
    const require = createRequire(import.meta.url);
    const legacy = require(join(directory, "page_inspect.cjs"));
    assert.equal(legacy.similarity("Save", "save draft"), 1);
    assert.equal(legacy, require(join(directory, "btk.cjs")));
  } finally {
    rmSync(directory, {recursive: true, force: true});
  }
});
