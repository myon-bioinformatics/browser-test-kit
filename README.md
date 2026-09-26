# browser-test-kit
Cross-browser testing reference kit for Playwright Node/Python, Stagehand, Replay, screenshots, mobile web, and GitHub Actions.

## Fast Init

This repository is documentation-first before browser implementation. The first PR records the cross-repository evidence, failure taxonomy, screenshot validation rules, and Node/Python policy that later implementation must follow.

Initial implementation target:
- Playwright Node/TypeScript and Playwright Python API/CLI as equal reference lanes.
- Chromium, Firefox, and WebKit, with explicit desktop/mobile profiles.
- Screenshot evidence validated by command result, file existence/size, PNG signature, and human-inspectable CI artifacts.
- Stagehand v4 Python as an optional agent-oriented lane, not a replacement for deterministic Playwright.
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
- **MISSING_FAILURE_ARTIFACTS:** retain screenshot/trace/video/logs on failure where useful.

### Provenance

The initial rules were distilled from working patterns and incidents in `mcp-toolcall-lab`, `flutter_navigation_basic`, `web-ui`, `markdown`, and `Ironmate`.

Notable portable lessons include WebKit producing a PNG before a non-zero shutdown, browser-config/install parity tests, exact Playwright CLI argv regression tests, staged visual-regression rollout, `python -m playwright screenshot` for simple Python CLI capture, and keeping Stagehand separate from deterministic Playwright.

### Incident record format

When a new repository teaches a reusable lesson, record: repository/PR, runtime (Node/Python/Stagehand/Replay), browser, device/profile, failure stage, observed symptom, root cause, fix, regression guard, and portable lesson.

### Page text without a browser (`scripts/page_text.py`)

Stdlib-only static extraction (runs under `python -S`) in the shape of a browser `get_page_text`: `Title:`, `URL:` (after redirects), `Source element:`, then the text.

```bash
python scripts/page_text.py https://example.com/ --max-chars 20000
python scripts/page_text.py fixtures/index.html --json
curl -sL https://example.com/ | python scripts/page_text.py - --url https://example.com/
python scripts/page_text.py <URL> --find "status page"
```

- The text comes from the first `<main>`, else the first `<article>`, else `<body>`; `script`, `style`, `noscript`, `template`, and `svg` are dropped with their contents.
- Line breaks follow `innerText` for each element's default display: a blank line around `<p>`, a new line for other block elements and `<br>`, and a tab between table cells. `<pre>` keeps its indentation, whitespace runs collapse to one space, and blank-line runs collapse to one.
- `--find` lists links, buttons, headings, and `[role=link|button]` elements whose text, `aria-label`, or `title` contains the query (case-insensitive), with hrefs resolved to absolute URLs. No match exits 1.
- `--json` adds `truncated`, `total_chars`, `bytes`, `status`, and `fetched_at`. `--max-chars`, `--max-bytes`, and `--timeout` bound the work.
- Exit codes: 0 OK; 1 no `--find` match, or an HTTP error status (the page is still printed; a 404 adds a `LOGIN_WALL_AS_404` hint); 2 usage, input, or network error.
- JavaScript is not run and CSS is not evaluated, so an empty result on a single-page app is `PAGE_TEXT_AS_RENDERED_TEXT`, not an empty page. Core tests use only local fixtures and a local HTTP server.

### Planned sequence

1. Documentation/evidence contract.
2. Shared local deterministic fixture and artifact validators.
3. Playwright Node matrix.
4. Playwright Python API + CLI matrix.
5. Cross-runtime/browser parity guards.
6. Stagehand v4 Python optional lane.
7. Replay optional lane.
8. Reusable workflow/template examples.
