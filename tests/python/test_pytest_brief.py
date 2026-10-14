"""pytest_brief: requirement parsing, missing-only install, and the kept summary lines."""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pytest_brief.py"
spec = importlib.util.spec_from_file_location("pytest_brief", SCRIPT)
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)


def test_requirement_names_ignore_comments_options_and_markers():
    text = "# c\npytest>=8\n-r other.txt\nPillow==12.3.0  # fixtures\npyyaml ; python_version>'3'\n\n"
    assert pb.requirement_names(text) == ["pytest", "Pillow", "pyyaml"]


def test_missing_reports_only_absent_distributions():
    assert pb.missing(["pytest", "surely-not-installed-xyz"]) == ["surely-not-installed-xyz"]
    assert pb.missing([]) == []


def test_brief_keeps_failures_coverage_and_summary():
    out = """....F
=========================== short test summary info ============================
FAILED tests/test_a.py::test_x - assert 1 == 2
Name        Stmts   Miss Branch BrPart  Cover   Missing
xprobe.py     560      4    296      3    99%   314
TOTAL         560      4    296      3    99%
Required test coverage of 90% reached. Total coverage: 99.18%
1 failed, 229 passed in 6.16s
"""
    assert pb.brief(out, 1, 5) == ["FAILED tests/test_a.py::test_x - assert 1 == 2",
                                   "TOTAL         560      4    296      3    99%",
                                   "Required test coverage of 90% reached. Total coverage: 99.18%",
                                   "1 failed, 229 passed in 6.16s"]


def test_brief_falls_back_to_tail_when_pytest_could_not_run():
    out = "ERROR: usage: python -m pytest\npython -m pytest: error: unrecognized arguments: --cov=x\n"
    assert pb.brief(out, 4, 1) == ["python -m pytest: error: unrecognized arguments: --cov=x"]


def test_cli_runs_a_project_and_returns_pytest_code(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "requirements.txt").write_text("pytest\n")
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n\ndef test_bad():\n    assert 1 == 2\n")
    done = subprocess.run([sys.executable, "-S", str(SCRIPT), "--", "-o", "addopts="], cwd=tmp_path,
                          capture_output=True, text=True)
    assert done.returncode == 1
    lines = done.stdout.strip().splitlines()
    assert lines[0].startswith("FAILED tests/test_ok.py::test_bad")
    assert lines[-1].startswith("1 failed, 1 passed") and "installed" not in done.stdout
    bad = subprocess.run([sys.executable, "-S", str(SCRIPT), "--requirements", "nope.txt"], cwd=tmp_path,
                         capture_output=True, text=True)
    assert bad.returncode == 3
