"""Mutex Windows partagé par les deux enregistreurs possibles."""

from __future__ import annotations

import ctypes
from typing import Any


MUTEX_NAME = "SakuraOptimizerHistory"
ERROR_ALREADY_EXISTS = 183


class HistoryMutex:
    """Possède un mutex nommé jusqu'à sa fermeture."""

    def __init__(self, handle: int, kernel32: Any) -> None:
        self.handle = handle
        self._kernel32 = kernel32

    def close(self) -> None:
        if self.handle:
            self._kernel32.ReleaseMutex(self.handle)
            self._kernel32.CloseHandle(self.handle)
            self.handle = 0

    def __enter__(self) -> "HistoryMutex":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def acquire_history_mutex(kernel32: Any | None = None) -> HistoryMutex | None:
    """Prend le mutex sans attendre, ou renvoie None s'il est déjà possédé."""
    if kernel32 is None:
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (AttributeError, OSError):
            return None
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        error_reader = ctypes.get_last_error
    else:
        error_reader = kernel32.GetLastError
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        return None
    if error_reader() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return HistoryMutex(handle, kernel32)
