from pathlib import Path
import json
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (ROOT / "fixtures" / "index.html").resolve().as_uri()
RESULTS = ROOT / "test-results" / "python"
BROWSERS = ("chromium", "firefox", "webkit")
PROFILES = (("desktop", None), ("mobile", "iPhone 13"))

@pytest.mark.parametrize("browser_name", BROWSERS)
@pytest.mark.parametrize("profile,device_name", PROFILES)
def test_shared_fixture(browser_name: str, profile: str, device_name: str | None) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    png = RESULTS / f"{browser_name}-{profile}.png"
    meta = RESULTS / f"{browser_name}-{profile}.json"
    stage = "launch"
    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch()
        try:
            context_args = dict(pw.devices[device_name]) if device_name else {}
            context = browser.new_context(**context_args)
            page = context.new_page()
            stage = "navigate"
            page.goto(FIXTURE)
            stage = "assert"
            assert page.locator("#unicode").inner_text() == "日本語 / Unicode ✓ / 🧪"
            stage = "interact"
            page.locator("#name").fill("Python")
            page.locator("#submit").click()
            stage = "assert"
            assert page.locator("#result").inner_text() == "Hello, Python!"
            stage = "screenshot"
            page.screenshot(path=png, full_page=True)
            stage = "artifact"
            from scripts.check_png import dimensions
            width, height = dimensions(png.read_bytes())
            meta.write_text(json.dumps({"runtime":"python","browser":browser_name,"profile":profile,"stage":"complete","artifact":str(png.relative_to(ROOT)),"width":width,"height":height})+"\n", encoding="utf-8")
        except Exception:
            if 'page' in locals():
                page.screenshot(path=RESULTS / f"{browser_name}-{profile}-failure.png", full_page=True)
            raise
        finally:
            browser.close()
