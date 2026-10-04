# browser-test-kit
Cross-browser testing reference kit for Playwright Node/Python, Stagehand, Replay, screenshots, mobile web, and GitHub Actions.

## Scope

The kit's center is browser testing: Playwright lanes, evidence acquisition and validation, execution strategy, and reproducible diagnostics. It also hosts stdlib-only engineering utilities that the same agents and CI jobs use around that work, such as repository orientation, GitHub/CI operations, log digests, Python-version matrices, HTML fixture building, and explicit-file commits. Every script must run under `python -S`, stay bounded in its output, and have unit tests. A utility that grows its own dependencies or domain belongs in its own repository.

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
python -S scripts/gh_ops.py --json pr-observe OWNER/REPO 24 > before.json     # PR/head/check/review snapshot
python -S scripts/gh_ops.py pr-diff before.json after.json                         # offline meaningful-change events
python -S scripts/gh_ops.py issue-comment OWNER/REPO 24 --file note.md --write     # verified top-level PR comment
python -S scripts/gh_ops.py pr-for-branch OWNER/REPO my-branch                    # existing PR for a branch? merged? (none -> exit 1)
python -S scripts/gh_ops.py open-prs OWNER [--org] [--repos a,b]               # open PRs across repositories, newest first
python -S scripts/gh_ops.py open-issues OWNER [--org] [--repos a,b]             # all open Issues, excluding PRs
python -S scripts/gh_ops.py repo-counts OWNER [--org] [--repos a,b]              # repo / open issues / open PRs / commits
python -S scripts/gh_ops.py --json repo-counts OWNER --repos a,b                # structured rows and totals
python -S scripts/gh_ops.py checks-wait OWNER/REPO <sha> --min 5
python -S scripts/gh_ops.py pr-merge OWNER/REPO 11 --sha ecfd0ba --min-checks 5 --method squash --write
python -S scripts/gh_ops.py pr-body-set OWNER/REPO 11 --file body.md --write     # replace the whole PR body
python -S scripts/gh_ops.py pr-edit OWNER/REPO 11 --title "New title" --write    # PATCH title/base/state (draft/ready needs GraphQL)
python -S scripts/gh_ops.py file-put OWNER/REPO path/to/file --from local.txt --branch my-branch --message "msg" --write
python -S scripts/gh_ops.py url pr OWNER/REPO 11 --tab checks                    # build a github.com/api URL; no network
```

Also: `pr-status`, `runs`, `workflow-state`, `workflow-dispatch`, `pr-body-replace`, `sync-main`. Every subcommand is a function (`from gh_ops import pr_merge`) returning a dict; the CLI is a thin adapter.

`pr-observe` binds the check summary to the PR's current head SHA and records small digests for conversation comments, reviews, and inline review comments. Zero checks are `pending`, never green. `pr-diff` is offline and emits events such as `head_changed`, `ci_became_green`, `ci_failed`, `draft_changed`, `merged`, and review/comment activity changes; it deliberately does not infer semantic labels such as Blocking/Should from prose. `issue-comment` is dry-run by default, first verifies that the number is a PR, and after POST re-reads the created comment. If verification is uncertain it reports that the comment may already exist and tells the caller to inspect before retrying, rather than encouraging duplicate posts.

`repo_counts(owner, org=False, repos=(), client=None)` and `open_issues(...)`
use only REST GETs with the same injectable HTTP transport. Without `--repos`,
they enumerate the user's repositories, or all organization repositories with
`--org`; explicit comma-separated **short repository names** bypass enumeration.
Archived and zero-count repositories are included, duplicate names are counted
once, and rows are sorted by repository name. Every Link `next` page is read,
without the search API's result cap or a silent page limit. The `/issues` response
contains both Issues and PRs: presence of `pull_request` identifies a PR;
`open_issues_count` is never used as an Issue count.

`repo-counts --json` returns `repositories` rows with `repo`, `open_issues`,
`open_prs`, `commits`, and `default_branch`, plus `repository_count`, `totals`,
`owner`, `org`, `ok`, and `commit_scope: "default_branch"`. Commits means all
commits reachable from the default branch, including merge commits, rather than
all branches or just commits in open PRs. Counting reads the complete commit
history, so large repositories may require many requests. An empty Git repository
counts as zero commits; other HTTP errors fail with exit 2 rather than silently
reporting zero or partial counts. Successful empty results exit 0. Reads are
sequential, so activity during collection can change the counts; this is not an
atomic snapshot. `open-issues --json` returns `issues` rows and `total`.

### Screenshot knowledge across repositories

See [docs/screenshot-evidence.md](docs/screenshot-evidence.md) for the shared
capture/validation/publishing procedure, existing validator limits and consumer
adoption map. Application-specific incidents retain source head/run and measured
repair status; the first record covers Flutter diagnostics #128.

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

- The text comes from the first `<main>`, else the first `<article>`, else `<body>`; `script`, `style`, `noscript`, `template`, `svg`, and `textarea` are dropped with their contents, as is the never-rendered fallback content of `iframe`, `noembed`, and `noframes`.
- Line breaks follow `innerText` for each element's default display: a blank line around `<p>`, a new line for other block elements and `<br>`, and a tab between table cells. `<pre>` keeps its indentation, whitespace runs collapse to one space, and blank-line runs collapse to one.
- `--find` lists links, buttons, headings, and `[role=link|button]` elements whose text, `aria-label`, or `title` contains the query (case-insensitive), with hrefs resolved to absolute URLs. No match exits 1.
- `--json` adds `truncated`, `total_chars`, `bytes`, `byte_limit_hit`, `status`, `content_type`, and `fetched_at`. `--find ""` lists every candidate. `--max-chars`, `--max-bytes`, and `--timeout` bound the work.
- Exit codes: 0 OK; 1 no `--find` match, or an HTTP error status (the page is still printed; a 404 adds a `LOGIN_WALL_AS_404` hint); 2 usage, input, or network error.
- JavaScript is not run and CSS is not evaluated, so an empty result on a single-page app is `PAGE_TEXT_AS_RENDERED_TEXT`, not an empty page. Core tests use only local fixtures and a local HTTP server.
- Not implemented yet: an automatic comparison of this static text with the Playwright lane's `inner_text()` (or terminal-browser's rendered text). Run both side by side when rendering matters.

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

### Shared Git inventory and churn

`repo_overview.list_files()` uses the stdlib-only `scripts/git_inspector.py`
from `myon-bioinformatics/myon-bioinformatics` at
`a06641024a782af31bdb51fb0e0d6a1ea21995d0`. The sibling
`git_inspector.provenance.json` records its source path, Git blob SHA-1 and
SHA-256; the vendored Python file is unchanged from upstream.

The combined inventory includes tracked and untracked-but-not-ignored files.
The consumer deduplicates, filters dependency/cache/result directories and
missing/non-file entries, and sorts the final result independently of Git's
order. Missing Git or a failed Git observation retains the directory-walk
fallback (which does not interpret `.gitignore`). A truncated successful
observation raises an explicit error rather than publishing a partial list or
walking ignored files: the shared bounds are 10,000 paths and 1,000,000 bytes.
Direct invocation and installed `python -m repo_overview` still work with
`python -S`; `git_inspector` itself is an import-only shared API.

`repo_overview.churn()` delegates Git execution and numstat parsing to
`log_numstat()`. Commit scanned counts include empty/merge/binary-only commits;
binary file counts remain excluded from ranking. Ranking is still commit count
descending, then raw path ascending, with committer dates and `--since` retained.

Intentional display improvements (covered by before/after fixtures): renames
are attributed to the destination path rather than Git's compact `old => new`
label, without folding earlier old-path history into the destination. Unicode
paths appear as Unicode rather than Git's quoted octal spelling. Control
characters (including tab/newline) use JSON string escaping so each path stays
on one row. Ordinary path output is unchanged. History now has explicit bounds
of 10,000 commits / 1,000,000 bytes: only complete commits count as scanned and
an additional truncation note makes partial-history rankings explicit. The top-N
file omission note remains independent. Missing/failed Git retains the existing
`not a git work tree; skipping --churn` message.

Write/network-capable `gh_ops.py` remains separate rollout work.

Public source placement and automatic Python CI updates: [vendor automation](docs/vendor-automation.md).
