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
element_overlay = _load("element_overlay")
# Locally a missing node skips; on CI it must fail, or the parity check would pass by not running.
needs_node = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("CI"),
                                reason="node is not installed")


def assert_twins_agree(py_fn, module, export, cases, *, binary64=False):
    left = tp.python_calls(py_fn, cases)
    right = tp.node_calls(ROOT / "scripts" / module, export, cases)
    if binary64:
        # JSON.stringify may spell large binary64 values as integer tokens.
        # Geometry compares as binary64, rather than Python arbitrary integers.
        left = json.loads(json.dumps(left), parse_int=float)
        right = json.loads(json.dumps(right), parse_int=float)
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


def overlay_cases():
    cases = [
        [[{"x": 10, "y": 20, "width": 100, "height": 40, "name": "Submit", "role": "button"}], {"viewport": "800x600"}],
        [[{"x": -10, "y": -5, "width": 50, "height": 20, "label": "Off", "id": "o1"}], {"viewport": {"width": 800, "height": 600}}],
        [[{"x": 0, "y": 0, "width": 0, "height": 10}, "invalid"], {}],
        [[{"x": 10, "y": 10, "width": 50, "height": 20, "name": "Search"}], {"find": "search"}],
    ]
    for x in (0.125, -0.125, 0.375, -0.375, 2.675, -0.005, 1e308, 1.8545181812522246e17):
        cases.append([[{"x": x, "y": x, "width": 0.25, "height": 0.75}], {}])
    for field in ("x", "y", "width", "height"):
        for value in (True, False, None, "1"):
            cases.append([[{"x": 0, "y": 0, "width": 2, "height": 2} | {field: value}], {}])
    box = {"x": 0, "y": 0, "width": 2, "height": 2}
    for value in (True, False, None, 0, "1"):
        cases.append([[box], {"viewport": {"width": value, "w": 800, "height": 600}}])
    rng = random.Random(109)
    for _ in range(100):
        box = {key: rng.randint(-1000, 1000) / 16 for key in ("x", "y")}
        box.update({key: rng.randint(1, 1000) / 16 for key in ("width", "height")})
        cases.append([[box], {"viewport": "390x844"}])
    return cases


@needs_node
def test_element_overlay_annotate_twins_agree():
    results = assert_twins_agree(element_overlay.annotate_elements, "element_overlay.mjs", "annotateElements", overlay_cases(), binary64=True)
    assert [row["value"]["count"] for row in results[:4]] == [1, 1, 0, 1]
    assert results[4]["value"]["items"][0]["x"] == 0.13
    assert results[5]["value"]["items"][0]["x"] == -0.12


@needs_node
def test_element_overlay_rejects_non_finite_and_boolean_geometry_in_both_apis():
    # Non-finite values cannot travel through JSON; exercise each API directly.
    invalid = [True, False, float("nan"), float("inf"), -float("inf")]
    base = {"x": 0, "y": 0, "width": 2, "height": 2}
    counts = [element_overlay.annotate_elements([base | {field: value}])["count"]
              for field in base for value in invalid]
    viewports = [element_overlay.annotate_elements([base], {"viewport": {"width": value, "height": 600}})["viewport"]
                 for value in invalid]
    overflowing = {"x": 1e308, "y": 0, "width": 1e308, "height": 2}
    counts.append(element_overlay.annotate_elements([overflowing])["count"])
    assert counts == [0] * 21
    assert viewports == [None] * 5
    program = """
      const {annotateElements} = await import(process.argv[1]);
      const invalid = [true, false, NaN, Infinity, -Infinity];
      const base = {x:0, y:0, width:2, height:2};
      const counts = Object.keys(base).flatMap(field => invalid.map(value =>
        annotateElements([{...base, [field]:value}]).count));
      const viewports = invalid.map(value =>
        annotateElements([base], {viewport:{width:value, height:600}}).viewport);
      counts.push(annotateElements([{x:1e308,y:0,width:1e308,height:2}]).count);
      console.log(JSON.stringify({counts,viewports}));
    """
    done = subprocess.run(["node", "--input-type=module", "-e", program,
                           (ROOT / "scripts/element_overlay.mjs").as_uri()],
                          text=True, capture_output=True, timeout=10)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {"counts": counts, "viewports": viewports}


@needs_node
def test_element_overlay_highlight_css_twins_agree():
    cases = [
        [["#btn-1", {"selector": ".btn-2"}], "#ff0055", 2],
        [[], "#000000", 1],
    ]
    assert_twins_agree(element_overlay.build_highlight_css, "element_overlay.mjs", "buildHighlightCss", cases)


@needs_node
def test_element_overlay_assert_twins_agree():
    cases = [
        [[{"x": 10, "y": 20, "width": 100, "height": 40, "name": "Submit", "role": "button"}], {"min_count": 1, "assert_role": "button"}],
        [[], {"min_count": 1}],
    ]
    results = assert_twins_agree(element_overlay.assert_elements, "element_overlay.mjs", "assertElements", cases)
    assert results[0]["value"]["ok"] is True
    assert results[1]["value"]["ok"] is False


@needs_node
def test_validate_steps_twins_agree_on_every_url_and_step_shape():
    results = assert_twins_agree(route_trail.validate_steps, "route_trail_node.mjs", "validateSteps", url_cases())
    accepted = {cases[0][0]["url"] for cases, r in zip(url_cases(), results) if r["ok"] and isinstance(cases[0], list)
                and cases[0] and isinstance(cases[0][0], dict) and "ready" not in cases[0][0]}
    assert {"HTTP://A/", "file://localhost/tmp/x", "http://[::1]:80/"} <= accepted
    assert not {" http://a/", "http://a b/", "http:///..", "file://", "file:/tmp/x", "http://a/\n", "https://例え.jp/", "http://a:99999/"} & accepted


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


@needs_node
def test_element_overlay_viewport_edges_and_alias_contract():
    box = {"x": 0, "y": 0, "width": 2, "height": 2}
    cases = []
    expected = []
    for field, alias in {"x": "left", "y": "top", "width": "w", "height": "h"}.items():
        cases.append([[{**box, field: None, alias: 2}], {}])
        expected.append((0, None, None))
    for viewport, valid in [("８００x６００", False), ("٠٨٠٠x٦٠٠", False),
                            ("0x600", False), ("2X2", True),
                            ("\u00852x2", False), ("\ufeff2x2", False),
                            ("2x2\u0085", False), ("2x2\ufeff", False),
                            (" \t2x2\r\n", True),
                            ({"w": 2, "h": 2}, True)]:
        cases.append([[box], {"viewport": viewport}])
        expected.append((1, {"width": 2, "height": 2} if valid else None, False))
    for field in ("width", "height"):
        for value in (True, False, None, 0, -1, "2"):
            viewport = {"width": 2, "height": 2, field: value, "w": 2, "h": 2}
            cases.append([[box], {"viewport": viewport}])
            expected.append((1, None, False))
    for x, width, clipped in [(0, 2, False), (-0.004, 2, True),
                              (0.004, 2, True), (2, 0.001, True),
                              (0, 0.001, False)]:
        cases.append([[{**box, "x": x, "width": width}], {"viewport": "2x2"}])
        expected.append((1, {"width": 2, "height": 2}, clipped))
    results = assert_twins_agree(element_overlay.annotate_elements, "element_overlay.mjs", "annotateElements", cases)
    for result, (count, viewport, clipped) in zip(results, expected):
        value = result["value"]
        assert value["count"] == count and value["viewport"] == viewport
        if count:
            assert value["items"][0]["clipped"] is clipped
        json.dumps(value, allow_nan=False)


@needs_node
def test_element_overlay_svg_twins_agree_without_precision_loss():
    # Compare complete SVG strings, not just parsed annotation records.
    cases = overlay_cases()
    for x in (123456.78, -123456.78, 1e20, 1e308, -0.0):
        cases.append([[{"x": x, "y": 20.125, "width": 1, "height": 2}], {}])
    cases.append([[{"x": 0.125, "y": -0.125, "width": 0.25, "height": 0.75}],
                  {"viewport": {"width": 0.0001, "height": 5e-324}, "fill_opacity": 0.125}])
    results = assert_twins_agree(element_overlay.render_svg_overlay, "element_overlay.mjs", "renderSvgOverlay", cases)
    svg = results[-6]["value"]
    assert 'x="1.2345678e5"' in svg
    assert 'cx="1.2345728e5"' in svg
    # A decimal formatting half tie must use the same direction too.
    tie = 1000000000000000.25
    formatted = assert_twins_agree(element_overlay.render_svg_overlay, "element_overlay.mjs", "renderSvgOverlay",
                                  [[[], {"width": tie, "height": tie}]])
    assert 'width="1.0000000000000003e15"' in formatted[0]["value"]
    # Rendering a precomputed evidence record uses the same formatting path.
    records = [[element_overlay.annotate_elements(*args), args[1]] for args in cases]
    assert_twins_agree(element_overlay.render_svg_overlay, "element_overlay.mjs", "renderSvgOverlay", records)


@needs_node
def test_element_overlay_empty_text_fields_fall_back_in_both_twins():
    box = {"x": 0, "y": 0, "width": 1, "height": 1,
           "name": "", "label": "Fallback", "selector": "", "id": "target"}
    results = assert_twins_agree(element_overlay.annotate_elements, "element_overlay.mjs", "annotateElements", [[[box], {}]])
    assert results[0]["value"]["items"][0]["name"] == "Fallback"
    assert results[0]["value"]["items"][0]["selector"] == "#target"
