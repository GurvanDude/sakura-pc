"""Crée le raccourci Bureau de Sakura AI. À lancer manuellement."""

import sys
from pathlib import Path

import win32com.client

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def main() -> None:
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(Path(shell.SpecialFolders("Desktop")) / "Sakura AI.lnk"))
    shortcut.Targetpath = str(Path(sys.executable).with_name("pythonw.exe"))
    shortcut.Arguments = f'"{ROOT / "ai.py"}"'
    shortcut.WorkingDirectory = str(ROOT)
    shortcut.IconLocation = str(REPO / "design" / "logo" / "ico" / "ai.ico")
    shortcut.Description = "Sakura AI — ton assistante locale"
    shortcut.save()


if __name__ == "__main__":
    main()

