# Platform matrix application adapters

`platform_probe.py collect` still defaults to the local SRI fixture. Its OS × engine ×
profile × mode workflow remains 42 environments (including optional Chrome/Edge).
No published-site request is added to that fixture lane.

The application lane is `.github/workflows/platform-apps.yml`. It observes the
published Flutter app separately on Chromium/Firefox/WebKit desktop plus Chromium
Pixel and WebKit iPhone **emulation**. These are not physical phones, and Playwright
WebKit is not Safari. The first adapters cover:

| Adapter | Layout scope | Real coordinate input and postcondition |
| --- | --- | --- |
| `flutter-home` | Shared title, Home, favorite and menu hit regions | Favorite text changes from `Favorite this page` to `Remove favorite` |
| `flutter-counter` | Those shared regions plus Increase/Decrease body buttons | Press Increase; Reset changes from disabled to enabled |

This is deliberately a selected-control contract, not a guarantee for every screen,
all painted text, or every app feature. Flutter's invisible semantics labels do not
have the same glyph metrics as its canvas. Their `scrollWidth` is not treated as
painted-text clipping; screenshots support visual inspection. No production Dart
changes, forced application clicks, or synthetic application state updates are used.
Flutter's opt-in accessibility placeholder is activated once: a centre tap/click
for Android's full-screen placeholder, or a DOM click for the off-screen desktop
placeholder. Polling never repeatedly dispatches activation events.
Application actions use measured integer centres with mouse or touch input and must
satisfy the app-specific postcondition. Flutter bypasses the ordinary DOM
`elementFromPoint` check because its semantics forward input to the canvas; its
real-input postcondition still fails when an overlay blocks the action.

```sh
python scripts/platform_probe.py collect --browser chromium --profile desktop \
  --adapter adapters/flutter-counter.json --widths 320 390 \
  --out app-results --evidence-dir app-results/counter/screenshots
python -S scripts/platform_probe.py merge app-results --out app-matrix/dataset.json
python -S scripts/platform_probe.py render app-matrix/dataset.json --out app-matrix/index.html
```

`--url https://.../#/route` overrides the adapter URL, for example for a locally
served pinned app build. Only HTTP(S) targets without embedded credentials are
accepted. Point adapters only at test actions that are appropriate to execute.
Use a distinct evidence directory per environment/adapter.

## Adapter contract

An adapter is trusted JSON with `schema: btk-platform-adapter/1`, a stable `id`, a
`url`, disjoint CSS `elements`, and a `click` object. Every layout element must be
unique, have a nonzero visible box, fit inside the viewport, and not intersect any
other listed element. Ordinary DOM controls must also be unclipped and unobscured.
Do not list a container together with its child (intentional nesting is not overlap).
The rules are property checks rather than cross-engine pixel equality.

`click.target` must be listed in `elements`. `click.observe`, `attribute`, `before`
and `after` describe an application-state transition. `attribute: textContent`
observes exact text; other values observe a DOM attribute. JSON `null` means an
absent attribute. Before and after must differ. Missing or ambiguous elements fail
closed. Optional `bindings` map alphanumeric names to `{selector, text}` and resolve
exact visible semantics text to `[data-btk-probe="name"]` markers; markers are
refreshed after layout changes. This supports Flutter controls without stable ids.
`flutter_semantics: true` waits for Flutter's accessibility tree before binding.

Browser/OS facts live in `scripts/platform_facts.js` and are used by both lanes:
screen, window, viewport, DPR, safe areas, input/media preferences, platform and font
widths. A shadow-isolated measuring probe avoids application CSS contaminating the
classic scrollbar measurement. Fixture-only library/SRI checks stay in the fixture.

## Width search, evidence and failures

The fixture retains its original monotonic binary search. Application layouts can
have passing islands around responsive breakpoints, so adapters scan each integer
width from 250px to the initial viewport width, stopping at the first layout pass.
`min_ok_width` is **layout-only**, scoped to those bounds and the current viewport
height, with the tested failures retained in `width_search.observations`. A 250px
result is lower-bound-censored: it says nothing about narrower widths. Widths below
250 are unsupported by Windows WebKit. The first passing width and explicit
`--widths` (default 320/390) also receive independent real clicks; a click failure
makes the record fail, without relabelling the layout threshold as a click threshold.
Each click sample uses a **fresh browser context**, isolating cookies and persistent
browser storage. Records contain per-width boxes, failure reasons and click before/
after values. Screenshots capture initial and tested widths.

The facts schema remains `btk-platform-facts/1` with additive target/sample fields;
old fixture records are still readable. Environment ids remain unchanged. File and
merge keys additionally include the adapter config hash and URL, so multiple pages
on one environment cannot overwrite each other. The viewer has a Target axis and
shows per-width results. The config snapshot and observation time accompany live
observations. A public deployment can change between runs: it is not a pinned app
artifact. Network failures or missing app controls are errors, never a passing
measurement. The application workflow's failing collect job remains failed even
when the report job can render other completed observations.

Offline regressions exercise a different DOM without fixture hooks, nonmonotonic
width rules, touch and mouse postconditions, persistent-storage isolation, overlap,
occlusion and missing elements. They use a loopback server and no public network.
