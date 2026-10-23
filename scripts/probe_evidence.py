"""Evidence envelope for passive page probes (btk-probe-evidence/1).

A finding is one claim about one page, with its source and how much of the page
was actually examined. A missing or truncated observation is never reported as
equivalent: coverage says what was examined, and anything skipped goes in
not_examined. Stdlib only, Python 3.9+. Node twin: scripts/probe_evidence.mjs.

Exit codes: 0 OK, 2 input error (CLI reads one JSON object on stdin).
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlsplit

SCHEMA = "btk-probe-evidence/1"
COVERAGE = ("complete", "partial", "unknown")


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _texts(name, values):
    values = list(values)
    for value in values:
        _text(name, value)
    return values


def origin(value):
    """Return value if it is a bare http(s) origin (scheme, host, optional port)."""
    _text("origin", value)
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("origin must be an http(s) URL with a host")
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError("origin must not carry a path, query, fragment or credentials")
    return value.rstrip("/")


def finding(claim, source, coverage, limitations=()):
    """One claim with its source, coverage ('complete' | 'partial' | 'unknown') and limits."""
    if coverage not in COVERAGE:
        raise ValueError(f"coverage must be one of {COVERAGE}")
    return {
        "claim": _text("claim", claim),
        "source": _text("source", source),
        "coverage": coverage,
        "limitations": _texts("limitation", limitations),
    }


def envelope(target_origin, findings, not_examined=()):
    """Assemble the evidence. overall is 'complete' only when every finding is complete
    and nothing was skipped; no findings means 'unknown'; anything else is 'partial'."""
    items = [finding(f["claim"], f["source"], f["coverage"], f["limitations"]) for f in findings]
    skipped = _texts("not_examined", not_examined)
    if not items:
        overall = "unknown"
    elif all(item["coverage"] == "complete" for item in items) and not skipped:
        overall = "complete"
    else:
        overall = "partial"
    return {
        "schema": SCHEMA,
        "target": {"origin": origin(target_origin)},
        "overall": overall,
        "findings": items,
        "not_examined": skipped,
    }


def to_json(evidence):
    """Deterministic JSON text (sorted keys, no extra whitespace)."""
    return json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("stdin must be one JSON object")
        result = envelope(
            data.get("origin"),
            [finding(**item) for item in data.get("findings", [])],
            data.get("not_examined", []),
        )
    except (ValueError, TypeError, KeyError) as exc:
        print(f"probe_evidence: {exc}", file=sys.stderr)
        return 2
    print(to_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
