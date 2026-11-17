"""Tests du démarrage : Registre et dossiers entièrement factices."""

from pathlib import Path

import pytest

from sakura_opt.actions import ActionManager
from sakura_opt.startup import RUN, RUN_WOW, STORE, Startup, recommendation


class FakeBackend:
    def __init__(self):
        self.registry = {}
        self.store = []
        self.commands = {}

    def registry_values(self, hive, key):
        return [(name, value, kind) for (item_hive, item_key, name), (value, kind)
                in self.registry.items() if (item_hive, item_key) == (hive, key)]

    def registry_get(self, hive, key, name):
        return self.registry.get((hive, key, name))

    def registry_set(self, hive, key, name, value, kind):
        self.registry[(hive, key, name)] = (value, kind)
        prefix = STORE + "\\"
        if hive == "CURRENT_USER" and key.startswith(prefix) and name == "State":
            package, task = key[len(prefix):].split("\\", 1)
            self.store = [(p, t, value if (p, t) == (package, task) else state)
                          for p, t, state in self.store]

    def registry_delete(self, hive, key, name):
        del self.registry[(hive, key, name)]

    def store_tasks(self):
        return list(self.store)

    def shortcut_command(self, shortcut):
        return self.commands.get(Path(shortcut).name, str(shortcut))


@pytest.fixture
def startup_services(tmp_path):
    clock = [1_000_000.0]
    user = tmp_path / "user"
    manager = ActionManager(
        tmp_path / "quarantaine", user_root=user,
        journal_path=user / "optimizer-actions.jsonl", now=lambda: clock[0],
    )
    backend = FakeBackend()
    user_startup = tmp_path / "startup"
    common_startup = tmp_path / "common-startup"
    user_startup.mkdir()
    common_startup.mkdir()
    startup = Startup(
        manager, backend=backend, user_startup=user_startup,
        common_startup=common_startup, disabled_dir=user / "demarrage_coupe",
    )
    return startup, manager, backend, clock, user_startup, common_startup


def test_liste_les_quatre_sources_et_garde_hklm_en_lecture_seule(startup_services):
    startup, _manager, backend, _clock, user_folder, common_folder = startup_services
    backend.registry[("CURRENT_USER", RUN, "Steam")] = (r'"C:\Steam\steam.exe" -silent', 2)
    backend.registry[("LOCAL_MACHINE", RUN, "Pilote")] = (r'C:\Driver\driver.exe', 1)
    backend.registry[("LOCAL_MACHINE", RUN_WOW, "Ancien pilote")] = (r'C:\Old\old.exe', 1)
    backend.store = [("MSTeams_package", "TeamsTask", 2)]
    (user_folder / "Discord.lnk").write_text("raccourci", encoding="utf-8")
    (common_folder / "Commun.lnk").write_text("raccourci", encoding="utf-8")
    backend.commands["Discord.lnk"] = r'C:\Discord\Discord.exe'

    entries = startup.list_entries()

    assert {entry["type"] for entry in entries} == {"run", "shortcut", "store"}
    assert {entry["source"] for entry in entries} >= {
        "Registre de ton compte", "Dossier Démarrage de ton compte", "Application du Store",
        "Registre de tous les comptes", "Dossier Démarrage de tous les comptes",
    }
    readonly = [entry for entry in entries if "tous les comptes" in entry["source"]]
    assert readonly and all(not entry["modifiable"] for entry in readonly)
    assert all(entry["raison"] ==
               "Réglé pour tous les comptes : il faut les droits administrateur."
               for entry in readonly)


@pytest.mark.parametrize("name,command,reason", [
    ("Sakura Lights", "lights.py", "Fait partie de Sakura PC"),
    ("Sécurité", "SecurityHealthSystray.exe", "Sécurité de Windows"),
])
def test_sakura_et_securite_sont_proteges(startup_services, name, command, reason):
    startup, _manager, backend, _clock, _user, _common = startup_services
    backend.registry[("CURRENT_USER", RUN, name)] = (command, 1)

    entry = startup.list_entries()[0]

    assert entry["modifiable"] is False
    assert entry["raison"] == reason


@pytest.mark.parametrize("name,level,text", [
    ("Steam", "inutile", None),
    ("LGHUB", "utile", None),
    ("Ollama", "utile", "Sakura AI s'en sert pour réfléchir."),
    ("Programme mystère", "neutre", None),
])
def test_recommandations(name, level, text):
    result = recommendation(name, "")
    assert result["niveau"] == level
    if text:
        assert result["texte"] == text


def test_coupe_puis_remet_run_avec_nom_valeur_et_type_identiques(startup_services):
    startup, manager, backend, _clock, _user, _common = startup_services
    original = (r'%LOCALAPPDATA%\App\app.exe --start', 2)
    backend.registry[("CURRENT_USER", RUN, "MonApp")] = original
    identifier = startup.list_entries()[0]["id"]

    cut = startup.disable(identifier)
    assert cut["ok"] is True
    assert backend.registry_get("CURRENT_USER", RUN, "MonApp") is None
    assert startup.list_entries()[0]["etat"] == "coupé"

    restored = startup.enable(identifier)
    assert restored["ok"] is True
    assert backend.registry_get("CURRENT_USER", RUN, "MonApp") == original
    assert manager.list_actions()[0]["etat"] == "annulé"


def test_remise_run_n_ecrase_pas_une_valeur_recreee(startup_services):
    startup, _manager, backend, _clock, _user, _common = startup_services
    backend.registry[("CURRENT_USER", RUN, "MonApp")] = ("ancienne", 1)
    identifier = startup.list_entries()[0]["id"]
    startup.disable(identifier)
    backend.registry[("CURRENT_USER", RUN, "MonApp")] = ("nouvelle", 2)

    result = startup.enable(identifier)

    assert result["ok"] is False
    assert "pas écrasée" in result["erreur"]
    assert backend.registry_get("CURRENT_USER", RUN, "MonApp") == ("nouvelle", 2)


def test_raccourci_est_deplace_hors_quarantaine_et_jamais_purge(startup_services):
    startup, manager, backend, clock, user_folder, _common = startup_services
    shortcut = user_folder / "Discord.lnk"
    shortcut.write_text("contenu", encoding="utf-8")
    backend.commands[shortcut.name] = r'C:\Discord\Discord.exe'
    identifier = startup.list_entries()[0]["id"]

    startup.disable(identifier)
    action = manager.list_actions()[0]
    disabled = Path(action["demarrage"]["disabled_path"])
    assert disabled.exists() and manager.quarantine_root not in disabled.parents

    clock[0] += 10 * 24 * 60 * 60
    assert manager.purge()["actions_purgees"] == 0
    assert disabled.exists() and manager.list_actions()[0]["annulable"] is True


def test_store_state_est_sauvegarde_puis_restaure(startup_services):
    startup, _manager, backend, _clock, _user, _common = startup_services
    backend.store = [("Package", "Task", 7)]
    identifier = startup.list_entries()[0]["id"]

    assert startup.disable(identifier)["ok"] is True
    assert backend.store == [("Package", "Task", 1)]
    assert startup.enable(identifier)["ok"] is True
    assert backend.store == [("Package", "Task", 7)]


def test_action_demarrage_reste_annulable_apres_dix_jours(startup_services):
    startup, manager, backend, clock, _user, _common = startup_services
    backend.registry[("CURRENT_USER", RUN, "App")] = ("app.exe", 1)
    identifier = startup.list_entries()[0]["id"]
    action = startup.disable(identifier)["action"]
    clock[0] += 10 * 24 * 60 * 60

    manager.purge()
    result = manager.undo(action["id"])

    assert result["ok"] is True
    assert backend.registry_get("CURRENT_USER", RUN, "App") == ("app.exe", 1)
