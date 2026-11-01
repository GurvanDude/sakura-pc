r"""Où vivent les fichiers de Sakura PC.

Le code est dans le dépôt. Tout ce qui est propre à ton PC (config, journaux, jaquettes, icônes d'applis,
logiciels tiers téléchargés) vit dans le dossier utilisateur : %APPDATA%\SakuraPC, ou SAKURA_HOME s'il est défini.
Ainsi le dépôt ne contient jamais rien de personnel."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
USER = Path(os.environ.get('SAKURA_HOME') or Path(os.environ.get('APPDATA', Path.home())) / 'SakuraPC')
CONFIG = USER / 'config.json'


def app(name):
    """Dossier du code d'une appli : apps/<name>."""
    return REPO / 'apps' / name


def log(name):
    """Journal d'une appli, dans le dossier utilisateur."""
    USER.mkdir(parents=True, exist_ok=True)
    return USER / f'{name}.log'
