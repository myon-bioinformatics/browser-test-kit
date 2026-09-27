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
- **Ctrl-C in the default (inherited-stdio) mode is handed to the child, not
  used to kill it.** The wrapper installs a SIGINT handler around the child's
  run that only records the interrupt instead of raising `KeyboardInterrupt`.
  The child receives the same SIGINT directly, because it shares the
  wrapper's foreground process group, and decides for itself how -- and how
  quickly -- to clean up and exit; the wrapper does not SIGKILL it. Once the
  child exits, `terminal_browser_exit` reports `interrupted: true` and a
  `returncode` that simply follows the child's own exit, normalized the same
  way as any other exit: a child that dies from the SIGINT itself still
  reports `returncode: 130` with `signal: 2`, while a child that catches the
  signal, cleans up, and exits some other way reports that exit code instead.
  Earlier versions of this wrapper let `subprocess.run`'s default
  `KeyboardInterrupt` handling SIGKILL the child immediately, which could
  leave an interactive TUI's terminal state (raw mode, alternate screen, ...)
  broken; this no longer happens in the default mode.
- `--log` (non-interactive capture) mode keeps the old immediate-abort
  behavior, since there is no interactive terminal state to protect there: a
  Ctrl-C still raises `KeyboardInterrupt`, and the wrapper reports
  `terminal_browser_exit` with `returncode: 130` and `interrupted: true`
  right away, without waiting on the child.
- A child terminated by a signal is normalized to `128 + signal`; for example,
  SIGTERM (signal 15) exits 143. The `terminal_browser_exit` event records the
  signal number in `signal`.
- `--log` mode decodes the child's combined stdout/stderr as UTF-8 with
  `errors="replace"`, so non-UTF-8 output is captured (with `�` in place
  of the invalid bytes) instead of crashing the wrapper.
- `--check` cannot be combined with `--log` or child arguments.
- Child arguments beginning with `-` must be passed after `--`, for example
  `-- --version`.
- Wrapper lifecycle events are JSONL on stderr with
  `source: "terminal-browser"`; child output remains on stdout in the default
  inherited-stdio mode.

## Non-interactive subcommand wrappers

We looked for real, documented non-interactive terminal-browser subcommands
(`action`, `dump`, `screenshot`, `eval`, ...) to add thin exact-argv wrappers
around, the way `--check` wraps discovery. We could not confirm any exist:

- npm, pip, and cargo were checked through the proxy. `npm view terminal-browser`
  resolves to a same-named package (`terminal-browser@1.0.2`, published by
  `martieeeese`), but pip and cargo have no matching package.
- That npm package installs and runs, but its `bin/dist/index.js` is five
  lines that unconditionally `render(<App />)` an Ink TUI -- it has no
  argument parsing at all (no `--help`, no `--version`, no subcommands), and
  it fails immediately outside a real TTY (`Raw mode is not supported on the
  current process.stdin`). It does not expose `open <url>`, `action --help`,
  or `-- --version` the way this document describes, so it does not match the
  interface `scripts/terminal_browser.py` targets.
- We could not confirm this npm package is the same project as
  [zenbu-labs/terminal-browser](https://github.com/zenbu-labs/terminal-browser)
  (no `repository` field ties them together), and we did not clone that
  GitHub repository to check, per this task's constraints.

Because we could not exercise a confirmed-real non-interactive subcommand, no
subcommand wrappers were added here. `scripts/terminal_browser.py` continues
to pass whatever argv the caller gives it straight through (`open ...`,
`action --help`, `-- --version`, ...) rather than inventing flags; that
generic passthrough is designed to already cover a real `action` interface
once one can be confirmed and installed in this environment (or in CI).

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

## Next steps

What this CI lane still cannot prove, and what closing each gap would need:

- **Rendered TUI output.** Everything tested here (`--check`, `--log`
  capture, the SIGINT/exit contract) runs terminal-browser as a plain child
  process; none of it drives or inspects the actual Ink-rendered terminal UI
  in the default inherited-stdio mode. Proving the renderer itself works
  needs a real or emulated TTY (for example a `pty`/`pexpect`-style harness,
  or a `script`/`tmux` session) plus something that can assert on terminal
  contents (a screen buffer or ANSI-aware snapshot), not just process exit
  codes and stderr JSONL.
- **A confirmed-real non-interactive subcommand surface.** We could not
  install or verify the actual `zenbu-labs/terminal-browser` tool in this
  environment (see "Non-interactive subcommand wrappers" above), so
  `action`/`dump`/`screenshot`-style wrappers remain unbuilt and untested
  against real output. Closing this needs either network access to the real
  package/binary this kit is meant to install, or an explicit stub contract
  from upstream (a documented, versioned CLI reference) that this repo can
  test against without guessing flags.
- **The Ctrl-C handoff under a real interactive child.** The new tests cover
  the handoff with a POSIX shell stand-in (`trap`, `sleep`, explicit `exit`
  codes) and a mocked `subprocess.run`. They do not exercise a process that
  actually puts the terminal into raw mode / an alternate screen and restores
  it on SIGINT, which is the scenario the fix is for. Proving that end-to-end
  needs the real tool (or a small fixture binary that mimics raw-mode/altscreen
  terminal state) running under a real or emulated TTY, plus a way to assert
  the terminal was left in a sane state afterward.
- **The `docs/terminal-browser.md` incident-linkage claim.** The `flutter_navigation_basic`
  #95 discussion above is deliberately framed as motivation rather than proof;
  actually validating the "visible, product-side Chromium symptom" claim needs
  a real incident where this lane was used to reproduce something Playwright's
  headless matrix did not catch, recorded here as it happens.
