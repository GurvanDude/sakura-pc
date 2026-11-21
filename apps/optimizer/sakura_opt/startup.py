"""Programmes lancés avec Windows, sans jamais demander les droits administrateur."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

from core import paths

from .actions import ActionManager, manager as action_manager
from .names import executable_info


RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_WOW = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
STORE = (r"Software\Classes\Local Settings\Software\Microsoft\Windows"
         r"\CurrentVersion\AppModel\SystemAppData")
STORE_DISABLED = 1

UNNEEDED = (
    # applis du Store qu'on ouvre soi-même
    "whatsapp", "yourphone", "lien avec le téléphone", "crossdevice", "appareils connectés", "startexperiences",
    "actualités de démarrer", "m365", "microsoft 365", "outlook", "xbox", "gamingapp", "windowsterminal",
    "terminal windows", "awezip", "claude", "codex", "clipchamp", "microsoft.people", "contacts",
    "steam", "discord", "epicgames", "eadm", "ea desktop", "eadesktop", "origin", "ubisoft", "uplay",
    "battle.net", "riot", "gog", "galaxy", "onedrive", "teams", "spotify", "opera",
    "msedge", "edge auto launch", "edgeautolaunch", "skype", "zoom", "nordvpn", "overwolf", "docker",
    "adobe updater", "adobeupdater", "ccleaner", "itunes helper", "ituneshelper",
)
USEFUL = ("lgmonitor", "lg monitor", "lghub", "g hub", "icue", "wallpaper engine", "wallpaperengine", "razer",
          "steelseries", "msi center", "msicenter")
KEEP = ("realtek", "amd software", "radeon", "nvidia", "antivirus", "defender", "avast",
        "avg", "bitdefender", "kaspersky", "eset", "malwarebytes")

TEXTS = {
    "inutile": "Tu peux le lancer quand tu en as besoin ; au démarrage il ralentit l'arrivée du bureau.",
    "utile": "Utile si tu veux tes réglages dès l'allumage.",
    "a_garder": "À garder au démarrage pour le bon fonctionnement du PC.",
    "neutre": "Je ne connais pas ce programme : coupe-le seulement si tu sais ce que c'est.",
}


def recommendation(name: str, command: str) -> dict[str, str]:
    text = f"{name} {command}".casefold()
    if "ollama" in text:
        return {"niveau": "utile", "texte": "Sakura AI s'en sert pour réfléchir."}
    if "amdnoisesuppression" in text or "amd noise suppression" in text:
        return {"niveau": "neutre", "texte": "Utile seulement si tu te sers de la suppression de bruit du micro AMD."}
    # les mots précis d'abord : Wallpaper Engine vit dans le dossier de Steam, « steam » ne doit pas l'emporter
    for level, words in (("utile", USEFUL), ("a_garder", KEEP), ("inutile", UNNEEDED)):
        if any(word in text for word in words):
            return {"niveau": level, "texte": TEXTS[level]}
    return {"niveau": "neutre", "texte": TEXTS["neutre"]}


# applis du Store courantes : début du nom de paquet → nom affiché
STORE_NAMES = {
    "microsoft.yourphone": "Lien avec le téléphone", "microsoftteams": "Microsoft Teams",
    "msteams": "Microsoft Teams", "spotifyab.spotifymusic": "Spotify", "5319275a.whatsappdesktop": "WhatsApp",
    "microsoft.windowsterminal": "Terminal Windows", "microsoft.gamingapp": "Xbox", "microsoft.xboxapp": "Xbox",
    "microsoft.windowscommunicationsapps": "Courrier et Calendrier", "microsoft.outlookforwindows": "Outlook",
    "microsoft.microsoftofficehub": "Microsoft 365", "microsoft.m365companions": "Compagnons Microsoft 365", "microsoft.startexperiencesapp": "Actualités de Démarrer",
    "microsoftwindows.crossdevice": "Appareils connectés", "microsoft.people": "Contacts",
    "lgelectronics.lgmonitorapp": "LG Monitor", "3138awezip.awezip": "AweZip", "claude": "Claude",
    "9426micro-starinternation.msicenter": "MSI Center", "advancedmicrodevicesinc-rsxcm": "AMD Software",
}


def store_name(package: str, task: str) -> str:
    """Nom lisible d'une appli du Store, d'après son paquet (« Editeur.NomAppli_hash »)."""
    family = package.split("_", 1)[0]
    for prefix, label in STORE_NAMES.items():
        if family.lower().startswith(prefix):
            return label
    name = family.split(".")[-1] if "." in family else family
    if re.fullmatch(r"[0-9a-fA-F-]{20,}", name):    # paquet sans nom lisible : on garde le nom de la tâche
        return task
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)   # « WindowsTerminal » → « Windows Terminal »


def _identifier(kind: str, *parts: str) -> str:
    raw = "\0".join((kind, *(str(part).casefold() for part in parts)))
    return f"{kind}-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _executable(command: str) -> Path | None:
    expanded = os.path.expandvars(str(command).strip())
    match = re.match(r'^"([^"]+\.exe)"|^([^\s]+\.exe)', expanded, re.I)
    return Path(match.group(1) or match.group(2)) if match else None


class WindowsStartupBackend:
    """Petit adaptateur isolant entièrement winreg pour les tests."""

    def registry_values(self, hive: str, key: str) -> list[tuple[str, Any, int]]:
        try:
            import winreg
            root = getattr(winreg, f"HKEY_{hive}")
            with winreg.OpenKey(root, key, 0, winreg.KEY_READ) as opened:
                result = []
                index = 0
                while True:
                    try:
                        result.append(winreg.EnumValue(opened, index))
                        index += 1
                    except OSError:
                        return result
        except (FileNotFoundError, OSError, AttributeError, ImportError):
            return []

    def registry_get(self, hive: str, key: str, name: str) -> tuple[Any, int] | None:
        return next(((value, kind) for item, value, kind in self.registry_values(hive, key)
                     if item == name), None)

    def registry_set(self, hive: str, key: str, name: str, value: Any, kind: int) -> None:
        import winreg
        root = getattr(winreg, f"HKEY_{hive}")
        with winreg.CreateKeyEx(root, key, 0, winreg.KEY_SET_VALUE) as opened:
            winreg.SetValueEx(opened, name, 0, kind, value)

    def registry_delete(self, hive: str, key: str, name: str) -> None:
        import winreg
        root = getattr(winreg, f"HKEY_{hive}")
        with winreg.OpenKey(root, key, 0, winreg.KEY_SET_VALUE) as opened:
            winreg.DeleteValue(opened, name)

    def store_tasks(self) -> list[tuple[str, str, int]]:
        try:
            import winreg
            result = []
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STORE) as root:
                package_index = 0
                while True:
                    try:
                        package = winreg.EnumKey(root, package_index)
                        package_index += 1
                    except OSError:
                        break
                    with winreg.OpenKey(root, package) as package_key:
                        task_index = 0
                        while True:
                            try:
                                task = winreg.EnumKey(package_key, task_index)
                                task_index += 1
                            except OSError:
                                break
                            value = self.registry_get("CURRENT_USER", f"{STORE}\\{package}\\{task}", "State")
                            if value is not None:
                                result.append((package, task, int(value[0])))
            return result
        except (FileNotFoundError, OSError, ImportError):
            return []

    def shortcut_command(self, shortcut: Path) -> str:
        if shortcut.suffix.casefold() != ".lnk":
            return str(shortcut)
        try:
            import win32com.client
            link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(shortcut))
            return " ".join(part for part in (link.TargetPath, link.Arguments) if part)
        except Exception:
            return str(shortcut)


class Startup:
    def __init__(
        self,
        actions: ActionManager | None = None,
        *,
        backend: Any | None = None,
        environ: dict[str, str] | None = None,
        user_startup: Path | None = None,
        common_startup: Path | None = None,
        disabled_dir: Path | None = None,
    ) -> None:
        self.actions = actions or action_manager()
        self.backend = backend or WindowsStartupBackend()
        self.environ = environ if environ is not None else os.environ
        appdata = self.environ.get("APPDATA", "")
        programdata = self.environ.get("ProgramData", self.environ.get("PROGRAMDATA", ""))
        self.user_startup = Path(user_startup) if user_startup is not None else Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup"
        self.common_startup = Path(common_startup) if common_startup is not None else Path(programdata) / "Microsoft/Windows/Start Menu/Programs/Startup"
        self.disabled_dir = Path(disabled_dir) if disabled_dir is not None else Path(paths.USER) / "demarrage_coupe"
        if hasattr(self.actions, "register_undo_handler"):
            self.actions.register_undo_handler("demarrage", self._restore)

    @staticmethod
    def _protected(name: str, command: str) -> str | None:
        text = f"{name} {command}".casefold()
        if "sakura" in text or "lights.py" in text or "launcher.py" in text:
            return "Fait partie de Sakura PC"
        if "securityhealth" in text or "windows security" in text:
            return "Sécurité de Windows"
        return None

    def _entry(self, *, identifier: str, name: str, command: str, source: str,
               modifiable: bool, reason: str | None = None, active: bool = True,
               kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        executable = _executable(command)
        description, company = executable_info(executable) if executable else (None, None)
        display = description or name
        protected = self._protected(display, command)
        if protected:
            modifiable, reason = False, protected
        rec = recommendation(display, command)
        if protected:
            rec = {"niveau": "a_garder", "texte": protected + "."}
        return {
            "id": identifier, "nom": display, "editeur": company or "",
            "éditeur": company or "", "commande": command, "source": source,
            "etat": "actif" if active else "coupé",
            "état": "actif" if active else "coupé",
            "modifiable": modifiable, "raison": reason or "",
            "recommandation": rec, "type": kind, "_data": data or {},
        }

    def _journal_payloads(self) -> dict[str, dict[str, Any]]:
        payloads = {}
        for row in self.actions.list_actions():
            payload = row.get("demarrage")
            if (row.get("type") == "demarrage" and row.get("etat", row.get("état")) == "fait"
                    and isinstance(payload, dict) and payload.get("entry_id")):
                payloads.setdefault(str(payload["entry_id"]), payload)
        return payloads

    def _entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        live_ids: set[str] = set()
        registry_sources = (
            ("CURRENT_USER", RUN, "Registre de ton compte", True),
            ("LOCAL_MACHINE", RUN, "Registre de tous les comptes", False),
            ("LOCAL_MACHINE", RUN_WOW, "Registre de tous les comptes (32 bits)", False),
        )
        admin_reason = "Réglé pour tous les comptes : il faut les droits administrateur."
        for hive, key, label, modifiable in registry_sources:
            for name, value, value_type in self.backend.registry_values(hive, key):
                identifier = _identifier("run", hive, key, name)
                live_ids.add(identifier)
                entries.append(self._entry(
                    identifier=identifier, name=name, command=str(value), source=label,
                    modifiable=modifiable, reason=None if modifiable else admin_reason,
                    kind="run", data={"hive": hive, "key": key, "name": name,
                                      "value": value, "value_type": value_type},
                ))

        for folder, label, modifiable in ((self.user_startup, "Dossier Démarrage de ton compte", True),
                                          (self.common_startup, "Dossier Démarrage de tous les comptes", False)):
            try:
                files: Iterable[Path] = (
                    item for item in folder.iterdir()
                    if item.is_file() and item.suffix.casefold() in (".lnk", ".url")
                )
                for shortcut in files:
                    command = self.backend.shortcut_command(shortcut)
                    identifier = _identifier("shortcut", str(folder), shortcut.name)
                    live_ids.add(identifier)
                    entries.append(self._entry(
                        identifier=identifier, name=shortcut.stem, command=command, source=label,
                        modifiable=modifiable, reason=None if modifiable else admin_reason,
                        kind="shortcut", data={"path": str(shortcut), "name": shortcut.name},
                    ))
            except OSError:
                pass

        for package, task, state in self.backend.store_tasks():
            identifier = _identifier("store", package, task)
            live_ids.add(identifier)
            entries.append(self._entry(
                identifier=identifier, name=store_name(package, task), command=package, source="Application du Store",
                modifiable=True, active=state != STORE_DISABLED, kind="store",
                data={"package": package, "task": task, "state": state},
            ))

        for identifier, payload in self._journal_payloads().items():
            if identifier in live_ids or payload.get("kind") == "store":
                continue
            kind = str(payload.get("kind", ""))
            if kind not in ("run", "shortcut"):
                continue
            entries.append(self._entry(
                identifier=identifier, name=str(payload.get("display_name") or payload.get("name") or "Programme"),
                command=str(payload.get("command") or payload.get("value") or ""),
                source=str(payload.get("source") or "Démarrage de ton compte"),
                modifiable=True, active=False, kind=kind, data=payload,
            ))
        # d'abord ce qui tourne et qu'on peut couper (les « inutiles » en tête), puis ce qui est déjà coupé
        order = {"inutile": 0, "neutre": 1, "utile": 2, "a_garder": 3}
        entries.sort(key=lambda item: (not item["modifiable"], item["etat"] != "actif",
                                       order.get(item["recommandation"]["niveau"], 1),
                                       item["nom"].casefold(), item["source"]))
        return entries

    def list_entries(self) -> list[dict[str, Any]]:
        """Renvoie seulement les données utiles à l'interface et au contrat JSON."""
        return [{key: value for key, value in entry.items() if key != "_data"}
                for entry in self._entries()]

    def disable(self, identifier: str) -> dict[str, Any]:
        entry = next((item for item in self._entries() if item["id"] == identifier), None)
        if entry is None:
            return {"ok": False, "erreur": "Cette entrée de démarrage est introuvable."}
        if not entry["modifiable"]:
            return {"ok": False, "erreur": entry["raison"] or "Cette entrée ne peut pas être modifiée."}
        if entry["etat"] != "actif":
            return {"ok": False, "erreur": "Ce programme est déjà coupé au démarrage."}
        data = dict(entry["_data"])
        payload = {**data, "entry_id": identifier, "kind": entry["type"],
                   "display_name": entry["nom"], "command": entry["commande"],
                   "source": entry["source"]}
        try:
            if entry["type"] == "run":
                current = self.backend.registry_get(data["hive"], data["key"], data["name"])
                if current is None:
                    return {"ok": False, "erreur": "Cette entrée vient de disparaître du Registre."}
                payload["value"], payload["value_type"] = current
                self.backend.registry_delete(data["hive"], data["key"], data["name"])
            elif entry["type"] == "shortcut":
                source = Path(data["path"])
                self.disabled_dir.mkdir(parents=True, exist_ok=True)
                destination = self.disabled_dir / source.name
                if destination.exists():
                    destination = ActionManager._restored_name(destination)
                shutil.move(str(source), str(destination))
                payload["disabled_path"] = str(destination)
                payload["original_path"] = str(source)
            else:
                payload["old_state"] = int(data["state"])
                key = f"{STORE}\\{data['package']}\\{data['task']}"
                self.backend.registry_set("CURRENT_USER", key, "State", STORE_DISABLED, 4)
        except (OSError, PermissionError) as exc:
            return {"ok": False, "erreur": f"Windows a refusé la modification : {exc}"}
        try:
            action = self.actions.record_startup(
                summary=f"{entry['nom']} coupé au démarrage", startup=payload
            )
        except OSError as exc:
            rollback = self._restore(payload)
            detail = " La modification a été remise comme avant." if rollback.get("ok") else ""
            return {"ok": False, "erreur": f"Le journal n'a pas pu être écrit : {exc}.{detail}"}
        return {"ok": True, "message": f"{entry['nom']} ne se lancera plus avec Windows.",
                "action": action}

    def _restore(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            if payload.get("kind") == "run":
                if self.backend.registry_get(payload["hive"], payload["key"], payload["name"]) is not None:
                    return {"ok": False, "erreur": "Une entrée du même nom existe déjà : je ne l'ai pas écrasée."}
                self.backend.registry_set(payload["hive"], payload["key"], payload["name"],
                                          payload["value"], int(payload["value_type"]))
            elif payload.get("kind") == "shortcut":
                source = Path(payload["disabled_path"])
                if not source.exists():
                    return {"ok": False, "erreur": "Le raccourci coupé est introuvable."}
                destination = Path(payload["original_path"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    destination = ActionManager._restored_name(destination)
                shutil.move(str(source), str(destination))
            elif payload.get("kind") == "store":
                key = f"{STORE}\\{payload['package']}\\{payload['task']}"
                self.backend.registry_set("CURRENT_USER", key, "State", int(payload["old_state"]), 4)
            else:
                return {"ok": False, "erreur": "Cette action de démarrage est incomplète."}
        except (OSError, PermissionError, KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "erreur": f"Windows a refusé la remise : {exc}"}
        return {"ok": True, "message": f"{payload.get('display_name', 'Le programme')} se lancera de nouveau avec Windows.",
                "restaures": 1}

    def enable(self, identifier: str) -> dict[str, Any]:
        for row in self.actions.list_actions():
            payload = row.get("demarrage") or {}
            if (row.get("type") == "demarrage" and row.get("etat", row.get("état")) == "fait"
                    and payload.get("entry_id") == identifier):
                return self.actions.undo(str(row["id"]))
        entry = next((item for item in self._entries() if item["id"] == identifier), None)
        if entry and entry["type"] == "store" and entry["etat"] != "actif":
            data = entry["_data"]
            try:
                key = f"{STORE}\\{data['package']}\\{data['task']}"
                self.backend.registry_set("CURRENT_USER", key, "State", 2, 4)
                payload = {
                    **data, "entry_id": identifier, "kind": "store", "old_state": int(data["state"]),
                    "display_name": entry["nom"], "command": entry["commande"],
                    "source": entry["source"], "operation": "enable",
                }
                try:
                    action = self.actions.record_startup(
                        summary=f"{entry['nom']} remis au démarrage", startup=payload
                    )
                except OSError as exc:
                    rollback = self._restore(payload)
                    detail = " La modification a été remise comme avant." if rollback.get("ok") else ""
                    return {"ok": False, "erreur": f"Le journal n'a pas pu être écrit : {exc}.{detail}"}
                return {"ok": True, "message": f"{entry['nom']} se lancera de nouveau avec Windows.",
                        "action": action}
            except (OSError, PermissionError) as exc:
                return {"ok": False, "erreur": f"Windows a refusé la remise : {exc}"}
        return {"ok": False, "erreur": "Je n'ai pas trouvé la sauvegarde de cette entrée."}


_default_startup: Startup | None = None


def service() -> Startup:
    global _default_startup
    if _default_startup is None:
        _default_startup = Startup()
    return _default_startup


def list_entries() -> list[dict[str, Any]]:
    return service().list_entries()


def disable(identifier: str) -> dict[str, Any]:
    return service().disable(identifier)


def enable(identifier: str) -> dict[str, Any]:
    return service().enable(identifier)
