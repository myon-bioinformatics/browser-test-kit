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

The project should cover the **high-value core browser matrix deterministically**: desktop web plus mobile web, Chromium/Firefox/WebKit where applicable, Android-oriented Chromium, and iPhone/iOS-oriented WebKit. The remaining device-specific tail must be named rather than silently implied.

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

The central catalog should cover these concepts, reusing existing IDs where possible. IDs not already present in `anti-patterns.md` below are **candidate / not yet adopted** until explicitly promoted into that stable catalog:

- **LANGUAGE_AS_GOAL** — preserving a language/framework becomes more important than platform reach or ownership cost.
- **MULTI_PLATFORM_BY_SINGLE_ENGINE** — one desktop Chromium pass is described as multi-platform support.
- **EMULATION_EQUALS_DEVICE** — a Playwright device descriptor is reported as physical-device proof.
- **SAFARI_EQUALS_WEBKIT** — existing stable ID; keep the distinction explicit.
- **MOBILE_VIEWPORT_ONLY** — existing stable ID; responsive viewport alone is treated as mobile-browser fidelity.
- **DUPLICATE_PLATFORM_IMPLEMENTATION** — the same business rule is independently implemented in Dart and JS/Python without a platform reason.
- **RUNTIME_FOR_NOVELTY** — Node/Deno/Python/Dart is introduced without reducing complexity or adding a necessary capability.
- **NATIVE_ONLY_BY_DEFAULT** — a browser-reachable feature is made native-only without a product requirement.
- **FULL_E2E_FOR_EVERY_CONTRACT** — every assertion boots the complete app even when static/protocol/unit evidence is sufficient.
- **EMULATION_EQUALS_DEVICE** — deterministic/device-emulated evidence is promoted into physical-device compatibility claims. This single candidate also covers the former Layer-1-vs-real-device wording; do not create a second ID.

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
