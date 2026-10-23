import json
import subprocess
import sys
from pathlib import Path

import app_inspector

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def test_extract_app_facts_basic():
    raw = {
        "title": "My App",
        "url": "https://localhost:8080/app",
        "user_agent": "Mozilla/5.0",
        "viewport": {"width": 1024, "height": 768},
        "frameworks": ["React", "electron"],
        "electronAPI": True,
        "global_keys": ["customKey", "appState"],
    }
    facts = app_inspector.extract_app_facts(raw)
    assert facts["schema"] == "btk-app-inspector/1"
    assert facts["title"] == "My App"
    assert facts["url"] == "https://localhost:8080/app"
    assert facts["frameworks"] == ["electron", "react"]
    assert facts["is_electron"] is True
    assert facts["has_electron_api"] is True
    assert facts["global_keys"] == ["appState", "customKey"]


def test_build_browser_probe_script():
    js = app_inspector.build_browser_probe_script()
    assert "(function()" in js
    assert "btk-app-inspector/1" in js
    assert "frameworks.push('react')" in js


def test_diff_app_states():
    before = {
        "title": "My App",
        "url": "https://localhost/page1",
        "global_keys": ["a", "b"],
        "frameworks": ["react"],
    }
    after = {
        "title": "My App - Dashboard",
        "url": "https://localhost/page2",
        "global_keys": ["b", "c"],
        "frameworks": ["react", "electron"],
    }
    diff = app_inspector.diff_app_states(before, after)
    assert diff["schema"] == "btk-app-inspector/1"
    assert diff["has_changes"] is True
    assert diff["title_changed"] is True
    assert diff["url_changed"] is True
    assert diff["added_globals"] == ["c"]
    assert diff["removed_globals"] == ["a"]
    assert diff["added_frameworks"] == ["electron"]


def test_cli_main_probe_and_diff(tmp_path: Path):
    out_file = tmp_path / "probe.js"
    code = app_inspector.main(["--generate-probe-script", "--out", str(out_file)])
    assert code == 0
    assert "(function()" in out_file.read_text(encoding="utf-8")

    f1 = tmp_path / "s1.json"
    f2 = tmp_path / "s2.json"
    f1.write_text(json.dumps({"title": "A"}), encoding="utf-8")
    f2.write_text(json.dumps({"title": "B"}), encoding="utf-8")

    code_diff = app_inspector.main(["--diff", str(f1), str(f2)])
    assert code_diff == 1  # 1 indicates detected changes


def test_cli_main_python_m(tmp_path: Path):
    env = {"PYTHONPATH": str(SCRIPTS)}
    done = subprocess.run(
        [sys.executable, "-S", "-m", "app_inspector", "--generate-probe-script"],
        capture_output=True, text=True, env=env, timeout=10
    )
    assert done.returncode == 0
    assert "(function()" in done.stdout
