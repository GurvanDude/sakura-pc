"""Sakura Optimizer surveille le PC et explique pourquoi ça rame.

    pythonw optimizer.py                         fenêtre simple
    python optimizer.py app                      fenêtre simple (explicite)
    python optimizer.py monitor                  moniteur technique temps réel
    python optimizer.py monitor --once           une seule mesure
    python optimizer.py monitor --json           une mesure au format JSON
"""
import argparse
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # racine du dépôt, pour core/
from core import paths  # noqa: E402

ROOT = paths.app('optimizer')
sys.path.insert(0, str(ROOT))   # paquet sakura_opt


def build_parser():
    """Construit les commandes disponibles dans le terminal."""
    parser = argparse.ArgumentParser(description='Surveille le PC et explique pourquoi ça rame.')
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('app', help='Ouvre la fenêtre simple.')
    monitor = subparsers.add_parser('monitor', help='Lance le moniteur temps réel.')
    monitor.add_argument('--interval', type=float, default=1.0, help='Délai entre deux mesures.')
    monitor.add_argument('--once', action='store_true', help='Affiche une mesure puis quitte.')
    monitor.add_argument('--json', action='store_true', help='Affiche une mesure JSON puis quitte.')
    return parser


def main():
    """Traite la commande demandée et renvoie le code de sortie."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command in (None, 'app'):
        from app import run
        run()
        return 0
    if args.command == 'monitor':
        if args.interval <= 0:
            parser.error('--interval doit être supérieur à zéro')
        from rich.console import Console
        from sakura_opt.monitor import render, run
        from sakura_opt.sensors import Sampler

        if args.once or args.json:
            sampler = Sampler()
            sampler.sample()
            time.sleep(1.0)
            status = sampler.sample()
            if args.json:
                print(json.dumps(status, ensure_ascii=False, indent=2))
            else:
                Console().print(render(status))
            return 0
        return run(args.interval)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
