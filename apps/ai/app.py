"""Fenêtre de conversation de Sakura AI."""

from __future__ import annotations

import functools
import http.server
import json
import logging
import os
import re
import socketserver
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from core import paths
from core import window as sk_window
from sakura_ai import brain
from sakura_ai import voice
from sakura_ai.history import ChatHistory, ChatStore
from sakura_ai.tools import Tool, ToolRegistry

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
UI_ROOT = (ROOT / "ui").resolve()
DESIGN_ROOT = (REPO / "design").resolve()
CONFIRM_TIMEOUT = 120.0
VOICE_DEFAULTS = {"enabled": False, "auto_send": True}

voice.vendor_path()


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


def _voice_settings() -> dict[str, bool]:
    settings = dict(VOICE_DEFAULTS)
    try:
        if not paths.CONFIG.exists():
            return settings
        payload = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return settings
    if not isinstance(payload, dict):
        return settings
    ai = payload.get("ai")
    configured = ai.get("voice") if isinstance(ai, dict) else None
    if isinstance(configured, dict):
        if isinstance(configured.get("enabled"), bool):
            settings["enabled"] = configured["enabled"]
        if isinstance(configured.get("auto_send"), bool):
            settings["auto_send"] = configured["auto_send"]
    return settings


def _write_voice_settings(settings: dict[str, bool]) -> bool:
    try:
        if paths.CONFIG.exists():
            payload = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False
        else:
            payload = {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    ai = payload.get("ai")
    if not isinstance(ai, dict):
        ai = {}
        payload["ai"] = ai
    ai["voice"] = {
        "enabled": bool(settings.get("enabled", False)),
        "auto_send": bool(settings.get("auto_send", True)),
    }
    temporary = paths.CONFIG.with_name(f"{paths.CONFIG.name}.{os.getpid()}.tmp")
    try:
        paths.CONFIG.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, paths.CONFIG)
        return True
    except OSError:
        temporary.unlink(missing_ok=True)
        return False


class Api:
    """Fonctions accessibles depuis l'interface."""

    # Attributs privés (_) : pywebview explore tout attribut public du js_api,
    # et se perd dans la fenêtre native si on lui en donne une.

    def __init__(
        self,
        history: ChatHistory | None = None,
        logger: logging.Logger | None = None,
        store: ChatStore | None = None,
        listener: Any = None,
        speaker: Any = None,
    ) -> None:
        if history is not None:
            self._store = history._store
            self._current_id = history._id
        else:
            self._store = store or ChatStore(logger=logger)
            listed = self._store.list()
            self._current_id = listed[0]["id"] if listed else self._store.create()["id"]
        self._logger = logger or _logger()
        self._window: Any = None
        self._maximized = False
        self._lock = threading.Lock()
        self._busy = False
        self._stop = threading.Event()
        self._tools = ToolRegistry(logger=self._logger)
        self._confirmations: dict[str, dict[str, Any]] = {}
        self._confirm_sequence = 0
        self._voice_settings = _voice_settings()
        self._listener = listener
        self._speaker = speaker
        self._listening = False

    def status(self) -> dict[str, Any]:
        ok, message = brain.is_ready()
        return {"ok": ok, "message": message}

    def voice_status(self) -> dict[str, Any]:
        return voice.status()

    def voice_settings(self) -> dict[str, bool]:
        return dict(self._voice_settings)

    def set_voice(self, enabled: bool) -> dict[str, Any]:
        wanted = bool(enabled)
        if wanted:
            available = voice.status()
            if not available["tts"]:
                return {"ok": False, "message": available["message"], **self.voice_settings()}
        updated = {**self._voice_settings, "enabled": wanted}
        if not _write_voice_settings(updated):
            return {
                "ok": False,
                "message": "Le réglage de voix n'a pas pu être enregistré.",
                **self.voice_settings(),
            }
        self._voice_settings = updated
        if not wanted:
            self._stop_speaker()
        return {"ok": True, **self.voice_settings()}

    def listen_start(self) -> dict[str, Any]:
        available = voice.status()
        if not available["stt"]:
            return {"ok": False, "message": available["message"]}
        with self._lock:
            if self._listening:
                return {"ok": False, "message": "Je t'écoute déjà."}
            self._listening = True
            if self._listener is None:
                self._listener = voice.Listener()
        self._js("onListen", {"state": "listening"})
        self._logger.info("Début de l'écoute")
        threading.Thread(
            target=self._listen,
            daemon=True,
            name="sakura-ai-listener",
        ).start()
        return {"ok": True}

    def listen_stop(self) -> dict[str, bool]:
        with self._lock:
            listener = self._listener if self._listening else None
        if listener is not None:
            listener.stop()
        return {"ok": True}

    def history(self) -> list[dict[str, str]]:
        try:
            return list(self._store.load(self._current_id)["messages"])
        except (OSError, ValueError, FileNotFoundError):
            return []

    def chats(self) -> list[dict[str, str]]:
        return self._store.list()

    def current(self) -> str:
        return self._current_id

    def open_chat(self, chat_id: str) -> dict[str, Any]:
        self._stop_speaker()
        with self._lock:
            if self._busy:
                return {"ok": False, "message": "Arrête d'abord la réponse en cours."}
            try:
                chat = self._store.load(chat_id)
            except (OSError, ValueError, FileNotFoundError):
                return {"ok": False, "message": "Cette discussion est introuvable."}
            self._current_id = chat["id"]
        return {"ok": True, "id": chat["id"], "messages": chat["messages"]}

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
                chat_id = self._current_id
                before = self._store.load(chat_id)["messages"]
                first_question = text if not before else None
                chat = self._store.append(chat_id, "user", text)
                messages = list(chat["messages"])
            except OSError:
                self._busy = False
                self._logger.exception("Impossible d'enregistrer un nouveau message")
                return {"ok": False, "message": "Le message n'a pas pu être enregistré. Réessaie."}
        threading.Thread(
            target=self._answer,
            args=(messages, chat_id, first_question),
            daemon=True,
            name="sakura-ai-answer",
        ).start()
        return {"ok": True}

    def stop(self) -> dict[str, bool]:
        self._stop.set()
        self._stop_speaker()
        with self._lock:
            for pending in self._confirmations.values():
                pending["event"].set()
        self._js("onCancelConfirm")
        return {"ok": True}

    def answer_confirm(self, confirmation_id: str, accepted: bool) -> dict[str, bool]:
        """Reçoit la réponse d'une confirmation intégrée à la bulle."""
        with self._lock:
            pending = self._confirmations.get(str(confirmation_id))
            if pending is None:
                return {"ok": False}
            pending["accepted"] = bool(accepted)
            pending["event"].set()
        return {"ok": True}

    def new_chat(self) -> dict[str, Any]:
        self._stop_speaker()
        with self._lock:
            if self._busy:
                return {"ok": False, "message": "Arrête d'abord la réponse en cours."}
            try:
                if not self._store.load(self._current_id)["messages"]:
                    self._store.delete(self._current_id)
            except (OSError, ValueError, FileNotFoundError):
                pass
            chat = self._store.create()
            self._current_id = chat["id"]
        self._logger.info("Nouvelle discussion préparée id=%s", chat["id"])
        return {"ok": True, "id": chat["id"], "messages": []}

    def rename_chat(self, chat_id: str, title: str) -> dict[str, Any]:
        title = title.strip() if isinstance(title, str) else ""
        if not title:
            return {"ok": False, "message": "Donne un titre à la discussion."}
        try:
            chat = self._store.rename(chat_id, title)
        except (OSError, ValueError, FileNotFoundError):
            return {"ok": False, "message": "La discussion n'a pas pu être renommée."}
        self._logger.info("Discussion renommée id=%s", chat_id)
        return {"ok": True, "title": chat["title"]}

    def delete_chat(self, chat_id: str) -> dict[str, Any]:
        with self._lock:
            if self._busy and chat_id == self._current_id:
                return {"ok": False, "message": "Arrête d'abord la réponse en cours."}
            try:
                self._store.load(chat_id)
                self._store.delete(chat_id)
            except (OSError, ValueError, FileNotFoundError):
                return {"ok": False, "message": "La discussion n'a pas pu être supprimée."}
            self._logger.info("Discussion mise à la corbeille id=%s", chat_id)
            if chat_id == self._current_id:
                listed = self._store.list()
                if listed:
                    self._current_id = listed[0]["id"]
                    messages = self._store.load(self._current_id)["messages"]
                else:
                    chat = self._store.create()
                    self._current_id = chat["id"]
                    messages = []
            else:
                messages = self._store.load(self._current_id)["messages"]
        return {"ok": True, "id": self._current_id, "messages": messages}

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

    def _js(self, function: str, *values: Any) -> None:
        if self._window is None:
            return
        arguments = ", ".join(json.dumps(value, ensure_ascii=False) for value in values)
        self._window.evaluate_js(f"{function}({arguments})")

    def _confirm(self, tool: Tool, args: dict[str, Any]) -> bool:
        """Affiche la confirmation et attend sa réponse sans bloquer l'interface."""
        if tool.confirm_text is None or self._stop.is_set():
            return False
        with self._lock:
            self._confirm_sequence += 1
            confirmation_id = str(self._confirm_sequence)
            pending = {"event": threading.Event(), "accepted": None}
            self._confirmations[confirmation_id] = pending
        self._js("onConfirm", confirmation_id, tool.confirm_text(args))
        deadline = time.monotonic() + CONFIRM_TIMEOUT
        while not self._stop.is_set() and time.monotonic() < deadline:
            if pending["event"].wait(min(0.1, max(0.0, deadline - time.monotonic()))):
                break
        with self._lock:
            self._confirmations.pop(confirmation_id, None)
        accepted = bool(pending["accepted"]) and not self._stop.is_set()
        if pending["accepted"] is None:
            decision = "délai" if not self._stop.is_set() else "arrêt"
            self._js("onCancelConfirm")
        else:
            decision = "oui" if accepted else "non"
        self._logger.info(
            "Confirmation %s outil=%s args=%s",
            decision,
            tool.name,
            json.dumps(args, ensure_ascii=False),
        )
        if not accepted:
            self._logger.error(
                "Outil %s args=%s résultat=%s",
                tool.name,
                json.dumps(args, ensure_ascii=False),
                json.dumps({"ok": False, "message": "Gurvan a refusé."}, ensure_ascii=False),
            )
        return accepted

    def _on_action(self, text: str) -> None:
        self._js("onAction", text)

    def _stop_speaker(self) -> None:
        if self._speaker is not None:
            self._speaker.stop()

    def _speak(self, text: str) -> None:
        spoken = voice.clean_for_speech(text)
        if not spoken:
            return
        if self._speaker is None:
            self._speaker = voice.Speaker(on_error=self._speaker_error)
        self._speaker.speak(spoken)

    def _speaker_error(self, error: Exception) -> None:
        self._logger.error(
            "Erreur pendant la synthèse vocale",
            exc_info=(type(error), error, error.__traceback__),
        )

    def _listen(self) -> None:
        transcription_started: float | None = None

        def transcribing() -> None:
            nonlocal transcription_started
            transcription_started = time.monotonic()
            self._js("onListen", {"state": "transcribing"})

        try:
            text = self._listener.listen(on_transcribing=transcribing)
            duration = time.monotonic() - transcription_started if transcription_started is not None else 0.0
            self._logger.info("Transcription terminée en %.2f s", duration)
            self._js("onListen", {"state": "done", "text": text})
        except Exception:
            self._logger.exception("Erreur pendant l'écoute ou la transcription")
            self._js("onListen", {
                "state": "error",
                "message": "Je n'ai pas réussi à écouter le micro. Réessaie.",
            })
        finally:
            with self._lock:
                self._listening = False
            self._logger.info("Fin de l'écoute")

    def _answer(self, messages: list[dict[str, str]], chat_id: str, first_question: str | None) -> None:
        started = time.monotonic()
        pending: list[str] = []
        actions: list[str] = []
        last_flush = 0.0
        splitter = voice.SentenceSplitter() if self._voice_settings["enabled"] else None

        def flush() -> None:
            nonlocal last_flush
            if pending:
                self._js("onChunk", "".join(pending))
                pending.clear()
                last_flush = time.monotonic()

        def receive(chunk: str) -> None:
            pending.append(chunk)
            if splitter is not None and self._voice_settings["enabled"] and not self._stop.is_set():
                for sentence in splitter.feed(chunk):
                    self._speak(sentence)
            if time.monotonic() - last_flush >= 0.05:
                flush()

        def action(text: str) -> None:
            actions.append(text)
            self._on_action(text)

        answer = ""
        try:
            answer = brain.chat_stream(
                messages,
                receive,
                self._stop,
                tools=self._tools,
                confirm=self._confirm,
                on_action=action,
            )
            flush()
            if splitter is not None and self._voice_settings["enabled"] and not self._stop.is_set():
                for sentence in splitter.flush():
                    self._speak(sentence)
            if answer or actions:
                extra = {"actions": actions} if actions else {}
                self._store.append(chat_id, "assistant", answer, **extra)
                if first_question is not None:
                    threading.Thread(
                        target=self._make_title,
                        args=(chat_id, first_question, answer),
                        daemon=True,
                        name="sakura-ai-title",
                    ).start()
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

    def _make_title(self, chat_id: str, question: str, answer: str) -> None:
        title = brain.make_title(question, answer)
        try:
            self._store.rename(chat_id, title, automatic=True)
            self._js("onChatsChanged")
        except (OSError, ValueError, FileNotFoundError):
            self._logger.exception("Impossible d'enregistrer le titre id=%s", chat_id)


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

