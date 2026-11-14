"""Agrandir une fenêtre sans bordure sans cacher la barre des tâches.

Sur Windows, une fenêtre pywebview `frameless=True` agrandie avec `window.maximize()` prend tout l'écran,
barre des tâches comprise. Ici on la cale sur la « zone de travail » de l'écran où elle se trouve
(l'écran moins la barre des tâches), et on retient sa taille d'avant pour pouvoir la rendre.

Utilisation dans une appli :
    from core import window as sk_window
    sk_window.maximize(self._window)   # au lieu de self._window.maximize()
    sk_window.restore(self._window)    # au lieu de self._window.restore()
"""
import ctypes
from ctypes import wintypes

_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_MONITOR_DEFAULTTONEAREST = 2

_saved = {}  # poignée de fenêtre -> (gauche, haut, largeur, hauteur) avant agrandissement


class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def _user32():
    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    return user32


def _hwnd(window):
    """Poignée Windows de la fenêtre pywebview (WinForms), ou None si introuvable."""
    handle = getattr(getattr(window, 'native', None), 'Handle', None)
    if handle is None:
        return None
    try:
        return int(handle.ToInt64()) if hasattr(handle, 'ToInt64') else int(handle)
    except Exception:
        return None


def work_area(hwnd):
    """(gauche, haut, largeur, hauteur) de la zone de travail de l'écran qui contient la fenêtre."""
    user32 = _user32()
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST), ctypes.byref(info)):
        return None
    r = info.rcWork
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def maximize(window):
    """Agrandit la fenêtre jusqu'à la barre des tâches (sans la recouvrir)."""
    hwnd = _hwnd(window)
    area = work_area(hwnd) if hwnd else None
    if not area:
        window.maximize()
        return
    user32 = _user32()
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        _saved[hwnd] = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    user32.SetWindowPos(hwnd, None, *area, _SWP_NOZORDER | _SWP_NOACTIVATE)


def restore(window):
    """Rend à la fenêtre la taille et la place qu'elle avait avant `maximize`."""
    hwnd = _hwnd(window)
    before = _saved.pop(hwnd, None) if hwnd else None
    if not before:
        window.restore()
        return
    _user32().SetWindowPos(hwnd, None, *before, _SWP_NOZORDER | _SWP_NOACTIVATE)
