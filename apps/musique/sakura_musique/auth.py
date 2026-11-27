"""OAuth Spotify PKCE, sans secret client et uniquement avec la bibliothèque standard."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.server
import json
import secrets
import string
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Callable

from . import store

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 47823
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/callback"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = (
    "user-read-playback-state user-modify-playback-state "
    "user-read-currently-playing playlist-read-private "
    "playlist-read-collaborative user-library-read user-library-modify "
    "user-read-private"
)
_VERIFIER_ALPHABET = string.ascii_letters + string.digits + "-._~"


class AuthError(RuntimeError):
    """Erreur OAuth déjà formulée simplement pour l'interface."""


def generate_code_verifier() -> str:
    return "".join(secrets.choice(_VERIFIER_ALPHABET) for _ in range(64))


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorize_url(client_id: str, verifier: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge(verifier),
            "state": state,
            "scope": SCOPES,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def _friendly_http_error(error: urllib.error.HTTPError) -> AuthError:
    try:
        payload = json.loads(error.read().decode("utf-8"))
        detail = payload.get("error_description") or payload.get("error", {}).get("message")
    except Exception:
        detail = None
    return AuthError(detail or "Spotify n’a pas accepté la connexion.")


class SpotifyAuth:
    def __init__(
        self,
        *,
        opener: Callable[[str], Any] = webbrowser.open,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._opener = opener
        self._clock = clock

    def _token_request(self, fields: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            TOKEN_URL,
            data=urllib.parse.urlencode(fields).encode("ascii"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise _friendly_http_error(error) from error
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise AuthError("Je n’arrive pas à joindre Spotify pour le moment.") from error
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise AuthError("Spotify n’a pas renvoyé de jeton utilisable.")
        return payload

    def exchange_code(self, code: str, verifier: str, client_id: str) -> dict[str, Any]:
        payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "code_verifier": verifier,
            }
        )
        tokens = dict(payload)
        tokens["expires_at"] = self._clock() + float(payload.get("expires_in", 3600))
        store.save_tokens(tokens)
        return tokens

    def refresh(self, client_id: str, refresh_token: str) -> dict[str, Any]:
        payload = self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            }
        )
        tokens = dict(payload)
        tokens["refresh_token"] = payload.get("refresh_token") or refresh_token
        tokens["expires_at"] = self._clock() + float(payload.get("expires_in", 3600))
        store.save_tokens(tokens)
        return tokens

    def access_token(self) -> str:
        saved = store.load()
        client_id = saved.get("client_id")
        tokens = saved.get("tokens") if isinstance(saved.get("tokens"), dict) else {}
        access_token = tokens.get("access_token")
        if not client_id or not access_token:
            raise AuthError("Ton compte Spotify n’est pas encore connecté.")
        try:
            expires_at = float(tokens.get("expires_at", 0))
        except (TypeError, ValueError):
            expires_at = 0
        if expires_at < self._clock() + 60:
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                raise AuthError("La connexion Spotify a expiré. Reconnecte ton compte.")
            tokens = self.refresh(client_id, refresh_token)
            access_token = tokens["access_token"]
        return str(access_token)

    def login(self, client_id: str, cancel: threading.Event | None = None) -> dict[str, Any]:
        cancel = cancel or threading.Event()
        verifier = generate_code_verifier()
        expected_state = secrets.token_urlsafe(24)
        result: dict[str, Any] = {}
        owner = self

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass

            def _page(self, status: int, title: str, text: str) -> None:
                body = (
                    "<!doctype html><html lang='fr'><meta charset='utf-8'>"
                    f"<title>{title}</title><body style='font-family:sans-serif;padding:3rem'>"
                    f"<h1>{title}</h1><p>{text}</p></body></html>"
                ).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path != "/callback":
                    self.send_error(404)
                    return
                query = urllib.parse.parse_qs(parsed.query)
                received_state = query.get("state", [""])[0]
                if not hmac.compare_digest(received_state, expected_state):
                    result["error"] = AuthError("La réponse de Spotify n’était pas sûre. Recommence.")
                    self._page(400, "Connexion interrompue", "Tu peux fermer cet onglet et recommencer.")
                    return
                if query.get("error"):
                    result["error"] = AuthError("Tu as refusé la connexion Spotify.")
                    self._page(400, "Connexion annulée", "Tu peux fermer cet onglet.")
                    return
                code = query.get("code", [""])[0]
                if not code:
                    result["error"] = AuthError("Spotify n’a pas renvoyé le code attendu.")
                    self._page(400, "Connexion interrompue", "Tu peux fermer cet onglet et recommencer.")
                    return
                try:
                    result["tokens"] = owner.exchange_code(code, verifier, client_id)
                except Exception as error:
                    result["error"] = error
                    self._page(502, "Spotify ne répond pas", "Tu peux fermer cet onglet et réessayer.")
                    return
                self._page(200, "C’est bon, tu peux fermer cet onglet", "Sakura Musique est connectée.")

        class CallbackServer(http.server.HTTPServer):
            allow_reuse_address = True

        try:
            server = CallbackServer((CALLBACK_HOST, CALLBACK_PORT), CallbackHandler)
        except OSError as error:
            raise AuthError("Le port de connexion Spotify est déjà utilisé.") from error
        server.timeout = 0.25
        try:
            self._opener(build_authorize_url(client_id, verifier, expected_state))
            while not result and not cancel.is_set():
                server.handle_request()
        finally:
            server.server_close()
        if cancel.is_set() and not result:
            raise AuthError("Connexion annulée.")
        if result.get("error"):
            error = result["error"]
            if isinstance(error, AuthError):
                raise error
            raise AuthError("La connexion Spotify n’a pas pu se terminer.") from error
        return result["tokens"]

