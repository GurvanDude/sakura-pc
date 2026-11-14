"""Tests des règles du diagnostic, sans lecture du PC réel."""

from sakura_opt.diagnose import diagnose


def rows(**changes):
    base = {
        "cpu": 35, "core_max": 45, "ram": 55, "swap": 4,
        "gpu": 40, "vram_gb": 4, "vram_total_gb": 16,
        "cpu_temp": 65, "gpu_temp": 60, "gpu_hotspot": 72,
        "cpu_clock": 4500, "disk_busy": 20, "c_free_gb": 100,
        "fg_app": "Ghost of Tsushima", "top_app": "Ghost of Tsushima",
        "top_cpu_app": "Ghost of Tsushima", "top_cpu": 30,
        "top_ram_app": "Ghost of Tsushima", "top_ram_gb": 3,
    }
    base.update(changes)
    return [dict(base, t=float(index * 60)) for index in range(4)]


def status(row):
    return {
        "fg_app": row.get("fg_app"),
        "cpu": {"percent": row.get("cpu"), "per_core": [row.get("core_max")]},
        "ram": {"percent": row.get("ram"), "swap_percent": row.get("swap")},
        "gpu": {
            "percent": row.get("gpu"), "vram_used_gb": row.get("vram_gb"),
            "vram_total_gb": row.get("vram_total_gb"),
        },
        "temps": {
            "cpu": row.get("cpu_temp"), "gpu": row.get("gpu_temp"),
            "gpu_hotspot": row.get("gpu_hotspot"), "cpu_clock_mhz": row.get("cpu_clock"),
        },
        "disk": {
            "per_disk": {"Disque 0": {"busy_percent": row.get("disk_busy")}},
            "partitions": [{"mount": "C:\\", "free_gb": row.get("c_free_gb")}],
        },
        "top_cpu": [{
            "name": row.get("top_cpu_app"), "friendly_name": row.get("top_cpu_app"),
            "cpu_percent": row.get("top_cpu"), "ram_mb": 200,
        }],
        "top_ram": [{
            "name": row.get("top_ram_app"), "friendly_name": row.get("top_ram_app"),
            "cpu_percent": 2, "ram_mb": (row.get("top_ram_gb") or 0) * 1024,
        }],
    }


def run(sample_rows, baseline=None):
    return diagnose(sample_rows, status(sample_rows[-1]), baseline)


def ids(result):
    return [finding["id"] for finding in result["findings"]]


def test_gpu_limitee_et_verdict_nomme_le_jeu():
    result = run(rows(gpu=98, cpu=55))

    assert result["bottleneck"] == "gpu"
    assert "Ghost of Tsushima" in result["verdict"]["title"]
    assert "carte graphique" in result["verdict"]["title"]


def test_vram_pleine():
    result = run(rows(vram_gb=15.5, vram_total_gb=16))

    assert "vram" in ids(result)
    assert next(item for item in result["findings"] if item["id"] == "vram")["severity"] == "attention"


def test_cpu_total_a_fond_et_appli_affichee():
    result = run(rows(cpu=94, top_cpu_app="Compilation", top_cpu=72))

    finding = next(item for item in result["findings"] if item["id"] == "cpu")
    assert any("Compilation" in item["value"] for item in finding["evidence"])


def test_coeur_unique_a_fond():
    result = run(rows(cpu=42, core_max=99, gpu=60))

    assert result["bottleneck"] == "cpu_core"


def test_coeur_unique_promene_par_windows(monkeypatch):
    # cas réel : le fil du jeu saute d'un cœur à l'autre, aucun cœur n'atteint 95 %,
    # mais le jeu au premier plan consomme à lui seul un cœur entier sur 16
    monkeypatch.setattr("sakura_opt.diagnose.psutil.cpu_count", lambda *a, **k: 16)
    result = run(rows(cpu=20, core_max=80, gpu=55, top_cpu=6.2))

    assert result["bottleneck"] == "cpu_core"


def test_coeur_charge_par_une_appli_en_fond_n_est_pas_un_coeur_unique(monkeypatch):
    monkeypatch.setattr("sakura_opt.diagnose.psutil.cpu_count", lambda *a, **k: 16)
    result = run(rows(cpu=20, core_max=80, gpu=55, top_cpu=6.2, top_cpu_app="Opera GX"))

    assert result["bottleneck"] != "cpu_core"


def test_ram_pleine_conseille_l_appli_lourde_en_fond():
    result = run(rows(ram=94, top_ram_app="Navigateur", top_ram_gb=5.25))

    finding = next(item for item in result["findings"] if item["id"] == "ram")
    assert finding["severity"] == "grave"
    assert any("Navigateur" in advice and "5,2 Go" in advice for advice in finding["advice"])
    assert any("5,2 Go" in item["value"] for item in finding["evidence"])


def test_ram_avec_swap_en_hausse_et_disque_occupe():
    sample_rows = rows(ram=87, disk_busy=75)
    for index, row in enumerate(sample_rows):
        row["swap"] = 3 + index * 2

    assert "ram" in ids(run(sample_rows))


def test_chaleur_cpu_avec_baisse_de_vitesse_et_baseline():
    sample_rows = rows(cpu_temp=87, cpu_clock=4500)
    sample_rows[-1]["cpu_clock"] = 3200
    result = run(sample_rows, {"cpu_temp": 74})

    finding = next(item for item in result["findings"] if item["id"] == "chaleur_cpu")
    assert any("ralentit" in item["value"] for item in finding["evidence"])
    assert any("+13 °C" in item["value"] for item in finding["evidence"])


def test_chaleur_gpu():
    result = run(rows(gpu_hotspot=108))

    assert "chaleur_gpu" in ids(result)


def test_disque_deborde_et_disque_c_presque_plein():
    result = run(rows(disk_busy=96, c_free_gb=8.4))

    assert "disque" in ids(result)
    assert "disk_space" in ids(result)
    space = next(item for item in result["findings"] if item["id"] == "disk_space")
    assert space["evidence"][0]["value"] == "8,4 Go"


def test_application_en_fond_pendant_un_jeu():
    result = run(rows(
        gpu=82, top_cpu_app="Discord", top_cpu=18,
        top_ram_app="Discord", top_ram_gb=2.4,
    ))

    finding = next(item for item in result["findings"] if item["id"] == "fond")
    assert "Discord" in finding["title"]
    assert any("18 %" in item["value"] for item in finding["evidence"])


def test_aucun_frein():
    result = run(rows())

    assert result["bottleneck"] == "aucun"
    assert result["verdict"]["mood"] == "ok"
    assert result["verdict"]["title"] == "Rien ne freine ton PC"


def test_donnees_insuffisantes_analysent_l_instant_present():
    sample_rows = rows(gpu=98, cpu=40)[:1]
    result = run(sample_rows)

    assert result["enough_data"] is False
    assert result["bottleneck"] == "gpu"
    assert "moins sûre" in result["verdict"]["text"]


def test_priorite_grave_devant_attention_et_information():
    result = run(rows(cpu=94, ram=96, gpu=98, vram_gb=15.8))

    assert result["findings"][0]["id"] == "ram"
    assert result["bottleneck"] == "ram"
