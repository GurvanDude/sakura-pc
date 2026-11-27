"""Tests du contrat JSON de la ligne de commande."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ENTRYPOINT = APP / "musique.py"


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


if __name__ == "__main__":
    unittest.main()
