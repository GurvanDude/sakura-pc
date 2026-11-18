"""Sakura Optimizer surveille le PC et explique pourquoi ça rame.

    pythonw optimizer.py                         fenêtre simple
    python optimizer.py app                      fenêtre simple (explicite)
    python optimizer.py monitor                  moniteur technique temps réel
    python optimizer.py monitor --once           une seule mesure
    python optimizer.py monitor --json           une mesure au format JSON
    python optimizer.py diagnose --minutes 5     diagnostic des dernières minutes
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
    diagnostic = subparsers.add_parser(
        'diagnose', help='Explique ce qui a ralenti le PC dans les dernières minutes.'
    )
    diagnostic.add_argument(
        '--minutes', type=float, default=5, help='Période à analyser, en minutes (5 par défaut).'
    )
    diagnostic.add_argument('--json', action='store_true', help='Affiche le résultat au format JSON.')
    cleanup = subparsers.add_parser('cleanup', help='Regarde ou range les fichiers temporaires.')
    cleanup_mode = cleanup.add_mutually_exclusive_group(required=True)
    cleanup_mode.add_argument('--preview', action='store_true', help='Aperçu sans rien toucher.')
    cleanup_mode.add_argument('--apply', metavar='IDS', help='Catégories à nettoyer, séparées par des virgules.')
    cleanup.add_argument('--json', action='store_true', help='Affiche le résultat au format JSON.')
    action_list = subparsers.add_parser('actions', help='Affiche le journal des actions.')
    action_list.add_argument('--json', action='store_true', help='Affiche le résultat au format JSON.')
    undo = subparsers.add_parser('undo', help='Annule une action encore en quarantaine.')
    undo.add_argument('id', help="Identifiant de l'action.")
    undo.add_argument('--json', action='store_true', help='Affiche le résultat au format JSON.')
    startup = subparsers.add_parser('startup', help='Affiche ou règle le démarrage de Windows.')
    startup_mode = startup.add_mutually_exclusive_group()
    startup_mode.add_argument('--disable', metavar='ID', help='Coupe cette entrée au démarrage.')
    startup_mode.add_argument('--enable', metavar='ID', help='Remet cette entrée au démarrage.')
    startup.add_argument('--json', action='store_true', help='Affiche le résultat au format JSON.')
    duplicates = subparsers.add_parser('duplicates', help='Cherche les fichiers strictement identiques.')
    duplicates.add_argument('--json', action='store_true', help='Affiche le résultat au format JSON.')
    return parser


def _size(value):
    units = ('octets', 'Ko', 'Mo', 'Go', 'To')
    number = float(value or 0)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            digits = 0 if unit == 'octets' else 1
            return f"{number:.{digits}f}".replace('.', ',') + f' {unit}'
        number /= 1024


def _print_diagnosis(result):
    """Affiche le diagnostic avec des mots simples dans le terminal."""
    print(result['verdict']['title'])
    print(result['verdict']['text'])
    if not result['findings']:
        return
    for finding in result['findings']:
        label = 'Important' if finding['severity'] == 'grave' else (
            'Attention' if finding['severity'] == 'attention' else 'Information'
        )
        print(f"\n{label} : {finding['title']}")
        print(finding['explanation'])
        for evidence in finding['evidence']:
            print(f"- {evidence['label']} : {evidence['value']}")
        for advice in finding['advice']:
            print(f"  Conseil : {advice}")


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
    if args.command == 'diagnose':
        if args.minutes <= 0 or args.minutes > 60:
            parser.error('--minutes doit être compris entre 1 et 60')
        from sakura_opt.diagnose import run_diagnosis

        result = run_diagnosis(args.minutes)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_diagnosis(result)
        return 0
    if args.command == 'cleanup':
        from sakura_opt.cleanup import apply, scan
        result = scan() if args.preview else apply(
            [value.strip() for value in args.apply.split(',') if value.strip()]
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.preview:
            print('Aperçu — rien n’a été touché :')
            for category in result['categories']:
                state = f" — {category['raison']}" if category['desactivee'] else ''
                print(f"- {category['titre']} : {_size(category['taille'])}, "
                      f"{category['nombre']} fichier(s){state}")
        else:
            print(f"{_size(result['place_gagnee'])} libérés ; "
                  f"{result['ignores']} fichier(s) en cours d’utilisation laissé(s) en place.")
        return 0
    if args.command == 'actions':
        from sakura_opt.actions import actions
        result = actions()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif not result:
            print("Aucune action dans le journal.")
        else:
            for action in result:
                print(f"{action['id']} · {action['date']} · {action['resume']} · "
                      f"{_size(action['place_gagnee'])} · {action['etat']}")
        return 0
    if args.command == 'undo':
        from sakura_opt.actions import undo
        result = undo(args.id)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"{result.get('restaures', 0)} fichier(s) remis en place." if result.get('ok')
                  else result.get('erreur', "L'action n'a pas pu être annulée."))
        return 0 if result.get('ok') else 1
    if args.command == 'startup':
        from sakura_opt.startup import disable, enable, list_entries
        result = disable(args.disable) if args.disable else (
            enable(args.enable) if args.enable else {"entries": list_entries()}
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.disable or args.enable:
            print(result.get('message') if result.get('ok') else result.get('erreur'))
        else:
            for entry in result['entries']:
                editor = f" · {entry['editeur']}" if entry['editeur'] else ''
                reason = f" · {entry['raison']}" if entry['raison'] else ''
                print(f"{entry['id']} · {entry['nom']}{editor} · {entry['etat']} · "
                      f"{entry['source']}{reason}")
        return 0 if result.get('ok', True) else 1
    if args.command == 'duplicates':
        from sakura_opt.duplicates import scan
        result = scan()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            copies = result.get('fichiers_en_double', sum(
                max(0, len(group['copies']) - 1) for group in result['groups']
            ))
            print(f"{copies} fichier(s) en double · {_size(result['gain_total'])} à gagner")
            print(f"{result['fichiers_regardes']:,} fichier(s) regardé(s)".replace(',', ' '))
        return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
