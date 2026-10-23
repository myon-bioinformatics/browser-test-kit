"""Offline page-inspect operations: scores, addresses, pages, and the CLI."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("page_inspect", ROOT / "scripts" / "page_inspect.py")
page_inspect = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(page_inspect)


def element(name, **extra):
    raw = {
        "tag": "button", "role": "button", "name": name, "text": name, "id": "", "testid": "",
        "href": "", "visible": True, "enabled": True, "in_viewport": True, "obscured": False,
        "box": {"x": 1, "y": 2, "width": 30, "height": 16}, "parent_tag": "body", "css": "button",
        "id_unique": False, "testid_unique": False, "css_unique": False,
    }
    raw.update(extra)
    return raw


def snapshot_of(*items, total=None):
    raw = {"title": "Fixture", "child_frames": 0, "shadow_roots": False, "shadow_scan": "complete",
           "total": total if total is not None else len(items), "truncated": False, "elements": list(items)}
    return page_inspect.assemble_survey(
        raw, environment={"os": "Linux", "browser": "chromium", "version": "0", "channel": None,
                          "headless": True, "profile": "desktop", "viewport": {"width": 1280, "height": 800}},
        url="file:///fixture.html", start=0, limit=50,
    )


def test_similarity_is_the_shorter_string_ratio():
    assert page_inspect.lcs_length("save drft", "save draft") == 7
    assert page_inspect.lcs_length("", "abc") == 0
    assert page_inspect.lcs_length("abc", "xyz") == 0
    assert page_inspect.similarity("Save", "save draft") == 1
    assert page_inspect.similarity("save drft", "save draft") == page_inspect.round6(7 / 9)
    assert page_inspect.similarity("", "save") == 0
    assert page_inspect.lcs_length("a\U0001f600b", "a\U0001f600b") == 4
    assert page_inspect.similarity("\U0001f600", "x\U0001f600y") == 1


def test_addresses_prefer_stable_ids_and_number_duplicate_roles():
    survey = snapshot_of(
        element("Save draft", id="save-draft", testid="save-draft", id_unique=True, testid_unique=True, css="#save-draft", css_unique=True),
        element("Cancel"),
        element("Cancel"),
        element("Go", role="link", tag="a", href="https://example.test/docs"),
    )
    save, first, second, link = survey["elements"]
    assert save["address"] == "id:save-draft"
    assert save["locators"][0] == {"kind": "id", "selector": "#save-draft", "unique": True, "nth": None}
    assert first["address"] == "role:button/Cancel#0"
    assert second["address"] == "role:button/Cancel#1"
    assert link["address"].startswith("role:link/")
    assert survey["hint"].startswith("h:N is valid only") or "h:N is valid only" in survey["hint"]


def test_locate_pages_ranks_and_refuses_a_shared_top_score():
    elements = snapshot_of(
        element("Save draft", id="save-draft", id_unique=True, css="#save-draft", css_unique=True),
        element("Saved items", role="link", tag="a"),
        element("Search", role="searchbox", tag="input", id="q", id_unique=True, css="#q", css_unique=True),
    )["elements"]
    unique = page_inspect.locate(elements, query="Save draft", unique=True)
    assert unique["ok"] is True and unique["items"][0]["address"] == "id:save-draft"
    shared = page_inspect.locate(elements, query="Save", unique=True)
    assert shared["ok"] is False and shared["error"].startswith("more than one")
    assert {item["name"] for item in shared["suggestions"]} == {"Save draft", "Saved items"}
    missed = page_inspect.locate(elements, query="Save drft")
    assert missed["ok"] is False and missed["suggestions"][0]["name"] == "Save draft"
    page = page_inspect.locate(elements, query="", start=1, limit=1)
    assert page["pagination"] == {"start": 1, "limit": 1, "returned": 1, "total": 3, "next_start": 2}
    counted = page_inspect.count_elements(elements, role="button")
    assert counted["total"] == 1 and counted["by_role"] == {"button": 1}


def test_describe_accepts_common_target_forms_and_rejects_memory_addresses():
    elements = snapshot_of(
        element("Save draft", id="save-draft", testid="save-draft", id_unique=True, testid_unique=True, css="#save-draft", css_unique=True),
        element("Cancel"),
        element("Cancel"),
    )["elements"]
    for target in ("id:save-draft", "#save-draft", "save-draft", 'role=button[name="Save draft"]',
                   'getByRole("button", { name: "Save draft" })', 'button "Save draft"', "h:0"):
        found = page_inspect.describe_element(elements, target)
        assert found["ok"] is True and found["item"]["id"] == "save-draft", target
    second = page_inspect.describe_element(elements, "role:button/Cancel#1")
    assert second["ok"] is True and second["item"]["handle"] == "h:2"
    ambiguous = page_inspect.describe_element(elements, 'button "Cancel"')
    assert ambiguous["ok"] is False and len(ambiguous["suggestions"]) == 2
    with pytest.raises(page_inspect.InspectError) as raised:
        page_inspect.describe_element(elements, "0x401000")
    assert "memory addresses" in raised.value.error
    missing = page_inspect.describe_element(elements, "zzzz")
    assert missing["ok"] is False and missing["suggestions"] == []
    spaced = snapshot_of(element("Save draft"), element("Go \U0001f600", role="link", tag="a"))["elements"]
    assert spaced[0]["address"] == "role:button/Save%20draft#0"
    emoji = page_inspect.describe_element(spaced, spaced[1]["address"])
    assert emoji["ok"] is True and emoji["item"]["handle"] == "h:1"
    paged = page_inspect.normalize_elements(
        {"elements": [element("One"), element("Two"), element("Three")], "total": 3}, start=1, limit=1,
    )
    assert paged["truncated"] is True and paged["elements"][0]["handle"] == "h:1"


def test_option_names_are_not_abbreviated_and_do_not_swallow_the_next_flag():
    parser = page_inspect.build_parser()
    args = parser.parse_args(["survey", "page.html", "--browser", "firefox", "--json", "--limit", "2"])
    assert args.browser == "firefox" and args.json is True and args.limit == 2
    attached = parser.parse_args(["survey", "page.html", "--browser=webkit"])
    assert attached.browser == "webkit"
    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["survey", "page.html", "--brow", "firefox"])
    assert raised.value.code == 2


def test_context_options_drop_is_mobile_only_for_firefox():
    devices = {"iPhone 13": {"is_mobile": True, "has_touch": True, "viewport": {"width": 390, "height": 844}, "default_browser_type": "webkit"}}
    firefox = page_inspect.context_options(devices, "firefox", "iphone", False)
    webkit = page_inspect.context_options(devices, "webkit", "iphone", False)
    assert "is_mobile" not in firefox and firefox["has_touch"] is True
    assert webkit["is_mobile"] is True and "default_browser_type" not in webkit
    desktop = page_inspect.context_options(devices, "chromium", "desktop", False)
    assert desktop["viewport"] == {"width": 1280, "height": 800}


def test_cli_offline_commands_match_the_library(tmp_path: Path):
    survey = snapshot_of(
        element("Save draft", id="save-draft", id_unique=True, css="#save-draft", css_unique=True),
        element("Saved items", role="link", tag="a"),
    )
    path = tmp_path / "survey.json"
    path.write_text(page_inspect.dumps(survey), encoding="utf-8")
    script = ROOT / "scripts" / "page_inspect.py"

    def run(args):
        return subprocess.run([sys.executable, "-S", str(script), *args], cwd=tmp_path, capture_output=True, text=True, timeout=30)

    listed = run(["operations"])
    assert listed.returncode == 0 and "locate:" in listed.stdout
    found = run(["locate", str(path), "--query", "Save draft", "--unique", "--json"])
    assert found.returncode == 0
    assert json.loads(found.stdout)["items"][0]["address"] == "id:save-draft"
    shared = run(["locate", str(path), "--query", "Save", "--unique"])
    assert shared.returncode == 1 and "suggest:" in shared.stderr and shared.stdout == ""
    described = run(["describe", str(path), "--target", "id:save-draft", "--json"])
    body = json.loads(described.stdout)
    assert described.returncode == 0 and body["resolved_as"] == "id" and body["context"][0].startswith("* ")
    memory = run(["describe", str(path), "--target", "0x10", "--json"])
    assert memory.returncode == 2 and json.loads(memory.stdout)["stage"] == "input"
    missing = run(["locate", str(tmp_path / "missing.json"), "--query", "Save"])
    assert missing.returncode == 2 and "survey --out" in missing.stderr
    help_text = run(["--help"])
    assert help_text.returncode == 0 and "usage" in help_text.stdout.lower()


def test_urls_reject_credentials_and_non_http_schemes(tmp_path: Path):
    page = tmp_path / "page.html"
    page.write_text("<!DOCTYPE html><title>x</title>", encoding="utf-8")
    assert page_inspect.target_url(str(page)).startswith("file:")
    with pytest.raises(page_inspect.InspectError):
        page_inspect.target_url("https://user:secret" + chr(64) + "example.test/path")
    with pytest.raises(page_inspect.InspectError):
        page_inspect.target_url("javascript:alert(1)")


def test_collect_script_is_an_expression_beside_the_module():
    source = page_inspect.collect_source()
    assert source.lstrip().startswith("(options)")
    assert "querySelectorAll" in source
