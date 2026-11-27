"""Tests du stockage personnel de Sakura Musique."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(APP))

from sakura_musique import store  # noqa: E402


class StoreTests(unittest.TestCase):
    def test_validation_du_client_id(self):
        self.assertTrue(store.validate_client_id("0123456789abcdefABCDEF0123456789"))
        self.assertFalse(store.validate_client_id("trop-court"))
        self.assertFalse(store.validate_client_id("g" * 32))
        self.assertFalse(store.validate_client_id("a" * 33))

    def test_ecriture_lecture_et_logout_sous_sakura_home(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"SAKURA_HOME": temporary}
        ):
            client_id = "a" * 32
            store.save_client_id(client_id)
            store.save_tokens({"access_token": "secret", "expires_at": 123})

            self.assertEqual(store.load()["client_id"], client_id)
            self.assertEqual(store.load()["tokens"]["access_token"], "secret")
            self.assertEqual(store.token_path(), Path(temporary) / "musique" / "token.json")

            store.logout()

            self.assertEqual(store.load(), {})
            self.assertFalse(store.token_path().exists())


if __name__ == "__main__":
    unittest.main()
