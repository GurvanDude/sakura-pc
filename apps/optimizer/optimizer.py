"""Sakura Optimizer surveille le PC et explique pourquoi ça rame.

    python optimizer.py monitor    moniteur temps réel (à venir)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # racine du dépôt, pour core/
from core import paths  # noqa: E402

ROOT = paths.app('optimizer')
sys.path.insert(0, str(ROOT))   # paquet sakura_opt


def build_parser():
    """Construit les commandes disponibles dans le terminal."""
    parser = argparse.ArgumentParser(description='Surveille le PC et explique pourquoi ça rame.')
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('monitor', help='Lance le moniteur temps réel (à venir).')
    return parser


def main():
    """Traite la commande demandée et renvoie le code de sortie."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == 'monitor':
        print('Moniteur temps réel : bientôt disponible.')
    else:
        parser.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
