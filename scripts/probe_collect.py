"""Collect passive survey counts from a live Playwright page into a probe snapshot.

Read-only. The page gets one fixed count script: it reads the DOM tree and open
shadow-root references and changes nothing. It calls no application functions and
does not click, type, scroll or navigate. Feed the result to probe_survey.summarize.

Limits, reported through the snapshot rather than hidden:
- Interactive elements are counted in the light DOM only. When any open shadow root
  exists, collection is "partial" because those elements were not counted.
- Closed shadow roots cannot be seen from the page, so they are never counted.
- Child frames are counted from the browser's frame list, not entered.
"""
from __future__ import annotations

from urllib.parse import urlsplit

INTERACTIVE_SELECTOR = (
    "a[href], button, input:not([type=hidden]), select, textarea, "
    "[role=button], [role=link], [role=checkbox], [role=textbox], [role=combobox], [contenteditable=true]"
)

# Read-only: querySelectorAll, the shadowRoot getter and tree traversal only.
COUNT_SCRIPT = """(selector) => {
  let shadow = 0;
  const visit = root => {
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) { shadow += 1; visit(el.shadowRoot); }
    }
  };
  visit(document);
  return {interactive: document.querySelectorAll(selector).length, shadow_roots: shadow};
}"""


def origin_of(url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


def collect(page):
    """Return a snapshot dict for probe_survey.summarize. The page must already be loaded."""
    counted = page.evaluate(COUNT_SCRIPT, INTERACTIVE_SELECTOR)
    shadow = counted["shadow_roots"]
    return {
        "origin": origin_of(page.url),
        "interactive": {
            "count": counted["interactive"],
            "collection": "partial" if shadow > 0 else "complete",
        },
        "shadow_roots": shadow,
        "frames": max(len(page.frames) - 1, 0),
    }
