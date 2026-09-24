# Sibling repository browser-testing survey

This report consolidates browser-test and anti-pattern knowledge already proven in older `myon-bioinformatics` repositories. It is intentionally evidence-first: this PR can compare/adopt the patterns after the inventory exists instead of rewriting history to match the current kit.

## Sources surveyed

| Repository | Evidence inspected | What it contributes |
| --- | --- | --- |
| `markdown` | `docs/antipatterns.md`, `tests/frontend/test_markdown_html_playwright_cli.py`, real-chat UI tests/workflows | incident-driven anti-pattern IDs; pytest fixture ordering; failure screenshots; Playwright Python CLI for static HTML; heavy browser lanes kept optional |
| `mcp-toolcall-lab` | `docs/antipatterns.md`, `tests/test_browser_fetch_protocol.py`, stub/browser docs, `frontends.py`, Docker smoke workflows | browser-as-protocol-client tests; optional `browser-test` extra; selector contracts; UI/MCP failure taxonomy; JSONL anti-pattern observations |
| `flutter_navigation_basic` | Playwright config, Python CLI wrapper tests, browser parity test, E2E docs/Docker | Chromium/Firefox/WebKit parity; exact argv regression tests; install/config drift guard; failure trace/screenshot/video policy; manual heavy E2E split |
| `web-ui` | `TOOLING.md` | deterministic Playwright vs optional Stagehand v4 separation; tooling/SHA evidence; live agent tests opt-in |
| `Ironmate` | repository search for browser/Playwright workflow patterns | parameterized Playwright/browser workflow precedent; useful portability target, but fewer pytest/browser-specific contracts than the repos above |

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

## PR #3 comparison checklist

After this inventory, compare the current kit implementation against it:

- [ ] exact-project Node evidence validator extracted and regression-tested;
- [ ] cleanup cannot mask original browser/test failure;
- [ ] anti-pattern table schema unified;
- [ ] fixture-order anti-pattern represented explicitly;
- [ ] fresh-profile overlay and DOM-assumption lessons represented;
- [ ] UI action vs backend/tool-call layers represented without MCP-specific implementation dependency;
- [ ] CLI argv and browser install/config parity remain executable contracts;
- [ ] static CLI, browser protocol, product UI, and full E2E lanes are documented as distinct patterns;
- [ ] Stagehand remains optional and subordinate to deterministic browser contracts;
- [ ] current Actions runtime warnings resolved or documented with a deliberate follow-up.

## Scope note

This is a consolidation report, not a claim that browser-test-kit already implements every item. The next step is a mechanical gap analysis against the current PR and then small regression additions where the contract is generic enough to belong here.


---

# Multi-platform browser implementation and verification doctrine

## North star: protect multi-platform reach, not a particular language

The architectural invariant is **multi-platform reachability**. Dart/Flutter, TypeScript/JavaScript, Node, Deno, Python, Playwright, and Stagehand are means, not ends. A feature should remain in Dart when Dart keeps the implementation, dependency graph, packaging, and maintenance simpler. A browser-native or separately testable layer is preferable when it removes platform-specific weight without weakening the product contract.

The target application is therefore broader than “a Flutter application”. It is a **multi-platform application whose useful functions remain reachable from an available browser across iPhone/iOS, Android, desktop, and ordinary web environments**, while native Flutter surfaces remain available where they add value.

A rewrite is not a goal. The preferred change is the smallest boundary change that reduces total complexity while preserving behavior and reach.

## Priority order for implementation choices

When two implementations satisfy the same product contract, evaluate them in this order:

1. **Reach** — can users reach the function from the intended desktop/mobile/iOS/Android environments?
2. **Web/platform standards first** — can a stable browser or language standard solve it without a framework-specific bridge?
3. **Dependency weight** — prefer fewer runtime dependencies, smaller install/bootstrap cost, and less duplicated tooling.
4. **Single source of truth** — avoid parallel Dart/JS/Python implementations of the same rule unless the platform boundary genuinely requires them.
5. **Testability** — prefer a boundary that can be verified deterministically without booting the entire product.
6. **Operational simplicity** — CI, local reproduction, artifact collection, version pinning, and upgrades must remain understandable.
7. **Native value** — retain Flutter/Dart where native integration, shared application state, performance, accessibility, packaging, or maintenance is materially simpler there.

This is deliberately not “replace Dart with JavaScript”. A Dart implementation that is lighter to own wins. A browser-standard implementation that removes unnecessary native/platform coupling also wins.

## Platform coverage model

Browser evidence must be labeled by what it actually proves. The core matrix is:

| Surface | Minimum deterministic evidence | Important limitation |
| --- | --- | --- |
| Desktop web / Chromium family | Chromium desktop project | not proof of Firefox/WebKit |
| Desktop web / Firefox | Firefox desktop project | engine-specific behavior remains possible |
| Desktop web / WebKit | WebKit desktop project | Playwright WebKit is not a claim of branded Safari parity |
| Android-oriented mobile web | Chromium + Android/Pixel-style device profile | emulation is not a physical Android device |
| iPhone/iOS-oriented mobile web | WebKit + iPhone-style device profile | emulation is not physical Mobile Safari |
| Responsive/mobile layout | viewport + touch/mobile metadata and UI assertions | viewport-only emulation must not be called full device fidelity |
| Real-device/native boundary | explicit downstream/manual/device-farm evidence when required | belongs outside the deterministic core unless the feature needs it |

The project should cover the **high-value ~80% browser matrix deterministically**: desktop web plus mobile web, Chromium/Firefox/WebKit where applicable, Android-oriented Chromium, and iPhone/iOS-oriented WebKit. The remaining device-specific tail must be named rather than silently implied.

## Three layers of confidence

**Layer 1 — deterministic core:** local fixtures, static pages, browser protocol calls, cross-engine smoke, device profiles, screenshots/metadata. This should be cheap enough to run routinely.

**Layer 2 — product integration:** a real Flutter web build or real chat/product UI, selectors, navigation, storage, routing, uploads, browser APIs, and failure artifacts. Run when the product boundary is relevant.

**Layer 3 — real environment:** physical iPhone/Android, branded Safari/Chrome differences, OS share sheets, camera/photo library, HEIC/EXIF, permissions, PWA/install behavior, and other OS-owned surfaces. Use targeted evidence; do not make every PR pay this cost.

Passing Layer 1 must never be reported as Layer 3 compatibility.

## Layout and responsive contract

“Works in a browser” includes layout reachability, not only successful JavaScript execution. A portable feature should define:

- desktop and mobile viewport expectations;
- controls that remain reachable without hover-only interaction;
- touch-sized/actionable controls where relevant;
- no essential function hidden solely by responsive breakpoints;
- keyboard behavior where desktop users depend on it;
- orientation/viewport changes where the feature is sensitive;
- overflow and long-content behavior;
- accessibility-oriented locators/roles where practical;
- screenshots as visual evidence, while behavioral assertions remain DOM/locator based.

The kit should provide reference profiles rather than application-specific CSS policy. Downstream projects decide exact breakpoints; the kit verifies that declared profiles are exercised and identified in evidence.

## Technology placement

A downstream project can use this decision guide:

| Need | Prefer first | Escalate when |
| --- | --- | --- |
| Shared product/business rule already natural in Flutter | Dart | browser-only boundary makes native ownership unnecessarily heavy |
| Browser interaction/E2E | Playwright Node or Python | agent reasoning is specifically being evaluated |
| Static HTML/render proof | Playwright's own CLI | interaction/state requires API/Test runner |
| Agent-oriented browser experiment | Stagehand v4, opt-in | never replace deterministic core solely with agent behavior |
| Small browser-native helper | Web standard / small JS/TS | framework/runtime adds clear value |
| Lightweight script/tooling | stdlib Python or existing project runtime | dependency is justified by the contract |
| JS runtime/service tooling | existing Node ecosystem | Deno materially simplifies distribution/dependency/permissions for that boundary |
| Cross-platform UI shell | Flutter/Dart where it remains simplest | web-first implementation gives the same reach with materially lower ownership cost |

Node, Deno, Python, and Dart can coexist, but every extra runtime must have a reason. “Available” is not enough; it should reduce total complexity or provide evidence unavailable from the existing layer.

## Downstream adoption: flutter_navigation_basic

The first proving ground for this doctrine should be `flutter_navigation_basic`.

Its architectural review should ask feature-by-feature:

- Is this genuinely a Flutter/native concern, or simply a capability users need from any available browser?
- Can the function be reached on desktop web and mobile web without an app-store/native-only path?
- What evidence exists for Chromium, Firefox, WebKit, Android-oriented Chromium, and iPhone/iOS-oriented WebKit?
- Does the feature depend on file/photo APIs, clipboard, share, camera, location, storage, download, or another browser/OS boundary that needs targeted platform evidence?
- Is the Dart implementation still the lightest source of truth?
- Would extracting a browser-standard helper reduce dependencies or duplicate platform code?
- If Node/TS/Deno/Python is introduced, does it replace complexity rather than merely add another implementation?
- Which tests belong to deterministic browser-test-kit contracts, and which remain product-specific Flutter E2E tests?

The desired result is **not** “less Flutter” by itself. It is a Flutter-based product whose useful capabilities are intentionally exposed and verified as a multi-platform application, with native-specific code only where native-specific value exists.

## Evidence metadata for downstream claims

Every reusable browser artifact should make the claim boundary visible. Prefer metadata containing at least:

- runtime and test lane;
- browser engine/project;
- desktop/mobile profile;
- viewport;
- emulation level (`full`, `partial`, or another explicitly defined value);
- stage reached;
- artifact path;
- repository/commit when generated in CI.

When physical-device evidence is added later, record OS/device/browser separately rather than overloading the Playwright project name.

## Anti-patterns implied by the doctrine

The central catalog should cover these concepts, reusing existing IDs where possible:

- **LANGUAGE_AS_GOAL** — preserving a language/framework becomes more important than platform reach or ownership cost.
- **MULTI_PLATFORM_BY_SINGLE_ENGINE** — one desktop Chromium pass is described as multi-platform support.
- **EMULATION_EQUALS_DEVICE** — a Playwright device descriptor is reported as physical-device proof.
- **WEBKIT_EQUALS_SAFARI** — already represented; keep the distinction explicit.
- **VIEWPORT_EQUALS_MOBILE** — responsive viewport alone is treated as mobile-browser fidelity.
- **DUPLICATE_PLATFORM_IMPLEMENTATION** — the same business rule is independently implemented in Dart and JS/Python without a platform reason.
- **RUNTIME_FOR_NOVELTY** — Node/Deno/Python/Dart is introduced without reducing complexity or adding a necessary capability.
- **NATIVE_ONLY_BY_DEFAULT** — a browser-reachable feature is made native-only without a product requirement.
- **FULL_E2E_FOR_EVERY_CONTRACT** — every assertion boots the complete app even when static/protocol/unit evidence is sufficient.
- **LAYER1_EQUALS_REAL_DEVICE** — deterministic emulation results are promoted into real-device compatibility claims.

## Definition of success for browser-test-kit

The repository can credibly call itself an aggregation point when a downstream maintainer can come here to answer, from one place:

1. which browser/platform surface a test actually proves;
2. which Node/Python/CLI/agent pattern fits that proof;
3. which anti-patterns have already failed in sibling repositories;
4. how evidence should be captured and named;
5. what remains unproven by emulation;
6. how to decide whether functionality belongs in Flutter/Dart or a lighter browser-oriented boundary;
7. how to carry the same contracts into desktop web, mobile web, Android-oriented browsers, and iPhone/iOS-oriented browsers.

That is the standard PR #3 should move toward. Centralization means **one decision vocabulary and evidence model**, not necessarily one implementation language.
