"""Collect counts from real Chromium against a deterministic local fixture (Python, CLI and Node twin)."""
import functools
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

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
EXPECTED = {"interactive": {"count": 4, "collection": "partial"}, "shadow_roots": 1, "frames": 1}


@pytest.fixture
def fixture_url(tmp_path):
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    (tmp_path / "child.html").write_text(CHILD, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _load_page_and_collect(url):
    import probe_collect
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True, timeout=60000)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_function("() => document.querySelector('iframe').contentDocument?.readyState === 'complete'")
            return probe_collect.collect(page)
        finally:
            browser.close()


@pytest.mark.browser
def test_collect_counts_from_live_page(fixture_url):
    snapshot = _load_page_and_collect(fixture_url + "/index.html")
    assert snapshot["origin"] == fixture_url
    # Light DOM only: two buttons, one link, one visible text input (hidden input excluded).
    assert {k: snapshot[k] for k in EXPECTED} == EXPECTED
    ev = probe_survey.summarize(snapshot)
    assert ev["overall"] == "partial"
    assert "shadow roots (1): not entered" in ev["not_examined"]
    assert "child frames (1): not entered" in ev["not_examined"]


@pytest.mark.browser
def test_cli_prints_envelope_and_refuses_bad_urls(fixture_url):
    run = subprocess.run([sys.executable, str(SCRIPTS / "probe_collect.py"), fixture_url + "/index.html"],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    ev = json.loads(run.stdout)
    assert ev["schema"] == "btk-probe-evidence/1"
    assert ev["overall"] == "partial"
    assert ev["target"] == {"origin": fixture_url}
    refused = subprocess.run([sys.executable, str(SCRIPTS / "probe_collect.py"), "https://u:p@x.test/"],
                             capture_output=True, text=True, timeout=60)
    assert refused.returncode == 2
    assert "credentials" in refused.stderr or "http(s)" in refused.stderr


@pytest.mark.browser
@pytest.mark.skipif(shutil.which("node") is None or not (ROOT / "node_modules" / "playwright").exists(),
                    reason="node and the repo's playwright package are required")
def test_node_twin_collects_the_same_snapshot(fixture_url):
    script = (
        "import {chromium} from 'playwright';\n"
        "import {collect} from './scripts/probe_collect.mjs';\n"
        f"const browser = await chromium.launch({{headless: true, executablePath: {json.dumps(os.environ.get('BTK_NODE_CHROMIUM') or None)}}});\n"
        "try {\n"
        "  const page = await browser.newPage();\n"
        f"  await page.goto({json.dumps(fixture_url + '/index.html')}, {{waitUntil: 'load'}});\n"
        "  await page.waitForFunction(() => document.querySelector('iframe').contentDocument?.readyState === 'complete');\n"
        "  process.stdout.write(JSON.stringify(await collect(page)));\n"
        "} finally { await browser.close(); }\n"
    )
    run = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    node_snapshot = json.loads(run.stdout)
    py_snapshot = _load_page_and_collect(fixture_url + "/index.html")
    assert node_snapshot == py_snapshot
