# Element Annotation Overlay, Highlight CSS, and TAP Assertions

`scripts/element_overlay.py` (Python stdlib-only) and `scripts/element_overlay.mjs` (Node ES module twin) provide target coordinate calculation, annotation overlay rendering, DOM highlight CSS generation, and Poku-style zero-dependency TAP element assertions.

It absorbs key capabilities from:
- **SeleniumBase & Midscene**: DOM element highlight CSS rules (`build_highlight_css`) for pre-screenshot visual indication.
- **Callstack agent-device & Midscene**: Bounding box target annotations (`[1]`, `[2]`, label badges, `x, y, w, h`, role, selector) and SVG overlay generation (`render_svg_overlay`).
- **Poku & PuppetSharp**: Zero-dependency TAP assertion formatting (`assert_elements`) and element trace digests.

## Python Command-Line Usage

```sh
# Annotate element coordinates and badges into JSON
python -S scripts/element_overlay.py --file elements.json --viewport 1280x720

# Filter elements by search query and generate SVG overlay diagram
python -S scripts/element_overlay.py --file elements.json --find "submit" --format svg --out overlay.svg

# Run zero-dependency TAP element assertions
python -S scripts/element_overlay.py --file elements.json --assert-role button --assert-min-count 1 --format tap

# Generate CSS highlight rules for pre-screenshot DOM injection
python -S scripts/element_overlay.py --file elements.json --format css --color "#ff0055"
```

## Python One-Liners (`python -m` / `python -c`)

```sh
# One-liner module CLI after installation
python -m element_overlay --file elements.json --format tap

# Python one-liner code snippet
python -c "import element_overlay; print(element_overlay.build_highlight_css(['#submit-btn', '.btn-primary']))"
```

## Node ES Module Usage (`scripts/element_overlay.mjs`)

```js
import { annotateElements, buildHighlightCss, renderSvgOverlay, assertElements } from './scripts/element_overlay.mjs';

const annotation = annotateElements(elements, { viewport: { width: 1280, height: 720 } });
const highlightCss = buildHighlightCss(['#btn-1', '#btn-2'], '#00ff00');
const svg = renderSvgOverlay(elements, { width: 800, height: 600 });
const tapResult = assertElements(elements, { min_count: 1, assert_role: 'button' });
```

## Evidence Schema (`btk-element-overlay/1`)

Output data adheres to schema `btk-element-overlay/1`:

```json
{
  "schema": "btk-element-overlay/1",
  "count": 1,
  "viewport": { "width": 1280, "height": 720 },
  "items": [
    {
      "index": 1,
      "label": "1",
      "name": "Submit Form",
      "role": "button",
      "selector": "#submit-btn",
      "x": 100.0,
      "y": 200.0,
      "width": 120.0,
      "height": 40.0,
      "cx": 160.0,
      "cy": 220.0,
      "clipped": false
    }
  ]
}
```
