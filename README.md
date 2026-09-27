# browser-test-kit
Cross-browser testing reference kit for Playwright Node/Python, Stagehand, Replay, screenshots, mobile web, and GitHub Actions.

## Fast Init

Implementation is staged by evidence layer. Deterministic Node/Python Playwright lanes are already implemented; optional agent/exploratory lanes remain separate and must not be described as proven until their own contracts are measured.

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

### GitHub operations without `gh` (`scripts/gh_ops.py`)

Stdlib-only (`python -S`) REST helpers for PR/CI work where the `gh` CLI is unavailable. Read-only by default; writes need `--write` and re-check their preconditions first. Token: `GITHUB_TOKEN` (fallback `GH_TOKEN`), never printed. Exit codes: 0 OK, 1 condition not met, 2 input/communication error.

```sh
python -S scripts/gh_ops.py issue-comments OWNER/REPO 24 --save comments.json   # one line per comment
python -S scripts/gh_ops.py issue-comments OWNER/REPO 24 --show 6,18            # full text of selected comments
python -S scripts/gh_ops.py comments-file saved-tool-result.txt --last 5        # same digest from a saved JSON dump, offline
python -S scripts/gh_ops.py pr-for-branch OWNER/REPO my-branch                    # existing PR for a branch? merged? (none -> exit 1)
python -S scripts/gh_ops.py open-prs OWNER [--org] [--repos a,b]               # open PRs across repositories, newest first
python -S scripts/gh_ops.py checks-wait OWNER/REPO <sha> --min 5
python -S scripts/gh_ops.py pr-merge OWNER/REPO 11 --sha ecfd0ba --min-checks 5 --method squash --write
python -S scripts/gh_ops.py pr-body-set OWNER/REPO 11 --file body.md --write     # replace the whole PR body
python -S scripts/gh_ops.py pr-edit OWNER/REPO 11 --title "New title" --write    # PATCH title/base/state (draft/ready needs GraphQL)
python -S scripts/gh_ops.py file-put OWNER/REPO path/to/file --from local.txt --branch my-branch --message "msg" --write
python -S scripts/gh_ops.py url pr OWNER/REPO 11 --tab checks                    # build a github.com/api URL; no network
```

Also: `pr-status`, `runs`, `workflow-state`, `workflow-dispatch`, `pr-body-replace`, `sync-main`. Every subcommand is a function (`from gh_ops import pr_merge`) returning a dict; the CLI is a thin adapter.

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
python scripts/terminal_browser.py --check        # verified: discovery + JSONL events
python scripts/terminal_browser.py -- <args...>   # passes args through unchanged
```

Upstream [zenbu-labs/terminal-browser](https://github.com/zenbu-labs/terminal-browser) documents `open <url>`, `action`, `ls`, and `upgrade`, installed via its own install script or Homebrew -- not the npm `terminal-browser@1.0.2` package, which is an unrelated same-name project. This repo's CI does not exercise the real upstream tool, so the wrappers here remain unverified against it. Arguments are forwarded as-is; see "Non-interactive subcommand wrappers" in docs/terminal-browser.md.

### Evidence events (btk-event/1)

See [`docs/evidence-events.md`](docs/evidence-events.md) for the shared JSONL
event contract (schema `btk-event/1`) that `scripts/terminal_browser.py`
emits, that the opt-in `scripts/pytest_btk_events.py` pytest plugin writes
per test, and that `scripts/evidence_board.py` aggregates into a Markdown
table, `--json`, or a GitHub Step Summary. Nothing here loads implicitly:
there is no `conftest.py`, and the plugin only runs when a project opts in
with `pytest -p pytest_btk_events --btk-events PATH`.
