"""Consumer wiring only; generic gh_ops regressions live in the parent repository."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_module_imports_with_adjacent_identity():
    spec = importlib.util.spec_from_file_location('consumer_gh_ops', ROOT / 'scripts/gh_ops.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert Path(module.gh_identity.__file__).resolve() == ROOT / 'scripts/gh_identity.py'
    assert callable(module.pr_status)
    assert callable(module.checks_status)


def test_canonical_cli_help_works_without_site_packages_or_credentials(tmp_path):
    result = subprocess.run([sys.executable, '-S', str(ROOT / 'scripts/gh_ops.py'), '--help'],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert 'usage:' in result.stdout.lower()
    assert not list(tmp_path.iterdir())


def test_gh_ops_is_a_locked_parent_dependency():
    lock = json.loads((ROOT / 'vendor.lock.json').read_text())
    entries = [e for e in lock['files'] if e['destination'] == 'scripts/gh_ops.py']
    assert len(entries) == 1
    assert entries[0]['repository'] == 'myon-bioinformatics/myon-bioinformatics'
    assert entries[0]['source'] == 'gh_ops.py'
    assert entries[0]['ref'] == 'refs/heads/main'
