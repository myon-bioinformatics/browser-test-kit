from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "repo_overview.py"
spec = importlib.util.spec_from_file_location("repo_overview", SCRIPT)
repo_overview = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(repo_overview)


def make_tree(root: Path) -> None:
    files = {
        "README.md": "# demo\nline 2\nline 3\n",
        "package.json": '{"private": true}\n',
        "requirements-test.txt": "pytest\n",
        ".github/workflows/ci.yml": "name: ci\n",
        "src/app.py": "print('hi')\n",
        "node_modules/pkg/index.js": "junk\n",
        "test-results/run/evidence.json": "{}\n",
        "src/__pycache__/app.cpython-312.pyc": "junk\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (root / "Dockerfile.bin").write_bytes(b"\x00\x01binary")


def git_env(**overrides: str) -> dict:
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
              GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
              GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com")
    env.update(overrides)
    return env


def commit_file(root: Path, relative: str, content, date: str) -> None:
    """Write ``relative`` (str or bytes) and commit it alone, at a fixed author/committer date."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content) if isinstance(content, bytes) else path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", relative], check=True, env=git_env())
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", f"commit {relative}"], check=True,
                   env=git_env(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date))


def test_key_files_then_file_list_without_dependency_or_result_dirs(tmp_path: Path) -> None:
    make_tree(tmp_path)
    out = repo_overview.overview(tmp_path)
    headers = [line for line in out.splitlines() if line.startswith("=== ")]
    assert headers == [
        "=== about ===",
        "=== README.md (3 lines) ===",
        "=== package.json (1 line) ===",
        "=== requirements-test.txt (1 line) ===",
        "=== Dockerfile.bin (binary, 8 bytes; not shown) ===",
        "=== .github/workflows/ci.yml (1 line) ===",
        "=== files (6) ===",
    ]
    listed = out.split("=== files (6) ===\n", 1)[1].splitlines()
    assert listed == [".github/workflows/ci.yml", "Dockerfile.bin", "README.md", "package.json",
                      "requirements-test.txt", "src/app.py"]


def test_caps_lines_and_files(tmp_path: Path) -> None:
    make_tree(tmp_path)
    out = repo_overview.overview(tmp_path, max_lines=1, max_files=2, include=("src/*.py",))
    assert "=== README.md (3 lines) ===\n# demo\n[... truncated: showing 1 of 3 lines (--max-lines)]" in out
    assert "=== src/app.py (1 line) ===" in out
    assert out.endswith("=== files (6) ===\n.github/workflows/ci.yml\nDockerfile.bin\n[... 4 more files (--max-files)]")


def test_git_work_tree_uses_ls_files_and_respects_gitignore(tmp_path: Path) -> None:
    make_tree(tmp_path)
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (tmp_path / "debug.log").write_text("noise\n", encoding="utf-8")
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=env)
    paths = repo_overview.list_files(tmp_path)
    assert "debug.log" not in paths and ".gitignore" in paths and "src/app.py" in paths
    assert not any(path.startswith(("node_modules/", "test-results/")) for path in paths)


def test_cli_on_this_repository_runs_without_site_packages() -> None:
    done = subprocess.run([sys.executable, "-S", str(SCRIPT), str(ROOT), "--max-lines", "3", "--max-files", "5"],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("=== about ===\n")
    assert "=== README.md (" in done.stdout
    assert "=== playwright.config.ts (" in done.stdout and "=== files (" in done.stdout
    missing = subprocess.run([sys.executable, "-S", str(SCRIPT), str(ROOT / "nope")], capture_output=True, text=True)
    assert missing.returncode == 2


# --- about --------------------------------------------------------------

def test_about_combines_package_json_pyproject_and_readme(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "demo", "description": "A demo package.  "}\n',
                                           encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndescription = "A demo project"\n',
                                             encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# demo\n\n"
        "[![CI](https://img.shields.io/badge/CI-passing-green)](https://example.com/ci)\n\n"
        "This is the real description paragraph spanning\n"
        "two lines of markdown source.\n\n"
        "## More\n\nignored body text\n",
        encoding="utf-8",
    )
    assert repo_overview.about(tmp_path) == (
        "=== about ===\n"
        "package.json: A demo package.\n"
        "pyproject.toml: A demo project\n"
        "README: This is the real description paragraph spanning two lines of markdown source."
    )


def test_about_omitted_when_nothing_found(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    assert repo_overview.about(tmp_path) is None
    assert "=== about ===" not in repo_overview.overview(tmp_path)


def test_about_ignores_package_json_without_description(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"private": true}\n', encoding="utf-8")
    assert repo_overview.about(tmp_path) is None


def test_about_readme_paragraph_truncated_to_300_chars(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(f"# t\n\n{'x' * 400}\n", encoding="utf-8")
    assert repo_overview.about(tmp_path) == "=== about ===\nREADME: " + "x" * 300


# --- stats ----------------------------------------------------------------

def test_stats_totals_and_per_extension_rows_sorted_by_lines(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "c.md").write_text("hello\nworld\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("license text\n", encoding="utf-8")
    (tmp_path / "img.bin").write_bytes(b"\x00\x01\x02\x03")
    assert repo_overview.stats(tmp_path).splitlines() == [
        "=== stats ===",
        "total  5 files  7 lines  45 B",
        ".py  2 files  4 lines  16 B",
        ".md  1 file  2 lines  12 B",
        "(none)  1 file  1 line  13 B",
        ".bin  1 file  0 lines  4 B",
    ]


def test_stats_truncates_to_top_15_extensions(tmp_path: Path) -> None:
    for i in range(17):
        (tmp_path / f"file{i}.ext{i:02d}").write_text("x\n", encoding="utf-8")
    lines = repo_overview.stats(tmp_path).splitlines()
    assert lines[0] == "=== stats ==="
    extension_rows = lines[2:-1]
    assert len(extension_rows) == 15
    assert extension_rows[0].startswith(".ext00 ") and extension_rows[-1].startswith(".ext14 ")
    assert lines[-1] == "[... 2 more extensions (top 15 shown)]"


# --- churn (git work trees only) ------------------------------------------

def test_churn_counts_commits_added_deleted_and_last_date(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=git_env())
    commit_file(tmp_path, "scripts/a.py", "print(1)\n", "2026-01-01T00:00:00+0000")
    commit_file(tmp_path, "scripts/a.py", "print(1)\nprint(2)\n", "2026-02-01T00:00:00+0000")
    commit_file(tmp_path, "scripts/b.py", "print('b')\n", "2026-03-01T00:00:00+0000")
    assert repo_overview.churn(tmp_path, 5).splitlines() == [
        "=== churn (3 commits scanned) ===",
        "  2 commits  +2/-0  2026-02-01  scripts/a.py",
        "  1 commit  +1/-0  2026-03-01  scripts/b.py",
    ]


def test_churn_skips_binary_numstat(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=git_env())
    commit_file(tmp_path, "scripts/a.py", "print(1)\n", "2026-01-01T00:00:00+0000")
    commit_file(tmp_path, "assets/logo.png", b"\x89PNG\x00\x01", "2026-01-02T00:00:00+0000")
    out = repo_overview.churn(tmp_path, 5)
    assert out.splitlines()[0] == "=== churn (2 commits scanned) ==="
    assert "logo.png" not in out
    assert "scripts/a.py" in out


def test_churn_truncates_to_top_n_and_notes_remainder(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=git_env())
    for i in range(3):
        commit_file(tmp_path, f"f{i}.py", f"x{i}\n", f"2026-01-0{i + 1}T00:00:00+0000")
    lines = repo_overview.churn(tmp_path, 2).splitlines()
    assert lines[0] == "=== churn (3 commits scanned) ==="
    assert len(lines) == 4
    assert lines[-1] == "[... 1 more files (--churn 2 shows the top 2)]"


def test_churn_since_filters_older_commits(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=git_env())
    commit_file(tmp_path, "old.py", "old\n", "2026-01-01T00:00:00+0000")
    commit_file(tmp_path, "new.py", "new\n", "2026-03-01T00:00:00+0000")
    out = repo_overview.churn(tmp_path, 5, since="2026-02-01")
    assert out.splitlines()[0] == "=== churn (1 commit scanned) ==="
    assert "new.py" in out and "old.py" not in out


def test_churn_outside_git_prints_one_line_note(tmp_path: Path) -> None:
    assert repo_overview.churn(tmp_path, 5) == "not a git work tree; skipping --churn"
    assert "=== churn" not in repo_overview.overview(tmp_path, churn_top=5)


def test_cli_stats_and_churn_flags(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=git_env())
    commit_file(tmp_path, "a.py", "x\n", "2026-01-01T00:00:00+0000")
    done = subprocess.run([sys.executable, "-S", str(SCRIPT), str(tmp_path), "--no-files", "--stats",
                          "--churn", "5"], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert "=== stats ===" in done.stdout
    assert "=== churn (1 commit scanned) ===" in done.stdout
    assert "a.py" in done.stdout
