"""Installe localement la reconnaissance et la synthèse vocales de Sakura."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
SITE_PACKAGES = VENDOR / "site-packages"
WHISPER_DIR = VENDOR / "models" / "whisper-small"
KOKORO_DIR = VENDOR / "models" / "kokoro"
WHISPER_URL = "https://huggingface.co/Systran/faster-whisper-small/resolve/main"
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")


def _python() -> Path:
    executable = Path(sys.executable)
    if executable.name.casefold() == "pythonw.exe":
        console_python = executable.with_name("python.exe")
        if console_python.is_file():
            return console_python
    return executable


def _remote_size(url: str) -> int | None:
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=30) as response:
            value = response.headers.get("Content-Length")
            return int(value) if value else None
    except (OSError, ValueError):
        return None


def _download(url: str, destination: Path) -> None:
    expected = _remote_size(url)
    if destination.is_file() and destination.stat().st_size > 0:
        if expected is None or destination.stat().st_size == expected:
            print(f"Déjà présent : {destination.name}")
            return

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f"{destination.name}.part")
    partial.unlink(missing_ok=True)
    print(f"Téléchargement de {destination.name}…")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
            total_value = response.headers.get("Content-Length")
            total = int(total_value) if total_value else expected
            received = 0
            last_percent = -1
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                received += len(block)
                if total:
                    percent = min(100, received * 100 // total)
                    if percent != last_percent:
                        print(f"  {percent:3d} %", end="\r", flush=True)
                        last_percent = percent
            if total:
                print("  100 %")
        if partial.stat().st_size <= 0:
            raise RuntimeError(f"Le fichier {destination.name} est vide.")
        if expected is not None and partial.stat().st_size != expected:
            raise RuntimeError(f"Le téléchargement de {destination.name} est incomplet.")
        os.replace(partial, destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _verify_onnx() -> None:
    if str(SITE_PACKAGES) not in sys.path:
        sys.path.insert(0, str(SITE_PACKAGES))
    try:
        import onnxruntime
    except ImportError:
        print("Vérification ONNX ignorée : onnxruntime n'est pas importable.")
        return
    print("Vérification du modèle Kokoro…")
    onnxruntime.InferenceSession(
        str(KOKORO_DIR / "kokoro-v1.0.onnx"),
        providers=["CPUExecutionProvider"],
    )


def _started_by_double_click() -> bool:
    if os.name != "nt":
        return False
    if Path(sys.executable).name.casefold() == "pythonw.exe":
        return True
    try:
        process_ids = (ctypes.c_ulong * 8)()
        return ctypes.windll.kernel32.GetConsoleProcessList(process_ids, len(process_ids)) <= 1
    except Exception:
        return False


def _pause_if_needed() -> None:
    if not _started_by_double_click():
        return
    try:
        input("Appuie sur Entrée pour fermer…")
    except (EOFError, OSError):
        pass


def main() -> int:
    try:
        SITE_PACKAGES.mkdir(parents=True, exist_ok=True)
        print("Installation des paquets voix dans apps/ai/vendor…")
        subprocess.check_call([
            str(_python()),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--target",
            str(SITE_PACKAGES),
            "-r",
            str(ROOT / "requirements-voice.txt"),
        ])
        for filename in WHISPER_FILES:
            _download(f"{WHISPER_URL}/{filename}", WHISPER_DIR / filename)
        for filename in KOKORO_FILES:
            _download(f"{KOKORO_URL}/{filename}", KOKORO_DIR / filename)
        _verify_onnx()
        print("Voix de Sakura prête ✔")
        return 0
    except Exception as exc:
        print(f"Installation interrompue : {exc}", file=sys.stderr)
        return 1
    finally:
        _pause_if_needed()


if __name__ == "__main__":
    raise SystemExit(main())
