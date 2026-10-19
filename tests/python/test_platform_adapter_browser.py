"""Local app doubles test adapters without depending on the published Flutter site."""
import functools
import importlib.util
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('platform_probe', ROOT / 'scripts/platform_probe.py')
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)
pa = pp.adapters


@pytest.fixture
def application(tmp_path):
    # This app has no __platformFacts / __layoutChecks hooks and uses different DOM ids.
    # Nonmonotonic responsive rules: passes at 260..279, fails at 280..299, passes >=300.
    (tmp_path / 'index.html').write_text('''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>body{margin:0}h1{margin:0;width:180px;height:32px}button{display:block;width:260px;height:40px}
    @media(min-width:280px) and (max-width:299px){button{width:310px}}
    #cover{display:none;position:fixed;inset:32px 0 0;background:white;z-index:5}</style>
    <h1 id="title">App title</h1><button id="increment" data-value="0" onclick="this.dataset.value=String(+this.dataset.value+1);localStorage.setItem('counter',this.dataset.value)">Increment</button><div id="cover"></div><script>document.querySelector("#increment").dataset.value=localStorage.getItem("counter") || "0";</script>''')
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/index.html'
    config = {'schema': 'btk-platform-adapter/1', 'id': 'local-app', 'url': url,
              'elements': ['#title', '#increment'],
              'click': {'target': '#increment', 'observe': '#increment', 'attribute': 'data-value', 'before': '0', 'after': '1'}}
    path = tmp_path / 'adapter.json'
    path.write_text(json.dumps(config))
    try:
        yield url, config, path
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.browser
@pytest.mark.parametrize('profile', ['desktop', 'pixel'])
def test_app_without_fixture_hooks_finds_true_first_pass_and_clicks_each_width(application, profile, tmp_path):
    url, config, path = application
    record = pp.collect('chromium', profile, adapter=str(path), widths=(320, 390), evidence_dir=str(tmp_path/'shots'))
    assert record['verdict'] == 'pass'
    assert record['min_ok_width'] == 260  # binary search would miss this passing island
    assert [s['width'] for s in record['samples']] == [260, 320, 390]
    assert all(s['click']['before'] == '0' and s['click']['after'] == '1' for s in record['samples'])
    assert record['facts']['fonts']['sans'] > 0
    assert record['target']['url'] == url and record['target']['config_sha256']
    assert (tmp_path/'shots/width-260.png').exists()
    assert record['env']['device_validation'] == ('emulation' if profile == 'pixel' else 'desktop-browser')


@pytest.mark.browser
def test_overlap_occlusion_missing_nodes_and_real_click_failure(application):
    from playwright.sync_api import sync_playwright
    url, config, _ = application
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={'width':390,'height':844})
            page.goto(url)
            assert pa.layout(page, config)['ok']
            page.locator('#increment').evaluate("e => e.style.transform='translateY(-20px)'")
            assert any(s.startswith('overlap:') for s in pa.layout(page, config)['failed'])
            page.locator('#increment').evaluate("e => e.style.transform='' ")
            page.locator('#cover').evaluate("e => e.style.display='block'")
            assert any(s.startswith('occluded:') for s in pa.layout(page, config)['failed'])
            # Even for Flutter forwarding mode, a coordinate click must change application state.
            assert not pa.click_check(page, {**config, 'flutter_semantics': True}, False)['ok']
            page.locator('#title').evaluate('e => e.remove()')
            assert any(s.startswith('missing_or_ambiguous:') for s in pa.layout(page, config)['failed'])
        finally:
            browser.close()
