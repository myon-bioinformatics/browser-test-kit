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

Install using the upstream-supported installer on macOS/Linux:

```sh
curl -fsSL https://terminal-browser.sh/install | bash
python scripts/terminal_browser.py --check
terminal-browser open http://127.0.0.1:8000
terminal-browser action
```

For a repository under test, start its local server first and use
`terminal-browser open <url>` for the quick exploratory pass. Keep Playwright
for deterministic assertions and the cross-browser matrix.

The wrapper accepts terminal-browser arguments verbatim and records structured
UTC lifecycle events:

```sh
python scripts/terminal_browser.py --log test-results/terminal-browser/action.log action --help
```

A missing executable exits 127 with `TERMINAL_BROWSER_UNAVAILABLE`, keeping
environment/setup failure separate from launch, navigation, interaction, and
application failures.

## Portable incident: flutter_navigation_basic #95

PR #95 is recorded as motivation, not as a retroactive proof. A quick
real-Chromium exploratory CLI lane could plausibly have exposed the observed UI
problem before the full Playwright path, so future incidents should explicitly
record whether terminal-browser reproduces them. Do not claim that this lane
would have caught an incident until it has been replayed.

Suggested incident runtime value: `terminal-browser/Chromium`.
