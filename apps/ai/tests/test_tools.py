"""Tests des outils sans effet sur le vrai PC."""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import sakura_ai.tools as tools_module
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


def diagnostic_result(payload, returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, json.dumps(payload), stderr)


def test_diagnose_schema_est_sur_et_decrit_les_minutes():
    registry = ToolRegistry()
    tool = registry.get("diagnose")

    assert tool is not None
    assert tool.risky is False
    assert tool.parameters["properties"]["minutes"] == {
        "type": "integer",
        "enum": [2, 5, 15],
        "default": 5,
    }
    assert registry.describe("diagnose", {"minutes": 5}) == "🩺 Diagnostic des 5 dernières minutes"


def test_diagnose_ramene_les_minutes_aux_valeurs_permises():
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        return diagnostic_result({})

    registry = ToolRegistry(diagnose_runner=runner)
    for value in (0, 4, 12, 99, "invalide"):
        registry.run("diagnose", {"minutes": value})

    assert [command[-3] for command in commands] == ["--minutes"] * 5
    assert [command[-2] for command in commands] == ["2", "5", "15", "15", "5"]


def test_diagnose_construit_la_commande_et_compacte_le_json():
    captured = {}
    payload = {
        "minutes": 5,
        "app": "Mon jeu",
        "bottleneck": "gpu",
        "verdict": {"mood": "warn", "title": "Le GPU est chargé", "text": "Le jeu demande beaucoup."},
        "enough_data": True,
        "findings": [
            {
                "id": f"finding-{index}",
                "severity": "attention",
                "title": f"Constat {index}",
                "explanation": f"Explication {index}",
                "evidence": [
                    {"label": "Charge", "value": f"{index} %"},
                    {"label": "Ignorée", "value": "trop longue"},
                ],
                "advice": ["Conseil 1", "Conseil 2", "Conseil 3", "Conseil ignoré"],
                "extra": "ignoré",
            }
            for index in range(5)
        ],
        "extra": "ignoré",
    }

    def runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return diagnostic_result(payload)

    result = ToolRegistry(diagnose_runner=runner).run("diagnose", {"minutes": 5})

    optimizer = tools_module.REPO / "apps" / "optimizer" / "optimizer.py"
    assert captured["command"] == [sys.executable, str(optimizer), "diagnose", "--minutes", "5", "--json"]
    assert captured["kwargs"]["cwd"] == optimizer.parent
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["env"]["PYTHONIOENCODING"] == "utf-8"
    expected_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    assert captured["kwargs"]["creationflags"] == expected_flags
    assert captured["kwargs"]["timeout"] == 90
    assert result == {
        "ok": True,
        "minutes": 5,
        "verdict_title": "Le GPU est chargé",
        "verdict_text": "Le jeu demande beaucoup.",
        "mood": "warn",
        "bottleneck": "gpu",
        "app": "Mon jeu",
        "enough_data": True,
        "findings": [
            {
                "title": f"Constat {index}",
                "explanation": f"Explication {index}",
                "advice": ["Conseil 1", "Conseil 2", "Conseil 3"],
                "evidence": f"Charge : {index} %",
            }
            for index in range(4)
        ],
    }


def test_diagnose_accepte_un_json_partiel():
    result = ToolRegistry(diagnose_runner=lambda *_args, **_kwargs: diagnostic_result({"verdict": None})).run(
        "diagnose", {}
    )

    assert result["ok"] is True
    assert result["minutes"] == 5
    assert result["verdict_title"] == ""
    assert result["findings"] == []


def test_diagnose_gere_un_code_de_sortie_non_nul():
    result = ToolRegistry(
        diagnose_runner=lambda *_args, **_kwargs: diagnostic_result({}, returncode=2, stderr="détail technique")
    ).run("diagnose", {})

    assert result == {"ok": False, "message": "Sakura Optimizer n'a pas pu faire le diagnostic."}
    assert "détail technique" not in result["message"]


def test_diagnose_journalise_un_stderr_tronque():
    calls = []

    class Logger:
        def info(self, *args):
            calls.append(args)

        def error(self, *args):
            calls.append(args)

    ToolRegistry(
        diagnose_runner=lambda *_args, **_kwargs: diagnostic_result({}, returncode=1, stderr="x" * 1500),
        logger=Logger(),
    ).run("diagnose", {})

    diagnostic_call = next(call for call in calls if call[0].startswith("Diagnostic Optimizer"))
    assert diagnostic_call[-1] == "x" * 1000


def test_diagnose_gere_un_json_illisible():
    completed = subprocess.CompletedProcess([], 0, "pas du json", "trace technique")
    result = ToolRegistry(diagnose_runner=lambda *_args, **_kwargs: completed).run("diagnose", {})

    assert result == {"ok": False, "message": "La réponse de Sakura Optimizer est illisible."}


def test_diagnose_gere_le_delai_depasse():
    def runner(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("optimizer", 90, stderr="trace technique")

    result = ToolRegistry(diagnose_runner=runner).run("diagnose", {})

    assert result == {"ok": False, "message": "Le diagnostic a pris trop de temps. Réessaie dans un instant."}


def test_diagnose_gere_optimizer_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(tools_module, "REPO", tmp_path)
    result = ToolRegistry(
        diagnose_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("aucun lancement attendu"))
    ).run("diagnose", {})

    assert result == {"ok": False, "message": "Sakura Optimizer est introuvable."}


def test_ai_nimporte_jamais_le_code_optimizer():
    ai_root = Path(__file__).resolve().parents[1]
    forbidden = []
    for source in ai_root.rglob("*.py"):
        if "vendor" in source.relative_to(ai_root).parts:
            continue  # paquets tiers installés pour la voix
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name == "sakura_opt" or name.startswith("sakura_opt.") for name in names):
                forbidden.append(str(source))
    assert forbidden == []
