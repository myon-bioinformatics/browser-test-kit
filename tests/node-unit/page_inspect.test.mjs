import test from "node:test";
import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {mkdtempSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

function pythonBin() {
  const candidates = [process.env.PYTHON, "python3", "python"].filter(Boolean);
  for (const bin of candidates) {
    const probe = spawnSync(bin, ["-c", "import sys; print(sys.version)"], {encoding: "utf8"});
    if (probe.status === 0) return bin;
  }
  throw new Error("python is required for the page-inspect twin");
}

const python = pythonBin();

test("Node and Python agree on score, loopback, fingerprints, and evidence", () => {
  const pairs = [
    ["similarity", "similarity", [["Save", "save draft"], ["", "abc"], ["\u{1F600}", "x\u{1F600}y"]]],
    ["loopback_target", "loopbackTarget", [
      ["http://127.0.0.1:9/a"], ["http://[::1]:80/a"], ["http://localhost:9/"], ["http://127.0.0.1/a"],
    ]],
    ["storage_fingerprint", "storageFingerprint", [["secret-value"], ["\uD800"], [""]]],
    ["evidence_relation", "evidenceRelation", [
      [{coverage: "not_requested"}, {coverage: "not_requested"}],
      [{coverage: "complete", digest: "abc"}, {coverage: "complete", digest: "abc"}],
      [{coverage: "complete", digest: "abc"}, {coverage: "complete", digest: "def"}],
    ]],
  ];
  for (const [pythonName, nodeName, cases] of pairs) {
    const done = spawnSync(python, [
      "-S", "scripts/twin_parity.py", `scripts/btk.py:${pythonName}`, `scripts/page_inspect.cjs:${nodeName}`,
    ], {input: JSON.stringify(cases), encoding: "utf8"});
    assert.equal(done.status, 0, done.stdout + done.stderr);
  }
});

test("the Node CLI help stays local and live commands use the vendored launcher", () => {
  const help = spawnSync(process.execPath, ["scripts/page_inspect.cjs", "--help"], {encoding: "utf8"});
  assert.equal(help.status, 0);
  assert.match(help.stdout, /observe/);
  const major = Number(process.versions.node.split(".")[0]);
  if (major < 24) return;
  const directory = mkdtempSync(join(tmpdir(), "page-inspect-"));
  const snapshot = join(directory, "observe.json");
  const body = {
    schema: "btk-page-observe/1", ok: true, elements: [{
      handle: "h:0", index: 0, address: "id:save-draft", tag: "button", role: "button", name: "Save draft",
      text: "Save draft", id: "save-draft", testid: "", visible: true, enabled: true, locators: [],
    }],
  };
  writeFileSync(snapshot, `${JSON.stringify(body)}\n`);
  const node = spawnSync(process.execPath, ["scripts/page_inspect.cjs", "locate", snapshot, "--query", "Save draft", "--unique", "--json"], {encoding: "utf8"});
  const py = spawnSync(python, ["-S", "scripts/btk.py", "locate", snapshot, "--query", "Save draft", "--unique", "--json"], {encoding: "utf8"});
  assert.equal(node.status, 0, node.stderr);
  assert.equal(py.status, 0, py.stderr);
  assert.deepEqual(JSON.parse(node.stdout), JSON.parse(py.stdout));
});
