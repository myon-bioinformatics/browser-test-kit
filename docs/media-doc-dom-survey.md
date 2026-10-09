# Media documentation HTML/DOM survey

Observed 2026-10-09. Added at the user's request after the earlier survey excluded
image/audio conversion. FFmpeg and Pillow are confirmed requested technologies.
Remotion (React video creation, including Remotion Studio) and Tone.js (Web Audio
music) are plausible candidates for the unnamed JS tool; identification is not
confirmed. No adoption or claim of current popularity follows from this survey.

| Project | Official page | Captured structure / when to consult |
| --- | --- | --- |
| FFmpeg | https://www.ffmpeg.org/ffmpeg.html | CLI conversion help; no main/article; h1 includes menu control; 108 pre blocks |
| Pillow | https://pillow.readthedocs.io/en/stable/reference/Image.html | Image API; article#furo-main-content; heading has inline module link and hidden permalink; 25 pre blocks |
| Remotion | https://www.remotion.dev/docs/the-fundamentals | Frame-driven React video concepts; main/article; 3 pre blocks containing filename div, code and copy button |
| Tone.js | https://tonejs.github.io/docs/14.9.17/classes/Player.html | Audio player API; versioned TypeDoc page; no main/article; 25 pre blocks after navigation settles |

Raw HTTP responses and representative live fragments were acquired. The small
[fixture](../fixtures/page_text/media-doc-dom-survey.json) retains source hashes,
raw headings, actual DOM fragments and text results. Complete HTTP responses are
in the separately delivered media-html-dom-2026-10-09.zip. This is not a whole-page
live DOM archive and does not cover every API page.

Tone.js /docs/Player initially returned an 89-byte redirect shell to curl. The
browser reached the versioned URL above; its resolved HTTP body was then fetched
once separately. The early browser sample had no heading, while a later sample
showed Class Player. Record readiness and final URL instead of accepting an empty
initial DOM or claiming that 14.9.17 is the newest release.

Remotion's pre contains a code-title div, code, and copy-button. Nested data-lsp
elements put type information in attributes. Text extraction should select actual
code and preserve line boundaries without treating tooltip attributes or filenames
as code. Only its small filename fragment is retained here; its code extraction
has not passed a test.

Tone.js code uses br between syntax-highlighted spans. textContent concatenates
those lines; innerText separates them. Existing page_text restores those internal
line breaks but strips the terminal LF. FFmpeg and Pillow code samples likewise
lose their terminal LF. The recorded comparisons report all three as unequal;
only the Remotion filename fragment exactly matches. No normalization masks these
differences, and no parser fix is claimed.

These are documentation references, not additions to web-ui's lightweight runtime.
Remotion's React/video toolchain must be evaluated separately from small JS
helpers. Existing capture and extraction ownership stays in browser-test-kit;
reuse fixtures offline rather than re-fetching each page for every consumer.
