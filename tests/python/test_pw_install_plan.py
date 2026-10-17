"""pw_install_plan: per-job install recommendation from configs and later commands."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pw_install_plan", ROOT / "scripts" / "pw_install_plan.py")
pip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pip)

WORKFLOW = """name: x
jobs:
  tests:
    steps:
      - run: npx playwright install --with-deps chromium firefox
      - run: npx playwright test
  shots:
    steps:
      - run: npx playwright install --with-deps --only-shell chromium
      - run: npx playwright screenshot --browser=chromium http://x a.png
  py:
    steps:
      - run: python -m playwright install --with-deps chromium
      - run: python -m pytest
"""


def repo(tmp_path, config):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(WORKFLOW)
    (tmp_path / "playwright.config.js").write_text(config)
    return tmp_path


def test_channel_chromium_needs_full_build_only_where_the_config_is_used(tmp_path):
    rows = pip.plan(str(repo(tmp_path, "use: { channel: 'chromium' }, projects: [{ use: devices['Desktop Chrome'] }]")))
    by_line = {where: (state, text) for state, where, text in rows if state != "warn"}
    assert by_line[".github/workflows/ci.yml:5"] == ("suggest", "add --no-shell (playwright.config.js uses channel 'chromium')")
    assert by_line[".github/workflows/ci.yml:9"][0] == "ok"
    assert by_line[".github/workflows/ci.yml:13"] == ("suggest", "add --only-shell (job runs headless only)")
    assert ("warn", ".github/workflows/ci.yml:5", "installs firefox but no config project uses it") in rows


def test_headless_config_suggests_only_shell_and_cli(tmp_path, capsys):
    root = repo(tmp_path, "projects: [{ name: 'chromium' }, { name: 'firefox' }]")
    rows = pip.plan(str(root))
    assert rows[0] == ("suggest", ".github/workflows/ci.yml:5", "add --only-shell (job runs headless only)")
    assert pip.main([str(root)]) == 1
    assert pip.main([str(tmp_path / "nope")]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert pip.main([str(empty)]) == 0 and "no playwright install lines" in capsys.readouterr().out
