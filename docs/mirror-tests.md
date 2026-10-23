# Mirror tests (no browser)

A **mirror test** asks two or more independent implementations the same question about
one artifact and checks that they agree: ExcelJS, SheetJS and a stdlib OOXML reader
reading one workbook; your Markdown helper, markdown-it and marked reading one file.
No side is the oracle. Agreement is evidence; a disagreement is a lead to look at.
It needs Node and a few npm packages (megabytes), not a browser download.

```sh
npm ci                                   # markdown-it, marked, linkedom, exceljs (devDependencies)
node scripts/mirror_facts.mjs markdown README.md                    > it.json
node scripts/mirror_facts.mjs markdown README.md --reader marked    > marked.json
python -S scripts/mirror_check.py compare ours.json it.json marked.json

node scripts/mirror_facts.mjs xlsx book.xlsx --reader exceljs       > exceljs.json
python -S scripts/mirror_check.py facts xlsx book.xlsx              > stdlib.json
python -S scripts/mirror_check.py compare exceljs.json stdlib.json
```

`compare` prints one `diff KEY READER vs CONSENSUS` line per deviating reader (what only
it has, what it lacks), or `split` lines when every reader answers differently.
Exit 0 = all agree, 1 = deviation, 2 = input error / cannot compare.
Before comparing, every input must be a JSON object with `schema: "mirror-facts/1"`,
the same supported `kind` (`markdown`, `html`, or `xlsx`), and **all** list keys for
that kind in the table below. Missing/non-list keys and mixed kinds return 2 with
`cannot compare`, never `all agree`. `compare()` raises `ValueError` for these inputs.
At least two documents and at least one fact in their required lists are needed;
fully empty outputs return 2. An empty individual list is valid (e.g. no images);
an empty list versus a populated list is a deviation (exit 1).
Additional list keys are compared only when all readers provide them as lists;
a partial extension is also an input error. Other metadata is ignored.

## Facts (`mirror-facts/1`)

| kind | readers | keys |
| --- | --- | --- |
| `markdown` | `markdown-it` (CommonMark), `marked` (GFM: also autolinks bare URLs) → `linkedom` | `headings` [level, text], `links` [href], `images` [src, alt], `code` [language, text] |
| `html` | `linkedom` | same as markdown |
| `xlsx` | `exceljs`, `sheetjs` (optional), `python-stdlib-ooxml` (`mirror_check.py facts xlsx`) | `sheets`, `cells` [sheet, ref, value] (cached formula results; dates as Excel serials), `formulas`, `merges` |

Your own implementation joins by printing the same JSON shape. Values are compared
after normalization (inline Markdown and tags removed from text, `<url>` brackets
removed, numbers rounded to 9 digits), as multisets.

Reader semantics that differ and are normalized away: ExcelJS repeats a merge's
master value on every covered cell (only the master is reported); SheetJS needs
`sheetStubs` to keep a formula that has no cached value. Semantics that are **not**
normalized because they are real dialect differences: marked (GFM) turns bare URLs
into links, markdown-it (CommonMark) does not.

SheetJS is optional: the npm `xlsx@0.18.5` build is old and has advisories for
crafted input, and the maintained build is published only on `cdn.sheetjs.com`
(`npm i --no-save https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz`). Use it to read
files you produced, not untrusted ones.

## What it found on the first run

Run over myon-bioinformatics/markdown's own docs and fixtures (markdown.py vs
markdown-it vs marked): headings, links and images inside fenced code blocks are
reported by `extract_sections` / `extract_links` / `extract_images` (e.g. a
`# comment` in a Python sample becomes a level-1 heading), and the autolink
`<https://...>` is not reported by `extract_links`. Both renderers agree on these.

## Lighter Playwright where a browser is still needed

`playwright install chromium` downloads the full Chromium **and** the headless shell
(measured for Playwright 1.63: 597 MB + 323 MB). Headless runs (the default) only
launch the headless shell, so a job that never opens a headed window can use

```sh
npx playwright install --with-deps --only-shell chromium
```

and skip the unused 597 MB. `--headed` runs still need the full build.
Firefox/WebKit are unaffected. `npx playwright screenshot` / `pdf` also launch the
headless shell. The opposite case: a config with `channel: 'chromium'` (new headless)
launches the full build only, so install it with `--no-shell` and skip the 323 MB shell.
A job that does both needs neither flag. `platform-matrix` launches Chromium headless
for each profile (`platform_probe.py collect` defaults to `headless=True`) and then
again with `--headed` under `xvfb-run` on Linux, so its install stays

```sh
python -m playwright install --with-deps chromium firefox webkit
```

## Mirror candidates elsewhere

| artifact | local implementation | independent readers |
| --- | --- | --- |
| Markdown structure | markdown `extract_*` | markdown-it, marked (+ linkedom) |
| HTML → Markdown | BlueProbe, portfolio `pixiv_markup` | Turndown, @mozilla/readability |
| PPTX / XLSX | Ironmate `pptx_xml`, openpyxl | JSZip + XML, ExcelJS, SheetJS, python-pptx |
| PNG difference | flutter `tool/python/image_diff.py` | pixelmatch (what Playwright's screenshot assertion uses) |
| SVG → PNG | Ironmate `svg_raster` | resvg-js |
| East Asian width | markdown, ascii_artist | string-width |
| Edit distance | flutter `search_patterns` | fastest-levenshtein |

## Vendoring `*.min.js`

Keep libraries as pinned npm devDependencies for tests. Vendor a `*.min.js` (with
commit/sha256 in `vendor.lock.json`) only for code a published page loads on every
visit; anything else stays a devDependency or a version-pinned CDN URL.

## Separate browserless execution

The existing mirror tests now run once in a dedicated runner configuration, without
installing any Chromium, Firefox or WebKit executable:

```sh
npm ci --ignore-scripts
npm run test:browserless
```

The Playwright **test runner package** is reused; these tests request no browser
fixtures. This changes execution, not the document readers or comparison contract.
The normal `npm run test:node` retains the real browser projects.

Python rules and CLI tests can run without even the Python Playwright package:

```sh
uv run --locked python -m pytest tests/python -q -m 'not browser'
```

Tests that launch browsers, including CLI subprocesses, carry `@pytest.mark.browser`.
Imports of Playwright are inside those tests, so collecting the fast lane needs no
browser package. A regular unfiltered pytest run still collects both lanes.
For actual browser integration, include the `browser` dependency group and the documented
browser engines, then use `uv run --locked --group browser python -m pytest tests/python -q -m browser`.

CI runs the existing Python rules, reconstructed-vendor baseline and Node mirrors
first. Only after all three pass do the Node and Python browser jobs install their
engines. The reconstructed-vendor job runs the non-browser suite, rather than
installing all three engines and repeating the same browser assertions. The checked-in
vendor files are still exercised by the complete browser matrix. Shared change
detection, locked provenance and the parent's JUnit collector remain in use.
JUnit from the Python core, controlled failures, browser integration and Node mirrors
is preserved separately. No browser test has been removed or turned into a skip.
Full browser checks still run on eligible PRs and main pushes after the fast gates;
this change does not add a schedule or infer that a browser is unnecessary from a
filename alone. Mark future real-browser tests explicitly, including browser launches
hidden behind subprocess helpers.
