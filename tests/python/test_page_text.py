import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "page_text.py"
SAMPLE = ROOT / "fixtures" / "page_text" / "sample.html"
GOLDEN = ROOT / "fixtures" / "page_text" / "sample.expected.txt"
SAMPLE_URL = "https://example.test/docs/page.html"
spec = importlib.util.spec_from_file_location("page_text", SCRIPT)
page_text = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(page_text)


def text_of(html: str) -> str:
    return page_text.page_text(html)["text"]


def run_cli(*args: str, stdin: bytes = b"") -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-S", str(SCRIPT), *args], input=stdin, capture_output=True,
                          env=env, timeout=60)


# -- golden fixture -----------------------------------------------------------

def test_golden_sample_in_process(capsys) -> None:
    assert page_text.main([str(SAMPLE), "--url", SAMPLE_URL]) == 0
    captured = capsys.readouterr()
    assert captured.out == GOLDEN.read_text(encoding="utf-8")
    assert captured.err == ""


def test_golden_sample_runs_without_site_packages() -> None:
    result = run_cli(str(SAMPLE), "--url", SAMPLE_URL)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.decode("utf-8") == GOLDEN.read_text(encoding="utf-8")


def test_golden_sample_prefers_main_and_drops_hidden_content() -> None:
    result = page_text.page_text(SAMPLE.read_text(encoding="utf-8"))
    assert result["title"] == "Sample & Page — テスト"
    assert result["source_element"] == "main"
    for absent in ("Home", "Footer text", "must not appear", "Enable JavaScript", "template text", "svg text",
                   "svg title", "iframe fallback", "script link"):
        assert absent not in result["text"]
    assert 'after it <tag> & "quotes" \U0001F9EA' in result["text"]


def test_file_output_reports_the_file_url() -> None:
    result = run_cli(str(SAMPLE))
    assert f"URL: {SAMPLE.resolve().as_uri()}\n" in result.stdout.decode("utf-8")


# -- line-break and whitespace rules (innerText for default display) ----------

@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<div>a</div><div>b</div>", "a\nb"),
        ("<p>a</p><p>b</p>", "a\n\nb"),
        ("<h2>T</h2><div>x</div><p>y</p>", "T\nx\n\ny"),
        ("<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>", "a\nb\nc"),
        ("<ul><li>a<li>b</ul>", "a\nb"),
        ("a<br><br><br><br>b", "a\n\nb"),
        ("a</br>b", "a\nb"),
        ("<span>a</span> <span>b</span>", "a b"),
        ("<div>\n  lots   of \n\t spaces  </div>", "lots of spaces"),
        ("<table><tr><th>a</th><th></th><th>c</th></tr>\n<tr><td> d </td></tr></table>", "a\t\tc\nd"),
        ("<pre>\n  x\n\n\n\ty  </pre>", "  x\n\n\ty"),
        ("a<pre>\nx</pre>", "a\nx"),
        ("a<pre><code>\nx</code></pre>", "a\n\nx"),
        ("<p>x&nbsp;&nbsp;y　z</p>", "x\xa0\xa0y　z"),
        ("<p>&lt;a&gt; &amp;amp; &#169; &#x1F9EA;</p>", "<a> &amp; \xa9 \U0001F9EA"),
        ("<pre>a\r\nb\rc</pre>", "a\nb\nc"),
        ("a﷐b﷒c", "a�b�c"),
        ("<div>a<hr>b</div>", "a\nb"),
        ("<p>a</p>\n\n<p>b</p>\n", "a\n\nb"),
    ],
)
def test_line_break_rules(html: str, expected: str) -> None:
    assert text_of(html) == expected


def test_title_is_collapsed_and_svg_titles_are_ignored() -> None:
    html = "<svg><title>icon</title></svg><title>  A &amp;\n B </title><title>second</title><p>x</p>"
    assert page_text.page_text(html)["title"] == "A & B"


def test_excluded_elements_are_dropped_with_descendants() -> None:
    html = ("<main><script>s()</script><style>p{}</style><noscript><p>n</p></noscript>"
            "<template><p>tp</p></template><svg><text>sv</text></svg><iframe>if</iframe>"
            "<noembed>ne</noembed><noframes>nf</noframes>ok</main>")
    assert text_of(html) == "ok"


def test_unclosed_nested_excluded_element_recovers_at_the_outer_end_tag() -> None:
    assert text_of("<p>before</p><noscript><svg><text>x</text></noscript><p>after</p>") == "before\n\nafter"


# -- source element selection -------------------------------------------------

def test_body_fallback_when_there_is_no_main_or_article() -> None:
    html = "<html><head><title>T</title><style>x{}</style></head><body><div>only body</div></body></html>"
    result = page_text.page_text(html)
    assert (result["source_element"], result["text"], result["title"]) == ("body", "only body", "T")


def test_body_fallback_cli_line() -> None:
    result = run_cli("-", stdin=b"<title>T</title><p>Hi</p>")
    assert result.returncode == 0
    assert result.stdout.decode("utf-8") == "Title: T\nURL: -\nSource element: body\n---\nHi\n"


def test_text_in_head_without_body_tag_starts_the_body() -> None:
    assert text_of("<html><head><title>T</title><p>Hi") == "Hi"


def test_article_is_used_when_there_is_no_main() -> None:
    result = page_text.page_text("<nav>n</nav><article><h1>A</h1>text</article><footer>f</footer>")
    assert (result["source_element"], result["text"]) == ("article", "A\ntext")


def test_main_wins_over_an_earlier_article_and_only_the_first_main_counts() -> None:
    result = page_text.page_text("<article>a</article><main>m1</main><main>m2</main>")
    assert (result["source_element"], result["text"]) == ("main", "m1")


def test_nested_main_does_not_end_the_outer_main_early() -> None:
    assert text_of("<main><main>inner</main>tail</main>after") == "inner\ntail"


def test_empty_main_prints_a_static_extraction_note() -> None:
    result = run_cli("-", stdin=b'<main id="app"></main><script>render()</script>')
    assert result.returncode == 0
    assert result.stdout.decode("utf-8").endswith("Source element: main\n---\n")
    assert "PAGE_TEXT_AS_RENDERED_TEXT" in result.stderr.decode("utf-8")


# -- limits and JSON ----------------------------------------------------------

def test_max_chars_truncates_and_flags_it() -> None:
    result = page_text.page_text("<p>abcdefghij</p>", max_chars=4)
    assert (result["text"], result["truncated"], result["total_chars"]) == ("abcd", True, 10)
    assert page_text.page_text("<p>abcd</p>", max_chars=4)["truncated"] is False


def test_cli_json_fields_and_truncation() -> None:
    result = run_cli(str(SAMPLE), "--json", "--max-chars", "12")
    assert result.returncode == 0
    data = json.loads(result.stdout.decode("utf-8"))
    for key in ("title", "url", "source_element", "text", "truncated", "bytes", "fetched_at"):
        assert key in data
    assert data["text"] == "Main heading" and data["truncated"] is True
    assert data["bytes"] == SAMPLE.stat().st_size and data["byte_limit_hit"] is False
    assert "truncated to 12 of" in result.stderr.decode("utf-8")


def test_max_bytes_limit_is_reported(tmp_path: Path) -> None:
    page = tmp_path / "big.html"
    page.write_text("<p>" + "x" * 500 + "</p>", encoding="utf-8")
    loaded = page_text.load(str(page), max_bytes=100)
    assert (loaded["bytes"], loaded["byte_limit_hit"]) == (100, True)


@pytest.mark.parametrize("option", ["--max-chars", "--max-bytes", "--limit", "--timeout"])
def test_non_positive_limits_are_usage_errors(option: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        page_text.main([str(SAMPLE), option, "0"])
    assert excinfo.value.code == 2


def test_missing_file_is_an_input_error(capsys) -> None:
    assert page_text.main(["does/not/exist.html"]) == 2
    assert "no such file" in capsys.readouterr().err


def test_file_url_source() -> None:
    assert page_text.load(SAMPLE.resolve().as_uri())["url"] == SAMPLE.resolve().as_uri()


@pytest.mark.parametrize(
    ("raw", "content_type", "expected"),
    [
        ("①テスト".encode("cp932"), "text/html; charset=Shift_JIS", "①テスト"),
        ('<meta charset="euc-jp">テスト'.encode("euc_jp"), "", '<meta charset="euc-jp">テスト'),
        ("’".encode("cp1252"), "text/html; charset=iso-8859-1", "’"),
        (b"\xef\xbb\xbfBOM", "text/html; charset=iso-8859-1", "BOM"),
        (b"ok", "text/html; charset=x-unknown", "ok"),
    ],
)
def test_decoding(raw: bytes, content_type: str, expected: str) -> None:
    assert page_text._decode(raw, content_type) == expected


# -- find ---------------------------------------------------------------------

def test_find_resolves_relative_hrefs_against_base_href() -> None:
    matches = page_text.find_elements(SAMPLE.read_text(encoding="utf-8"), "status page", url=SAMPLE_URL)
    assert matches == [{"kind": "link", "text": "status page", "href": "https://example.test/docs/status.html",
                        "index": matches[0]["index"], "aria_label": None, "title": "Status page"}]
    home = page_text.find_elements(SAMPLE.read_text(encoding="utf-8"), "home", url=SAMPLE_URL)
    assert home[0]["href"] == "https://example.test/"


def test_find_resolves_relative_hrefs_against_the_page_url() -> None:
    html = '<a href="../settings/security">Code security</a><a href=" #top ">Top</a>'
    matches = page_text.find_elements(html, "", url="https://github.com/o/r/settings/actions")
    assert [match["href"] for match in matches] == [
        "https://github.com/o/r/settings/security", "https://github.com/o/r/settings/actions#top"]


def test_find_matches_text_aria_label_and_title_case_insensitively() -> None:
    html = SAMPLE.read_text(encoding="utf-8")
    assert [(m["kind"], m["text"]) for m in page_text.find_elements(html, "CLOSE DIALOG")] == [("button", "×")]
    assert [(m["kind"], m["text"]) for m in page_text.find_elements(html, "refresh data")] == [
        ("button", "↻ Refresh")]
    assert [(m["kind"], m["text"]) for m in page_text.find_elements(html, "main heading")] == [
        ("heading", "Main heading")]


def test_find_candidates_and_non_candidates() -> None:
    html = ('<input type="submit" value="Save changes"><input type="text" value="Save draft">'
            '<span role="link">Save link</span><a>Save anchor without href</a><p>Save paragraph</p>'
            '<button>Save<br>all</button>')
    assert [(m["kind"], m["text"]) for m in page_text.find_elements(html, "save")] == [
        ("button", "Save changes"), ("link", "Save link"), ("button", "Save all")]


def test_find_never_matches_script_style_or_template_text() -> None:
    html = ("<style>.status-page{}</style><script>var a = '<a href=x>status page</a>';</script>"
            "<template><a href=y>status page</a></template><noscript><a href=z>status page</a></noscript>")
    assert page_text.find_elements(html, "status") == []


def test_find_nbsp_and_nested_elements() -> None:
    html = '<div role="button"><div>status</div>&nbsp;page</div><a href="/x"><b>status</b>\n page</a>'
    assert [m["text"] for m in page_text.find_elements(html, "status page")] == ["status \xa0page", "status page"]


def test_find_an_unclosed_link_ends_at_the_next_link() -> None:
    html = '<a href="/1">one<a href="/2">two</a>'
    assert [m["text"] for m in page_text.find_elements(html, "")] == ["one", "two"]


def test_find_limit_and_index_order() -> None:
    html = "".join(f'<a href="/{n}">item {n}</a>' for n in range(5))
    matches = page_text.find_elements(html, "item", limit=2)
    assert [(m["text"], m["index"]) for m in matches] == [("item 0", 0), ("item 1", 1)]


def test_find_cli_output_and_exit_codes() -> None:
    found = run_cli(str(SAMPLE), "--url", SAMPLE_URL, "--find", "status page")
    assert found.returncode == 0
    assert found.stdout.decode("utf-8") == (
        'Found 1 match(es) for "status page":\n'
        '- link "status page" href=https://example.test/docs/status.html\n')
    labelled = run_cli(str(SAMPLE), "--find", "close")
    assert labelled.stdout.decode("utf-8").endswith('- button "×" aria-label="Close dialog"\n')
    missing = run_cli(str(SAMPLE), "--find", "script link")
    assert missing.returncode == 1
    assert missing.stdout.decode("utf-8") == 'No matches for "script link".\n'
    as_json = run_cli(str(SAMPLE), "--find", "nothing here", "--json")
    assert (as_json.returncode, json.loads(as_json.stdout)) == (1, [])


def test_existing_browser_fixture_is_readable() -> None:
    result = run_cli(str(ROOT / "fixtures" / "index.html"), "--find", "反映")
    assert result.returncode == 0
    assert result.stdout.decode("utf-8").endswith('- button "反映"\n')
    text = page_text.page_text((ROOT / "fixtures" / "index.html").read_text(encoding="utf-8"))["text"]
    assert "addEventListener" not in text and "日本語 / Unicode ✓ / 🧪" in text


# -- HTTP (local server only; EXTERNAL_SITE_AS_CORE_FIXTURE) -------------------

ROUTES = {
    "/old": (302, {"Location": "/new"}, b""),
    "/new": (200, {"Content-Type": "text/html; charset=Shift_JIS"},
             "<title>新</title><main><p>①移動後</p><a href='next'>次へ</a></main>".encode("cp932")),
    "/missing": (404, {"Content-Type": "text/html"}, b"<title>Page not found</title><main>Not Found</main>"),
    "/forbidden": (403, {"Content-Type": "text/html"}, b"<p>Forbidden</p>"),
    "/image.png": (200, {"Content-Type": "image/png"}, b"\x89PNG\r\n\x1a\n"),
}


@pytest.fixture()
def server(monkeypatch):
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            status, headers, body = ROUTES[self.path]
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_redirect_reports_final_url_and_decodes_header_charset(server, capsys) -> None:
    assert page_text.main([f"{server}/old"]) == 0
    out = capsys.readouterr().out
    assert out == f"Title: 新\nURL: {server}/new\nSource element: main\n---\n①移動後\n\n次へ\n"
    assert page_text.main([f"{server}/old", "--find", "次"]) == 0
    assert f"href={server}/next" in capsys.readouterr().out


def test_http_404_still_prints_the_page_and_warns_about_login_walls(server, capsys) -> None:
    assert page_text.main([f"{server}/missing"]) == 1
    captured = capsys.readouterr()
    assert "Not Found" in captured.out
    assert "HTTP 404" in captured.err and "LOGIN_WALL_AS_404" in captured.err
    assert page_text.main([f"{server}/forbidden", "--json"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == 403
    assert "HTTP 403" in captured.err and "LOGIN_WALL_AS_404" not in captured.err


def test_http_non_html_content_type_warns(server, capsys) -> None:
    page_text.main([f"{server}/image.png"])
    assert "Content-Type is image/png, not HTML" in capsys.readouterr().err


def test_network_failure_is_exit_2(monkeypatch, capsys) -> None:
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert page_text.main([f"http://127.0.0.1:{port}/", "--timeout", "5"]) == 2
    assert "fetch failed" in capsys.readouterr().err
