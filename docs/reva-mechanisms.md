# ReVa mechanisms for browser automation

Studied from the public tree of `cyberkaida/reverse-engineering-assistant` at commit `314653432717466a5aaa55e74308df38e0e34e98` (README, developer notes, tool providers, and the address, lookup, decompilation-context, and similarity helpers). This note maps those mechanisms onto browser-test-kit. It does not vendor that project, and it does not add its server or its reverse-engineering runtime.

ReVa is a Ghidra extension that exposes many small operations to an agent. Each operation takes a tolerant input, returns one JSON document, pages large results, and adds the neighboring fact a person would have looked at next. Mistakes come back as an error plus a hint, not as a traceback. That shape is what this kit should copy for Stagehand and for multi-browser work. The binary-analysis operations themselves do not transfer.

## Mechanisms that transfer

| ReVa mechanism | What it does there | Browser-test-kit use |
| --- | --- | --- |
| One operation, one job | Separate tools to count, list, search, and open one function with its neighbors | `operations`, `count`, `survey`, `locate`, `describe`. Count and locate share a filter. Describe returns one control. |
| Count, then page | A count tool is the cheap call. List tools take `startIndex` and `maxCount` and report `nextStartIndex`. | `count` returns totals and role counts with no element bodies. `locate` and `survey` take `--start` and `--limit` and report `returned`, `total`, and `next_start`. |
| Stable address, loose input | Every address is rendered the same way. One argument accepts an address or a symbol name. A common misshapen value is corrected or explained. | An element `address` is `id:`, `testid:`, `role:`, or `css:`. `h:N` is only an ordinal in that snapshot. The same `--target` accepts those forms, a role selector, and a quoted `button "Save"`. A `0x` memory address is rejected with a hint, not interpreted. |
| Rank, then page | String search sorts by longest common substring, then pages. The published score is that length divided by the shorter string. `1` means the shorter string sits inside the longer one. Empty input scores `0`. | `locate --query` uses that score against name, text, id, testid, and role (the best field wins). The default threshold is `1` (containment). A lower `--threshold` opts into fuzzy rank. Ties break by exact lowercased name, then shorter UTF-16 length, then document order. |
| Suggest, do not guess | A missing program names up to three similar programs, or the available list, and says what to open. | No match returns up to three suggestions with scores. `--unique` fails when two elements share the top score and lists those addresses. |
| Incremental context | Decompilation of a caller can include a few lines around the reference. The full listing is a separate, larger call. Cross-references are capped because each extra snippet is expensive. | `describe` returns one control, its locator recipes, and `--context` neighbor lines (default 1, max 5). Neighbors are adjacent surveyed controls in the snapshot, not the DOM parent chain and not the whole document. |
| Facts a person sees together | A decompilation response also carries the name and the references that are on screen beside it. | Each surveyed control carries role, name, integer box, enabled/visible, and a few locator recipes in one object. |
| Envelope and key order | New tools build one object: success flag, program identity, then the payload. Errors are `{success:false, error}` plus a next step. | `btk-page-survey/1` is the snapshot. `btk-page-inspect/1` is every other result, including failures (`ok`, `operation`, `stage`, `error`, `hint`). |
| Bounds are visible | Large answers are paged. Expensive context is off unless asked for, and then capped. | Survey stores at most 500 controls and pages that list (default 50, max 200). Locate pages at most 100. Truncation is a field, not a silent cut. |
| Same result from two hosts | The server is a thin adapter over a library. | Python (`python -S` for offline commands) and Node implement the same score, normalize, count, locate, and describe steps. Live survey is a thin Playwright adapter over one shared page script. |
| Real execution, not a stub | Integration tests check the program after the call, on the real runtime. | Browser tests run the CLI on Chromium, Firefox, and WebKit. A Node test runs the same page script under the existing engine projects, including the emulated phone profiles. |
| Headless and headed are different modes | One process can serve a UI session; another runs headless for automation. They share operations. | Survey defaults to headless so CI can install the shell build only. `--headed` is explicit and is not a claim about window-frame pixels. |
| Recorded identity of the program | Every result names the program path that was actually used. | Every survey records `os`, browser, version, channel, headless, profile, and viewport. Firefox still drops the emulated-phone `is_mobile` flag (`DEVICE_DESCRIPTOR_CROSS_ENGINE`). |

Failure stages on the envelope are `input`, `launch`, `navigate`, `inspect`, and `cleanup`. A navigate timeout is not reported as a bad flag. Cleanup failures are reported and do not replace an earlier error (`EVIDENCE_MASKS_ROOT_FAILURE`, `SILENT_CLEANUP_EXCEPTION`).

This repository does not vendor the `cli_args` toolkit. The new CLI uses argparse directly, with the local rules that match both that toolkit and this repo: no option abbreviations (`CLI_ARG_GREEDINESS`), no shell, exit `0` / `1` / `2`, and a JSON document. Flags stay `--json`, as in the other scripts here. Offline commands run under `python -S`. Survey is the only command that imports Playwright.

## Mechanisms that do not transfer

- Ghidra programs, address spaces, instruction listings, data types, structures, vtables, call graphs, and binary diff. A page is not a program database.
- Decompiler transactions and renaming symbols in place. Changing the page is a later action phase; this increment only reads.
- The embedded server, the streamable transport, the plugin split between the project window and the code browser, and the stdio bridge that starts a headless session. The kit stays a CLI. A transport can wait until the envelopes stop changing. Tracked as issue 117.
- Holding a live object handle across calls. ReVa addresses stay valid because the program is stored. DOM nodes are replaced (`STALE_ELEMENT_HANDLE_WAIT`). `h:N` is an ordinal in one snapshot file. The stable value to reuse is `address`, and a later action must query it again.
- JVM default-locale lowercasing. The score uses simple Unicode `lower` so Python and Node agree. Strings are compared as UTF-16 code units for the same reason (`TWIN_PARSER_DRIFT` is the analogue: one rule, two hosts).
- Treating one engine, one OS, or a headless viewport as the whole matrix (`ONE_ENGINE_ASSUMPTION`, `SAFARI_EQUALS_WEBKIT`, `MOBILE_VIEWPORT_ONLY`, `HEADLESS_AS_REAL_WINDOW`). WebKit is not Safari. An emulated phone is not a device. Android Chrome and WebView are not this increment.
- Dumping the DOM, the accessibility tree, or a screenshot as the way to find a locator (`UNBOUNDED_TOOL_OUTPUT`, `SCREENSHOT_AS_SELECTOR`).

## First increment

`scripts/page_inspect.py` and `scripts/page_inspect.mjs` implement the table above for read-only inspection. `scripts/page_inspect_collect.js` is the only page script, evaluated by both hosts. Core tests use `fixtures/page_inspect.html`. Commands:

```sh
python scripts/page_inspect.py survey fixtures/page_inspect.html --browser chromium --json --out survey.json
python -S scripts/page_inspect.py count survey.json --role button --json
python -S scripts/page_inspect.py locate survey.json --query "Save draft" --unique --json
python -S scripts/page_inspect.py describe survey.json --target id:save-draft --json
node scripts/page_inspect.mjs locate survey.json --query "Save draft" --unique --json
```

Exit `0` is success. Exit `1` is a completed operation with no match or a non-unique top score. Exit `2` is usage, a bad snapshot, or a launch, navigate, inspect, or cleanup failure.

## Deferred

Issue 117 tracks actions that re-query by address, frame and shadow address spaces, a new snapshot after navigation, the macOS / Windows / Linux / Android matrix, branded channels, an optional Stagehand caller, a headed survey lane, and a protocol transport after this CLI stays stable.


Page-inspect network boundary (#116): HTTP(S) targets accept only literal
`127.0.0.1` or `[::1]` on fixed port **8080**, matching the existing route CLI
port. Hostnames (including `localhost`), alternate IP spellings, credentials,
LAN/external addresses and other ports are rejected before browser launch.
Existing local HTML paths and local `file:///` URLs remain an explicit fixture
exception. The same request guard applies to page resources; HTTP redirects are
refused without following them. Service workers and WebSockets are blocked in
the survey context. There is no port override. This is a browser request boundary,
not an OS-level sandbox.
