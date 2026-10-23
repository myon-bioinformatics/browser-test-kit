#!/usr/bin/env python3
"""Electron & browser app state inspection, probe snippet generation, and state diffing.

Provides zero-dependency inspection helpers and JS probe generation for reverse-engineering
and inspecting Electron, React, or browser applications across Python and Node.

Stdlib-only; runs under ``python -S``::

    python -S scripts/app_inspector.py --generate-probe-script --out probe.js
    python -S scripts/app_inspector.py --diff state1.json state2.json
    python -c "import app_inspector; print(app_inspector.build_browser_probe_script())"

Exit codes: 0 OK; 1 state diff detected changes; 2 usage or input error.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Union

SCHEMA = "btk-app-inspector/1"

PROBE_SCRIPT_JS = """(function() {
  var globalKeys = [];
  try {
    for (var k in window) {
      if (Object.prototype.hasOwnProperty.call(window, k) && !k.startsWith('__')) {
        globalKeys.push(k);
      }
    }
  } catch(e) {}

  var frameworks = [];
  if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__ || document.querySelector('[data-reactroot]')) frameworks.push('react');
  if (window.__VUE__ || window.Vue) frameworks.push('vue');
  if (window.angular || document.querySelector('[ng-version]')) frameworks.push('angular');
  if (window.process && window.process.versions && window.process.versions.electron) frameworks.push('electron');

  var isElectron = !!(window.process && window.process.versions && window.process.versions.electron);
  var electronApi = !!(window.electronAPI || window.electron || (window.require && typeof window.require === 'function'));

  return JSON.stringify({
    schema: 'btk-app-inspector/1',
    title: document.title || '',
    url: window.location ? window.location.href : '',
    user_agent: navigator ? navigator.userAgent : '',
    viewport: { width: window.innerWidth || 0, height: window.innerHeight || 0 },
    frameworks: frameworks,
    is_electron: isElectron,
    has_electron_api: electronApi,
    global_keys: globalKeys.slice(0, 100)
  });
})();"""


def extract_app_facts(raw_state: Any) -> Dict[str, Any]:
    """Extract structured app inspection facts from a state dict or JSON string."""
    if isinstance(raw_state, str):
        try:
            raw = json.loads(raw_state)
        except Exception:
            raw = {}
    elif isinstance(raw_state, dict):
        raw = raw_state
    else:
        raw = {}

    title = str(raw.get("title") or raw.get("page_title") or "").strip()
    url = str(raw.get("url") or raw.get("href") or "").strip()
    user_agent = str(raw.get("user_agent") or raw.get("userAgent") or "").strip()

    viewport_raw = raw.get("viewport") or {}
    vw = float(viewport_raw.get("width") or 0.0)
    vh = float(viewport_raw.get("height") or 0.0)

    frameworks_in = raw.get("frameworks")
    if isinstance(frameworks_in, list):
        frameworks = sorted(list({str(f).lower() for f in frameworks_in if f}))
    else:
        frameworks = []

    is_electron = bool(raw.get("is_electron") or raw.get("isElectron") or ("electron" in frameworks))
    has_electron_api = bool(raw.get("has_electron_api") or raw.get("hasElectronApi") or raw.get("electronAPI"))

    globals_in = raw.get("global_keys") or raw.get("globalKeys") or raw.get("globals")
    if isinstance(globals_in, list):
        global_keys = sorted(list({str(k) for k in globals_in if k}))
    else:
        global_keys = []

    return {
        "schema": SCHEMA,
        "title": title,
        "url": url,
        "user_agent": user_agent,
        "viewport": {"width": vw, "height": vh},
        "frameworks": frameworks,
        "is_electron": is_electron,
        "has_electron_api": has_electron_api,
        "global_keys": global_keys,
    }


def build_browser_probe_script(options: Optional[Dict[str, Any]] = None) -> str:
    """Return a zero-dependency JS probe snippet for browser/Electron page evaluation."""
    return PROBE_SCRIPT_JS


def diff_app_states(before: Any, after: Any) -> Dict[str, Any]:
    """Compare two app state snapshots and report additions, removals, and mutations."""
    b = extract_app_facts(before)
    a = extract_app_facts(after)

    bg_set = set(b["global_keys"])
    ag_set = set(a["global_keys"])

    added_globals = sorted(list(ag_set - bg_set))
    removed_globals = sorted(list(bg_set - ag_set))

    bf_set = set(b["frameworks"])
    af_set = set(a["frameworks"])
    added_frameworks = sorted(list(af_set - bf_set))

    url_changed = (b["url"] != a["url"])
    title_changed = (b["title"] != a["title"])
    electron_api_changed = (b["has_electron_api"] != a["has_electron_api"])

    has_changes = bool(added_globals or removed_globals or added_frameworks or url_changed or title_changed or electron_api_changed)

    return {
        "schema": SCHEMA,
        "has_changes": has_changes,
        "title_changed": title_changed,
        "url_changed": url_changed,
        "electron_api_changed": electron_api_changed,
        "before_url": b["url"],
        "after_url": a["url"],
        "added_globals": added_globals,
        "removed_globals": removed_globals,
        "added_frameworks": added_frameworks,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", help="JSON file containing app state (default: stdin)")
    parser.add_argument("--generate-probe-script", action="store_true", help="Output browser JS probe snippet")
    parser.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"), help="Compare two state JSON files")
    parser.add_argument("--format", choices=["json", "script"], default="json", help="Output format")
    parser.add_argument("--out", help="Write output to file instead of stdout")
    args = parser.parse_args(argv)

    if args.generate_probe_script or args.format == "script":
        output_text = build_browser_probe_script()
        exit_code = 0
    elif args.diff:
        try:
            with open(args.diff[0], "r", encoding="utf-8") as f1:
                b_data = json.load(f1)
            with open(args.diff[1], "r", encoding="utf-8") as f2:
                a_data = json.load(f2)
            diff_res = diff_app_states(b_data, a_data)
            output_text = json.dumps(diff_res, indent=2)
            exit_code = 1 if diff_res["has_changes"] else 0
        except Exception as err:
            print(f"app_inspector: error reading diff files: {err}", file=sys.stderr)
            return 2
    else:
        try:
            if args.file and args.file != "-":
                with open(args.file, "r", encoding="utf-8") as f:
                    content = json.load(f)
            else:
                if sys.stdin.isatty():
                    content = {}
                else:
                    raw_in = sys.stdin.read().strip()
                    content = json.loads(raw_in) if raw_in else {}
            facts = extract_app_facts(content)
            output_text = json.dumps(facts, indent=2)
            exit_code = 0
        except Exception as err:
            print(f"app_inspector: error reading input: {err}", file=sys.stderr)
            return 2

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output_text)
            if not output_text.endswith("\n"):
                f.write("\n")
    else:
        sys.stdout.write(output_text)
        if not output_text.endswith("\n"):
            sys.stdout.write("\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
