# REA observation for browser-test-kit

Studied from the public docs of `morluto/rea` (MIT): `docs/browser-observation.md` at commit `b6a0f32b14ff9c6b651a7897aaf9f546bfdda24b` and `docs/browser-scenario-contract.md` at commit `809f3b7b5b6a8cff3a3170542b4af4d67c88b02a`. This note maps those mechanisms onto browser-test-kit. It does not vendor REA, and it does not run REA's server or any reverse-engineering runtime. The page under test is a browser document, not a program database.

Issue 116 is the spec for this probe. Issue 117 still tracks the phases that are not in this increment.

## Mechanisms that transfer

| REA mechanism | What it does there | browser-test-kit use |
| --- | --- | --- |
| Separate passive observation from actions | `inspect_web_page` does not drive the page. `capture_browser_scenario` is a declared action list with its own authority. | `observe`, `locate`, and `act` are different commands. Locate is offline. Act does not reuse an observe ordinal. |
| Do not call the page during observation | Passive capture uses CDP. It does not send a page call, navigate as a generic remote control, or invoke registered tools. | Chromium `observe` sends DOM, Accessibility, Page, Network, and DOMStorage commands. It enables Runtime only to record console argument types. It never sends a page call. Firefox and WebKit have no CDP session in Playwright, so observe returns `unavailable` coverage and an empty control list. |
| Evidence names its source and its limit | Every section says where it came from and whether it is complete, filtered, attach-limited, truncated, or not requested. | Each section has `source` and `coverage`. A digest is stored only for `complete` and `complete_within_window`. |
| Missing is not the same | Comparison refuses equality when a section is missing, truncated, or not requested. | `evidence_relation` returns `unknown` unless both sides are complete and both have digests. Two `not_requested` sections are unknown, not same. Attach-limited network and console stay unknown even when the arrays match, because events before attach were not seen. |
| Storage is keys and fingerprints | Values stay redacted. Fingerprints are SHA-256, version 2, with a distinct encoding for unpaired UTF-16 surrogates. | `--include-storage-keys` lists names. `--include-storage-fingerprints` adds the digest and still omits the value. Omitting the flags leaves storage `not_requested`. |
| Loopback endpoints only | HTTP discovery accepts `127.0.0.1` or `[::1]` with an explicit port. Hostnames, credentials, and implicit ports are rejected. | `observe` and `act` accept only those URLs. The route handler aborts any other request and any redirect. |
| Fixed action vocabulary | A scenario names click, wait, and similar steps. Unsupported tags fail before launch. | `act` allows `click`, `fill`, and `wait_for_timeout`. `h:N` is rejected before the browser starts. |
| Headless by default | Launch mode defaults to headless and owns a temporary profile. | Both commands default to headless so CI can install the shell build only. `--headed` is explicit. |
| One result, two hosts | CLI and the other surface return the same evidence shape. | Python implements observe and act. `scripts/page_inspect.cjs` calls that CLI through vendored `vendor/py_launch.cjs` (Node 24+, one synchronous spawn, no resident channel). Score, loopback policy, storage fingerprints, and evidence relation are implemented in both languages and checked with `scripts/twin_parity.py`. |

Failure stages remain `input`, `launch`, `navigate`, `inspect`, and `cleanup`. A navigation failure is not reported as a bad flag. A cleanup failure does not replace an earlier error.

This repository does not vendor the `cli_args` toolkit. The Python CLI uses argparse with no abbreviations, no shell, exit `0` / `1` / `2`, and `--json`. The Node side is CommonJS. The bridge is the existing `py_launch.cjs` from `myon-bioinformatics/myon-bioinformatics`, copied into `vendor/` and recorded in `vendor.lock.json`. A second bridge was not added. Python does not call back into Node during that spawn.

## Where Playwright still runs code

Navigation loads the document, so the page's own scripts run. That is ordinary browsing, recorded as `navigation_runs_page_scripts`. Observe does not add a call of its own.

Playwright installs its driver in an isolated world whenever it owns the browser. This tool does not call that driver during observe. The CDP method list on the result is the list this command sent.

`act` click and fill ask Playwright to resolve one locator. That selector engine runs in the page. The result sets `page_js_called` and `bounded_to` to that single action. `wait_for_timeout` does not resolve a locator, so `page_js_called` stays false. Caller-supplied script text is not accepted as an action.

Service workers are blocked and redirects are aborted. Those are bounds on the session, not a claim that the page was unable to run its own scripts after a successful navigation.

## Mechanisms that do not transfer

- REA's server, its tool catalog, generic CDP passthrough, and tool invocation.
- Ghidra, Hopper, IDA, and every other reverse-engineering runtime. Issue 116 keeps those out.
- Electron `file://` observation, Node Inspector, and .NET targets.
- Holding a DOM object across calls. `h:N` is an ordinal in one snapshot file. Act queries `id:`, `testid:`, `role:`, or `css:` again.
- Screenshot pixel comparison and its 256 MiB working-memory budget. Not this increment.
- Full scenario comparison (step alignment, history, event families). `evidence_relation` is only the missing-is-not-same rule.
- Treating WebKit as Safari, a headless phone profile as a device, or one engine as the whole matrix.

## Locator ranking that stays

`locate` still ranks controls by the longest common substring divided by the shorter UTF-16 length, after simple Unicode `lower`. The default threshold is `1` (containment). `--unique` fails when the top score is shared. That ranking is local arithmetic on the snapshot. It does not call the page. Addresses prefer `id:`, then `testid:`, then `role:`, then `css:`.

## Snapshot compare

`observe --after-action SPEC` (or `--after-click LOCATOR` as `click:LOCATOR`) takes one passive snapshot, runs a single Playwright step, then takes a second snapshot in the same browser. `SPEC` is `click:LOCATOR`, `hover:LOCATOR`, `scroll:DX,DY`, or `scroll-into:LOCATOR` using the same `id:`, `testid:`, `role:`, or `css:` addresses as `act`. The second snapshot has `step` (index, action, target, URL before and after) and limits such as `click_runs_page_scripts`, `hover_may_trigger_css`, or `scroll_may_run_page_scripts`. The two results go to separate files (`--out` and `--after-out`) so `compare` can read them. Network and console are cleared after the step. This is not passive observation when the step uses Playwright's pointer or selector engine.

`compare` reads two `btk-page-observe/1` files and runs no browser. It reuses `evidence_relation`, so a section is `same` only when both sides are complete and their digests match. Shadow-root counts and child-frame and element totals are reported as left, right, and delta. A count is `null` when that side's section was not complete. Environment differences (OS, browser, profile, headless) are reported but do not change the section relations.

## Deferred on issue 117

Child frames and shadow roots as their own address spaces. Observe counts child frames and author open plus closed shadow roots (pierced DOM, `shadow_roots` section, `contents: not_entered`, `user_agent` for Chromium built-in roots); it does not enter either and does not read shadow attributes. A new snapshot after navigation in one session. macOS, Windows, Linux, and Android Chrome or WebView. Branded channels as a matrix. A Stagehand caller. A headed lane in CI. An agent transport after these envelopes stay stable. Screenshot comparison and full scenario diffs.
