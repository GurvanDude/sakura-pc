"""Petite façade de l'API Web Spotify."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .auth import AuthError, SpotifyAuth

ME_URL = "https://api.spotify.com/v1/me"


def get_me(auth: SpotifyAuth | None = None) -> dict[str, Any]:
    service = auth or SpotifyAuth()
    request = urllib.request.Request(
        ME_URL,
        headers={"Authorization": f"Bearer {service.access_token()}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise AuthError("Spotify n’a pas accepté la demande. Reconnecte ton compte.") from error
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise AuthError("Je n’arrive pas à joindre Spotify pour le moment.") from error
    if not isinstance(payload, dict):
        raise AuthError("Spotify a renvoyé une réponse que je ne reconnais pas.")
    images = payload.get("images") if isinstance(payload.get("images"), list) else []
    image = images[0].get("url") if images and isinstance(images[0], dict) else None
    return {
        "display_name": payload.get("display_name") or "Gurvan",
        "product": payload.get("product") or "unknown",
        "image": image,
    }

