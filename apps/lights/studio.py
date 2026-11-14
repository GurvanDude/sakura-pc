"""Ouvre l'appli « Sakura Light » (réglage et aperçu des effets lumineux).
Démarre le programme lumières s'il ne tourne pas déjà.

    pythonw studio.py
"""
import time
import urllib.request

import webview

import lights
from core import window as sk_window


class WindowApi:
    """Commandes appelées par la barre de titre Sakura dans la page."""

    def __init__(self):
        self._window = None
        self._maximized = False

    def _bind(self, window):
        self._window = window

    def minimize(self):
        if self._window:
            self._window.minimize()

    def toggle_maximize(self):
        if not self._window:
            return
        if self._maximized:
            sk_window.restore(self._window)
            self._maximized = False
        else:
            sk_window.maximize(self._window)
            self._maximized = True

    def close(self):
        if self._window:
            self._window.destroy()


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
    api = WindowApi()
    window = webview.create_window(
        'Sakura Light', f'http://127.0.0.1:{lights.PORT}/studio',
        width=1280, height=900, frameless=True, easy_drag=False, js_api=api,
    )
    api._bind(window)
    webview.start(gui='edgechromium')
