"""observe --after-action / --after-click: one step, then a second snapshot in its own file."""
import functools
import json
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import page_inspect  # noqa: E402

SCRIPT = ROOT / "scripts" / "page_inspect.py"

FIRST = """<!doctype html><meta charset="utf-8"><title>first</title>
<a id="next" href="second.html">Next</a>
"""
SECOND = """<!doctype html><meta charset="utf-8"><title>second</title>
<button id="done">Done</button>
"""

HOVER = """<!doctype html><meta charset="utf-8"><title>hover</title>
<style>
  #secret { display: none; }
  #host:hover #secret { display: block; }
</style>
<div id="host"><span>hover here</span><button id="secret">revealed</button></div>
"""

SCROLL = """<!doctype html><meta charset="utf-8"><title>scroll</title>
<style>body { min-height: 2400px; }</style>
<div id="top">top</div>
<div id="far" style="margin-top:1800px"><button id="deep">deep</button></div>
<script>
  const deep = document.getElementById('deep');
  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !document.getElementById('injected')) {
      const b = document.createElement('button');
      b.id = 'injected';
      b.textContent = 'after scroll';
      document.body.appendChild(b);
    }
  }).observe(deep);
</script>
"""


def run(args, cwd):
    return subprocess.run([sys.executable, str(SCRIPT), "observe", *args], cwd=cwd,
                          capture_output=True, text=True, timeout=180)


def test_parse_after_action_accepts_all_kinds():
    assert page_inspect.parse_after_action("click:id:save") == {"kind": "click", "locator": "id:save"}
    assert page_inspect.parse_after_action("hover:testid:menu") == {"kind": "hover", "locator": "testid:menu"}
    assert page_inspect.parse_after_action("scroll:0,-400") == {"kind": "scroll", "dx": 0, "dy": -400}
    assert page_inspect.parse_after_action("scroll:id:deep") == {"kind": "scroll_into", "locator": "id:deep"}
    assert page_inspect.parse_after_action("scroll-into:css:#deep") == {"kind": "scroll_into", "locator": "css:#deep"}


def test_parse_after_action_rejects_bad_specs():
    with pytest.raises(page_inspect.InspectError):
        page_inspect.parse_after_action("h:1")
    with pytest.raises(page_inspect.InspectError):
        page_inspect.parse_after_action("scroll:1")
    with pytest.raises(page_inspect.InspectError):
        page_inspect.parse_after_action("tap:id:x")


def test_sequence_arguments_are_checked_before_any_browser_launch(tmp_path):
    url = "http://127.0.0.1:9/index.html"
    missing_after = run([url, "--after-click", "id:next", "--out", str(tmp_path / "a.json")], tmp_path)
    assert missing_after.returncode == 2 and "--after-out" in missing_after.stderr
    missing_out = run([url, "--after-action", "click:id:next", "--after-out", str(tmp_path / "b.json")], tmp_path)
    assert missing_out.returncode == 2 and "--out" in missing_out.stderr
    both = run([url, "--after-click", "id:next", "--after-action", "click:id:next", "--out", str(tmp_path / "a.json"),
                "--after-out", str(tmp_path / "b.json")], tmp_path)
    assert both.returncode == 2 and "only one" in both.stderr
    ordinal = run([url, "--after-action", "click:h:2", "--out", str(tmp_path / "a.json"),
                   "--after-out", str(tmp_path / "b.json")], tmp_path)
    assert ordinal.returncode == 2 and "ordinal" in ordinal.stderr
    same = run([url, "--after-click", "id:next", "--out", str(tmp_path / "a.json"),
                "--after-out", str(tmp_path / "a.json")], tmp_path)
    assert same.returncode == 2 and "different files" in same.stderr
    no_dir = run([url, "--after-click", "id:next", "--out", str(tmp_path / "a.json"),
                  "--after-out", str(tmp_path / "missing" / "b.json")], tmp_path)
    assert no_dir.returncode == 2 and "directory does not exist" in no_dir.stderr
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["ok"] is False
    assert not (tmp_path / "missing" / "b.json").exists()


def _compare_dom_differs(before_path, after_path, cwd):
    compared = subprocess.run([sys.executable, "-S", str(SCRIPT), "compare", str(before_path), str(after_path), "--json"],
                              cwd=cwd, capture_output=True, text=True, timeout=60)
    assert compared.returncode == 0
    sections = json.loads(compared.stdout)["sections"]
    assert sections["dom"]["relation"] == "different"


@pytest.mark.browser
def test_click_then_second_snapshot_in_its_own_file(tmp_path):
    (tmp_path / "first.html").write_text(FIRST, encoding="utf-8")
    (tmp_path / "second.html").write_text(SECOND, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/first.html"
        done = run([url, "--after-action", "click:id:next", "--out", str(tmp_path / "before.json"),
                    "--after-out", str(tmp_path / "after.json"), "--json"], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    before = json.loads((tmp_path / "before.json").read_text(encoding="utf-8"))
    after = json.loads((tmp_path / "after.json").read_text(encoding="utf-8"))
    assert before["url"].endswith("/first.html") and "step" not in before
    assert after["url"].endswith("/second.html")
    assert after["step"]["index"] == 2 and after["step"]["action"] == "click"
    assert after["step"]["target"] == "id:next"
    assert after["limits"]["click_runs_page_scripts"] is True
    _compare_dom_differs(tmp_path / "before.json", tmp_path / "after.json", tmp_path)


@pytest.mark.browser
def test_hover_reveals_control_in_second_snapshot(tmp_path):
    (tmp_path / "index.html").write_text(HOVER, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        done = run([url, "--after-action", "hover:id:host", "--out", str(tmp_path / "before.json"),
                    "--after-out", str(tmp_path / "after.json"), "--json"], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    after = json.loads((tmp_path / "after.json").read_text(encoding="utf-8"))
    assert after["step"]["action"] == "hover"
    assert after["limits"].get("hover_may_trigger_css") is True
    names = [element.get("name") for element in after.get("elements") or []]
    assert "revealed" in names
    _compare_dom_differs(tmp_path / "before.json", tmp_path / "after.json", tmp_path)


@pytest.mark.browser
def test_scroll_wheel_triggers_dom_change_in_second_snapshot(tmp_path):
    page = """<!doctype html><meta charset="utf-8"><title>wheel</title>
<style>body { height: 3000px; }</style>
<div id="top">top</div>
<script>
  window.addEventListener('scroll', () => {
    if (!document.getElementById('injected')) {
      const b = document.createElement('button');
      b.id = 'injected';
      document.body.appendChild(b);
    }
  }, {passive: true});
</script>
"""
    (tmp_path / "wheel.html").write_text(page, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/wheel.html"
        done = run([url, "--after-action", "scroll:0,800", "--out", str(tmp_path / "before.json"),
                    "--after-out", str(tmp_path / "after.json"), "--json"], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    after = json.loads((tmp_path / "after.json").read_text(encoding="utf-8"))
    assert after["step"]["action"] == "scroll" and after["step"]["target"] == "0,800"
    scroll_y = after["limits"]["scroll_y"]
    assert 650 <= scroll_y <= 950, f"expected scrollY near 800, got {scroll_y}"
    ids = [element.get("id") for element in after.get("elements") or []]
    assert "injected" in ids


@pytest.mark.browser
def test_scroll_into_view_triggers_dom_change_in_second_snapshot(tmp_path):
    (tmp_path / "index.html").write_text(SCROLL, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        done = run([url, "--after-action", "scroll-into:id:deep", "--out", str(tmp_path / "before.json"),
                    "--after-out", str(tmp_path / "after.json"), "--json"], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    after = json.loads((tmp_path / "after.json").read_text(encoding="utf-8"))
    assert after["step"]["action"] == "scroll_into"
    assert after["step"]["target"] == "id:deep"
    assert after["limits"].get("scroll_may_run_page_scripts") is True
    ids = [element.get("id") for element in after.get("elements") or []]
    assert "injected" in ids
    _compare_dom_differs(tmp_path / "before.json", tmp_path / "after.json", tmp_path)


@pytest.mark.browser
def test_after_click_alias_matches_explicit_click_action(tmp_path):
    (tmp_path / "first.html").write_text(FIRST, encoding="utf-8")
    (tmp_path / "second.html").write_text(SECOND, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/first.html"
        done = run([url, "--after-click", "id:next", "--out", str(tmp_path / "before.json"),
                    "--after-out", str(tmp_path / "after.json"), "--json"], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    after = json.loads((tmp_path / "after.json").read_text(encoding="utf-8"))
    assert after["step"]["action"] == "click" and after["step"]["target"] == "id:next"


@pytest.mark.browser
def test_same_page_observed_twice_reads_same_for_identity_sections(tmp_path):
    (tmp_path / "first.html").write_text(FIRST, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/first.html"
        for name in ("one.json", "two.json"):
            done = run([url, "--out", str(tmp_path / name), "--json"], tmp_path)
            assert done.returncode == 0, done.stderr
    finally:
        server.shutdown()
    compared = subprocess.run([sys.executable, "-S", str(SCRIPT), "compare", str(tmp_path / "one.json"),
                               str(tmp_path / "two.json"), "--json"], cwd=tmp_path,
                              capture_output=True, text=True, timeout=60)
    sections = json.loads(compared.stdout)["sections"]
    for name in ("dom", "accessibility", "resources"):
        assert sections[name]["relation"] == "same", name
