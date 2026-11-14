"""Outils locaux que Sakura peut confier au modèle."""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core import paths

APP_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_ROOT = APP_ROOT.parent / "launcher"
FILE_SEARCH_SECONDS = 3.0
MAX_FILE_RESULTS = 10
START_MENU_CACHE_SECONDS = 5 * 60
MAX_OTHER_APPS = 60

_IGNORED_SHORTCUT_WORDS = {
    "uninstall", "desinstaller", "help", "aide", "read me", "readme",
    "website", "manuel",
}

_WINDOWS_APPS: tuple[dict[str, Any], ...] = (
    {
        "name": "Bloc-notes",
        "aliases": ["notepad", "bloc note", "blocnote"],
        "launch": {"exe": "notepad.exe"},
        "processes": ["notepad.exe"],
    },
    {
        "name": "Calculatrice",
        "aliases": ["calc", "calculator"],
        "launch": {"exe": "calc.exe"},
        "processes": ["CalculatorApp.exe"],
    },
    {
        "name": "Paint",
        "aliases": ["mspaint"],
        "launch": {"exe": "mspaint.exe"},
        "processes": ["mspaint.exe"],
    },
    {
        "name": "Explorateur de fichiers",
        "aliases": ["explorateur", "explorer", "file explorer"],
        "launch": {"exe": "explorer.exe"},
        "processes": ["explorer.exe"],
    },
    {
        "name": "Paramètres",
        "aliases": ["reglages windows", "parametres windows", "settings", "windows settings"],
        "launch": {"uri": "ms-settings:"},
        "processes": ["SystemSettings.exe"],
    },
    {
        "name": "Gestionnaire des tâches",
        "aliases": ["task manager", "taskmgr"],
        "launch": {"exe": "taskmgr.exe"},
        "processes": ["taskmgr.exe"],
    },
    {
        "name": "Invite de commandes",
        "aliases": ["cmd", "command prompt"],
        "launch": {"exe": "cmd.exe"},
        "processes": ["cmd.exe"],
    },
    {
        "name": "Capture d'écran",
        "aliases": ["outil capture", "snipping tool", "screen clip"],
        "launch": {"uri": "ms-screenclip:"},
        "processes": ["SnippingTool.exe", "ScreenClippingHost.exe"],
    },
)


def _normalise(value: Any) -> str:
    """Retire accents et ponctuation pour comparer des noms souplement."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _load_config() -> dict[str, Any]:
    try:
        value = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for section in ("apps", "games"):
        values = config.get(section, [])
        if isinstance(values, list):
            found.extend(
                entry for entry in values
                if isinstance(entry, dict) and isinstance(entry.get("name"), str)
            )
    return found


def _entry_names(entry: dict[str, Any]) -> list[str]:
    aliases = entry.get("aliases", [])
    return [entry["name"], *(alias for alias in aliases if isinstance(alias, str))]


def _words_match(wanted: str, name: str) -> bool:
    """Chaque mot important demandé doit ressembler à un mot du nom.
    Sinon « sakura optimizer » finirait sur « sakura lumieres » grâce au seul mot commun."""
    words = name.split()
    return all(
        any(difflib.SequenceMatcher(None, word, other).ratio() >= 0.75 for other in words)
        for word in wanted.split() if len(word) >= 4
    )


def _matches(query: str, entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    wanted = _normalise(query)
    named = [(entry, _normalise(alias)) for entry in entries for alias in _entry_names(entry)]
    if not wanted:
        return [], [entry["name"] for entry in entries[:5]]

    exact = _highest_priority(_unique_entries(entry for entry, name in named if name == wanted))
    if exact:
        return exact, []
    partial = _highest_priority(_unique_entries(entry for entry, name in named if wanted in name))
    if partial:
        return partial, []

    by_name: dict[str, dict[str, Any]] = {}
    for entry, normal in named:
        by_name.setdefault(normal, entry)
    close = difflib.get_close_matches(wanted, list(by_name), n=5, cutoff=0.45)
    if close:
        best = difflib.SequenceMatcher(None, wanted, close[0]).ratio()
        matches = _highest_priority(_unique_entries(
            by_name[name] for name in close
            if difflib.SequenceMatcher(None, wanted, name).ratio() >= best - 0.03
        ))
        length_ratio = min(len(wanted), len(close[0])) / max(len(wanted), len(close[0]))
        # les mots courts (« obs ») ressemblent vite à autre chose (« osu ») : on exige plus
        if best >= (0.62 if len(wanted) >= 6 else 0.8) and length_ratio >= 0.7                 and _words_match(wanted, close[0]):
            return matches, []
    return [], [by_name[name]["name"] for name in close] or [entry["name"] for entry, _ in named[:5]]


def _unique_entries(entries) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entry in entries:
        marker = id(entry)
        if marker not in seen:
            seen.add(marker)
            found.append(entry)
    return found


def _highest_priority(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        return []
    ranks = {"launcher": 0, "start_menu": 1, "windows": 2}
    best = min(ranks.get(entry.get("_source"), 0) for entry in entries)
    return [entry for entry in entries if ranks.get(entry.get("_source"), 0) == best]


def _default_start_menu_roots() -> list[Path]:
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    program_data = os.environ.get("ProgramData") or os.environ.get("PROGRAMDATA")
    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if program_data:
        roots.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    # raccourcis du Bureau (ex. Sakura Optimizer), lus sans descendre dans les sous-dossiers
    public = os.environ.get("PUBLIC")
    for desktop in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop", Path(public) / "Desktop" if public else None):
        if desktop is not None and desktop not in roots:
            roots.append(desktop)
    return roots


def _shortcut_target(path: Path) -> str | None:
    try:
        import win32com.client

        target = win32com.client.Dispatch("WScript.Shell").CreateShortCut(str(path)).Targetpath
        return target if isinstance(target, str) and target else None
    except Exception:
        return None


def _launcher_start(launch: dict[str, Any], browser: str | None) -> None:
    """Importe le moteur du Launcher sans en dupliquer le code."""
    if "url" in launch and not browser:
        os.startfile(launch["url"])
        return
    exe = launch.get("exe")
    if exe and not os.path.isabs(exe):
        # « notepad.exe » seul : le Launcher démarrerait dans un dossier vide, on donne le chemin complet
        launch = {**launch, "exe": shutil.which(exe) or exe}
    launcher_path = str(LAUNCHER_ROOT)
    if launcher_path not in sys.path:
        sys.path.insert(0, launcher_path)
    import engine

    engine.start(launch, browser)


def _volume_endpoint():
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    speakers = AudioUtilities.GetSpeakers()
    if hasattr(speakers, "EndpointVolume"):
        return speakers.EndpointVolume
    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _default_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / name for name in (
            "Desktop", "Bureau", "Documents", "Downloads", "Téléchargements",
            "Pictures", "Images", "Music", "Musique", "Videos", "Vidéos",
        )
    ]
    for one_drive in (home / "OneDrive", home / "OneDrive - Personal"):
        roots.extend((one_drive / "Desktop", one_drive / "Bureau"))
    unique: list[Path] = []
    for root in roots:
        if root.exists() and root not in unique:
            unique.append(root)
    return unique


@dataclass(frozen=True)
class Tool:
    """Définition d'un outil exposé à Ollama."""

    name: str
    description: str
    parameters: dict[str, Any]
    risky: bool
    function: Callable[..., dict[str, Any]]
    describe: Callable[[dict[str, Any]], str]
    confirm_text: Callable[[dict[str, Any]], dict[str, str]] | None = None


class ToolRegistry:
    """Registre injectable, sans effet réel pendant les tests."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], dict[str, Any]] = _load_config,
        launcher_start: Callable[[dict[str, Any], str | None], None] = _launcher_start,
        volume_endpoint: Callable[[], Any] = _volume_endpoint,
        search_roots: Callable[[], list[Path]] = _default_roots,
        start_menu_roots: Callable[[], list[Path]] = _default_start_menu_roots,
        shortcut_target: Callable[[Path], str | None] = _shortcut_target,
        monotonic: Callable[[], float] = time.monotonic,
        process_iter: Callable[..., Any] | None = None,
        wait_procs: Callable[..., Any] | None = None,
        logger: Any = None,
    ) -> None:
        self._config_loader = config_loader
        self._launcher_start = launcher_start
        self._volume_endpoint = volume_endpoint
        self._search_roots = search_roots
        self._start_menu_roots = start_menu_roots
        self._shortcut_target = shortcut_target
        self._monotonic = monotonic
        self._start_menu_cache: list[dict[str, Any]] | None = None
        self._start_menu_cache_time = 0.0
        self._process_iter = process_iter
        self._wait_procs = wait_procs
        self._logger = logger
        self._tools = {tool.name: tool for tool in self._build_tools()}

    def _build_tools(self) -> list[Tool]:
        text = {"type": "string"}
        return [
            Tool(
                "open_app", "Ouvre une application ou un jeu du Launcher, toute application installée, ou une application Windows (bloc-notes, calculatrice, paramètres…).",
                _object_schema({"name": text}, ["name"]), False, self._open_app,
                lambda args: f"{args.get('name', 'Application')} ouvert",
            ),
            Tool(
                "list_apps", "Liste les applications et jeux disponibles.",
                _object_schema({}, []), False, self._list_apps,
                lambda _args: "Applications disponibles listées",
            ),
            Tool(
                "set_volume", "Règle le volume général entre 0 et 100 %.",
                _object_schema({"percent": {"type": "number", "minimum": 0, "maximum": 100}}, ["percent"]),
                False, self._set_volume, lambda args: f"Volume réglé à {_bounded_percent(args.get('percent'))} %",
            ),
            Tool(
                "mute", "Active ou enlève le mode muet du volume général.",
                _object_schema({"on": {"type": "boolean"}}, ["on"]), False, self._mute,
                lambda args: "Son coupé" if args.get("on") else "Son réactivé",
            ),
            Tool(
                "find_files", "Cherche des fichiers par leur nom dans les dossiers personnels.",
                _object_schema({"query": text}, ["query"]), False, self._find_files,
                lambda args: f"Recherche de fichiers : {args.get('query', '')}",
            ),
            Tool(
                "close_app", "Ferme proprement une application en cours d'exécution.",
                _object_schema({"name": text}, ["name"]), True, self._close_app,
                lambda args: f"{args.get('name', 'Application')} fermé",
                lambda args: {
                    "title": f"Fermer {args.get('name', 'cette application')} ?",
                    "text": f"Ce qui n'est pas enregistré dans {args.get('name', 'cette application')} sera perdu.",
                    "yes": "Oui, ferme-le",
                    "no": "Non, laisse",
                },
            ),
        ]

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }}
            for tool in self._tools.values()
        ]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def describe(self, name: str, args: dict[str, Any]) -> str:
        tool = self.get(name)
        if tool is None:
            return name
        try:
            return tool.describe(args)
        except Exception:
            return tool.description

    def run(self, name: str, args: Any) -> dict[str, Any]:
        """Exécute un outil et transforme toute erreur en résultat français."""
        tool = self.get(name)
        safe_args = args if isinstance(args, dict) else {}
        if tool is None:
            result = {"ok": False, "message": f"Je ne connais pas l'outil {name}."}
        else:
            try:
                result = tool.function(**safe_args)
                if not isinstance(result, dict):
                    result = {"ok": True, "message": str(result)}
            except TypeError:
                result = {"ok": False, "message": "Les paramètres de cet outil sont incomplets ou invalides."}
            except Exception as exc:
                result = {"ok": False, "message": f"L'action a échoué : {exc}"}
        if self._logger is not None:
            try:
                level = self._logger.info if result.get("ok") else self._logger.error
                level(
                    "Outil %s args=%s résultat=%s",
                    name,
                    json.dumps(safe_args, ensure_ascii=False, default=str),
                    json.dumps(result, ensure_ascii=False, default=str),
                )
            except Exception:
                pass
        return result

    def _open_app(self, name: str) -> dict[str, Any]:
        config = self._config_loader()
        matches, suggestions = _matches(name, self._catalog(config))
        if len(matches) > 1:
            return {"ok": False, "message": "Plusieurs applications correspondent.", "choices": [item["name"] for item in matches]}
        if not matches:
            return {"ok": False, "message": f"Je n'ai pas trouvé « {name} ».", "suggestions": suggestions}
        entry = matches[0]
        launch = entry.get("launch")
        if not isinstance(launch, dict):
            return {"ok": False, "message": f"{entry['name']} n'a pas de commande de lancement."}
        settings = config.get("settings", {})
        browser = settings.get("browser") if isinstance(settings, dict) else None
        self._launcher_start(launch, browser if isinstance(browser, str) and browser else None)
        return {"ok": True, "message": f"{entry['name']} est ouvert.", "name": entry["name"]}

    def _list_apps(self) -> dict[str, Any]:
        config = self._config_loader()
        apps = [entry["name"] for entry in config.get("apps", []) if isinstance(entry, dict) and isinstance(entry.get("name"), str)] if isinstance(config.get("apps", []), list) else []
        games = [entry["name"] for entry in config.get("games", []) if isinstance(entry, dict) and isinstance(entry.get("name"), str)] if isinstance(config.get("games", []), list) else []
        other_apps = sorted(
            {entry["name"] for entry in self._catalog(config) if entry.get("_source") != "launcher"},
            key=_normalise,
        )[:MAX_OTHER_APPS]
        return {
            "ok": True,
            "message": f"{len(apps) + len(games) + len(other_apps)} éléments disponibles.",
            "apps": apps,
            "games": games,
            "other_apps": other_apps,
        }

    def _catalog(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        launcher = [{**entry, "_source": "launcher"} for entry in _entries(config)]
        candidates = [*launcher, *self._start_menu_entries(), *({**entry, "_source": "windows"} for entry in _WINDOWS_APPS)]
        catalog: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in candidates:
            normal = _normalise(entry["name"])
            if normal and normal not in seen:
                seen.add(normal)
                catalog.append(entry)
        return catalog

    def _start_menu_entries(self) -> list[dict[str, Any]]:
        now = self._monotonic()
        if self._start_menu_cache is not None and now - self._start_menu_cache_time <= START_MENU_CACHE_SECONDS:
            return self._start_menu_cache
        entries: list[dict[str, Any]] = []
        for root in self._start_menu_roots():
            try:
                found = root.glob("*.lnk") if root.name.lower() == "desktop" else root.rglob("*.lnk")
                shortcuts = sorted(found, key=lambda path: _normalise(path.stem)) if root.exists() else []
            except OSError:
                shortcuts = []
            for shortcut in shortcuts:
                normal = _normalise(shortcut.stem)
                if any(word in normal for word in _IGNORED_SHORTCUT_WORDS):
                    continue
                entries.append({
                    "name": shortcut.stem,
                    "launch": {"file": str(shortcut)},
                    "_source": "start_menu",
                    "_shortcut": shortcut,
                })
        self._start_menu_cache = entries
        self._start_menu_cache_time = now
        return entries

    def _set_volume(self, percent: Any) -> dict[str, Any]:
        value = _bounded_percent(percent)
        self._volume_endpoint().SetMasterVolumeLevelScalar(value / 100, None)
        return {"ok": True, "message": f"Volume réglé à {value} %.", "percent": value}

    def _mute(self, on: bool) -> dict[str, Any]:
        if not isinstance(on, bool):
            return {"ok": False, "message": "L'état muet doit être vrai ou faux."}
        self._volume_endpoint().SetMute(on, None)
        return {"ok": True, "message": "Son coupé." if on else "Son réactivé.", "muted": on}

    def _find_files(self, query: str) -> dict[str, Any]:
        words = _normalise(query).split()
        if not words:
            return {"ok": False, "message": "Indique le nom du fichier à chercher.", "files": []}
        deadline = time.monotonic() + FILE_SEARCH_SECONDS
        ignored = {"appdata", "node_modules", ".git", "__pycache__"}
        found: list[tuple[float, Path]] = []
        timed_out = False
        for root in self._search_roots():
            if time.monotonic() >= deadline:
                timed_out = True
                break
            if not root.exists():
                continue
            for current, dirs, files in os.walk(root, onerror=lambda _error: None):
                dirs[:] = [folder for folder in dirs if not folder.startswith(".") and folder.casefold() not in ignored]
                for filename in files:
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
                    if all(word in _normalise(filename) for word in words):
                        path = Path(current) / filename
                        try:
                            found.append((path.stat().st_mtime, path))
                        except OSError:
                            pass
                if timed_out:
                    break
            if timed_out:
                break
        found.sort(key=lambda item: item[0], reverse=True)
        files = [{"path": str(path), "modified": datetime.fromtimestamp(modified).isoformat(timespec="seconds")} for modified, path in found[:MAX_FILE_RESULTS]]
        return {"ok": True, "message": f"{len(files)} fichier(s) trouvé(s).", "files": files, "timed_out": timed_out}

    def _close_app(self, name: str) -> dict[str, Any]:
        import psutil

        wanted = _normalise(name)
        if not wanted:
            return {"ok": False, "message": "Indique l'application à fermer."}
        protected = {
            "explorer", "system", "registry", "wininit", "winlogon", "csrss", "services", "lsass",
            "smss", "dwm", "svchost", "fontdrvhost", "sihost", "taskhostw", "audiodg", "conhost",
            "logonui", "securityhealthservice", "memory compression", "secure system",
            "python", "pythonw", "ollama", "ollama app",
        }
        aliases: set[str] = {wanted}
        if wanted in protected or wanted.startswith("python") or wanted.startswith("ollama"):
            return {"ok": False, "message": f"Je ne peux pas fermer le processus protégé {name}."}
        config = self._config_loader()
        catalog_matches, _suggestions = _matches(name, self._catalog(config))
        if len(catalog_matches) > 1:
            return {
                "ok": False,
                "message": "Plusieurs applications correspondent.",
                "choices": [entry["name"] for entry in catalog_matches],
            }
        if catalog_matches:
            entry = catalog_matches[0]
            process = entry.get("process")
            if isinstance(process, str):
                aliases.add(_normalise(Path(process).stem))
            for process_name in entry.get("processes", []):
                if isinstance(process_name, str):
                    aliases.add(_normalise(Path(process_name).stem))
            launch = entry.get("launch", {})
            if isinstance(launch, dict) and isinstance(launch.get("exe"), str):
                aliases.add(_normalise(Path(launch["exe"]).stem))
            shortcut = entry.get("_shortcut")
            if isinstance(shortcut, Path):
                target = self._shortcut_target(shortcut)
                if target:
                    aliases.add(_normalise(Path(target).stem))
        if aliases & protected or any(alias.startswith("python") or alias.startswith("ollama") for alias in aliases):
            return {"ok": False, "message": f"Je ne peux pas fermer le processus protégé {name}."}

        iterator = self._process_iter or psutil.process_iter
        matches = []
        for process in iterator(["pid", "name", "username"]):
            try:
                process_name = process.info.get("name") if hasattr(process, "info") else process.name()
                pid = process.info.get("pid", process.pid) if hasattr(process, "info") else process.pid
                username = process.info.get("username", "") if hasattr(process, "info") else ""
                normal = _normalise(Path(process_name or "").stem)
                system_account = _normalise(username) in {
                    "nt authority system", "nt authority local service", "nt authority network service",
                    "autorite nt systeme", "autorite nt service local", "autorite nt service reseau",
                }
                if pid in {0, 4, os.getpid()} or system_account or normal in protected or normal.startswith("python") or normal.startswith("ollama"):
                    continue
                if normal in aliases:
                    matches.append(process)
            except (psutil.Error, OSError):
                continue
        if not matches:
            return {"ok": False, "message": f"{name} n'est pas en cours d'exécution."}
        for process in matches:
            try:
                process.terminate()
            except psutil.Error:
                pass
        waiter = self._wait_procs or psutil.wait_procs
        _gone, alive = waiter(matches, timeout=5)
        for process in alive:
            try:
                process.kill()
            except psutil.Error:
                pass
        return {"ok": True, "message": f"{name} a été fermé.", "processes": len(matches)}


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _bounded_percent(value: Any) -> int:
    try:
        return round(max(0.0, min(100.0, float(value))))
    except (TypeError, ValueError):
        raise ValueError("Le volume doit être un nombre entre 0 et 100.") from None


_DEFAULT = ToolRegistry()


def schemas() -> list[dict[str, Any]]:
    return _DEFAULT.schemas()


def run(name: str, args: Any) -> dict[str, Any]:
    return _DEFAULT.run(name, args)

