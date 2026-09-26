import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]

def test_browser_install_and_config_parity() -> None:
    config = (ROOT / "playwright.config.ts").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "playwright.yml").read_text(encoding="utf-8")
    engines = {"chromium", "firefox", "webkit"}
    assert engines <= set(re.findall(r"name: '(chromium|firefox|webkit)'", config))
    installs = re.findall(r"playwright install --with-deps ([^\n]+)", workflow)
    assert len(installs) == 2
    for line in installs:
        assert engines == set(line.strip().split())

def _evidence_expectations(workflow: str, directory: str) -> set[str]:
    match = re.search(rf"check_evidence\.py {re.escape(directory)} .*--expect ([\w,-]+)", workflow)
    assert match, f"no check_evidence.py step for {directory}"
    return set(match.group(1).split(","))

def test_evidence_expectations_match_the_test_matrices() -> None:
    config = (ROOT / "playwright.config.ts").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "playwright.yml").read_text(encoding="utf-8")
    assert _evidence_expectations(workflow, "test-results") == set(re.findall(r"name: '([^']+)'", config))
    smoke = ast.parse((ROOT / "tests" / "python" / "test_smoke.py").read_text(encoding="utf-8"))
    matrix = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in smoke.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"BROWSERS", "PROFILES"}
    }
    projects = {f"{browser}-{profile}" for browser in matrix["BROWSERS"] for profile, _ in matrix["PROFILES"]}
    assert _evidence_expectations(workflow, "test-results/python") == projects
