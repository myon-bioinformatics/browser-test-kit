"""Explicit legacy-provenance projection from the verified shared vendor lock.

No source acquisition, importing candidate modules, tokens or repository writes.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BINDINGS = [['scripts/git_inspector.provenance.json',
  'scripts/git_inspector.py',
  {'git_blob_sha1': 'blob_sha',
   'sha256': 'sha256',
   'upstream_commit': 'commit',
   'upstream_path': 'source',
   'upstream_repository': 'repository',
   'vendored_path': 'destination'}]]
EXPECTED = {('myon-bioinformatics/myon-bioinformatics', 'git_inspector.py', 'scripts/git_inspector.py')}


def records(root):
    lock = json.loads((root / "vendor.lock.json").read_text(encoding="utf-8"))
    if lock["schema"] != "vendor-lock/1":
        raise ValueError("unsupported vendor lock")
    files = lock["files"]
    if len(files) != len(EXPECTED) or {(e["repository"], e["source"], e["destination"]) for e in files} != EXPECTED:
        raise ValueError("unexpected source or destination")
    by_destination = {e["destination"]: e for e in files}
    for e in files:
        if e["ref"] != "refs/heads/main" or not re.fullmatch(r"[0-9a-f]{40}", e["commit"]):
            raise ValueError("invalid source identity")
        data = (root / e["destination"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != e["blob_sha"] or hashlib.sha256(data).hexdigest() != e["sha256"]:
            raise ValueError("locked bytes mismatch: " + e["destination"])
    return by_destination


def project(root):
    entries = records(root)  # Verify every source/LICENSE before writing any metadata.
    pending = {}
    for path, destination, fields in BINDINGS:
        record = json.loads((root / path).read_text(encoding="utf-8"))
        entry = entries[destination]
        old_commit = record.get("commit")
        for target, source in fields.items():
            record[target] = "https://github.com/" + entry["repository"] if source == "repository_url" else entry[source]
        if "date" in record and old_commit != record["commit"]:
            record["date"] = datetime.now(timezone.utc).date().isoformat()
        if "license" in record:
            license_entry = next(e for e in entries.values() if e["repository"] == entry["repository"] and e["source"] == "LICENSE")
            record["license"] = {"source_path": "LICENSE", "vendored_path": license_entry["destination"],
                                 "blob_sha": license_entry["blob_sha"], "sha256": license_entry["sha256"]}
        pending[path] = record
    # All per-file formats are mapped above.
    for path, record in pending.items():
        (root / path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        project(ROOT)
    except (ValueError, KeyError, OSError) as error:
        print("vendor-provenance: " + str(error), file=sys.stderr)
        raise SystemExit(2)
