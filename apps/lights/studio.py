"""Ouvre l'appli « Sakura Lumières » (réglage et aperçu des effets lumineux).
Démarre le programme lumières s'il ne tourne pas déjà.

    pythonw studio.py
"""
import time
import urllib.request

import webview

import lights


def wait_lights(timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{lights.PORT}/api/state', timeout=1).close()
            return True
        except OSError:
            time.sleep(.3)
    return False


if __name__ == '__main__':
    lights.ensure_running()
    wait_lights()
    webview.create_window('Sakura Lumières', f'http://127.0.0.1:{lights.PORT}/studio', width=1280, height=900,
                          background_color='#0d0a16')
    webview.start(gui='edgechromium')
