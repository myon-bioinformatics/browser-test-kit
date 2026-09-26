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


def test_key_files_then_file_list_without_dependency_or_result_dirs(tmp_path: Path) -> None:
    make_tree(tmp_path)
    out = repo_overview.overview(tmp_path)
    headers = [line for line in out.splitlines() if line.startswith("=== ")]
    assert headers == [
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
    assert done.stdout.startswith("=== README.md (")
    assert "=== playwright.config.ts (" in done.stdout and "=== files (" in done.stdout
    missing = subprocess.run([sys.executable, "-S", str(SCRIPT), str(ROOT / "nope")], capture_output=True, text=True)
    assert missing.returncode == 2
