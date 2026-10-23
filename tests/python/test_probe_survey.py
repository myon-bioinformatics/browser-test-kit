import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_survey as ps  # noqa: E402

spec = importlib.util.spec_from_file_location("twin_parity_under_test", ROOT / "scripts" / "twin_parity.py")
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)

PY = str(ROOT / "scripts" / "probe_survey.py") + ":summarize"


def snap(**over):
    base = {"origin": "https://x.test", "interactive": {"count": 12, "collection": "complete"},
            "shadow_roots": 0, "frames": 0}
    base.update(over)
    return base


def test_complete_count_with_nothing_skipped_is_complete():
    ev = ps.summarize(snap())
    assert ev["overall"] == "complete"
    assert ev["findings"][0]["claim"] == "interactive elements: 12"
    assert ev["not_examined"] == []


def test_partial_collection_stays_partial_with_limit():
    ev = ps.summarize(snap(interactive={"count": 7, "collection": "partial"}))
    assert ev["overall"] == "partial"
    assert ev["findings"][0]["coverage"] == "partial"
    assert ev["findings"][0]["limitations"] == ["collection partial"]


def test_uncounted_is_unknown_not_zero():
    ev = ps.summarize(snap(interactive={"count": None, "collection": "unknown"}))
    assert ev["findings"][0]["claim"] == "interactive elements: not counted"
    assert ev["findings"][0]["coverage"] == "unknown"


def test_shadow_roots_and_frames_are_listed_as_not_examined():
    ev = ps.summarize(snap(shadow_roots=2, frames=None))
    assert ev["not_examined"] == ["shadow roots (2): not entered", "child frames: not counted"]
    assert ev["overall"] == "partial"


def test_rejects_bad_counts_and_collection():
    for bad in ({"count": -1, "collection": "complete"}, {"count": True, "collection": "complete"},
                {"count": 1, "collection": "all"}, {"count": 1.5, "collection": "complete"}):
        with pytest.raises(ValueError):
            ps.summarize(snap(interactive=bad))
    with pytest.raises(ValueError):
        ps.summarize(snap(frames="3"))
    with pytest.raises(ValueError):
        ps.summarize(snap(origin="https://x.test/path"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_summarize_twins_agree():
    cases = [
        [snap()],
        [snap(interactive={"count": None, "collection": "unknown"})],
        [snap(interactive={"count": 3, "collection": "partial"}, shadow_roots=None, frames=4)],
        [snap(shadow_roots=-1)],
        [snap(interactive={"count": 1, "collection": "bogus"})],
        [snap(origin="ftp://x.test")],
        [[]],
    ]
    left = tp.python_calls(tp.load_python(PY), cases)
    right = tp.node_calls(ROOT / "scripts" / "probe_survey.mjs", "summarize", cases)
    assert tp.mismatches(left, right) == []
