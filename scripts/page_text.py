#!/usr/bin/env python3
"""Read the text of a web page without a browser (#8).

Stdlib only (``html.parser`` + ``urllib.request``), so it runs under
``python -S``. The source is an http(s) or file URL, a local HTML file, or
``-`` for stdin. The output mirrors a browser ``get_page_text``::

    Title: <title>
    URL: <final URL after redirects>
    Source element: <main|article|body>
    ---
    <text>

Rules (v1):

* The text comes from the first ``<main>``, else the first ``<article>``,
  else ``<body>``.
* ``script``, ``style``, ``noscript``, ``template`` and ``svg`` are dropped
  with everything inside them, as is the fallback content of ``iframe``,
  ``noembed`` and ``noframes``, which browsers never render.
* Line breaks follow the browser's ``innerText`` rules for the default
  display of each element: a ``<p>`` is set off by a blank line, other block
  elements (``div``, ``li``, ``h1``-``h6``, ``tr``, ``section`` ...) and
  ``<br>`` start a new line, and table cells are separated by a tab. Runs of
  blank lines collapse to one.
* Runs of ASCII whitespace collapse to one space (``&nbsp;`` and the
  ideographic space U+3000 are text, not whitespace); ``<pre>`` keeps its
  line breaks and indentation. Character references are expanded.

This is *static* extraction: text that JavaScript renders later is not seen
(``PAGE_TEXT_AS_RENDERED_TEXT``), and visibility from CSS or the ``hidden``
attribute is not evaluated.

``--find QUERY`` lists links (``a[href]``), buttons (``button``,
``input[type=submit|button]``), headings (``h1``-``h6``) and
``[role=link|button]`` elements whose text, ``aria-label`` or ``title``
contains QUERY (case-insensitive), with each href resolved to an absolute
URL against the page URL and ``<base href>``.

Exit codes: 0 = OK; 1 = no ``--find`` match, or an HTTP error status (the
page is still printed); 2 = usage, input, or network error.
"""
from __future__ import annotations

import argparse
import datetime
import http.client
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

USER_AGENT = "browser-test-kit-page-text/1"
# Never rendered as page text; dropped together with all descendants.
EXCLUDED = frozenset({"script", "style", "noscript", "template", "svg", "iframe", "noembed", "noframes"})
# innerText "required line break count": 2 for <p>, 1 for other default block-level boxes.
PARAGRAPH = frozenset({"p"})
BLOCK = frozenset({
    "address", "article", "aside", "blockquote", "caption", "center", "dd", "details", "dialog", "dir", "div",
    "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hgroup", "hr", "legend", "li", "listing", "main", "menu", "nav", "ol", "optgroup", "option",
    "pre", "search", "section", "summary", "table", "tr", "ul", "xmp",
})
PREFORMATTED = frozenset({"pre", "listing", "xmp", "textarea"})
HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
HEAD_CONTENT = frozenset({"base", "basefont", "bgsound", "link", "meta", "noscript", "script", "style", "template",
                          "title"})
VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
                  "track", "wbr"})
MATCH_TEXT_MAX = 200

_WS = re.compile(r"[ \t\n\r\f]+")
# Unicode noncharacters used as private markers; any already in the input become U+FFFD.
_PRE_SPACE, _PRE_TAB, _CELL = "﷐", "﷑", "﷒"
_MARKERS = re.compile("[﷐-﷒]")
_CELL_GAP = re.compile(" ?﷒ ?")
_CONTENT_TYPE_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?([^\s;\"']+)", re.IGNORECASE)
_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.IGNORECASE)
# Labels that browsers decode with a superset encoding (WHATWG Encoding Standard).
_CHARSET_ALIASES = {
    **dict.fromkeys(("ascii", "us-ascii", "iso-8859-1", "iso8859-1", "iso_8859-1", "latin1", "latin-1", "l1"),
                    "cp1252"),
    **dict.fromkeys(("shift_jis", "shift-jis", "sjis", "x-sjis", "ms_kanji", "csshiftjis", "windows-31j"), "cp932"),
    **dict.fromkeys(("gb2312", "gbk", "x-gbk"), "gb18030"),
}


class PageTextError(Exception):
    """Input or network error (exit code 2)."""


class _Sink:
    """innerText-style accumulator: adjacent block boundaries merge (max), text flushes them."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.pending = 0

    def require(self, count: int) -> None:
        self.pending = max(self.pending, count)

    def write(self, text: str) -> None:
        if self.pending:
            if not text.strip(" "):
                return  # a collapsible space next to a block boundary
            if self.parts:
                self.parts.append("\n" * self.pending)
            self.pending = 0
        self.parts.append(text)


def _candidate_kind(tag: str, attrs: dict[str, str]) -> str | None:
    if tag == "a" and "href" in attrs:
        return "link"
    if tag == "button" or (tag == "input" and attrs.get("type", "").strip().lower() in {"submit", "button"}):
        return "button"
    if tag in HEADINGS:
        return "heading"
    role = attrs.get("role", "").strip().lower()
    return role if role in {"link", "button"} else None


class _PageParser(HTMLParser):
    """One pass: title, ``<base href>``, main/article/body text, and ``--find`` candidates."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.titles = 0
        self.base_href: str | None = None
        self.sinks = {"main": _Sink(), "article": _Sink(), "body": _Sink()}
        # None = not seen; > 0 = open at that stack level; 0 = closed. Only the first of each counts.
        self.region: dict[str, int | None] = {"main": None, "article": None}
        self.stack: list[str] = []
        self.skip: list[str] = []
        self.cells: list[int] = []
        self.in_head = False
        self.head_done = False
        self.in_title = False
        self.pre_start = False
        self.candidates: list[dict[str, Any]] = []
        self.open: list[dict[str, Any]] = []

    # -- helpers ----------------------------------------------------------------
    def _sinks(self) -> list[_Sink]:
        if self.skip or self.in_head or self.in_title:
            return []
        return [self.sinks["body"]] + [self.sinks[name] for name, level in self.region.items() if level]

    def _write(self, text: str) -> None:
        for sink in self._sinks():
            sink.write(text)

    def _separate_candidates(self) -> None:
        for candidate in self.open:
            candidate["parts"].append(" ")

    def _boundary(self, tag: str) -> None:
        count = 2 if tag in PARAGRAPH else 1 if tag in BLOCK else 0
        if count:
            for sink in self._sinks():
                sink.require(count)
            self._separate_candidates()

    def _leave_head(self) -> None:
        self.in_head = False
        self.head_done = True

    def _close(self, tag: str) -> None:
        """Pop the open-element stack through the innermost ``tag``, like its end tag."""
        if tag not in self.stack:
            return  # a stray end tag is ignored
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        for popped in reversed(self.stack[index:]):
            self._boundary(popped)
            if popped == "tr" and self.cells:
                self.cells.pop()
        del self.stack[index:]
        for name, level in self.region.items():
            if level and level > index:
                self.region[name] = 0
        self.open = [candidate for candidate in self.open if candidate["level"] <= index]

    # -- parser callbacks -------------------------------------------------------
    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        if self.skip:
            if tag in EXCLUDED:
                self.skip.append(tag)
            return
        self.pre_start = False
        attrs: dict[str, str] = {}
        for key, value in attrs_list:
            attrs.setdefault(key, value or "")
        if tag in EXCLUDED:
            self.skip.append(tag)
            return
        if tag == "title":
            self.titles += 1
            self.in_title = True
            return
        if tag == "base":
            if self.base_href is None and attrs.get("href"):
                self.base_href = attrs["href"]
            return
        if tag in {"html", "head", "body"}:
            if tag == "head" and not self.head_done:
                self.in_head = True
            elif tag == "body":
                self._leave_head()
            return
        if tag not in HEAD_CONTENT:
            self._leave_head()  # body content ends <head>; a later <head> tag is ignored
        if tag in {"a", "button"}:
            self._close(tag)  # a nested <a>/<button> ends the open one
        if tag not in VOID:
            self.stack.append(tag)
        if tag in self.region and self.region[tag] is None:
            self.region[tag] = len(self.stack)
        self._boundary(tag)
        if tag in PREFORMATTED:
            self.pre_start = True
        elif tag == "br":
            self._write("\n")
            self._separate_candidates()
        elif tag == "tr":
            self.cells.append(0)
        elif tag in {"td", "th"} and self.cells:
            if self.cells[-1]:
                self._write(_CELL)
            self.cells[-1] += 1
        kind = _candidate_kind(tag, attrs)
        if kind:
            candidate = {"kind": kind, "parts": [], "aria_label": attrs.get("aria-label", ""),
                         "title": attrs.get("title", ""), "href": attrs.get("href") if tag == "a" else None,
                         "level": len(self.stack)}
            self.candidates.append(candidate)
            if tag == "input":
                candidate["parts"].append(attrs.get("value", ""))
            else:
                self.open.append(candidate)

    def handle_startendtag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs_list)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.skip:
            if tag in self.skip:
                while self.skip.pop() != tag:
                    pass
            return
        self.pre_start = False
        if tag == "title":
            self.in_title = False
        elif tag == "head":
            if self.in_head:
                self._leave_head()
        elif tag == "br":
            self.handle_starttag("br", [])  # browsers read </br> as <br>
        elif tag not in {"html", "body"}:
            self._close(tag)

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.in_title:
            if self.titles == 1:
                self.title_parts.append(data)
            return
        if self.in_head:
            if not data.strip(" \t\n\f"):
                return
            self._leave_head()
        for candidate in self.open:
            candidate["parts"].append(data)
        if any(tag in PREFORMATTED for tag in self.stack):
            if self.pre_start and data.startswith("\n"):
                data = data[1:]  # the newline right after <pre> is not content
            text = data.replace(" ", _PRE_SPACE).replace("\t", _PRE_TAB)
        else:
            text = _WS.sub(" ", data)
        self.pre_start = False
        if text:
            self._write(text)


def _normalize(raw: str) -> str:
    lines: list[str] = []
    for line in raw.split("\n"):
        line = _CELL_GAP.sub("\t", _WS.sub(" ", line).strip(" "))
        line = line.replace(_PRE_SPACE, " ").replace(_PRE_TAB, "\t").rstrip(" ")
        if line or (lines and lines[-1]):
            lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _collapse(value: str) -> str:
    return _WS.sub(" ", value).strip(" ")


def _fold(value: str) -> str:
    return _collapse(value.replace("\xa0", " ")).casefold()


def _decode(raw: bytes, content_type: str = "") -> str:
    """Decode by BOM, then the Content-Type charset, then ``<meta charset>``, then UTF-8."""
    for bom, codec in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if raw.startswith(bom):
            return raw[len(bom):].decode(codec, "replace")
    match = _CONTENT_TYPE_CHARSET_RE.search(content_type)
    meta = None if match else _META_CHARSET_RE.search(raw[:4096])
    label = match.group(1) if match else meta.group(1).decode("ascii", "replace") if meta else "utf-8"
    label = label.strip().lower()
    try:
        return raw.decode(_CHARSET_ALIASES.get(label, label), "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def _read_file(path: Path, source: str, max_bytes: int) -> bytes:
    if not path.is_file():
        raise PageTextError(f"no such file: {source}")
    with path.open("rb") as handle:
        return handle.read(max_bytes + 1)


def load(source: str, *, timeout: float = 20.0, max_bytes: int = 5_000_000) -> dict:
    """Read ``source`` into ``{"html", "url", "status", "content_type", "bytes", "byte_limit_hit"}``.

    ``source`` is an http(s) URL (redirects followed; ``url`` is the final
    one), a ``file:`` URL, a path, or ``-`` for stdin. An HTTP error status
    is returned, not raised, so the error page can still be read.
    """
    status: int | None = None
    content_type = ""
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={
            "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                raw = reply.read(max_bytes + 1)
                status, url = reply.status, reply.geturl()
                content_type = reply.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            try:
                raw = error.read(max_bytes + 1)
            except (http.client.HTTPException, OSError):
                raw = b""
            finally:
                error.close()
            status, url = error.code, error.geturl() or source
            content_type = error.headers.get("Content-Type", "") if error.headers else ""
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
            reason = getattr(error, "reason", None) or error
            raise PageTextError(f"fetch failed for {source}: {reason}") from None
    elif source == "-":
        raw, url = sys.stdin.buffer.read(max_bytes + 1), ""
    elif source.startswith("file:"):
        path = Path(urllib.request.url2pathname(urllib.parse.urlparse(source).path))
        raw, url = _read_file(path, source, max_bytes), path.resolve().as_uri()
    else:
        path = Path(source)
        raw, url = _read_file(path, source, max_bytes), path.resolve().as_uri()
    hit = len(raw) > max_bytes
    raw = raw[:max_bytes]
    return {"html": _decode(raw, content_type), "url": url, "status": status, "content_type": content_type,
            "bytes": len(raw), "byte_limit_hit": hit}


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(_MARKERS.sub("�", html.replace("\r\n", "\n").replace("\r", "\n")))
    parser.close()
    return parser


def page_text(html: str, *, url: str = "", max_chars: int = 50_000) -> dict:
    """Return ``{"title", "url", "source_element", "text", "truncated", "total_chars"}``."""
    parser = _parse(html)
    source = next((name for name in ("main", "article") if parser.region[name] is not None), "body")
    text = _normalize("".join(parser.sinks[source].parts))
    return {
        "title": _collapse("".join(parser.title_parts)),
        "url": url,
        "source_element": source,
        "text": text[:max_chars],
        "truncated": len(text) > max_chars,
        "total_chars": len(text),
    }


def find_elements(html: str, query: str, *, url: str = "", limit: int = 20) -> list[dict]:
    """Return ``[{"kind", "text", "href", "index", "aria_label", "title"}]`` for matching elements.

    ``index`` is the element's position among all candidate elements in
    document order; ``href`` is absolute (``None`` for non-links).
    """
    parser = _parse(html)
    base = urllib.parse.urljoin(url, parser.base_href.strip()) if parser.base_href else url
    needle = _fold(query)
    matches: list[dict] = []
    for index, candidate in enumerate(parser.candidates):
        text = _collapse("".join(candidate["parts"]))
        if not any(needle in _fold(value) for value in (text, candidate["aria_label"], candidate["title"])):
            continue
        label = text or _collapse(candidate["aria_label"]) or _collapse(candidate["title"])
        if len(label) > MATCH_TEXT_MAX:
            label = label[:MATCH_TEXT_MAX - 1] + "…"
        href = candidate["href"]
        matches.append({
            "kind": candidate["kind"],
            "text": label,
            "href": urllib.parse.urljoin(base, href.strip(" \t\n\r\f")) if href is not None else None,
            "index": index,
            "aria_label": candidate["aria_label"] or None,
            "title": candidate["title"] or None,
        })
        if len(matches) >= limit:
            break
    return matches


def _positive(kind: Callable[[str], Any]) -> Callable[[str], Any]:
    def parse(value: str) -> Any:
        number = kind(value)
        if number <= 0:
            raise argparse.ArgumentTypeError(f"must be greater than 0, got {value}")
        return number

    parse.__name__ = kind.__name__
    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="page_text.py", description="Read the text of a web page without a browser.")
    parser.add_argument("source", help="http(s) or file URL, local HTML file, or - for stdin")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--max-chars", type=_positive(int), default=50_000,
                        help="truncate the text to this many characters (default: 50000)")
    parser.add_argument("--max-bytes", type=_positive(int), default=5_000_000,
                        help="read at most this many bytes (default: 5000000)")
    parser.add_argument("--timeout", type=_positive(float), default=20.0, help="network timeout in seconds")
    parser.add_argument("--url", help="URL to report and resolve relative links against (default: the final "
                                      "fetched URL, the file URL, or none for stdin)")
    parser.add_argument("--find", metavar="QUERY", help="list links/buttons/headings whose text, aria-label or "
                                                        "title contains QUERY")
    parser.add_argument("--limit", type=_positive(int), default=20, help="maximum --find matches (default: 20)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        loaded = load(args.source, timeout=args.timeout, max_bytes=args.max_bytes)
    except PageTextError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    url = loaded["url"] if args.url is None else args.url
    status = loaded["status"]
    http_error = status is not None and status >= 400
    if http_error:
        hint = ("; a 404 can also mean the page exists but needs a login, as on GitHub (LOGIN_WALL_AS_404)"
                if status == 404 else "")
        print(f"warning: HTTP {status} for {loaded['url']}{hint}", file=sys.stderr)
    content_type = loaded["content_type"]
    if content_type and not re.match(r"\s*(text/|application/(xhtml\+)?xml)", content_type, re.IGNORECASE):
        print(f"warning: Content-Type is {content_type}, not HTML", file=sys.stderr)
    if loaded["byte_limit_hit"]:
        print(f"warning: read only the first {args.max_bytes} bytes (--max-bytes)", file=sys.stderr)

    if args.find is not None:
        matches = find_elements(loaded["html"], args.find, url=url, limit=args.limit)
        if args.json:
            print(json.dumps(matches, ensure_ascii=False, indent=2))
        elif matches:
            print(f'Found {len(matches)} match(es) for "{args.find}":')
            for match in matches:
                extra = "".join(f' {name}="{match[key]}"' for key, name in (("aria_label", "aria-label"),
                                                                            ("title", "title"))
                                if match[key] and _fold(match[key]) != _fold(match["text"]))
                if match["href"] is not None:
                    extra += f" href={match['href']}"
                print(f'- {match["kind"]} "{match["text"]}"{extra}')
        else:
            print(f'No matches for "{args.find}".')
        return 0 if matches and not http_error else 1

    result = page_text(loaded["html"], url=url, max_chars=args.max_chars)
    if not result["text"]:
        print(f"note: no text in <{result['source_element']}>; text rendered by JavaScript is not visible to "
              "static extraction (PAGE_TEXT_AS_RENDERED_TEXT)", file=sys.stderr)
    if result["truncated"]:
        print(f"note: truncated to {args.max_chars} of {result['total_chars']} characters (--max-chars)",
              file=sys.stderr)
    if args.json:
        result.update(bytes=loaded["bytes"], byte_limit_hit=loaded["byte_limit_hit"], status=status,
                      content_type=content_type or None,
                      fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Title: {result['title']}\nURL: {result['url'] or '-'}\n"
              f"Source element: {result['source_element']}\n---")
        if result["text"]:
            print(result["text"])
    return 1 if http_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
