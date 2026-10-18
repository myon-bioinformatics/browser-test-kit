"""Measure how one OS x browser x device sees the same page, and compare them in tabs (platform-matrix).

    python scripts/platform_probe.py collect --browser chromium --profile desktop --out DIR [--headed] [--channel chrome]
    python -S scripts/platform_probe.py merge DIR... --out dataset.json      # one dataset from many runs
    python -S scripts/platform_probe.py summary dataset.json                 # one line per environment; exit 1 if any fail
    python -S scripts/platform_probe.py render dataset.json --out matrix.html  # tabs: OS / browser / device / mode

collect opens fixtures/platform_probe.html and records `btk-platform-facts/1`:
screen, window outer/inner (frame = outer - inner; real only when headed), scrollbar
width (page / always-scrolling probe), devicePixelRatio, visualViewport, safe-area insets, pointer/hover/touch,
measured font widths, platform and browser version. The environment passes when
the layout holds (no horizontal overflow, no overlap, nothing clipped) and a real
click (a tap on touch profiles) at the integer centre of the button registers.
`min_ok_width` is the narrowest viewport width at which the layout still holds,
found by binary search (the checks are monotonic in width).

Only collect needs Playwright; merge, summary and render are stdlib-only.
Exit codes: 0 OK; 1 an environment failed (collect, summary); 2 input error.
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import os
import platform
import sys
from pathlib import Path

FACTS_SCHEMA = "btk-platform-facts/1"
DATASET_SCHEMA = "btk-platform-matrix/1"
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "platform_probe.html"
PROFILES = {"desktop": None, "iphone": "iPhone 13", "pixel": "Pixel 7"}
DESKTOP_VIEWPORT = {"width": 1280, "height": 800}
MIN_SEARCH_WIDTH = 240


def os_name() -> str:
    return {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(platform.system(), platform.system())


def env_id(env: dict) -> str:
    browser = env.get("channel") or env["browser"]
    return f"{env['os']}-{browser}-{env['profile']}-{'headless' if env['headless'] else 'headed'}"


def narrowest_ok_width(ok_at, low: int, high: int) -> int | None:
    """Smallest width in [low, high] where ok_at(width) is true, assuming monotonic; None if high fails."""
    if not ok_at(high):
        return None
    if ok_at(low):
        return low
    while high - low > 1:
        mid = (low + high) // 2
        if ok_at(mid):
            high = mid
        else:
            low = mid
    return high


def verdict(record: dict) -> str:
    return "pass" if record["layout"]["ok"] and record["click"]["ok"] else "fail"


def collect(browser_name: str, profile: str, *, headed: bool = False, channel: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright  # only collect needs a browser

    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {sorted(PROFILES)}")
    with sync_playwright() as pw:
        engine = getattr(pw, browser_name)
        browser = engine.launch(headless=not headed, **({"channel": channel} if channel else {}))
        try:
            device = PROFILES[profile]
            if device:
                args = dict(pw.devices[device])
            elif headed:
                # A real window: an emulated viewport would make inner larger than outer (negative frame).
                args = {"no_viewport": True}
            else:
                args = {"viewport": dict(DESKTOP_VIEWPORT)}
            args.pop("default_browser_type", None)
            if browser_name == "firefox":
                args.pop("is_mobile", None)  # DEVICE_DESCRIPTOR_CROSS_ENGINE
            context = browser.new_context(**args)
            page = context.new_page()
            page.goto(FIXTURE.resolve().as_uri())
            facts = page.evaluate("window.__platformFacts()")
            layout = page.evaluate("window.__layoutChecks()")
            box = page.locator("#action").bounding_box()
            x, y = int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2)
            touch = bool(args.get("has_touch"))
            (page.touchscreen.tap if touch else page.mouse.click)(x, y)
            clicks = int(page.locator("#action").get_attribute("data-clicks"))
            size = page.viewport_size or {"width": facts["window"]["inner_width"],
                                          "height": facts["window"]["inner_height"]}

            def ok_at(width: int) -> bool:
                page.set_viewport_size({"width": width, "height": size["height"]})
                return page.evaluate("window.__layoutChecks().ok")
            min_width = narrowest_ok_width(ok_at, MIN_SEARCH_WIDTH, size["width"])
            version = browser.version
        finally:
            browser.close()
    record = {
        "schema": FACTS_SCHEMA,
        "env": {"os": os_name(), "os_release": platform.release(), "runner_image": os.environ.get("ImageOS"),
                "browser": browser_name, "channel": channel, "browser_version": version,
                "profile": profile, "device": PROFILES[profile] or "Desktop", "headless": not headed},
        "facts": facts, "layout": layout,
        "click": {"ok": clicks == 1, "count": clicks, "input": "touch" if touch else "mouse", "point": [x, y]},
        "min_ok_width": min_width,
    }
    record["env"]["id"] = env_id(record["env"])
    record["verdict"] = verdict(record)
    return record


def load_records(paths: list[str]) -> list[dict]:
    records = {}
    for pattern in paths:
        files = [Path(p) for p in glob.glob(str(Path(pattern) / "**" / "*.json"), recursive=True)] \
            if Path(pattern).is_dir() else [Path(p) for p in glob.glob(pattern)]
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data["records"] if isinstance(data, dict) and data.get("schema") == DATASET_SCHEMA else [data]
            for item in items:
                if not isinstance(item, dict) or item.get("schema") != FACTS_SCHEMA:
                    continue
                records[item["env"]["id"]] = item
    if not records:
        raise ValueError("no btk-platform-facts/1 records found")
    return [records[k] for k in sorted(records)]


def summary_lines(records: list[dict]) -> list[str]:
    out = []
    for r in records:
        w, v = r["facts"]["window"], r["facts"]["viewport"]
        failed = ",".join(r["layout"]["failed"]) or "-"
        out.append(f"{r['verdict']:4} {r['env']['id']:38} v{r['env']['browser_version']} "
                   f"frame={w['frame_width']}x{w['frame_height']} scrollbar={v['scrollbar_width']}/{v.get('scrollbar_classic')} "
                   f"dpr={v['device_pixel_ratio']} min_ok_width={r['min_ok_width']} failed={failed}")
    return out


_PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Platform matrix</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#d8d8d8;--tab:#f1f1f1;--on:#1f5fbf;--ok:#1a7f37;--ng:#c62828;--chg:#fff3bf}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--muted:#999;--line:#333;--tab:#222;--on:#6ea8ff;--ok:#4cc26a;--ng:#ff6b6b;--chg:#4a3f00}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 12px}
.row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0}.row b{width:72px;color:var(--muted);font-weight:500}
.row button{font:inherit;border:1px solid var(--line);background:var(--tab);color:var(--fg);border-radius:6px;padding:4px 10px;cursor:pointer}
.row button[aria-pressed=true]{background:var(--on);border-color:var(--on);color:#fff}
.row button.none{opacity:.45}
#head{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:12px 0}
.badge{font-weight:600;padding:2px 10px;border-radius:999px;color:#fff}.pass{background:var(--ok)}.fail{background:var(--ng)}
.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}@media(max-width:760px){.grid{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:3px 6px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{color:var(--muted);font-weight:500;width:42%}tr.group th{color:var(--fg);font-weight:600;padding-top:10px}
td.changed{background:var(--chg);transition:background .2s}td.varies::after{content:" *";color:var(--muted)}
svg{width:100%;height:auto;border:1px solid var(--line);border-radius:6px}svg text{font:11px system-ui;fill:var(--fg)}
.note{color:var(--muted);font-size:12px}
</style></head><body><main>
<h1>Platform matrix</h1>
<p class="sub">同じ fixture を OS × ブラウザ × 端末で開いた実測値。タブを切り替えると、直前と値が変わった行が色付きになります（* は環境によって値が違う項目）。</p>
<div id="tabs"></div>
<div id="head"></div>
<div class="grid"><div><table id="facts"></table></div><div><svg id="diagram" viewBox="0 0 420 300" role="img" aria-label="screen, window and viewport"></svg>
<p class="note">外枠 = screen、点線 = avail、青 = window（outer）、緑 = viewport（inner）、赤 = scrollbar。headless では枠が 0 になります。</p></div></div>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
const records = JSON.parse(document.getElementById('data').textContent).records;
const axes = [['OS', r => r.env.os], ['Browser', r => r.env.channel || r.env.browser], ['Device', r => r.env.device],
              ['Mode', r => r.env.headless ? 'headless' : 'headed']];
const sel = axes.map(([, f]) => f(records[0]));
let previous = null;
const flat = (o, p = '') => Object.entries(o).flatMap(([k, v]) =>
  v && typeof v === 'object' && !Array.isArray(v) ? flat(v, p + k + '.') : [[p + k, v]]);
const varies = new Set();
const allFlat = records.map(r => new Map(flat({facts: r.facts, min_ok_width: r.min_ok_width, browser_version: r.env.browser_version})));
for (const key of allFlat[0].keys()) if (new Set(allFlat.map(m => JSON.stringify(m.get(key)))).size > 1) varies.add(key);
function match() { return records.find(r => axes.every(([, f], i) => f(r) === sel[i])); }
function tabs() {
  const box = document.getElementById('tabs'); box.textContent = '';
  axes.forEach(([name, f], i) => {
    const row = document.createElement('div'); row.className = 'row';
    row.append(Object.assign(document.createElement('b'), {textContent: name}));
    for (const value of [...new Set(records.map(f))].sort()) {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = value;
      b.setAttribute('aria-pressed', String(sel[i] === value));
      const probe = sel.slice(); probe[i] = value;
      if (!records.some(r => axes.every(([, g], j) => g(r) === probe[j]))) b.classList.add('none');
      b.onclick = () => { sel[i] = value; show(); };
      row.append(b);
    }
    box.append(row);
  });
}
function rect(svg, x, y, w, h, stroke, dash, label, line = 0) {
  const ns = 'http://www.w3.org/2000/svg', r = document.createElementNS(ns, 'rect');
  Object.entries({x, y, width: Math.max(w, 0), height: Math.max(h, 0), fill: 'none', stroke, 'stroke-width': 2,
    'stroke-dasharray': dash || ''}).forEach(([k, v]) => r.setAttribute(k, v));
  svg.append(r);
  if (label) { const t = document.createElementNS(ns, 'text'); t.setAttribute('x', x + 4); t.setAttribute('y', y + 13 + 14 * line);
    if (stroke !== 'currentColor') { t.style.fill = stroke; t.style.fontWeight = '600'; }
    t.textContent = label; svg.append(t); }
}
function diagram(r) {
  const svg = document.getElementById('diagram'); svg.textContent = '';
  if (!r) return;
  const s = r.facts.screen, w = r.facts.window, v = r.facts.viewport;
  const k = Math.min(400 / Math.max(s.width, w.outer_width), 280 / Math.max(s.height, w.outer_height));
  const ox = 10, oy = 10;
  rect(svg, ox, oy, s.width * k, s.height * k, 'currentColor', '', `screen ${s.width}×${s.height}`);
  rect(svg, ox + (s.avail_left || 0) * k, oy + (s.avail_top || 0) * k, s.avail_width * k, s.avail_height * k, 'currentColor', '4 3');
  const wx = ox + Math.max(0, w.screen_x) * k, wy = oy + Math.max(0, w.screen_y) * k;
  rect(svg, wx, wy, w.outer_width * k, w.outer_height * k, '#1f5fbf', '', `window ${w.outer_width}×${w.outer_height}（枠 ${w.frame_width}×${w.frame_height}）`, 1);
  const side = Math.max(0, w.frame_width) / 2;
  const ix = wx + side * k, iy = wy + Math.max(0, w.frame_height - side) * k;
  rect(svg, ix, iy, w.inner_width * k, w.inner_height * k, '#1a7f37', '', `viewport ${w.inner_width}×${w.inner_height}`, 2);
  if (v.scrollbar_width > 0) rect(svg, ix + v.client_width * k, iy, v.scrollbar_width * k, w.inner_height * k, '#c62828', '');
}
function show() {
  tabs();
  const r = match(), head = document.getElementById('head'), table = document.getElementById('facts');
  head.textContent = ''; table.textContent = '';
  if (!r) { head.textContent = 'この組み合わせは未測定です（薄いタブは測定がありません）'; diagram(null); previous = null; return; }
  const badge = Object.assign(document.createElement('span'), {className: 'badge ' + r.verdict, textContent: r.verdict});
  head.append(badge, ` ${r.env.id}  v${r.env.browser_version}  OS ${r.env.os_release}`,
    `  ・最小幅 ${r.min_ok_width ?? '—'}px`, r.layout.failed.length ? `  ・崩れ: ${r.layout.failed.join(', ')}` : '',
    `  ・クリック ${r.click.ok ? 'OK' : 'NG'}（${r.click.input} @ ${r.click.point.join(',')}）`);
  const now = new Map(flat({facts: r.facts, min_ok_width: r.min_ok_width, browser_version: r.env.browser_version}));
  let group = '';
  for (const [key, value] of now) {
    const top = key.split('.').slice(0, 2).join('.');
    if (top !== group) { group = top; const g = table.insertRow(); g.className = 'group';
      g.append(Object.assign(document.createElement('th'), {colSpan: 2, textContent: top.replace('facts.', '')})); }
    const row = table.insertRow();
    row.append(Object.assign(document.createElement('th'), {textContent: key.split('.').slice(2).join('.') || key}));
    const td = row.insertCell(); td.textContent = value === null ? '—' : String(value);
    if (varies.has(key)) td.classList.add('varies');
    if (previous && JSON.stringify(previous.get(key)) !== JSON.stringify(value)) td.classList.add('changed');
  }
  diagram(r); previous = now;
}
show();
</script></body></html>
"""


def render(records: list[dict]) -> str:
    data = json.dumps({"schema": DATASET_SCHEMA, "records": records}, ensure_ascii=False)
    return _PAGE.replace("__DATA__", data.replace("<", "\\u003c"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect", help="measure one environment (needs Playwright)")
    c.add_argument("--browser", choices=("chromium", "firefox", "webkit"), required=True)
    c.add_argument("--channel", help="installed branded browser, e.g. chrome or msedge (chromium only)")
    c.add_argument("--profile", choices=sorted(PROFILES), default="desktop")
    c.add_argument("--headed", action="store_true", help="a real window, so the frame size is measured")
    c.add_argument("--out", required=True, help="directory for <env-id>.json")
    m = sub.add_parser("merge", help="combine records into one dataset")
    m.add_argument("inputs", nargs="+", help="directories or JSON files")
    m.add_argument("--out", required=True)
    s = sub.add_parser("summary", help="one line per environment; exit 1 if any fail")
    s.add_argument("inputs", nargs="+")
    r = sub.add_parser("render", help="self-contained HTML with OS / browser / device / mode tabs")
    r.add_argument("inputs", nargs="+")
    r.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            if args.channel and args.browser != "chromium":
                raise ValueError("--channel needs --browser chromium")
            try:
                record = collect(args.browser, args.profile, headed=args.headed, channel=args.channel)
            except Exception as exc:  # a browser that cannot launch or navigate is a finding, not a crash
                where = f"{args.browser}{'/' + args.channel if args.channel else ''} {args.profile}" \
                        f"{' headed' if args.headed else ''}"
                first = str(exc).strip().splitlines()[0][:300] if str(exc).strip() else ""
                print(f"error: {where}: {type(exc).__name__}: {first}", file=sys.stderr)
                if os.environ.get("GITHUB_ACTIONS"):
                    print(f"::error title=platform_probe collect::{where}: {type(exc).__name__}: {first}")
                return 2
            Path(args.out).mkdir(parents=True, exist_ok=True)
            path = Path(args.out) / f"{record['env']['id']}.json"
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(summary_lines([record])[0])
            return 0 if record["verdict"] == "pass" else 1
        records = load_records(args.inputs)
        if args.command in ("merge", "render"):
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        if args.command == "merge":
            Path(args.out).write_text(json.dumps({"schema": DATASET_SCHEMA, "records": records}, ensure_ascii=False,
                                                 indent=1) + "\n", encoding="utf-8")
            print(f"{len(records)} environments -> {args.out}")
            return 0
        if args.command == "summary":
            lines = summary_lines(records)
            print("\n".join(lines))
            return 0 if all(r["verdict"] == "pass" for r in records) else 1
        Path(args.out).write_text(render(records), encoding="utf-8")
        print(f"{len(records)} environments -> {args.out}")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::error title=platform_probe {args.command}::{type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
