"""Python / Node twins give the same results for the same inputs, compared in memory (no files).

Node runs once per twin for every case (stdin -> stdout pipe). Twins may word errors
differently; they must agree on accept/reject and on every accepted value.
"""
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_under_test", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tp = _load("twin_parity")
interaction = _load("interaction")
route_trail = _load("route_trail")
# Locally a missing node skips; on CI it must fail, or the parity check would pass by not running.
needs_node = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("CI"),
                                reason="node is not installed")


def assert_twins_agree(py_fn, module, export, cases):
    left = tp.python_calls(py_fn, cases)
    right = tp.node_calls(ROOT / "scripts" / module, export, cases)
    bad = tp.mismatches(left, right)
    assert not bad, [{"args": cases[i], "python": left[i], "node": right[i]} for i in bad[:5]]
    return left


def press_cases(seed=11, count=400):
    rng = random.Random(seed)
    sixteenth = lambda lo, hi: rng.randint(lo * 16, hi * 16) / 16  # exact binary fractions hit ties
    cases = [
        [{"x": 0, "y": 0, "width": 16, "height": 16}, {"width": 9, "height": 16}, 0.5],   # 9/16: 0.562 vs 0.563
        [{"x": 0, "y": 0, "width": 16, "height": 16}, {"width": 15, "height": 16}, 0.5],
        [None, {"width": 10, "height": 10}],
        [{"x": 0, "y": 0, "width": 0.5, "height": 10}, {"width": 10, "height": 10}],
        [{"x": 0, "y": 0, "width": 10, "height": 10}, {"width": 10, "height": 10}, 0],
        [{"x": 0, "y": 0, "width": 10, "height": 10}, {"width": 10, "height": 10}, 1.5],
        [{"x": -4.5, "y": -0.5, "width": 9, "height": 9}, {"width": 4, "height": 4}, 0.1],
    ]
    for _ in range(count):
        box = {"x": sixteenth(-40, 400), "y": sixteenth(-40, 400), "width": sixteenth(0, 120),
               "height": sixteenth(0, 120)}
        cases.append([box, {"width": rng.choice([320, 390, 1280]), "height": rng.choice([240, 664, 800])},
                      rng.choice([0.25, 0.5, 0.75, 0.9, 1])])
    return cases


EDGE_URLS = [  # every divergence the first parity run found, plus the plain accepted forms
    "http://a/", "https://a.b:8080/x?q#f", "HTTP://A/", "http://[::1]:80/", "https://例え.jp/",
    "file:///tmp/x", "file://localhost/tmp/x", "FILE:///x",
    " http://a/", "http://a b/", "http://%%", "http:// ", "http:///..", "https:///a#", "http://u:p@a/",
    "http://a/\\x", "http://a/\x01", "http://a/\n", "file:/tmp/x", "file://", "file://#.", "file://host/x",
    "file:relative", "ftp://a/", "javascript:alert(1)", "//a/", "http:a", "http://a:99999/", "http://a:/",
]


def url_cases(seed=5, count=400):
    base = {"emoji": "🏠", "route": "/", "url": "http://localhost:8080/#/"}
    cases = [[[dict(base, url=u)]] for u in EDGE_URLS]
    rng = random.Random(seed)
    alphabet = "aA0:/@.\\#?% é[]"
    for _ in range(count):
        tail = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 14)))
        cases.append([[dict(base, url=rng.choice(["http://", "https://", "HtTp://", "file://", "file:", ""]) + tail)]])
    for ready in (None, {}, {"selector": ""}, {"selector": "#a", "text": "x"}, {"selector": "#a", "text": 1},
                  {"selector": "#a", "x": 1}, [], "#a", {"selector": "x" * 513}):
        cases.append([[dict(base, ready=ready)]])
    for steps in ([], "x", [1], [dict(base, extra=1)], [{"emoji": "x", "route": "/"}], [dict(base, emoji=1)]):
        cases.append([steps])
    for timeout in (0, 1, 120000, 120001, -5, True, "10"):
        cases.append([[base], timeout])
    return cases


@needs_node
def test_press_point_twins_agree_including_rounding_ties():
    results = assert_twins_agree(interaction.press_point, "interaction.mjs", "pressPoint", press_cases())
    assert results[0] == {"ok": True, "value": {"x": 8, "y": 8, "visible_ratio": 0.563}}


@needs_node
def test_validate_steps_twins_agree_on_every_url_and_step_shape():
    results = assert_twins_agree(route_trail.validate_steps, "route_trail_node.mjs", "validateSteps", url_cases())
    accepted = {cases[0][0]["url"] for cases, r in zip(url_cases(), results) if r["ok"] and isinstance(cases[0], list)
                and cases[0] and isinstance(cases[0][0], dict) and "ready" not in cases[0][0]}
    assert {"HTTP://A/", "file://localhost/tmp/x", "http://[::1]:80/", "https://例え.jp/"} <= accepted
    assert not {" http://a/", "http://a b/", "http:///..", "file://", "file:/tmp/x", "http://a/\n"} & accepted


def test_execution_url_regex_is_the_same_source_in_both_twins():
    node = (ROOT / "scripts" / "route_trail_node.mjs").read_text(encoding="utf-8")
    source = re.search(r"export const EXECUTION_URL = /(.*)/;", node).group(1)
    assert source == route_trail.EXECUTION_URL_SOURCE


def test_mismatches_and_python_calls():
    left = tp.python_calls(lambda x: {"v": x} if x > 0 else int("bad"), [[1], [0], [2]])
    assert left[0] == {"ok": True, "value": {"v": 1}} and left[1]["ok"] is False
    right = [{"ok": True, "value": {"v": 1}}, {"ok": False, "error": "other words"}, {"ok": True, "value": {"v": 3}}]
    assert tp.mismatches(left, right) == [2]
    assert tp.mismatches(left, right, messages=True) == [1, 2]


@needs_node
def test_cli_reads_cases_from_a_pipe_and_reports_mismatches():
    run = lambda cases, *extra: subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts" / "twin_parity.py"),
         f"{ROOT / 'scripts' / 'interaction.py'}:press_point", f"{ROOT / 'scripts' / 'interaction.mjs'}:pressPoint", *extra],
        input=json.dumps(cases), capture_output=True, text=True, timeout=60)
    ok = run(press_cases(count=20))
    assert ok.returncode == 0 and ok.stdout.strip().endswith("27 cases, 0 mismatch(es)")
    assert run([[None, {"width": 1, "height": 1}]], "--messages").returncode == 0  # same words for this error
    bad = subprocess.run([sys.executable, "-S", str(ROOT / "scripts" / "twin_parity.py"),
                          f"{ROOT / 'scripts' / 'interaction.py'}:press_point", f"{ROOT / 'scripts' / 'interaction.mjs'}:nope"],
                         input="[[1]]", capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2 and "no exported function nope" in bad.stderr
    assert run({"not": "a list"}).returncode == 2
