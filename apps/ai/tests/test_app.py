"""Tests de l'API pywebview et du serveur statique."""

import http.client
import logging

from app import Api, _serve
from sakura_ai.history import ChatHistory


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
