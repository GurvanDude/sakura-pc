"""Tests des outils sans effet sur le vrai PC."""

import os
import time

from sakura_ai.tools import ToolRegistry


def fake_config():
    return {
        "settings": {"browser": "browser.exe"},
        "apps": [
            {"name": "Minecraft (moddé)", "launch": {"exe": "minecraft.exe"}, "process": "minecraft.exe"},
            {"name": "Discord", "launch": {"exe": "discord.exe"}, "process": "discord.exe"},
            {"name": "Visual Studio Code", "launch": {"exe": "code.exe"}},
            {"name": "Visual Studio", "launch": {"exe": "devenv.exe"}},
        ],
        "games": [
            {"name": "Hollow Knight: Silksong", "launch": {"uri": "steam://silksong"}},
        ],
    }


def test_correspondance_de_noms_et_lancement_injecte():
    launched = []
    registry = ToolRegistry(config_loader=fake_config, launcher_start=lambda launch, browser: launched.append((launch, browser)))

    assert registry.run("open_app", {"name": "silksong"})["name"] == "Hollow Knight: Silksong"
    assert registry.run("open_app", {"name": "minecraft"})["name"] == "Minecraft (moddé)"
    assert len(launched) == 2
    assert launched[0][1] == "browser.exe"


def test_correspondance_ambigue_et_introuvable_ne_lance_rien():
    launched = []
    registry = ToolRegistry(config_loader=fake_config, launcher_start=lambda *args: launched.append(args))

    ambiguous = registry.run("open_app", {"name": "visual"})
    missing = registry.run("open_app", {"name": "calculatrice quantique"})

    assert ambiguous == {
        "ok": False,
        "message": "Plusieurs applications correspondent.",
        "choices": ["Visual Studio Code", "Visual Studio"],
    }
    assert missing["ok"] is False
    assert missing["suggestions"]
    assert launched == []


def test_find_files_ignore_les_dossiers_caches_et_trie(tmp_path):
    documents = tmp_path / "Documents"
    documents.mkdir()
    old = documents / "Projet Sakura ancien.txt"
    new = documents / "notes-projet-sákura.md"
    old.write_text("ancien", encoding="utf-8")
    new.write_text("récent", encoding="utf-8")
    os.utime(old, (time.time() - 60, time.time() - 60))
    hidden = documents / ".cache"
    hidden.mkdir()
    (hidden / "projet sakura secret.txt").write_text("non", encoding="utf-8")
    modules = documents / "node_modules"
    modules.mkdir()
    (modules / "projet sakura paquet.txt").write_text("non", encoding="utf-8")
    registry = ToolRegistry(search_roots=lambda: [documents])

    result = registry.run("find_files", {"query": "projet sakura"})

    assert result["ok"] is True
    assert [item["path"] for item in result["files"]] == [str(new), str(old)]
    assert all("modified" in item for item in result["files"])


class FakeProcess:
    def __init__(self, pid, name):
        self.pid = pid
        self.info = {"pid": pid, "name": name}
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def test_close_app_ne_touche_jamais_a_la_liste_noire():
    processes = [
        FakeProcess(100, "explorer.exe"),
        FakeProcess(101, "pythonw.exe"),
        FakeProcess(102, "ollama.exe"),
        FakeProcess(4, "System"),
    ]
    registry = ToolRegistry(
        config_loader=lambda: {"apps": [], "games": []},
        process_iter=lambda _attrs: processes,
        wait_procs=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("aucune attente attendue")),
    )

    for name in ("explorer", "python", "ollama", "system"):
        assert registry.run("close_app", {"name": name})["ok"] is False
    assert not any(process.terminated or process.killed for process in processes)

