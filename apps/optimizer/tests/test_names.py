"""Tests du regroupement des programmes."""

import sakura_opt.names as names


def test_group_apps_merges_windows_processes(monkeypatch):
    monkeypatch.setattr(names, "friendly_name", lambda _pid, name: f"Lisible {name}")
    status = {
        "ram": {"total_gb": 16},
        "top_cpu": [
            {"pid": 4, "name": "System", "cpu_percent": 12, "ram_mb": 30},
            {"pid": 8, "name": "svchost.exe", "cpu_percent": 7, "ram_mb": 80},
        ],
        "top_ram": [
            {"pid": 8, "name": "svchost.exe", "cpu_percent": 7, "ram_mb": 80},
            {"pid": 9, "name": "dwm.exe", "cpu_percent": 2, "ram_mb": 300},
        ],
    }
    grouped = names.group_apps(status)
    windows = next(app for app in grouped if app["name"] == "Windows")
    assert windows["cpu_percent"] == 21
    assert windows["ram_percent"] == 2.5
    assert windows["ram_gb"] == 0.4
    assert windows["cpu_text"] == "21 % du processeur"
    assert windows["ram_text"] == "0,4 Go de mémoire"
    assert len(grouped) == 1


def test_group_apps_marks_busiest_non_windows():
    grouped = names.group_apps({
        "ram": {"total_gb": 16},
        "top_cpu": [
            {"pid": 1, "name": "jeu.exe", "cpu_percent": 17, "ram_mb": 3072},
            {"pid": 2, "name": "chat.exe", "cpu_percent": 4, "ram_mb": 512},
        ],
    }, name_reader=lambda _pid, name: name.removesuffix(".exe"))
    game = next(app for app in grouped if app["name"] == "jeu")
    assert game["cpu_text"] == "17 % du processeur"
    assert game["ram_text"] == "3,0 Go de mémoire"
    assert game["what"] == "c'est lui qui travaille le plus"
