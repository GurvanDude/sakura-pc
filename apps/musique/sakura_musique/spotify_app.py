"""Démarrage discret de Spotify et choix de l'appareil de ce PC."""

from __future__ import annotations

import csv
import ctypes
import io
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .api import SpotifyApiError

SW_HIDE = 0
SW_SHOW = 5


def _spotify_pids() -> set[int]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Spotify.exe", "/FO", "CSV", "/NH"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                check=False, creationflags=flags)
    except OSError:
        return set()
    pids: set[int] = set()
    for row in csv.reader(io.StringIO(result.stdout)):
        if len(row) > 1 and row[0].lower() == "spotify.exe":
            try:
                pids.add(int(row[1]))
            except ValueError:
                pass
    return pids


def _set_windows(pids: set[int], command: int, *, visible_only: bool = False) -> int:
    if os.name != "nt" or not pids:
        return 0
    user32 = ctypes.windll.user32
    count = 0
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd: int, _param: int) -> bool:
        nonlocal count
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and (not visible_only or user32.IsWindowVisible(hwnd)):
            user32.ShowWindow(hwnd, command)
            count += 1
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return count


def launch_hidden(*, sleep: Callable[[float], Any] = time.sleep, duration: float = 10.0) -> bool:
    """Lance Spotify réduit puis masque ses fenêtres visibles pendant son démarrage."""
    executable = Path(os.environ.get("APPDATA", "")) / "Spotify" / "Spotify.exe"
    try:
        if executable.is_file():
            subprocess.Popen([str(executable), "--minimized"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.startfile("spotify:")  # type: ignore[attr-defined]
    except OSError as error:
        raise SpotifyApiError("Je n’arrive pas à lancer Spotify sur ce PC.") from error
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        _set_windows(_spotify_pids(), SW_HIDE, visible_only=True)
        sleep(0.25)
    return True


def show_spotify() -> bool:
    """Réaffiche les fenêtres Spotify existantes, sans démarrer ni fermer Spotify."""
    return bool(_set_windows(_spotify_pids(), SW_SHOW))


def _computer(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((item for item in items if str(item.get("type", "")).lower() == "computer"), None)


def ensure_device(api: Any, *, launcher: Callable[[], Any] = launch_hidden,
                  sleep: Callable[[float], Any] = time.sleep, timeout: float = 20.0) -> dict[str, Any]:
    """Renvoie un appareil actif, ou réveille et sélectionne Spotify sur ce PC."""
    available = api.devices()
    active = next((item for item in available if item.get("is_active")), None)
    if active:
        return active
    computer = _computer(available)
    if computer:
        api.transfer(computer["id"], play=False)
        return computer
    launcher()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        computer = _computer(api.devices())
        if computer:
            api.transfer(computer["id"], play=False)
            return computer
        sleep(0.5)
    raise SpotifyApiError("Spotify s’est lancé, mais son lecteur n’est pas encore prêt.")
