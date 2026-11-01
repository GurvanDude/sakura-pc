"""Génère les fonds candidats avec l'API d'images d'OpenAI (ChatGPT).

Prérequis : une clé API OpenAI dans la variable d'environnement OPENAI_API_KEY
(sur platform.openai.com ; l'abonnement ChatGPT Plus ne donne pas de crédits API).

Exemples :
  python tools/generate_images.py                  # les 40 images, qualité "medium"
  python tools/generate_images.py day-main         # une seule catégorie
  python tools/generate_images.py night-side-03 --quality high
Les images arrivent dans images/candidates/<id>.png ; celles qui existent déjà sont sautées.
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / 'images' / 'PROMPTS.md'
OUT = ROOT / 'images' / 'candidates'


def load_prompts():
    # chaque ligne contient déjà le prompt complet (format, disposition, style, texte)
    text = PROMPTS.read_text(encoding='utf-8')
    return [(pid, prompt.strip()) for pid, prompt in re.findall(r'^- \*\*((?:day|night)-(?:main|side)-\d+)\*\* : (.+)$', text, re.M)]


def generate(prompt, quality, model):
    body = json.dumps({'model': model, 'prompt': prompt, 'size': '1536x1024', 'quality': quality, 'n': 1}).encode()
    req = urllib.request.Request('https://api.openai.com/v1/images/generations', data=body, headers={
        'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
        'Content-Type': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=300) as r:
        return base64.b64decode(json.load(r)['data'][0]['b64_json'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('only', nargs='?', default='', help='préfixe d\'id à générer (ex. day-main, night-side-03)')
    ap.add_argument('--quality', default='medium', choices=['low', 'medium', 'high'])
    ap.add_argument('--model', default=os.environ.get('OPENAI_IMAGE_MODEL', 'gpt-image-1'))
    args = ap.parse_args()
    if not os.environ.get('OPENAI_API_KEY'):
        sys.exit('OPENAI_API_KEY manquante (voir le haut de ce fichier).')
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [(i, p) for i, p in load_prompts() if i.startswith(args.only)]
    for n, (pid, prompt) in enumerate(todo, 1):
        dest = OUT / f'{pid}.png'
        if dest.exists():
            print(f'[{n}/{len(todo)}] {pid} déjà là'); continue
        print(f'[{n}/{len(todo)}] {pid}…', flush=True)
        try:
            dest.write_bytes(generate(prompt, args.quality, args.model))
        except Exception as e:  # on continue avec les suivantes
            print(f'   échec : {e}')


if __name__ == '__main__':
    main()
