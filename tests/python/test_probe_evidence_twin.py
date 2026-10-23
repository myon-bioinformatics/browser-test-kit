"""Python probe_evidence and its Node twin agree on accept/reject and on every accepted value."""
import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / "scripts" / "probe_evidence.py") + ":envelope"
NODE_TWIN = "scripts/probe_evidence.mjs"

spec = importlib.util.spec_from_file_location("twin_parity_under_test", ROOT / "scripts" / "twin_parity.py")
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

ok_finding = {"claim": "login form present", "source": "dom:form#login", "coverage": "complete", "limitations": []}
partial_finding = {"claim": "widgets", "source": "dom:all", "coverage": "partial", "limitations": ["iframes not entered"]}

CASES = [
    ["https://x.test", [ok_finding]],
    ["https://x.test:8443/", [ok_finding, partial_finding]],
    ["http://127.0.0.1:3000", []],
    ["https://x.test", [ok_finding], ["shadow roots"]],
    ["ftp://x.test", [ok_finding]],
    ["https://x.test/path", [ok_finding]],
    ["https://x.test?q=1", [ok_finding]],
    ["https://x.test#frag", [ok_finding]],
    ["https://u:p@x.test", [ok_finding]],
    ["x.test", [ok_finding]],
    ["", [ok_finding]],
    ["https://x.test", [{"claim": "c", "source": "s", "coverage": "maybe", "limitations": []}]],
    ["https://x.test", [{"claim": " ", "source": "s", "coverage": "complete", "limitations": []}]],
    ["https://x.test", [{"claim": "c", "source": "s", "coverage": "complete", "limitations": ["  "]}]],
    ["https://x.test", [{"claim": "c", "source": "s"}]],
    ["https://x.test", "not a list"],
    ["https://x.test", [ok_finding], "not a list"],
    ["https://[bad", [ok_finding]],
]


def test_envelope_twins_agree_on_every_case():
    left = tp.python_calls(tp.load_python(PY), CASES)
    right = tp.node_calls(ROOT / NODE_TWIN, "envelope", CASES)
    assert tp.mismatches(left, right) == []


def test_envelope_twin_serializes_identically():
    case = [["https://x.test:8443/", [ok_finding, partial_finding], ["shadow roots"]]]
    py_env = tp.python_calls(tp.load_python(PY), case)[0]["value"]
    node_json = tp.node_calls(ROOT / NODE_TWIN, "to_json", [[py_env]])[0]["value"]
    py_json = tp.python_calls(tp.load_python(str(ROOT / "scripts" / "probe_evidence.py") + ":to_json"), [[py_env]])[0]["value"]
    assert node_json == py_json
