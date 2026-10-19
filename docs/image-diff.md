# image_diff.py

Compare two screenshots (`PATH` or `ZIP::member`) and print one line: size, changed pixels, bbox, max channel delta.

Canonical implementation lives in this repository (`scripts/image_diff.py`). Pillow is the only runtime dependency and is imported lazily when diffing; without it the CLI exits `2` with an install hint. The tool is not part of the stdlib-only vendor catalog (`vendor.lock.json`).

```bash
pip install pillow   # or: pip install browser-test-kit-tools[image]
python scripts/image_diff.py a.png b.png [--clip X,Y,W,H] [--viewport-width CSS_PX] [--tolerance N]
```

Exit `0` = identical within tolerance, `1` = differs, `2` = input error or missing Pillow.

See also [screenshot-evidence.md](screenshot-evidence.md) for how this fits next to `check_png.py` and receipt validators.

## Regression tests

Install test dependencies (`uv run --locked` includes Pillow) and run:

```bash
uv run --locked python -m pytest tests/python/test_browser_test_kit_image_diff.py
```

The test module imports Pillow directly so a missing dependency fails collection instead of skipping regressions. Runtime imports remain lazy; the missing-Pillow exit-2 diagnostic is tested separately by blocking PIL imports.

Downstream consumers (for example Flutter) may vendor a fixed copy of `scripts/image_diff.py` with provenance metadata. That adoption path does not enroll the script in `vendor.lock.json`; update vendored copies from reviewed merges of this repository.
