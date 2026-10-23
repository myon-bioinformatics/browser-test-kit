"""act's first-stage actions reach the Playwright method of the same name; the page shows each one in the name of the #out button. (id "status" is avoided: it clashes with window.status.)"""
import functools
import json
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "btk.py"

PAGE = """<!doctype html><meta charset="utf-8"><title>actions fixture</title>
<button id="out" onclick="this.textContent='clicked'">idle</button>
<input id="box" type="checkbox" onchange="out.textContent = this.checked ? 'checked' : 'unchecked'">
<button id="dbl" ondblclick="out.textContent='dblclicked'">dbl</button>
<button id="hov" onmouseover="out.textContent='hovered'">hov</button>
<input id="name" onkeydown="if (event.key === 'Enter') out.textContent='entered'">
<select id="pick" onchange="out.textContent='picked ' + this.value"><option value="a">a</option><option value="b">b</option></select>
"""


def act(url, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "act", url, *args, "--json"],
                          capture_output=True, text=True, timeout=180)


def test_text_actions_need_text_before_any_browser_launch():
    run = subprocess.run([sys.executable, "-S", str(SCRIPT), "act", "http://127.0.0.1:9/x", "--action", "select",
                          "--locator", "id:pick", "--json"], capture_output=True, text=True, timeout=60)
    assert run.returncode == 2 and "select needs --text" in run.stdout


@pytest.mark.browser
def test_each_action_changes_the_page_the_way_playwright_would(tmp_path):
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        cases = [
            (["--action", "check", "--locator", "id:box"], "checked"),
            (["--action", "dblclick", "--locator", "id:dbl"], "dblclicked"),
            (["--action", "hover", "--locator", "id:hov"], "hovered"),
            (["--action", "press", "--locator", "id:name", "--text", "Enter"], "entered"),
            (["--action", "select", "--locator", "id:pick", "--text", "b"], "picked b"),
        ]
        results = []
        for args, expected in cases:
            done = act(url, *args)
            assert done.returncode == 0, (args, done.stdout, done.stderr)
            body = json.loads(done.stdout)
            names = body["sections"]["accessibility"].get("names", [])
            results.append((args[1], expected in names, body["limits"]["page_js_called"]))
    finally:
        server.shutdown()
    assert all(found for _, found, _ in results), results
    assert all(js for _, _, js in results), results
