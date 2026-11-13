"""Relais administrateur des températures pour Sakura Optimizer."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import time


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parents[1]
sys.path[:0] = [str(REPO_DIR), str(APP_DIR)]

import win32api
import win32event
import winerror

from core import paths
from sakura_opt.temps import read_direct


MUTEX_NAME = "SakuraOptimizerTemps"
TEMPS_FILE = paths.USER / "temps.json"
STOP_FILE = paths.USER / "temps.stop"


def _write_temperatures() -> str | None:
    """Publie une mesure complète sans laisser de fichier partiel."""
    values = read_direct()
    values["time"] = time.time()
    paths.USER.mkdir(parents=True, exist_ok=True)
    temporary = TEMPS_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, TEMPS_FILE)
    reason = values.get("reason")
    return str(reason) if reason else None


def main() -> None:
    """Mesure toutes les deux secondes tant que l'arrêt n'est pas demandé."""
    mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.CloseHandle(mutex)
        return

    logging.basicConfig(
        filename=paths.log("optimizer-temps"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logging.info("Lecteur de températures démarré")
    last_errors: dict[str, float] = {}
    try:
        while not STOP_FILE.exists():
            started = time.monotonic()
            try:
                message = _write_temperatures()
                now = time.monotonic()
                if message and now - last_errors.get(message, -60.0) >= 60:
                    logging.warning("Lecture incomplète : %s", message)
                    last_errors[message] = now
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                now = time.monotonic()
                if now - last_errors.get(message, -60.0) >= 60:
                    logging.exception("Erreur de lecture : %s", message)
                    last_errors[message] = now
            time.sleep(max(0.0, 2.0 - (time.monotonic() - started)))
    finally:
        try:
            STOP_FILE.unlink(missing_ok=True)
        except OSError:
            logging.exception("Impossible de supprimer la demande d'arrêt")
        logging.info("Lecteur de températures arrêté")
        win32api.CloseHandle(mutex)


if __name__ == "__main__":
    main()
