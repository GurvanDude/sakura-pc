"""Point d'entrée commun de Sakura Musique."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from sakura_musique import store  # noqa: E402
from sakura_musique.api import get_me  # noqa: E402
from sakura_musique.auth import AuthError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Branche Spotify à Sakura Musique.")
    subparsers = parser.add_subparsers(dest="command")
    status = subparsers.add_parser("status", help="Affiche l’état de la connexion Spotify.")
    status.add_argument("--json", action="store_true", help="Affiche un objet JSON stable.")
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
            print(f"Connecté à Spotify : {result['user']}" if result["connected"] else "Spotify n’est pas connecté.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

