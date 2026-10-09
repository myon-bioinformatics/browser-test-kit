# Optional browser DOM capture

This example belongs to the browser-testing lane. It uses the repository's existing
`requirements-test.txt` Playwright dependency and Chromium installation, rather
than adding a browser dependency to gh_identity or the stdlib scripts.

```sh
python examples/capture_browser_dom.py https://chatgpt.com/ --selector h1 --output chatgpt-dom.json
python examples/capture_browser_dom.py http://127.0.0.1:7860 --selector '#dom-lab-body' --output local-dom.json
```

The sample opens a fresh isolated context, navigates once, requires a unique
selector, and stores HTML, textContent, innerText, source URL/time and hash. It
does not log in, submit, accept consent or retry. Normal page subresources run.
Output is historical evidence, not content validation: `content_verified` is false.
Limits apply per operation and to selected output after collection, not all
network traffic/memory. Existing evidence files are not overwritten. Exit 0 means
captured, 1 ambiguous selection, 2 error. `--headed` shows the temporary browser.

Use existing `scripts/page_text.py` for static extraction without a browser.
GHI's selected-body HTML reader remains a separate downstream consumer. No GHI
import or vendor update is required here. Local fixture coverage runs in the
existing Python Playwright CI lane; external sites are not core test fixtures.
CLI preflight passed locally; real Chromium execution awaits that CI lane because
the authoring environment has no installed Playwright/browser binaries.
