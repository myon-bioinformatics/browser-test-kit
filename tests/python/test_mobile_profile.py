import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("smoke", ROOT / "tests" / "python" / "test_smoke.py")
smoke = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(smoke)

class FakePW:
    devices = {"iPhone 13": {"is_mobile": True, "has_touch": True, "viewport": {"width": 390, "height": 844}}}

def test_firefox_drops_unsupported_is_mobile_only() -> None:
    args = smoke.build_context_args(FakePW(), "firefox", "iPhone 13")
    assert "is_mobile" not in args
    assert args["has_touch"] is True
    assert args["viewport"] == {"width": 390, "height": 844}

def test_webkit_keeps_is_mobile() -> None:
    assert smoke.build_context_args(FakePW(), "webkit", "iPhone 13")["is_mobile"] is True
