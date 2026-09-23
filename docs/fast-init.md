# Fast Init: browser testing knowledge base

## Purpose

`browser-test-kit` is a reusable reference kit for browser testing, browser operation, screenshots, failure evidence, and GitHub Actions.

It is not a wrapper around one product and it does not choose Node over Python. The goal is to collect working patterns and failure lessons that other repositories can adopt selectively.

## Initial lanes

| Lane | Purpose | Initial status |
| --- | --- | --- |
| Playwright Node/TypeScript | Deterministic Node reference | planned |
| Playwright Python API | Deterministic Python reference | planned |
| Playwright Python CLI | Minimal screenshot/browser command reference | planned |
| Stagehand v4 Python | Agent-oriented observe/act/extract experiments | planned, optional |
| Replay | Recorded execution/debug evidence | planned, optional |

The deterministic Playwright lanes remain the baseline. Agent/cloud/external-service lanes must not make the core matrix unreliable.

## Browser/device coverage

The first implementation phase should make the same local fixture observable from both Node and Python through Chromium, Firefox, and WebKit. Desktop and mobile/device-emulated examples should be explicit rather than implied.

Do not describe Playwright WebKit as Safari. It is a WebKit build. Platform-specific behavior and branded browser fidelity are separate concerns.

## Shared semantic scenario

Node and Python should exercise the same behavior rather than merely both launching a browser:

1. open a local deterministic fixture;
2. assert Japanese/Unicode text;
3. fill an input;
4. click a button;
5. wait for deterministic DOM state;
6. capture a screenshot;
7. validate the screenshot artifact;
8. preserve browser/runtime metadata.

This gives future repositories a side-by-side answer to “how do I do the same thing from Node or Python?”

## Evidence contract

Every screenshot-producing example should make success and failure inspectable.

Machine checks:
- exit/exception status;
- expected path;
- non-zero size;
- image signature;
- dimensions when relevant;
- expected DOM/URL state independently of the screenshot.

Human checks:
- upload screenshots to GitHub Actions artifacts;
- retain useful logs;
- give artifacts stable names containing runtime/browser/device;
- keep visual inspection possible even when pixel-diff blocking is not enabled.

For interaction failures, prefer trace/screenshot/video retention where the runtime supports it.

## Failure taxonomy

Use these stages in logs and docs:

`install -> launch -> navigate -> interact -> assert -> screenshot -> artifact -> cleanup`

Also record runtime, browser, device/profile, target URL category (local/external), and artifact path. External 403/429/network failures belong to a different layer from local browser or rendering failures.

## Python and Node policy

### Node

Use Playwright Test for the canonical Node matrix and its projects/reporting/artifact facilities.

### Python

Keep two examples:

- Playwright Python/pytest for real interaction tests.
- Playwright's Python CLI for tasks where a one-command screenshot is sufficient.

The CLI example is intentionally not replaced by a custom Python script: choosing the smallest suitable surface is part of the reference material.

### Stagehand

Start with Python. Keep it optional. It should operate against the same deterministic fixture where possible so agent behavior can be compared with deterministic Playwright behavior.

## Research provenance

The initial documentation was distilled from working patterns in this GitHub organization, especially `mcp-toolcall-lab`, `flutter_navigation_basic`, `web-ui`, `markdown`, and `Ironmate`.

The repository should continue this cycle:

`incident in a project -> portable lesson -> browser-test-kit -> regression example -> adoption by another project`

See [anti-patterns.md](./anti-patterns.md) for the first catalogue.

## Planned implementation sequence

1. Documentation-only Fast Init.
2. Shared deterministic fixture + evidence validators.
3. Playwright Node matrix.
4. Playwright Python API + CLI matrix.
5. Cross-runtime/browser parity checks.
6. Stagehand v4 Python optional lane.
7. Replay optional lane.
8. Reusable workflow/template examples after the behavior is stable.

This order keeps the repository useful as documentation before it becomes another source of CI complexity.
