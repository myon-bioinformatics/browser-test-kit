#!/usr/bin/env python3
"""Thin, dependency-free launcher for terminal-browser.

Keeps terminal-browser optional: browser-test-kit can validate the integration
without requiring a graphical/kitty-capable terminal in every CI runner.
"""
from __future__ import annotations

import argparse
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import btk_events


def emit(event: str, **fields: object) -> None:
    # schema identifies this as a btk-event/1 payload (docs/evidence-events.md);
    # every existing field keeps its name and meaning, so older consumers that
    # only look at source/time/event/returncode/signal/interrupted are unaffected.
    btk_events.emit(sys.stderr, source="terminal-browser", event=event, **fields)


def _normalized_returncode(returncode: int) -> tuple[int, int | None]:
    if returncode >= 0:
        return returncode, None
    signal_number = -returncode
    return 128 + signal_number, signal_number


def main() -> int:
    parser = argparse.ArgumentParser(description="Run terminal-browser with structured diagnostics")
    parser.add_argument("--check", action="store_true", help="only verify that terminal-browser is installed")
    parser.add_argument(
        "--log",
        type=Path,
        help="capture combined child stdout/stderr to a file; intended for non-interactive commands",
    )
    parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to terminal-browser")
    ns = parser.parse_args()

    if ns.check and (ns.log is not None or ns.args):
        parser.error("--check cannot be combined with --log or terminal-browser arguments")

    executable = shutil.which("terminal-browser")
    if executable is None:
        emit("TERMINAL_BROWSER_UNAVAILABLE")
        return 127

    emit("terminal_browser_found", executable=executable)
    if ns.check:
        return 0

    child_args = ns.args[1:] if ns.args[:1] == ["--"] else ns.args
    argv = [executable, *child_args]
    emit("terminal_browser_start", argv=argv)

    interrupted = False

    try:
        if ns.log is None:
            # Preserve the child's terminal. Interactive commands such as `open`
            # must see the real stdin/stdout/stderr instead of pipes.
            #
            # A bare Ctrl-C raises KeyboardInterrupt on Python's default SIGINT
            # handler while subprocess.run() is waiting; run() reacts to that
            # by SIGKILLing the child immediately (see the bare "except:" in
            # cpython's subprocess.run), which can leave an interactive TUI's
            # terminal state (raw mode, alternate screen, ...) broken. The
            # child shares our foreground process group, so it receives the
            # same SIGINT directly. Install a handler that only records the
            # interrupt instead of raising, so run() keeps waiting and the
            # child gets to decide how -- and how quickly -- it cleans up and
            # exits.
            previous_handler = signal.getsignal(signal.SIGINT)

            def _record_interrupt(signum: int, frame: object) -> None:
                nonlocal interrupted
                interrupted = True

            signal.signal(signal.SIGINT, _record_interrupt)
            try:
                proc = subprocess.run(argv)
            finally:
                signal.signal(signal.SIGINT, previous_handler)
        else:
            proc = subprocess.run(
                argv,
                text=True,
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output = proc.stdout or ""
            if output:
                print(output, end="" if output.endswith("\n") else "\n")
            ns.log.parent.mkdir(parents=True, exist_ok=True)
            ns.log.write_text(output, encoding="utf-8", errors="replace")
    except KeyboardInterrupt:
        # Only reachable for --log mode (piped stdio): the handler above keeps
        # the default inherited-stdio path from ever raising here.
        exit_fields: dict[str, object] = {"returncode": 130, "interrupted": True}
        exit_fields["status"] = btk_events.classify_terminal_browser({"event": "terminal_browser_exit", **exit_fields})
        emit("terminal_browser_exit", **exit_fields)
        return 130

    returncode, signal_number = _normalized_returncode(proc.returncode)
    exit_fields = {"returncode": returncode}
    if interrupted:
        exit_fields["interrupted"] = True
    if signal_number is not None:
        exit_fields["signal"] = signal_number
    exit_fields["status"] = btk_events.classify_terminal_browser({"event": "terminal_browser_exit", **exit_fields})
    emit("terminal_browser_exit", **exit_fields)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
