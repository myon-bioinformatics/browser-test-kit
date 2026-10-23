"""Multi-step observe, viewport, interstitial events, and compare deltas."""
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

MULTI = """<!doctype html><meta charset="utf-8"><title>steps</title>
<input id="q" type="text" />
<button id="go">Go</button>
<div id="out"></div>
<script>
  document.getElementById('go').addEventListener('click', () => {
    document.getElementById('out').textContent = document.getElementById('q').value || 'empty';
    console.warn('clicked');
  });
  fetch('/missing').catch(() => {});
</script>
"""

EVENTS = """<!doctype html><meta charset="utf-8"><title>events</title>
<button id="bad">fail</button>
<script>
  document.getElementById('bad').addEventListener('click', () => {
    console.error('boom');
    fetch('/nope');
  });
</script>
"""


def run(args, cwd):
    return subprocess.run([sys.executable, str(SCRIPT), "observe", *args], cwd=cwd,
                          capture_output=True, text=True, timeout=180)


def test_parse_step_spec_new_kinds():
    step = page_inspect.parse_step_spec("type:id:q=hello")
    assert step["kind"] == "type" and step["locator"] == "id:q" and step["text"] == "hello"
    assert page_inspect.parse_step_spec("press:Enter")["kind"] == "press"
    assert page_inspect.parse_step_spec("focus:id:q")["kind"] == "focus"
    assert page_inspect.parse_step_spec("wait:250")["kind"] == "wait_ms"
    assert page_inspect.parse_step_spec("wait:id:go")["kind"] == "wait_locator"


def test_parse_viewport():
    assert page_inspect.parse_viewport("1280x720") == {"width": 1280, "height": 720}
    with pytest.raises(page_inspect.InspectError):
        page_inspect.parse_viewport("bad")


@pytest.mark.browser
def test_multi_step_writes_indexed_snapshots(tmp_path):
    (tmp_path / "index.html").write_text(MULTI, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    steps_dir = tmp_path / "steps"
    steps_dir.mkdir()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        done = run([
            url, "--out", str(tmp_path / "passive.json"),
            "--steps-dir", str(steps_dir),
            "--step", "focus:id:q",
            "--step", "type:id:q=hi",
            "--step", "click:id:go",
            "--json",
        ], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    one = json.loads((steps_dir / "step-001.json").read_text(encoding="utf-8"))
    three = json.loads((steps_dir / "step-003.json").read_text(encoding="utf-8"))
    assert one["step"]["index"] == 2 and one["step"]["action"] == "focus"
    two = json.loads((steps_dir / "step-002.json").read_text(encoding="utf-8"))
    assert two["step"]["action"] == "type" and two["step"]["target"] == "id:q"
    assert two["step"]["value_meta"]["length"] == 2
    assert "hi" not in json.dumps(two["step"]["events"])
    assert three["step"]["index"] == 4 and three["step"]["action"] == "click"
    console = three["step"]["events"]["console"]
    assert console and console[0]["level"] == "warning" and console[0]["source"] == "console"
    assert console[0].get("count", 1) == 1
    assert "clicked" not in json.dumps(console)


@pytest.mark.browser
def test_step_events_capture_without_message_bodies(tmp_path):
    (tmp_path / "index.html").write_text(EVENTS, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        done = run([
            url, "--out", str(tmp_path / "passive.json"),
            "--after-out", str(tmp_path / "after.json"),
            "--step", "click:id:bad",
            "--json",
        ], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    events = json.loads((tmp_path / "after.json").read_text(encoding="utf-8"))["step"]["events"]
    assert events["bodies"] == "not_recorded"
    assert events["console"] and all(item["level"] == "error" for item in events["console"])
    assert events["failed_requests"] and events["failed_requests"][0]["url"].endswith("/nope")
    dumped = json.dumps(events)
    assert "boom" not in dumped


@pytest.mark.browser
def test_viewport_is_recorded_on_environment(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        done = run([url, "--viewport", "640x480", "--json"], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    env = json.loads(done.stdout)["environment"]
    assert env["viewport"] == {"width": 640, "height": 480}


@pytest.mark.browser
def test_compare_reports_step_event_deltas(tmp_path):
    passive = {
        "schema": page_inspect.SCHEMA_OBSERVE,
        "url": "http://127.0.0.1:1/",
        "environment": {"os": "linux", "browser": "chromium", "profile": "desktop", "headless": True},
        "sections": {},
        "elements": [],
        "total": 0,
        "child_frames": 0,
    }
    quiet = dict(passive)
    quiet["step"] = {"events": {"console": [], "failed_requests": [], "navigations": [], "truncated": False, "bodies": "not_recorded"}}
    noisy = dict(passive)
    noisy["step"] = {"events": {"console": [{"level": "warning"}], "failed_requests": [{"url": "http://127.0.0.1:1/nope", "status": 404}], "navigations": [], "truncated": False, "bodies": "not_recorded"}}
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(page_inspect.dumps(quiet), encoding="utf-8")
    right.write_text(page_inspect.dumps(noisy), encoding="utf-8")
    compared = subprocess.run([sys.executable, "-S", str(SCRIPT), "compare", str(left), str(right), "--json"],
                              cwd=tmp_path, capture_output=True, text=True, timeout=30)
    report = json.loads(compared.stdout)
    assert report["step_events"]["relation"] == "different"
    assert report["step_events"]["counts"]["console"]["delta"] == 1


FAILURES = """<!doctype html><meta charset="utf-8"><title>failures</title>
<button id="go">Go</button>
<script>
  document.getElementById('go').addEventListener('click', () => {
    fetch('/a404');
    fetch('/b404');
    fetch('/c404');
  });
</script>
"""

CONSOLE_DUP = """<!doctype html><meta charset="utf-8"><title>dup</title>
<button id="go">Go</button>
<script>
  document.getElementById('go').addEventListener('click', () => {
    console.warn('same');
    console.warn('same');
  });
</script>
"""


@pytest.mark.browser
def test_step_events_record_distinct_failed_requests(tmp_path):
    (tmp_path / "index.html").write_text(FAILURES, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        steps_dir = tmp_path / "steps"
        steps_dir.mkdir()
        done = run([
            url, "--out", str(tmp_path / "passive.json"),
            "--steps-dir", str(steps_dir),
            "--step", "click:id:go",
            "--step", "wait:400",
            "--json",
        ], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    failed = json.loads((steps_dir / "step-001.json").read_text(encoding="utf-8"))["step"]["events"]["failed_requests"]
    urls = [row["url"] for row in failed]
    assert any(url.endswith("/a404") for url in urls)
    assert any(url.endswith("/b404") for url in urls)
    assert any(url.endswith("/c404") for url in urls)
    assert len({row["url"] for row in failed}) == 3


def test_step_collector_strips_userinfo_from_request_url():
    class FakeClient:
        def on(self, *_args, **_kwargs):
            return None

        def remove_listener(self, *_args, **_kwargs):
            return None

    collector = page_inspect.StepEventCollector(FakeClient(), None, [])
    collector._request_urls["req-1"] = page_inspect.strip_userinfo("http://user:secret@127.0.0.1:1/x")
    collector._note_failed("req-1", 404, "")
    assert collector.failed_requests[0]["url"] == "http://127.0.0.1:1/x"


@pytest.mark.browser
def test_step_events_dedupe_console_rows_with_count(tmp_path):
    (tmp_path / "index.html").write_text(CONSOLE_DUP, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        done = run([
            url, "--out", str(tmp_path / "passive.json"),
            "--after-out", str(tmp_path / "after.json"),
            "--step", "click:id:go",
            "--json",
        ], tmp_path)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    console = json.loads((tmp_path / "after.json").read_text(encoding="utf-8"))["step"]["events"]["console"]
    assert len(console) == 1
    assert console[0]["level"] == "warning" and console[0]["count"] == 2


@pytest.mark.browser
def test_value_meta_length_only_unless_storage_fingerprints(tmp_path):
    (tmp_path / "index.html").write_text(MULTI, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        plain = run([
            url, "--out", str(tmp_path / "passive.json"),
            "--after-out", str(tmp_path / "plain.json"),
            "--step", "type:id:q=secret",
            "--json",
        ], tmp_path)
        flagged = run([
            url, "--out", str(tmp_path / "passive2.json"),
            "--after-out", str(tmp_path / "finger.json"),
            "--include-storage-keys",
            "--include-storage-fingerprints",
            "--step", "type:id:q=secret",
            "--json",
        ], tmp_path)
    finally:
        server.shutdown()
    assert plain.returncode == 0 and flagged.returncode == 0, plain.stderr + flagged.stderr
    plain_meta = json.loads((tmp_path / "plain.json").read_text(encoding="utf-8"))["step"]["value_meta"]
    finger_meta = json.loads((tmp_path / "finger.json").read_text(encoding="utf-8"))["step"]["value_meta"]
    assert plain_meta == {"length": 6}
    assert finger_meta["length"] == 6 and "sha256" in finger_meta
