"""Tests de la voix locale sans micro, haut-parleur ni modèle installé."""

from __future__ import annotations

import math
import threading

from sakura_ai import voice


def test_sentence_splitter_gere_les_morceaux_et_abreviations():
    splitter = voice.SentenceSplitter()

    assert splitter.feed("Bonjour M.") == []
    assert splitter.feed(" Dupont. La valeur est 3.") == ["Bonjour M. Dupont."]
    assert splitter.feed("5, etc. puis tout va bien ! Reste") == [
        "La valeur est 3.5, etc. puis tout va bien !",
    ]
    assert splitter.flush() == ["Reste"]


def test_sentence_splitter_reconnait_deux_points_ellipse_et_retour_ligne():
    splitter = voice.SentenceSplitter()

    assert splitter.feed("Voilà : ensuite…\nDernier") == ["Voilà :", "ensuite…"]
    assert splitter.flush() == ["Dernier"]


def test_clean_for_speech_retire_markdown_liens_emojis_et_actions():
    source = """# **Bonjour** *Gurvan* 🌸
- Va sur [Sakura](https://example.test) puis lis `ce texte`.
✦ Application ouverte
```python
print('silence')
```"""

    assert voice.clean_for_speech(source) == "Bonjour Gurvan\nVa sur Sakura puis lis ce texte."


class _Array:
    def __init__(self, values):
        self.values = [float(value) for value in values]

    @property
    def size(self):
        return len(self.values)

    def reshape(self, *_shape):
        return self

    def copy(self):
        return _Array(self.values)

    def astype(self, *_args, **_kwargs):
        return self


class _Numpy:
    float32 = "float32"

    @staticmethod
    def asarray(data, dtype=None):
        del dtype
        return data if isinstance(data, _Array) else _Array(data)

    @staticmethod
    def square(data):
        return _Array(value * value for value in data.values)

    @staticmethod
    def mean(data):
        return sum(data.values) / len(data.values) if data.values else 0.0

    sqrt = staticmethod(math.sqrt)

    @staticmethod
    def concatenate(chunks):
        return _Array(value for chunk in chunks for value in chunk.values)


class _InputStream:
    def __init__(self, blocks, **_kwargs):
        self._blocks = iter(blocks)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _blocksize):
        return _Array(next(self._blocks)), False


class _SoundDevice:
    def __init__(self, blocks):
        self._blocks = blocks

    def InputStream(self, **kwargs):
        return _InputStream(self._blocks, **kwargs)


class _Whisper:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append((audio, options))
        return [type("Segment", (), {"text": " Bonjour Sakura "})()], None


def test_listener_sarrete_apres_une_seconde_de_silence():
    # Trois blocs de calibration, deux de parole, puis dix blocs silencieux.
    blocks = [[0.001] * 10] * 3 + [[0.2] * 10] * 2 + [[0.0] * 10] * 10 + [[0.3] * 10]
    model = _Whisper()
    listener = voice.Listener(
        sounddevice_module=_SoundDevice(blocks),
        numpy_module=_Numpy(),
        model_factory=lambda *_args, **_kwargs: model,
        sample_rate=100,
        block_seconds=0.1,
        max_seconds=3,
    )

    assert listener.listen() == "Bonjour Sakura"
    options = model.calls[0][1]
    assert {key: options[key] for key in ("language", "vad_filter", "beam_size")} == {"language": "fr", "vad_filter": True, "beam_size": 1}
    assert "Gurvan" in options["initial_prompt"]
    assert model.calls[0][0].size == 150


class _BlockingKokoro:
    def __init__(self, started, release):
        self._started = started
        self._release = release

    def create(self, _text, **_options):
        self._started.set()
        self._release.wait(2)
        return [0.0], 24_000


class _Playback:
    def __init__(self):
        self.stopped = False

    def play(self, *_args):
        pass

    def wait(self):
        pass

    def stop(self):
        self.stopped = True


def test_speaker_stop_vide_la_file_et_coupe_le_son():
    started = threading.Event()
    release = threading.Event()
    playback = _Playback()
    speaker = voice.Speaker(
        sounddevice_module=playback,
        kokoro_factory=lambda *_args: _BlockingKokoro(started, release),
    )
    speaker.speak("Première phrase.")
    assert started.wait(1)
    speaker.speak("Deuxième phrase.")

    speaker.stop()
    assert speaker._queue.empty()
    assert playback.stopped is True
    release.set()


def test_status_indique_que_la_voix_nest_pas_installee(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "WHISPER_DIR", tmp_path / "whisper")
    monkeypatch.setattr(voice, "KOKORO_MODEL", tmp_path / "kokoro.onnx")
    monkeypatch.setattr(voice, "KOKORO_VOICES", tmp_path / "voices.bin")
    monkeypatch.setattr(voice, "_importable", lambda _name: False)

    assert voice.status() == {"stt": False, "tts": False, "message": voice.NOT_INSTALLED}
