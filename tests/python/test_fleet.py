"""fleet: status/tracking fix on local clones; checks and pr against a fake API."""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fleet", ROOT / "scripts" / "fleet.py")
fleet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleet)


def g(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def clones(tmp_path):
    origin = tmp_path / "origin.git"
    g(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    g(tmp_path, "clone", "-q", str(origin), str(work))
    (work / "a").write_text("1")
    g(work, "add", ".")
    g(work, "commit", "-qm", "a")
    g(work, "push", "-q", "origin", "main")
    g(work, "remote", "set-url", "origin", "https://github.com/o/r.git")
    g(work, "remote", "set-url", "--push", "origin", str(origin))
    return origin, work


def test_status_flags_missing_upstream_and_fix_tracking(tmp_path, capsys):
    origin, work = clones(tmp_path)
    g(work, "checkout", "-q", "-b", "feat")
    (work / "b").write_text("2")
    g(work, "add", ".")
    g(work, "commit", "-qm", "b")
    g(work, "push", "-q", str(origin), "feat")  # pushed, but no tracking config (the hook's false alarm)
    g(work, "remote", "set-url", "origin", str(origin))
    ok, line = fleet.status(str(work))
    assert not ok and "no upstream" in line
    ok, line = fleet.status(str(work), fix=True)
    assert ok and "origin/feat +0/-0" in line and "(tracking fixed)" in line
    (work / "c").write_text("3")
    assert fleet.main(["status", str(work)]) == 1
    assert "untracked=1" in capsys.readouterr().out


def fake_api(responses):
    calls = []

    def call(path, body=None):
        calls.append((path, body))
        for prefix, value in responses.items():
            if prefix in path:
                return value(body) if callable(value) else value
        raise RuntimeError("no fake for " + path)
    call.calls = calls
    return call


def test_checks_reports_failed_steps_and_annotations(tmp_path, capsys):
    _, work = clones(tmp_path)
    runs = {"check_runs": [
        {"id": 1, "name": "python", "status": "completed", "conclusion": "failure"},
        {"id": 2, "name": "node", "status": "completed", "conclusion": "success"},
        {"id": 3, "name": "copilot-pull-request-reviewer", "status": "completed", "conclusion": "failure"}]}
    call = fake_api({"/check-runs?": runs, "actions/jobs/1": {"steps": [{"name": "Run pytest", "conclusion": "failure"}]},
                     "check-runs/1/annotations": [
                         {"annotation_level": "failure", "path": ".github", "start_line": 9, "message": "Process completed with exit code 1."},
                         {"annotation_level": "failure", "path": "tests/x.py", "start_line": 3, "message": "assert  1 == 2"}]})
    assert fleet.main(["checks", str(work), "--steps"], call=call) == 1
    out = capsys.readouterr().out
    assert "failed  o/r@" in out and "runs=2" in out and "x python (failure)" in out
    assert "step: Run pytest" in out and "tests/x.py:3 assert 1 == 2" in out and "exit code" not in out


def test_checks_wait_until_green(tmp_path, capsys):
    _, work = clones(tmp_path)
    states = iter(["in_progress", "completed"])
    call = fake_api({"/check-runs?": lambda body: {"check_runs": [
        {"id": 1, "name": "ci", "status": next(states), "conclusion": "success"}]}})
    sleeps = []
    assert fleet.main(["checks", str(work), "--wait", "100", "--interval", "1"], call=call, sleep=sleeps.append) == 0
    assert len(sleeps) == 1 and capsys.readouterr().out.startswith("green")


def test_pr_opens_or_reports_existing(tmp_path, capsys):
    _, work = clones(tmp_path)
    g(work, "checkout", "-q", "-b", "feat")
    body = tmp_path / "body.md"
    body.write_text("hello")
    call = fake_api({"pulls?state=open": [], "repos/o/r/pulls": lambda b: {"number": 5, "html_url": "u5"}})
    assert fleet.main(["pr", str(work), "--title", "t", "--body-file", str(body)], call=call) == 0
    assert "opened o/r #5 u5" in capsys.readouterr().out
    assert call.calls[-1][1] == {"title": "t", "head": "feat", "base": "main", "body": "hello", "draft": False}
    call = fake_api({"pulls?state=open": [{"number": 4, "html_url": "u4"}]})
    assert fleet.main(["pr", str(work), "--title", "t", "--body-file", str(body)], call=call) == 0
    assert "exists o/r #4 u4" in capsys.readouterr().out
    assert fleet.main(["status", str(tmp_path / "missing")]) == 2
