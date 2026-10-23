"""Turn a passive page-survey snapshot into a btk-probe-evidence/1 envelope.

The snapshot holds counts a browser collector already gathered (no JavaScript is
evaluated by this module). Counts that were not collected stay unknown; shadow roots
and child frames are listed in not_examined because they are not entered here.
Stdlib only, Python 3.9+. Node twin: scripts/probe_survey.mjs.

Snapshot shape:
  {"origin": "https://x.test",
   "interactive": {"count": 12 | null, "collection": "complete" | "partial" | "unknown"},
   "shadow_roots": 0 | N | null,   # null = not counted
   "frames": 0 | N | null}         # null = not counted
Counts must be non-negative integers. Node cannot tell 1.0 from 1, so send integers.
"""
from __future__ import annotations

from probe_evidence import envelope, finding

COLLECTION = ("complete", "partial", "unknown")


def _count(name, value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer or null")
    return value


def summarize(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    interactive = snapshot.get("interactive")
    if not isinstance(interactive, dict):
        raise ValueError("interactive must be an object")
    count = _count("interactive.count", interactive.get("count"))
    collection = interactive.get("collection")
    if collection not in COLLECTION:
        raise ValueError(f"interactive.collection must be one of {COLLECTION}")
    shadow = _count("shadow_roots", snapshot.get("shadow_roots"))
    frames = _count("frames", snapshot.get("frames"))

    if count is None:
        item = finding("interactive elements: not counted", "dom:interactive", "unknown", ["count not collected"])
    else:
        limits = [] if collection == "complete" else [f"collection {collection}"]
        item = finding(f"interactive elements: {count}", "dom:interactive", collection, limits)

    skipped = []
    if shadow != 0:
        skipped.append("shadow roots: not counted" if shadow is None else f"shadow roots ({shadow}): not entered")
    if frames != 0:
        skipped.append("child frames: not counted" if frames is None else f"child frames ({frames}): not entered")
    return envelope(snapshot.get("origin"), [item], skipped)
