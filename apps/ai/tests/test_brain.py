"""Tests du dialogue Ollama sans accès réseau."""

import json
import threading
import urllib.error
import urllib.request

from sakura_ai import brain


class FakeResponse:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)

    def read(self):
        return b"".join(self.lines)


def ndjson(content="", done=False):
    return (json.dumps({"message": {"content": content}, "done": done}) + "\n").encode()


def test_filtre_think_avec_balises_coupees():
    filtering = brain.ThinkFilter()
    visible = [
        filtering.feed("Bonjour <thi"),
        filtering.feed("nk>raison secrète</thi"),
        filtering.feed("nk>Gurvan !"),
        filtering.finish(),
    ]
    assert "".join(visible) == "Bonjour Gurvan !"


def test_chat_stream_parse_le_ndjson_et_le_corps(monkeypatch, sakura_home):
    captured = {}
    response = FakeResponse([
        ndjson("Salut "),
        ndjson("<think>non</think>Gurvan"),
        ndjson(done=True),
    ])

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    chunks = []
    result = brain.chat_stream(
        [{"role": "user", "content": "Bonjour"}],
        chunks.append,
        threading.Event(),
    )

    assert result == "Salut Gurvan"
    assert "".join(chunks) == result
    payload = json.loads(captured["request"].data)
    assert payload["model"] == "qwen3:14b"
    assert payload["stream"] is True
    assert payload["think"] is False
    assert payload["messages"][0]["role"] == "system"


def test_chat_stream_sarrete_proprement(monkeypatch, sakura_home):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse([ndjson("premier"), ndjson(" second"), ndjson(done=True)]),
    )
    stop = threading.Event()
    chunks = []

    def receive(text):
        chunks.append(text)
        stop.set()

    result = brain.chat_stream([], receive, stop)
    assert result == "premier"
    assert chunks == ["premier"]


def test_is_ready_serveur_absent(monkeypatch, sakura_home):
    def unavailable(*_args, **_kwargs):
        raise urllib.error.URLError("absent")

    monkeypatch.setattr(urllib.request, "urlopen", unavailable)
    assert brain.is_ready() == (
        False,
        "Ollama n'est pas lancé. Ouvre l'appli Ollama puis réessaie.",
    )


def test_is_ready_modele_absent(monkeypatch, sakura_home):
    payload = json.dumps({"models": [{"name": "autre:latest"}]}).encode()
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse([payload]),
    )
    assert brain.is_ready() == (False, "Le modèle qwen3:14b n'est pas téléchargé.")


def test_modele_lu_dans_la_configuration(sakura_home):
    from core import paths

    paths.CONFIG.write_text('{"ai": {"model": "gemma3:12b"}}', encoding="utf-8")
    assert brain.model_name() == "gemma3:12b"


def test_conversation_limitee_aux_derniers_messages():
    messages = [{"role": "user", "content": str(index)} for index in range(40)]
    trimmed = brain._trim_messages(messages)
    assert len(trimmed) == 31
    assert trimmed[0]["role"] == "system"
    assert trimmed[1]["content"] == "10"

