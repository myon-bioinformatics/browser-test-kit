# terminal-browser lane

[terminal-browser](https://github.com/zenbu-labs/terminal-browser) is an optional,
real-Chromium CLI/TUI lane beside deterministic Playwright. It is intentionally
not a replacement for the Chromium/Firefox/WebKit matrix.

## Why it belongs here

The kit needs a fast way for a developer or coding agent to open the same local
fixture or application that later receives the full Playwright matrix. The
`terminal-browser action` interface also gives agents a CLI-oriented interaction
surface over an already-open terminal-browser.

This lane is **optional/non-blocking first** because terminal-browser needs a
supported terminal environment for rendered interactive use. CI therefore tests
our wrapper contract without pretending that a headless Actions runner proves
the interactive renderer.

## Install and run

Install using an upstream-supported installation method, then verify discovery:

```sh
python scripts/terminal_browser.py --check
```

For interactive use, run through the wrapper so the child inherits the real
terminal stdin/stdout/stderr:

```sh
python scripts/terminal_browser.py open http://127.0.0.1:8000
```

Start the repository's local server first. Keep Playwright for deterministic
assertions and the cross-browser matrix.

Structured lifecycle events are JSONL on **stderr**, separate from the child
process's normal stdout. Each event includes `source: "terminal-browser"`,
UTC `time`, and `event`.

`--log` switches the child to capture mode and writes combined child
stdout/stderr to a file. It is intended for **non-interactive commands** such as
`action --help`; do not use capture mode as proof of TUI rendering:

```sh
python scripts/terminal_browser.py --log test-results/terminal-browser/action.log action --help
```

When a terminal-browser top-level argument starts with `-`, use the explicit
wrapper delimiter so argparse cannot consume it:

```sh
python scripts/terminal_browser.py -- --version
```

## Exit and event contract

- A missing executable exits 127 and emits `TERMINAL_BROWSER_UNAVAILABLE`.
  Exit code 127 alone is not sufficient attribution because a discovered child
  process could itself return 127; use the event to identify the wrapper's
  missing-tool case.
- Ctrl-C exits 130 and emits `terminal_browser_exit` with
  `interrupted: true`.
- A child terminated by a signal is normalized to `128 + signal`; for example,
  SIGTERM (signal 15) exits 143. The `terminal_browser_exit` event records the
  signal number in `signal`.
- `--check` cannot be combined with `--log` or child arguments.
- Child arguments beginning with `-` must be passed after `--`, for example
  `-- --version`.
- Wrapper lifecycle events are JSONL on stderr with
  `source: "terminal-browser"`; child output remains on stdout in the default
  inherited-stdio mode.

## Portable incident: flutter_navigation_basic #95

PR #95 is motivation, not retroactive proof. terminal-browser may be useful for
**visible, product-side Chromium symptoms**, for example checking whether an
image accepted by an upload flow renders as expected. It does not prove
parser/regex behavior such as `rejected:un` or `64x32Arm`, Firefox/WebKit or
mobile-chromium differences, or whether a Playwright/Flutter semantics action
represents physical pointer interaction.

For future incidents, record whether a visible product-side symptom was actually
reproduced through this lane before promoting a portable detection claim.

Suggested incident runtime value: `terminal-browser/Chromium`.
