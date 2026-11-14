"""Tests de l'historique local, sans toucher aux données de l'utilisateur."""

import sqlite3

from sakura_opt.explain import history_view
from sakura_opt.history import History, NEW_COLUMNS


def sample(cpu=20, ram=40, gpu=30, cpu_temp=60, gpu_temp=55, app="Mon jeu"):
    row = {"pid": 12, "name": f"{app}.exe", "friendly_name": app, "cpu_percent": cpu, "ram_mb": 800}
    return {
        "cpu": {"percent": cpu, "freq_mhz": 4200, "per_core": [12, 82]},
        "ram": {"percent": ram, "total_gb": 16, "swap_percent": 7},
        "gpu": {"percent": gpu, "vram_used_gb": 3.5, "vram_total_gb": 16},
        "disk": {
            "read_mb_s": 12, "write_mb_s": 4,
            "per_disk": {"Disque 0": {"busy_percent": 34}},
            "partitions": [{"mount": "C:\\", "free_gb": 123}],
        },
        "temps": {"cpu": cpu_temp, "gpu": gpu_temp, "gpu_hotspot": gpu_temp + 8, "cpu_clock_mhz": 4200},
        "top_cpu": [row], "top_ram": [row],
    }


def test_record_query_et_reduction(tmp_path):
    clock = [10_000.0]
    history = History(tmp_path / "history.db", now=lambda: clock[0])
    for index in range(30):
        clock[0] = 9_700 + index * 10
        history.record(sample(cpu=index))
    clock[0] = 10_000

    rows = history.query(400, points=6)

    assert 1 < len(rows) <= 6
    assert all(set(("t", "cpu", "ram", "gpu", "cpu_temp", "top_app")) <= set(row) for row in rows)
    assert rows[-1]["core_max"] == 82
    assert rows[-1]["swap"] == 7
    assert rows[-1]["vram_total_gb"] == 16
    assert rows[-1]["disk_busy"] == 34
    assert rows[-1]["c_free_gb"] == 123
    assert rows[-1]["top_cpu_app"] == "Mon jeu"
    assert rows[-1]["top_ram_gb"] == 0.78


def test_migration_ancienne_base_conserve_et_complete_les_lignes(tmp_path):
    path = tmp_path / "ancienne.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE samples (t REAL NOT NULL, cpu REAL, ram REAL, gpu REAL, "
                           "vram_gb REAL, cpu_temp REAL, gpu_temp REAL, gpu_hotspot REAL, "
                           "cpu_clock REAL, disk_read REAL, disk_write REAL, top_app TEXT)")
        connection.execute("INSERT INTO samples (t, cpu, top_app) VALUES (900, 42, 'Ancien jeu')")
    history = History(path, now=lambda: 1000)

    old = history.query(200)
    history.record(sample())

    assert old[0]["cpu"] == 42
    assert old[0]["core_max"] is None
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(samples)")}
        count = connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert set(NEW_COLUMNS) <= columns
    assert count == 2


def test_summary_max_temperature_heure_et_appli_frequente(tmp_path):
    clock = [1_000.0]
    history = History(tmp_path / "history.db", now=lambda: clock[0])
    for when, temp, app in ((800, 60, "Jeu"), (900, 78, "Jeu"), (950, 70, "Navigateur")):
        clock[0] = when
        history.record(sample(cpu_temp=temp, app=app))
    clock[0] = 1_000

    result = history.summary(300)

    assert result["max_cpu_temp"] == 78
    assert result["max_cpu_temp_t"] == 900
    assert result["top_app"] == "Jeu"
    assert result["duration_s"] == 150


def test_prune_supprime_les_anciennes_lignes(tmp_path):
    clock = [1_000_000.0]
    history = History(tmp_path / "history.db", now=lambda: clock[0])
    history.record(sample())
    with history._connect() as connection:
        connection.execute("INSERT INTO samples (t, cpu) VALUES (?, ?)", (1.0, 99))

    history.prune(days=7)

    assert all(row["t"] != 1.0 for row in history.query(2_000_000, points=120))


def test_query_conserve_un_trou_visible(tmp_path):
    clock = [100.0]
    history = History(tmp_path / "history.db", now=lambda: clock[0])
    history.record(sample())
    clock[0] = 500
    history.record(sample())

    rows = history.query(500, points=120)

    assert len(rows) == 2
    assert rows[1]["t"] - rows[0]["t"] == 400


def test_base_absente_donne_des_resultats_vides(tmp_path):
    history = History(tmp_path / "absente.db")

    assert history.query(3600) == []
    assert history.summary(3600) == {}
    assert not history.path.exists()


def test_history_view_assez_de_donnees():
    summary = {
        "duration_s": 600, "top_app": "Ghost of Tsushima", "avg_cpu": 35,
        "max_cpu": 81, "max_cpu_t": 1_700_000_000,
        "max_gpu": 92, "max_gpu_t": 1_700_000_010,
        "max_cpu_temp": 72, "max_cpu_temp_t": 1_700_000_020,
        "max_gpu_temp": 68, "max_gpu_temp_t": 1_700_000_030,
        "max_ram": 74, "max_ram_t": 1_700_000_040,
    }

    view = history_view([{"t": 1}], summary, "la dernière heure")

    assert "Ghost of Tsushima" in view["sentence"]
    assert "35 %" in view["sentence"]
    assert "72 °C" in view["sentence"]
    assert len(view["facts"]) == 6


def test_history_view_pas_assez_de_donnees():
    view = history_view([], {"duration_s": 119}, "les 15 dernières minutes")

    assert "pas encore assez de souvenirs" in view["sentence"]
    assert view["facts"] == []
