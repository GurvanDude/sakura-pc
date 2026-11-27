"""Tests sans réseau du flux OAuth PKCE."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(APP))

from sakura_musique import store  # noqa: E402
from sakura_musique.auth import (  # noqa: E402
    REDIRECT_URI,
    SCOPES,
    SpotifyAuth,
    build_authorize_url,
    code_challenge,
    generate_code_verifier,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._payload


class AuthTests(unittest.TestCase):
    def test_pkce_est_sha256_base64url_sans_egal(self):
        verifier = generate_code_verifier()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")

        self.assertEqual(len(verifier), 64)
        self.assertEqual(code_challenge(verifier), expected)
        self.assertNotIn("=", code_challenge(verifier))

    def test_url_d_autorisation_contient_tous_les_parametres(self):
        verifier = "a" * 64
        url = build_authorize_url("1" * 32, verifier, "etat-test")
        query = parse_qs(urlsplit(url).query)

        self.assertEqual(urlsplit(url).scheme, "https")
        self.assertEqual(urlsplit(url).netloc, "accounts.spotify.com")
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["1" * 32])
        self.assertEqual(query["redirect_uri"], [REDIRECT_URI])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["code_challenge"], [code_challenge(verifier)])
        self.assertEqual(query["state"], ["etat-test"])
        self.assertEqual(query["scope"], [SCOPES])

    def test_jeton_expirant_est_rafraichi_et_garde_l_ancien_refresh_token(self):
        saved = {
            "client_id": "a" * 32,
            "tokens": {
                "access_token": "ancien-acces",
                "refresh_token": "ancien-refresh",
                "expires_at": 1050,
            },
        }
        response = FakeResponse({"access_token": "nouvel-acces", "expires_in": 3600})

        with patch.object(store, "load", return_value=saved), \
             patch.object(store, "save_tokens") as save_tokens, \
             patch("urllib.request.urlopen", return_value=response) as urlopen:
            token = SpotifyAuth(clock=lambda: 1000).access_token()

        self.assertEqual(token, "nouvel-acces")
        written = save_tokens.call_args.args[0]
        self.assertEqual(written["refresh_token"], "ancien-refresh")
        self.assertEqual(written["expires_at"], 4600)
        request = urlopen.call_args.args[0]
        body = parse_qs(request.data.decode("ascii"))
        self.assertEqual(body["grant_type"], ["refresh_token"])
        self.assertEqual(body["client_id"], ["a" * 32])


if __name__ == "__main__":
    unittest.main()
