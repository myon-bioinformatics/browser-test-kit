"""Real browsers exercise shared navigation, readiness and resumable execution."""
import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("route_trail", ROOT / "scripts" / "route_trail.py")
route_trail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route_trail)
BASE = (ROOT / "fixtures" / "route_trail_delayed.html").as_uri()


def registry():
    return route_trail.load_registry((ROOT / "fixtures" / "route_trail_execution.json").read_text())


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_walk_resume_and_failure(browser_name):
    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch()
        try:
            page = browser.new_page()
            iterator = route_trail.walk_steps(page, "@home → @hub → @world → @home", registry(), base=BASE)
            assert next(iterator)["index"] == 0
            page.evaluate("window.retained = 42")
            assert len(list(iterator)) == 3
            assert page.evaluate("window.retained") == 42
            assert page.locator("#visits").inner_text() == "4"
            bad = registry()
            bad["@hub"]["ready"]["text"] = "Never rendered"
            with pytest.raises(route_trail.TrailExecutionError) as err:
                route_trail.walk(page, "@home → @hub → @world", bad, base=BASE, timeout_ms=250)
            assert err.value.receipt["completed"] == 1
            assert err.value.receipt["error"]["phase"] == "ready"
            assert page.url.endswith("#/hub")
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_async_walk(browser_name):
    async def run():
        async with async_playwright() as pw:
            browser = await getattr(pw, browser_name).launch()
            try:
                page = await browser.new_page()
                async def check(page, step):
                    await asyncio.sleep(0)
                    assert await page.locator("#visits").inner_text() == str(step["index"] + 1)
                result = await route_trail.awalk(page, "@home ↔ @hub", registry(), base=BASE, check=check)
                assert result["ok"] and result["completed"] == 3
            finally:
                await browser.close()
    asyncio.run(run())


@pytest.mark.parametrize("backend", ("python", "python-async"))
def test_cli_run_from_stdlib_parent(backend):
    args = [sys.executable, "-S", str(ROOT / "scripts/route_trail.py"), "@home ↔ @hub",
            "--registry", str(ROOT / "fixtures/route_trail_execution.json"), "--base", BASE,
            "--run", "--backend", backend, "--json"]
    child = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stdout + child.stderr
    result = json.loads(child.stdout)
    assert result["ok"] and result["completed"] == 3
    assert all(s["verification"] == "url+marker" for s in result["steps"])
