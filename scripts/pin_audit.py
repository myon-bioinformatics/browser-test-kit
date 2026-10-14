#!/usr/bin/env python3
"""Audit commit pins in a checkout: merged? final merge point? pinned files drifted? One line per pin.

Pins are collected from

* workflows (``.github/workflows/*.yml``): ``uses: OWNER/REPO[/path]@<40-hex>`` and an
  ``actions/checkout`` block's ``repository:`` + ``ref: <40-hex>``;
* JSON files (``--json GLOB``, default ``vendor.lock.json``, ``**/vendor.lock.json``,
  ``**/publication.json``): any object with ``repository`` and a 40-hex ``commit``; its
  ``source`` / ``source_path`` (when present) are the pinned files.

Each distinct (repository, commit) is checked with plain ``git`` against the public remote
(no API token): a bare temporary repository fetches the default branch with
``--filter=blob:none`` (full history, no file contents; a ``--depth=1`` fetch cannot
answer ancestry) and the pinned commit, then reports

* ``unmerged``  the commit is not reachable from the default branch;
* ``not-final`` it is merged, but only through a later merge commit on the default
  branch's first-parent line (a PR head was pinned, not the merge point) -> that commit;
* ``drift``     the pinned files differ between the pin and the default branch tip;
* ``ok``        otherwise (``+N`` = default-branch commits since the pin).

Stdlib + git only; runs under ``python -S``::

    python -S scripts/pin_audit.py .                       # whole checkout
    python -S scripts/pin_audit.py . --only myon-bioinformatics --json 'tools/**/lock*.json'

Exit codes: 0 = all ok; 1 = some pin is unmerged / not-final / drifted; 2 = input or git
error (e.g. the remote could not be reached).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile

HEX40 = re.compile(r"\b[0-9a-f]{40}\b")
USES = re.compile(r"uses:\s*['\"]?(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?P<path>/[^@\s'\"]*)?@(?P<sha>[0-9a-f]{40})\b")
CHECKOUT_REPO = re.compile(r"^\s+repository:\s*['\"]?(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)['\"]?\s*$")
CHECKOUT_REF = re.compile(r"^\s+ref:\s*['\"]?(?P<sha>[0-9a-f]{40})['\"]?\s*$")
DEFAULT_JSON = ("vendor.lock.json", "**/vendor.lock.json", "**/publication.json")


def repo_name(value: str) -> str:
    value = value.strip().removesuffix(".git")
    match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)$", value.replace("https://github.com/", ""))
    if not match:
        raise ValueError("not an OWNER/REPO: " + value)
    return match.group(1)


def workflow_pins(path: str, text: str) -> list[dict]:
    pins, lines = [], text.splitlines()
    for number, line in enumerate(lines, 1):
        match = USES.search(line)
        if match:
            pins.append({"repository": match["repo"], "commit": match["sha"], "file": path, "line": number,
                         "entry": (match["repo"] + (match["path"] or "")), "paths": []})
        repo = CHECKOUT_REPO.match(line)
        if repo:
            for later in range(number, min(number + 12, len(lines))):
                ref = CHECKOUT_REF.match(lines[later])
                if ref:
                    pins.append({"repository": repo["repo"], "commit": ref["sha"], "file": path,
                                 "line": later + 1, "entry": "checkout " + repo["repo"], "paths": []})
                    break
    return pins


def json_pins(path: str, document) -> list[dict]:
    pins = []

    def walk(node):
        if isinstance(node, dict):
            commit, repository = node.get("commit"), node.get("repository")
            if isinstance(repository, str) and isinstance(commit, str) and HEX40.fullmatch(commit):
                source = node.get("source") or node.get("source_path")
                pins.append({"repository": repo_name(repository), "commit": commit, "file": path, "line": None,
                             "entry": node.get("destination") or node.get("path") or source or "",
                             "paths": [source] if isinstance(source, str) else []})
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    return pins


def collect(root: str, json_globs=DEFAULT_JSON) -> list[dict]:
    pins = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in (".git", "node_modules", ".venv", "__pycache__"))
        for name in sorted(files):
            full = os.path.join(directory, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
                with open(full, encoding="utf-8") as handle:
                    pins += workflow_pins(rel, handle.read())
            elif name.endswith(".json") and any(fnmatch.fnmatch(rel, g) for g in json_globs):
                with open(full, encoding="utf-8") as handle:
                    try:
                        pins += json_pins(rel, json.load(handle))
                    except ValueError:
                        continue
    return pins


def git(*args: str, cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    done = subprocess.run(["git", "-c", "credential.helper=", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=300)
    if check and done.returncode:
        raise RuntimeError(done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "git " + args[0] + " failed")
    return done


def check_pins(repository: str, items: list[dict], remote: str) -> list[dict]:
    """Check every pin of one source repository in a single bare clone."""
    with tempfile.TemporaryDirectory(prefix="pin-audit-") as bare:
        git("init", "-q", "--bare", bare)
        head = git("ls-remote", "--symref", remote, "HEAD").stdout
        match = re.search(r"ref: refs/heads/(\S+)\s+HEAD", head)
        branch = match.group(1) if match else "main"
        git("fetch", "-q", "--no-tags", "--filter=blob:none", remote,
            f"refs/heads/{branch}:refs/heads/{branch}", cwd=bare)
        tip = git("rev-parse", branch, cwd=bare).stdout.strip()
        results = []
        for commit in sorted({p["commit"] for p in items}):
            pins = [p for p in items if p["commit"] == commit]
            row = {"repository": repository, "commit": commit, "branch": branch, "pins": pins}
            if git("cat-file", "-e", commit + "^{commit}", cwd=bare, check=False).returncode:
                fetched = git("fetch", "-q", "--no-tags", "--filter=blob:none", remote, commit, cwd=bare, check=False)
                if fetched.returncode:
                    results.append({**row, "state": "unmerged", "detail": "commit not found on the remote"})
                    continue
            if git("merge-base", "--is-ancestor", commit, branch, cwd=bare, check=False).returncode:
                results.append({**row, "state": "unmerged", "detail": f"not reachable from {branch}"})
                continue
            first_parent = git("rev-list", "--first-parent", branch, cwd=bare).stdout.split()
            since = git("rev-list", "--count", f"{commit}..{branch}", cwd=bare).stdout.strip()
            if commit not in first_parent:
                # Oldest first-parent commit that descends from the pin = where it was merged.
                descendants = set(git("rev-list", "--ancestry-path", f"{commit}..{branch}", cwd=bare).stdout.split())
                merge = next((c for c in reversed(first_parent) if c in descendants), tip)
                subject = git("log", "-1", "--format=%s", merge, cwd=bare).stdout.strip()
                results.append({**row, "state": "not-final", "final": merge,
                                "detail": f"merged via {merge[:7]} ({subject[:60]})"})
                continue
            paths = sorted({p for pin in pins for p in pin["paths"]})
            changed = []
            if paths:
                changed = git("diff", "--name-only", commit, branch, "--", *paths, cwd=bare).stdout.split()
            if changed:
                results.append({**row, "state": "drift", "detail": f"{len(changed)} pinned file(s) changed on {branch}: "
                                + ", ".join(changed[:3])})
            else:
                results.append({**row, "state": "ok", "detail": f"+{since} on {branch}"})
        return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("root", nargs="?", default=".", help="checkout to scan")
    parser.add_argument("--json", action="append", dest="json_globs", metavar="GLOB",
                        help="JSON files holding repository+commit pins (repeatable)")
    parser.add_argument("--only", action="append", metavar="OWNER", help="only pins whose repository owner is OWNER")
    parser.add_argument("--remote-base", default="https://github.com/", help="URL prefix for OWNER/REPO remotes")
    args = parser.parse_args(argv)
    try:
        pins = collect(args.root, tuple(args.json_globs or DEFAULT_JSON))
    except (OSError, ValueError) as exc:
        print(f"pin_audit: {exc}", file=sys.stderr)
        return 2
    if args.only:
        pins = [p for p in pins if p["repository"].split("/")[0] in args.only]
    if not pins:
        print("pins=0")
        return 0
    by_repo: dict[str, list[dict]] = {}
    for pin in pins:
        by_repo.setdefault(pin["repository"], []).append(pin)
    code, counts = 0, {}
    for repository in sorted(by_repo):
        try:
            results = check_pins(repository, by_repo[repository], args.remote_base + repository)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"error {repository}: {exc}")
            code = 2
            continue
        for row in results:
            counts[row["state"]] = counts.get(row["state"], 0) + 1
            where = sorted({p["file"] + (f":{p['line']}" if p["line"] else "") for p in row["pins"]})
            more = f" +{len(where) - 2} more" if len(where) > 2 else ""
            print(f"{row['state']} {repository}@{row['commit'][:7]} {row['detail']}  [{len(row['pins'])} pin(s): "
                  f"{', '.join(where[:2])}{more}]")
            if row["state"] != "ok" and code == 0:
                code = 1
    print("pins=" + str(len(pins)) + " " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return code


if __name__ == "__main__":
    sys.exit(main())
