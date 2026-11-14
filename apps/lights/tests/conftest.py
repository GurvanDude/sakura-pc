import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
LIGHTS_PY = REPO / 'apps' / 'lights' / 'lights.py'


@pytest.fixture
def lights_module(tmp_path, monkeypatch):
    home = tmp_path / 'sakura-home'
    home.mkdir()
    (home / 'config.json').write_text(json.dumps({
        'settings': {
            'day_start': 8,
            'day_end': 18,
            'ram_driver': 'openrgb',
        },
        'lights': {},
    }), encoding='utf-8')

    monkeypatch.setenv('SAKURA_HOME', str(home))
    monkeypatch.syspath_prepend(str(REPO))
    sys.modules.pop('core.paths', None)
    sys.modules.pop('sakura_lights_test', None)
    core = sys.modules.get('core')
    if core is not None and hasattr(core, 'paths'):
        monkeypatch.delattr(core, 'paths')

    spec = importlib.util.spec_from_file_location('sakura_lights_test', LIGHTS_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
