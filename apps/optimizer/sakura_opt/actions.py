"""Quarantaine et journal communs aux optimisations de Sakura Optimizer."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import shutil
import string
import uuid
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

from core import paths


SEVEN_DAYS = 7 * 24 * 60 * 60
REPARSE_POINT = 0x400


def _is_reparse(path: Path) -> bool:
    """Repère aussi les jonctions Windows, que Path.is_symlink ne voit pas toujours."""
    try:
        stat = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & REPARSE_POINT)


def _strictly_below(path: Path, root: Path) -> tuple[Path, Path] | None:
    """Renvoie les chemins résolus seulement si le fichier reste strictement sous root."""
    try:
        lexical_root = root.absolute()
        lexical_path = path.absolute()
        lexical_relative = lexical_path.relative_to(lexical_root)
        if not lexical_relative.parts or _is_reparse(lexical_root):
            return None
        current = lexical_root
        for part in lexical_relative.parts:
            current = current / part
            if _is_reparse(current):
                return None
        clean_root = root.resolve(strict=True)
        clean_path = path.resolve(strict=True)
        relative = clean_path.relative_to(clean_root)
    except (OSError, RuntimeError, ValueError):
        return None
    if not relative.parts or clean_path == clean_root:
        return None
    return clean_path, relative


def _tree_has_reparse(root: Path) -> bool:
    try:
        for current, dirs, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            if _is_reparse(current_path):
                return True
            if any(_is_reparse(current_path / name) for name in dirs + files):
                return True
    except OSError:
        return True
    return False


def _fixed_drives() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import ctypes
        get_type = ctypes.windll.kernel32.GetDriveTypeW
        return [
            Path(f"{letter}:\\") for letter in string.ascii_uppercase
            if get_type(f"{letter}:\\") == 3
        ]
    except Exception:
        return []


def choose_quarantine_root(
    *,
    user_root: Path = paths.USER,
    drives: Iterable[Path] | None = None,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
) -> Path:
    """Choisit le disque fixe hors C: qui possède le plus de place libre, sans rien créer."""
    choices: list[tuple[int, Path]] = []
    for drive in list(drives) if drives is not None else _fixed_drives():
        drive = Path(drive)
        if drive.drive.upper() == "C:" or str(drive).upper().startswith("C:"):
            continue
        try:
            choices.append((int(disk_usage(drive).free), drive))
        except OSError:
            continue
    if choices:
        return max(choices, key=lambda item: item[0])[1] / "SakuraPC" / "quarantaine"
    return Path(user_root) / "quarantaine"


class ActionManager:
    """Déplace, restaure et purge des fichiers sans jamais demander les droits admin."""

    def __init__(
        self,
        quarantine_root: Path | None = None,
        *,
        user_root: Path | None = None,
        journal_path: Path | None = None,
        now: Callable[[], float] | None = None,
        drives: Iterable[Path] | None = None,
        disk_usage: Callable[[Path], Any] = shutil.disk_usage,
        log_path: Path | None = None,
    ) -> None:
        self.user_root = Path(user_root) if user_root is not None else paths.USER
        self.quarantine_root = Path(quarantine_root) if quarantine_root is not None else (
            choose_quarantine_root(user_root=self.user_root, drives=drives, disk_usage=disk_usage)
        )
        self.journal_path = Path(journal_path) if journal_path is not None else (
            self.user_root / "optimizer-actions.jsonl"
        )
        self.now = now or __import__("time").time
        self.log_path = Path(log_path) if log_path is not None else (
            None if user_root is None else self.user_root / "optimizer-actions.log"
        )
        self.logger = logging.getLogger("sakura.optimizer.actions")
        self.logger.addHandler(logging.NullHandler())
        self._lock = threading.RLock()

    def _log(self, level: int, message: str, *args: Any) -> None:
        """Écrit puis ferme aussitôt le fichier, pour ne jamais le garder verrouillé."""
        try:
            log_path = self.log_path or paths.log("optimizer-actions")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            record = self.logger.makeRecord(
                self.logger.name, level, __file__, 0, message, args, None
            )
            handler.emit(record)
            handler.close()
        except OSError:
            pass

    def _read(self) -> list[dict[str, Any]]:
        try:
            lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        result = []
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                result.append(value)
        return result

    def _write_all(self, rows: list[dict[str, Any]]) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal_path.with_suffix(self.journal_path.suffix + ".tmp")
        temporary.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        temporary.replace(self.journal_path)

    def _append(self, row: dict[str, Any]) -> None:
        with self._lock:
            rows = self._read()
            rows.append(row)
            self._write_all(rows)
        self._log(logging.INFO, "%s : %s", row["id"], row["resume"])

    def list_actions(self) -> list[dict[str, Any]]:
        return list(reversed(self._read()))

    def _date(self) -> str:
        return dt.datetime.fromtimestamp(self.now(), dt.timezone.utc).isoformat()

    def quarantine(
        self,
        files: Iterable[tuple[Path, Path, str]],
        *,
        action_type: str,
        summary: str,
    ) -> dict[str, Any]:
        """Déplace les fichiers validés. Chaque erreur est isolée et comptée."""
        identifier = uuid.uuid4().hex
        elements: list[dict[str, Any]] = []
        skipped = 0
        refused = 0
        for raw_path, raw_root, category in files:
            path, root = Path(raw_path), Path(raw_root)
            category = str(category)
            if not category or category in (".", "..") or Path(category).name != category:
                refused += 1
                continue
            checked = _strictly_below(path, root)
            if checked is None:
                refused += 1
                continue
            clean_path, relative = checked
            try:
                if not clean_path.is_file():
                    refused += 1
                    continue
                size = clean_path.stat().st_size
                destination = self.quarantine_root / identifier / category / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                lexical_root = self.quarantine_root.absolute()
                lexical_parent = destination.parent.absolute()
                parent_relative = lexical_parent.relative_to(lexical_root)
                if _is_reparse(lexical_root):
                    refused += 1
                    continue
                current = lexical_root
                for part in parent_relative.parts:
                    current = current / part
                    if _is_reparse(current):
                        raise OSError("Une jonction est présente dans la quarantaine")
                lexical_parent.resolve(strict=True).relative_to(lexical_root.resolve(strict=True))
                if destination.exists():
                    destination = self._restored_name(destination)
                shutil.move(str(clean_path), str(destination))
                elements.append({
                    "original": str(clean_path),
                    "quarantaine": str(destination),
                    "taille": int(size),
                })
            except (OSError, PermissionError) as exc:
                skipped += 1
                self._log(logging.WARNING, "Fichier laissé en place (%s) : %s", clean_path, exc)
            except Exception as exc:
                skipped += 1
                self._log(logging.ERROR, "Erreur isolée pour %s : %s", clean_path, exc)
        gained = sum(item["taille"] for item in elements)
        row = {
            "id": identifier,
            "date": self._date(),
            "type": action_type,
            "resume": summary,
            "résumé": summary,
            "elements": elements,
            "éléments": elements,
            "place_gagnee": gained,
            "place gagnée": gained,
            "etat": "fait",
            "état": "fait",
            "ignores": skipped,
            "refuses": refused,
            "annulable": bool(elements),
        }
        self._append(row)
        return row

    def record_permanent(self, *, summary: str, gained: int) -> dict[str, Any]:
        """Journalise une action définitive, par exemple la corbeille Windows."""
        identifier = uuid.uuid4().hex
        row = {
            "id": identifier,
            "date": self._date(),
            "type": "définitif",
            "resume": summary,
            "résumé": summary,
            "elements": [],
            "éléments": [],
            "place_gagnee": int(gained),
            "place gagnée": int(gained),
            "etat": "fait",
            "état": "fait",
            "ignores": 0,
            "refuses": 0,
            "annulable": False,
        }
        self._append(row)
        return row

    @staticmethod
    def _restored_name(path: Path) -> Path:
        candidate = path.with_name(f"{path.stem} (restauré){path.suffix}")
        number = 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem} (restauré {number}){path.suffix}")
            number += 1
        return candidate

    def undo(self, identifier: str) -> dict[str, Any]:
        rows = self._read()
        row = next((item for item in rows if item.get("id") == identifier), None)
        if row is None:
            return {"ok": False, "erreur": "Action introuvable."}
        if row.get("etat", row.get("état")) != "fait" or not row.get("annulable"):
            return {"ok": False, "erreur": "Cette action ne peut pas être annulée."}
        restored = 0
        skipped = 0
        for element in row.get("elements", row.get("éléments", [])):
            source = Path(element["quarantaine"])
            try:
                if _strictly_below(source, self.quarantine_root) is None or not source.is_file():
                    skipped += 1
                    continue
                destination = Path(element["original"])
                if destination.exists():
                    destination = self._restored_name(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
                restored += 1
            except (OSError, RuntimeError, ValueError):
                skipped += 1
        row["etat"] = row["état"] = "annulé"
        row["annulable"] = False
        row["restaures"] = restored
        row["ignores_annulation"] = skipped
        self._write_all(rows)
        self._log(logging.INFO, "%s annulée : %s fichier(s) remis", identifier, restored)
        return {"ok": True, "action": row, "restaures": restored, "ignores": skipped}

    def purge(self, *, older_than_days: int = 7) -> dict[str, Any]:
        threshold = self.now() - older_than_days * 24 * 60 * 60
        rows = self._read()
        purged = 0
        freed = 0
        for row in rows:
            if row.get("etat", row.get("état")) != "fait" or not row.get("elements", row.get("éléments")):
                continue
            try:
                timestamp = dt.datetime.fromisoformat(row["date"]).timestamp()
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp > threshold:
                continue
            action_root = self.quarantine_root / str(row.get("id", ""))
            try:
                resolved_root = self.quarantine_root.resolve(strict=True)
                resolved_action = action_root.resolve(strict=True)
                resolved_action.relative_to(resolved_root)
                if resolved_action == resolved_root or _tree_has_reparse(action_root):
                    continue
                shutil.rmtree(action_root)
            except FileNotFoundError:
                pass
            except (OSError, RuntimeError, ValueError) as exc:
                self._log(logging.WARNING, "Purge impossible pour %s : %s", row.get("id"), exc)
                continue
            row["etat"] = row["état"] = "purgé"
            row["annulable"] = False
            purged += 1
            freed += int(row.get("place_gagnee", row.get("place gagnée", 0)))
        if purged:
            self._write_all(rows)
        return {"ok": True, "actions_purgees": purged, "octets": freed}

    def empty(self) -> dict[str, Any]:
        return self.purge(older_than_days=0)

    def quarantine_info(self) -> dict[str, Any]:
        total = 0
        for row in self._read():
            if row.get("etat", row.get("état")) == "fait" and row.get("annulable"):
                total += int(row.get("place_gagnee", row.get("place gagnée", 0)))
        drive = self.quarantine_root.drive or str(self.quarantine_root.anchor or self.quarantine_root)
        return {"taille": total, "disque": drive.rstrip("\\/"), "chemin": str(self.quarantine_root)}


_default_manager: ActionManager | None = None


def manager() -> ActionManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = ActionManager()
    return _default_manager


def actions() -> list[dict[str, Any]]:
    return manager().list_actions()


def undo(identifier: str) -> dict[str, Any]:
    return manager().undo(identifier)


def purge_quarantine() -> dict[str, Any]:
    return manager().purge()


def vider_quarantaine() -> dict[str, Any]:
    return manager().empty()
