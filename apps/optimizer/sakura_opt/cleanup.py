"""Aperçu et application des nettoyages sûrs, sans droits administrateur."""

from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path
from typing import Any, Callable, Iterable

import psutil

from .actions import ActionManager, _is_reparse, _strictly_below, manager as action_manager


GB = 1024 ** 3
DAY = 24 * 60 * 60

CATEGORY_TEXT = {
    "temp": ("Fichiers temporaires", "Des restes laissés par tes applications.",
             "Les fichiers de moins de 24 h restent en place.", True),
    "plantages": ("Rapports de plantage", "Des rapports créés quand une application se ferme mal.",
                  "Tu perds seulement d'anciens rapports de diagnostic.", True),
    "miniatures": ("Miniatures et icônes", "Les aperçus d'images et les icônes gardés par Windows.",
                   "Windows les refait tout seul quand il en a besoin.", True),
    "navigateur": ("Cache d'Opera GX", "Des copies de pages conservées pour les ouvrir plus vite.",
                   "La première ouverture de certains sites pourra être un peu plus lente.", False),
    "shaders": ("Caches graphiques AMD", "Des calculs graphiques déjà préparés pour tes jeux.",
                "Tes jeux vont saccader un peu le temps de les refaire.", False),
    "corbeille": ("Corbeille", "Les fichiers que tu as déjà mis à la corbeille.",
                  "Elle sera vidée pour de bon : aucune annulation ne sera possible.", False),
}


def _process_names() -> set[str]:
    names = set()
    for process in psutil.process_iter(["name"]):
        try:
            names.add(str(process.info.get("name") or "").casefold())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return names


def _query_recycle_bin() -> tuple[int, int]:
    if os.name != "nt":
        return 0, 0

    class Info(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("i64Size", ctypes.c_longlong),
                    ("i64NumItems", ctypes.c_longlong)]

    info = Info(ctypes.sizeof(Info), 0, 0)
    result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    if result != 0:
        raise OSError(result, "Impossible de lire la corbeille")
    return int(info.i64Size), int(info.i64NumItems)


def _empty_recycle_bin() -> None:
    if os.name != "nt":
        return
    # Pas de confirmation Windows, pas de barre de progression, pas de son.
    result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)
    if result != 0:
        raise OSError(result, "Impossible de vider la corbeille")


class Cleanup:
    def __init__(
        self,
        actions: ActionManager | None = None,
        *,
        environ: dict[str, str] | None = None,
        now: Callable[[], float] = time.time,
        process_names: Callable[[], Iterable[str]] = _process_names,
        recycle_query: Callable[[], tuple[int, int]] = _query_recycle_bin,
        recycle_empty: Callable[[], None] = _empty_recycle_bin,
    ) -> None:
        self.actions = actions or action_manager()
        self.environ = environ if environ is not None else os.environ
        self.now = now
        self.process_names = process_names
        self.recycle_query = recycle_query
        self.recycle_empty = recycle_empty

    def _local(self, *parts: str) -> Path | None:
        value = self.environ.get("LOCALAPPDATA")
        return Path(value).joinpath(*parts) if value else None

    def _roots(self, identifier: str) -> list[tuple[Path, str | None]]:
        temp = self.environ.get("TEMP") or self.environ.get("TMP")
        local = self._local()
        if identifier == "temp":
            return [(Path(temp), None)] if temp else []
        if local is None:
            return []
        if identifier == "plantages":
            return [
                (local / "CrashDumps", None),
                (local / "Microsoft" / "Windows" / "WER", None),
            ]
        if identifier == "miniatures":
            explorer = local / "Microsoft" / "Windows" / "Explorer"
            return [(explorer, "thumbcache_*.db"), (explorer, "iconcache_*.db")]
        if identifier == "navigateur":
            return [(local / "Opera Software" / "Opera GX Stable" / "Cache", None)]
        if identifier == "shaders":
            amd = local / "AMD"
            return [(amd / name, None) for name in ("DxCache", "DxcCache", "VkCache")]
        return []

    def _walk(self, root: Path, pattern: str | None, identifier: str) -> list[tuple[Path, Path, str]]:
        if not root.exists() or _is_reparse(root) or not root.is_dir():
            return []
        found: list[tuple[Path, Path, str]] = []
        if pattern:
            candidates = root.glob(pattern)
        else:
            def safe_walk() -> Iterable[Path]:
                for current, dirs, files in os.walk(root, followlinks=False):
                    current_path = Path(current)
                    dirs[:] = [name for name in dirs if not _is_reparse(current_path / name)]
                    for name in files:
                        yield current_path / name
            candidates = safe_walk()
        for candidate in candidates:
            if _strictly_below(candidate, root) is None:
                continue
            try:
                if identifier == "temp" and candidate.stat().st_mtime > self.now() - DAY:
                    continue
                if candidate.is_file():
                    found.append((candidate, root, identifier))
            except OSError:
                continue
        return found

    def candidates(self, identifier: str) -> list[tuple[Path, Path, str]]:
        result = []
        for root, pattern in self._roots(identifier):
            result.extend(self._walk(root, pattern, identifier))
        return result

    def scan(self) -> dict[str, Any]:
        running = {str(name).casefold() for name in self.process_names()}
        categories = []
        for identifier, (title, explanation, risk, checked) in CATEGORY_TEXT.items():
            disabled = identifier == "navigateur" and "opera.exe" in running
            reason = "Ferme Opera GX pour la vider" if disabled else ""
            if identifier == "corbeille":
                try:
                    size, count = self.recycle_query()
                except Exception:
                    size, count = 0, 0
            elif disabled:
                size, count = 0, 0
            else:
                files = self.candidates(identifier)
                sizes = []
                for path, _, _ in files:
                    try:
                        sizes.append(path.stat().st_size)
                    except OSError:
                        pass
                size, count = sum(sizes), len(sizes)
            categories.append({
                "id": identifier, "titre": title, "explication": explanation, "risque": risk,
                "cochee": checked, "taille": int(size), "nombre": int(count),
                "desactivee": disabled, "raison": reason,
            })
        return {"categories": categories, "taille_totale": sum(c["taille"] for c in categories)}

    def apply(self, identifiers: Iterable[str]) -> dict[str, Any]:
        requested = list(dict.fromkeys(str(value) for value in identifiers))
        valid = [value for value in requested if value in CATEGORY_TEXT]
        running = {str(name).casefold() for name in self.process_names()}
        if "navigateur" in valid and "opera.exe" in running:
            valid.remove("navigateur")
        files = [item for identifier in valid if identifier != "corbeille" for item in self.candidates(identifier)]
        rows = []
        if files:
            titles = [CATEGORY_TEXT[value][0] for value in valid if value != "corbeille"]
            rows.append(self.actions.quarantine(
                files, action_type="nettoyage", summary="Ménage : " + ", ".join(titles),
            ))
        recycle_size = 0
        recycle_error = ""
        if "corbeille" in valid:
            try:
                recycle_size, _ = self.recycle_query()
                self.recycle_empty()
                rows.append(self.actions.record_permanent(
                    summary="Corbeille vidée pour de bon", gained=recycle_size,
                ))
            except Exception as exc:
                recycle_error = str(exc)
        gained = sum(int(row.get("place_gagnee", 0)) for row in rows)
        ignored = sum(int(row.get("ignores", 0)) for row in rows)
        refused = sum(int(row.get("refuses", 0)) for row in rows)
        return {
            "ok": bool(rows) or not valid,
            "actions": rows,
            "action_id": rows[0]["id"] if rows else None,
            "place_gagnee": gained,
            "ignores": ignored,
            "refuses": refused,
            "erreur_corbeille": recycle_error,
        }


_default_cleanup: Cleanup | None = None


def service() -> Cleanup:
    global _default_cleanup
    if _default_cleanup is None:
        _default_cleanup = Cleanup()
    return _default_cleanup


def scan() -> dict[str, Any]:
    return service().scan()


def apply(identifiers: Iterable[str]) -> dict[str, Any]:
    return service().apply(identifiers)
