"""Fenêtre Sakura de l'Optimizer et serveur local de son interface."""

from __future__ import annotations

import datetime as dt
import functools
import http.server
import json
import mimetypes
import os
import re
import socketserver
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from core import paths
from core import window as sk_window
from sakura_opt.explain import explain
from sakura_opt.names import friendly_name
from sakura_opt.sensors import Sampler

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def _token(name: str, fallback: str) -> str:
    """Lit une couleur commune sans la recopier dans l'application."""
    try:
        css = (REPO / "design" / "tokens.css").read_text(encoding="utf-8")
        match = re.search(rf"--{re.escape(name)}\s*:\s*([^;]+)", css)
        return match.group(1).strip() if match else fallback
    except OSError:
        return fallback


def _launcher_theme(config_path: Path) -> str:
    """Déduit le mode actuel des horaires configurés dans le Launcher."""
    try:
        settings = json.loads(config_path.read_text(encoding="utf-8"))["settings"]
        start = int(settings["day_start"])
        end = int(settings["day_end"])
        hour = dt.datetime.now().hour
        is_day = start <= hour < end if start <= end else hour >= start or hour < end
        return "day" if is_day else "night"
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return "day"


def _open_windows_settings(uri: str) -> None:
    """Retarde l'accès à l'API Windows pour garder l'Api testable ailleurs."""
    os.startfile(uri)


class Monitor:
    """Échantillonne en fond avec un seul Sampler partagé."""

    def __init__(self, sampler: Sampler | None = None) -> None:
        self.sampler = sampler or Sampler()
        self.latest: dict[str, Any] | None = None
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True, name="optimizer-sampler").start()

    def _run(self) -> None:
        while True:
            status = self.sampler.sample()
            self._add_names(status)
            with self._lock:
                self.latest = status
            time.sleep(1.5)

    @staticmethod
    def _add_names(status: dict[str, Any]) -> None:
        """Fait les lectures de noms dans le thread de fond, jamais dans get_view."""
        known: dict[int, str] = {}
        for key in ("top_cpu", "top_ram"):
            rows = status.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    pid = int(row["pid"])
                    if pid not in known:
                        known[pid] = friendly_name(pid, str(row.get("name") or "Programme"))
                    row["friendly_name"] = known[pid]
                except (KeyError, TypeError, ValueError):
                    continue

    def get(self) -> dict[str, Any] | None:
        with self._lock:
            return self.latest


class Api:
    def __init__(
        self,
        monitor: Monitor,
        *,
        theme_path: Path | None = None,
        config_path: Path | None = None,
        opener: Callable[[str], Any] | None = None,
    ) -> None:
        self._monitor = monitor
        self._window: Any | None = None
        self._maximized = False
        self._theme_path = Path(theme_path) if theme_path is not None else paths.USER / "optimizer.json"
        self._config_path = Path(config_path) if config_path is not None else paths.CONFIG
        self._opener = opener or _open_windows_settings

    def get_view(self) -> dict[str, Any]:
        status = self._monitor.get()
        if status is None:
            view = explain({})
            view["verdict"] = {
                "mood": "ok", "emoji": "🌸", "title": "Je regarde ton PC…",
                "text": "Ça prend juste un instant.",
            }
            return {"view": view, "status": {}}
        return {"view": explain(status), "status": status}

    def minimize(self) -> None:
        if self._window is not None:
            self._window.minimize()

    def toggle_maximize(self) -> None:
        if self._window is None:
            return
        if self._maximized:
            sk_window.restore(self._window)
        else:
            sk_window.maximize(self._window)
        self._maximized = not self._maximized

    def close(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def get_theme(self) -> str:
        try:
            theme = json.loads(self._theme_path.read_text(encoding="utf-8")).get("theme")
            if theme in ("day", "night"):
                return theme
        except (OSError, AttributeError, json.JSONDecodeError):
            pass
        return _launcher_theme(self._config_path)

    def set_theme(self, theme: str) -> str:
        clean = "night" if theme == "night" else "day"
        self._theme_path.parent.mkdir(parents=True, exist_ok=True)
        self._theme_path.write_text(
            json.dumps({"theme": clean}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return clean

    def free_space(self) -> None:
        """Ouvre les réglages Windows sans supprimer le moindre fichier."""
        self._opener("ms-settings:storagesense")


def _serve(api: Api) -> tuple[socketserver.ThreadingTCPServer, int]:
    routes = {
        "/": ROOT / "ui" / "index.html",
        "/index.html": ROOT / "ui" / "index.html",
        "/app.js": ROOT / "ui" / "app.js",
        "/style.css": ROOT / "ui" / "style.css",
        "/design/tokens.css": REPO / "design" / "tokens.css",
        "/design/ui/sakura.css": REPO / "design" / "ui" / "sakura.css",
        "/design/ui/sakura.js": REPO / "design" / "ui" / "sakura.js",
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
            request_path = unquote(urlsplit(self.path).path)
            if request_path == "/api/view":
                payload = json.dumps(api.get_view(), ensure_ascii=False).encode("utf-8")
                self._headers(200, "application/json; charset=utf-8", len(payload))
                self.wfile.write(payload)
                return
            file_path = routes.get(request_path)
            if file_path is None:
                self.send_error(404)
                return
            try:
                payload = file_path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self._headers(200, f"{content_type}; charset=utf-8", len(payload))
            self.wfile.write(payload)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="optimizer-ui").start()
    return server, server.server_address[1]


def _set_icon(window: Any) -> None:
    try:
        import ctypes
        icon = str(REPO / "design" / "logo" / "ico" / "optimizer.ico")
        hwnd = window.native.Handle.ToInt32()
        handle = ctypes.windll.user32.LoadImageW(None, icon, 1, 0, 0, 0x10)
        if handle:
            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 0, handle)
            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 1, handle)
    except Exception:
        pass


def run(debug: bool = False) -> None:
    import webview
    # pythonnet (clr) doit être chargé ici, dans le fil principal : sinon le moniteur et pywebview le chargent
    # en même temps et pywebview tombe sur un module à moitié prêt (« clr has no attribute AddReference »)
    import clr  # noqa: F401
    monitor = Monitor()
    api = Api(monitor)
    server, port = _serve(api)
    window = webview.create_window(
        "Sakura Optimizer", f"http://127.0.0.1:{port}/index.html", js_api=api,
        width=1000, height=720, min_size=(760, 600), resizable=True,
        frameless=True, easy_drag=False, background_color=_token("cream", "white"),
    )
    api._window = window
    window.events.shown += functools.partial(_set_icon, window)
    try:
        webview.start(
            gui="edgechromium", debug=debug, private_mode=False,
            storage_path=str(paths.USER / ".webview"),
        )
    finally:
        server.shutdown()
        server.server_close()
