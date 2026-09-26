#!/usr/bin/env python3
"""Digest a JSONL log (events, test or agent transcripts, tool traces) instead of reading it whole.

Prints the record count (and unparsable lines), counts per kind (``--key``,
default: the first of ``event``/``type``/``kind`` present), the time range
(``time``/``timestamp``/``ts``/``created_at``), records that look like
errors (``level`` error/fatal/critical, a non-empty ``error``, or a
``status``/``conclusion``/``outcome`` of failure/failed/error), and the last
``--last`` records as one compact line each (``--width`` characters).
``--show N`` prints record N in full. Stdlib only; runs under ``python -S``::

    python -S scripts/jsonl_digest.py run.jsonl
    python -S scripts/jsonl_digest.py session.jsonl --key type --last 5 --show 12
    some-command 2>&1 | python -S scripts/jsonl_digest.py -

Exit codes: 0 = digested (even if it contains errors); 1 = no JSON records;
2 = unreadable input.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

KIND_KEYS = ("event", "type", "kind")
TIME_KEYS = ("time", "timestamp", "ts", "created_at")
FAILED = {"failure", "failed", "error", "errored"}


def _first(record: dict, keys: tuple[str, ...]) -> tuple[str | None, object]:
    for key in keys:
        if record.get(key) not in (None, ""):
            return key, record[key]
    return None, None


def is_error(record: object) -> bool:
    if not isinstance(record, dict):
        return False
    level = str(record.get("level", "")).lower()
    outcome = {str(record.get(key, "")).lower() for key in ("status", "conclusion", "outcome")}
    return level in {"error", "fatal", "critical"} or bool(record.get("error")) or bool(outcome & FAILED)


def compact(index: int, record: object, width: int, key: str | None) -> str:
    if not isinstance(record, dict):
        text = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        return f"[{index}] {text[:width]}"
    time_key, when = _first(record, TIME_KEYS)
    kind_key, kind = (key, record.get(key)) if key else _first(record, KIND_KEYS)
    rest = {k: v for k, v in record.items() if k not in {time_key, kind_key}}
    text = json.dumps(rest, ensure_ascii=False, separators=(",", ":"))
    if len(text) > width:
        text = text[: max(width - 1, 0)] + "…"
    prefix = " ".join(str(part) for part in (when, f"{kind}:" if kind is not None else None) if part is not None)
    return f"[{index}] {prefix} {text}".replace("  ", " ")


def digest(lines: list[str], *, source: str, key: str | None = None, last: int = 10, width: int = 160,
           show: tuple[int, ...] = ()) -> tuple[str, int]:
    records: list[object] = []
    bad = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    if not records:
        return f"{source}: no JSON records ({bad} unparsable line(s))", 1
    out = [f"{source}: {len(records)} record(s)" + (f" ({bad} unparsable line(s))" if bad else "")]
    dicts = [record for record in records if isinstance(record, dict)]
    times = sorted(str(value) for value in (_first(record, TIME_KEYS)[1] for record in dicts) if value is not None)
    if times:
        out.append(f"time: {times[0]} .. {times[-1]}")
    counts = Counter(str(record.get(key) if key else _first(record, KIND_KEYS)[1]) for record in dicts)
    if counts and set(counts) != {"None"}:
        label = key or "kind"
        out.append(f"by {label}: " + ", ".join(f"{name} {count}" for name, count in counts.most_common(15)))
    errors = [(index, record) for index, record in enumerate(records) if is_error(record)]
    out.append(f"errors: {len(errors)}")
    out += ["  " + compact(index, record, width, key) for index, record in errors[:10]]
    if len(errors) > 10:
        out.append(f"  [... {len(errors) - 10} more]")
    if last:
        out.append(f"last {min(last, len(records))}:")
        out += ["  " + compact(index, records[index], width, key)
                for index in range(max(len(records) - last, 0), len(records))]
    for index in show:
        if not 0 <= index < len(records):
            return f"{source}: no record {index} (0..{len(records) - 1})", 2
        out += [f"--- [{index}] ---", json.dumps(records[index], ensure_ascii=False, indent=2)]
    return "\n".join(out), 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Digest a JSONL log instead of reading it whole.")
    parser.add_argument("path", help="JSONL file, or - for stdin")
    parser.add_argument("--key", help="field to count by (default: first of event/type/kind)")
    parser.add_argument("--last", type=int, default=10, help="compact lines for the last N records (default 10)")
    parser.add_argument("--width", type=int, default=160, help="characters per compact line (default 160)")
    parser.add_argument("--show", default="", help="comma-separated record indexes to print in full")
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8", errors="replace")
        show = tuple(int(part) for part in args.show.split(",") if part.strip())
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    report, code = digest(text.splitlines(), source=args.path, key=args.key, last=args.last, width=args.width,
                          show=show)
    print(report, file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
