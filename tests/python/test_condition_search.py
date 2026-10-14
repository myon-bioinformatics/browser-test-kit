"""condition_search: rank conditions that explain an outcome; counterexamples; CLI."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "condition_search.py"
spec = importlib.util.spec_from_file_location("condition_search", SCRIPT)
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


def presses():
    """Merged-semantics cards (tall box, many children) miss; plain buttons hit; one noisy miss."""
    rows = []
    for i, (h, kids, hit) in enumerate([(40, 0, True), (44, 0, True), (38, 0, True), (42, 1, True),
                                        (122, 2, False), (130, 3, False), (125, 2, False), (118, 2, False),
                                        (41, 0, False)]):
        rows.append({"label": f"r{i}", "hit": {"self": hit, "tag": "div"}, "box": {"height": h}, "children": kids})
    return rows


def test_finds_the_merged_card_condition_and_reports_counterexamples():
    rows = cs.load(json.dumps(presses()))
    report = cs.search(rows, "hit.self", False, skip=["label"])
    best = report["results"][0]
    assert "box.height > " in best["expr"] or "children > " in best["expr"]
    assert (best["tp"], best["fp"], best["fn"]) == (4, 0, 1)
    assert best["fn_rows"] == [8] and best["mcc"] >= 0.8


def test_same_matching_set_is_listed_once_simplest_first():
    report = cs.search(cs.load(json.dumps(presses())), "hit.self", False, skip=["label"], top=20)
    masks = [(r["tp"], r["fp"], tuple(r["fn_rows"]), tuple(r["fp_rows"])) for r in report["results"]]
    assert len(masks) == len(set(masks))


def test_loads_jsonl_and_flattens_nested_and_missing_fields_never_match():
    rows = cs.load('{"a": {"b": 1}}\n{"a": {"b": 5}, "c": true}\n')
    assert rows[0] == {"a.b": 1} and rows[1] == {"a.b": 5, "c": True}
    preds = cs.predicates(rows, set())
    assert preds["c == true"] == 0b10


def test_cli_exit_codes_and_bounded_output(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps(presses()))
    run = lambda *a: subprocess.run([sys.executable, "-S", str(SCRIPT), *a], capture_output=True, text=True)
    ok = run(str(path), "--target", "hit.self=false", "--id", "label", "--top", "2")
    assert ok.returncode == 0 and "fn: r8" in ok.stdout and ok.stdout.count("mcc=") == 2
    assert run(str(path), "--target", "hit.self=false", "--min-mcc", "0.99").returncode == 1
    assert run(str(path), "--target", "nope=1").returncode == 2
    assert run(str(tmp_path / "missing.json"), "--target", "hit.self=false").returncode == 2
