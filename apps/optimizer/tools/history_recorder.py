"""Enregistre l'activité du PC sans droits administrateur."""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import paths  # noqa: E402
from sakura_opt.history import History  # noqa: E402
from sakura_opt.history_mutex import acquire_history_mutex  # noqa: E402
from sakura_opt.names import add_friendly_names  # noqa: E402
from sakura_opt.sensors import Sampler  # noqa: E402
from sakura_opt.temps import read_temps  # noqa: E402


STOP_FILE = paths.USER / "history.stop"


def record_once(
    sampler: Any,
    history: Any,
    temps_reader: Callable[[], dict[str, Any]] = read_temps,
) -> None:
    """Prend et conserve une mesure complète ; isolé pour les tests."""
    status = sampler.sample()
    add_friendly_names(status)
    temperatures = temps_reader()
    status["temps"] = temperatures
    history.record(status, temperatures)


def _log_error_once(errors: dict[str, float], exc: Exception, now: float) -> None:
    message = str(exc) or type(exc).__name__
    if now - errors.get(message, -60.0) >= 60.0:
        logging.exception("Erreur d'enregistrement : %s", message)
        errors[message] = now


def main() -> None:
    logging.basicConfig(
        filename=paths.log("optimizer-history"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    sampler = Sampler()
    history = History()
    errors: dict[str, float] = {}
    mutex = None
    logging.info("Enregistreur d'historique démarré")
    try:
        while not STOP_FILE.exists():
            if mutex is None:
                mutex = acquire_history_mutex()
                if mutex is None:
                    for _ in range(30):
                        if STOP_FILE.exists():
                            break
                        time.sleep(1)
                    continue
            started = time.monotonic()
            try:
                record_once(sampler, history)
            except Exception as exc:
                _log_error_once(errors, exc, time.monotonic())
            remaining = max(0.0, 5.0 - (time.monotonic() - started))
            end = time.monotonic() + remaining
            while not STOP_FILE.exists() and time.monotonic() < end:
                time.sleep(max(0.0, min(0.5, end - time.monotonic())))
    finally:
        if mutex is not None:
            mutex.close()
        try:
            STOP_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        logging.info("Enregistreur d'historique arrêté")


if __name__ == "__main__":
    main()
