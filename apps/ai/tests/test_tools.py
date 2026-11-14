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


def test_open_app_connait_les_alias_du_bloc_notes():
    launched = []
    registry = ToolRegistry(
        config_loader=lambda: {"apps": [], "games": []},
        start_menu_roots=lambda: [],
        launcher_start=lambda launch, browser: launched.append((launch, browser)),
    )

    for name in ("bloc-notes", "bloc note", "Notepad"):
        result = registry.run("open_app", {"name": name})
        assert result["ok"] is True
        assert result["name"] == "Bloc-notes"

    assert launched == [({"exe": "notepad.exe"}, None)] * 3


def test_open_app_trouve_un_raccourci_du_menu_demarrer(tmp_path):
    shortcut = tmp_path / "Outils" / "Mon Application.lnk"
    shortcut.parent.mkdir()
    shortcut.write_bytes(b"faux raccourci")
    launched = []
    registry = ToolRegistry(
        config_loader=lambda: {"apps": [], "games": []},
        start_menu_roots=lambda: [tmp_path],
        launcher_start=lambda launch, browser: launched.append((launch, browser)),
    )

    result = registry.run("open_app", {"name": "mon application"})

    assert result["ok"] is True
    assert launched == [({"file": str(shortcut)}, None)]


def test_menu_demarrer_ignore_les_raccourcis_de_desinstallation(tmp_path):
    (tmp_path / "Désinstaller X.lnk").write_bytes(b"faux raccourci")
    registry = ToolRegistry(
        config_loader=lambda: {"apps": [], "games": []},
        start_menu_roots=lambda: [tmp_path],
        launcher_start=lambda *_args: (_ for _ in ()).throw(AssertionError("aucun lancement attendu")),
    )

    result = registry.run("open_app", {"name": "Désinstaller X"})

    assert result["ok"] is False


def test_launcher_est_prioritaire_sur_un_raccourci_du_meme_nom(tmp_path):
    shortcut = tmp_path / "Discord.lnk"
    shortcut.write_bytes(b"faux raccourci")
    launched = []
    registry = ToolRegistry(
        config_loader=fake_config,
        start_menu_roots=lambda: [tmp_path],
        launcher_start=lambda launch, browser: launched.append((launch, browser)),
    )

    registry.run("open_app", {"name": "Discord"})

    assert launched == [({"exe": "discord.exe"}, "browser.exe")]


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


def test_close_app_bloc_notes_vise_notepad():
    notepad = FakeProcess(100, "notepad.exe")
    registry = ToolRegistry(
        config_loader=lambda: {"apps": [], "games": []},
        start_menu_roots=lambda: [],
        process_iter=lambda _attrs: [notepad],
        wait_procs=lambda processes, timeout: (processes, []),
    )

    result = registry.run("close_app", {"name": "bloc-notes"})

    assert result["ok"] is True
    assert notepad.terminated is True


def test_close_app_refuse_alias_explorateur():
    explorer = FakeProcess(100, "explorer.exe")
    registry = ToolRegistry(
        config_loader=lambda: {"apps": [], "games": []},
        start_menu_roots=lambda: [],
        process_iter=lambda _attrs: [explorer],
        wait_procs=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("aucune attente attendue")),
    )

    result = registry.run("close_app", {"name": "explorateur"})

    assert result["ok"] is False
    assert explorer.terminated is False



def test_un_seul_mot_commun_ne_suffit_pas(tmp_path):
    for name in ("Sakura Lumières", "Sakura Optimizer"):
        (tmp_path / f"{name}.lnk").write_bytes(b"faux raccourci")
    launched = []
    registry = ToolRegistry(
        config_loader=lambda: {"apps": [], "games": []},
        start_menu_roots=lambda: [tmp_path],
        launcher_start=lambda launch, browser: launched.append(launch),
    )

    assert registry.run("open_app", {"name": "sakura optimiseur"})["name"] == "Sakura Optimizer"
    assert registry.run("open_app", {"name": "sakura robot"})["ok"] is False
    assert launched == [{"file": str(tmp_path / "Sakura Optimizer.lnk")}]
