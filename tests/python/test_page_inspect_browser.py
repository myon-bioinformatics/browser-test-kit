"""Real survey, locate, and describe runs through the CLI on three engines."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "page_inspect.html"
SCRIPT = ROOT / "scripts" / "page_inspect.py"
RESULTS = ROOT / "test-results" / "page-inspect"
BROWSERS = ("chromium", "firefox", "webkit")


def notice(capsys, title, text):
    if os.environ.get("GITHUB_ACTIONS"):
        with capsys.disabled():
            print(f"\n::notice title={title}::{text[:900]}", flush=True)


def run(args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


def names(survey):
    return [element["name"] for element in survey["elements"]]


def survey(browser, profile, out, extra=()):
    command = ["survey", str(FIXTURE), "--browser", browser, "--profile", profile, "--json", "--out", str(out), *extra]
    done = run(command)
    assert done.returncode == 0, done.stderr
    payload = json.loads(done.stdout)
    assert json.loads(out.read_text(encoding="utf-8"))["total"] == payload["total"]
    return payload


def test_desktop_survey_locates_the_same_controls(browser_name, capsys):
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{browser_name}-desktop.json"
    payload = survey(browser_name, "desktop", out)
    found = names(payload)
    assert payload["schema"] == "btk-page-survey/1" and payload["ok"] is True
    assert payload["environment"]["browser"] == browser_name
    assert payload["environment"]["profile"] == "desktop" and payload["environment"]["headless"] is True
    assert payload["environment"]["os"] in {"Linux", "macOS", "Windows"}
    assert payload["environment"]["version"]
    for expected in ("Save draft", "Cancel", "Documentation", "Saved items", "Search", "Remember me", "Unavailable"):
        assert expected in found, found
    assert found.count("Cancel") == 2
    for absent in ("Secret", "Also hidden", "Inside shadow", "Child frame"):
        assert absent not in found
    assert payload["child_frames"] >= 1 and payload["shadow_roots"] is True
    save = next(element for element in payload["elements"] if element["name"] == "Save draft")
    assert save["address"] == "id:save-draft"
    assert all(isinstance(save["box"][key], int) for key in ("x", "y", "width", "height"))
    unavailable = next(element for element in payload["elements"] if element["name"] == "Unavailable")
    assert unavailable["enabled"] is False and unavailable["visible"] is True
    located = run(["locate", str(out), "--query", "Save draft", "--unique", "--json"])
    assert located.returncode == 0 and json.loads(located.stdout)["items"][0]["address"] == "id:save-draft"
    ambiguous = run(["locate", str(out), "--query", "Cancel", "--unique", "--json"])
    assert ambiguous.returncode == 1 and json.loads(ambiguous.stdout)["ok"] is False
    described = run(["describe", str(out), "--target", "id:save-draft", "--json"])
    body = json.loads(described.stdout)
    assert described.returncode == 0 and body["item"]["testid"] == "save-draft" and any(line.startswith("* ") for line in body["context"])
    counted = run(["count", str(out), "--role", "button", "--json"])
    assert counted.returncode == 0 and json.loads(counted.stdout)["by_role"]["button"] >= 4
    notice(capsys, f"page-inspect {browser_name}", f"elements={payload['total']} save={save['address']} frames={payload['child_frames']}")


def test_hidden_controls_stay_out_until_requested(capsys):
    RESULTS.mkdir(parents=True, exist_ok=True)
    shown = survey("chromium", "desktop", RESULTS / "chromium-shown.json")
    hidden = survey("chromium", "desktop", RESULTS / "chromium-hidden.json", ("--include-hidden",))
    assert "Secret" not in names(shown) and "Also hidden" not in names(shown)
    assert "Secret" in names(hidden) and "Also hidden" in names(hidden)
    assert "Inside shadow" not in names(hidden)
    notice(capsys, "page-inspect hidden", f"shown={shown['total']} hidden={hidden['total']}")


def test_iphone_profile_launches_on_chromium_and_firefox(browser_name, capsys):
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = survey(browser_name, "iphone", RESULTS / f"{browser_name}-iphone.json")
    assert payload["environment"]["profile"] == "iphone"
    assert payload["environment"]["viewport"]["width"] == 390
    assert next(element["address"] for element in payload["elements"] if element["name"] == "Save draft") == "id:save-draft"
    notice(capsys, f"page-inspect {browser_name} iphone", f"elements={payload['total']} width=390")


test_desktop_survey_locates_the_same_controls = pytest.mark.browser(
    pytest.mark.parametrize("browser_name", BROWSERS)(test_desktop_survey_locates_the_same_controls)
)
test_hidden_controls_stay_out_until_requested = pytest.mark.browser(test_hidden_controls_stay_out_until_requested)
test_iphone_profile_launches_on_chromium_and_firefox = pytest.mark.browser(
    pytest.mark.parametrize("browser_name", ("chromium", "firefox"))(test_iphone_profile_launches_on_chromium_and_firefox)
)
