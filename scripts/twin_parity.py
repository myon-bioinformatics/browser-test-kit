"""Run a Python function and its Node twin on the same inputs and compare the results in memory.

    python -S scripts/twin_parity.py scripts/interaction.py:press_point scripts/interaction.mjs:pressPoint < cases.json
    echo '[[{"x":0,"y":0,"width":10,"height":10},{"width":100,"height":100}]]' | python -S scripts/twin_parity.py PY:FN MJS:FN

Cases are a JSON list of argument lists. Node runs once for all of them: the cases go
in on stdin and the results come back on stdout, and nothing is written to disk. Each
side returns `{"ok": true, "value": ...}` or `{"ok": false, "error": message}`. A
mismatch is a case where one side accepts and the other rejects, or both accept with
different values (compared as JSON, the form a record crosses the boundary in). Error
messages may differ between twins and are only compared with `--messages`.

Library: `node_calls(module, name, cases)`, `python_calls(fn, cases)`, `mismatches(a, b)`.
Exit codes: 0 the twins agree; 1 a mismatch; 2 input error (no node, bad spec, bad JSON).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

# One Node process for every case; inputs and outputs travel through the pipe only.
NODE_PROGRAM = r"""
import {pathToFileURL} from 'node:url';
const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const {module, name, cases} = JSON.parse(Buffer.concat(chunks).toString('utf8'));
let fn;
try { fn = (await import(pathToFileURL(module).href))[name]; }
catch (error) { process.stderr.write(`twin-parity: cannot import ${module}: ${error?.message ?? error}\n`); process.exit(3); }
if (typeof fn !== 'function') { process.stderr.write(`twin-parity: no exported function ${name}\n`); process.exit(3); }
const out = [];
for (const args of cases) {
  try { out.push({ok: true, value: await fn(...args)}); }
  catch (error) { out.push({ok: false, error: String(error?.message ?? error)}); }
}
process.stdout.write(JSON.stringify(out));
"""


def node_calls(module: str | Path, name: str, cases: list, *, timeout: float = 60) -> list[dict]:
    node = shutil.which("node")
    if not node:
        raise FileNotFoundError("node is not installed")
    payload = json.dumps({"module": str(Path(module).resolve()), "name": name, "cases": cases})
    try:
        done = subprocess.run([node, "--input-type=module", "-e", NODE_PROGRAM], input=payload,
                              capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"node did not answer within {timeout:g}s") from None
    if done.returncode != 0:
        lines = done.stderr.strip().splitlines()
        reason = next((l.split("twin-parity: ", 1)[1] for l in lines if "twin-parity: " in l),
                      next((l for l in lines if l.startswith(("Error", "TypeError", "SyntaxError"))), "?"))
        raise RuntimeError("node failed: " + reason[:300])
    results = json.loads(done.stdout)
    if len(results) != len(cases):
        raise RuntimeError("node returned a different number of results")
    return results


def python_calls(fn, cases: list) -> list[dict]:
    out = []
    for args in cases:
        try:
            # JSON round trip: the value is compared in the form it would cross the boundary.
            out.append({"ok": True, "value": json.loads(json.dumps(fn(*args)))})
        except Exception as error:  # a twin rejecting an input is a result, not a crash
            out.append({"ok": False, "error": str(error)})
    return out


def mismatches(left: list[dict], right: list[dict], *, messages: bool = False) -> list[int]:
    bad = []
    for index, (a, b) in enumerate(zip(left, right)):
        if a["ok"] != b["ok"] or (a["ok"] and a["value"] != b["value"]) or (
                messages and not a["ok"] and a["error"] != b["error"]):
            bad.append(index)
    return bad


def load_python(spec: str):
    path, _, name = spec.rpartition(":")
    if not path or not name:
        raise ValueError(f"expected FILE.py:FUNCTION, got {spec!r}")
    module_spec = importlib.util.spec_from_file_location(Path(path).stem + "_twin", path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return getattr(module, name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("python", metavar="FILE.py:FUNCTION")
    parser.add_argument("node", metavar="FILE.mjs:EXPORT")
    parser.add_argument("--messages", action="store_true", help="also require identical error messages")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    try:
        module, _, name = args.node.rpartition(":")
        if not module or not name:
            raise ValueError(f"expected FILE.mjs:EXPORT, got {args.node!r}")
        cases = json.loads(sys.stdin.read())
        if not isinstance(cases, list) or not all(isinstance(c, list) for c in cases):
            raise ValueError("cases must be a JSON list of argument lists")
        left = python_calls(load_python(args.python), cases)
        right = node_calls(module, name, cases, timeout=args.timeout)
    except (OSError, ValueError, RuntimeError, AttributeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    bad = mismatches(left, right, messages=args.messages)
    for index in bad:
        print(json.dumps({"case": index, "args": cases[index], "python": left[index], "node": right[index]},
                         ensure_ascii=False))
    print(f"{len(cases)} cases, {len(bad)} mismatch(es)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
