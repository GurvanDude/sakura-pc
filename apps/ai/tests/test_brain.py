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


def ndjson_tool(name, arguments, done=True):
    return (json.dumps({
        "message": {"content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]},
        "done": done,
    }) + "\n").encode()


class FakeTool:
    def __init__(self, risky=False):
        self.risky = risky


class FakeTools:
    def __init__(self, risky=False, on_run=None):
        self.tool = FakeTool(risky)
        self.calls = []
        self.on_run = on_run

    def schemas(self):
        return [{"type": "function", "function": {"name": "demo", "description": "Démo", "parameters": {"type": "object"}}}]

    def get(self, name):
        return self.tool if name == "demo" else None

    def run(self, name, args):
        self.calls.append((name, args))
        if self.on_run:
            self.on_run()
        return {"ok": True, "message": "fait"}

    def describe(self, name, args):
        return f"Action {args.get('value')}"


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


def test_make_title_nettoie_la_reponse(monkeypatch, sakura_home):
    payload = json.dumps({"message": {"content": "« Ranger les fichiers Sakura. »"}}).encode()
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        return FakeResponse([payload])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert brain.make_title("Comment ranger mes fichiers ?", "Voici comment.") == "Ranger les fichiers Sakura"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["think"] is False


def test_make_title_se_replie_sur_la_question(monkeypatch, sakura_home):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError("absent")),
    )

    title = brain.make_title(
        "Comment organiser proprement tous les très anciens fichiers de mon ordinateur ?",
        "",
    )

    assert len(title) <= 40
    assert title == "Comment organiser proprement tous les"


def test_conversation_limitee_aux_derniers_messages():
    messages = [{"role": "user", "content": str(index)} for index in range(40)]
    trimmed = brain._trim_messages(messages)
    assert len(trimmed) == 31
    assert trimmed[0]["role"] == "system"
    assert trimmed[1]["content"] == "10"


def test_boucle_outil_puis_reponse(monkeypatch, sakura_home):
    responses = iter([
        FakeResponse([ndjson_tool("demo", {"value": 7})]),
        FakeResponse([ndjson("C'est fait.", done=True)]),
    ])
    requests = []

    def fake_urlopen(request, **_kwargs):
        requests.append(json.loads(request.data))
        return next(responses)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    tools = FakeTools()
    actions = []
    result = brain.chat_stream([], lambda _text: None, threading.Event(), tools, lambda *_args: True, actions.append)

    assert result == "C'est fait."
    assert tools.calls == [("demo", {"value": 7})]
    assert actions == ["Action 7"]
    assert requests[0]["tools"] == tools.schemas()
    assert requests[1]["messages"][-1] == {
        "role": "tool", "tool_name": "demo", "content": '{"ok": true, "message": "fait"}',
    }


def test_outil_risque_refuse(monkeypatch, sakura_home):
    responses = iter([
        FakeResponse([ndjson_tool("demo", {"value": 1})]),
        FakeResponse([ndjson("D'accord, je le laisse ouvert.", done=True)]),
    ])
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: next(responses))
    tools = FakeTools(risky=True)

    result = brain.chat_stream([], lambda _text: None, threading.Event(), tools, lambda *_args: False)

    assert result == "D'accord, je le laisse ouvert."
    assert tools.calls == []


def test_limite_de_quatre_tours_outils(monkeypatch, sakura_home):
    responses = iter(FakeResponse([ndjson_tool("demo", {"value": index})]) for index in range(5))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: next(responses))
    tools = FakeTools()
    chunks = []

    result = brain.chat_stream([], chunks.append, threading.Event(), tools, lambda *_args: True)

    assert len(tools.calls) == 4
    assert "limite de quatre tours" in result


def test_stop_interrompt_aussi_la_boucle_outils(monkeypatch, sakura_home):
    stop = threading.Event()
    opened = 0

    def fake_urlopen(*_args, **_kwargs):
        nonlocal opened
        opened += 1
        return FakeResponse([ndjson_tool("demo", {})])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    tools = FakeTools(on_run=stop.set)
    brain.chat_stream([], lambda _text: None, stop, tools, lambda *_args: True)

    assert opened == 1
    assert len(tools.calls) == 1

