#!/usr/bin/env python3
"""Thin, dependency-free launcher for terminal-browser.

Keeps terminal-browser optional: browser-test-kit can validate the integration
without requiring a graphical/kitty-capable terminal in every CI runner.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def emit(event: str, **fields: object) -> None:
    payload = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run terminal-browser with structured diagnostics")
    parser.add_argument("--check", action="store_true", help="only verify that terminal-browser is installed")
    parser.add_argument("--log", type=Path, help="write combined stdout/stderr to this file")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to terminal-browser")
    ns = parser.parse_args()

    executable = shutil.which("terminal-browser")
    if executable is None:
        emit("TERMINAL_BROWSER_UNAVAILABLE")
        return 127

    emit("terminal_browser_found", executable=executable)
    if ns.check:
        return 0

    argv = [executable, *ns.args]
    emit("terminal_browser_start", argv=argv)
    proc = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = proc.stdout or ""
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    if ns.log:
        ns.log.parent.mkdir(parents=True, exist_ok=True)
        ns.log.write_text(output, encoding="utf-8")
    emit("terminal_browser_exit", returncode=proc.returncode)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
