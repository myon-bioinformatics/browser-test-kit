import importlib.util
from pathlib import Path
import struct
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_png", ROOT / "scripts" / "check_png.py")
check_png = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(check_png)

def test_png_header_dimensions() -> None:
    data = check_png.PNG + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 390, 844)
    assert check_png.dimensions(data) == (390, 844)

def test_rejects_non_png() -> None:
    with pytest.raises(ValueError, match="valid PNG"):
        check_png.dimensions(b"not an image")
