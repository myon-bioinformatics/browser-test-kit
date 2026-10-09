"""Exercise real Chromium against a deterministic local HTTP fixture."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading


def test_dom_capture_local_page(tmp_path):
    (tmp_path/'index.html').write_text('<main id="body"><h1>日本語</h1><p>Body &amp; text</p></main>',encoding='utf-8')
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
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
