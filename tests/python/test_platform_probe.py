"""platform_probe offline: width search, verdict, dataset merge, summary gate, viewer HTML."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("platform_probe", ROOT / "scripts" / "platform_probe.py")
pp = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(pp)


def record(os_="Linux", browser="chromium", profile="desktop", headless=True, ok=True, click=True, channel=None):
    env = {"os": os_, "os_release": "x", "runner_image": None, "browser": browser, "channel": channel,
           "browser_version": "1.0", "profile": profile, "device": "Desktop", "headless": headless}
    env["id"] = pp.env_id(env)
    r = {"schema": pp.FACTS_SCHEMA, "env": env,
         "facts": {"window": {"frame_width": 0, "frame_height": 0}, "viewport": {"scrollbar_width": 0, "device_pixel_ratio": 1}},
         "layout": {"ok": ok, "failed": [] if ok else ["toolbar_clipped"]},
         "click": {"ok": click, "count": int(click), "input": "mouse", "point": [1, 2]}, "min_ok_width": 300}
    r["verdict"] = pp.verdict(r)
    return r


@pytest.mark.parametrize("threshold", [240, 241, 266, 407, 1279, 1280])
def test_narrowest_ok_width_matches_a_linear_scan_with_few_probes(threshold):
    calls = []

    def ok_at(width):
        calls.append(width)
        return width >= threshold
    assert pp.narrowest_ok_width(ok_at, 240, 1280) == threshold
    assert len(calls) <= 13  # log2(1040) + the two ends


def test_narrowest_ok_width_none_when_even_the_full_width_fails():
    assert pp.narrowest_ok_width(lambda w: False, 240, 1280) is None


def test_verdict_needs_layout_and_click():
    assert record()["verdict"] == "pass"
    assert record(ok=False)["verdict"] == "fail"
    assert record(click=False)["verdict"] == "fail"


def test_env_id_uses_channel_and_mode():
    assert record(channel="msedge", headless=False)["env"]["id"] == "Linux-msedge-desktop-headed"


def test_merge_dedupes_by_env_and_accepts_datasets(tmp_path):
    a, b = record(), record(os_="Windows")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "a.json").write_text(json.dumps(a))
    (tmp_path / "runs" / "dup.json").write_text(json.dumps(a))
    (tmp_path / "other.json").write_text(json.dumps({"schema": "something-else"}))
    dataset = tmp_path / "d.json"
    dataset.write_text(json.dumps({"schema": pp.DATASET_SCHEMA, "records": [b]}))
    records = pp.load_records([str(tmp_path / "runs"), str(dataset), str(tmp_path / "other.json")])
    assert [r["env"]["id"] for r in records] == ["Linux-chromium-desktop-headless", "Windows-chromium-desktop-headless"]


def test_summary_gate_and_cli(tmp_path, capsys):
    (tmp_path / "ok.json").write_text(json.dumps(record()))
    assert pp.main(["summary", str(tmp_path)]) == 0
    (tmp_path / "ng.json").write_text(json.dumps(record(os_="macOS", ok=False)))
    assert pp.main(["summary", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "fail macOS-chromium-desktop-headless" in out and "failed=toolbar_clipped" in out
    assert pp.main(["summary", str(tmp_path / "missing")]) == 2
    assert pp.main(["collect", "--browser", "firefox", "--channel", "chrome", "--out", str(tmp_path)]) == 2


def test_render_embeds_data_safely(tmp_path):
    hostile = record()
    hostile["facts"]["platform"] = {"ua": "</script><script>alert(1)</script>"}
    page = pp.render([hostile, record(browser="webkit")])
    assert "</script><script>alert(1)" not in page and "\\u003c/script>" in page
    data = page.split('<script type="application/json" id="data">')[1].split("</script>")[0]
    assert len(json.loads(data)["records"]) == 2


def test_merge_and_render_create_the_output_directory(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps(record()))
    assert pp.main(["merge", str(tmp_path / "r.json"), "--out", str(tmp_path / "new" / "dataset.json")]) == 0
    assert pp.main(["render", str(tmp_path / "new" / "dataset.json"), "--out", str(tmp_path / "x" / "index.html")]) == 0
    assert (tmp_path / "x" / "index.html").read_text(encoding="utf-8").startswith("<!doctype html>")


def test_errors_become_actions_annotations(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert pp.main(["summary", str(tmp_path)]) == 2
    assert "::error title=platform_probe summary::ValueError" in capsys.readouterr().out
