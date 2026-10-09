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


@pytest.mark.parametrize('style', [
    '--sample:";display:none;"', "--sample:';display:none;'",
    '--sample:fn(;display:none;)', '/* ;display:none; */display:block',
    'display:none;display:/* restored */inline',
    'display:none;display:',
])
def test_css_data_and_comments_do_not_become_hiding_declarations(style):
    from html import escape
    expected = '' if style == 'display:none;display:' else 'visible'
    assert text_of('<span style="'+escape(style, quote=True)+'">visible</span>') == expected


@pytest.mark.parametrize('sample', json.loads(
    (FIXTURES / 'media-code-dom.json').read_text())['samples'], ids=lambda s: s['id'])
def test_selected_media_code_preserves_context_and_excludes_controls(sample):
    import hashlib
    assert hashlib.sha256(sample['pre_outer_html'].encode()).hexdigest() == sample['pre_sha256']
    assert hashlib.sha256(sample['code_outer_html'].encode()).hexdigest() == sample['code_sha256']
    assert sample['code_outer_html'] in sample['pre_outer_html']
    assert '<button' in sample['pre_outer_html']
    assert '<button' not in sample['code_outer_html']
    # Explicit context model for the selected code, not the original complete pre.
    assert text_of('<pre>'+sample['code_outer_html']+'</pre>') == sample['code_inner_text']
    assert 'Copy' not in sample['code_inner_text']
    assert 'MyComposition.tsx' not in sample['code_inner_text']
    assert 'const frame: number' not in sample['code_inner_text']


@pytest.mark.parametrize('name', ['ffmpeg', 'pillow'])
def test_previously_recorded_media_newlines_now_match(name):
    samples = json.loads((FIXTURES / 'media-doc-dom-survey.json').read_text())
    # The historical comparisons stay unchanged; the current reader is checked here.
    sample = next(s for s in samples if s['name'] == name)
    assert text_of(sample['fragment_html']) == sample['fragment_inner_text']
