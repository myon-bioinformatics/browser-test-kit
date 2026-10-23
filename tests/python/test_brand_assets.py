"""Guard brand artwork by file hash, PNG header, documented homes and fixture icon links (stdlib only)."""
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "docs/assets/brand"
MANIFEST = json.loads((BRAND / "manifest.json").read_text(encoding="utf-8"))
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RGB_COLOR_TYPE = 2

# Reviewed derivative sources and sizes from PR #111. Pixel contents are checked by file hash only.
DERIVATIVE_SOURCES = {
    "fixtures/icons/favicon-16.png": ("docs/assets/brand/validation-buddy-favicon-source.png", (16, 16)),
    "fixtures/icons/favicon-32.png": ("docs/assets/brand/validation-buddy-favicon-source.png", (32, 32)),
    "fixtures/icons/favicon-64.png": ("docs/assets/brand/validation-buddy-favicon-source.png", (64, 64)),
    "fixtures/icons/apple-touch-icon.png": ("docs/assets/brand/camera-validation.png", (180, 180)),
}


def png_header(data):
    """Return (width, height, bit_depth, color_type) from the IHDR chunk."""
    if data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise AssertionError("not a PNG with an IHDR chunk")
    return struct.unpack(">IIBB", data[16:26])


def test_brand_source_and_crops():
    source_path = ROOT / MANIFEST["source"]
    source = source_path.read_bytes()
    assert sha256(source).hexdigest() == MANIFEST["source_sha256"]
    width, height, bit_depth, color_type = png_header(source)
    assert [width, height] == MANIFEST["source_size"] == [1080, 720]
    assert (bit_depth, color_type) == (8, RGB_COLOR_TYPE) and MANIFEST["source_mode"] == "RGB"
    for record in MANIFEST["crops"]:
        data = (ROOT / record["path"]).read_bytes()
        assert sha256(data).hexdigest() == record["sha256"]
        x1, y1, x2, y2 = record["crop_xyxy"]
        assert [x2 - x1, y2 - y1] == record["size"]
        assert list(png_header(data)[:2]) == record["size"]


def test_brand_derivatives_match_reviewed_files():
    records = MANIFEST["derivatives"]
    assert {record["path"] for record in records} == set(DERIVATIVE_SOURCES)
    assert len(records) == len(DERIVATIVE_SOURCES)
    crop_paths = {crop["path"] for crop in MANIFEST["crops"]}
    for record in records:
        source, size = DERIVATIVE_SOURCES[record["path"]]
        assert record["source"] == source
        assert tuple(record["size"]) == size
        assert source in crop_paths
        data = (ROOT / record["path"]).read_bytes()
        assert sha256(data).hexdigest() == record["sha256"]
        assert tuple(png_header(data)[:2]) == size


class IconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.in_head = False

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.in_head = True
        if tag == "link":
            attributes = dict(attrs)
            if attributes.get("rel") in ("icon", "apple-touch-icon"):
                assert self.in_head
                self.links.append(attributes)

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False


def test_fixture_icons_are_local_and_match_declared_dimensions():
    fixture = ROOT / "fixtures/index.html"
    parser = IconLinks()
    parser.feed(fixture.read_text(encoding="utf-8"))
    expected = {
        ("icon", "16x16", "icons/favicon-16.png"),
        ("icon", "32x32", "icons/favicon-32.png"),
        ("icon", "64x64", "icons/favicon-64.png"),
        ("apple-touch-icon", "180x180", "icons/apple-touch-icon.png"),
    }
    assert {(a["rel"], a["sizes"], a["href"]) for a in parser.links} == expected
    assert len(parser.links) == len(expected)
    for attrs in parser.links:
        data = (fixture.parent / attrs["href"]).read_bytes()
        width, height, _, _ = png_header(data)
        assert attrs["sizes"] == f"{width}x{height}"
        if attrs["rel"] == "icon":
            assert attrs["type"] == "image/png"


def test_each_large_mark_has_its_documented_home():
    assert 'src="docs/assets/brand/validation-buddy.png"' in (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'src="assets/brand/camera-validation.png"' in (ROOT / "docs/screenshot-evidence.md").read_text(encoding="utf-8")
    assert 'src="assets/brand/pipeline-hub.png"' in (ROOT / "docs/fast-init.md").read_text(encoding="utf-8")


def test_brand_validation_without_site_packages():
    result = subprocess.run(
        [sys.executable, "-S", str(Path(__file__).resolve())],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "4 asset checks passed without site packages"


if __name__ == "__main__":
    test_brand_source_and_crops()
    test_brand_derivatives_match_reviewed_files()
    test_fixture_icons_are_local_and_match_declared_dimensions()
    test_each_large_mark_has_its_documented_home()
    print("4 asset checks passed without site packages")
