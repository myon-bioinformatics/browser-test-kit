"""Keep the stdlib distribution separate from supported optional/dev environments."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_metadata_support_split():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    assert project['project']['requires-python'] == '>=3.9'
    assert project['project'].get('dependencies', []) == []
    assert project['project']['optional-dependencies']['image'] == ['pillow>=13']
    assert project['tool']['uv']['environments'] == ["python_version >= '3.11'"]
    for name in ('dev', 'browser'):
        assert project['tool']['uv']['dependency-groups'][name]['requires-python'] == '>=3.11'
    assert 'pillow>=13' in project['dependency-groups']['dev']
    assert 'pip>=26.2' in project['dependency-groups']['dev']
    requirements = (ROOT / 'requirements-test-core.txt').read_text()
    assert 'pillow>=13' in requirements
    assert 'pip>=26.2' in requirements
    assert 'pytest>=9.0.3' in requirements


def test_lock_has_no_legacy_pillow_or_pip():
    lock = tomllib.loads((ROOT / 'uv.lock').read_text())
    assert lock['supported-markers'] == ["python_full_version >= '3.11'"]
    for package in lock['package']:
        version = tuple(map(int, package['version'].split('.')))
        if package['name'] == 'pillow':
            assert version >= (13,)
        if package['name'] == 'pip':
            assert version >= (26, 2)
        if package['name'] == 'pytest':
            assert version >= (9, 0, 3)


def test_built_wheel_metadata_when_present():
    from email.parser import Parser
    import zipfile

    wheels = list((ROOT / 'dist').glob('*.whl'))
    if not wheels:
        import pytest
        pytest.skip('Run uv build first to inspect the distributable metadata')
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            path = next(p for p in archive.namelist() if p.endswith('.dist-info/METADATA'))
            metadata = Parser().parsestr(archive.read(path).decode())
        assert metadata['Requires-Python'] == '>=3.9'
        assert metadata.get_all('Requires-Dist') == ['pillow>=13; extra == "image"']
