from pathlib import Path
import importlib.util
import json
import sys
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (ROOT / "fixtures" / "index.html").resolve().as_uri()
RESULTS = ROOT / "test-results" / "python"
BROWSERS = ("chromium", "firefox", "webkit")
PROFILES = (("desktop", None), ("mobile", "iPhone 13"))

_spec = importlib.util.spec_from_file_location("check_png", ROOT / "scripts" / "check_png.py")
_check_png = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(_check_png)

def build_context_args(pw, browser_name: str, device_name: str | None) -> dict:
    if not device_name:
        return {}
    args = dict(pw.devices[device_name])
    if browser_name == "firefox":
        args.pop("is_mobile", None)
    return args

@pytest.mark.parametrize("browser_name", BROWSERS)
@pytest.mark.parametrize("profile,device_name", PROFILES)
def test_shared_fixture(browser_name: str, profile: str, device_name: str | None) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    png = RESULTS / f"{browser_name}-{profile}.png"
    meta = RESULTS / f"{browser_name}-{profile}.json"
    stage = "launch"
    page = None
    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch()
        try:
            ctx_args = build_context_args(pw, browser_name, device_name)
            context = browser.new_context(**ctx_args)
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
            width, height = _check_png.dimensions(png.read_bytes())
            meta.write_text(json.dumps({"runtime":"python","browser":browser_name,"profile":profile,"emulation":"partial" if browser_name=="firefox" and profile=="mobile" else "full","stage":"complete","artifact":str(png.relative_to(ROOT)),"width":width,"height":height})+"\n", encoding="utf-8")
        except Exception as exc:
            meta.write_text(json.dumps({"runtime":"python","browser":browser_name,"profile":profile,"stage":stage,"error":type(exc).__name__,"message":str(exc)[:500]})+"\n", encoding="utf-8")
            if page is not None:
                try:
                    page.screenshot(path=RESULTS / f"{browser_name}-{profile}-failure.png", full_page=True)
                except Exception as evidence_exc:
                    print(f"warning: failure screenshot unavailable: {type(evidence_exc).__name__}: {evidence_exc}", file=sys.stderr)
            raise
        finally:
            browser.close()
