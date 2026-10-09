"""Saved live DOM evidence; no upstream access in regression tests."""
import json
from pathlib import Path
import pytest
from test_page_text import text_of, page_text

FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures/page_text'


def test_alpine_hidden_copy_is_not_duplicated():
    sample = json.loads((FIXTURES / 'alpine-code-dom.json').read_text())
    assert text_of(sample['html']) == sample['visible_text']


def test_deno_pre_keeps_terminal_newline():
    sample = json.loads((FIXTURES / 'deno-doc-dom.json').read_text())['samples'][0]
    assert text_of(sample['dom_html']) == sample['inner_text']


@pytest.mark.parametrize('attributes', ['hidden', 'hidden="false"',
    'style="DISPLAY: none !important"', 'style="display:block;display:none"'])
def test_hidden_nested_and_void_elements_do_not_leak_or_swallow_siblings(attributes):
    assert text_of(f'<main><div {attributes}><div>copy</div><a href="/x">secret</a></div>'
                   f'<input {attributes}>kept</main>') == 'kept'
    assert not page_text.find_elements(f'<a {attributes} href="/x">secret</a>', 'secret')


def test_aria_hidden_is_accessibility_not_visual_hiding():
    assert text_of('<span aria-hidden="true">visible</span>') == 'visible'
    assert text_of('<span style="display:none;display:inline">visible</span>') == 'visible'
    assert text_of('<span style="display:none!important;display:inline">hidden</span>') == ''


@pytest.mark.parametrize('code', ['x\n', 'x\n\n\n', 'x  \n\t y  ', '\n\nx\n'])
def test_pre_preserves_content_not_print_formatting(code):
    assert text_of('<pre><code>' + code + '</code></pre>') == code


def test_pre_br_is_a_preserved_line_break():
    assert text_of('<pre><code>x<br>y<br></code></pre>') == 'x\ny\n'
