"""Tests de la fenêtre et du petit serveur local de l'Optimizer."""

from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from app import Api, Monitor, _serve


class FakeMonitor:
    def get(self):
        return {
            "cpu": {"percent": 20, "per_core": [25]},
            "ram": {"percent": 40, "swap_percent": 2},
            "gpu": {"percent": 30, "vram_used_gb": 2, "vram_total_gb": 16},
            "disk": {"per_disk": {}, "partitions": [{"mount": "C:\\", "free_gb": 100}]},
            "temps": {"cpu": 60, "gpu": 55, "gpu_hotspot": 65, "cpu_clock_mhz": 4200},
            "top_cpu": [], "top_ram": [],
        }


class FakeHistory:
    def __init__(self):
        self.recorded = []

    def record(self, status, temps=None):
        self.recorded.append((status, temps))

    def query(self, _seconds):
        return [{"t": 100, "cpu": 20, "ram": 40, "gpu": 10, "cpu_temp": 60}]

    def summary(self, _seconds):
        return {"duration_s": 600, "top_app": "Jeu", "avg_cpu": 20}


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


def test_periode_historique_partage_le_fichier_du_theme(tmp_path):
    theme_path = tmp_path / "optimizer.json"
    api = Api(FakeMonitor(), theme_path=theme_path, config_path=tmp_path / "missing.json")

    api.set_theme("night")
    assert api.set_history_period("6h") == "6h"

    assert api.get_history_period() == "6h"
    assert json.loads(theme_path.read_text(encoding="utf-8")) == {
        "theme": "night", "history_period": "6h",
    }


def test_get_history_renvoie_les_series_et_la_vue(tmp_path):
    api = Api(
        FakeMonitor(), theme_path=tmp_path / "theme.json", history=FakeHistory()
    )

    payload = api.get_history("1h")

    assert payload["series"][0]["cpu"] == 20
    assert "view" in payload
    assert "Jeu" in payload["view"]["sentence"]


def test_fenetre_n_enregistre_pas_si_mutex_deja_pris():
    history = FakeHistory()
    monitor = Monitor(sampler=object(), history=history, mutex_factory=lambda: None, start=False)

    monitor._record_history({"temps": {"cpu": 60}}, now=0)

    assert history.recorded == []


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
    api = Api(FakeMonitor(), theme_path=tmp_path / "theme.json", history=FakeHistory())
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
    with urlopen(local_server + "/api/history?period=1h") as response:
        history = json.load(response)
    assert set(history) == {"series", "view"}
    with urlopen(local_server + "/api/diagnose?minutes=2") as response:
        diagnostic = json.load(response)
    assert diagnostic["minutes"] == 2
    assert isinstance(diagnostic["findings"], list)


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
