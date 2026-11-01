"""Mode « coquille » : à l'ouverture de ta session, Windows lance le Sakura Launcher À LA PLACE du bureau.
Le launcher démarre ensuite lui-même le bureau (explorer) caché derrière lui : le tout premier écran
que tu vois est donc le launcher.

    python tools/shell_mode.py on     active le mode coquille (et retire le lancement par le dossier Démarrage)
    python tools/shell_mode.py off    revient au fonctionnement normal de Windows

Le réglage ne concerne que ton compte (registre HKCU), pas besoin d'être administrateur.
En cas de souci (écran noir au démarrage) : Ctrl+Alt+Suppr → Gestionnaire des tâches → « Exécuter une
nouvelle tâche » → tape explorer → OK, puis lance « python tools/shell_mode.py off ».
"""
import subprocess
import sys
import winreg
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parent.parent
KEY = r'Software\Microsoft\Windows NT\CurrentVersion\Winlogon'
PYTHONW = Path(sys.executable).with_name('pythonw.exe')

mode = sys.argv[1] if len(sys.argv) > 1 else ''
if mode == 'on':
    cmd = f'"{PYTHONW}" "{ROOT / "launcher.py"}" --shell'
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, 'Shell', 0, winreg.REG_SZ, cmd)
    # le dossier Démarrage relancerait un second launcher plus tard
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'install_autostart.py'), '--remove'], check=True)
    print('Mode coquille activé. Au prochain démarrage, le launcher passe avant le bureau.')
elif mode == 'off':
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, 'Shell')
    except FileNotFoundError:
        pass
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'install_autostart.py')], check=True)
    print('Mode coquille désactivé : Windows redémarre normalement sur le bureau, puis le launcher.')
else:
    print(__doc__)
