"""pin_audit: collect pins from workflows/JSON; unmerged / not-final / drift / ok against a local remote."""
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pin_audit", ROOT / "scripts" / "pin_audit.py")
pa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pa)


def g(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def upstream(tmp_path):
    repo = tmp_path / "remotes" / "o" / "up"
    repo.mkdir(parents=True)
    g(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("a1\n")
    (repo / "b.txt").write_text("b1\n")
    g(repo, "add", ".")
    g(repo, "commit", "-q", "-m", "A")
    a = g(repo, "rev-parse", "HEAD")
    g(repo, "checkout", "-q", "-b", "feature")
    (repo / "b.txt").write_text("b2\n")
    g(repo, "commit", "-qam", "F")
    f = g(repo, "rev-parse", "HEAD")
    g(repo, "checkout", "-q", "main")
    g(repo, "merge", "-q", "--no-ff", "feature", "-m", "Merge feature (#1)")
    m = g(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("a2\n")
    g(repo, "commit", "-qam", "C")
    g(repo, "checkout", "-q", "-b", "side", a)
    (repo / "c.txt").write_text("c\n")
    g(repo, "add", ".")
    g(repo, "commit", "-qm", "U")
    u = g(repo, "rev-parse", "HEAD")
    g(repo, "checkout", "-q", "main")
    return a, f, m, u


def test_collect_workflow_and_json_pins(tmp_path):
    sha = "1" * 40
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    wf.joinpath("ci.yml").write_text(
        f"jobs:\n  a:\n    uses: o/up/.github/workflows/x.yml@{sha}\n  b:\n    steps:\n"
        f"      - uses: actions/checkout@{sha}\n        with:\n          repository: o/up\n          ref: {sha}\n"
        "      - uses: actions/setup-python@v5\n")
    (tmp_path / "vendor.lock.json").write_text(json.dumps({"files": [
        {"repository": "https://github.com/o/up", "commit": sha, "source": "b.txt", "destination": "v/b.txt"},
        {"repository": "o/up", "commit": "main"}]}))
    pins = pa.collect(str(tmp_path))
    kinds = sorted((p["entry"], p["line"]) for p in pins)
    assert kinds == [("actions/checkout", 6), ("checkout o/up", 9), ("o/up/.github/workflows/x.yml", 3), ("v/b.txt", None)]
    assert [p["paths"] for p in pins if p["entry"] == "v/b.txt"] == [["b.txt"]]


def test_states_against_a_local_remote(tmp_path, capsys):
    a, f, m, u = upstream(tmp_path)
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "vendor.lock.json").write_text(json.dumps({"files": [
        {"repository": "o/up", "commit": m, "source": "b.txt"},
        {"repository": "o/up", "commit": f, "source": "b.txt"},
        {"repository": "o/up", "commit": u},
        {"repository": "o/up", "commit": a, "source": "a.txt"},
        {"repository": "o/up", "commit": "9" * 40}]}))
    code = pa.main([str(consumer), "--remote-base", (tmp_path / "remotes").as_uri() + "/"])
    out = capsys.readouterr().out
    assert code == 1
    assert f"ok o/up@{m[:7]} +1 on main" in out
    assert f"not-final o/up@{f[:7]} merged via {m[:7]} (Merge feature (#1))" in out
    assert f"unmerged o/up@{u[:7]} not reachable from main" in out
    assert f"drift o/up@{a[:7]} 1 pinned file(s) changed on main: a.txt" in out
    assert f"unmerged o/up@{'9' * 7} commit not found on the remote" in out
    assert out.strip().splitlines()[-1] == "pins=5 drift=1 not-final=1 ok=1 unmerged=2"


def test_only_filter_empty_and_unreachable(tmp_path, capsys):
    (tmp_path / "vendor.lock.json").write_text(json.dumps({"repository": "x/y", "commit": "2" * 40}))
    assert pa.main([str(tmp_path), "--only", "other"]) == 0
    assert capsys.readouterr().out.strip() == "pins=0"
    assert pa.main([str(tmp_path), "--remote-base", (tmp_path / "nowhere").as_uri() + "/"]) == 2
    assert capsys.readouterr().out.startswith("error x/y:")
