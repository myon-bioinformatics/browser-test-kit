import importlib.util
import io
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
spec = importlib.util.spec_from_file_location("gh_ops", SCRIPTS / "gh_ops.py")
gh_ops = importlib.util.module_from_spec(spec)
assert spec.loader
sys.modules["gh_ops"] = gh_ops
spec.loader.exec_module(gh_ops)

REPO = "octo/demo"
HEAD = "ecfd0ba1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7"
OTHER = "ecfd0ba9999999999999999999999999999999aa"


def reply(data=None, status=200, link=None):
    return gh_ops.Response(status, data, {"link": link} if link else {})


class Stub:
    """Transport stub: routes (METHOD, path) to a reply, a reply list, or a callable."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, body, headers):
        parts = urllib.parse.urlsplit(url)
        self.calls.append({"method": method, "path": parts.path, "query": urllib.parse.parse_qs(parts.query),
                           "body": body, "headers": headers})
        route = self.routes[(method, parts.path)]
        if callable(route):
            return route(parts, body)
        if isinstance(route, list):
            return route.pop(0) if len(route) > 1 else route[0]
        return route

    @property
    def methods(self):
        return [call["method"] for call in self.calls]


def client_for(routes, token="t0ken"):
    stub = Stub(routes)
    return gh_ops.Client(token=token, transport=stub), stub


def check_run(name, conclusion="success", status="completed", annotations=0, run_id=1):
    return {"id": run_id, "name": name, "status": status, "conclusion": conclusion, "head_sha": HEAD,
            "output": {"annotations_count": annotations}}


def pr_payload(**overrides):
    data = {"state": "open", "merged": False, "mergeable": True, "mergeable_state": "clean", "draft": False,
            "head": {"sha": HEAD, "ref": "feature"}, "base": {"ref": "main"}, "commits": 2, "changed_files": 3,
            "additions": 10, "deletions": 2, "html_url": "https://github.com/octo/demo/pull/11", "body": ""}
    data.update(overrides)
    return data


# --- issue-comments ---------------------------------------------------------------

def comment(index, author="alice", body=None):
    return {"id": 100 + index, "created_at": f"2026-09-2{index % 10}T00:00:00Z", "user": {"login": author},
            "body": body if body is not None else f"comment {index}", "html_url": f"https://x/{index}"}


def comments_routes(total=150, since=None):
    items = [comment(i, author="bot" if i % 2 else "alice") for i in range(total)]
    items[0]["body"] = "line one\n\nline   two " + "x" * 300

    def pages(parts, body):
        query = urllib.parse.parse_qs(parts.query)
        if since is not None:
            assert query["since"] == [since]
        page = int(query.get("page", ["1"])[0])
        chunk = items[(page - 1) * 100: page * 100]
        link = None
        if page * 100 < total:
            link = f'<https://api.github.com/repos/octo/demo/issues/24/comments?per_page=100&page={page + 1}>; rel="next"'
        return reply(chunk, link=link)

    return {
        ("GET", "/repos/octo/demo/issues/24"): reply({"title": "Roadmap", "state": "open", "body": "b" * 42}),
        ("GET", "/repos/octo/demo/issues/24/comments"): pages,
    }


def test_issue_comments_paginates_and_digests_without_full_bodies():
    client, stub = client_for(comments_routes())
    result = gh_ops.issue_comments(REPO, 24, client=client, preview=20)
    assert result["total_comments"] == 150
    assert len(result["comments"]) == 150
    first = result["comments"][0]
    assert first["preview"] == "line one line two x…"
    assert first["chars"] == len("line one\n\nline   two " + "x" * 300)
    assert result["shown"] == {}
    assert result["body_chars"] == 42 and result["is_pull_request"] is False
    assert [call["query"].get("page") for call in stub.calls[1:]] == [None, ["2"]]
    assert set(stub.methods) == {"GET"}


def test_issue_comments_filters_show_and_save(tmp_path):
    client, _ = client_for(comments_routes(total=5, since="2026-09-20T00:00:00Z"))
    target = tmp_path / "out" / "comments.json"
    result = gh_ops.issue_comments(REPO, 24, client=client, since="2026-09-20T00:00:00Z", author="bot",
                                   last=1, show=(2,), save=str(target))
    assert [row["index"] for row in result["comments"]] == [3]
    assert result["shown"] == {2: "comment 2"}
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["issue"]["title"] == "Roadmap" and len(saved["comments"]) == 5


def test_issue_comments_rejects_unknown_show_index():
    client, _ = client_for(comments_routes(total=3))
    with pytest.raises(gh_ops.GhOpsError, match="no comment with index 7"):
        gh_ops.issue_comments(REPO, 24, client=client, show=(7,))


def test_issue_comments_cli_prints_one_line_per_comment(capsys):
    client, _ = client_for(comments_routes(total=3))
    assert gh_ops.main(["issue-comments", REPO, "24", "--show", "1"], client=client) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == 'issue #24 open "Roadmap" -- 3 comment(s), body 42 chars'
    assert out[1].startswith("[0] 2026-09-20T00:00:00Z alice ")
    assert out[3].startswith("[2] ")
    assert out[4:] == ["--- [1] ---", "comment 1"]


# --- pr-status / runs / workflow-state ----------------------------------------------

def test_pr_status_summary(capsys):
    client, _ = client_for({("GET", "/repos/octo/demo/pulls/11"): reply(pr_payload())})
    assert gh_ops.main(["pr-status", REPO, "11"], client=client) == 0
    assert capsys.readouterr().out.strip() == (
        "#11 open draft=False merged=False mergeable=True (clean) head=ecfd0ba1c2d3 feature -> main "
        "commits=2 files=3 +10/-2"
    )


def test_runs_by_sha_and_workflow():
    data = {"total_count": 1, "workflow_runs": [{"id": 9, "event": "pull_request", "head_sha": HEAD,
                                                 "status": "completed", "conclusion": "success", "html_url": "u"}]}
    client, stub = client_for({
        ("GET", "/repos/octo/demo/actions/runs"): reply(data),
        ("GET", "/repos/octo/demo/actions/workflows/codeql.yml/runs"): reply(data),
    })
    assert gh_ops.runs(REPO, sha=HEAD, client=client)["runs"][0]["id"] == 9
    assert stub.calls[0]["query"]["head_sha"] == [HEAD]
    assert gh_ops.runs(REPO, workflow="codeql.yml", client=client)["total_count"] == 1
    with pytest.raises(gh_ops.GhOpsError):
        gh_ops.runs(REPO, client=client)


def test_workflow_state_exit_codes():
    client, _ = client_for({("GET", "/repos/octo/demo/actions/workflows/codeql.yml"): reply({"state": "disabled_inactivity"})})
    assert gh_ops.main(["workflow-state", REPO, "codeql.yml"], client=client) == 1


# --- checks-wait ----------------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def wait(routes, **kwargs):
    client, stub = client_for(routes)
    clock = FakeClock()
    result = gh_ops.checks_wait(REPO, HEAD, client=client, sleep=clock.sleep, clock=clock, interval=10, **kwargs)
    return result, stub, clock


def test_zero_checks_until_timeout_is_not_green():
    result, _, clock = wait({("GET", f"/repos/octo/demo/commits/{HEAD}/check-runs"): reply({"check_runs": []})},
                            min_checks=1, timeout=30)
    assert result["ok"] is False and result["timed_out"] is True
    assert result["reason"].startswith("timeout: only 0 check run(s)")
    assert clock.sleeps == [10, 10, 10]


def test_checks_wait_polls_until_complete():
    path = ("GET", f"/repos/octo/demo/commits/{HEAD}/check-runs")
    result, _, clock = wait({path: [
        reply({"check_runs": [check_run("unit", conclusion=None, status="in_progress")]}),
        reply({"check_runs": [check_run("unit"), check_run("lint", conclusion="skipped", run_id=2)]}),
    ]}, min_checks=2)
    assert result["ok"] is True and result["succeeded"] == 1 and clock.sleeps == [10]


def test_checks_wait_failure_reports_annotations(capsys):
    routes = {
        ("GET", f"/repos/octo/demo/commits/{HEAD}/check-runs"): reply({"check_runs": [
            check_run("unit"), check_run("e2e", conclusion="failure", annotations=1, run_id=7)]}),
        ("GET", "/repos/octo/demo/check-runs/7/annotations"): reply([
            {"annotation_level": "failure", "title": "tests", "message": "3 failed (py3.12, tested ecfd0ba)"}]),
    }
    client, _ = client_for(routes)
    assert gh_ops.main(["checks-wait", REPO, HEAD, "--min", "2"], client=client) == 1
    out = capsys.readouterr().out
    assert "1 check run(s) failed: e2e" in out
    assert "[failure] tests: 3 failed (py3.12, tested ecfd0ba)" in out


def test_all_skipped_is_not_green():
    result, _, _ = wait({("GET", f"/repos/octo/demo/commits/{HEAD}/check-runs"): reply(
        {"check_runs": [check_run("a", conclusion="skipped")]})})
    assert result["ok"] is False and "no check run concluded success" in result["reason"]


def test_min_checks_must_be_positive():
    with pytest.raises(gh_ops.GhOpsError):
        wait({}, min_checks=0)


# --- workflow-dispatch ----------------------------------------------------------------

def dispatch_routes(state="active"):
    return {
        ("GET", "/repos/octo/demo/actions/workflows/codeql.yml"): reply({"state": state}),
        ("POST", "/repos/octo/demo/actions/workflows/codeql.yml/dispatches"): reply(None, status=204),
    }


def test_workflow_dispatch_dry_run_and_inactive_never_post():
    client, stub = client_for(dispatch_routes())
    assert gh_ops.workflow_dispatch(REPO, "codeql.yml", ref="main", client=client)["dry_run"] is True
    client2, stub2 = client_for(dispatch_routes(state="disabled_inactivity"))
    assert gh_ops.workflow_dispatch(REPO, "codeql.yml", ref="main", write=True, client=client2)["ok"] is False
    assert set(stub.methods) == set(stub2.methods) == {"GET"}


def test_workflow_dispatch_write_posts_ref():
    client, stub = client_for(dispatch_routes())
    assert gh_ops.workflow_dispatch(REPO, "codeql.yml", ref="main", write=True, client=client)["dispatched"] is True
    assert stub.calls[-1]["method"] == "POST" and stub.calls[-1]["body"] == {"ref": "main"}


# --- pr-body-replace ------------------------------------------------------------------

def body_routes(body, after=None):
    bodies = [reply({"body": body})] + ([reply({"body": after})] if after is not None else [])
    return {
        ("GET", "/repos/octo/demo/pulls/11"): bodies,
        ("PATCH", "/repos/octo/demo/pulls/11"): reply({"body": after}),
    }


@pytest.mark.parametrize("body,count", [("no anchor here", 0), ("A-ANCHOR and A-ANCHOR", 2)])
def test_pr_body_replace_requires_exactly_one_anchor(body, count):
    client, stub = client_for(body_routes(body))
    result = gh_ops.pr_body_replace(REPO, 11, old="A-ANCHOR", new="B", write=True, client=client)
    assert result["ok"] is False and result["anchor_count"] == count
    assert set(stub.methods) == {"GET"}


def test_pr_body_replace_mentions_crlf_bodies():
    client, _ = client_for(body_routes("line1\r\nline2"))
    result = gh_ops.pr_body_replace(REPO, 11, old="line1\nline2", new="x", client=client)
    assert "CRLF" in result["reason"]


def test_pr_body_replace_dry_run_then_write_and_verify():
    client, stub = client_for(body_routes("keep [OLD] keep"))
    assert gh_ops.pr_body_replace(REPO, 11, old="[OLD]", new="[NEW]", client=client)["dry_run"] is True
    assert set(stub.methods) == {"GET"}
    client, stub = client_for(body_routes("keep [OLD] keep", after="keep [NEW] keep"))
    result = gh_ops.pr_body_replace(REPO, 11, old="[OLD]", new="[NEW]", write=True, client=client)
    assert result["ok"] is True and result["verified"] is True
    assert stub.calls[1] == {**stub.calls[1], "method": "PATCH", "body": {"body": "keep [NEW] keep"}}


# --- pr-merge -------------------------------------------------------------------------

def merge_routes(pr=None, commits=(HEAD,), runs=None, merge_reply=None):
    return {
        ("GET", "/repos/octo/demo/pulls/11"): reply(pr or pr_payload()),
        ("GET", "/repos/octo/demo/pulls/11/commits"): reply([{"sha": sha} for sha in commits]),
        ("GET", f"/repos/octo/demo/commits/{HEAD}/check-runs"): reply(
            {"check_runs": runs if runs is not None else [check_run(f"c{i}", run_id=i) for i in range(5)]}),
        ("PUT", "/repos/octo/demo/pulls/11/merge"): merge_reply or reply({"merged": True, "sha": "m3rg3"}),
    }


@pytest.mark.parametrize(
    "routes,sha,needle",
    [
        (merge_routes(pr=pr_payload(head={"sha": "0" * 40, "ref": "f"})), "ecfd0ba", "does not match"),
        (merge_routes(commits=(OTHER, HEAD)), "ecfd0ba", "matches 2 commits"),
        (merge_routes(commits=("1" * 40,)), "ecfd0ba", "does not contain the head commit"),
        (merge_routes(pr=pr_payload(mergeable_state="blocked")), "ecfd0ba", "not 'clean'"),
        (merge_routes(pr=pr_payload(state="closed")), "ecfd0ba", "not open"),
        (merge_routes(runs=[]), "ecfd0ba", "only 0 check run(s)"),
        (merge_routes(runs=[check_run(f"c{i}", run_id=i) for i in range(4)] + [check_run("bad", "failure", run_id=9)]),
         "ecfd0ba", "failed: bad"),
        (merge_routes(runs=[check_run(f"c{i}", run_id=i) for i in range(4)] + [check_run("p", None, "queued", run_id=9)]),
         "ecfd0ba", "still pending"),
    ],
)
def test_pr_merge_never_writes_when_a_precondition_fails(routes, sha, needle):
    client, stub = client_for(routes)
    result = gh_ops.pr_merge(REPO, 11, sha=sha, min_checks=5, write=True, client=client)
    assert result["ok"] is False and result["merged"] is False
    assert any(needle in failure for failure in result["failures"]), result["failures"]
    assert "PUT" not in stub.methods


def test_pr_merge_dry_run_describes_the_pinned_merge():
    client, stub = client_for(merge_routes())
    result = gh_ops.pr_merge(REPO, 11, sha="ecfd0ba", min_checks=5, message="msg", client=client)
    assert result["ok"] is True and result["dry_run"] is True
    assert result["would_merge"] == {"sha": HEAD, "merge_method": "squash", "commit_message": "msg"}
    assert "PUT" not in stub.methods


def test_pr_merge_write_pins_head_sha_and_reports_merge_commit():
    client, stub = client_for(merge_routes())
    result = gh_ops.pr_merge(REPO, 11, sha="ecfd0ba", min_checks=5, method="squash", write=True, client=client)
    assert result == {**result, "ok": True, "merged": True, "merge_sha": "m3rg3"}
    put = [call for call in stub.calls if call["method"] == "PUT"]
    assert len(put) == 1 and put[0]["body"]["sha"] == HEAD


def test_pr_merge_head_moved_during_merge_is_a_condition_failure():
    client, _ = client_for(merge_routes(merge_reply=reply({"message": "Head branch was modified"}, status=409)))
    result = gh_ops.pr_merge(REPO, 11, sha="ecfd0ba", min_checks=5, write=True, client=client)
    assert result["ok"] is False and "409" in result["failures"][0]


def test_pr_merge_cli_one_line_dry_run_exit_code(tmp_path, capsys):
    message = tmp_path / "msg.txt"
    message.write_text("Squash title body\n", encoding="utf-8")
    client, stub = client_for(merge_routes())
    code = gh_ops.main(["pr-merge", REPO, "11", "--sha", "ecfd0ba", "--min-checks", "5",
                        "--message-file", str(message)], client=client)
    assert code == 0 and "PUT" not in stub.methods
    assert capsys.readouterr().out.startswith("OK pr-merge (dry run)")


@pytest.mark.parametrize("sha", ["xyz", "abc", "g" * 7])
def test_invalid_sha_is_an_input_error(sha):
    client, _ = client_for(merge_routes())
    with pytest.raises(gh_ops.GhOpsError):
        gh_ops.pr_merge(REPO, 11, sha=sha, client=client)


# --- tokens and HTTP error attribution ---------------------------------------------------

def test_token_is_sent_but_never_printed(monkeypatch, capsys):
    secret = "ghp_" + "S3cr3t" * 5
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    stub = Stub({("GET", "/repos/octo/demo/pulls/11"): reply({"message": f"Bad credentials {secret}"}, status=401)})
    code = gh_ops.main(["--json", "pr-status", REPO, "11"], client=gh_ops.Client(transport=stub))
    captured = capsys.readouterr()
    assert code == 2
    assert stub.calls[0]["headers"]["Authorization"] == f"Bearer {secret}"
    assert secret not in captured.out + captured.err
    assert "HTTP 401" in captured.err


def test_forbidden_is_not_reported_as_unconfigured():
    client, _ = client_for({("GET", "/repos/octo/demo/actions/workflows/codeql.yml"): reply({"message": "Resource not accessible"}, 403)})
    with pytest.raises(gh_ops.GhOpsError, match="not evidence that the feature is unconfigured"):
        gh_ops.workflow_state(REPO, "codeql.yml", client=client)


# --- stdlib-only / one-line import ---------------------------------------------------------

def test_runs_with_python_dash_s_and_imports_in_one_line():
    help_run = subprocess.run([sys.executable, "-S", str(SCRIPTS / "gh_ops.py"), "--help"], capture_output=True, text=True)
    assert help_run.returncode == 0 and "issue-comments" in help_run.stdout
    one_line = subprocess.run([sys.executable, "-S", "-c", "from gh_ops import pr_merge, issue_comments; print('ok')"],
                              cwd=SCRIPTS, capture_output=True, text=True)
    assert one_line.stdout.strip() == "ok", one_line.stderr


# --- sync-main (git) ------------------------------------------------------------------------

def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}.items():
        monkeypatch.setenv(key, value)
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    git(tmp_path, "clone", str(remote), str(work))
    (work / "a.txt").write_text("base\n", encoding="utf-8")
    git(work, "add", "a.txt"); git(work, "commit", "-m", "base"); git(work, "push", "origin", "HEAD:main")
    git(work, "checkout", "-b", "feature")
    (work / "b.txt").write_text("feature\n", encoding="utf-8")
    git(work, "add", "b.txt"); git(work, "commit", "-m", "feature"); git(work, "push", "-u", "origin", "feature")
    return remote, work


def advance_main(remote, tmp_path, filename, text):
    other = tmp_path / f"other-{filename}"
    git(tmp_path, "clone", "-b", "main", str(remote), str(other))
    (other / filename).write_text(text, encoding="utf-8")
    git(other, "add", filename); git(other, "commit", "-m", f"main {filename}"); git(other, "push", "origin", "main")


def test_sync_main_dry_run_then_merge(repos, tmp_path):
    remote, work = repos
    advance_main(remote, tmp_path, "c.txt", "main\n")
    assert gh_ops.sync_main(cwd=str(work)) == {"ok": True, "branch": "feature", "behind": 1, "merged": False, "dry_run": True}
    result = gh_ops.sync_main(cwd=str(work), write=True, push=True)
    assert result["merged"] is True and result["pushed"] is True
    assert git(work, "rev-parse", "HEAD") == git(work, "rev-parse", "origin/feature")
    assert (work / "c.txt").exists()


def test_sync_main_conflict_aborts_cleanly(repos, tmp_path):
    remote, work = repos
    advance_main(remote, tmp_path, "b.txt", "conflicting\n")
    result = gh_ops.sync_main(cwd=str(work), write=True)
    assert result["ok"] is False and result["conflicts"] == ["b.txt"]
    assert git(work, "status", "--porcelain") == ""
    assert (work / "b.txt").read_text(encoding="utf-8") == "feature\n"


def test_sync_main_refuses_diverged_local_or_dirty_tree(repos):
    _, work = repos
    (work / "b.txt").write_text("dirty\n", encoding="utf-8")
    assert gh_ops.sync_main(cwd=str(work), write=True)["reason"] == "working tree has uncommitted changes"
    git(work, "commit", "-am", "local only")
    assert "differs from origin/feature" in gh_ops.sync_main(cwd=str(work), write=True)["reason"]


# --- comments-file (offline digest of a saved JSON dump) ----------------------------

def _saved_comments(count=43, size=2000):
    return [{"id": n, "created_at": f"2026-09-20T14:{n:02d}:00Z",
             "user": {"login": "claude[bot]" if n == 0 else "myon"}, "body": ("本文 " * size)[:size],
             "html_url": f"https://github.com/o/r/issues/24#issuecomment-{n}"} for n in range(count)]


def test_comments_file_digests_an_oversized_saved_tool_result(tmp_path, capsys):
    path = tmp_path / "mcp-github-issue_read.txt"
    path.write_text(json.dumps(_saved_comments(), ensure_ascii=False), encoding="utf-8")  # ~90k chars, 1 line
    assert gh_ops.main(["comments-file", str(path), "--preview", "40"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"{path} -- 43 comment(s)"
    assert len(lines) == 44 and max(len(line) for line in lines[1:]) < 120
    assert lines[1].startswith("[0] 2026-09-20T14:00:00Z claude[bot] 2000 chars: 本文")


def test_comments_file_reads_save_output_from_stdin_and_filters(monkeypatch):
    saved = {"issue": {"title": "Roadmap", "state": "open"}, "comments": _saved_comments(3, 10)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(saved)))
    result = gh_ops.comments_file("-", author="myon", last=1, show=(0,))
    assert (result["title"], result["total_comments"]) == ("Roadmap", 3)
    assert [row["index"] for row in result["comments"]] == [2]
    assert result["shown"] == {0: saved["comments"][0]["body"]}


def test_comments_file_rejects_non_comment_json(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"not": "comments"}', encoding="utf-8")
    assert gh_ops.main(["comments-file", str(path)]) == 2
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(gh_ops.GhOpsError, match="not JSON"):
        gh_ops.comments_file(str(path))


def test_comments_file_runs_offline_without_a_token(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(_saved_comments(2, 5)), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in {"GITHUB_TOKEN", "GH_TOKEN"}}
    env.update(PYTHONIOENCODING="utf-8", HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9")
    done = subprocess.run([sys.executable, "-S", str(SCRIPTS / "gh_ops.py"), "comments-file", str(path),
                           "--last", "1"], capture_output=True, text=True, encoding="utf-8", env=env)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[1].startswith("[1] 2026-09-20T14:01:00Z myon 5 chars: ")


# --- pr-for-branch -----------------------------------------------------------------

def test_pr_for_branch_lists_matches_with_an_owner_qualified_head(capsys):
    pulls = [{"number": 61, "state": "closed", "merged_at": "2026-09-26T17:00:00Z", "draft": False,
              "head": {"sha": "f534c03af3d5aaaa"}, "base": {"ref": "main"}, "title": "feat: P7",
              "html_url": "https://github.com/octo/demo/pull/61"}]
    client, stub = client_for({("GET", "/repos/octo/demo/pulls"): reply(pulls)})
    assert gh_ops.main(["pr-for-branch", REPO, "claude/x"], client=client) == 0
    assert capsys.readouterr().out.strip() == (
        '#61 merged head=f534c03af3d5 -> main "feat: P7" https://github.com/octo/demo/pull/61')
    assert stub.calls[0]["query"]["head"] == ["octo:claude/x"]
    assert stub.calls[0]["query"]["state"] == ["all"]


def test_pr_for_branch_without_a_pr_is_exit_1(capsys):
    client, stub = client_for({("GET", "/repos/octo/demo/pulls"): reply([])})
    assert gh_ops.main(["pr-for-branch", REPO, "fork:feature", "--state", "open"], client=client) == 1
    assert capsys.readouterr().out.strip() == "no open PR with head fork:feature"
    assert stub.calls[0]["query"]["head"] == ["fork:feature"]
