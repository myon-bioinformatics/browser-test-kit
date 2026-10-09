# Documentation candidates from sibling repositories

Surveyed 2026-10-09. This complements [bioinformatics sources](bioinformatics-sources.md)
with technologies actually declared or described in myon-bioinformatics projects.
The sample covers ten public, non-archived repositories, excluding browser-test-kit
and gh_identity as evidence sources. It is not an exhaustive dependency inventory
or a count of imports, installations or execution frequency.

Evidence links below pin the inspected main commit. Manifest entries establish
declared dependencies; README statements establish documented usage, not proof of
a successful runtime. Optional frontends, test tooling and external clients are
kept distinct from runtime requirements. No dependent repository was modified.

## Runtime, frontend and protocol candidates

| Technology / official documentation | Observed role and pinned evidence | Proposed extraction check |
| --- | --- | --- |
| [Flutter](https://docs.flutter.dev/), [Dart](https://dart.dev/docs), [Flutter API](https://api.flutter.dev/index.html) | SDK and runtime dependencies in [flutter_navigation_basic / pubspec.yaml](https://github.com/myon-bioinformatics/flutter_navigation_basic/blob/da549946839dec5a99c7cd1390cef4164608bcf2/pubspec.yaml) | Class signatures, inherited members, examples and API links |
| [FastMCP](https://gofastmcp.com/getting-started/welcome) | Required runtime dependency, 3.x constraint in [mcp-toolcall-lab / pyproject.toml](https://github.com/myon-bioinformatics/mcp-toolcall-lab/blob/53ae4bf2c3af0178e3eaf30badffbde5e10cc5b7/pyproject.toml) | API signatures, version badges and transport examples |
| [MCP specification](https://modelcontextprotocol.io/specification/latest) | Streamable HTTP and protocol testing described in [mcp-toolcall-lab / README.md](https://github.com/myon-bioinformatics/mcp-toolcall-lab/blob/53ae4bf2c3af0178e3eaf30badffbde5e10cc5b7/README.md) | Protocol version, JSON-RPC examples and normative requirement text |
| [Gradio](https://gradio.app/docs) | Optional galleria extra in [mcp-toolcall-lab / pyproject.toml](https://github.com/myon-bioinformatics/mcp-toolcall-lab/blob/53ae4bf2c3af0178e3eaf30badffbde5e10cc5b7/pyproject.toml); optional frontend in [markdown / requirements-frontend.txt](https://github.com/myon-bioinformatics/markdown/blob/3ed6f2202c8a22680aa8e5fff6716957a34854f9/requirements-frontend.txt) | Component parameters, default values and event examples |
| [Streamlit](https://docs.streamlit.io/) | Optional manual frontend in [markdown / requirements-frontend.txt](https://github.com/myon-bioinformatics/markdown/blob/3ed6f2202c8a22680aa8e5fff6716957a34854f9/requirements-frontend.txt) | API signatures, expandable sections and embedded demo boundaries |
| [Polars](https://docs.pola.rs/) | Declared runtime dependency in [Aoi / pyproject.toml](https://github.com/myon-bioinformatics/Aoi/blob/b86054b1fe50360f665128d87aedbc1f968a6763/pyproject.toml) | Expressions, code/output distinction and tables |
| [HTTPX](https://www.python-httpx.org/) | Runtime in [Aoi / pyproject.toml](https://github.com/myon-bioinformatics/Aoi/blob/b86054b1fe50360f665128d87aedbc1f968a6763/pyproject.toml); test extra in [mcp-toolcall-lab / pyproject.toml](https://github.com/myon-bioinformatics/mcp-toolcall-lab/blob/53ae4bf2c3af0178e3eaf30badffbde5e10cc5b7/pyproject.toml) | Sync/async examples and parameter descriptions |
| [selectolax](https://selectolax.readthedocs.io/en/latest/) | Declared runtime HTML parser in [Aoi / pyproject.toml](https://github.com/myon-bioinformatics/Aoi/blob/b86054b1fe50360f665128d87aedbc1f968a6763/pyproject.toml) | Parser API signatures and literal CSS selectors |
| [OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver) | Optional solver, explicitly marked in [Aoi / sakanalytics/season-requirements.txt](https://github.com/myon-bioinformatics/Aoi/blob/b86054b1fe50360f665128d87aedbc1f968a6763/sakanalytics/season-requirements.txt) | Language-specific code tabs and solver-status semantics |
| [Pillow](https://pillow.readthedocs.io/en/stable/) | Pinned runtime dependency in [convert_img_fmt_to_webp-CUI- / requirements.txt](https://github.com/myon-bioinformatics/convert_img_fmt_to_webp-CUI-/blob/6d37bc7eeb71d46e9a4e94328c5a796aaeb60bee/requirements.txt) | Image-format options, warnings and API links |
| [FFmpeg](https://ffmpeg.org/ffmpeg.html), [filters](https://ffmpeg.org/ffmpeg-filters.html) | External executable detection and conversion commands in [audio_any2any_gui / audio_any2any_gui.py](https://github.com/myon-bioinformatics/audio_any2any_gui/blob/ebd9dc399114052a0a3d97f386e5839f0e62d04e/audio_any2any_gui.py) | CLI flags, filter expressions and significant punctuation |
| [FreeSimpleGUI](https://freesimplegui.readthedocs.io/) | Preferred import with PySimpleGUI fallback in [audio_any2any_gui / audio_any2any_gui.py](https://github.com/myon-bioinformatics/audio_any2any_gui/blob/ebd9dc399114052a0a3d97f386e5839f0e62d04e/audio_any2any_gui.py) | Constructor parameters and legacy naming; no runtime validation implied |
| [NVD CVE API](https://nvd.nist.gov/developers/vulnerabilities), [FIRST CVSS v3.1](https://www.first.org/cvss/v3.1/specification-document) | API 2.0 client and local v2/v3 score calculation described in [nvd_nist_known_vulns / README.md](https://github.com/myon-bioinformatics/nvd_nist_known_vulns/blob/a4c62d2b9fad083bf31e45a492bca58da5f32394/README.md) | Query parameters, metric tables, vector strings and equations |
| [Open WebUI](https://docs.openwebui.com/), [LibreChat](https://www.librechat.ai/docs) | External clients under test, not Python package dependencies: [mcp-toolcall-lab / README.md](https://github.com/myon-bioinformatics/mcp-toolcall-lab/blob/53ae4bf2c3af0178e3eaf30badffbde5e10cc5b7/README.md) | MCP configuration examples and client-specific names |
| [Docker Compose](https://docs.docker.com/compose/) | Documented client/server smoke stacks in [mcp-toolcall-lab / README.md](https://github.com/myon-bioinformatics/mcp-toolcall-lab/blob/53ae4bf2c3af0178e3eaf30badffbde5e10cc5b7/README.md) | YAML indentation, network names and environment variables |
| [MDN DOM](https://developer.mozilla.org/en-US/docs/Web/API/Document_Object_Model), [WHATWG HTML](https://html.spec.whatwg.org/multipage/) | Semantic HTML/CSS/JS contract in [web-ui / README.md](https://github.com/myon-bioinformatics/web-ui/blob/372564693ce38ba67994ae5915be648a1f5b642b/README.md) | Element definitions, attribute tables, hidden content and code literals |

## Testing and supporting references

| Technology / official documentation | Observed role and pinned evidence | Proposed extraction check |
| --- | --- | --- |
| [Playwright](https://playwright.dev/docs/intro) | E2E dev dependency in [flutter_navigation_basic / e2e/package.json](https://github.com/myon-bioinformatics/flutter_navigation_basic/blob/da549946839dec5a99c7cd1390cef4164608bcf2/e2e/package.json), [myon-bioinformatics.github.io / package.json](https://github.com/myon-bioinformatics/myon-bioinformatics.github.io/blob/950a7f3ef0782276ea2c4a568a47df82887ba419/package.json); optional browser test extra in lab | Language tabs, locator examples and assertion documentation |
| [Stagehand](https://docs.stagehand.dev/v4/first-steps/introduction) | Test dependency in [web-ui / tests/requirements.txt](https://github.com/myon-bioinformatics/web-ui/blob/372564693ce38ba67994ae5915be648a1f5b642b/tests/requirements.txt); dev dependency in [myon-bioinformatics.github.io / package.json](https://github.com/myon-bioinformatics/myon-bioinformatics.github.io/blob/950a7f3ef0782276ea2c4a568a47df82887ba419/package.json). web-ui calls this an optional experiment | Version-specific API examples and agent/browser boundaries |
| [pytest](https://docs.pytest.org/en/stable/) | Dev dependency in [Aoi / pyproject.toml](https://github.com/myon-bioinformatics/Aoi/blob/b86054b1fe50360f665128d87aedbc1f968a6763/pyproject.toml), lab test extra, web-ui test requirements | CLI options, fixture signatures and report examples |
| [NCBI Nucleotide](https://www.ncbi.nlm.nih.gov/nuccore/), [Protein](https://www.ncbi.nlm.nih.gov/protein/) | Reference-data links in [search_seq_including_spaces / README.md](https://github.com/myon-bioinformatics/search_seq_including_spaces/blob/7dc059061f6e98869f662c6027a0801b3028bda0/README.md); reader runtime is explicitly stdlib-only | Accession identifiers and reference links; do not infer Biopython use |

The inspected Flutter manifest explicitly limits GetX to historical/reference
patterns. Do not promote that entry to a new primary framework recommendation.
Likewise, a protocol dependency or a test extra does not justify adding that
dependency to a stdlib consumer.

## Acquisition status and next samples

All rows are **documentation discovery candidates, not verified DOM support**.
Official documentation entry points were located through search or public page
retrieval. NVD's developer URL returned no body through that retrieval path; its
link is independently present in the inspected README. The WHATWG single-page
request failed; its multipage entry was found through official-domain search.
These observations do not establish whether a browser can render those pages.

Prioritize Flutter/Dart, Gradio, FastMCP/MCP, then the Aoi parser/data stack and
Pillow/FFmpeg. This order reflects direct project relevance and varied document
content, not a measured popularity score. Playwright and pytest remain shared
cross-project references even though browser-test-kit was excluded from sampling.

Follow the acquisition/replay contract in [dom-capture.md](dom-capture.md).
Capture a bounded live section once, preserve the evidence, then exercise existing
page_text and relevant downstream readers offline. Keep raw DOM, browser-visible
text and normalized text separately; do not invent site selectors or hide code
newline changes in normalization.

FastMCP's current site states that it reflects main and may include unreleased
features, while lab constrains FastMCP to 3.x. MCP /latest redirected to a dated
specification during retrieval; that does not identify the protocol negotiated by
lab. Always match documentation versions to the inspected dependency/protocol
before using extracted text to guide implementation.

Cross-repository reuse here means shared evidence and existing readers. It does
not introduce a second capture implementation or generic browser probes in GHI.
