"""Configuration commune aux tests de Sakura AI."""

import importlib
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(APP))


@pytest.fixture
def sakura_home(tmp_path, monkeypatch):
    """Isole tous les fichiers personnels dans le dossier du test."""
    monkeypatch.setenv("SAKURA_HOME", str(tmp_path))
    from core import paths

    importlib.reload(paths)
    return tmp_path

