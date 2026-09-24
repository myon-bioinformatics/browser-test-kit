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
