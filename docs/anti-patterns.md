# Browser testing anti-patterns

This repository starts from observed browser-testing failures rather than from a preferred framework.

## Evidence rules

A browser command exiting successfully is not sufficient evidence by itself. Keep the command log and validate the artifact that matters.

For screenshots, the minimum useful contract is:

1. the browser command was attempted and its exit status is recorded;
2. the expected file exists and is non-empty;
3. the file signature matches the declared image format (PNG: `89 50 4e 47 0d 0a 1a 0a`);
4. dimensions/viewport/device/browser are recorded when they matter;
5. CI uploads the image and relevant logs for human inspection.

Screenshots are visual evidence, not a selector strategy. Prefer DOM/accessibility/locator state for interaction assertions, and screenshots for layout, rendering, canvas/chart content, and bug evidence.

## Stable anti-pattern catalogue

| ID | Anti-pattern | Failure mode | Preferred pattern |
| --- | --- | --- | --- |
| `EXIT_ZERO_ONLY` | Treating exit code 0 as proof of a valid screenshot | Empty/corrupt/wrong artifact can pass | Validate existence, size, signature, then retain artifact |
| `NONEMPTY_IMAGE_ONLY` | Checking only `test -s` | Non-image bytes can pass | Check magic bytes; optionally dimensions |
| `BROWSER_MATRIX_DRIFT` | Config declares Chromium/Firefox/WebKit while CI installs fewer browsers | Works locally/config looks complete, CI fails or silently skips coverage | Test config/install parity |
| `ONE_ENGINE_ASSUMPTION` | Chromium success is treated as cross-browser success | WebKit/Firefox-specific regressions escape | Keep explicit engine lanes |
| `SAFARI_EQUALS_WEBKIT` | Calling Playwright WebKit “Safari” | Overstates fidelity | Say WebKit; document when macOS/Safari fidelity matters |
| `MOBILE_VIEWPORT_ONLY` | A narrow viewport is treated as a real mobile profile | UA/touch/device scale/browser engine differences are missed | Use named device emulation where appropriate and record the profile |
| `DEVICE_DESCRIPTOR_CROSS_ENGINE` | Reusing one named device descriptor unchanged across every browser engine | Engine-specific context options can fail at launch/context creation (for example Firefox rejects Playwright `is_mobile`) | Treat device descriptors as engine-sensitive; adapt unsupported options explicitly and regression-test the adaptation |
| `SCREENSHOT_AS_SELECTOR` | Acting on pixels/screenshots when DOM/locator evidence exists | Brittle automation | Interact through locators/snapshots; screenshot for visual evidence |
| `STALE_ELEMENT_HANDLE_WAIT` | Polling a captured node while a framework replaces it | Timeout although visible DOM is correct | Re-query locator/selector during polling |
| `SILENT_CLEANUP_EXCEPTION` | Cleanup/diagnostic exceptions are swallowed | Original failure loses its evidence | Preserve logs and report cleanup failures without masking root cause |
| `CLI_ARG_GREEDINESS` | Wrapper constructs ambiguous Playwright CLI argv | Project/file args are consumed incorrectly | Unit-test exact argv construction; prefer explicit `--project=...` forms |
| `BROWSER_BINARY_MISMATCH` | Python/Node package revision and installed browser binary drift | Launch failure in CI/sandbox | Install browsers from the same Playwright version; expose intentional executable override only when needed |
| `EXTERNAL_SITE_AS_CORE_FIXTURE` | CI depends on a third-party page | 403/429/network failures masquerade as product regressions | Core tests use local deterministic fixture; external evidence is a separate lane |
| `FAILURE_LAYER_FLATTENING` | Browser, network, app and artifact failures all become generic failure | Diagnosis becomes slow | Emit stage/browser/runtime/URL/artifact metadata |
| `VISUAL_DIFF_TOO_EARLY` | Pixel baseline is made blocking before deterministic capture is stable | Noisy CI | First validate candidate screenshots; promote stable baselines later |
| `NODE_OR_PYTHON_MONOCULTURE` | One Playwright binding is presented as the only reference | Other repos cannot reuse the pattern naturally | Maintain equivalent Node and Python examples with shared semantics |
| `AGENT_REPLACES_DETERMINISTIC_TEST` | Stagehand/agent lane replaces deterministic Playwright checks | Model/external variability weakens regression signal | Keep Stagehand optional and separate from deterministic Playwright |
| `MISSING_FAILURE_ARTIFACTS` | Screenshot/trace/video exists only on success or is discarded on failure | Hardest failures are least observable | Retain-on-failure screenshot/trace/video where useful |

## Observed source patterns in this organization

These are intentionally generalized; copy the lesson, not necessarily the original implementation.

- `mcp-toolcall-lab`: WebKit screenshot commands can produce a PNG even when shutdown reports non-zero. The workflow therefore records the exit status and validates the PNG signature before deciding whether useful evidence exists.
- `browser-test-kit` PR #2: applying Playwright's `iPhone 13` descriptor unchanged to Firefox failed because Firefox does not support the `is_mobile` BrowserContext option. The compatibility layer now removes only that unsupported option for Firefox while retaining the remaining mobile-profile settings, with a regression test for the distinction.
- `flutter_navigation_basic`: browser configuration and CI/Docker installation drift was prevented with a regression test that checks Chromium, Firefox, and WebKit parity. Its Playwright config also retains trace on first retry, screenshot only on failure, and video on failure.
- `flutter_navigation_basic`: the Python stdlib CLI wrapper has regression tests for the exact Node Playwright argv shape; this caught the CLI's project-argument parsing behavior.
- `web-ui`: visual regression was deliberately staged: first validate deterministic candidate screenshots, then require baselines after the capture lane is trustworthy.
- `web-ui`: Stagehand v4 is treated as an optional agent-oriented lane beside deterministic Playwright, not as its replacement.
- `markdown`: simple HTML rendering uses `python -m playwright screenshot` rather than writing a custom browser program when the CLI is sufficient. More interactive UI tests use the Python API.
- `markdown`: existing anti-pattern documentation records stale element handles and swallowed cleanup exceptions as browser-debugging hazards.
- `Ironmate`: a small screenshot lane shows the value of parameterizing Playwright version/browser rather than burying them in commands.

## Failure record template

When a new incident teaches something reusable, append a short record:

```text
ID:
Repository / PR:
Runtime: node | python | stagehand | replay
Browser: chromium | firefox | webkit | replay-chromium | other
Device/profile:
Stage: install | launch | navigate | interact | assert | screenshot | artifact | cleanup
Observed:
Root cause:
Fix:
Regression guard:
Portable lesson:
```

Do not store secrets, transient tokens, or large binary artifacts in this document.
