"""Tests du ménage : uniquement des fichiers temporaires fabriqués par le test."""

import os
import shutil
import time
from pathlib import Path

import pytest

from sakura_opt.actions import ActionManager, choose_quarantine_root
from sakura_opt.cleanup import Cleanup, DAY


def make_services(tmp_path, *, clock=None, processes=(), recycle=(0, 0), empty=None):
    user = tmp_path / "user"
    manager = ActionManager(
        tmp_path / "quarantaine", user_root=user,
        journal_path=user / "optimizer-actions.jsonl",
        now=(lambda: clock[0]) if clock is not None else None,
    )
    environment = {
        "TEMP": str(tmp_path / "temp"),
        "LOCALAPPDATA": str(tmp_path / "local"),
    }
    cleanup = Cleanup(
        manager, environ=environment,
        now=(lambda: clock[0]) if clock is not None else time.time,
        process_names=lambda: processes,
        recycle_query=lambda: recycle,
        recycle_empty=empty or (lambda: None),
    )
    return manager, cleanup, environment


def old_file(path: Path, content=b"ancien", *, now=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    timestamp = (time.time() if now is None else now) - DAY - 1
    os.utime(path, (timestamp, timestamp))
    return path


def test_quarantaine_choisit_le_disque_fixe_hors_c_le_plus_libre(tmp_path):
    free = {"C:": 999, "D:": 200, "E:": 500}

    class Usage:
        def __init__(self, value):
            self.free = value

    root = choose_quarantine_root(
        user_root=tmp_path / "user",
        drives=[Path("C:\\"), Path("D:\\"), Path("E:\\")],
        disk_usage=lambda drive: Usage(free[drive.drive]),
    )

    assert root == Path("E:\\") / "SakuraPC" / "quarantaine"


def test_scan_n_ecrit_rien_et_garde_les_temp_recents(tmp_path):
    manager, cleanup, environment = make_services(tmp_path)
    old_file(Path(environment["TEMP"]) / "ancien.tmp")
    recent = Path(environment["TEMP"]) / "recent.tmp"
    recent.write_text("récent", encoding="utf-8")

    result = cleanup.scan()

    temp = next(row for row in result["categories"] if row["id"] == "temp")
    assert temp["nombre"] == 1
    assert recent.exists()
    assert not manager.journal_path.exists()
    assert not manager.quarantine_root.exists()


def test_apply_deplace_journalise_puis_annule_avec_suffixe(tmp_path):
    manager, cleanup, environment = make_services(tmp_path)
    original = old_file(Path(environment["TEMP"]) / "dossier" / "trace.log", b"123456")

    result = cleanup.apply(["temp"])

    assert result["place_gagnee"] == 6
    assert not original.exists()
    action = manager.list_actions()[0]
    quarantined = Path(action["elements"][0]["quarantaine"])
    assert quarantined.exists()
    assert action["etat"] == "fait"

    original.write_text("nouveau", encoding="utf-8")
    undone = manager.undo(action["id"])
    assert undone["ok"] is True
    assert original.read_text(encoding="utf-8") == "nouveau"
    assert original.with_name("trace (restauré).log").read_bytes() == b"123456"
    assert manager.list_actions()[0]["etat"] == "annulé"


def test_purge_apres_sept_jours(tmp_path):
    clock = [1_000_000.0]
    manager, cleanup, environment = make_services(tmp_path, clock=clock)
    original = old_file(Path(environment["TEMP"]) / "ancien.tmp", now=clock[0])
    cleanup.apply(["temp"])
    action = manager.list_actions()[0]
    assert not original.exists()

    clock[0] += 7 * DAY + 1
    result = manager.purge()

    assert result["actions_purgees"] == 1
    assert manager.list_actions()[0]["etat"] == "purgé"
    assert not (manager.quarantine_root / action["id"]).exists()


def test_lien_symbolique_est_ignore(tmp_path):
    _manager, cleanup, environment = make_services(tmp_path)
    outside = old_file(tmp_path / "outside" / "secret.tmp")
    temp = Path(environment["TEMP"])
    temp.mkdir(parents=True)
    link = temp / "lien"
    try:
        link.symlink_to(outside.parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Création de lien interdite sans droits sur ce Windows : {exc}")

    result = cleanup.scan()

    category = next(row for row in result["categories"] if row["id"] == "temp")
    assert category["nombre"] == 0
    assert outside.exists()


def test_chemin_hors_racine_est_refuse(tmp_path):
    manager, _cleanup, _environment = make_services(tmp_path)
    root = tmp_path / "autorise"
    root.mkdir()
    outside = old_file(tmp_path / "interdit" / "secret.tmp")

    action = manager.quarantine(
        [(outside, root, "temp")], action_type="nettoyage", summary="Test de sécurité"
    )

    assert action["refuses"] == 1
    assert action["elements"] == []
    assert outside.exists()


def test_fichier_verrouille_est_saute_et_compte(tmp_path, monkeypatch):
    manager, cleanup, environment = make_services(tmp_path)
    locked = old_file(Path(environment["TEMP"]) / "verrouille.tmp")
    real_move = shutil.move

    def refused(source, destination):
        if Path(source) == locked:
            raise PermissionError("fichier utilisé")
        return real_move(source, destination)

    monkeypatch.setattr("sakura_opt.actions.shutil.move", refused)
    result = cleanup.apply(["temp"])

    assert result["ignores"] == 1
    assert locked.exists()


def test_corbeille_est_injectable_et_journalisee_comme_definitive(tmp_path):
    emptied = []
    manager, cleanup, _environment = make_services(
        tmp_path, recycle=(456, 3), empty=lambda: emptied.append(True)
    )

    result = cleanup.apply(["corbeille"])

    assert emptied == [True]
    assert result["place_gagnee"] == 456
    action = manager.list_actions()[0]
    assert action["type"] == "définitif"
    assert action["annulable"] is False


def test_navigateur_desactive_si_opera_tourne(tmp_path):
    _manager, cleanup, environment = make_services(tmp_path, processes=["Opera.exe"])
    old_file(Path(environment["LOCALAPPDATA"]) / "Opera Software" / "Opera GX Stable" / "Cache" / "cache.bin")

    result = cleanup.scan()

    browser = next(row for row in result["categories"] if row["id"] == "navigateur")
    assert browser["desactivee"] is True
    assert browser["raison"] == "Ferme Opera GX pour la vider"
    assert browser["taille"] == 0
