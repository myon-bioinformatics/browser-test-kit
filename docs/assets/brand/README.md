# Browser Test Kit artwork

These assets are cropped from the project owner's supplied concept sheet. The
artwork, colors, rounded tiles, and opaque backgrounds are preserved. The three
large marks serve different roles rather than competing for one display slot:

- **Validation Buddy (A):** the main repository README illustration. Its simplified
  face-only mark is used for the existing fixture's 16, 32, and 64 px browser-tab
  icons, where a clear silhouette is more useful than a detailed diagram.
- **Camera Validation (B):** the screenshot-evidence documentation mark. A square,
  padded 180 px derivative is linked as the existing fixture's Apple touch icon.
  This is icon metadata only, not a PWA, an installability claim, or an Apple-device
  validation result.
- **Pipeline Hub (C):** the Fast Init execution-lanes illustration. It is a pipeline
  symbol, not the complete technical architecture or proof of supported lanes.
  The documentation and tested matrix remain the source of truth.

No GitHub account avatar or repository settings are changed. The supplied sheet's
"Repository Icon" caption describes an artwork use case, not an account action.

## Files and provenance

`source-sheet.png` is the original 1080 × 720 RGB PNG, retained without byte changes.
`manifest.json` records its SHA-256, the lossless crop rectangles, resulting sizes,
and hashes for every output. Crop coordinates use Pillow's `(left, top, right,
bottom)` convention, with right/bottom exclusive. Crops are saved as RGB PNGs;
no background removal, redrawing, or generated details are applied.

The three `*-favicon-source.png` files preserve the sheet's largest simplified
favicon designs at their actual sheet-pixel dimensions. The size captions in the
sheet are intended use sizes, not exact pixel measurements of those drawings.
Camera and pipeline favicon alternatives are retained for future use; the existing
fixture currently uses Validation Buddy consistently across all tab sizes.

To reproduce the crops, open `source-sheet.png` with Pillow and call `crop()` with
each recorded rectangle, then save as PNG. To reproduce derived icons:

1. Resize `validation-buddy-favicon-source.png` to 16 × 16, 32 × 32, and 64 × 64
   using `Image.Resampling.LANCZOS`.
2. Paste the unscaled 195 × 212 camera crop at `(8, 0)` on a white RGB 212 × 212
   canvas, then resize that canvas to 180 × 180 with the same filter.

Only these derivative files were resampled when the artwork was prepared. The
Pillow instructions above document that authoring procedure, not a runtime or
development dependency. Do not regenerate the reviewed PNGs during tests.

`tests/python/test_brand_assets.py` checks encoded file hashes, PNG header dimensions and color type, the manifest's crop and derivative records, documentation references, and fixture icon links. It does not decode pixels, so it cannot confirm that the crops or derivatives match the source pixels. Review the artwork by eye before intentionally updating hashes.

PNG encoding may vary across authoring-tool versions, so review the artwork
before intentionally updating hashes.

All fixture icon paths are relative to `fixtures/index.html`, so they work for the
existing local-file example as well as a locally served repository. No network
request to an external asset host is introduced, and the fixture's visible body,
styles, controls, and script are unchanged.
