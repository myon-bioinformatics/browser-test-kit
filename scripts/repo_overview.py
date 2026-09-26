#!/usr/bin/env python3
"""One-command repository orientation: key files, then the file list, bounded.

Prints the README, agent notes (CLAUDE.md / AGENTS.md), and build/test
configuration (package.json, pyproject.toml, requirements*.txt,
playwright.config.*, Dockerfile, compose files, GitHub workflows, ...) under
``=== path ===`` headers, then every file path. Each file is capped at
``--max-lines`` and the list at ``--max-files``, so the output stays usable in
a log or an agent context (``UNBOUNDED_TOOL_OUTPUT``). The file list comes
from ``git ls-files`` (tracked plus untracked-but-not-ignored) when ROOT is a
git work tree, else from a directory walk; dependency, cache, and result
directories are skipped either way.

Stdlib only; runs under ``python -S``::

    python -S scripts/repo_overview.py
    python -S scripts/repo_overview.py ../other-repo --max-lines 40 --no-files
    python -S scripts/repo_overview.py --include 'docs/*.md'

Exit codes: 0 = OK, 2 = ROOT is not a directory.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

KEY_FILES = (
    "README*", "CLAUDE.md", "AGENTS.md", "CONTRIBUTING*",
    "package.json", "pyproject.toml", "setup.cfg", "setup.py", "requirements*.txt", "Pipfile", "tox.ini",
    "noxfile.py", "Makefile", "Dockerfile*", "docker-compose*.y*ml", "compose*.y*ml",
    "playwright.config.*", "tsconfig.json", "vite.config.*", "go.mod", "Cargo.toml",
    ".tool-versions", ".python-version", ".nvmrc", ".github/workflows/*.y*ml",
)
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache",
                       ".pytest_cache", ".ruff_cache", "dist", "build", "test-results", "playwright-report"})


def _skipped(relative: str) -> bool:
    return any(part in SKIP_DIRS for part in Path(relative).parts[:-1])


def list_files(root: Path) -> list[str]:
    """Repository files relative to ``root``, sorted, without dependency/cache/result directories."""
    try:
        done = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                              capture_output=True, check=True)
        files = {path for path in done.stdout.decode("utf-8", "replace").split("\0") if path}
    except (OSError, subprocess.CalledProcessError):
        files = set()
        for directory, subdirs, names in os.walk(root):
            subdirs[:] = [name for name in subdirs if name not in SKIP_DIRS]
            files.update(Path(directory, name).relative_to(root).as_posix() for name in names)
    return sorted(path for path in files if not _skipped(path) and (root / path).is_file())


def key_files(root: Path, patterns: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            relative = path.relative_to(root).as_posix()
            if path.is_file() and relative not in found and not _skipped(relative):
                found.append(relative)
    return found


def render_file(root: Path, relative: str, max_lines: int) -> str:
    data = (root / relative).read_bytes()
    if b"\0" in data[:4096]:
        return f"=== {relative} (binary, {len(data)} bytes; not shown) ==="
    lines = data.decode("utf-8", "replace").splitlines()
    head = f"=== {relative} ({len(lines)} line{'' if len(lines) == 1 else 's'}) ==="
    body = lines[:max_lines]
    if len(lines) > max_lines:
        body.append(f"[... truncated: showing {max_lines} of {len(lines)} lines (--max-lines)]")
    return "\n".join([head, *body])


def overview(root: Path, *, max_lines: int = 120, max_files: int = 400, files: bool = True,
             include: tuple[str, ...] = ()) -> str:
    sections = [render_file(root, relative, max_lines) for relative in key_files(root, KEY_FILES + include)]
    if files:
        paths = list_files(root)
        shown = paths[:max_files]
        if len(paths) > max_files:
            shown.append(f"[... {len(paths) - max_files} more files (--max-files)]")
        sections.append("\n".join([f"=== files ({len(paths)}) ===", *shown]))
    return "\n\n".join(sections)


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a repository's key files and file list, bounded.")
    parser.add_argument("root", nargs="?", default=".", help="repository directory (default: .)")
    parser.add_argument("--max-lines", type=_positive, default=120, help="lines shown per file (default: 120)")
    parser.add_argument("--max-files", type=_positive, default=400, help="paths listed (default: 400)")
    parser.add_argument("--no-files", action="store_true", help="skip the file list")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="extra key-file glob relative to ROOT (repeatable)")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: not a directory: {args.root}", file=sys.stderr)
        return 2
    print(overview(root.resolve(), max_lines=args.max_lines, max_files=args.max_files, files=not args.no_files,
                   include=tuple(args.include)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
