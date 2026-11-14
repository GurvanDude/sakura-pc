"""Noms simples des programmes affichés dans l'interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import psutil


_WINDOWS_PROCESSES = {
    "system", "registry", "memcompression", "svchost", "dwm", "csrss",
    "lsass", "services", "wininit", "smss", "wmiprvse", "explorer",
    "searchhost", "runtimebroker", "audiodg", "fontdrvhost", "conhost",
    "sihost", "taskhostw", "ctfmon", "startmenuexperiencehost",
    "shellexperiencehost", "securityhealthservice", "spoolsv", "winlogon",
}
_PATH_NAMES: dict[str, str] = {}


def _plain_name(exe_name: str | None) -> str:
    name = Path(exe_name or "Programme").name
    return name[:-4] if name.lower().endswith(".exe") else name


def _is_windows(name: str | None) -> bool:
    return _plain_name(name).lower() in _WINDOWS_PROCESSES


def friendly_name(pid: int, exe_name: str) -> str:
    """Renvoie la description Windows de l'exécutable, avec un repli lisible."""
    if _is_windows(exe_name):
        return "Windows"
    try:
        path = psutil.Process(pid).exe()
    except (psutil.Error, OSError, ValueError, TypeError):
        return _plain_name(exe_name)
    if not path:
        return _plain_name(exe_name)

    key = str(Path(path)).casefold()
    if key in _PATH_NAMES:
        return _PATH_NAMES[key]
    result = _plain_name(exe_name)
    try:
        import win32api

        language = win32api.GetFileVersionInfo(path, r"\VarFileInfo\Translation")
        translations = language or [(0x0409, 1200)]
        for lang, codepage in translations:
            prefix = rf"\StringFileInfo\{lang:04x}{codepage:04x}"
            for field in ("FileDescription", "ProductName"):
                try:
                    value = win32api.GetFileVersionInfo(path, prefix + "\\" + field)
                except Exception:
                    continue
                if isinstance(value, str) and value.strip():
                    result = value.strip()
                    raise StopIteration
    except StopIteration:
        pass
    except Exception:
        pass
    _PATH_NAMES[key] = result
    return result


def _fr(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _fr_percent(value: float) -> str:
    digits = 0 if value.is_integer() else 1
    return _fr(value, digits)


def group_apps(
    status: dict[str, Any], name_reader: Callable[[int, str], str] | None = None
) -> list[dict[str, Any]]:
    """Fusionne les classements CPU et mémoire en six applications maximum."""
    reader = name_reader or friendly_name
    by_pid: dict[int, dict[str, Any]] = {}
    for key in ("top_cpu", "top_ram"):
        rows = status.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                pid = int(row.get("pid"))
            except (TypeError, ValueError):
                continue
            current = by_pid.setdefault(pid, {"pid": pid, "name": row.get("name") or "Programme"})
            if row.get("friendly_name"):
                current["friendly_name"] = str(row["friendly_name"])
            current["cpu_percent"] = max(float(current.get("cpu_percent", 0)), float(row.get("cpu_percent") or 0))
            current["ram_mb"] = max(float(current.get("ram_mb", 0)), float(row.get("ram_mb") or 0))

    grouped: dict[str, dict[str, float]] = {}
    for row in by_pid.values():
        raw = str(row["name"])
        name = "Windows" if _is_windows(raw) else row.get("friendly_name") or reader(row["pid"], raw)
        item = grouped.setdefault(name or _plain_name(raw), {"cpu": 0.0, "ram_mb": 0.0})
        item["cpu"] += row.get("cpu_percent", 0.0)
        item["ram_mb"] += row.get("ram_mb", 0.0)

    ram = status.get("ram") if isinstance(status.get("ram"), dict) else {}
    total_mb = float(ram.get("total_gb") or 0) * 1024
    result = []
    for name, values in grouped.items():
        cpu, ram_mb = values["cpu"], values["ram_mb"]
        ram_share = ram_mb / total_mb * 100 if total_mb else ram_mb / 1024
        ram_gb = ram_mb / 1024
        if cpu >= 25 and cpu >= ram_share:
            what = "utilise beaucoup le processeur"
        elif ram_gb >= 1:
            what = "utilise beaucoup de mémoire"
        elif cpu >= 8:
            what = "fait travailler le processeur"
        elif ram_mb >= 400:
            what = "prend un peu de mémoire"
        else:
            what = "presque rien"
        result.append({
            "name": name,
            "cpu_percent": round(cpu, 1),
            "ram_percent": round(ram_share, 1) if total_mb else 0.0,
            "ram_gb": round(ram_gb, 1),
            "cpu_text": f"{_fr_percent(cpu)} % du processeur",
            "ram_text": f"{_fr(ram_gb)} Go de mémoire",
            "what": what,
            "_weight": cpu + ram_share,
        })
    busiest = max(
        (item for item in result if item["name"] != "Windows"),
        key=lambda item: item["cpu_percent"],
        default=None,
    )
    if busiest is not None:
        busiest["what"] = "c'est lui qui travaille le plus"
    result.sort(key=lambda item: item["_weight"], reverse=True)
    for item in result:
        item.pop("_weight", None)
    return result[:6]
