"""Tests des explications en français courant."""

from sakura_opt.explain import explain


def status(cpu=12, ram=35, gpu=8, partitions=None):
    return {
        "cpu": {"percent": cpu},
        "ram": {"percent": ram, "used_gb": 5.6, "total_gb": 16, "available_gb": 10.4},
        "gpu": {"percent": gpu},
        "disk": {"partitions": partitions or [{"mount": "C:\\", "percent": 42, "free_gb": 201}]},
        "temps": {"cpu": 65, "gpu": 55, "reason": None},
        "top_cpu": [{"pid": 7, "name": "jeu.exe", "cpu_percent": 50, "ram_mb": 900}],
        "top_ram": [{"pid": 7, "name": "jeu.exe", "cpu_percent": 50, "ram_mb": 900}],
    }


def test_verdict_ok(monkeypatch):
    monkeypatch.setattr("sakura_opt.names.friendly_name", lambda _pid, name: name.removesuffix(".exe"))
    view = explain(status())
    assert view["verdict"]["mood"] == "ok"
    assert view["tips"] == []


def test_verdict_busy():
    sample = status(cpu=82)
    for row in sample["top_cpu"] + sample["top_ram"]:
        row["friendly_name"] = "Mon jeu"
    view = explain(sample)
    assert view["verdict"]["mood"] == "busy"
    assert "Mon jeu" in view["verdict"]["title"]


def test_disk_warn_and_tip_uses_room_on_d(monkeypatch):
    monkeypatch.setattr("sakura_opt.names.friendly_name", lambda _pid, name: name)
    view = explain(status(partitions=[
        {"mount": "C:\\", "percent": 98, "free_gb": 17.6},
        {"mount": "D:\\", "percent": 14, "free_gb": 801},
    ]))
    assert view["verdict"]["mood"] == "warn"
    assert "C" in view["verdict"]["title"]
    assert any("D" in tip["text"] and "801 Go" in tip["text"] for tip in view["tips"])
    storage = next(card for card in view["cards"] if card["id"] == "stockage")
    assert storage["figures"][0] == {
        "label": "Disque C", "value": "98 % plein · 17,6 Go libres", "hint": "presque plein"
    }


def test_figures_are_always_well_formed():
    view = explain(status())
    assert all(card["figures"] for card in view["cards"])
    assert all(
        set(figure) == {"label", "value", "hint"}
        for card in view["cards"] for figure in card["figures"]
    )


def test_none_status_is_safe():
    view = explain({key: None for key in ("cpu", "ram", "gpu", "disk", "temps", "top_cpu", "top_ram")})
    assert len(view["cards"]) == 4
    assert all(card["level"] == "inconnu" for card in view["cards"])
    assert all("Impossible" in card["sentence"] for card in view["cards"])
    assert all(card["figures"][0]["value"] == "—" for card in view["cards"])


def test_temperature_vitesse_et_hints_sont_expliques():
    sample = status()
    sample["temps"].update({"cpu": 72, "cpu_clock_mhz": 4500, "gpu_hotspot": 94})

    view = explain(sample)
    cpu = next(card for card in view["cards"] if card["id"] == "processeur")
    gpu = next(card for card in view["cards"] if card["id"] == "graphique")

    cpu_values = {row["label"]: (row["value"], row["hint"]) for row in cpu["figures"]}
    assert cpu_values["Température"] == ("72 °C", "chaud, mais ça va")
    assert cpu_values["Vitesse"] == ("4,5 GHz", "plus c'est haut, plus il va vite")
    hotspot = next(row for row in gpu["figures"] if row["label"] == "Point le plus chaud")
    assert hotspot == {
        "label": "Point le plus chaud", "value": "94 °C", "hint": "chaud, mais ça va"
    }


def test_processeur_tres_chaud_declenche_une_alerte():
    sample = status()
    sample["temps"]["cpu"] = 86

    view = explain(sample)

    assert view["verdict"]["mood"] == "warn"
    assert view["verdict"]["title"] == "Ton processeur chauffe beaucoup"
    assert "ventilateurs" in view["verdict"]["text"]
    assert "dépoussière" in view["verdict"]["text"]


def test_point_chaud_du_gpu_declenche_une_alerte():
    sample = status()
    sample["temps"]["gpu_hotspot"] = 106

    view = explain(sample)

    assert view["verdict"]["mood"] == "warn"
    assert view["verdict"]["title"] == "Ta carte graphique chauffe beaucoup"
    assert "ventilateurs" in view["verdict"]["text"]


def test_tip_propose_le_lecteur_de_temperatures():
    sample = status()
    sample["temps"] = {
        "cpu": None,
        "gpu": 41,
        "reason": "température du processeur : il faut installer le lecteur de températures",
    }

    view = explain(sample)
    cpu = next(card for card in view["cards"] if card["id"] == "processeur")

    assert any(
        tip["icon"] == "🌡️" and "installe le lecteur de températures" in tip["text"]
        for tip in view["tips"]
    )
    assert all(figure["label"] != "Température" for figure in cpu["figures"])
