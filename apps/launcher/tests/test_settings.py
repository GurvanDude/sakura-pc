import json
import os
from pathlib import Path

import pytest


def write_config(path: Path, settings_module):
    config = settings_module._defaults()
    config["settings"]["welcome_name"] = "Sakura"
    config["unmanaged"] = {"keep": True}
    config["games"] = [{"id": "game", "name": "Jeu", "launch": {"uri": "steam://game"}}]
    path.write_text(json.dumps(config), encoding="utf-8")
    return config


def test_read_and_save_only_managed_keys(launcher_modules, tmp_path):
    settings, _, _ = launcher_modules
    config_path = tmp_path / "config.json"
    original = write_config(config_path, settings)

    managed = settings.read_managed(config_path)
    assert "welcome_name" not in managed["settings"]
    assert "unmanaged" not in managed

    managed["settings"]["day_start"] = 9
    managed["games"][0]["name"] = "Nouveau nom"
    saved = settings.save_managed(managed, config_path, data_writer=lambda _: None)

    assert saved["settings"]["day_start"] == 9
    assert saved["settings"]["welcome_name"] == "Sakura"
    assert saved["unmanaged"] == original["unmanaged"]


def test_backup_is_created_before_write(launcher_modules, tmp_path):
    settings, _, _ = launcher_modules
    config_path = tmp_path / "config.json"
    original = write_config(config_path, settings)
    managed = settings.read_managed(config_path)
    managed["settings"]["day_start"] = 11

    settings.save_managed(managed, config_path, data_writer=lambda _: None)

    backups = list((tmp_path / "backups").glob("config-????????-??????.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original
    assert json.loads(config_path.read_text(encoding="utf-8"))["settings"]["day_start"] == 11


def test_first_save_without_existing_config_does_not_fail(launcher_modules, tmp_path):
    settings, _, _ = launcher_modules
    config_path = tmp_path / "config.json"
    settings.save_managed(settings._defaults(), config_path, data_writer=lambda _: None)
    assert config_path.is_file()
    assert not (tmp_path / "backups").exists()


def test_backups_are_limited_to_twenty(launcher_modules, tmp_path):
    settings, _, _ = launcher_modules
    config_path = tmp_path / "config.json"
    write_config(config_path, settings)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(21):
        backup = backup_dir / f"config-20260101-{index:06d}.json"
        backup.write_text("{}", encoding="utf-8")
        os.utime(backup, (index + 1, index + 1))

    settings.save_managed(settings.read_managed(config_path), config_path, data_writer=lambda _: None)

    assert len(list(backup_dir.glob("config-????????-??????.json"))) == 20
    assert not (backup_dir / "config-20260101-000000.json").exists()


@pytest.mark.parametrize("value", [-1, 24, "demain", None])
def test_clean_payload_refuses_invalid_hours(launcher_modules, value):
    settings, _, _ = launcher_modules
    payload = settings._defaults()
    payload["settings"]["day_start"] = value
    with pytest.raises(ValueError, match="heures"):
        settings._clean_payload(payload)


def test_clean_payload_refuses_duplicate_ids(launcher_modules):
    settings, _, _ = launcher_modules
    payload = settings._defaults()
    payload["games"] = [{"id": "same", "name": "Jeu"}]
    payload["apps"] = [{"id": "same", "name": "Appli"}]
    with pytest.raises(ValueError, match="deux fois"):
        settings._clean_payload(payload)


@pytest.mark.parametrize(
    ("address", "expected"),
    [("https://example.test", "url"), ("HTTP://example.test", "url"), ("steam://open/main", "uri")],
)
def test_make_link_selects_url_or_uri(launcher_modules, address, expected):
    settings, _, _ = launcher_modules
    result = settings.SettingsApi().make_link("Mon lien", address, [])
    assert result["launch"] == {expected: address}
