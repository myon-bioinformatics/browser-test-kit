"""Expected URL decisions and preflight side effects, not just twin agreement."""
import asyncio
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trail = load('route_trail')
twins = load('twin_parity')
VALID = [
    'http://a:1/', 'http://a:65535/', 'http://a:00001/',
    'https://localhost:443/x?q=1#f', 'HTTP://A/', 'http://example.com./',
    'http://127.0.0.1:65535/', 'http://0.0.0.0/', 'http://255.255.255.255/',
    'http://[::1]:65535/', 'https://[2001:db8::1]/',
    'http://[::ffff:192.0.2.1]:80/', 'http://[1:2:3:4:5:6:7:8]/',
    'file:///tmp/a', 'file://localhost/tmp/a', 'FILE:///C:/temp/a',
    'http://a/日本語?q=絵文字😀#内容', 'http://a/?next=http://b:99999/',
    'http://a/' + '😀' * (4096 - len('http://a/')),
]
INVALID = [
    'http://a:0/', 'http://a:00000/', 'http://a:65536/', 'http://a:99999/',
    'http://[::1]:0/', 'http://[::1]:65536/', 'http://a:-1/', 'http://a:+80/',
    'http://a:/', 'http://a:123456/', 'http://a:８０/', 'http://a:80:90/',
    'http://[::::]/', 'http://[1.2.3.4]/', 'http://[1:2:3]/',
    'http://[1:2:3:4:5:6:7:8:9]/', 'http://[::ffff:999.0.0.1]/',
    'http://[fe80::1%25eth0]/', 'http://::1/', 'http://[::1/', 'http://[::1]]/',
    'http://a b/', 'http://a\t/', 'http://a\n/', 'http://a/\n', 'http://a/\r',
    'http://a/\u00a0', 'http://a/\u2003', 'http://a/\ufeff', 'http://a/\x00',
    'http://a/\u0085', 'http://a/\\b', 'http://a\\@b/',
    'http://user:pass@a/', 'http://a%2fb/', 'http://a%00/', 'http://a<b/',
    'http://a>b/', 'http://a^b/', 'http://a|b/', 'http://a_b/', 'http://a"b/',
    'http:///a/', 'http:///', 'http://?a/', 'http://#a/', 'http:/a/', '//a/',
    'http://.a/', 'http://a..b/', 'http://-a/', 'http://a-/', 'http://a../',
    'http://256.0.0.1/', 'http://1.2.3.999/', 'http://127.1/', 'http://2130706433/',
    'http://0177.0.0.1/', 'http://0x7f.0.0.1/', 'http://example.123/', 'http://0x/',
    'http://xn--a/', 'https://例え.jp/', 'http://xn--r8jz45g.jp/',
    'http://' + 'a'*64 + '/', 'http://' + '.'.join(['a'*63]*4) + '/',
    'file:/tmp/a', 'file://', 'file://remote/tmp/a', 'file://localhost:80/tmp/a',
    'ftp://a/', 'javascript:alert(1)', ' http://a/',
    'http://a/' + '😀' * (4097 - len('http://a/')),
]


def step(url):
    return {'emoji': '🏠', 'route': '/', 'url': url}


@pytest.mark.parametrize('url,expected', [(u, True) for u in VALID] + [(u, False) for u in INVALID])
def test_python_expected_url_decisions(url, expected):
    if expected:
        assert trail.validate_steps([step(url)]) == [step(url)]
    else:
        with pytest.raises(ValueError, match='execution URLs'):
            trail.validate_steps([step(url)])


@pytest.mark.skipif(shutil.which('node') is None, reason='node unavailable')
def test_node_expected_decisions_and_native_parser_agree():
    cases = [[[step(url)]] for url in VALID + INVALID]
    actual = twins.node_calls(ROOT / 'scripts/route_trail_node.mjs', 'validateSteps', cases)
    assert [r['ok'] for r in actual] == [True]*len(VALID) + [False]*len(INVALID)
    # An independent implementation checks the positive oracle is browser-parseable.
    parsed = subprocess.run(['node', '--input-type=module', '-e',
        'const urls=JSON.parse(process.argv[1]);for(const u of urls)new URL(u);', json.dumps(VALID)],
        capture_output=True, text=True, timeout=30)
    assert parsed.returncode == 0, parsed.stderr


@pytest.mark.skipif(shutil.which('node') is None, reason='node unavailable')
def test_port_boundaries_have_expected_decisions_for_both_twins():
    urls = [f'http://{host}:{port}/' for host in ('a', '127.0.0.1', '[::1]')
            for port in (0, 1, 65534, 65535, 65536, 99999)]
    expected = [port in (1, 65534, 65535) for _ in range(3)
                for port in (0, 1, 65534, 65535, 65536, 99999)]
    cases = [[[step(u)]] for u in urls]
    for results in (twins.python_calls(trail.validate_steps, cases),
                    twins.node_calls(ROOT / 'scripts/route_trail_node.mjs', 'validateSteps', cases)):
        assert [r['ok'] for r in results] == expected


@pytest.mark.parametrize('bad_url', INVALID)
def test_invalid_later_step_prevents_python_navigation_and_process(monkeypatch, bad_url):
    plan = [step('http://localhost/'), step(bad_url)]
    monkeypatch.setattr(trail, 'resolve', lambda *a, **kw: plan)
    class Page:
        def goto(self, *a, **kw):
            pytest.fail('navigation began before whole-plan validation')
    def run(*a, **kw):
        pytest.fail('runtime subprocess began before whole-plan validation')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(ValueError):
        trail.walk(Page(), 'unused', {})
    with pytest.raises(ValueError):
        asyncio.run(trail.awalk(Page(), 'unused', {}))
    for backend in ('python', 'python-async', 'node'):
        with pytest.raises(ValueError):
            trail.run_plan(plan, backend=backend)


@pytest.mark.skipif(shutil.which('node') is None, reason='node unavailable')
def test_invalid_later_step_prevents_node_navigation():
    script = """
import {walk,walkSteps} from './scripts/route_trail_node.mjs';
let calls=0;
const page={goto(){calls++;throw Error('navigation called');}};
for(const url of JSON.parse(process.argv[1])){
  const plan=[{emoji:'a',route:'/',url:'http://localhost/'},{emoji:'b',route:'/b',url}];
  for(const iterate of [false,true]){
    let rejected=false;
    try{if(iterate){for await(const row of walkSteps(page,plan)){};}else await walk(page,plan);}
    catch(e){if(!e.message.includes('execution URLs'))throw e;rejected=true;}
    if(!rejected)throw Error('invalid plan accepted');
  }
}
if(calls!==0)throw Error('navigation began');
"""
    result = subprocess.run(['node', '--input-type=module', '-e', script, json.dumps(INVALID)],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
