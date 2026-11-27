"""Tests du pont pywebview, sans ouvrir de fenêtre."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(APP))

from app import Api  # noqa: E402


class FakeAuth:
    pass


class AppTests(unittest.TestCase):
    def test_objets_complexes_du_pont_restent_prives(self):
        api = Api(auth=FakeAuth())

        public_values = {
            name: value for name, value in vars(api).items() if not name.startswith("_")
        }

        self.assertEqual(public_values, {})


if __name__ == "__main__":
    unittest.main()
