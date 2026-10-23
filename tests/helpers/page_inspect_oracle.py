"""Stdlib oracle for page_inspect. One JSON request on stdin, one JSON object on stdout."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("page_inspect", ROOT / "scripts" / "page_inspect.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def call(request):
    name = request["fn"]
    if name == "lcs":
        return module.lcs_length(request["left"], request["right"])
    if name == "similarity":
        return module.similarity(request["left"], request["right"])
    if name == "normalize":
        return module.normalize_elements(request["raw"], start=request.get("start", 0), limit=request.get("limit", 50))
    if name == "locate":
        return module.locate(
            request["elements"], query=request.get("query", ""), role=request.get("role", ""),
            threshold=request.get("threshold", 1), start=request.get("start", 0),
            limit=request.get("limit", 20), unique=request.get("unique", False),
        )
    if name == "count":
        return module.count_elements(
            request["elements"], query=request.get("query", ""), role=request.get("role", ""),
            threshold=request.get("threshold", 1),
        )
    if name == "describe":
        return module.describe_element(request["elements"], request["target"], context=request.get("context", 1))
    if name == "operations":
        return module.operations()
    if name == "assemble":
        return module.assemble_survey(
            request["raw"], environment=request["environment"], url=request["url"],
            start=request.get("start", 0), limit=request.get("limit", 50),
        )
    if name == "target":
        return module.target_url(request["target"])
    if name == "os":
        return module.os_name()
    if name == "hard_cap":
        return module.HARD_CAP
    raise module.InspectError(f"unknown oracle fn {name}", "the parity test sent a function this oracle does not run")


def main() -> int:
    request = json.loads(sys.stdin.read() or "{}")
    try:
        value = call(request)
    except module.InspectError as exc:
        value = {"ok": False, "error": exc.error, "hint": exc.hint, "stage": exc.stage, "code": exc.code}
        json.dump(value, sys.stdout)
        sys.stdout.write("\n")
        return 0
    json.dump({"ok": True, "value": value}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
