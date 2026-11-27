"""Tests de sélection et réveil de l'appareil Spotify."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(APP))

from sakura_musique.spotify_app import ensure_device  # noqa: E402


class FakeAPI:
    def __init__(self, answers):
        self.answers = list(answers)
        self.transfers = []

    def devices(self):
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def transfer(self, device_id, play=False):
        self.transfers.append((device_id, play))


class SpotifyAppTests(unittest.TestCase):
    def test_appareil_actif_est_reutilise(self):
        device = {"id": "actif", "type": "Computer", "is_active": True}
        api = FakeAPI([[device]])
        self.assertIs(ensure_device(api), device)
        self.assertEqual(api.transfers, [])

    def test_ordinateur_inactif_est_transfere_sans_lecture(self):
        device = {"id": "pc", "type": "Computer", "is_active": False}
        api = FakeAPI([[device]])
        self.assertIs(ensure_device(api), device)
        self.assertEqual(api.transfers, [("pc", False)])

    def test_spotify_est_lance_puis_le_nouvel_ordinateur_est_transfere(self):
        launched = []
        device = {"id": "nouveau", "type": "Computer", "is_active": False}
        api = FakeAPI([[], [device]])
        result = ensure_device(api, launcher=lambda: launched.append(True), sleep=lambda _seconds: None)
        self.assertIs(result, device)
        self.assertEqual(launched, [True])
        self.assertEqual(api.transfers, [("nouveau", False)])


if __name__ == "__main__":
    unittest.main()
