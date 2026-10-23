"""ControlOrMeta resolution, ported from Playwright's resolveSmartModifierString (offline)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import page_inspect  # noqa: E402


def test_control_or_meta_is_control_off_macos_and_meta_on_macos():
    assert page_inspect.resolve_smart_key("ControlOrMeta", "linux") == "Control"
    assert page_inspect.resolve_smart_key("ControlOrMeta", "win32") == "Control"
    assert page_inspect.resolve_smart_key("ControlOrMeta", "darwin") == "Meta"


def test_chords_resolve_each_part_and_leave_other_keys_alone():
    assert page_inspect.resolve_smart_key("ControlOrMeta+A", "linux") == "Control+A"
    assert page_inspect.resolve_smart_key("Shift+ControlOrMeta+Enter", "darwin") == "Shift+Meta+Enter"
    assert page_inspect.resolve_smart_key("Enter", "linux") == "Enter"
    assert page_inspect.resolve_smart_key("+", "linux") == "+"
    assert page_inspect.resolve_smart_key("Control+A", "darwin") == "Control+A"


def test_default_platform_follows_sys_platform():
    expected = "Meta" if sys.platform == "darwin" else "Control"
    assert page_inspect.resolve_smart_key("ControlOrMeta") == expected


def test_page_keyboard_press_does_not_take_a_timeout():
    source = (ROOT / "scripts" / "page_inspect.py").read_text(encoding="utf-8")
    assert "page.keyboard.press(text, timeout=" not in source
    assert "page.keyboard.press(text)" in source
    assert "target.press(text, timeout=timeout_ms)" in source
