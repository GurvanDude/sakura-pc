"""Tests de l'API pywebview et du serveur statique."""

import http.client
import logging
import threading

import app
from app import Api, _serve
from sakura_ai.history import ChatHistory
from sakura_ai.tools import Tool


def test_api_ne_contient_que_des_attributs_prives(sakura_home):
    api = Api(history=ChatHistory(), logger=logging.getLogger("sakura.ai.test"))

    assert all(name.startswith("_") for name in vars(api))


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
