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
from urllib.parse import parse_qs, unquote, urlsplit

from core import paths
from core import window as sk_window
from sakura_opt.diagnose import run_diagnosis
from sakura_opt.explain import explain, history_view
from sakura_opt.history import History
from sakura_opt.history_mutex import acquire_history_mutex
from sakura_opt.names import add_friendly_names
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

    def __init__(
        self,
        sampler: Sampler | None = None,
        history: History | None = None,
        mutex_factory: Callable[[], Any | None] = acquire_history_mutex,
        *,
        start: bool = True,
    ) -> None:
        self.sampler = sampler or Sampler()
        self.history = history or History()
        self._mutex_factory = mutex_factory
        self._history_mutex: Any | None = None
        self._next_history = 0.0
        self._next_mutex_attempt = 0.0
        self._stop = threading.Event()
        self.latest: dict[str, Any] | None = None
        self._lock = threading.Lock()
        if start:
            threading.Thread(target=self._run, daemon=True, name="optimizer-sampler").start()
            threading.Thread(
                target=self._history_run, daemon=True, name="optimizer-history"
            ).start()

    def _run(self) -> None:
        while not self._stop.is_set():
            status = self.sampler.sample()
            add_friendly_names(status)
            with self._lock:
                self.latest = status
            self._stop.wait(1.5)

    def _history_run(self) -> None:
        while not self._stop.is_set():
            status = self.get()
            if status is not None:
                self._record_history(status)
            self._stop.wait(5.0)

    def _record_history(self, status: dict[str, Any], now: float | None = None) -> None:
        """Enregistre seulement si la fenêtre possède le mutex partagé."""
        if self._stop.is_set():
            return
        current = time.monotonic() if now is None else now
        if self._history_mutex is None and current >= self._next_mutex_attempt:
            self._history_mutex = self._mutex_factory()
            self._next_mutex_attempt = current + 30.0
        if self._history_mutex is not None and current >= self._next_history:
            try:
                self.history.record(status, status.get("temps"))
            except Exception:
                pass
            self._next_history = current + 5.0

    def close(self) -> None:
        self._stop.set()
        if self._history_mutex is not None:
            self._history_mutex.close()
            self._history_mutex = None

    def get(self) -> dict[str, Any] | None:
        with self._lock:
            return self.latest


class Api:
    HISTORY_PERIODS = {
        "15m": (15 * 60, "les 15 dernières minutes"),
        "1h": (60 * 60, "la dernière heure"),
        "6h": (6 * 60 * 60, "les 6 dernières heures"),
        "24h": (24 * 60 * 60, "les dernières 24 heures"),
        "7j": (7 * 24 * 60 * 60, "les 7 derniers jours"),
    }

    def __init__(
        self,
        monitor: Monitor,
        *,
        theme_path: Path | None = None,
        config_path: Path | None = None,
        opener: Callable[[str], Any] | None = None,
        history: History | None = None,
    ) -> None:
        self._monitor = monitor
        self._window: Any | None = None
        self._maximized = False
        self._theme_path = Path(theme_path) if theme_path is not None else paths.USER / "optimizer.json"
        self._config_path = Path(config_path) if config_path is not None else paths.CONFIG
        self._opener = opener or _open_windows_settings
        self._history = history or History()
        self._preferences_lock = threading.Lock()

    def _preferences(self) -> dict[str, Any]:
        try:
            value = json.loads(self._theme_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_preference(self, key: str, value: str) -> None:
        with self._preferences_lock:
            preferences = self._preferences()
            preferences[key] = value
            self._theme_path.parent.mkdir(parents=True, exist_ok=True)
            self._theme_path.write_text(
                json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8"
            )

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
        theme = self._preferences().get("theme")
        if theme in ("day", "night"):
            return theme
        return _launcher_theme(self._config_path)

    def set_theme(self, theme: str) -> str:
        clean = "night" if theme == "night" else "day"
        self._save_preference("theme", clean)
        return clean

    def get_history_period(self) -> str:
        period = self._preferences().get("history_period")
        return period if period in self.HISTORY_PERIODS else "1h"

    def set_history_period(self, period: str) -> str:
        clean = period if period in self.HISTORY_PERIODS else "1h"
        self._save_preference("history_period", clean)
        return clean

    def get_history(self, period: str) -> dict[str, Any]:
        clean = period if period in self.HISTORY_PERIODS else "1h"
        seconds, label = self.HISTORY_PERIODS[clean]
        series = self._history.query(seconds)
        summary = self._history.summary(seconds)
        return {"series": series, "view": history_view(series, summary, label)}

    def diagnose(self, minutes: int | float | str = 5) -> dict[str, Any]:
        """Analyse immédiatement l'historique et la dernière mesure disponible."""
        try:
            duration = max(1.0, min(60.0, float(minutes)))
        except (TypeError, ValueError, OverflowError):
            duration = 5.0
        return run_diagnosis(
            duration,
            history=self._history,
            status=self._monitor.get(),
        )

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
            request = urlsplit(self.path)
            request_path = unquote(request.path)
            if request_path == "/api/view":
                payload = json.dumps(api.get_view(), ensure_ascii=False).encode("utf-8")
                self._headers(200, "application/json; charset=utf-8", len(payload))
                self.wfile.write(payload)
                return
            if request_path == "/api/history":
                period = parse_qs(request.query).get("period", ["1h"])[0]
                payload = json.dumps(api.get_history(period), ensure_ascii=False).encode("utf-8")
                self._headers(200, "application/json; charset=utf-8", len(payload))
                self.wfile.write(payload)
                return
            if request_path == "/api/diagnose":
                minutes = parse_qs(request.query).get("minutes", ["5"])[0]
                payload = json.dumps(api.diagnose(minutes), ensure_ascii=False).encode("utf-8")
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
        monitor.close()
        server.shutdown()
        server.server_close()
