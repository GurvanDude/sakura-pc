"""Tests de la fenêtre et du petit serveur local de l'Optimizer."""

from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from app import Api, _serve


class FakeMonitor:
    def get(self):
        return None


def test_free_space_utilise_l_ouvreur_injecte(tmp_path):
    opened = []
    api = Api(FakeMonitor(), theme_path=tmp_path / "theme.json", opener=opened.append)

    api.free_space()

    assert opened == ["ms-settings:storagesense"]


def test_theme_est_memorise_dans_le_fichier_utilisateur(tmp_path):
    theme_path = tmp_path / "optimizer.json"
    api = Api(FakeMonitor(), theme_path=theme_path, config_path=tmp_path / "missing.json")

    assert api.get_theme() == "day"
    assert api.set_theme("night") == "night"
    assert api.get_theme() == "night"
    assert json.loads(theme_path.read_text(encoding="utf-8")) == {"theme": "night"}


def test_theme_par_defaut_suit_les_horaires_du_launcher(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"settings": {"day_start": 0, "day_end": 24}}), encoding="utf-8"
    )
    api = Api(FakeMonitor(), theme_path=tmp_path / "missing.json", config_path=config_path)

    assert api.get_theme() == "day"

    config_path.write_text(
        json.dumps({"settings": {"day_start": 0, "day_end": 0}}), encoding="utf-8"
    )
    assert api.get_theme() == "night"


@pytest.fixture
def local_server(tmp_path):
    api = Api(FakeMonitor(), theme_path=tmp_path / "theme.json")
    server, port = _serve(api)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_server_sert_le_kit_et_la_vue_json(local_server):
    with urlopen(local_server + "/design/ui/sakura.js") as response:
        assert b"global.Sakura" in response.read()
    with urlopen(local_server + "/api/view") as response:
        payload = json.load(response)
    assert "view" in payload


@pytest.mark.parametrize(
    "path",
    [
        "/../design/ui/sakura.js",
        "/design/ui/../tokens.css",
        "/design/ui/%2e%2e/sakura.js",
        "/design/ui/../../apps/optimizer/app.py",
    ],
)
def test_server_refuse_les_remontees_de_chemin(local_server, path):
    with pytest.raises(HTTPError) as error:
        urlopen(local_server + path)
    assert error.value.code == 404
