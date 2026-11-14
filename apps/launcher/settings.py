"""Fenêtre de réglages indépendante pour Sakura Launcher.

Lancer avec : pythonw settings.py
"""

from __future__ import annotations

import copy
import datetime
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # racine du dépôt, pour core/
from core import paths  # noqa: E402
from core import window as sk_window  # noqa: E402

import launcher


ROOT = Path(__file__).resolve().parent
CONFIG = paths.CONFIG
UI = ROOT / "ui"

MANAGED_SETTINGS = ("day_start", "day_end", "backgrounds", "boot_block", "pause_if_playing")
MANAGED_ROOTS = ("games", "apps", "classic", "music")


def _defaults() -> dict[str, Any]:
    return {
        "settings": {
            "day_start": 8,
            "day_end": 18,
            "backgrounds": {
                "day": {"main": "day-main", "side": "day-side"},
                "night": {"main": "night-main", "side": "night-side"},
            },
            "boot_block": [],
            "pause_if_playing": [],
        },
        "games": [],
        "apps": [],
        "classic": [],
        "music": {},
    }


def _load_config(config_path: Path = CONFIG) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((ROOT / "config.example.json").read_text(encoding="utf-8"), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def read_managed(config_path: Path = CONFIG) -> dict[str, Any]:
    """Lit uniquement ce que l'éditeur sait modifier."""
    cfg = _load_config(config_path)
    result = _defaults()
    settings = cfg.get("settings", {})
    for key in MANAGED_SETTINGS:
        if key in settings:
            result["settings"][key] = copy.deepcopy(settings[key])
    for key in MANAGED_ROOTS:
        if key in cfg:
            result[key] = copy.deepcopy(cfg[key])
    return result


def _clean_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("settings"), dict):
        raise ValueError("Réglages incomplets.")
    s = payload["settings"]
    try:
        start, end = int(s.get("day_start", -1)), int(s.get("day_end", -1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Les heures doivent être comprises entre 0 et 23.") from exc
    if not (0 <= start <= 23 and 0 <= end <= 23):
        raise ValueError("Les heures doivent être comprises entre 0 et 23.")

    backgrounds = s.get("backgrounds")
    if not isinstance(backgrounds, dict):
        raise ValueError("Les fonds d'écran sont incomplets.")
    clean_bg: dict[str, dict[str, str]] = {}
    for theme in ("day", "night"):
        group = backgrounds.get(theme)
        if not isinstance(group, dict):
            raise ValueError("Les fonds d'écran sont incomplets.")
        clean_bg[theme] = {}
        for screen in ("main", "side"):
            value = group.get(screen)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Un nom de fond d'écran manque.")
            clean_bg[theme][screen] = value.strip()

    def names(key: str) -> list[str]:
        value = s.get(key, [])
        if not isinstance(value, list):
            raise ValueError("Une liste de programmes est invalide.")
        return [str(item).strip() for item in value if str(item).strip()]

    seen_ids: set[str] = set()

    def entries(key: str) -> list[dict[str, Any]]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"La liste {key} est invalide.")
        output: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict) or not str(item.get("id", "")).strip():
                raise ValueError(f"Une entrée de {key} est invalide.")
            entry = copy.deepcopy(item)
            entry["id"] = str(entry["id"]).strip()
            entry["name"] = str(entry.get("name", entry["id"])).strip() or entry["id"]
            if entry["id"] in seen_ids:
                raise ValueError(f"L'identifiant {entry['id']} est utilisé deux fois.")
            seen_ids.add(entry["id"])
            output.append(entry)
        return output

    music = payload.get("music")
    if not isinstance(music, dict):
        raise ValueError("Le programme de musique est invalide.")

    return {
        "settings": {
            "day_start": start,
            "day_end": end,
            "backgrounds": clean_bg,
            "boot_block": names("boot_block"),
            "pause_if_playing": names("pause_if_playing"),
        },
        "games": entries("games"),
        "apps": entries("apps"),
        "classic": entries("classic"),
        "music": copy.deepcopy(music),
    }


def _backup_config(config_path: Path) -> Path | None:
    """Copie la configuration existante et ne garde que les 20 secours récents."""
    path = Path(config_path)
    if not path.is_file():
        return None
    folder = paths.USER / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    moment = datetime.datetime.now()
    destination = folder / f"config-{moment:%Y%m%d-%H%M%S}.json"
    while destination.exists():
        moment += datetime.timedelta(seconds=1)
        destination = folder / f"config-{moment:%Y%m%d-%H%M%S}.json"
    shutil.copy2(path, destination)
    backups = sorted(folder.glob("config-????????-??????.json"), reverse=True)
    for old in backups[20:]:
        old.unlink()
    return destination


def save_managed(
    payload: Any,
    config_path: Path = CONFIG,
    data_writer: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Relit le disque et remplace exclusivement les clés gérées par cette appli."""
    clean = _clean_payload(payload)
    path = Path(config_path)
    _backup_config(path)
    cfg = _load_config(path)
    settings = cfg.setdefault("settings", {})
    for key in MANAGED_SETTINGS:
        settings[key] = copy.deepcopy(clean["settings"][key])
    for key in MANAGED_ROOTS:
        cfg[key] = copy.deepcopy(clean[key])
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_writer or launcher.write_data_js)(cfg)
    return cfg


class SettingsApi:
    def __init__(self) -> None:
        self._window = None
        self._maximized = False

    def load(self) -> dict[str, Any]:
        return read_managed()

    def save(self, payload: Any) -> dict[str, Any]:
        try:
            save_managed(payload)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> None:
        if self._maximized:
            sk_window.restore(self._window)
        else:
            sk_window.maximize(self._window)
        self._maximized = not self._maximized

    def close(self) -> None:
        self._window.destroy()

    def _dialog(self, file_types: tuple[str, ...]) -> Path | None:
        import webview

        result = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=file_types)
        if not result:
            return None
        selected = result[0] if isinstance(result, (list, tuple)) else result
        return Path(selected)

    @staticmethod
    def _unique_name(folder: Path, stem: str, suffix: str) -> str:
        taken = {path.stem for path in folder.iterdir()} if folder.exists() else set()
        clean = launcher.slug(stem, taken)
        while (folder / f"{clean}{suffix}").exists():
            taken.add(clean)
            clean = launcher.slug(stem, taken)
        return clean

    def choose_image(self, kind: str) -> dict[str, Any] | None:
        source = self._dialog(("Images (*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.gif)", "Tous les fichiers (*.*)"))
        if not source:
            return None
        if source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
            return {"error": "Choisissez un fichier image (JPG, PNG, WebP, BMP ou GIF)."}
        if kind == "background":
            folder, suffix = UI / "assets" / "bg", ".jpg"
        elif kind == "cover":
            folder, suffix = paths.USER / "covers", source.suffix.lower()
        else:
            folder, suffix = paths.USER / "icons", source.suffix.lower()
        folder.mkdir(parents=True, exist_ok=True)
        stem = self._unique_name(folder, source.stem, suffix)
        destination = folder / f"{stem}{suffix}"
        shutil.copyfile(source, destination)
        if kind == "background":
            return {"value": stem, "preview": f"assets/bg/{stem}.jpg"}
        relative = f"assets/{folder.name}/{destination.name}"
        return {"value": relative, "preview": relative}

    def choose_program(self, kind: str, taken: list[str]) -> dict[str, Any] | None:
        source = self._dialog(("Programmes (*.exe)", "Tous les fichiers (*.*)"))
        if not source:
            return None
        if source.suffix.lower() != ".exe":
            return {"error": "Choisissez un programme Windows au format .exe."}
        name = source.stem
        return {
            "id": launcher.slug(name, set(map(str, taken))),
            "name": name,
            "launch": {"exe": str(source)},
            "process": source.name,
        }

    def make_link(self, name: str, address: str, taken: list[str]) -> dict[str, Any]:
        name, address = name.strip(), address.strip()
        if not name or not address:
            return {"error": "Indiquez un nom et une adresse."}
        key = "url" if address.lower().startswith(("http://", "https://")) else "uri"
        return {
            "id": launcher.slug(name, set(map(str, taken))),
            "name": name,
            "launch": {key: address},
        }


def main() -> None:
    import webview

    api = SettingsApi()
    port = launcher.serve(ROOT)
    window = webview.create_window(
        "Sakura Launcher — Réglages",
        f"http://127.0.0.1:{port}/ui/settings.html",
        js_api=api,
        width=1200,
        height=850,
        min_size=(900, 650),
        background_color="#0d0a16",
        frameless=True,
        easy_drag=False,
    )
    api._window = window
    webview.start(gui="edgechromium", private_mode=False, storage_path=str(ROOT / ".webview"))


if __name__ == "__main__":
    main()
