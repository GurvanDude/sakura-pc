"""Voix locale de Sakura, avec dépendances chargées uniquement à la demande."""

from __future__ import annotations

import importlib
import queue
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
SITE_PACKAGES = VENDOR / "site-packages"
WHISPER_DIR = VENDOR / "models" / "whisper-small"
KOKORO_DIR = VENDOR / "models" / "kokoro"
WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"
NOT_INSTALLED = "La voix n'est pas encore installée. Lance apps/ai/tools/setup_voice.py."


def vendor_path() -> Path:
    """Donne priorité aux paquets privés de Sakura s'ils sont installés."""
    path = str(SITE_PACKAGES)
    if SITE_PACKAGES.is_dir() and (not sys.path or sys.path[0] != path):
        while path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
        importlib.invalidate_caches()
    return SITE_PACKAGES


def _importable(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def status() -> dict[str, Any]:
    vendor_path()
    audio_packages = _importable("sounddevice") and _importable("numpy")
    stt = audio_packages and _importable("faster_whisper") and all(
        (WHISPER_DIR / name).is_file() and (WHISPER_DIR / name).stat().st_size > 0
        for name in WHISPER_FILES
    )
    tts = audio_packages and _importable("kokoro_onnx") and _importable("onnxruntime") and all(
        path.is_file() and path.stat().st_size > 0 for path in (KOKORO_MODEL, KOKORO_VOICES)
    )
    return {
        "stt": bool(stt),
        "tts": bool(tts),
        "message": "La voix de Sakura est prête." if stt and tts else NOT_INSTALLED,
    }


class SentenceSplitter:
    """Assemble un flux de texte et livre uniquement ses phrases terminées."""

    _abbreviations = {"m", "mme", "mlle", "mr", "dr", "pr", "etc", "ex", "env", "p", "pp"}

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, chunk: str) -> list[str]:
        if chunk:
            self._buffer += str(chunk)
        return self._extract(final=False)

    def flush(self) -> list[str]:
        sentences = self._extract(final=True)
        tail = self._buffer.strip()
        self._buffer = ""
        if tail:
            sentences.append(tail)
        return sentences

    def _period_is_boundary(self, index: int, final: bool) -> bool:
        before = self._buffer[:index]
        after = self._buffer[index + 1:]
        if before[-1:].isdigit() and after[:1].isdigit():
            return False
        word_match = re.search(r"([A-Za-zÀ-ÖØ-öø-ÿ]+)$", before)
        word = word_match.group(1).casefold() if word_match else ""
        if word in self._abbreviations:
            if word != "etc":
                return False
            next_match = re.search(r"\S", after)
            if next_match and after[next_match.start()].islower():
                return False
        if not after and not final:
            return False
        return True

    def _extract(self, final: bool) -> list[str]:
        sentences: list[str] = []
        start = 0
        index = 0
        while index < len(self._buffer):
            char = self._buffer[index]
            boundary = char in "!?…:\n"
            if char == ".":
                boundary = self._period_is_boundary(index, final)
            if not boundary:
                index += 1
                continue
            end = index + 1
            while end < len(self._buffer) and self._buffer[end] in ".!?…":
                end += 1
            sentence = self._buffer[start:end].strip()
            if sentence:
                sentences.append(sentence)
            while end < len(self._buffer) and self._buffer[end].isspace():
                end += 1
            start = end
            index = end
        self._buffer = self._buffer[start:]
        return sentences


def clean_for_speech(text: str) -> str:
    """Transforme une réponse Markdown en texte naturel à prononcer."""
    value = str(text or "").replace("\r\n", "\n")
    value = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    value = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", value)
    value = re.sub(r"https?://\S+|www\.\S+", "", value, flags=re.IGNORECASE)
    kept: list[str] = []
    for line in value.splitlines():
        if re.match(r"^\s*(?:✦|⚙|🩺|▶|\[?action\]?\s*:)", line, flags=re.IGNORECASE):
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*(?:[-+*•]|\d+[.)])\s+", "", line)
        kept.append(line)
    value = "\n".join(kept)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"(\*\*|__|~~)(.*?)\1", r"\2", value)
    value = re.sub(r"(?<!\w)[*_](.*?)[*_](?!\w)", r"\1", value)
    value = re.sub(
        "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U0001F1E6-\U0001F1FF]",
        "",
        value,
    )
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n+ *", "\n", value)
    return value.strip()


class Listener:
    """Enregistre une demande puis la transcrit localement."""

    def __init__(
        self,
        sounddevice_module: Any = None,
        numpy_module: Any = None,
        model_factory: Callable[..., Any] | None = None,
        sample_rate: int = 16_000,
        silence_seconds: float = 1.0,
        max_seconds: float = 30.0,
        calibration_seconds: float = 0.3,
        block_seconds: float = 0.1,
    ) -> None:
        self._sounddevice = sounddevice_module
        self._numpy = numpy_module
        self._model_factory = model_factory
        self._sample_rate = sample_rate
        self._silence_seconds = silence_seconds
        self._max_seconds = max_seconds
        self._calibration_seconds = calibration_seconds
        self._block_seconds = block_seconds
        self._stop = threading.Event()
        self._model: Any = None
        self._model_lock = threading.Lock()

    def stop(self) -> None:
        self._stop.set()

    def _dependencies(self) -> tuple[Any, Any]:
        vendor_path()
        sounddevice = self._sounddevice or importlib.import_module("sounddevice")
        numpy = self._numpy or importlib.import_module("numpy")
        return sounddevice, numpy

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                factory = self._model_factory
                if factory is None:
                    factory = importlib.import_module("faster_whisper").WhisperModel
                self._model = factory(str(WHISPER_DIR), device="cpu", compute_type="int8")
        return self._model

    def listen(self, on_transcribing: Callable[[], None] | None = None) -> str:
        sounddevice, numpy = self._dependencies()
        self._stop.clear()
        blocksize = max(1, int(self._sample_rate * self._block_seconds))
        max_blocks = max(1, round(self._max_seconds / self._block_seconds))
        calibration_blocks = max(1, round(self._calibration_seconds / self._block_seconds))
        silence_blocks_needed = max(1, round(self._silence_seconds / self._block_seconds))
        chunks: list[Any] = []
        calibration: list[float] = []
        silence_blocks = 0

        with sounddevice.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            for _ in range(max_blocks):
                if self._stop.is_set():
                    break
                data, _overflowed = stream.read(blocksize)
                mono = numpy.asarray(data, dtype=numpy.float32).reshape(-1).copy()
                chunks.append(mono)
                rms = float(numpy.sqrt(numpy.mean(numpy.square(mono)))) if mono.size else 0.0
                if len(calibration) < calibration_blocks:
                    calibration.append(rms)
                    continue
                baseline = sum(calibration) / len(calibration)
                threshold = max(0.006, baseline * 2.5)
                if rms >= threshold:
                    silence_blocks = 0
                else:
                    silence_blocks += 1
                    if silence_blocks >= silence_blocks_needed:
                        break

        if on_transcribing is not None:
            on_transcribing()
        if not chunks:
            return ""
        audio = numpy.concatenate(chunks).astype(numpy.float32, copy=False)
        segments, _info = self._load_model().transcribe(
            audio,
            language="fr",
            vad_filter=True,
            beam_size=1,
            # indice pour bien écrire les noms propres (sinon « gurevant »)
            initial_prompt="Gurvan parle à Sakura, son assistante sur son PC.",
        )
        return " ".join(str(segment.text).strip() for segment in segments if str(segment.text).strip()).strip()

    transcribe = listen


class Speaker:
    """Prononce les phrases en ordre sur un unique fil de lecture."""

    def __init__(
        self,
        sounddevice_module: Any = None,
        kokoro_factory: Callable[..., Any] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._sounddevice = sounddevice_module
        self._kokoro_factory = kokoro_factory
        self._on_error = on_error
        self._kokoro: Any = None
        self._kokoro_lock = threading.Lock()
        self._queue: queue.Queue[tuple[int, str]] = queue.Queue()
        self._generation = 0
        self._generation_lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="sakura-ai-speaker")
        self._thread.start()

    def speak(self, text: str) -> None:
        cleaned = str(text or "").strip()
        if not cleaned:
            return
        with self._generation_lock:
            generation = self._generation
        self._queue.put((generation, cleaned))

    enqueue = speak

    def stop(self) -> None:
        with self._generation_lock:
            self._generation += 1
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        try:
            (self._sounddevice or importlib.import_module("sounddevice")).stop()
        except Exception:
            pass

    def _engine(self) -> Any:
        if self._kokoro is not None:
            return self._kokoro
        with self._kokoro_lock:
            if self._kokoro is None:
                vendor_path()
                factory = self._kokoro_factory
                if factory is None:
                    factory = importlib.import_module("kokoro_onnx").Kokoro
                self._kokoro = factory(str(KOKORO_MODEL), str(KOKORO_VOICES))
        return self._kokoro

    def _worker(self) -> None:
        while True:
            generation, text = self._queue.get()
            try:
                with self._generation_lock:
                    if generation != self._generation:
                        continue
                samples, sample_rate = self._engine().create(
                    text,
                    voice="ff_siwis",
                    speed=1.0,
                    lang="fr-fr",
                )
                with self._generation_lock:
                    if generation != self._generation:
                        continue
                sounddevice = self._sounddevice or importlib.import_module("sounddevice")
                sounddevice.play(samples, sample_rate)
                sounddevice.wait()
            except Exception as exc:
                if self._on_error is not None:
                    self._on_error(exc)
            finally:
                self._queue.task_done()
