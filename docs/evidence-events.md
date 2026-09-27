# btk-event/1: the evidence event contract

This is the event contract a [PR #16](../../../pull/16) review asked for before adding more
terminal-browser features: one JSONL event stream that a pytest plugin, an
aggregate evidence board, the GitHub Step Summary, and incident reports can
all consume, instead of each terminal-browser feature growing its own ad hoc
log shape. It generalizes the JSONL events `scripts/terminal_browser.py`
already emits on stderr (see `docs/terminal-browser.md`) into a shape any
producer in this kit -- or in a project that vendors this kit -- can reuse.

It exists to keep this repo's own anti-patterns
(`docs/anti-patterns.md`) from recurring in the aggregation layer:
`FAILURE_LAYER_FLATTENING` (record which stage failed), `MISSING_FAILURE_ARTIFACTS`
and `EVIDENCE_MASKS_ROOT_FAILURE` (do not let evidence capture hide the real
failure), and `SUCCESS_COUNT_VS_RETRY_ARTIFACTS` (aggregate by identity, not
by raw count).

## Nothing here is implicit

This kit is used across projects. Nothing in this contract is loaded or
applied automatically:

- there is no `conftest.py`; a project that wants `scripts/pytest_btk_events.py`
  opts in explicitly with `pytest -p pytest_btk_events --btk-events PATH`;
- the plugin does nothing at all unless `--btk-events PATH` is given;
- `scripts/evidence_board.py` only reads the JSONL files you pass it.

## Shape

One JSON object per line (JSONL). A producer may write to its own file, or
to stderr the way `scripts/terminal_browser.py` does; consumers read whatever
stream or file they are given.

### Required fields

Every event has all four:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | string | Contract version, always the literal `"btk-event/1"` for this version. |
| `source` | string | Producer identity, e.g. `"terminal-browser"`, `"pytest-btk-events"`. |
| `time` | string | UTC ISO 8601 timestamp (`datetime.now(timezone.utc).isoformat()`). |
| `event` | string | Producer-defined event name, e.g. `"terminal_browser_exit"`, `"test_result"`, `"session_summary"`. |

### Optional fields

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | Opaque id for one execution/run (e.g. a CI run id), to correlate events across files and sources. |
| `test_id` | string | Identifies one test/case, e.g. a pytest nodeid. |
| `project` | string | A sub-project/browser-profile/lane, e.g. a Playwright project name. |
| `stage` | string | One of `install`, `launch`, `navigate`, `interact`, `assert`, `screenshot`, `artifact`, `cleanup` -- the `FAILURE_LAYER_FLATTENING` layers. |
| `status` | string | One of the status vocabulary below. |
| `returncode` | int | Process exit code, normalized the way `terminal_browser.py` already normalizes signal deaths (`128 + signal`). |
| `signal` | int | Signal number, present only when the process died from a signal. |
| `interrupted` | bool | `true` when a person or CI asked the run to stop (Ctrl-C/SIGINT) and the producer is reporting that as a deliberate stop. |
| `artifact` | string | Path to a file the event refers to (screenshot, log, trace, ...). |
| `message` | string | Short human-readable detail, e.g. an exception summary. |

## Status vocabulary

`status` is optional (lifecycle events like `terminal_browser_found` carry no
status), but when present it must be one of exactly these seven values:

- **`passed`** -- the step/test ran to completion and its expectations held.
- **`failed`** -- the step/test ran to completion but did not meet its
  expectation (an assertion failure, or a plain non-zero exit that is not
  itself an infrastructure problem).
- **`error`** -- the step/test could not be evaluated at all because
  something in the harness/fixture/tooling broke: a setup/teardown
  exception, an unexpected signal (SIGSEGV, an externally sent SIGTERM,
  ...), or another wrapper-detected abnormal termination. The distinction
  from `failed` matters: `failed` means the code under test disagreed with
  the assertion; `error` means it never got far enough to disagree.
- **`interrupted`** -- a person or CI explicitly asked the run to stop
  (Ctrl-C/SIGINT) and the producer is honoring that as a deliberate stop
  rather than reporting a failure. Never counted as `passed`, and kept
  distinct from `failed` so a dashboard does not read "someone hit Ctrl-C"
  as "the code is broken".
- **`blocked`** -- the step/test could not proceed because a prerequisite it
  depends on did not hold (an unhealthy fixture/service dependency, a
  required earlier stage that did not reach the state this stage needs).
  Distinct from `unavailable`: `blocked` is an unmet precondition in this
  run; `unavailable` is a tool that is not installed at all.
- **`unavailable`** -- the tool/binary/service the step needed is not
  installed or reachable in this environment, so the step could not even
  attempt to run (for example: terminal-browser is not on `PATH`). It is a
  statement about the environment, not about the code, and is never counted
  as `passed`.
- **`skipped`** -- the step/test was deliberately not run (a skip marker, a
  platform guard). Nothing was attempted and nothing failed.

## Mapping `scripts/terminal_browser.py` exits to `status`

`scripts/btk_events.classify_terminal_browser(event)` implements this, in
this order:

1. `event == "TERMINAL_BROWSER_UNAVAILABLE"` -> **`unavailable`** (the
   wrapper's exit code is 127, but 127 alone is not sufficient attribution
   per `docs/terminal-browser.md`, since a discovered child could itself
   exit 127 -- use the event name).
2. `event == "terminal_browser_exit"` and `interrupted` is true ->
   **`interrupted`**, regardless of `returncode`/`signal`. An interrupted run
   can still exit via the SIGINT it received (`returncode: 130, signal: 2`);
   that stays `interrupted`, not `error`, because the wrapper handed off to
   the child deliberately (see the Ctrl-C handoff in `docs/terminal-browser.md`).
3. `event == "terminal_browser_exit"`, `interrupted` is not set, and `signal`
   is present -> **`error`** (the child died from a signal nobody asked for,
   e.g. an externally sent SIGTERM).
4. `event == "terminal_browser_exit"` and `returncode == 0` -> **`passed`**.
5. `event == "terminal_browser_exit"` and any other `returncode` ->
   **`failed`**.

## Compatibility

- Consumers must ignore fields they do not recognize.
- Producers must never rename or repurpose a field within schema version
  `"btk-event/1"`. A breaking change to a field's meaning ships as a new
  schema string (`"btk-event/2"`), not a silent redefinition.
- New optional fields and new `event` names can be added freely; only
  `status`, when present, is restricted to the vocabulary above.

## Using the board in CI

`evidence_board.py` exit codes:

- **0**: no event has a blocking status (failed, error, interrupted, blocked, unavailable), or every blocking status present is listed in `--allow`.
- **1**: at least one blocking status is not allowed.
- **2**: bad input (a missing or unreadable file, or an unknown status in `--allow`).

`skipped` and `passed` never fail the board. `--allow unavailable` is the usual choice for a CI job where an optional tool such as terminal-browser is not installed; the board still reports those events in its callout line.

Set `run_id` so JSONL files from several jobs or retries can be joined later, for example in GitHub Actions:

```sh
PYTHONPATH=scripts python -m pytest -p pytest_btk_events \
  --btk-events test-results/btk-events.jsonl \
  --btk-events-run-id "$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
python scripts/evidence_board.py test-results/*.jsonl --allow unavailable --step-summary
```

## Reference implementation

- `scripts/btk_events.py` -- `emit()`, `read()`, `classify_terminal_browser()`;
  stdlib-only, importable by any producer or consumer.
- `scripts/pytest_btk_events.py` -- opt-in pytest plugin producer
  (`pytest -p pytest_btk_events --btk-events PATH`).
- `scripts/evidence_board.py` -- aggregator/consumer: Markdown table, `--json`,
  `--step-summary`.
