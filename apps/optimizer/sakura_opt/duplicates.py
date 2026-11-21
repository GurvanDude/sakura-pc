"""Recherche prudente de fichiers strictement identiques dans les dossiers personnels."""

from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from core import paths

from .actions import ActionManager, REPARSE_POINT, _is_reparse


MIB = 1024 * 1024
IMAGE_MINIMUM = 200 * 1024
PARTIAL_SIZE = 64 * 1024
OFFLINE_ATTRIBUTES = 0x1000 | 0x40000 | 0x400000

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "heic", "bmp", "tif", "tiff"}
REGULAR_EXTENSIONS = {
    "mp4", "mkv", "mov", "avi", "webm", "m4v",
    "mp3", "flac", "m4a", "ogg", "aac", "wav",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp",
    "txt", "rtf", "epub", "zip", "rar", "7z",
}
INSTALLER_EXTENSIONS = {"exe", "msi"}
BLOCKED_NAMES = {
    ".git", "node_modules", "__pycache__", "site-packages", "appdata", "$recycle.bin",
    "my games", "saved games", "image-line", "fl studio", "xfer", "native instruments",
    "spitfire", "splice", "ableton", "vital", "surge xt", "producersources",
    "echo sound works", "fabfilter", "samples", "plugins", "vst", "vst3",
}
# signes d'un projet de code ou d'un logiciel : on ne touche à rien dedans
PROJECT_MARKERS = {".git", ".sln", "package.json", "project.godot", "requirements.txt", "pyproject.toml",
                   "setup.py", "venv", ".venv", "cargo.toml", "cmakelists.txt", "go.mod", "pom.xml", "build.gradle",
                   "makefile", "unins000.exe"}
CODE_EXTENSIONS = (".py", ".js", ".ts", ".cs", ".cpp", ".gd", ".csproj", ".vcxproj", ".dll")
KEEPER_DEPRIORITIZED = {"téléchargements", "bureau"}

KNOWN_FOLDER_GUIDS = {
    "Documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "Téléchargements": "374DE290-123F-4565-9164-39C4925E467B",
    "Images": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "Vidéos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
    "Musique": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "Bureau": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
}


def known_folders() -> dict[str, Path]:
    """Lit les dossiers connus de Windows, y compris leurs redirections OneDrive."""
    if os.name != "nt":
        home = Path.home()
        return {
            "Documents": home / "Documents", "Téléchargements": home / "Downloads",
            "Images": home / "Pictures", "Vidéos": home / "Videos",
            "Musique": home / "Music", "Bureau": home / "Desktop",
        }

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8),
        ]

    shell = ctypes.windll.shell32
    ole = ctypes.windll.ole32
    result: dict[str, Path] = {}
    for label, raw_guid in KNOWN_FOLDER_GUIDS.items():
        value = uuid.UUID(raw_guid)
        data = value.bytes_le
        guid = GUID.from_buffer_copy(data)
        pointer = ctypes.c_wchar_p()
        try:
            status = shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(pointer))
            if status == 0 and pointer.value:
                result[label] = Path(pointer.value)
        finally:
            if pointer:
                ole.CoTaskMemFree(pointer)
    return result


def file_attributes(path: Path) -> int:
    """Lit les attributs sans ouvrir le contenu, pour ne pas rappeler un fichier OneDrive."""
    if os.name == "nt":
        getter = ctypes.windll.kernel32.GetFileAttributesW
        getter.restype = ctypes.c_ulong
        value = int(getter(str(path)))
        return 0 if value == 0xFFFFFFFF else value
    try:
        return int(getattr(path.lstat(), "st_file_attributes", 0))
    except OSError:
        return 0


def _same_or_below(path: Path, root: Path) -> bool:
    try:
        path.absolute().relative_to(root.absolute())
        return True
    except (OSError, ValueError):
        # Les chemins Windows ne sont pas sensibles à la casse.
        clean_path = os.path.normcase(str(path.absolute())).rstrip("\\/")
        clean_root = os.path.normcase(str(root.absolute())).rstrip("\\/")
        return clean_path == clean_root or clean_path.startswith(clean_root + os.sep)


def _date(timestamp: float) -> str:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()


class Duplicates:
    """Analyse et met en quarantaine sans toucher aux projets ni aux logiciels."""

    def __init__(
        self,
        actions: ActionManager | None = None,
        *,
        folders: Mapping[str, Path] | Iterable[Path] | None = None,
        attributes: Callable[[Path], int] = file_attributes,
        config_path: Path | None = None,
        folder_opener: Callable[[Path], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        file_opener: Callable[..., Any] = open,
    ) -> None:
        self.actions = actions or ActionManager()
        raw_folders = known_folders() if folders is None else folders
        if isinstance(raw_folders, Mapping):
            self.folders = {str(label): Path(folder) for label, folder in raw_folders.items()}
        else:
            self.folders = {Path(folder).name: Path(folder) for folder in raw_folders}
        self.attributes = attributes
        self.config_path = Path(config_path) if config_path is not None else paths.USER / "optimizer.json"
        self.folder_opener = folder_opener or self._open_in_explorer
        self.clock = clock
        self.file_opener = file_opener
        self.last_result: dict[str, Any] = self._empty_result()
        self._groups: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {
            "groups": [], "fichiers_regardes": 0, "duree_s": 0.0,
            "gain_total": 0, "fichiers_en_double": 0, "ignorés": 0, "annule": False,
        }

    def _preferences(self) -> dict[str, Any]:
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _excluded_roots(self) -> list[Path]:
        values = self._preferences().get("doublons_exclus", [])
        if not isinstance(values, list):
            return []
        return [Path(value) for value in values if isinstance(value, str) and value]

    def _blocked_path(self, path: Path, excluded: list[Path], root: Path | None = None) -> bool:
        # les noms interdits (AppData, .git…) ne comptent qu'À L'INTÉRIEUR du dossier regardé,
        # pas au-dessus (sinon un Documents placé sous AppData serait ignoré en entier)
        try:
            parts = path.relative_to(root).parts if root is not None else path.parts
        except ValueError:
            parts = path.parts
        if any(part.casefold() in BLOCKED_NAMES for part in parts):
            return True
        return any(_same_or_below(path, root) for root in excluded)

    @staticmethod
    def _has_project_marker(dirs: list[str], files: list[str]) -> bool:
        names = {name.casefold() for name in dirs + files}
        return (bool(names & PROJECT_MARKERS) or any(name.endswith(".sln") for name in names)
                or any(name.casefold().endswith(CODE_EXTENSIONS) for name in files))

    def _candidate(self, path: Path, root: Path, label: str) -> tuple[os.stat_result, int] | None:
        extension = path.suffix.removeprefix(".").casefold()
        if extension in INSTALLER_EXTENSIONS:
            if label.casefold() not in {"téléchargements", "bureau", "documents"}:
                return None
            try:
                if path.parent.absolute() != root.absolute():
                    return None
            except OSError:
                return None
        elif extension not in IMAGE_EXTENSIONS and extension not in REGULAR_EXTENSIONS:
            return None
        try:
            if path.is_symlink():
                return None
            attrs = int(self.attributes(path))
            if attrs & (OFFLINE_ATTRIBUTES | REPARSE_POINT):
                return None
            stat = path.lstat()
            if not path.is_file():
                return None
        except (OSError, PermissionError):
            return None
        minimum = IMAGE_MINIMUM if extension in IMAGE_EXTENSIONS else MIB
        if stat.st_size == 0 or stat.st_size < minimum:
            return None
        return stat, attrs

    def _hash(
        self, path: Path, *, partial: bool, cancel: threading.Event | None = None
    ) -> str | None:
        digest = hashlib.blake2b()
        remaining = PARTIAL_SIZE if partial else None
        try:
            if int(self.attributes(path)) & (OFFLINE_ATTRIBUTES | REPARSE_POINT):
                return None
            with self.file_opener(path, "rb") as stream:
                while remaining is None or remaining > 0:
                    if self._cancelled(cancel):
                        return None
                    size = 1024 * 1024 if remaining is None else min(remaining, 1024 * 1024)
                    block = stream.read(size)
                    if not block:
                        break
                    digest.update(block)
                    if remaining is not None:
                        remaining -= len(block)
            return digest.hexdigest()
        except (OSError, PermissionError):
            return None

    def _display_folder(self, path: Path, root: Path, label: str) -> str:
        try:
            relative = path.parent.absolute().relative_to(root.absolute())
        except (OSError, ValueError):
            return label
        return " › ".join((label, *relative.parts)) if relative.parts else label

    @staticmethod
    def _cancelled(cancel: threading.Event | None) -> bool:
        return bool(cancel and cancel.is_set())

    def scan(
        self,
        progress: Callable[[int], Any] | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        started = self.clock()
        excluded = self._excluded_roots()
        by_size: dict[int, list[dict[str, Any]]] = defaultdict(list)
        seen: set[str] = set()
        looked = 0
        ignored = 0

        for label, root in self.folders.items():
            if self._cancelled(cancel):
                break
            if self._blocked_path(root, excluded, root) or _is_reparse(root) or not root.is_dir():
                ignored += 1
                continue
            try:
                walker = os.walk(root, topdown=True, followlinks=False)
                for current_raw, dirs, files in walker:
                    if self._cancelled(cancel):
                        break
                    current = Path(current_raw)
                    if self._blocked_path(current, excluded, root) or _is_reparse(current):
                        dirs[:] = []
                        ignored += 1
                        continue
                    if self._has_project_marker(dirs, files):
                        dirs[:] = []
                        ignored += len(files) + 1
                        continue
                    kept_dirs = []
                    for name in dirs:
                        child = current / name
                        if self._blocked_path(child, excluded, root) or _is_reparse(child):
                            ignored += 1
                        else:
                            kept_dirs.append(name)
                    dirs[:] = kept_dirs
                    for name in files:
                        looked += 1
                        if progress:
                            progress(looked)
                        path = current / name
                        key = os.path.normcase(str(path.absolute()))
                        if key in seen:
                            continue
                        candidate = self._candidate(path, root, label)
                        if candidate is None:
                            ignored += 1
                            continue
                        seen.add(key)
                        stat, _attrs = candidate
                        by_size[int(stat.st_size)].append({
                            "path": path, "root": root, "label": label,
                            "size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns),
                            "mtime": float(stat.st_mtime),
                        })
            except (OSError, PermissionError):
                ignored += 1

        internal_groups: dict[str, dict[str, Any]] = {}
        if not self._cancelled(cancel):
            for size, same_size in by_size.items():
                if len(same_size) < 2:
                    continue
                by_partial: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for item in same_size:
                    if self._cancelled(cancel):
                        break
                    partial = self._hash(item["path"], partial=True, cancel=cancel)
                    if partial is None:
                        ignored += 1
                    else:
                        by_partial[partial].append(item)
                for same_partial in by_partial.values():
                    if len(same_partial) < 2 or self._cancelled(cancel):
                        continue
                    by_full: dict[str, list[dict[str, Any]]] = defaultdict(list)
                    for item in same_partial:
                        full = self._hash(item["path"], partial=False, cancel=cancel)
                        if full is None:
                            ignored += 1
                        else:
                            item["digest"] = full
                            by_full[full].append(item)
                    for digest, copies in by_full.items():
                        if len(copies) < 2:
                            continue
                        if not _spread_out(copies):
                            ignored += len(copies)   # doublons voulus dans un même projet / une même banque de sons
                            continue
                        copies.sort(key=lambda item: (
                            item["label"].casefold() in KEEPER_DEPRIORITIZED,
                            item["mtime_ns"], len(str(item["path"])), str(item["path"]).casefold(),
                        ))
                        identifier = hashlib.blake2b(
                            f"{size}:{digest}".encode("ascii"), digest_size=16
                        ).hexdigest()
                        copies[0]["keep"] = True
                        for item in copies[1:]:
                            item["keep"] = False
                        internal_groups[identifier] = {
                            "id": identifier, "size": size, "digest": digest, "copies": copies,
                        }

        public_groups = []
        for group in internal_groups.values():
            copies = group["copies"]
            public_groups.append({
                "id": group["id"], "nom": copies[0]["path"].name, "taille": group["size"],
                "copies": [{
                    "chemin": str(item["path"]),
                    "dossier_lisible": self._display_folder(item["path"], item["root"], item["label"]),
                    "date_modif": _date(item["mtime"]), "garder": bool(item["keep"]),
                } for item in copies],
                "gain": group["size"] * (len(copies) - 1),
            })
        public_groups.sort(key=lambda group: (-group["gain"], group["nom"].casefold()))
        total = sum(group["gain"] for group in public_groups)
        duplicate_count = sum(len(group["copies"]) - 1 for group in public_groups)
        result = {
            "groups": public_groups[:200], "fichiers_regardes": looked,
            "duree_s": round(max(0.0, self.clock() - started), 3), "gain_total": total,
            "fichiers_en_double": duplicate_count,
            "ignorés": ignored, "annule": self._cancelled(cancel),
        }
        with self._lock:
            self._groups = internal_groups
            self.last_result = result
        return result

    @staticmethod
    def _selected_paths(selection: Any) -> list[str]:
        if isinstance(selection, str):
            return [selection]
        if isinstance(selection, list):
            result = []
            for item in selection:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    values = item.get("chemins", item.get("copies", item.get("chemin", [])))
                    result.extend(Duplicates._selected_paths(values))
            return result
        if isinstance(selection, dict):
            values = selection.get("chemins", selection.get("copies", selection.get("selection")))
            if values is not None:
                return Duplicates._selected_paths(values)
            result = []
            for value in selection.values():
                result.extend(Duplicates._selected_paths(value))
            return result
        return []

    def apply(self, selection: Any) -> dict[str, Any]:
        wanted = set(self._selected_paths(selection))
        ready: list[tuple[Path, Path, str]] = []
        messages: list[str] = []
        skipped = 0
        with self._lock:
            groups = list(self._groups.values())
        known_paths = {str(item["path"]) for group in groups for item in group["copies"]}
        unknown = wanted - known_paths
        if unknown:
            skipped += len(unknown)
            messages.append(f"{len(unknown)} fichier(s) ne viennent pas de la dernière analyse.")

        for group in groups:
            chosen = [item for item in group["copies"] if str(item["path"]) in wanted]
            if not chosen:
                continue
            keeper = next(item for item in group["copies"] if item["keep"])
            if keeper in chosen or len(chosen) >= len(group["copies"]):
                skipped += len(chosen)
                messages.append("Je garde toujours au moins une copie de chaque fichier.")
                continue
            keeper_hash = self._current_hash(keeper)
            if keeper_hash != group["digest"]:
                skipped += len(chosen)
                messages.append(f"{keeper['path'].name} : la copie gardée a disparu ou a changé.")
                continue
            for item in chosen:
                try:
                    stat = item["path"].lstat()
                    unchanged = (
                        not item["path"].is_symlink()
                        and int(stat.st_size) == item["size"]
                        and int(stat.st_mtime_ns) == item["mtime_ns"]
                        and not (int(self.attributes(item["path"])) & (OFFLINE_ATTRIBUTES | REPARSE_POINT))
                    )
                except (OSError, PermissionError):
                    unchanged = False
                if not unchanged:
                    skipped += 1
                    messages.append(f"{item['path'].name} a changé depuis l’analyse : je le laisse en place.")
                    continue
                ready.append((item["path"], item["root"], "doublons"))

        if not ready:
            return {
                "ok": False, "deplaces": 0, "place_gagnee": 0, "ignores": skipped,
                "messages": messages, "resultat": self.last_result,
            }
        action = self.actions.quarantine(
            ready, action_type="doublons",
            summary=f"{len(ready)} fichier(s) en double mis en quarantaine",
        )
        moved = {item["original"] for item in action.get("elements", [])}
        skipped += int(action.get("ignores", 0)) + int(action.get("refuses", 0))
        self._remove_moved(moved)
        return {
            "ok": bool(moved), "deplaces": len(moved),
            "place_gagnee": int(action.get("place_gagnee", 0)), "ignores": skipped,
            "messages": messages, "action": action, "resultat": self.last_result,
        }

    def _current_hash(self, item: dict[str, Any]) -> str | None:
        try:
            stat = item["path"].lstat()
            if item["path"].is_symlink() or int(stat.st_size) != item["size"]:
                return None
            if int(self.attributes(item["path"])) & (OFFLINE_ATTRIBUTES | REPARSE_POINT):
                return None
        except (OSError, PermissionError):
            return None
        return self._hash(item["path"], partial=False)

    def _remove_moved(self, moved: set[str]) -> None:
        if not moved:
            return
        with self._lock:
            for identifier in list(self._groups):
                group = self._groups[identifier]
                group["copies"] = [item for item in group["copies"] if str(item["path"]) not in moved]
                if len(group["copies"]) < 2:
                    del self._groups[identifier]
            groups = []
            for group in self._groups.values():
                copies = group["copies"]
                groups.append({
                    "id": group["id"], "nom": copies[0]["path"].name, "taille": group["size"],
                    "copies": [{
                        "chemin": str(item["path"]),
                        "dossier_lisible": self._display_folder(item["path"], item["root"], item["label"]),
                        "date_modif": _date(item["mtime"]), "garder": bool(item["keep"]),
                    } for item in copies],
                    "gain": group["size"] * (len(copies) - 1),
                })
            groups.sort(key=lambda value: (-value["gain"], value["nom"].casefold()))
            self.last_result = {
                **self.last_result, "groups": groups[:200],
                "gain_total": sum(group["gain"] for group in groups),
                "fichiers_en_double": sum(len(group["copies"]) - 1 for group in groups),
            }

    @staticmethod
    def _open_in_explorer(path: Path) -> Any:
        return subprocess.Popen(["explorer.exe", "/select,", str(path)])

    def open_folder(self, raw_path: str) -> dict[str, Any]:
        path = str(raw_path)
        with self._lock:
            allowed = {str(item["path"]) for group in self._groups.values() for item in group["copies"]}
        if path not in allowed:
            return {"ok": False, "erreur": "Ce fichier n’est pas dans la dernière analyse."}
        try:
            self.folder_opener(Path(path))
            return {"ok": True}
        except OSError:
            return {"ok": False, "erreur": "Je n’arrive pas à ouvrir ce dossier."}

    def exclude_folder(self, raw_path: str) -> dict[str, Any]:
        folder = Path(raw_path)
        if folder.suffix or not folder.is_dir():
            folder = folder.parent
        if not folder.is_dir() or not any(_same_or_below(folder, root) for root in self.folders.values()):
            return {"ok": False, "erreur": "Ce dossier n’est pas dans les dossiers analysés."}
        preferences = self._preferences()
        raw_excluded = preferences.get("doublons_exclus", [])
        excluded = (
            [value for value in raw_excluded if isinstance(value, str)]
            if isinstance(raw_excluded, list) else []
        )
        if str(folder) not in excluded:
            excluded.append(str(folder))
        preferences["doublons_exclus"] = excluded
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
            temporary.write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.config_path)
        except OSError:
            return {"ok": False, "erreur": "Je n’arrive pas à mémoriser ce dossier."}
        return {"ok": True, "dossier": str(folder)}


_default_service: Duplicates | None = None


def service() -> Duplicates:
    global _default_service
    if _default_service is None:
        _default_service = Duplicates()
    return _default_service


def _spread_out(copies: list[dict[str, Any]]) -> bool:
    """Un groupe n'est proposé que si ses copies sont dans des endroits différents (ex. Téléchargements et Images),
    ou si l'une traîne dans Téléchargements / sur le Bureau. Des fichiers identiques rangés dans le MÊME dossier de
    premier niveau (un projet, une banque de sons comme S.K.Y. Keys) sont presque toujours voulus : on n'y touche pas."""
    if any(item["label"].casefold() in KEEPER_DEPRIORITIZED for item in copies):
        return True
    zones = set()
    for item in copies:
        relative = item["path"].relative_to(item["root"]).parts
        zones.add((item["label"], relative[0].casefold() if len(relative) > 1 else ""))
    return len(zones) >= 2


def scan(progress: Callable[[int], Any] | None = None, cancel: threading.Event | None = None) -> dict[str, Any]:
    return service().scan(progress=progress, cancel=cancel)


def apply(selection: Any) -> dict[str, Any]:
    return service().apply(selection)
