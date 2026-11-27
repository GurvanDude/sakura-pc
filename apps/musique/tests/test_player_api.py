"""Tests sans réseau de l'API du lecteur Spotify."""

from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(APP))

from sakura_musique import store  # noqa: E402
from sakura_musique.api import SpotifyAPI  # noqa: E402


class FakeAuth:
    def __init__(self) -> None:
        self.refresh_calls = []

    def access_token(self):
        return "ancien"

    def refresh(self, client_id, refresh_token):
        self.refresh_calls.append((client_id, refresh_token))
        return {"access_token": "nouveau"}


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self.status = status
        self.payload = b"" if payload is None else json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def http_error(status, payload=None, headers=None):
    body = io.BytesIO(json.dumps(payload or {}).encode("utf-8"))
    return urllib.error.HTTPError("https://api.spotify.com", status, "erreur", headers or {}, body)


class PlayerApiTests(unittest.TestCase):
    def test_player_state_est_simplifie_et_prend_la_plus_grande_image(self):
        payload = {
            "is_playing": True,
            "progress_ms": 1250,
            "shuffle_state": True,
            "repeat_state": "context",
            "device": {"id": "pc", "name": "Ce PC", "type": "Computer", "volume_percent": 42},
            "item": {
                "name": "Sakura",
                "duration_ms": 180000,
                "artists": [{"name": "Aiko"}, {"name": "Mina"}],
                "album": {"name": "Hanami", "images": [
                    {"url": "petite", "width": 64}, {"url": "grande", "width": 640}
                ]},
            },
        }
        with patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
            state = SpotifyAPI(FakeAuth()).player_state()

        self.assertEqual(state["title"], "Sakura")
        self.assertEqual(state["artists"], "Aiko, Mina")
        self.assertEqual(state["cover_url"], "grande")
        self.assertEqual(state["device"], {"id": "pc", "name": "Ce PC", "type": "Computer"})
        self.assertEqual(state["volume"], 42)

    def test_reponse_204_devient_none(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(status=204)):
            self.assertIsNone(SpotifyAPI(FakeAuth()).player_state())

    def test_401_rafraichit_puis_reessaie_une_fois(self):
        auth = FakeAuth()
        saved = {"client_id": "a" * 32, "tokens": {"refresh_token": "rafraichir"}}
        with patch.object(store, "load", return_value=saved), patch(
            "urllib.request.urlopen", side_effect=[http_error(401), FakeResponse(status=204)]
        ) as urlopen:
            result = SpotifyAPI(auth).player_state()

        self.assertIsNone(result)
        self.assertEqual(auth.refresh_calls, [("a" * 32, "rafraichir")])
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(urlopen.call_args.args[0].headers["Authorization"], "Bearer nouveau")

    def test_429_respecte_retry_after(self):
        sleeps = []
        with patch("urllib.request.urlopen", side_effect=[
            http_error(429, headers={"Retry-After": "2.5"}), FakeResponse(status=204)
        ]) as urlopen:
            result = SpotifyAPI(FakeAuth(), sleep=sleeps.append).player_state()

        self.assertIsNone(result)
        self.assertEqual(sleeps, [2.5])
        self.assertEqual(urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
