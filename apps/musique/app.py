"""Fenêtre pywebview de Sakura Musique."""

from __future__ import annotations

import http.server
import mimetypes
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from core import paths  # noqa: E402
from core import window as sk_window  # noqa: E402
from sakura_musique import store  # noqa: E402
from sakura_musique.api import get_me  # noqa: E402
from sakura_musique.auth import REDIRECT_URI, AuthError, SpotifyAuth  # noqa: E402


def _token(name: str, fallback: str) -> str:
    """Lit une couleur commune pour le bref fond natif avant le chargement de l'UI."""
    try:
        css = (REPO / "design" / "tokens.css").read_text(encoding="utf-8")
        match = re.search(rf"--{re.escape(name)}\s*:\s*([^;]+)", css)
        return match.group(1).strip() if match else fallback
    except OSError:
        return fallback


def _log(message: str) -> None:
    try:
        target = paths.log("musique")
        with target.open("a", encoding="utf-8") as journal:
            journal.write(message.rstrip() + "\n")
    except Exception:
        pass


class Api:
    """Pont JSON minimal entre JavaScript et Python."""

    def __init__(self, auth: SpotifyAuth | None = None) -> None:
        self._window: Any | None = None
        self._auth = auth or SpotifyAuth()
        self._maximized = False
        self._login_active = False
        self._login_error: str | None = None
        self._login_cancelled = False
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._profile: dict[str, Any] | None = None

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

    def state(self) -> dict[str, Any]:
        saved = store.load()
        has_client_id = bool(saved.get("client_id"))
        tokens = saved.get("tokens") if isinstance(saved.get("tokens"), dict) else {}
        with self._lock:
            active = self._login_active
            error = self._login_error
            cancelled = self._login_cancelled
            profile = dict(self._profile) if self._profile else None
        if tokens and profile is None and not active:
            try:
                profile = get_me(self._auth)
                with self._lock:
                    self._profile = dict(profile)
            except AuthError as exc:
                error = str(exc)
                _log(f"État Spotify : {exc}")
        return {
            "client_id_present": has_client_id,
            "connected": bool(tokens and profile),
            "user": profile.get("display_name") if profile else None,
            "product": profile.get("product") if profile else None,
            "image": profile.get("image") if profile else None,
            "login": {"active": active, "error": error, "cancelled": cancelled},
            "redirect_uri": REDIRECT_URI,
        }

    def save_client_id(self, client_id: str) -> dict[str, Any]:
        try:
            store.save_client_id(client_id)
        except ValueError:
            return {"ok": False, "error": "Ce Client ID ne semble pas bon : il faut 32 caractères hexadécimaux."}
        with self._lock:
            self._profile = None
            self._login_error = None
        return {"ok": True}

    def login(self) -> dict[str, Any]:
        with self._lock:
            if self._login_active:
                return {"ok": True, "started": False}
            client_id = store.load().get("client_id")
            if not client_id:
                return {"ok": False, "error": "Enregistre d’abord ton Client ID."}
            self._login_active = True
            self._login_error = None
            self._login_cancelled = False
            self._profile = None
            self._cancel = threading.Event()

        def worker() -> None:
            error: str | None = None
            cancelled = False
            try:
                self._auth.login(str(client_id), self._cancel)
                if self._cancel.is_set():
                    store.logout()
                    raise AuthError("Connexion annulée.")
                profile = get_me(self._auth)
                with self._lock:
                    self._profile = dict(profile)
            except AuthError as exc:
                error = str(exc)
                cancelled = self._cancel.is_set()
                if not cancelled:
                    _log(f"Connexion Spotify : {exc}")
            except Exception as exc:
                error = "La connexion Spotify n’a pas pu se terminer."
                _log(f"Connexion Spotify inattendue : {type(exc).__name__}: {exc}")
            finally:
                with self._lock:
                    self._login_active = False
                    self._login_error = error
                    self._login_cancelled = cancelled

        threading.Thread(target=worker, daemon=True, name="musique-oauth").start()
        return {"ok": True, "started": True}

    def cancel_login(self) -> dict[str, Any]:
        self._cancel.set()
        return {"ok": True}

    def logout(self) -> dict[str, Any]:
        self._cancel.set()
        store.logout()
        with self._lock:
            self._profile = None
            self._login_error = None
            self._login_cancelled = False
        _log("Compte Spotify déconnecté ; Client ID et jetons effacés.")
        return {"ok": True}

    def copy_redirect(self) -> dict[str, Any]:
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["clip"], input=REDIRECT_URI, text=True, check=True, creationflags=flags
            )
            return {"ok": True}
        except (OSError, subprocess.SubprocessError):
            return {"ok": False, "error": "Je n’ai pas pu copier l’adresse."}


def _serve() -> tuple[http.server.ThreadingHTTPServer, int]:
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

        def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
            file_path = routes.get(unquote(urlsplit(self.path).path))
            if file_path is None:
                self.send_error(404)
                return
            try:
                payload = file_path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="musique-ui").start()
    return server, int(server.server_address[1])


def run(debug: bool = False) -> None:
    import webview

    api = Api()
    server, port = _serve()
    window = webview.create_window(
        "Sakura Musique",
        f"http://127.0.0.1:{port}/index.html",
        js_api=api,
        width=900,
        height=650,
        min_size=(700, 560),
        resizable=True,
        frameless=True,
        easy_drag=False,
        background_color=_token("cream", "white"),
    )
    api._window = window
    try:
        webview.start(
            gui="edgechromium",
            debug=debug,
            private_mode=False,
            storage_path=str(paths.USER / ".webview"),
        )
    finally:
        api._cancel.set()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    run()

