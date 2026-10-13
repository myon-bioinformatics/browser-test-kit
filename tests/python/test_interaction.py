"""Measured press and side-effect records: pure rules, CLI, and real browsers."""
import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("interaction", ROOT / "scripts" / "interaction.py")
interaction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(interaction)
URL = (ROOT / "fixtures" / "interaction.html").as_uri()
VIEW = {"width": 800, "height": 600}


def test_press_point_uses_integer_centre_and_viewport_ratio():
    assert interaction.press_point({"x": 40, "y": 10.25, "width": 161, "height": 47}, VIEW) == \
        {"x": 120, "y": 33, "visible_ratio": 1.0}
    half = {"x": 700, "y": 0, "width": 200, "height": 10}
    assert interaction.press_point(half, VIEW, ratio=0.5)["visible_ratio"] == 0.5
    with pytest.raises(ValueError, match="0.50 in the viewport"):
        interaction.press_point(half, VIEW)
    for box in (None, {"x": 0, "y": 0, "width": 0, "height": 5}):
        with pytest.raises(ValueError, match="no layout box"):
            interaction.press_point(box, VIEW)
    with pytest.raises(ValueError, match="ratio"):
        interaction.press_point(half, VIEW, ratio=0)


def _side(quiet, **extra):
    record = {"schema": "side-effects/1", "quiet": quiet, "requests": [], "dialogs": [], "page_errors": [],
              "popups": [], "storage": {"before": {"local": 0, "session": 0}, "after": {"local": 0, "session": 0}}}
    record.update(extra)
    return record


def test_cli_check_is_assert_late(tmp_path):
    press = {"schema": "pointer-press/1", "input": "mouse", "input_source": "explicit", "x": 1, "y": 2,
             "visible_ratio": 1.0, "box": {}, "hit": {"tag": "div", "self": False}}
    good = tmp_path / "good.jsonl"
    good.write_text("\n".join(json.dumps(r) for r in (press, _side(True))), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([_side(False, requests=["http://x.invalid/"])]), encoding="utf-8")
    junk = tmp_path / "junk.json"
    junk.write_text(json.dumps({"schema": "other"}), encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, "-S", str(ROOT / "scripts" / "interaction.py"), "check", *a],
                                    capture_output=True, text=True)
    done = run(str(good))
    assert done.returncode == 0 and "self=False" in done.stdout and "PASS 2 records" in done.stdout
    done = run(str(bad), "--json")
    assert done.returncode == 1 and json.loads(done.stdout)["lines"] == ["0 side-effects NOT QUIET: requests"]
    assert run(str(junk)).returncode == 2


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_press_reaches_coordinate_hit_target_and_watch_records(browser_name):
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch()
        try:
            page = browser.new_page(viewport=VIEW)
            page.goto(URL)
            target, log = page.locator("#target"), page.locator("#log")
            # Actionability sees the pane on top: the DOM click path cannot work.
            with pytest.raises(PlaywrightError):
                target.click(timeout=500)
            record = interaction.press(page, target, touch=False)
            # Annotation for CI when this fails (job logs may be unreadable from agents).
            print(f"::notice title=interaction {browser_name}::press {json.dumps(record)} log={log.inner_text()!r}")
            assert log.inner_text() == "pressed 1 mouse"
            assert record["hit"] == {"tag": "div", "self": False}
            assert record["visible_ratio"] == 1.0 and isinstance(record["x"], int) and record["input_source"] == "explicit"
            # A synthetic DOM click "passes" through a path no real input can take.
            target.evaluate("el => el.click()")
            assert log.inner_text() == "synthetic"

            page.goto(URL)
            w = interaction.watch(page)
            page.locator("#quiet").click()
            assert w.stop()["quiet"] is True
            w = interaction.watch(page)
            page.locator("#noisy").click()
            page.wait_for_timeout(200)
            report = w.stop()
            print(f"::notice title=interaction {browser_name}::watch {json.dumps(report)}")
            assert report["quiet"] is False
            assert report["dialogs"] == [{"type": "alert", "message": "noisy"}]
            assert "http://side-effect.invalid/beacon" in report["requests"]
            assert len(report["page_errors"]) == 1 and "noisy error" in report["page_errors"][0]

            # Same key, same value length: only the content fingerprint can change.
            page.goto(URL)
            w = interaction.watch(page)
            page.locator("#overwrite").click()
            report = w.stop()
            before, after = report["storage"]["before"], report["storage"]["after"]
            assert before["local"] is not None and after["local"]["keys"] == before["local"]["keys"]
            assert after["local"]["fingerprint"] != before["local"]["fingerprint"]
            assert after["session"] == before["session"]
            assert report["quiet"] is False and "bbbb" not in json.dumps(report)
        finally:
            browser.close()


def test_async_press_and_watch_chromium():
    from playwright.async_api import async_playwright

    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEW, has_touch=True)
                await page.goto(URL)
                w = await interaction.awatch(page)
                record = await interaction.apress(page, page.locator("#target"))
                assert record["input"] == "touch" and record["input_source"] == "navigator.maxTouchPoints"
                assert await page.locator("#log").inner_text() == "pressed 1 touch"
                await page.locator("#noisy").evaluate("el => el.click()")
                await page.wait_for_timeout(200)
                report = await w.stop()
                assert report["dialogs"] == [{"type": "alert", "message": "noisy"}]
                assert report["quiet"] is False
                w = await interaction.awatch(page)
                await page.locator("#overwrite").evaluate("el => el.click()")
                report = await w.stop()
                assert report["quiet"] is False
                assert report["storage"]["after"]["local"]["fingerprint"] != report["storage"]["before"]["local"]["fingerprint"]
            finally:
                await browser.close()

    asyncio.run(run())


def test_node_and_python_share_the_page_functions():
    mjs = (ROOT / "scripts" / "interaction.mjs").read_text(encoding="utf-8")
    assert interaction._STORAGE in mjs and interaction._INVENTORY in mjs
    assert f"INVENTORY_SELECTOR = '{interaction.INVENTORY_SELECTOR}'" in mjs


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_inventory_shows_merged_card_and_field_press(browser_name):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch()
        try:
            page = browser.new_page(viewport=VIEW)
            page.goto(URL)
            listed = interaction.inventory(page, selector='[role="button"], [role="combobox"]', limit=1)
            assert listed["truncated"] is True and len(listed["elements"]) == 1
            listed = interaction.inventory(page, selector='[role="button"], [role="combobox"]')
            card = next(e for e in listed["elements"] if e["aria_label"] == "Door card")
            field = next(e for e in listed["elements"] if e["id"] == "door-field")
            assert card["box"]["height"] > 3 * field["box"]["height"] and card["in_viewport"]
            # Raw attribute, not the accessible name: Playwright still names this button "quiet".
            quiet = interaction.inventory(page, selector="#quiet")["elements"][0]
            assert (quiet["role"], quiet["aria_label"], quiet["text"]) == (None, None, "quiet")
            assert page.get_by_role("button", name="quiet").count() == 1
            interaction.press(page, page.get_by_role("button", name="Door card"), touch=False)
            assert page.locator("#log").inner_text() == "card body"
            interaction.press(page, page.get_by_test_id("door-field"), touch=False)
            assert page.locator("#log").inner_text() == "field opened"
        finally:
            browser.close()
