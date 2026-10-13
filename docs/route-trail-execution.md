# Route trail execution

`route_trail` keeps the dependency-free planner and adds optional Playwright execution.
It accepts legacy emoji → route JSON or Dart string maps, and a portable JSON catalog:

```json
{"schema":"route-trail/1","pages":[
  {"id":"home","emoji":"🏠","title":"Home","route":"/","ready":{"selector":"#page","text":"🏠 Home"}},
  {"id":"world","emoji":"🌍","title":"World","route":"/world","ready":{"selector":"#page","text":"🌍 World"}}
]}
```

Use emoji or `@id` in a trail; they can be mixed:

```sh
python -S scripts/route_trail.py '🏠 ↔ 🌍' --registry pages.json --base https://example.test --run --json
python -S scripts/route_trail.py '🏠 ↔ @world' --registry pages.json --base https://example.test --run --json
```

An emoji is matched as a complete registry identity, including ZWJ sequences,
skin tones, flags and keycaps. Only whitespace and variation selectors are
normalized; skin tones and ZWJ are retained. Emoji alone selects a registered
page, not an arbitrary emoji substring of a title. If an application consistently
puts its unique identity at a known title position, a consumer can read that
identity and pass it to `resolve`; display-language changes do not alter lookup.
Flutter Navigation Basic appends it (`Home 🏠`); for that contract, use
`title.rsplit(maxsplit=1)[-1]` in Python. The shared browser fixture tests this
trailing-title identity lookup in both runtimes.
There is no automatic scan of all title/body emojis or fuzzy title matching.
Duplicate normalized identities are errors, and unknown emojis fail before any
navigation. Registration is required; aliases resolve to the canonical page.

`→` visits each listed page; `↔` expands to
outbound and return visits. IDs are stable ASCII names, independent of display
emoji/title. IDs, normalized emoji and routes must be unique. Variation selectors
are ignored only for emoji lookup; readiness text retains the original text.
Unknown fields are errors. `ready.selector` waits for a visible locator;
optional `ready.text` is literal, exact text with Playwright whitespace normalization.
Avoid non-unique readiness selectors. Title is metadata, not a document-title assertion.

## CLI and CI

Planning still works with `python -S`, without installed Playwright:

```sh
python -S scripts/route_trail.py '@home ↔ @world' --registry pages.json --base https://example.test --json
python -S scripts/route_trail.py '@home ↔ @world' --registry pages.json --base https://example.test --run --json
python -S scripts/route_trail.py '@home ↔ @world' --registry pages.json --base https://example.test --run --backend python-async --json
python -S scripts/route_trail.py '@home ↔ @world' --registry pages.json --base https://example.test --run --backend node --node-cwd /path/to/existing/node/project --json
```

Execution starts **one worker, one browser and one Page for the entire trail**.
Python workers use the same interpreter with site packages enabled; install the
consumer's Playwright and browser binaries first. Node uses the consumer's existing
`playwright` installation in `--node-cwd` (default current directory). No extra
npm library, TypeScript compiler, Deno or Dart runtime is required. The `.mjs`
helper ships in the Python wheel under `share/browser-test-kit`.

`--browser chromium|firefox|webkit`, `--timeout-ms` (per Playwright wait, default
10000), `--run-timeout` (whole subprocess, default 120 seconds), `--path-routing`
and `--ready-selector` (visible default marker for pages without their own marker)
are available. Limits: 1000 steps, 2 MiB worker input, 120000 ms per wait,
3600 seconds whole run. Execution accepts absolute HTTP(S) and local file URLs;
credentials and executable URL schemes are rejected before navigation.
Callbacks should enforce their own deadlines; the CLI has an overall deadline.

Exit codes: 0 success, 1 execution/setup/protocol failure, 2 invalid input.
`--run --json` emits one `route-trail-run/1` receipt with `ok`, `total`,
`completed`, verified `steps`, and on failure `error` (index/route when available,
phase, message). Execution stops at the first failure. Only the completed prefix
is successful; a cleanup error does not replace the primary error.
Without `--json`, execution prints a compact PASS/FAIL line.

## Existing Page and resumable APIs

```python
from route_trail import load_registry, walk, walk_steps, awalk, awalk_steps
registry = load_registry(open("pages.json", encoding="utf-8").read())
result = walk(page, "@home ↔ @world", registry, base=base)
result = await awalk(page, "@home ↔ @world", registry, base=base)

async for step in awalk_steps(page, "@home ↔ @world", registry, base=base):
    await inspect_current_page(page, step)  # next navigation starts after this work
```

Python `walk_steps` is a sync generator; `awalk_steps` is an async generator.
`walk` / `awalk` collect a receipt. `TrailExecutionError.receipt` contains the
completed prefix and failing phase. The caller owns the Page/context/browser.
Hooks `navigate(page, step)`, `ready(page, step)`, `check(page, step)` run in that
order (step includes zero-based index). Explicit `False` fails a hook. Sync
execution rejects awaitables; async execution accepts sync or async hooks.

```js
import {walk, walkSteps} from './scripts/route_trail_node.mjs';
// steps are JSON records from the Python planner; Node does not duplicate its parser.
const result = await walk(page, steps, {check: async (page, step) => inspect(page, step)});
for await (const step of walkSteps(page, steps)) await inspect(page, step);
```

Node uses the same readiness/receipt contract and exposes `navigate`, `ready`,
`check`, `timeoutMs`. The generator snapshots the plan before the first action.
Both runtimes validate the full plan first. Pausing between yields retains the
same Page and browser state **within that running process**. Separate CLI calls
start fresh browser contexts; this is not a persistent browser service.

Default navigation is `goto`, waits for DOMContentLoaded, rejects HTTP errors,
waits for the marker/hooks, then verifies the exact URL. Without a marker the
receipt says `verification: "url"`: it does not claim application rendering was
verified. Hash transitions keep the document; path navigation may reload it.
Framework semantics, Home confirmation dialogs and clicking UI controls remain
consumer hooks: supply `navigate` to implement them, then `ready`/`check` for
framework-specific readiness. Direct `goto` does not test clicks/history-back.

## Reuse and validation

This extends the existing `route_trail` planner introduced from
Flutter Navigation Basic's JSON/emoji identity workflow. No Flutter or Dart
runtime is needed; application identities/readiness live in the consumer catalog.
Existing Dart map parsing remains a source-text compatibility adapter.

`fixtures/route_trail_execution.json` is the shared portable catalog. Its delayed
hash router proves marker waits, forward/return visits and retained document
state. Python tests cover sync/async and Chromium/Firefox/WebKit; the existing
Node matrix also covers mobile Chromium/WebKit emulation. Node tests consume
Python-generated plans and execute the Python → Node CLI bridge. Unit tests
cover strict catalogs, whole-plan validation, hooks, prefix errors, bounded
subprocesses and receipt validation. These execute in existing CI jobs.
