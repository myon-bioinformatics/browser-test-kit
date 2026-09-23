from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (ROOT / "fixtures" / "index.html").resolve().as_uri()
BROWSERS = ("chromium", "firefox", "webkit")

@pytest.mark.parametrize("browser_name", BROWSERS)
def test_shared_fixture(browser_name: str, tmp_path: Path) -> None:
    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch()
        page = browser.new_page()
        page.goto(FIXTURE)
        assert "日本語" in page.locator("#unicode").inner_text()
        page.locator("#name").fill("Python")
        page.locator("#submit").click()
        assert page.locator("#result").inner_text() == "Hello, Python!"
        page.screenshot(path=tmp_path / f"python-{browser_name}.png", full_page=True)
        browser.close()
