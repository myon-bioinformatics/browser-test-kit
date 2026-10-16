#!/usr/bin/env python3
"""Work on several local clones at once: one line per repository.

The same change often lands in many repositories (a CI flag, a vendored file). These
subcommands replace the shell loops that were retyped for it::

    python -S scripts/fleet.py status ~/repo-a ~/repo-b            # branch, upstream, ahead/behind, dirty
    python -S scripts/fleet.py status ~/repo-* --fix-tracking      # set missing upstream + fetch refspec
    python -S scripts/fleet.py checks ~/repo-* --wait 900 --steps  # CI of each HEAD; failed steps + annotations
    python -S scripts/fleet.py pr ~/repo-* --title "ci: ..." --body-file body.md   # open (or find) the PR

``status`` flags clones whose branch has no upstream or no remote-tracking ref (the
state "unpushed / no remote branch" hooks complain about even after a push);
``--fix-tracking`` sets ``branch.<b>.remote/merge`` and adds the fetch refspec that
shallow clones lack, then fetches. ``checks`` reads the check runs of each clone's
HEAD (``--ignore`` names to disregard; default: copilot-pull-request-reviewer) and,
with ``--steps``, the failed steps and the failure/warning annotations of each failed run (job logs are
often not downloadable, annotations are). ``pr`` opens a PR for each clone's current
branch, or prints the existing one. GitHub access: ``gh api`` if available, else
``GITHUB_TOKEN``/``GH_TOKEN``. Stdlib only; runs under ``python -S``.

Exit codes: 0 = all fine; 1 = something needs attention (no upstream, dirty, failed
check, PR error); 2 = usage error; 3 = checks still pending when ``--wait`` ran out.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

NOISE = re.compile(r"ubuntu-latest label will migrate|^Process completed with exit code")


def git(repo: str, *args: str, check: bool = True) -> str:
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and done.returncode:
        raise RuntimeError(done.stderr.strip() or f"git {args[0]} failed")
    return done.stdout.strip()


def slug(repo: str) -> str:
    url = git(repo, "remote", "get-url", "origin")
    match = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not match:
        raise RuntimeError("origin is not a GitHub URL: " + url)
    return match.group(1)


def api(path: str, body: dict | None = None):
    if shutil.which("gh"):
        argv = ["gh", "api", path] + (["--method", "POST", "--input", "-"] if body is not None else [])
        done = subprocess.run(argv, input=json.dumps(body) if body is not None else None,
                              capture_output=True, text=True, timeout=120)
        if done.returncode:
            raise RuntimeError((done.stdout + done.stderr).strip()[:300])
        return json.loads(done.stdout or "null")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "fleet"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request("https://api.github.com/" + path.lstrip("/"), data=data, headers=headers,
                                     method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read() or b"null")


def status(repo: str, fix: bool = False) -> tuple[bool, str]:
    branch = git(repo, "branch", "--show-current") or "(detached)"
    dirty = [l for l in git(repo, "status", "--porcelain").splitlines() if l]
    untracked = sum(1 for l in dirty if l.startswith("??"))
    upstream = git(repo, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
    fixed = ""
    if not upstream and fix and branch != "(detached)":
        if git(repo, "ls-remote", "--heads", "origin", branch, check=False):
            git(repo, "config", f"branch.{branch}.remote", "origin")
            git(repo, "config", f"branch.{branch}.merge", f"refs/heads/{branch}")
            refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
            if refspec not in git(repo, "config", "--get-all", "remote.origin.fetch", check=False).splitlines():
                git(repo, "config", "--add", "remote.origin.fetch", refspec)
            git(repo, "fetch", "-q", "origin", branch)
            upstream = git(repo, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
            fixed = " (tracking fixed)"
    if upstream:
        behind, ahead = git(repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD").split()
        track = f"{upstream} +{ahead}/-{behind}"
        ok = ahead == "0"
    else:
        track, ok = "no upstream", False
    ok = ok and len(dirty) == untracked == 0
    head = git(repo, "rev-parse", "--short", "HEAD")
    return ok, (f"{'ok  ' if ok else 'todo'} {os.path.basename(os.path.abspath(repo))} {branch}@{head} {track}"
                f" changed={len(dirty) - untracked} untracked={untracked}{fixed}")


def check_report(repo: str, ignore: set[str], steps: bool, call=api) -> tuple[str, list[str]]:
    name, sha = slug(repo), git(repo, "rev-parse", "HEAD")
    runs = call(f"repos/{name}/commits/{sha}/check-runs?per_page=100")["check_runs"]
    runs = [r for r in runs if r["name"] not in ignore]
    pending = [r for r in runs if r["status"] != "completed"]
    failed = [r for r in runs if r["status"] == "completed" and r["conclusion"] not in ("success", "skipped", "neutral")]
    state = "pending" if pending else ("failed" if failed else ("none" if not runs else "green"))
    lines = [f"{state:7} {name}@{sha[:7]} runs={len(runs)} pending={len(pending)} failed={len(failed)}"]
    for run in failed:
        lines.append(f"   x {run['name']} ({run['conclusion']})")
        if steps:
            try:
                job = call(f"repos/{name}/actions/jobs/{run['id']}")
                for step in job.get("steps", []):
                    if step.get("conclusion") == "failure":
                        lines.append(f"     step: {step['name']}")
            except RuntimeError:
                pass
            for note in call(f"repos/{name}/check-runs/{run['id']}/annotations") or []:
                message = " ".join((note.get("message") or "").split())
                if note.get("annotation_level") != "notice" and not NOISE.search(message):
                    lines.append(f"     {note.get('annotation_level')}: {note.get('path')}:{note.get('start_line')} {message[:200]}")
    return state, lines


def open_pr(repo: str, title: str, body: str, base: str, draft: bool, call=api) -> tuple[bool, str]:
    name, branch = slug(repo), git(repo, "branch", "--show-current")
    owner = name.split("/")[0]
    existing = call(f"repos/{name}/pulls?state=open&head={owner}:{branch}")
    if existing:
        return True, f"exists {name} #{existing[0]['number']} {existing[0]['html_url']}"
    try:
        made = call(f"repos/{name}/pulls", {"title": title, "head": branch, "base": base, "body": body, "draft": draft})
    except RuntimeError as exc:
        return False, f"error  {name} {branch}: {exc}"
    return True, f"opened {name} #{made['number']} {made['html_url']}"


def main(argv=None, call=api, sleep=time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("status")
    p.add_argument("repos", nargs="+")
    p.add_argument("--fix-tracking", action="store_true")
    p = sub.add_parser("checks")
    p.add_argument("repos", nargs="+")
    p.add_argument("--wait", type=float, default=0)
    p.add_argument("--interval", type=float, default=30)
    p.add_argument("--steps", action="store_true")
    p.add_argument("--ignore", action="append", default=None)
    p = sub.add_parser("pr")
    p.add_argument("repos", nargs="+")
    p.add_argument("--title", required=True)
    p.add_argument("--body-file", required=True)
    p.add_argument("--base", default="main")
    p.add_argument("--draft", action="store_true")
    args = parser.parse_args(argv)
    code = 0
    try:
        if args.command == "status":
            for repo in args.repos:
                ok, line = status(repo, args.fix_tracking)
                print(line)
                code = code or (0 if ok else 1)
        elif args.command == "checks":
            ignore = set(args.ignore if args.ignore is not None else ["copilot-pull-request-reviewer"])
            deadline = time.monotonic() + args.wait
            while True:
                reports = [check_report(repo, ignore, args.steps, call) for repo in args.repos]
                if not any(s == "pending" for s, _ in reports) or time.monotonic() + args.interval > deadline:
                    break
                sleep(args.interval)
            for state, lines in reports:
                print("\n".join(lines))
            states = {s for s, _ in reports}
            code = 1 if "failed" in states else (3 if "pending" in states else 0)
        else:
            with open(args.body_file, encoding="utf-8") as handle:
                body = handle.read()
            for repo in args.repos:
                ok, line = open_pr(repo, args.title, body, args.base, args.draft, call)
                print(line)
                code = code or (0 if ok else 1)
    except (OSError, RuntimeError, KeyError) as exc:
        print(f"fleet: {exc}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
