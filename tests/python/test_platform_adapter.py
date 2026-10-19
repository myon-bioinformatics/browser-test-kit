"""Offline adapter contracts, dataset identity and app verdict gating."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('platform_probe', ROOT / 'scripts/platform_probe.py')
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)
pa = pp.adapters


def config():
    return {'schema': 'btk-platform-adapter/1', 'id': 'demo', 'url': 'https://example.test/',
            'elements': ['#title', '#action'],
            'click': {'target': '#action', 'observe': '#action', 'attribute': 'data-clicks', 'before': '0', 'after': '1'}}


@pytest.mark.parametrize('url', ['file:///tmp/a', 'javascript:alert(1)', 'https://user:pass@example.test/', ''])
def test_reject_non_http_and_credentials(url):
    with pytest.raises(ValueError):
        pa.validate_url(url)


def test_adapters_are_valid_and_target_identity_is_sensitive_to_url_and_rules():
    for path in (ROOT / 'adapters').glob('*.json'):
        pa.load_adapter(path)
    a = config()
    first = pa.target_identity(a, a['url'])
    assert first == pa.target_identity(a, a['url'])
    assert first['key'] != pa.target_identity(a, a['url'] + '#counter')['key']
    assert first['key'] != pa.target_identity({**a, 'elements': ['#action']}, a['url'])['key']


@pytest.mark.parametrize('change', [{'schema': 'bad'}, {'id': '../bad'}, {'elements': []}, {'click': {}},
                                    {'elements': ['#other']}])
def test_invalid_adapter_fails_before_browser_launch(tmp_path, change):
    path = tmp_path / 'adapter.json'
    path.write_text(json.dumps({**config(), **change}))
    with pytest.raises(ValueError):
        pa.load_adapter(path)


def test_same_environment_different_targets_do_not_overwrite(tmp_path):
    base = {'schema': pp.FACTS_SCHEMA, 'env': {'id': 'Linux-chromium-desktop-headless'}}
    records = [base, {**base, 'target': {'key': 'flutter-home-a'}},
               {**base, 'target': {'key': 'flutter-counter-b'}}]
    for n, record in enumerate(records):
        (tmp_path / f'{n}.json').write_text(json.dumps(record))
    assert len(pp.load_records([str(tmp_path)])) == 3
    page = pp.render(records)
    assert "['Target'" in page and '実機ではありません' in page


@pytest.mark.parametrize('layout,click', [(False, True), (True, False)])
def test_narrow_width_failure_gates_verdict_even_if_initial_passes(layout, click):
    record = {'layout': {'ok': True}, 'click': {'ok': True},
              'samples': [{'layout': {'ok': layout}, 'click': {'ok': click}}]}
    assert pp.verdict(record) == 'fail'


def test_fixture_workflow_remains_42_and_published_lane_is_separate():
    fixture = (ROOT / '.github/workflows/platform-matrix.yml').read_text()
    apps = (ROOT / '.github/workflows/platform-apps.yml').read_text()
    assert 'os: [ubuntu-24.04, windows-latest, macos-latest]' in fixture
    assert 'for profile in desktop iphone pixel' in fixture
    assert '--adapter' not in fixture
    assert '--adapter' in apps and 'needs: published-flutter' in apps
