"""Tests du contrat JSON de la ligne de commande."""

from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

APP = Path(__file__).resolve().parents[1]
ENTRYPOINT = APP / "musique.py"
REPO = APP.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(APP))

import musique  # noqa: E402


class CliTests(unittest.TestCase):
    def test_status_json_sans_compte(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = dict(os.environ)
            environment["SAKURA_HOME"] = temporary
            result = subprocess.run(
                [sys.executable, str(ENTRYPOINT), "status", "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"connected": False, "user": None})

    def test_now_json_sans_lecture(self):
        class API:
            def player_state(self):
                return None

        self.assertEqual(musique.now(API()), {"ok": True, "error": None, "playing": False})

    def test_play_reveille_appareil_et_renvoie_le_morceau(self):
        class API:
            def __init__(self):
                self.played = False

            def play(self, device_id=None):
                self.played = device_id

            def player_state(self):
                return {"is_playing": True, "title": "Sakura"}

        api = API()
        with patch.object(musique, "ensure_device", return_value={"id": "pc"}) as ensure:
            result = musique.play(api)

        ensure.assert_called_once_with(api)
        self.assertEqual(api.played, "pc")
        self.assertEqual(result, {"ok": True, "error": None, "is_playing": True, "title": "Sakura"})

    def test_commandes_now_et_play_ecrivent_du_json(self):
        cases = {
            "now": {"ok": True, "error": None, "playing": False},
            "play": {"ok": True, "error": None, "is_playing": True},
        }
        for command, expected in cases.items():
            with self.subTest(command=command), patch.object(
                musique, command, return_value=expected
            ), patch.object(sys, "argv", ["musique.py", command, "--json"]):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = musique.main()
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue()), expected)


if __name__ == "__main__":
    unittest.main()
