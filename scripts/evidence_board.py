#!/usr/bin/env python3
"""Aggregate one or more btk-event/1 JSONL streams into an evidence board.

Reads every event from the given files (see ``docs/evidence-events.md`` for
the contract) and reports:

- counts per ``status``;
- counts per ``source``/``project`` (grouped as ``source`` alone, or
  ``source/project`` when the event carries a ``project``);
- the first failure recorded for each ``stage``
  (``FAILURE_LAYER_FLATTENING`` in ``docs/anti-patterns.md``);
- ``interrupted``/``unavailable`` counts, called out separately -- neither is
  ever folded into "passed".

Output is a Markdown table by default, or ``--json``. ``--step-summary``
also appends the Markdown table to ``$GITHUB_STEP_SUMMARY`` when that
environment variable is set (as in a GitHub Actions step), regardless of
``--json``.

Exit codes: 0 = nothing failed/errored/interrupted/blocked/unavailable (or
every such status is covered by ``--allow``); 1 = otherwise; 2 = bad input
(missing file, unreadable file, unknown ``--allow`` status).

Stdlib only; runs under ``python -S``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Union

import btk_events

# Statuses that block a green board unless explicitly --allow-ed.
BLOCKING_STATUSES = btk_events.NEVER_PASSING_STATUSES
# Of those, the two the review specifically asked never be silently counted
# as passed, and that get their own callout line/fields.
CALLOUT_STATUSES = ("interrupted", "unavailable")
# Statuses that pin down which stage a failure happened at.
FAILING_STATUSES = frozenset({"failed", "error"})


def aggregate(paths: list, allow: set) -> dict:
    counts_by_status: dict = {}
    counts_by_group: dict = {}
    first_failure_by_stage: dict = {}
    malformed_lines = 0
    total_events = 0

    for path in paths:
        result = btk_events.read(path)
        malformed_lines += result.malformed
        for record in result.events:
            total_events += 1
            source = record.get("source") or "(unknown source)"
            project = record.get("project")
            group = f"{source}/{project}" if project else source
            counts_by_group[group] = counts_by_group.get(group, 0) + 1

            status = record.get("status")
            if status is None:
                continue
            counts_by_status[status] = counts_by_status.get(status, 0) + 1

            stage = record.get("stage")
            if stage and status in FAILING_STATUSES and stage not in first_failure_by_stage:
                first_failure_by_stage[stage] = {
                    "status": status,
                    "source": source,
                    "project": project,
                    "test_id": record.get("test_id"),
                    "time": record.get("time"),
                    "message": record.get("message"),
                }

    present_blocking = {status for status in BLOCKING_STATUSES if counts_by_status.get(status, 0) > 0}
    blocking = sorted(present_blocking - allow)

    return {
        "counts_by_status": counts_by_status,
        "counts_by_group": counts_by_group,
        "first_failure_by_stage": first_failure_by_stage,
        "interrupted": counts_by_status.get("interrupted", 0),
        "unavailable": counts_by_status.get("unavailable", 0),
        "malformed_lines": malformed_lines,
        "total_events": total_events,
        "allowed": sorted(allow),
        "blocking_statuses": blocking,
        "exit_code": 1 if blocking else 0,
    }


def render_markdown(stats: dict, paths: list) -> str:
    lines = ["# Evidence board", ""]
    lines.append("Files: " + ", ".join(f"`{path}`" for path in paths))
    lines.append("")

    lines.append("| Status | Count |")
    lines.append("| --- | --- |")
    for status in sorted(btk_events.STATUSES):
        count = stats["counts_by_status"].get(status, 0)
        if count:
            lines.append(f"| {status} | {count} |")
    if not stats["counts_by_status"]:
        lines.append("| _(none)_ | 0 |")
    lines.append("")

    lines.append("| Source/project | Events |")
    lines.append("| --- | --- |")
    for group, count in sorted(stats["counts_by_group"].items()):
        lines.append(f"| {group} | {count} |")
    if not stats["counts_by_group"]:
        lines.append("| _(none)_ | 0 |")
    lines.append("")

    if stats["first_failure_by_stage"]:
        lines.append("| Stage | First failure |")
        lines.append("| --- | --- |")
        for stage, info in sorted(stats["first_failure_by_stage"].items()):
            label = info.get("test_id") or info.get("source")
            message = f" -- {info['message']}" if info.get("message") else ""
            lines.append(f"| {stage} | `{label}` ({info['status']}){message} |")
        lines.append("")

    notes = []
    for status in CALLOUT_STATUSES:
        count = stats[status]
        if count:
            notes.append(f"{count} `{status}` event(s) (never counted as passed)")
    if stats["malformed_lines"]:
        notes.append(f"{stats['malformed_lines']} malformed JSONL line(s) skipped")
    if stats["allowed"]:
        notes.append(f"allowed (excluded from failing the board): {', '.join(stats['allowed'])}")
    if notes:
        lines.append("Notes: " + "; ".join(notes))
        lines.append("")

    lines.append(f"**Result: {'FAIL' if stats['exit_code'] else 'PASS'}**")
    if stats["blocking_statuses"]:
        lines.append(f"Blocking status(es): {', '.join(stats['blocking_statuses'])}")
    return "\n".join(lines)


def main(argv: Union[list, None] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evidence_board",
        description="Aggregate one or more btk-event/1 JSONL files into a Markdown or JSON evidence board.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="btk-event/1 JSONL file(s) to aggregate")
    parser.add_argument("--json", action="store_true", help="print the aggregate as JSON instead of a Markdown table")
    parser.add_argument(
        "--step-summary",
        action="store_true",
        help="also append the Markdown table to $GITHUB_STEP_SUMMARY, when that variable is set",
    )
    parser.add_argument(
        "--allow",
        default="",
        metavar="STATUS[,STATUS...]",
        help=(
            "comma-separated statuses that must not fail the board even though they are "
            "not 'passed' (for example: unavailable, when terminal-browser is missing on CI)"
        ),
    )
    args = parser.parse_args(argv)

    allow = {name.strip() for name in args.allow.split(",") if name.strip()}
    unknown = allow - btk_events.STATUSES
    if unknown:
        parser.error(f"--allow: unknown status(es): {', '.join(sorted(unknown))}")

    for path in args.paths:
        if not path.is_file():
            print(f"error: {path}: no such file", file=sys.stderr)
            return 2

    try:
        stats = aggregate(args.paths, allow)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    markdown = render_markdown(stats, args.paths)
    if args.json:
        print(json.dumps(stats, indent=2, sort_keys=True))
    else:
        print(markdown)

    if args.step_summary:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(markdown + "\n")

    return stats["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
