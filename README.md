# browser-test-kit
Cross-browser testing reference kit for Playwright Node/Python, Stagehand, Replay, screenshots, mobile web, and GitHub Actions.

## Fast Init

This repository is documentation-first before browser implementation. The first PR records the cross-repository evidence, failure taxonomy, screenshot validation rules, and Node/Python policy that later implementation must follow.

Initial implementation target:
- Playwright Node/TypeScript and Playwright Python API/CLI as equal reference lanes.
- Chromium, Firefox, and WebKit, with explicit desktop/mobile profiles.
- Screenshot evidence validated by command result, file existence/size, PNG signature, and human-inspectable CI artifacts.
- Stagehand v4 Python as an optional agent-oriented lane, not a replacement for deterministic Playwright.
- terminal-browser as an optional real-Chromium CLI/TUI exploratory lane for fast local/agent feedback before the deterministic matrix.
- Replay as an optional recorded-execution/debug lane.
- Core CI uses a local deterministic fixture; external network failures remain a separate failure layer.

### Anti-patterns to preserve

The implementation must guard against lessons already observed in sibling repositories:

- **EXIT_ZERO_ONLY / NONEMPTY_IMAGE_ONLY:** exit 0 or `test -s` alone does not prove a valid screenshot; validate PNG magic bytes and useful metadata.
- **BROWSER_MATRIX_DRIFT:** keep configured Chromium/Firefox/WebKit projects in parity with CI/Docker browser installation.
- **ONE_ENGINE_ASSUMPTION:** Chromium green is not cross-browser green.
- **SAFARI_EQUALS_WEBKIT:** call Playwright's engine WebKit, not Safari.
- **MOBILE_VIEWPORT_ONLY:** distinguish a narrow viewport from a named device profile.
- **STALE_ELEMENT_HANDLE_WAIT:** re-query locators when frameworks replace nodes.
- **SILENT_CLEANUP_EXCEPTION:** do not discard the diagnostics needed to understand the original failure.
- **CLI_ARG_GREEDINESS:** unit-test exact wrapper argv, especially Playwright `--project=...` handling.
- **BROWSER_BINARY_MISMATCH:** keep package and installed browser revisions aligned.
- **EXTERNAL_SITE_AS_CORE_FIXTURE:** deterministic core tests must not depend on third-party availability/403/429 behavior.
- **FAILURE_LAYER_FLATTENING:** report whether failure occurred at install, launch, navigate, interact, assert, screenshot, artifact, or cleanup.
- **VISUAL_DIFF_TOO_EARLY:** validate deterministic screenshot candidates before making pixel baselines blocking.
- **NODE_OR_PYTHON_MONOCULTURE:** show equivalent Node and Python patterns rather than selecting one as canonical for every repository.
- **AGENT_REPLACES_DETERMINISTIC_TEST:** Stagehand remains an additional lane.
- **TERMINAL_BROWSER_AS_MATRIX:** terminal-browser is a fast Chromium exploratory lane, not evidence of Firefox/WebKit parity.
- **MISSING_FAILURE_ARTIFACTS:** retain screenshot/trace/video/logs on failure where useful.

### Provenance

The initial rules were distilled from working patterns and incidents in `mcp-toolcall-lab`, `flutter_navigation_basic`, `web-ui`, `markdown`, and `Ironmate`.

Notable portable lessons include WebKit producing a PNG before a non-zero shutdown, browser-config/install parity tests, exact Playwright CLI argv regression tests, staged visual-regression rollout, `python -m playwright screenshot` for simple Python CLI capture, and keeping Stagehand separate from deterministic Playwright.

### Incident record format

When a new repository teaches a reusable lesson, record: repository/PR, runtime (Node/Python/Stagehand/Replay), browser, device/profile, failure stage, observed symptom, root cause, fix, regression guard, and portable lesson.

### Planned sequence

1. Documentation/evidence contract.
2. Shared local deterministic fixture and artifact validators.
3. Playwright Node matrix.
4. Playwright Python API + CLI matrix.
5. Cross-runtime/browser parity guards.
6. Stagehand v4 Python optional lane.
7. terminal-browser optional CLI/TUI lane.
8. Replay optional lane.
9. Reusable workflow/template examples.

### terminal-browser quick lane

See [`docs/terminal-browser.md`](docs/terminal-browser.md). The dependency-free wrapper keeps missing-tool failures explicit and passes upstream CLI arguments through unchanged:

```sh
python scripts/terminal_browser.py --check
python scripts/terminal_browser.py action --help
```
