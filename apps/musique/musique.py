"""Point d'entrée graphique et contrat JSON de Sakura Musique."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from sakura_musique import store  # noqa: E402
from sakura_musique.api import SpotifyAPI, SpotifyApiError, get_me  # noqa: E402
from sakura_musique.auth import AuthError  # noqa: E402
from sakura_musique.spotify_app import ensure_device  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Branche Spotify à Sakura Musique.")
    subparsers = parser.add_subparsers(dest="command")
    for name, help_text in (
        ("status", "Affiche l'état de la connexion Spotify."),
        ("now", "Affiche le morceau en cours."),
        ("play", "Lance ou reprend la lecture."),
        ("pause", "Met la lecture en pause."),
        ("next", "Passe au morceau suivant."),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--json", action="store_true", help="Affiche un objet JSON stable.")
    return parser


def status() -> dict[str, object]:
    saved = store.load()
    if not isinstance(saved.get("tokens"), dict):
        return {"connected": False, "user": None}
    try:
        profile = get_me()
    except AuthError:
        return {"connected": False, "user": None}
    return {"connected": True, "user": profile["display_name"]}


def now(api: SpotifyAPI | None = None) -> dict[str, Any]:
    service = api or SpotifyAPI()
    try:
        state = service.player_state()
        if state is None:
            return {"ok": True, "error": None, "playing": False}
        return {"ok": True, "error": None, **state}
    except AuthError as error:
        return {"ok": False, "error": str(error), "playing": False}


def _control(action: Callable[[SpotifyAPI], Any], api: SpotifyAPI | None = None) -> dict[str, Any]:
    service = api or SpotifyAPI()
    try:
        try:
            action(service)
        except SpotifyApiError as error:
            if error.code != "NO_ACTIVE_DEVICE":
                raise
            ensure_device(service)
            action(service)
        state = service.player_state()
        return {"ok": True, "error": None, **(state or {"playing": False})}
    except (AuthError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def play(api: SpotifyAPI | None = None) -> dict[str, Any]:
    service = api or SpotifyAPI()
    try:
        device = ensure_device(service)
        service.play(device.get("id"))
        state = service.player_state()
        return {"ok": True, "error": None, **(state or {"playing": False})}
    except (AuthError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def pause(api: SpotifyAPI | None = None) -> dict[str, Any]:
    return _control(lambda service: service.pause(), api)


def next_track(api: SpotifyAPI | None = None) -> dict[str, Any]:
    return _control(lambda service: service.next(), api)


def _plain(command: str, result: dict[str, Any]) -> str:
    if not result.get("ok", True):
        return str(result.get("error") or "Spotify ne répond pas.")
    if command == "now":
        if not result.get("is_playing"):
            return "Rien ne joue pour l'instant."
        return f"{result.get('title', '')} — {result.get('artists', '')}"
    return {"play": "Lecture lancée.", "pause": "Lecture en pause.", "next": "Morceau suivant."}.get(command, "C'est fait.")


def main() -> int:
    args = build_parser().parse_args()
    if args.command is None:
        from app import run

        run()
        return 0
    if args.command == "status":
        result = status()
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Connecté à Spotify : {result['user']}" if result["connected"] else "Spotify n'est pas connecté.")
        return 0
    handlers = {"now": now, "play": play, "pause": pause, "next": next_track}
    result = handlers[args.command]()
    print(json.dumps(result, ensure_ascii=False) if args.json else _plain(args.command, result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
