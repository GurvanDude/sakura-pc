"""Fenêtre de conversation de Sakura AI."""

from __future__ import annotations

import functools
import http.server
import json
import logging
import re
import socketserver
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from core import paths
from sakura_ai import brain
from sakura_ai.history import ChatHistory

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
UI_ROOT = (ROOT / "ui").resolve()
DESIGN_ROOT = (REPO / "design").resolve()


def _token(name: str, fallback: str) -> str:
    try:
        css = (REPO / "design" / "tokens.css").read_text(encoding="utf-8")
        match = re.search(rf"--{re.escape(name)}\s*:\s*([^;]+)", css)
        return match.group(1).strip() if match else fallback
    except OSError:
        return fallback


def _logger() -> logging.Logger:
    logger = logging.getLogger("sakura.ai")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(paths.log("ai"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


class Api:
    """Fonctions accessibles depuis l'interface."""

    # Attributs privés (_) : pywebview explore tout attribut public du js_api,
    # et se perd dans la fenêtre native si on lui en donne une.

    def __init__(self, history: ChatHistory | None = None, logger: logging.Logger | None = None) -> None:
        self._chat = history or ChatHistory()
        self._logger = logger or _logger()
        self._window: Any = None
        self._maximized = False
        self._lock = threading.Lock()
        self._busy = False
        self._stop = threading.Event()

    def status(self) -> dict[str, Any]:
        ok, message = brain.is_ready()
        return {"ok": ok, "message": message}

    def history(self) -> list[dict[str, str]]:
        return list(self._chat.messages)

    def send(self, text: str) -> dict[str, Any]:
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            return {"ok": False, "message": "Écris d'abord un message."}
        with self._lock:
            if self._busy:
                return {"ok": False, "message": "Sakura répond déjà."}
            self._busy = True
            self._stop.clear()
            try:
                self._chat.append("user", text)
                messages = list(self._chat.messages)
            except OSError:
                self._busy = False
                self._logger.exception("Impossible d'enregistrer un nouveau message")
                return {"ok": False, "message": "Le message n'a pas pu être enregistré. Réessaie."}
        threading.Thread(
            target=self._answer,
            args=(messages,),
            daemon=True,
            name="sakura-ai-answer",
        ).start()
        return {"ok": True}

    def stop(self) -> dict[str, bool]:
        self._stop.set()
        return {"ok": True}

    def new_chat(self) -> dict[str, Any]:
        with self._lock:
            if self._busy:
                return {"ok": False, "message": "Arrête d'abord la réponse en cours."}
            try:
                self._chat.clear()
            except OSError:
                self._logger.exception("Impossible de vider la conversation")
                return {"ok": False, "message": "La discussion n'a pas pu être effacée. Réessaie."}
        return {"ok": True}

    def minimize(self) -> None:
        if self._window is not None:
            self._window.minimize()

    def toggle_maximize(self) -> None:
        if self._window is None:
            return
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized

    def close(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def _js(self, function: str, value: str | None = None) -> None:
        if self._window is None:
            return
        argument = "" if value is None else json.dumps(value, ensure_ascii=False)
        self._window.evaluate_js(f"{function}({argument})")

    def _answer(self, messages: list[dict[str, str]]) -> None:
        started = time.monotonic()
        pending: list[str] = []
        last_flush = 0.0

        def flush() -> None:
            nonlocal last_flush
            if pending:
                self._js("onChunk", "".join(pending))
                pending.clear()
                last_flush = time.monotonic()

        def receive(chunk: str) -> None:
            pending.append(chunk)
            if time.monotonic() - last_flush >= 0.05:
                flush()

        answer = ""
        try:
            answer = brain.chat_stream(messages, receive, self._stop)
            flush()
            if answer:
                self._chat.append("assistant", answer)
            self._js("onDone")
            duration = time.monotonic() - started
            self._logger.info("Réponse terminée en %.2f s%s", duration, " (arrêtée)" if self._stop.is_set() else "")
        except Exception as exc:
            flush()
            message = str(exc) if isinstance(exc, brain.OllamaError) else "Un souci inattendu est arrivé. Réessaie."
            self._logger.exception("Erreur pendant une réponse")
            self._js("onError", message)
        finally:
            with self._lock:
                self._busy = False


def _serve() -> tuple[socketserver.ThreadingTCPServer, int]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            pass

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def translate_path(self, path: str) -> str:
            clean = unquote(urlsplit(path).path)
            if clean.startswith("/design/"):
                base = DESIGN_ROOT
                relative = clean.removeprefix("/design/")
            else:
                base = UI_ROOT
                relative = clean.lstrip("/") or "index.html"

            candidate = (base / relative).resolve()
            try:
                candidate.relative_to(base)
            except ValueError:
                return str(UI_ROOT / "__not_found__")
            return str(candidate)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="sakura-ai-ui").start()
    return server, server.server_address[1]


def _set_icon(window: Any) -> None:
    try:
        import ctypes

        icon = str(REPO / "design" / "logo" / "ico" / "ai.ico")
        hwnd = window.native.Handle.ToInt32()
        handle = ctypes.windll.user32.LoadImageW(None, icon, 1, 0, 0, 0x10)
        if handle:
            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 0, handle)
            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 1, handle)
    except Exception:
        pass


def run(debug: bool = False) -> None:
    import webview

    logger = _logger()
    logger.info("Démarrage de Sakura AI")
    server, port = _serve()
    api = Api(logger=logger)
    window = webview.create_window(
        "Sakura AI",
        f"http://127.0.0.1:{port}/index.html",
        js_api=api,
        width=900,
        height=780,
        min_size=(620, 560),
        resizable=True,
        frameless=True,
        easy_drag=False,
        background_color=_token("night", "#140818"),
    )
    api._window = window
    window.events.shown += functools.partial(_set_icon, window)
    try:
        webview.start(
            gui="edgechromium",
            debug=debug,
            private_mode=False,
            storage_path=str(paths.USER / ".webview"),
        )
    finally:
        server.shutdown()
        server.server_close()

