"""Guard source-preserving branding and relative fixture icon references."""
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "docs/assets/brand"
MANIFEST = json.loads((BRAND / "manifest.json").read_text(encoding="utf-8"))


def test_brand_source_and_lossless_crops():
    source_path = ROOT / MANIFEST["source"]
    assert sha256(source_path.read_bytes()).hexdigest() == MANIFEST["source_sha256"]
    with Image.open(source_path) as source:
        assert list(source.size) == MANIFEST["source_size"] == [1080, 720]
        assert source.mode == MANIFEST["source_mode"] == "RGB"
        for record in MANIFEST["crops"]:
            path = ROOT / record["path"]
            assert sha256(path.read_bytes()).hexdigest() == record["sha256"]
            with Image.open(path) as actual:
                expected = source.crop(record["crop_xyxy"])
                assert actual.mode == expected.mode
                assert list(actual.size) == record["size"]
                assert actual.tobytes() == expected.tobytes()


def test_brand_derivatives_preserve_the_recorded_transform():
    for record in MANIFEST["derivatives"]:
        path = ROOT / record["path"]
        assert sha256(path.read_bytes()).hexdigest() == record["sha256"]
        with Image.open(ROOT / record["source"]) as source:
            if path.name == "apple-touch-icon.png":
                square = Image.new("RGB", (212, 212), "white")
                square.paste(source, (8, 0))
                expected = square.resize((180, 180), Image.Resampling.LANCZOS)
            else:
                expected = source.resize(tuple(record["size"]), Image.Resampling.LANCZOS)
            with Image.open(path) as actual:
                assert actual.mode == expected.mode
                assert list(actual.size) == record["size"]
                assert actual.tobytes() == expected.tobytes()


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
        path = fixture.parent / attrs["href"]
        with Image.open(path) as icon:
            assert icon.format == "PNG"
            assert attrs["sizes"] == f"{icon.width}x{icon.height}"
        if attrs["rel"] == "icon":
            assert attrs["type"] == "image/png"


def test_each_large_mark_has_its_documented_home():
    assert 'src="docs/assets/brand/validation-buddy.png"' in (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'src="assets/brand/camera-validation.png"' in (ROOT / "docs/screenshot-evidence.md").read_text(encoding="utf-8")
    assert 'src="assets/brand/pipeline-hub.png"' in (ROOT / "docs/fast-init.md").read_text(encoding="utf-8")
