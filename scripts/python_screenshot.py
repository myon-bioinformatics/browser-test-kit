#!/usr/bin/env python3
"""Small Python CLI reference: screenshot a URL with a selected Playwright engine."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("output", type=Path)
    p.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = getattr(pw, args.browser).launch()
        page = browser.new_page()
        page.goto(args.url)
        page.screenshot(path=args.output, full_page=True)
        browser.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
