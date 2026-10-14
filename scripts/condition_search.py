#!/usr/bin/env python3
"""Find the simple conditions that explain a yes/no outcome in a list of records.

Typical use: many ``pointer-press/1`` / ``element-inventory/1`` records (one per press) where
some presses missed. Instead of eyeballing them, state the outcome once and let the tool rank
the conditions on the other fields that separate the misses from the hits::

    python -S scripts/condition_search.py records.json --target hit.self=false --id label

Records are a JSON array or JSONL (``-`` = stdin); nested objects are flattened to dotted
names (``box.height``). Predicates are generated from every other field: booleans and
strings with few values as ``field == value``, numbers as ``field <= t`` / ``field > t`` at
midpoints between observed values (at most ``--thresholds`` per field); a missing field never
matches. Searched: single predicates, ``A and B``, ``A or B``. Ranked by MCC (then fewer
predicates); formulas with the same set of matching records are listed once, simplest first.
For each formula the *counterexamples* are printed too: ``fp`` (predicted yes, was no) and
``fn`` (predicted no, was yes) record ids (``--id``, else row numbers).

This describes the sample it is given; it is not a validation on new records. Stdlib only;
runs under ``python -S``. Exit codes: 0 = a formula with MCC >= ``--min-mcc`` (default 0.5)
exists; 1 = none; 2 = input error.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys


def flatten(value, prefix=""):
    out = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            out.update(flatten(inner, f"{prefix}{key}."))
    elif isinstance(value, list):
        out[prefix[:-1]] = json.dumps(value, sort_keys=True)
    else:
        out[prefix[:-1]] = value
    return out


def load(text):
    text = text.strip()
    if not text:
        raise ValueError("no records")
    try:
        data = json.loads(text)
        rows = data if isinstance(data, list) else [data]
    except ValueError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError("records must be JSON objects")
    return [flatten(r) for r in rows]


def predicates(rows, skip, max_thresholds=12, max_values=8):
    """Return {expr: bitmask} over rows (bit i = row i)."""
    out = {}
    names = sorted({k for r in rows for k in r} - skip)
    for name in names:
        values = [r.get(name) for r in rows]
        seen = [v for v in values if v is not None]
        numeric = [v for v in seen if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if seen and len(numeric) == len(seen):
            distinct = sorted(set(numeric))
            mids = [(a + b) / 2 for a, b in zip(distinct, distinct[1:])]
            if len(mids) > max_thresholds:
                step = (len(mids) - 1) / (max_thresholds - 1)
                mids = [mids[round(i * step)] for i in range(max_thresholds)]
            for t in mids:
                t = round(t, 6)
                out[f"{name} <= {t:g}"] = sum(1 << i for i, v in enumerate(values) if v is not None and v <= t)
                out[f"{name} > {t:g}"] = sum(1 << i for i, v in enumerate(values) if v is not None and v > t)
        else:
            distinct = sorted({json.dumps(v) for v in seen})
            if 1 <= len(distinct) <= max_values:
                for d in distinct:
                    value = json.loads(d)
                    out[f"{name} == {d}"] = sum(1 << i for i, v in enumerate(values) if v is not None and v == value)
    return out


def popcount(n):
    return bin(n).count("1")


def mcc(tp, fp, fn, tn):
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / denom if denom else 0.0


def search(rows, target_name, target_value, skip=(), top=5, max_thresholds=12):
    n = len(rows)
    full = (1 << n) - 1
    target = sum(1 << i for i, r in enumerate(rows) if r.get(target_name) == target_value)
    preds = predicates(rows, {target_name, *skip}, max_thresholds)
    candidates = {}  # mask -> (complexity, expr)

    def offer(mask, complexity, expr):
        if mask in (0, full):
            return
        if mask not in candidates or (complexity, expr) < candidates[mask]:
            candidates[mask] = (complexity, expr)

    for expr, mask in preds.items():
        offer(mask, 1, expr)
    for (ea, ma), (eb, mb) in itertools.combinations(sorted(preds.items()), 2):
        offer(ma & mb, 2, f"[{ea}] and [{eb}]")
        offer(ma | mb, 2, f"[{ea}] or [{eb}]")
    scored = []
    for mask, (complexity, expr) in candidates.items():
        tp, fp = popcount(mask & target), popcount(mask & ~target & full)
        fn, tn = popcount(~mask & target & full), popcount(~mask & ~target & full)
        scored.append((-mcc(tp, fp, fn, tn), complexity, expr, mask, tp, fp, fn))
    scored.sort(key=lambda s: s[:3])
    results = []
    for neg_mcc, _c, expr, mask, tp, fp, fn in scored[:top]:
        results.append({"mcc": round(-neg_mcc, 4), "tp": tp, "fp": fp, "fn": fn, "expr": expr,
                        "fp_rows": [i for i in range(n) if mask >> i & 1 and not target >> i & 1],
                        "fn_rows": [i for i in range(n) if not mask >> i & 1 and target >> i & 1]})
    return {"rows": n, "target_rows": popcount(target), "predicates": len(preds), "results": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", help="JSON array / JSONL file, or - for stdin")
    parser.add_argument("--target", required=True, metavar="FIELD=VALUE",
                        help="the outcome to explain; VALUE is a JSON literal (false, 3, \"x\")")
    parser.add_argument("--id", help="field naming each record in the counterexample lists (default: row number)")
    parser.add_argument("--skip", action="append", default=[], metavar="FIELD", help="field not to use as a condition (repeatable)")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--thresholds", type=int, default=12, help="thresholds tried per numeric field")
    parser.add_argument("--min-mcc", type=float, default=0.5)
    parser.add_argument("--max-ids", type=int, default=8, help="counterexample ids printed per formula")
    args = parser.parse_args(argv)
    try:
        name, _, literal = args.target.partition("=")
        value = json.loads(literal)
        text = sys.stdin.read() if args.source == "-" else open(args.source, encoding="utf-8").read()
        rows = load(text)
    except (OSError, ValueError) as exc:
        print(f"condition_search: {exc}", file=sys.stderr)
        return 2
    if name not in {k for r in rows for k in r}:
        print(f"condition_search: no record has field {name!r}", file=sys.stderr)
        return 2
    report = search(rows, name, value, [args.id] if args.id else [], args.top, args.thresholds)
    print(f"rows={report['rows']} target_rows={report['target_rows']} predicates={report['predicates']}")

    def ids(indexes):
        labels = [str(rows[i].get(args.id, i)) if args.id else str(i) for i in indexes]
        more = f" +{len(labels) - args.max_ids}" if len(labels) > args.max_ids else ""
        return ",".join(labels[: args.max_ids]) + more

    for rank, r in enumerate(report["results"], 1):
        print(f"{rank}. mcc={r['mcc']} tp={r['tp']} fp={r['fp']} fn={r['fn']}  {r['expr']}")
        if r["fp"] or r["fn"]:
            print(f"   fp: {ids(r['fp_rows']) or '-'}   fn: {ids(r['fn_rows']) or '-'}")
    return 0 if report["results"] and report["results"][0]["mcc"] >= args.min_mcc else 1


if __name__ == "__main__":
    sys.exit(main())
