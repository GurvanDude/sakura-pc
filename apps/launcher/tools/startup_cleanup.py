"""Tri des applis lancées au démarrage de Windows (équivalent de l'onglet Démarrage du Gestionnaire des tâches).

    python tools/startup_cleanup.py            applique le tri (et sauvegarde l'état d'avant)
    python tools/startup_cleanup.py --restore  remet tout comme avant
Quand le bureau est démarré par le launcher (mode coquille), Windows ignore les cases « désactivé » :
les entrées coupées sont donc aussi retirées de la clé Run (leur commande est gardée dans la sauvegarde).
L'état d'origine est gardé dans tools/startup_backup.json.
"""
import json
import subprocess
import sys
import winreg
from pathlib import Path

BACKUP = Path(__file__).with_name('startup_backup.json')
RUN = r'Software\Microsoft\Windows\CurrentVersion\Run'
APPROVED = r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
STORE = r'Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData'

# entrées « Run » de l'utilisateur à ne plus lancer au démarrage
RUN_OFF = ['OneDrive', 'Opera GX Stable', 'Opera GX Browser Assistant', 'Steam', 'EpicGamesLauncher', 'Discord',
           'GogGalaxy', 'GalaxyClient', 'Teams', 'MicrosoftEdgeAutoLaunch_C46CFC0629905CC775E70B50EA8A519C',
           # déjà désactivées avant le launcher
           'EADM', 'Overwolf', 'NordVPN', 'RiotClient', 'Docker Desktop']
# tâches de démarrage des applis du Store (paquet, tâche)
STORE_OFF = [
    ('3138AweZip.AweZip_ffd303wmbhcjt', 'ArchiveObserverStartupTask'),
    ('Microsoft.MicrosoftOfficeHub_8wekyb3d8bbwe', 'WebViewHostStartupId'),
    ('Microsoft.StartExperiencesApp_8wekyb3d8bbwe', 'MicrosoftStartFeedProvider'),
    ('Microsoft.YourPhone_8wekyb3d8bbwe', 'YourPhone.Start'),
    ('MicrosoftWindows.CrossDevice_cw5n1h2txyewy', 'CrossDevice.Start'),
    ('MSTeams_8wekyb3d8bbwe', 'TeamsTfwStartupTask'),
    ('OpenAI.Codex_2p2nqsd0c76g0', 'App'),
    ('SpotifyAB.SpotifyMusic_zpdnekdrzrea0', 'Spotify'),
    ('SpotifyAB.SpotifyMusic_zpdnekdrzrea0', 'SpotifyLauncher'),
]
# tâches planifiées à l'ouverture de session
TASKS_OFF = [r'\OneDrive Startup Task-S-1-5-21-3019138659-1511099916-2421452700-1000']

DISABLED = bytes([3, 0, 0, 0]) + bytes(8)   # même valeur que le Gestionnaire des tâches


def read_approved(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED) as k:
            return winreg.QueryValueEx(k, name)[0].hex()
    except FileNotFoundError:
        return None


def write_approved(name, value_hex):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, APPROVED, 0, winreg.KEY_SET_VALUE) as k:
        if value_hex is None:
            winreg.DeleteValue(k, name)
        else:
            winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, bytes.fromhex(value_hex))


def store_state(pkg, task, value=None):
    path = rf'{STORE}\{pkg}\{task}'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            if value is None:
                return winreg.QueryValueEx(k, 'State')[0]
            winreg.SetValueEx(k, 'State', 0, winreg.REG_DWORD, value)
    except FileNotFoundError:
        return None


def task_enabled(name):
    out = subprocess.run(['powershell', '-NoProfile', '-Command',
                          f"(Get-ScheduledTask -TaskPath '\\' -TaskName '{name.lstrip(chr(92))}' -ErrorAction SilentlyContinue).State"],
                         capture_output=True, text=True).stdout.strip()
    return out and out != 'Disabled'


def set_task(name, enabled):
    verb = 'Enable-ScheduledTask' if enabled else 'Disable-ScheduledTask'
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    f"{verb} -TaskPath '\\' -TaskName '{name.lstrip(chr(92))}' | Out-Null"], check=False)


def pop_run(name):
    """Retire une entrée de la clé Run et renvoie sa commande (None si absente)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            value = winreg.QueryValueEx(k, name)[0]
            winreg.DeleteValue(k, name)
            return value
    except FileNotFoundError:
        return None


if '--restore' in sys.argv:
    b = json.loads(BACKUP.read_text(encoding='utf-8'))
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as k:
        for name, cmd in b.get('run_values', {}).items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, cmd)
    for name, v in b['run'].items():
        write_approved(name, v)
    for key, v in b['store'].items():
        if v is not None:
            store_state(*key.split('|'), value=v)
    for name, on in b['tasks'].items():
        set_task(name, on)
    print('Démarrage remis comme avant.')
    sys.exit()

if not BACKUP.exists():
    BACKUP.write_text(json.dumps({
        'run': {n: read_approved(n) for n in RUN_OFF},
        'store': {f'{p}|{t}': store_state(p, t) for p, t in STORE_OFF},
        'tasks': {t: bool(task_enabled(t)) for t in TASKS_OFF},
    }, indent=2), encoding='utf-8')

backup = json.loads(BACKUP.read_text(encoding='utf-8'))
values = backup.setdefault('run_values', {})
for n in RUN_OFF:
    write_approved(n, DISABLED.hex())
    cmd = pop_run(n)
    if cmd is not None:
        values[n] = cmd
BACKUP.write_text(json.dumps(backup, indent=2), encoding='utf-8')
for p, t in STORE_OFF:
    if store_state(p, t) is not None:
        store_state(p, t, value=1)   # 1 = désactivé par l'utilisateur
for t in TASKS_OFF:
    set_task(t, False)
print('Tri appliqué. Pour revenir en arrière : python tools/startup_cleanup.py --restore')
