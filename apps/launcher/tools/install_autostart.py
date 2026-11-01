"""Crée (ou retire) le raccourci qui lance le Sakura Launcher à l'ouverture de la session Windows.

    python tools/install_autostart.py            installe le démarrage automatique
    python tools/install_autostart.py --remove   le retire
    python tools/install_autostart.py --local    crée seulement les raccourcis du dossier du projet
Crée aussi « Sakura Launcher.lnk » dans le dossier du projet pour le lancer à la main.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTUP = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup/Sakura Launcher.lnk'
PYTHONW = Path(sys.executable).with_name('pythonw.exe')


def shortcut(path, args=''):
    ps = f"""$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{path}')
$s.TargetPath = '{PYTHONW}'
$s.Arguments = '"{ROOT / 'launcher.py'}" {args}'
$s.WorkingDirectory = '{ROOT}'
$s.Description = 'Sakura Launcher'
$s.Save()"""
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], check=True)


if '--remove' in sys.argv:
    STARTUP.unlink(missing_ok=True)
    print('Démarrage automatique retiré.')
else:
    shortcut(ROOT / 'Sakura Launcher.lnk')
    shortcut(ROOT / 'Sakura Launcher (essai).lnk', '--dry')
    print('Raccourcis créés dans le dossier du projet.')
    if '--local' not in sys.argv:
        shortcut(STARTUP)
        print(f'Démarrage automatique installé : {STARTUP}')
