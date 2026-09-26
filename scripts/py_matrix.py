#!/usr/bin/env python3
"""Run pytest under several Python versions and print one line per version.

Each run is ``uv run --no-project --python VERSION --with pytest python -m
pytest -q -p no:cacheprovider [ARGS]``, so uv fetches and caches the
interpreters and the project environment is untouched.
``PYTHONDONTWRITEBYTECODE=1`` keeps ``__pycache__`` out of the work tree. A
passing version prints only pytest's summary line; a failing one also
prints its last ``--tail`` lines.

Stdlib only; runs under ``python -S``::

    python -S scripts/py_matrix.py 3.9 3.13 -- tests/python/test_gh_ops.py
    python -S scripts/py_matrix.py 3.9 3.12 3.13 --with 'pytest>=8,<10' --timeout 300

Exit codes: 0 = every version passed; 1 = a version failed or timed out;
2 = uv not found or usage error.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Callable


def command(version: str, packages: list[str], pytest_args: list[str]) -> list[str]:
    argv = ["uv", "run", "--no-project", "--quiet", "--python", version]
    for package in packages:
        argv += ["--with", package]
    return argv + ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", *pytest_args]


def run_version(version: str, packages: list[str], pytest_args: list[str], *, timeout: float, tail: int,
                run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> tuple[bool, list[str]]:
    """Return ``(passed, lines to print)`` for one interpreter."""
    try:
        done = run(command(version, packages, pytest_args), capture_output=True, text=True, timeout=timeout,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    except subprocess.TimeoutExpired:
        return False, [f"py{version}: TIMEOUT after {timeout:g}s"]
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    summary = lines[-1] if lines else "(no output)"
    if done.returncode == 0:
        return True, [f"py{version}: {summary}"]
    return False, [f"py{version}: FAILED (exit {done.returncode}): {summary}"] + [f"  {line}" for line in lines[-tail:]]


def main(argv: list[str] | None = None, *, which: Callable[[str], str | None] = shutil.which,
         run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    pytest_args: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, pytest_args = argv[:split], argv[split + 1:]
    parser = argparse.ArgumentParser(description="Run pytest under several Python versions via uv.",
                                     usage="%(prog)s VERSION [VERSION ...] [options] [-- PYTEST_ARGS]")
    parser.add_argument("versions", nargs="+", help="Python versions, e.g. 3.9 3.13")
    parser.add_argument("--with", dest="packages", action="append", help="package for uv --with (default: pytest)")
    parser.add_argument("--timeout", type=float, default=300.0, help="seconds per version (default: 300)")
    parser.add_argument("--tail", type=int, default=15, help="output lines shown for a failing version")
    args = parser.parse_args(argv)
    if which("uv") is None:
        print("error: uv not found; install uv or run pytest under each interpreter directly", file=sys.stderr)
        return 2
    all_passed = True
    for version in args.versions:
        passed, lines = run_version(version, args.packages or ["pytest"], pytest_args, timeout=args.timeout,
                                    tail=args.tail, run=run)
        all_passed &= passed
        print("\n".join(lines), flush=True)
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
