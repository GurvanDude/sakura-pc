"""Fenêtre simple de Sakura Optimizer."""

from __future__ import annotations

import functools
import http.server
import re
import socketserver
import threading
import time
from pathlib import Path
from typing import Any

from core import paths
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
    def __init__(self, monitor: Monitor) -> None:
        self.monitor = monitor

    def get_view(self) -> dict[str, Any]:
        status = self.monitor.get()
        if status is None:
            view = explain({})
            view["verdict"] = {"mood": "ok", "emoji": "🌸", "title": "Je regarde ton PC…", "text": "Ça prend juste un instant."}
            return {"view": view, "status": {}}
        return {"view": explain(status), "status": status}


def _serve() -> tuple[socketserver.ThreadingTCPServer, int]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def translate_path(self, path: str) -> str:
            clean = path.split("?", 1)[0].split("#", 1)[0]
            if clean == "/tokens.css":
                return str(REPO / "design" / "tokens.css")
            if clean == "/logo.png":
                return str(REPO / "design" / "logo" / "optimizer.png")
            return str(ROOT / "ui" / (clean.lstrip("/") or "index.html"))

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
    server, port = _serve()
    monitor = Monitor()
    window = webview.create_window(
        "Sakura Optimizer", f"http://127.0.0.1:{port}/index.html", js_api=Api(monitor),
        width=1000, height=720, min_size=(760, 600), resizable=True,
        background_color=_token("cream", "white"),
    )
    window.events.shown += functools.partial(_set_icon, window)
    try:
        webview.start(gui="edgechromium", debug=debug, private_mode=False, storage_path=str(paths.USER / ".webview"))
    finally:
        server.shutdown()
        server.server_close()
