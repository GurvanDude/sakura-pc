import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture
def launcher_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("SAKURA_HOME", str(tmp_path))
    app_dir = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(app_dir))
    for name in ("settings", "launcher", "core.paths"):
        sys.modules.pop(name, None)
    paths = importlib.import_module("core.paths")
    launcher = importlib.import_module("launcher")
    settings = importlib.import_module("settings")
    return settings, launcher, paths
