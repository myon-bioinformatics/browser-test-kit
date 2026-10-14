#!/usr/bin/env python3
"""Digest CI artifacts (zip, directory, JUnit XML, JSON receipts) instead of reading them whole.

Agents often receive a downloaded Actions artifact zip and then paste ad-hoc
``python - <<PY`` loops to find which test failed and why. This does that in
one bounded command, without extracting anything to disk:

* every JUnit ``*.xml`` member: one counts line (tests/failures/errors/skipped)
  and one ``FAIL`` line per failing testcase (message collapsed to ``--width``
  characters, at most ``--limit`` failures overall);
* every JSON member whose name matches ``--json`` (default ``route-audit.json``
  and ``*receipt*.json``): only the ``--keys`` fields (default ``schema``,
  ``stage``, ``failed_step``, ``last_capture``, ``error``), one line each;
* everything else is only counted by extension (``--list`` names the members).

Sources may be ``.zip`` files, directories, or single ``.xml``/``.json`` files.
Members above ``--max-bytes`` are skipped and named; XML containing a DOCTYPE or
ENTITY declaration is refused (no entity expansion). Stdlib only; runs under
``python -S``::

    python -S scripts/artifact_digest.py artifacts.zip
    python -S scripts/artifact_digest.py junit-dir/ results.xml --limit 5 --width 300
    python -S scripts/artifact_digest.py evidence.zip --json 'route-audit.json' --keys stage,failed_step

Exit codes: 0 = no failing testcase; 1 = at least one failing testcase;
2 = input error (missing source, not a zip/dir/file, unreadable member).
"""
from __future__ import annotations

import argparse
import collections
import fnmatch
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

DEFAULT_JSON = ("route-audit.json", "*receipt*.json")
DEFAULT_KEYS = ("schema", "stage", "failed_step", "last_capture", "error")


def _collapse(text, width):
    flat = re.sub(r"\s+", " ", text or "").strip()
    return flat if len(flat) <= width else flat[: max(width - 1, 0)] + "…"


def _members(source, max_bytes):
    """Yield (name, data_or_None, size) for a zip, directory or file; data None = skipped as too large."""
    if os.path.isdir(source):
        for root, _dirs, files in sorted(os.walk(source)):
            for fname in sorted(files):
                path = os.path.join(root, fname)
                size = os.path.getsize(path)
                name = os.path.relpath(path, source)
                if size > max_bytes:
                    yield name, None, size
                else:
                    with open(path, "rb") as handle:
                        yield name, handle.read(), size
    elif zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if info.file_size > max_bytes:
                    yield info.filename, None, info.file_size
                else:
                    yield info.filename, archive.read(info), info.file_size
    elif os.path.isfile(source):
        size = os.path.getsize(source)
        if size > max_bytes:
            yield os.path.basename(source), None, size
        else:
            with open(source, "rb") as handle:
                yield os.path.basename(source), handle.read(), size
    else:
        raise FileNotFoundError(source)


def _junit(name, data, width, failures):
    """Return (counts line, failing cases appended to *failures*). Raises ValueError for unsafe/invalid XML."""
    if re.search(rb"<!(DOCTYPE|ENTITY)", data, re.I):
        raise ValueError("DOCTYPE/ENTITY declarations are refused")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"invalid XML: {exc}") from exc
    totals = collections.Counter()
    for case in root.iter("testcase"):
        totals["tests"] += 1
        bad = [*case.findall("failure"), *case.findall("error")]
        if case.find("skipped") is not None:
            totals["skipped"] += 1
        for node in bad:
            kind = "error" if node.tag == "error" else "failure"
            totals[kind + "s"] += 1
            title = case.get("classname", "") + "::" + case.get("name", "?") if case.get("classname") else case.get("name", "?")
            message = node.get("message") or ""
            detail = _collapse(message + " | " + (node.text or "") if message else node.text, width)
            failures.append(f"FAIL {name} {title}: {detail}")
    return (f"junit {name}: tests={totals['tests']} failures={totals['failures']} "
            f"errors={totals['errors']} skipped={totals['skipped']}")


def _receipt(name, data, keys, width):
    try:
        doc = json.loads(data)
    except ValueError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        return f"json {name}: {type(doc).__name__}"
    picked = {k: doc[k] for k in keys if k in doc}
    return f"json {name}: " + _collapse(json.dumps(picked, ensure_ascii=False, sort_keys=False), width * 2)


def digest(sources, *, width=240, limit=20, json_patterns=DEFAULT_JSON, keys=DEFAULT_KEYS,
           max_bytes=50_000_000, list_members=False):
    """Return (lines, failing_count). Never raises for per-member problems; they become 'problem' lines."""
    lines, failures, other = [], [], collections.Counter()
    skipped = []
    listed = []
    for source in sources:
        for name, data, size in _members(source, max_bytes):
            label = name if len(sources) == 1 else f"{os.path.basename(source)}:{name}"
            if data is None:
                skipped.append(f"{label} ({size} bytes)")
                continue
            base = os.path.basename(name)
            try:
                if name.lower().endswith(".xml"):
                    lines.append(_junit(label, data, width, failures))
                elif name.lower().endswith(".json") and any(fnmatch.fnmatch(base, p) for p in json_patterns):
                    lines.append(_receipt(label, data, keys, width))
                else:
                    other[os.path.splitext(name)[1].lower() or "(none)"] += 1
                    listed.append(label)
            except ValueError as exc:
                lines.append(f"problem {label}: {exc}")
    shown = failures[:limit]
    lines.extend(shown)
    if len(failures) > len(shown):
        lines.append(f"... {len(failures) - len(shown)} more failing testcase(s); raise --limit")
    if other:
        lines.append("other: " + ", ".join(f"{ext}×{n}" for ext, n in sorted(other.items())))
    if list_members:
        lines.extend(f"  {label}" for label in listed)
    if skipped:
        lines.append("skipped (over --max-bytes): " + ", ".join(skipped))
    lines.append(f"failing testcases: {len(failures)}")
    return lines, len(failures)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sources", nargs="+", help="zip file, directory, or .xml/.json file")
    parser.add_argument("--width", type=int, default=240, help="characters kept per failure message (default 240)")
    parser.add_argument("--limit", type=int, default=20, help="failing testcases printed (default 20)")
    parser.add_argument("--json", action="append", dest="json_patterns", metavar="GLOB",
                        help="JSON member basename pattern to summarize (repeatable; default route-audit.json, *receipt*.json)")
    parser.add_argument("--keys", default=",".join(DEFAULT_KEYS), help="comma-separated JSON fields to keep")
    parser.add_argument("--max-bytes", type=int, default=50_000_000, help="skip members larger than this")
    parser.add_argument("--list", action="store_true", dest="list_members", help="also name the uncategorized members")
    args = parser.parse_args(argv)
    try:
        lines, failing = digest(
            args.sources, width=args.width, limit=args.limit,
            json_patterns=tuple(args.json_patterns or DEFAULT_JSON),
            keys=tuple(k for k in args.keys.split(",") if k),
            max_bytes=args.max_bytes, list_members=args.list_members)
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"artifact_digest: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
