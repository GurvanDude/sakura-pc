"""Tests des doublons : uniquement des fichiers fabriqués sous tmp_path."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sakura_opt.actions import ActionManager
from sakura_opt.duplicates import Duplicates, OFFLINE_ATTRIBUTES


CONTENT = b"sakura" * 40_000  # image assez grande, test rapide


def services(tmp_path, *, attributes=lambda _path: 0, opener=None):
    folders = {
        "Documents": tmp_path / "Documents",
        "Téléchargements": tmp_path / "Downloads",
        "Images": tmp_path / "Pictures",
        "Vidéos": tmp_path / "Videos",
        "Musique": tmp_path / "Music",
        "Bureau": tmp_path / "Desktop",
    }
    for folder in folders.values():
        folder.mkdir(parents=True)
    manager = ActionManager(
        tmp_path / "quarantaine", user_root=tmp_path / "user",
        journal_path=tmp_path / "user" / "actions.jsonl",
    )
    duplicates = Duplicates(
        manager, folders=folders, attributes=attributes,
        config_path=tmp_path / "user" / "optimizer.json", folder_opener=opener,
    )
    return manager, duplicates, folders


def write(path: Path, content: bytes = CONTENT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_deux_fichiers_identiques_sont_trouves(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    write(folders["Documents"] / "photo.jpg")
    write(folders["Images"] / "copie.jpg")

    result = duplicates.scan()

    assert len(result["groups"]) == 1
    assert len(result["groups"][0]["copies"]) == 2
    assert result["gain_total"] == len(CONTENT)


def test_meme_taille_contenu_different_n_est_pas_un_doublon(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    write(folders["Documents"] / "a.jpg", b"a" * len(CONTENT))
    write(folders["Images"] / "b.jpg", b"b" * len(CONTENT))

    assert duplicates.scan()["groups"] == []


def test_extension_hors_liste_et_exe_en_profondeur_sont_ignores(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    write(folders["Documents"] / "a.bin")
    write(folders["Images"] / "b.bin")
    write(folders["Documents"] / "logiciel" / "setup.exe", b"x" * (1024 * 1024))
    write(folders["Téléchargements"] / "logiciel" / "setup.exe", b"x" * (1024 * 1024))

    assert duplicates.scan()["groups"] == []


@pytest.mark.parametrize("blocked", ["Image-Line", ".git"])
def test_dossier_protege_est_ignore(tmp_path, blocked):
    _manager, duplicates, folders = services(tmp_path)
    write(folders["Documents"] / blocked / "a.jpg")
    write(folders["Images"] / blocked / "b.jpg")

    assert duplicates.scan()["groups"] == []


def test_projet_godot_et_dossier_exclu_sont_ignores(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    project = folders["Documents"] / "jeu"
    write(project / "project.godot", b"[application]")
    write(project / "a.jpg", b"g" * len(CONTENT))
    write(folders["Images"] / "jeu" / "b.jpg", b"g" * len(CONTENT))
    excluded = folders["Documents"] / "privé"
    write(excluded / "c.jpg", b"p" * len(CONTENT))
    write(folders["Images"] / "c.jpg", b"p" * len(CONTENT))
    duplicates.config_path.parent.mkdir(parents=True)
    duplicates.config_path.write_text(
        json.dumps({"doublons_exclus": [str(excluded)]}), encoding="utf-8"
    )

    assert duplicates.scan()["groups"] == []


def test_fichier_en_ligne_seulement_n_est_jamais_ouvert(tmp_path):
    opened = []
    offline = tmp_path / "Documents" / "cloud.jpg"

    def attributes(path):
        return OFFLINE_ATTRIBUTES if path == offline else 0

    def opening(path, mode):
        opened.append(path)
        return open(path, mode)

    _manager, duplicates, folders = services(tmp_path, attributes=attributes)
    duplicates.file_opener = opening
    write(offline)
    write(folders["Images"] / "local.jpg")

    duplicates.scan()

    assert offline not in opened


def test_lien_est_ignore(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    target = write(tmp_path / "ailleurs" / "photo.jpg")
    link = folders["Documents"] / "lien.jpg"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Création de lien interdite sur ce Windows : {exc}")
    write(folders["Images"] / "copie.jpg")

    assert duplicates.scan()["groups"] == []


def test_copie_gardee_hors_telechargements_puis_la_plus_ancienne(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    download = write(folders["Téléchargements"] / "a.jpg")
    recent = write(folders["Documents"] / "recent.jpg")
    old = write(folders["Images"] / "old.jpg")
    os.utime(download, (10, 10))
    os.utime(recent, (30, 30))
    os.utime(old, (20, 20))

    group = duplicates.scan()["groups"][0]
    kept = next(copy for copy in group["copies"] if copy["garder"])

    assert kept["chemin"] == str(old)


def test_apply_refuse_toutes_les_copies(tmp_path):
    manager, duplicates, folders = services(tmp_path)
    first = write(folders["Documents"] / "a.jpg")
    second = write(folders["Images"] / "b.jpg")
    duplicates.scan()

    result = duplicates.apply([str(first), str(second)])

    assert result["ok"] is False
    assert first.exists() and second.exists()
    assert manager.list_actions() == []


def test_apply_saute_fichier_modifie_et_groupe_sans_copie_gardee(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    keep_a = write(folders["Documents"] / "keep-a.jpg")
    changed = write(folders["Images"] / "changed.jpg")
    keep_b = write(folders["Documents"] / "keep-b.png", b"z" * len(CONTENT))
    removable = write(folders["Images"] / "remove.png", b"z" * len(CONTENT))
    os.utime(keep_a, (10, 10))
    os.utime(changed, (20, 20))
    os.utime(keep_b, (10, 10))
    os.utime(removable, (20, 20))
    result = duplicates.scan()
    changed.write_bytes(b"q" * len(CONTENT))
    os.utime(changed, None)
    second_group = next(group for group in result["groups"] if str(removable) in {
        copy["chemin"] for copy in group["copies"]
    })
    keeper = next(copy for copy in second_group["copies"] if copy["garder"])
    Path(keeper["chemin"]).unlink()

    applied = duplicates.apply([str(changed), str(removable)])

    assert applied["ok"] is False
    assert applied["ignores"] == 2
    assert changed.exists() and removable.exists()


def test_annulation_remet_le_fichier(tmp_path):
    manager, duplicates, folders = services(tmp_path)
    write(folders["Documents"] / "a.jpg")
    second = write(folders["Images"] / "b.jpg")
    group = duplicates.scan()["groups"][0]
    selected = next(copy["chemin"] for copy in group["copies"] if not copy["garder"])

    applied = duplicates.apply([selected])
    undone = manager.undo(applied["action"]["id"])

    assert applied["ok"] is True
    assert undone["ok"] is True
    assert Path(selected).exists()
    assert second.exists() or Path(selected).exists()


def test_open_folder_refuse_un_chemin_hors_analyse(tmp_path):
    opened = []
    _manager, duplicates, _folders = services(tmp_path, opener=opened.append)

    result = duplicates.open_folder(str(tmp_path / "secret.txt"))

    assert result["ok"] is False
    assert opened == []


def test_doublons_dans_un_meme_projet_ou_une_banque_de_sons_ne_sont_pas_proposes(tmp_path):
    # cas réel : S.K.Y. Keys contient les mêmes sons dans deux sous-dossiers, ils sont voulus
    _manager, duplicates, folders = services(tmp_path)
    write(folders["Documents"] / "S.K.Y. Studios" / "Lost Youth" / "pad.wav")
    write(folders["Documents"] / "S.K.Y. Studios" / "Fountain Youth" / "pad.wav")

    assert duplicates.scan()["groups"] == []


def test_doublon_entre_deux_endroits_differents_est_propose(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    write(folders["Documents"] / "Vacances" / "plage.jpg")
    write(folders["Images"] / "Vacances" / "plage.jpg")

    assert len(duplicates.scan()["groups"]) == 1


def test_projet_python_avec_requirements_est_ignore(tmp_path):
    _manager, duplicates, folders = services(tmp_path)
    write(folders["Images"] / "Screenshots" / "capture.png")
    write(folders["Documents"] / "bot" / "requirements.txt", b"rich")
    write(folders["Documents"] / "bot" / "tests" / "fixtures" / "capture.png")

    assert duplicates.scan()["groups"] == []
