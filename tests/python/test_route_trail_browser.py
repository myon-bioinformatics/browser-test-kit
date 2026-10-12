"""Walk an emoji trail in a real browser: each step's URL must show that page (hash routing)."""
import importlib.util
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("route_trail", ROOT / "scripts" / "route_trail.py")
route_trail = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(route_trail)


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_walk_trail(browser_name):
    registry = route_trail.load_registry((ROOT / "fixtures" / "route_trail_registry.json").read_text(encoding="utf-8"))
    base = (ROOT / "fixtures" / "route_trail.html").resolve().as_uri()
    steps = route_trail.resolve("🏠 → 🗺 → 🌍 ↔ 🕒", registry, base=base)
    seen = []
    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch()
        try:
            page = browser.new_page()
            for step in steps:
                page.goto(step["url"])
                seen.append(route_trail.norm(page.locator("#page").inner_text().split()[0]))
            # Hash-only steps stay in one document, as an in-app navigation would.
            visits = int(page.locator("#visits").inner_text())
        finally:
            browser.close()
    assert seen == [s["emoji"] for s in steps]
    assert visits == len(steps)
