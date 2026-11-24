"""Tests de l'API pywebview et du serveur statique."""

import http.client
import json
import logging
import threading

import app
from app import Api, _serve
from sakura_ai.history import ChatHistory, ChatStore
from sakura_ai.tools import Tool


def test_api_ne_contient_que_des_attributs_prives(sakura_home):
    api = Api(history=ChatHistory(), logger=logging.getLogger("sakura.ai.test"))

    assert all(name.startswith("_") for name in vars(api))


def test_interface_utilise_la_sidebar_du_kit():
    html = (app.ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    javascript = (app.ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    css = (app.ROOT / "ui" / "style.css").read_text(encoding="utf-8")

    assert 'class="sk-layout app-layout"' in html
    assert 'class="sk-sidebar"' in html
    assert 'class="sk-sidebar-head"' in html
    assert 'class="sk-sidebar-list"' in html
    assert 'class="sk-layout-main app-content"' in html
    assert "sk-sidebar-item chat-row" in javascript
    assert "Sakura.sidebar(appLayout" in javascript
    assert "localStorage" not in javascript
    assert "sidebar-backdrop" not in html
    assert ".sidebar-open" not in css


def test_serveur_expose_design_sans_autoriser_les_sorties():
    server, port = _serve()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/design/ui/sakura.css")
        response = connection.getresponse()
        assert response.status == 200
        response.read()

        connection.request("GET", "/design/../core/paths.py")
        response = connection.getresponse()
        assert response.status == 404
        response.read()

        connection.request("GET", "/../app.py")
        response = connection.getresponse()
        assert response.status == 404
        response.read()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()


def test_confirmation_expire_sans_reponse(monkeypatch, sakura_home):
    api = Api(history=ChatHistory(), logger=logging.getLogger("sakura.ai.confirm.test"))
    scripts = []

    class Window:
        def evaluate_js(self, script):
            scripts.append(script)

    api._window = Window()
    monkeypatch.setattr(app, "CONFIRM_TIMEOUT", 0.01)
    tool = Tool(
        "close_app", "Ferme", {"type": "object"}, True,
        lambda **_args: {"ok": True}, lambda _args: "Fermé",
        lambda _args: {"title": "Fermer ?", "text": "Perte possible.", "yes": "Oui", "no": "Non"},
    )

    assert api._confirm(tool, {"name": "Discord"}) is False
    assert scripts and scripts[0].startswith('onConfirm("1", ')
    assert api._confirmations == {}


def test_confirmation_peut_etre_acceptee(sakura_home):
    api = Api(history=ChatHistory(), logger=logging.getLogger("sakura.ai.confirm.accept.test"))

    class Window:
        def evaluate_js(self, _script):
            threading.Timer(0.01, lambda: api.answer_confirm("1", True)).start()

    api._window = Window()
    tool = Tool(
        "close_app", "Ferme", {"type": "object"}, True,
        lambda **_args: {"ok": True}, lambda _args: "Fermé",
        lambda _args: {"title": "Fermer ?", "text": "Perte possible.", "yes": "Oui", "no": "Non"},
    )

    assert api._confirm(tool, {}) is True


def test_api_refuse_de_changer_la_conversation_pendant_une_reponse(sakura_home):
    store = ChatStore()
    first = store.create()
    store.append(first["id"], "user", "Première")
    second = store.create()
    store.append(second["id"], "user", "Deuxième")
    api = Api(store=store, logger=logging.getLogger("sakura.ai.busy.test"))
    api._current_id = first["id"]
    api._busy = True

    assert api.open_chat(second["id"]) == {
        "ok": False,
        "message": "Arrête d'abord la réponse en cours.",
    }
    assert api.new_chat() == {
        "ok": False,
        "message": "Arrête d'abord la réponse en cours.",
    }
    assert api.delete_chat(first["id"]) == {
        "ok": False,
        "message": "Arrête d'abord la réponse en cours.",
    }


def test_reglage_voix_preserve_toute_la_configuration(monkeypatch, sakura_home):
    from core import paths

    original = {
        "launcher": {"theme": "night"},
        "ai": {"model": "qwen3:14b", "autre": 7},
        "inconnue": [1, 2, 3],
    }
    paths.CONFIG.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(app.voice, "status", lambda: {"stt": True, "tts": True, "message": "Prête"})
    api = Api(history=ChatHistory(), logger=logging.getLogger("sakura.ai.voice.settings.test"))

    assert api.set_voice(True)["ok"] is True
    saved = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
    assert saved["launcher"] == original["launcher"]
    assert saved["inconnue"] == original["inconnue"]
    assert saved["ai"]["model"] == "qwen3:14b"
    assert saved["ai"]["autre"] == 7
    assert saved["ai"]["voice"] == {"enabled": True, "auto_send": True}


def test_reglage_voix_ne_recrit_pas_une_configuration_illisible(sakura_home):
    from core import paths

    paths.CONFIG.write_text("{cassé", encoding="utf-8")
    api = Api(history=ChatHistory(), logger=logging.getLogger("sakura.ai.voice.invalid.test"))

    assert api.set_voice(False)["ok"] is False
    assert paths.CONFIG.read_text(encoding="utf-8") == "{cassé"


def test_listen_start_refuse_une_deuxieme_ecoute(monkeypatch, sakura_home):
    release = threading.Event()

    class Listener:
        def listen(self, on_transcribing):
            release.wait(2)
            on_transcribing()
            return ""

        def stop(self):
            release.set()

    monkeypatch.setattr(app.voice, "status", lambda: {"stt": True, "tts": True, "message": "Prête"})
    api = Api(
        history=ChatHistory(),
        logger=logging.getLogger("sakura.ai.voice.listen.test"),
        listener=Listener(),
    )

    assert api.listen_start() == {"ok": True}
    assert api.listen_start() == {"ok": False, "message": "Je t'écoute déjà."}
    api.listen_stop()
    release.set()
