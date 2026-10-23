import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_evidence as pe  # noqa: E402


class ProbeEvidence(unittest.TestCase):
    def test_complete_only_when_everything_was_examined(self):
        f = pe.finding("login form present", "dom:form#login", "complete")
        self.assertEqual(pe.envelope("https://example.test", [f])["overall"], "complete")

    def test_partial_finding_makes_overall_partial(self):
        f = pe.finding("widget count", "dom:all", "partial", ["iframes not entered"])
        self.assertEqual(pe.envelope("https://example.test", [f])["overall"], "partial")

    def test_skipped_scope_is_never_complete(self):
        f = pe.finding("title", "dom:title", "complete")
        ev = pe.envelope("https://example.test", [f], not_examined=["shadow roots"])
        self.assertEqual(ev["overall"], "partial")
        self.assertEqual(ev["not_examined"], ["shadow roots"])

    def test_no_findings_is_unknown_not_empty_success(self):
        self.assertEqual(pe.envelope("http://127.0.0.1:3000", [])["overall"], "unknown")

    def test_rejects_unknown_coverage_and_empty_fields(self):
        with self.assertRaises(ValueError):
            pe.finding("c", "s", "maybe")
        with self.assertRaises(ValueError):
            pe.finding("", "s", "complete")
        with self.assertRaises(ValueError):
            pe.finding("c", "s", "complete", ["  "])

    def test_origin_must_be_bare_http_origin(self):
        for bad in ("ftp://x.test", "https://x.test/path", "https://x.test?q=1", "https://u:p@x.test", "x.test"):
            with self.subTest(origin=bad), self.assertRaises(ValueError):
                pe.origin(bad)
        self.assertEqual(pe.origin("https://x.test:8443/"), "https://x.test:8443")

    def test_serialization_is_deterministic(self):
        f = pe.finding("c", "s", "complete")
        a = pe.to_json(pe.envelope("https://x.test", [f]))
        b = pe.to_json(json.loads(a))
        self.assertEqual(a, b)
        self.assertEqual(json.loads(a)["schema"], pe.SCHEMA)

    def test_cli_reads_json_and_rejects_bad_input(self):
        payload = json.dumps({"origin": "https://x.test", "findings": [
            {"claim": "c", "source": "s", "coverage": "complete"}]})
        ok = subprocess.run([sys.executable, "-S", str(ROOT / "scripts" / "probe_evidence.py")],
                            input=payload, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["overall"], "complete")
        bad = subprocess.run([sys.executable, "-S", str(ROOT / "scripts" / "probe_evidence.py")],
                             input="[]", capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
