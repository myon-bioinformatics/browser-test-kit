"""Exercise scripts/pytest_btk_events.py the way a project actually loads it:
as a real, separate `pytest -p pytest_btk_events` subprocess against a tiny
temp test file. No pytester plugin is used or required.
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

FIXTURE_TESTS = '''
import pytest

def test_pass():
    assert True

def test_fail():
    assert False

def test_skip():
    pytest.skip("not relevant here")

@pytest.mark.skip(reason="marker skip, evaluated during setup")
def test_marker_skip():
    assert True

@pytest.fixture
def broken_fixture():
    raise RuntimeError("fixture setup boom")

def test_setup_error(broken_fixture):
    assert True
'''


def _env_with_scripts_on_path():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SCRIPTS) + (os.pathsep + existing if existing else "")
    return env


def _read_events(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_opt_in_writes_nothing_without_the_flag(tmp_path):
    test_file = tmp_path / "test_fixture.py"
    test_file.write_text(FIXTURE_TESTS, encoding="utf-8")
    env = _env_with_scripts_on_path()

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-p", "pytest_btk_events", "-q"],
        env=env,
        text=True,
        capture_output=True,
    )

    # The plugin loaded (no import error) but did nothing: no --btk-events path
    # was given, so it must not write anywhere on its own.
    assert "pytest_btk_events" not in result.stderr or "Error" not in result.stderr
    assert not any(tmp_path.glob("*.jsonl"))


def test_records_one_event_per_test_with_the_right_status_and_stage(tmp_path):
    test_file = tmp_path / "test_fixture.py"
    test_file.write_text(FIXTURE_TESTS, encoding="utf-8")
    events_path = tmp_path / "btk-events.jsonl"
    env = _env_with_scripts_on_path()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-p",
            "pytest_btk_events",
            "--btk-events",
            str(events_path),
            "-q",
        ],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1, result.stdout + result.stderr  # test_fail + test_setup_error
    assert events_path.is_file()
    events = _read_events(events_path)
    assert all(event["schema"] == "btk-event/1" for event in events)
    assert all(event["source"] == "pytest-btk-events" for event in events)

    by_test = {
        event["test_id"].rsplit("::", 1)[-1]: event
        for event in events
        if event["event"] == "test_result"
    }
    assert by_test["test_pass"]["status"] == "passed"
    assert by_test["test_pass"]["stage"] == "call"
    assert by_test["test_fail"]["status"] == "failed"
    assert by_test["test_fail"]["stage"] == "call"
    # A runtime pytest.skip() inside the test body is reported at the "call" phase.
    assert by_test["test_skip"]["status"] == "skipped"
    assert by_test["test_skip"]["stage"] == "call"
    # A skip marker is evaluated before the test body ever runs: "setup" phase.
    assert by_test["test_marker_skip"]["status"] == "skipped"
    assert by_test["test_marker_skip"]["stage"] == "setup"
    assert by_test["test_setup_error"]["status"] == "error"
    assert by_test["test_setup_error"]["stage"] == "setup"
    assert "boom" in by_test["test_setup_error"]["message"]

    events_by_name = [event["event"] for event in events]
    assert events_by_name[0] == "session_start"
    summary = next(event for event in events if event["event"] == "session_summary")
    assert summary["status"] == "failed"
    assert summary["returncode"] == 1
    assert summary["count_passed"] == 1
    assert summary["count_failed"] == 1
    assert summary["count_skipped"] == 2
    assert summary["count_error"] == 1


def test_project_and_run_id_are_recorded_on_every_event(tmp_path):
    test_file = tmp_path / "test_fixture.py"
    test_file.write_text("def test_pass():\n    assert True\n", encoding="utf-8")
    events_path = tmp_path / "btk-events.jsonl"
    env = _env_with_scripts_on_path()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-p",
            "pytest_btk_events",
            "--btk-events",
            str(events_path),
            "--btk-events-project",
            "demo-project",
            "--btk-events-run-id",
            "run-123",
            "-q",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    events = _read_events(events_path)
    assert all(event["project"] == "demo-project" for event in events)
    assert all(event["run_id"] == "run-123" for event in events)


def test_keyboard_interrupt_is_reported_as_interrupted_at_session_finish(tmp_path):
    test_file = tmp_path / "test_slow.py"
    test_file.write_text(
        "import time\n\ndef test_slow():\n    time.sleep(5)\n",
        encoding="utf-8",
    )
    events_path = tmp_path / "btk-events.jsonl"
    env = _env_with_scripts_on_path()

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-p",
            "pytest_btk_events",
            "--btk-events",
            str(events_path),
            "-q",
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        time.sleep(0.5)
        os.kill(proc.pid, signal.SIGINT)
        proc.communicate(timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    events = _read_events(events_path)
    summary = next(event for event in events if event["event"] == "session_summary")
    assert summary["status"] == "interrupted"
