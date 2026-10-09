"""Exercise real Chromium against a deterministic local HTTP fixture."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import pytest


def test_dom_capture_local_page(tmp_path):
    (tmp_path/'index.html').write_text('<!doctype html><meta charset="utf-8"><main id="body"><h1>日本語</h1><p>Body &amp; text</p></main>',encoding='utf-8')
    handler=functools.partial(SimpleHTTPRequestHandler,directory=str(tmp_path))
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        script=Path(__file__).resolve().parents[2]/'examples/capture_browser_dom.py'
        output=tmp_path/'capture.json'
        args=[sys.executable,str(script),f'http://127.0.0.1:{server.server_port}/index.html',
              '--selector','#body','--output',str(output)]
        run=subprocess.run(args,capture_output=True,text=True,timeout=90)
        assert run.returncode==0,run.stderr
        result=json.loads(output.read_text())
        assert result['schema']=='btk-browser-dom/1'
        assert 'Body &amp; text' in result['html']
        assert result['visible'].split()==['日本語','Body','&','text']
        assert result['content_verified'] is False
        # A repeated capture must preserve the original evidence byte for byte.
        original = output.read_bytes()
        repeat = subprocess.run(args, capture_output=True, text=True, timeout=10)
        assert repeat.returncode == 2
        assert 'output already exists' in repeat.stderr
        assert output.read_bytes() == original
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


@pytest.mark.parametrize('selector,code,error', [
    ('#missing', 2, 'Timeout'),
    ('p', 1, 'ambiguous_selector'),
])
def test_selector_mismatch_does_not_save(tmp_path, selector, code, error):
    (tmp_path / 'index.html').write_text('<main><p>one</p><p>two</p></main>', encoding='utf-8')
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        script = Path(__file__).resolve().parents[2] / 'examples/capture_browser_dom.py'
        output = tmp_path / 'capture.json'
        run = subprocess.run(
            [sys.executable, str(script), f'http://127.0.0.1:{server.server_port}/index.html',
             '--selector', selector, '--output', str(output), '--timeout-ms', '3000'],
            capture_output=True, text=True, timeout=30)
        assert run.returncode == code, run.stderr
        assert error in run.stderr
        assert not output.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
