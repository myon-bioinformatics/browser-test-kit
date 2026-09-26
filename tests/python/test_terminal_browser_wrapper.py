import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "terminal_browser.py"


def _fake_terminal_browser(tmp_path: Path, body: str) -> dict[str, str]:
    fake = tmp_path / "terminal-browser"
    fake.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env.get('PATH', '')}"
    return env


def _events(stderr: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]


def test_unavailable_is_distinct(tmp_path):
    env = os.environ.copy()
    env["PATH"] = str(tmp_path)
    result = subprocess.run([sys.executable, str(WRAPPER), "--check"], env=env, text=True, capture_output=True)
    assert result.returncode == 127
    assert result.stdout == ""
    assert '"event": "TERMINAL_BROWSER_UNAVAILABLE"' in result.stderr


def test_passthrough_and_log_keep_events_separate(tmp_path):
    env = _fake_terminal_browser(
        tmp_path,
        "printf 'fake terminal-browser: %s\\n' \"$*\"\nprintf '{child-json-like-output}\\n'\n",
    )
    log = tmp_path / "tb.log"
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "--log", str(log), "action", "--help"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout == "fake terminal-browser: action --help\n{child-json-like-output}\n"
    assert log.read_text(encoding="utf-8") == result.stdout
    events = _events(result.stderr)
    assert [event["event"] for event in events] == [
        "terminal_browser_found",
        "terminal_browser_start",
        "terminal_browser_exit",
    ]
    assert all(event["source"] == "terminal-browser" for event in events)


def test_double_dash_passes_top_level_child_flag_verbatim(tmp_path):
    env = _fake_terminal_browser(tmp_path, "printf '%s\\n' \"$*\"\n")
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "--log", str(tmp_path / "version.log"), "--", "--version"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout == "--version\n"
    start = next(event for event in _events(result.stderr) if event["event"] == "terminal_browser_start")
    assert start["argv"][-1] == "--version"
    assert "--" not in start["argv"][1:]


def test_default_mode_does_not_capture_child_stdio(tmp_path, monkeypatch):
    spec = __import__("importlib.util").util.spec_from_file_location("terminal_browser_wrapper", WRAPPER)
    module = __import__("importlib.util").util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    monkeypatch.setattr(module.shutil, "which", lambda _: "/fake/terminal-browser")
    seen = {}

    class Result:
        returncode = 0

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [str(WRAPPER), "open", "http://127.0.0.1:8000"])

    assert module.main() == 0
    assert seen["argv"] == ["/fake/terminal-browser", "open", "http://127.0.0.1:8000"]
    assert "stdout" not in seen["kwargs"]
    assert "stderr" not in seen["kwargs"]


def test_keyboard_interrupt_is_recorded_as_130(monkeypatch, capsys):
    importlib_spec = importlib.util.spec_from_file_location("terminal_browser_interrupt", WRAPPER)
    assert importlib_spec is not None
    module = importlib.util.module_from_spec(importlib_spec)
    assert importlib_spec.loader is not None
    importlib_spec.loader.exec_module(module)

    monkeypatch.setattr(module.shutil, "which", lambda _: "/fake/terminal-browser")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(sys, "argv", [str(WRAPPER), "open", "http://127.0.0.1:8000"])

    assert module.main() == 130
    events = _events(capsys.readouterr().err)
    assert events[-1]["event"] == "terminal_browser_exit"
    assert events[-1]["returncode"] == 130
    assert events[-1]["interrupted"] is True


def test_signal_exit_is_normalized(tmp_path):
    env = _fake_terminal_browser(tmp_path, "kill -TERM $$\n")
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "action"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 143
    events = _events(result.stderr)
    assert events[-1]["event"] == "terminal_browser_exit"
    assert events[-1]["returncode"] == 143
    assert events[-1]["signal"] == 15


def test_check_rejects_child_arguments(tmp_path):
    env = _fake_terminal_browser(tmp_path, "exit 0\n")
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "--check", "action"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "--check cannot be combined" in result.stderr
