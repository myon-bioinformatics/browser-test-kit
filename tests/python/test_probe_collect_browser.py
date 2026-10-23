"""Collect counts from real Chromium against a deterministic local fixture."""
import functools
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_survey  # noqa: E402

PAGE = """<!doctype html><meta charset="utf-8"><title>fixture</title>
<button>one</button><button>two</button><a href="#x">link</a>
<input type="hidden" name="h"><input type="text">
<div id="host"></div>
<script>
  const root = document.getElementById('host').attachShadow({mode: 'open'});
  root.innerHTML = '<button>inside shadow</button>';
</script>
<iframe src="child.html"></iframe>
"""
CHILD = '<!doctype html><meta charset="utf-8"><button>in frame</button>'


@pytest.mark.browser
def test_collect_counts_from_live_page(tmp_path):
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    (tmp_path / "child.html").write_text(CHILD, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        from playwright.sync_api import sync_playwright
        import probe_collect
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True, timeout=60000)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="load", timeout=30000)
                page.wait_for_selector("iframe")
                page.wait_for_function("() => document.querySelector('iframe').contentDocument?.readyState === 'complete'")
                snapshot = probe_collect.collect(page)
            finally:
                browser.close()
    finally:
        server.shutdown()
    assert snapshot["origin"] == f"http://127.0.0.1:{server.server_port}"
    # Light DOM only: two buttons, one link, one visible text input (hidden input excluded).
    assert snapshot["interactive"] == {"count": 4, "collection": "partial"}
    assert snapshot["shadow_roots"] == 1
    assert snapshot["frames"] == 1
    ev = probe_survey.summarize(snapshot)
    assert ev["overall"] == "partial"
    assert "shadow roots (1): not entered" in ev["not_examined"]
    assert "child frames (1): not entered" in ev["not_examined"]
