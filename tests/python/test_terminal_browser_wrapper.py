import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "terminal_browser.py"


def test_unavailable_is_distinct(tmp_path):
    env = os.environ.copy()
    env["PATH"] = str(tmp_path)
    result = subprocess.run([sys.executable, str(WRAPPER), "--check"], env=env, text=True, capture_output=True)
    assert result.returncode == 127
    assert '"event": "TERMINAL_BROWSER_UNAVAILABLE"' in result.stdout


def test_passthrough_and_log(tmp_path):
    fake = tmp_path / "terminal-browser"
    fake.write_text("#!/bin/sh\nprintf 'fake terminal-browser: %s\\n' \"$*\"\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "tb.log"
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env.get('PATH', '')}"
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "--log", str(log), "action", "--help"],
        env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0
    assert "fake terminal-browser: action --help" in result.stdout
    assert log.read_text(encoding="utf-8") == "fake terminal-browser: action --help\n"
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert [event["event"] for event in events] == [
        "terminal_browser_found", "terminal_browser_start", "terminal_browser_exit"
    ]
