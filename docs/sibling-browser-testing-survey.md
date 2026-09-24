# Sibling repository browser-testing survey

This report consolidates browser-test and anti-pattern knowledge already proven in older `myon-bioinformatics` repositories. It is intentionally evidence-first: this PR can compare/adopt the patterns after the inventory exists instead of rewriting history to match the current kit.

## Sources surveyed

| Repository | Evidence inspected | What it contributes |
| --- | --- | --- |
| `markdown` | `docs/antipatterns.md`, `tests/frontend/test_markdown_html_playwright_cli.py`, real-chat UI tests/workflows | incident-driven anti-pattern IDs; pytest fixture ordering; failure screenshots; Playwright Python CLI for static HTML; heavy browser lanes kept optional |
| `mcp-toolcall-lab` | `docs/antipatterns.md`, `tests/test_browser_fetch_protocol.py`, stub/browser docs, `frontends.py`, Docker smoke workflows | browser-as-protocol-client tests; optional `browser-test` extra; selector contracts; UI/MCP failure taxonomy; JSONL anti-pattern observations |
| `flutter_navigation_basic` | Playwright config, Python CLI wrapper tests, browser parity test, E2E docs/Docker | Chromium/Firefox/WebKit parity; exact argv regression tests; install/config drift guard; failure trace/screenshot/video policy; manual heavy E2E split |
| `web-ui` | `TOOLING.md` | deterministic Playwright vs optional Stagehand v4 separation; tooling/SHA evidence; live agent tests opt-in |
| `Ironmate` | repository search for browser/Playwright workflow patterns (weaker evidence; needs direct workflow/file follow-up) | parameterized Playwright/browser workflow precedent; portability lead only, not yet treated as a proven pytest/browser contract |

## Consolidated test-pattern catalog

### 1. Test the smallest browser surface that proves the contract

There are at least four distinct browser lanes in the sibling repositories; they should not be collapsed into one “E2E” bucket.

1. **Static render evidence** — `markdown` writes deterministic HTML to a temporary file and invokes Playwright's own Python CLI against `file://`. No app server or custom browser script is introduced when a screenshot/PDF is the contract.
2. **Browser protocol client** — `mcp-toolcall-lab` uses `page.evaluate(fetch(...))` against a same-origin MCP endpoint. There is deliberately no clicking or screenshot because the contract is browser HTTP behavior, not UI.
3. **Product UI interaction** — Open WebUI/LibreChat lanes drive the actual composer and response surface. Selectors/auth/composer/MCP wiring are centralized as product contracts instead of copied ad hoc into each test.
4. **Application E2E / visual lane** — `flutter_navigation_basic` drives the built app, keeps visual snapshots explicit, and separates lightweight PR smoke/listing from heavier full E2E.

**Kit rule:** choose the least powerful lane that proves the behavior. Do not require a product UI for a render contract, and do not substitute screenshots for protocol assertions.

### 2. Pytest + Playwright patterns worth preserving

- Use `pytest.importorskip("playwright.sync_api")` / optional browser extras when browser support is not part of the default lightweight test dependency set.
- Module-scoped browser fixtures amortize launch cost; function-scoped pages isolate tests.
- Browser executable override via `PLAYWRIGHT_CHROMIUM_EXECUTABLE` is a useful escape hatch when package/browser revisions differ.
- Fixture dependencies must be explicit. An autouse failure-screenshot fixture that reaches into `request.node.funcargs` does **not** acquire pytest teardown-order guarantees.
- Page cleanup belongs in `finally`; diagnostic cleanup must not silently swallow useful evidence or mask the original failure.
- Exact CLI argv deserves unit tests. `flutter_navigation_basic` caught Playwright's greedy `--project chromium <spec>` parsing and locked in `--project=chromium`.
- Configured browser engines and CI/Docker-installed engines need a parity regression guard, not a convention.
- Heavy Docker/product browser tests should be opt-in or dedicated workflows when they would make the default `pytest -q` lane slow/flaky.

### 3. Cross-browser and device patterns

The strongest reusable baseline across the siblings is:

- explicit Chromium / Firefox / WebKit identities;
- do not call Playwright WebKit “Safari” in evidence claims;
- install/config parity is testable;
- named device descriptors are engine-sensitive;
- viewport-only or partially adapted emulation must not be presented as full physical-device fidelity;
- desktop/mobile identity belongs in evidence metadata;
- retries must not invalidate artifact accounting.

The kit should remain the place where these are expressed as portable contracts rather than forcing each application repository to rediscover them.

### 4. Evidence patterns

A browser test result is stronger when the evidence layers are separable:

- command/test exit status;
- browser/runtime/project/device/profile identity;
- failure stage;
- screenshot path and PNG structural validity;
- trace/video where the runner supports them;
- tool/repository SHA and environment metadata where useful;
- uploaded artifact with a stable name;
- raw protocol/UI observations when the screenshot is not the real assertion.

A non-empty file alone is weak evidence. Likewise, a screenshot can prove rendering but not that an MCP call occurred.

## Consolidated anti-patterns from senior repositories

These are candidates for the kit catalog. Existing kit IDs should be reused instead of duplicated when semantics already match.

| Source lesson | Portable anti-pattern | Kit relationship |
| --- | --- | --- |
| markdown: failure screenshot fixture used `request.node.funcargs` and ran after page teardown | implicit fixture dependency / teardown-order bug | strengthens `SILENT_CLEANUP_EXCEPTION`; candidate new explicit fixture-order ID |
| markdown: broad `except: pass` hid screenshot failure | diagnostic cleanup silently disappears | already `SILENT_CLEANUP_EXCEPTION` / `EVIDENCE_MASKS_ROOT_FAILURE` |
| markdown: fresh account repeatedly shows changelog/onboarding modal | fresh-profile overlay blocks the real control | candidate `FRESH_PROFILE_OVERLAY` |
| markdown: framework replaces DOM node while code polls captured element | stale element handle wait | already `STALE_ELEMENT_HANDLE_WAIT` |
| markdown: product DOM is not conventional HTML expected by test | standard DOM assumption | candidate `STANDARD_DOM_ASSUMPTION` |
| markdown: substring-only assertions accept structurally wrong output | substring-only assertion | candidate `SUBSTRING_ONLY_ASSERTION` |
| mcp-toolcall-lab: input/send succeeds but MCP is never called | UI action equals backend success | candidate `UI_ACTION_EQUALS_BACKEND_CALL`; preserve layer taxonomy |
| mcp-toolcall-lab: advertised tool treated as invoked tool | advertised equals called | candidate `TOOL_ADVERTISED_EQUALS_TOOL_CALLED` |
| mcp-toolcall-lab: selector/auth/send/timeout/MCP/render failures flattened together | failure-layer flattening | already `FAILURE_LAYER_FLATTENING` |
| mcp-toolcall-lab: one SDK is treated as full protocol proof | SDK-only probe | candidate `SDK_ONLY_PROBE` |
| flutter: `--project chromium` absorbs following argv | CLI argument greediness | already `CLI_ARG_GREEDINESS` |
| flutter: configured engines differ from installed engines | browser matrix drift | already `BROWSER_MATRIX_DRIFT` |
| flutter: only one browser assumed representative | one-engine assumption | already `ONE_ENGINE_ASSUMPTION` |
| web-ui: agent browser tooling replaces deterministic checks | agent replaces deterministic test | already `AGENT_REPLACES_DETERMINISTIC_TEST` |
| all: live external/network behavior gates deterministic core tests | external site as core fixture | already `EXTERNAL_SITE_AS_CORE_FIXTURE` |

## Failure taxonomy to centralize

The kit currently has a useful generic sequence:

`install -> launch -> navigate -> interact -> assert -> screenshot -> artifact -> cleanup`

The sibling repos show two additional orthogonal axes that should be documented rather than flattened into that sequence:

**Product/UI axis:** `auth -> selector -> input -> send -> response-render`

**Tool/protocol axis:** `advertised -> selected -> assistant tool_call -> MCP tools/call -> MCP result -> product envelope -> UI render`

A browser test should record only the stages it can actually observe. For example, a screenshot after clicking Send must not claim `tools/call` success unless protocol/log evidence exists.

## Recommended aggregation model for browser-test-kit

To credibly act as the organization's browser-testing aggregation point, keep three layers:

- **Catalog:** stable anti-pattern IDs and portable contracts.
- **Survey/provenance:** this document records which sibling implementation or incident motivated each contract.
- **Executable kit:** minimal Node/Python examples and regression guards. Adoption can happen gradually; the survey must not claim every source pattern is already implemented here.

This avoids two failure modes: copying every application-specific workaround into the kit, and claiming centralization while the useful incident knowledge remains scattered across old PRs.


## Multi-platform doctrine

The implementation and verification policy derived from this survey lives in [platform-doctrine.md](./platform-doctrine.md). Keeping provenance and doctrine separate lets source evidence evolve independently from architectural policy.
