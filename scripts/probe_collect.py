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

import argparse
import json
import sys
from urllib.parse import urlsplit

from probe_survey import summarize

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


def main(argv=None):
    """CLI: probe one URL and print a btk-probe-evidence/1 envelope as JSON.

    Exit 0 OK; 2 input or browser error. Credentials, paths and non-HTTP(S) URLs are refused
    before a browser starts.
    """
    parser = argparse.ArgumentParser(description="Probe one page passively and print evidence JSON.")
    parser.add_argument("url")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args(argv)
    parts = urlsplit(args.url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        print("probe_collect: an http(s) URL without credentials is required", file=sys.stderr)
        return 2
    if args.timeout_ms < 1:
        print("probe_collect: --timeout-ms must be positive", file=sys.stderr)
        return 2
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True, timeout=args.timeout_ms)
            try:
                page = browser.new_page()
                page.goto(args.url, wait_until="load", timeout=args.timeout_ms)
                evidence = summarize(collect(page))
            finally:
                browser.close()
    except Exception as exc:  # browser or navigation failure is reported, not a traceback
        print(f"probe_collect: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
