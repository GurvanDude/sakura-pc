"""Grave « tout éteint » dans la mémoire permanente de la puce RGB de la carte mère (ITE 8297, GIGABYTE).
C'est ce que la puce affiche à l'allumage du PC, avant Windows. À relancer si GIGABYTE Control Center
réenregistre un effet. Le programme lumières doit tourner (il met la puce en « fixe noir » avant la sauvegarde)."""
import ctypes
import sys
import time
from pathlib import Path

import hid

ROOT = Path(__file__).resolve().parent.parent
user32 = ctypes.windll.user32
hwnd = user32.FindWindowW('SakuraLightsShutdown', None)
if not hwnd:
    sys.exit('Le programme lumières ne tourne pas.')
user32.SendMessageW(hwnd, 0x0011, 0, 0)          # comme une extinction : tout en noir, puce en « fixe noir »
time.sleep(1)
path = next(d['path'] for d in hid.enumerate(0x048D) if d['usage'] == 0xCC)
dev = hid.device()
dev.open_path(path)
dev.send_feature_report([0xCC, 0x5E, 0x00, 0x00] + [0] * 60)   # 0x5E : sauvegarde en mémoire permanente
time.sleep(.2)
dev.close()
print('Noir enregistré dans la puce.')
# on relance le programme lumières pour reprendre l'ambiance
import psutil   # noqa: E402
for proc in psutil.process_iter(['cmdline']):
    if (proc.info['cmdline'] or [''])[-1].endswith('lights.py'):
        proc.kill()
time.sleep(2)
sys.path.insert(0, str(ROOT))
import lights   # noqa: E402
lights.ensure_running()
