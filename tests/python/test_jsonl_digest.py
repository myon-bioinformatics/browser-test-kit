from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jsonl_digest.py"
spec = importlib.util.spec_from_file_location("jsonl_digest", SCRIPT)
jsonl_digest = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(jsonl_digest)

EVENTS = [
    {"source": "terminal-browser", "time": "2026-09-26T01:00:00Z", "event": "terminal_browser_found"},
    {"source": "terminal-browser", "time": "2026-09-26T01:00:01Z", "event": "terminal_browser_start", "argv": ["x"]},
    {"time": "2026-09-26T01:00:05Z", "event": "tool_call", "status": "failed", "detail": "y" * 300},
    {"time": "2026-09-26T01:00:09Z", "event": "terminal_browser_exit", "returncode": 130, "interrupted": True},
]


def lines(records, extra=()):
    return [json.dumps(record) for record in records] + list(extra)


def test_digest_counts_time_range_errors_and_last_lines() -> None:
    report, code = jsonl_digest.digest(lines(EVENTS, ["not json", ""]), source="run.jsonl", last=2, width=40)
    assert code == 0
    out = report.splitlines()
    assert out[0] == "run.jsonl: 4 record(s) (1 unparsable line(s))"
    assert out[1] == "time: 2026-09-26T01:00:00Z .. 2026-09-26T01:00:09Z"
    assert out[2].startswith("by kind: terminal_browser_found 1, terminal_browser_start 1, tool_call 1")
    assert out[3] == "errors: 1"
    assert out[4].startswith('  [2] 2026-09-26T01:00:05Z tool_call: {"status":"failed","detail":"yyy')
    assert len(out[4]) <= 2 + len("[2] 2026-09-26T01:00:05Z tool_call: ") + 40
    assert out[5] == "last 2:"
    assert out[7] == '  [3] 2026-09-26T01:00:09Z terminal_browser_exit: {"returncode":130,"interrupted":true}'


def test_key_option_show_and_errors_by_level() -> None:
    records = [{"type": "user", "level": "info"}, {"type": "assistant", "level": "error", "message": "boom"}]
    report, code = jsonl_digest.digest(lines(records), source="s.jsonl", key="type", last=0, show=(1,))
    assert code == 0
    assert "by type: user 1, assistant 1" in report
    assert "errors: 1\n  [1] assistant: " in report
    assert report.endswith('--- [1] ---\n{\n  "type": "assistant",\n  "level": "error",\n  "message": "boom"\n}')


def test_no_records_is_exit_1_and_bad_show_is_exit_2() -> None:
    assert jsonl_digest.digest(["", "nope"], source="x")[1] == 1
    assert jsonl_digest.digest(lines(EVENTS), source="x", show=(9,))[1] == 2


def test_cli_reads_stdin_without_site_packages() -> None:
    done = subprocess.run([sys.executable, "-S", str(SCRIPT), "-", "--last", "1"], input="\n".join(lines(EVENTS)),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("-: 4 record(s)\n")
    assert done.stdout.rstrip().endswith("terminal_browser_exit: {\"returncode\":130,\"interrupted\":true}")
