"""Petite façade de l'API Web Spotify."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from . import store
from .auth import AuthError, SpotifyAuth

API_URL = "https://api.spotify.com/v1"
ME_URL = f"{API_URL}/me"


class SpotifyApiError(AuthError):
    """Erreur Spotify déjà formulée pour l'interface et la ligne de commande."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _error_details(error: urllib.error.HTTPError) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(error.read().decode("utf-8"))
        detail = payload.get("error", payload) if isinstance(payload, dict) else {}
        if isinstance(detail, dict):
            return detail.get("reason"), detail.get("message")
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return None, None


class SpotifyAPI:
    """Client Spotify sans dépendance, avec rafraîchissement et erreurs homogènes."""

    def __init__(self, auth: SpotifyAuth | None = None, *, sleep: Callable[[float], Any] = time.sleep) -> None:
        self._auth = auth or SpotifyAuth()
        self._sleep = sleep

    def _force_refresh(self) -> str:
        saved = store.load()
        tokens = saved.get("tokens") if isinstance(saved.get("tokens"), dict) else {}
        client_id = saved.get("client_id")
        refresh_token = tokens.get("refresh_token")
        if not client_id or not refresh_token:
            raise SpotifyApiError("La connexion Spotify a expiré. Reconnecte ton compte.", status=401)
        refreshed = self._auth.refresh(str(client_id), str(refresh_token))
        return str(refreshed["access_token"])

    def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None,
                 retry_401: bool = True, retry_429: bool = True) -> Any:
        token = self._auth.access_token()
        url = path if path.startswith("https://") else f"{API_URL}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None

        def make_request(access_token: str) -> Any:
            request = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": f"Bearer {access_token}", "Accept": "application/json",
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(request, timeout=15) as response:
                status = getattr(response, "status", None) or response.getcode()
                payload = response.read()
                if status == 204 or not payload:
                    return None
                decoded = json.loads(payload.decode("utf-8"))
                if not isinstance(decoded, (dict, list)):
                    raise ValueError("Réponse JSON inattendue")
                return decoded

        try:
            return make_request(token)
        except urllib.error.HTTPError as error:
            status = error.code
            if status == 401 and retry_401:
                try:
                    return make_request(self._force_refresh())
                except urllib.error.HTTPError as second:
                    error, status = second, second.code
                    retry_401 = False
            if status == 429 and retry_429:
                try:
                    delay = max(0.0, float(error.headers.get("Retry-After", "1")))
                except (TypeError, ValueError):
                    delay = 1.0
                self._sleep(delay)
                return self._request(method, path, body=body, retry_401=retry_401, retry_429=False)
            reason, detail = _error_details(error)
            if status == 403:
                raise SpotifyApiError("Il faut Spotify Premium pour piloter la lecture.", status=403, code=reason) from error
            if status == 404 and (reason == "NO_ACTIVE_DEVICE" or "device" in (detail or "").lower()):
                raise SpotifyApiError("Aucun appareil Spotify n’est actif.", status=404, code="NO_ACTIVE_DEVICE") from error
            if status == 401:
                raise SpotifyApiError("La connexion Spotify a expiré. Reconnecte ton compte.", status=401) from error
            raise SpotifyApiError(detail or "Spotify ne répond pas, je réessaie.", status=status, code=reason) from error
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise SpotifyApiError("Je n’arrive pas à joindre Spotify pour le moment.") from error

    def me(self) -> dict[str, Any]:
        payload = self._request("GET", "/me")
        if not isinstance(payload, dict):
            raise SpotifyApiError("Spotify a renvoyé une réponse que je ne reconnais pas.")
        images = payload.get("images") if isinstance(payload.get("images"), list) else []
        image = images[0].get("url") if images and isinstance(images[0], dict) else None
        return {"display_name": payload.get("display_name") or "Gurvan",
                "product": payload.get("product") or "unknown", "image": image}

    def player_state(self) -> dict[str, Any] | None:
        payload = self._request("GET", "/me/player")
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise SpotifyApiError("Spotify a renvoyé un lecteur que je ne reconnais pas.")
        item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
        album = item.get("album") if isinstance(item.get("album"), dict) else {}
        artists = item.get("artists") if isinstance(item.get("artists"), list) else []
        names = [str(a.get("name")) for a in artists if isinstance(a, dict) and a.get("name")]
        images = album.get("images") if isinstance(album.get("images"), list) else []
        valid = [image for image in images if isinstance(image, dict) and image.get("url")]
        cover = max(valid, key=lambda image: int(image.get("width") or 0), default={})
        device = payload.get("device") if isinstance(payload.get("device"), dict) else {}
        return {
            "is_playing": bool(payload.get("is_playing")), "progress_ms": int(payload.get("progress_ms") or 0),
            "duration_ms": int(item.get("duration_ms") or 0), "title": item.get("name") or "",
            "artists": ", ".join(names), "album": album.get("name") or "", "cover_url": cover.get("url"),
            "shuffle": bool(payload.get("shuffle_state")), "repeat": payload.get("repeat_state") or "off",
            "volume": int(device.get("volume_percent") or 0),
            "device": {"id": device.get("id"), "name": device.get("name") or "", "type": device.get("type") or ""},
        }

    def devices(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/me/player/devices")
        rows = payload.get("devices", []) if isinstance(payload, dict) else []
        return [{"id": row.get("id"), "name": row.get("name") or "Spotify", "type": row.get("type") or "",
                 "is_active": bool(row.get("is_active")), "volume": int(row.get("volume_percent") or 0)}
                for row in rows if isinstance(row, dict) and row.get("id")]

    @staticmethod
    def _device_query(device_id: str | None) -> str:
        return "?" + urllib.parse.urlencode({"device_id": device_id}) if device_id else ""

    def play(self, device_id: str | None = None) -> None:
        self._request("PUT", f"/me/player/play{self._device_query(device_id)}")

    def pause(self) -> None:
        self._request("PUT", "/me/player/pause")

    def next(self) -> None:
        self._request("POST", "/me/player/next")

    def previous(self) -> None:
        self._request("POST", "/me/player/previous")

    def seek(self, milliseconds: int) -> None:
        self._request("PUT", f"/me/player/seek?{urllib.parse.urlencode({'position_ms': max(0, int(milliseconds))})}")

    def set_volume(self, percent: int) -> None:
        value = min(100, max(0, int(percent)))
        self._request("PUT", f"/me/player/volume?{urllib.parse.urlencode({'volume_percent': value})}")

    def set_shuffle(self, enabled: bool) -> None:
        state = str(bool(enabled)).lower()
        self._request("PUT", f"/me/player/shuffle?{urllib.parse.urlencode({'state': state})}")

    def set_repeat(self, mode: str) -> None:
        if mode not in {"off", "context", "track"}:
            raise ValueError("Le mode de répétition doit être off, context ou track.")
        self._request("PUT", f"/me/player/repeat?{urllib.parse.urlencode({'state': mode})}")

    def transfer(self, device_id: str, play: bool = False) -> None:
        self._request("PUT", "/me/player", body={"device_ids": [device_id], "play": bool(play)})


def get_me(auth: SpotifyAuth | None = None) -> dict[str, Any]:
    return SpotifyAPI(auth).me()


def player_state(auth: SpotifyAuth | None = None) -> dict[str, Any] | None:
    return SpotifyAPI(auth).player_state()


def devices(auth: SpotifyAuth | None = None) -> list[dict[str, Any]]:
    return SpotifyAPI(auth).devices()


def play(device_id: str | None = None, auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).play(device_id)


def pause(auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).pause()


def next(auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).next()


def previous(auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).previous()


def seek(milliseconds: int, auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).seek(milliseconds)


def set_volume(percent: int, auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).set_volume(percent)


def set_shuffle(enabled: bool, auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).set_shuffle(enabled)


def set_repeat(mode: str, auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).set_repeat(mode)


def transfer(device_id: str, play: bool = False, auth: SpotifyAuth | None = None) -> None:
    SpotifyAPI(auth).transfer(device_id, play)
