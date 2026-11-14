"""Tests de l'enregistreur utilisateur, sans lancer de boucle de fond."""

from sakura_opt.history import History
from tools.history_recorder import record_once


class FakeSampler:
    def sample(self):
        row = {
            "pid": 999999, "name": "jeu.exe", "cpu_percent": 42, "ram_mb": 800,
        }
        return {
            "cpu": {"percent": 42}, "ram": {"percent": 50},
            "gpu": {"percent": 30}, "disk": {"read_mb_s": 2, "write_mb_s": 1},
            "top_cpu": [row], "top_ram": [dict(row)],
        }


def test_une_iteration_ajoute_une_ligne(tmp_path):
    clock = [1_000.0]
    history = History(tmp_path / "history.db", now=lambda: clock[0])

    record_once(
        FakeSampler(), history,
        temps_reader=lambda: {"cpu": 63, "gpu": 54, "gpu_hotspot": 61},
    )

    rows = history.query(10)
    assert len(rows) == 1
    assert rows[0]["cpu"] == 42
    assert rows[0]["cpu_temp"] == 63
    assert rows[0]["top_app"] == "jeu"
