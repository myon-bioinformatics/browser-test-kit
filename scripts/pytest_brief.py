#!/usr/bin/env python3
"""Install only the missing test requirements, run pytest, print only what decides the result.

Replaces the re-typed one-liner
``pip install -q --break-system-packages pytest-cov | tail -1; python -m pytest -q ... --cov... | tail -N``:

* requirements (``--requirements``, default ``tests/requirements.txt`` if present) are
  checked with ``importlib.metadata`` in the target interpreter; only the missing names are installed, quietly, with
  ``--break-system-packages`` only when the interpreter is marked EXTERNALLY-MANAGED;
* pytest runs in this interpreter as ``python -m pytest -q -rfE -p no:cacheprovider [ARGS]``;
* printed: the installed names (if any), ``FAILED``/``ERROR`` lines, the coverage ``TOTAL``
  and ``Required test coverage`` lines, and pytest's final summary line. If pytest itself
  could not run (exit 2-5 with no summary), the last ``--tail`` lines instead.

Stdlib only; runs under ``python -S`` (the child pytest runs without ``-S``)::

    python -S scripts/pytest_brief.py -- --cov=xprobe --cov-branch --cov-report=term --cov-fail-under=90
    python -S scripts/pytest_brief.py --requirements tool/python/requirements.txt -- tool/python/tests

Exit code: pytest's own (0 passed, 1 failed, ...); 3 = installing a requirement failed.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import sysconfig

KEEP = re.compile(r"^(FAILED|ERROR) |^TOTAL\s|Required test coverage|^=+ .*\b(passed|failed|error|errors|skipped|deselected|no tests ran)\b.* =+$|^\d+ (passed|failed)")


def requirement_names(text: str) -> list[str]:
    """Distribution names from a requirements file (options, URLs and markers ignored)."""
    names = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", line)
        if match:
            names.append(match.group(0))
    return names


_PROBE = ("import sys\nfrom importlib import metadata\nfor n in sys.argv[1:]:\n"
          "    try: metadata.version(n)\n    except metadata.PackageNotFoundError: print(n)\n")


def missing(names: list[str], python: str = sys.executable) -> list[str]:
    """Names not installed for *python* (asked in a child, so ``-S`` here does not hide site-packages)."""
    if not names:
        return []
    done = subprocess.run([python, "-c", _PROBE, *names], capture_output=True, text=True, check=True)
    return done.stdout.split()


def externally_managed() -> bool:
    return os.path.exists(os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED"))


def brief(output: str, returncode: int, tail: int) -> list[str]:
    lines = [line.rstrip() for line in output.splitlines()]
    kept = [line for line in lines if KEEP.search(line)]
    if not any(re.search(r"\b(passed|failed|no tests ran|error)\b", line) for line in kept) and returncode not in (0, 1):
        return [line for line in lines if line][-tail:]
    return kept


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    pytest_args = argv[argv.index("--") + 1:] if "--" in argv else []
    own = argv[: argv.index("--")] if "--" in argv else argv
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--requirements", help="requirements file (default: tests/requirements.txt if present)")
    parser.add_argument("--tail", type=int, default=15, help="lines shown when pytest could not run")
    parser.add_argument("--python", default=sys.executable, help="interpreter for pip and pytest")
    args = parser.parse_args(own)
    req = args.requirements or ("tests/requirements.txt" if os.path.exists("tests/requirements.txt") else None)
    if req:
        try:
            with open(req, encoding="utf-8") as handle:
                need = missing(requirement_names(handle.read()), args.python)
        except OSError as exc:
            print(f"pytest_brief: {exc}", file=sys.stderr)
            return 3
        if need:
            pip = [args.python, "-m", "pip", "install", "-q", "--disable-pip-version-check"]
            if externally_managed():
                pip.append("--break-system-packages")
            done = subprocess.run(pip + need, capture_output=True, text=True)
            if done.returncode:
                print(f"pytest_brief: pip install {' '.join(need)} failed", file=sys.stderr)
                print("\n".join(done.stderr.strip().splitlines()[-args.tail:]), file=sys.stderr)
                return 3
            print("installed: " + ", ".join(need))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([args.python, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", *pytest_args],
                          capture_output=True, text=True, env=env)
    print("\n".join(brief(done.stdout + done.stderr, done.returncode, args.tail)))
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
