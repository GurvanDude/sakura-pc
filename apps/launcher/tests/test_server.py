def test_design_resolver_refuses_escape(launcher_modules, monkeypatch, tmp_path):
    _, launcher, _ = launcher_modules

    class FakeServer:
        server_address = ("127.0.0.1", 12345)
        daemon_threads = False

        def __init__(self, *_args, **_kwargs):
            pass

        def serve_forever(self):
            pass

    class FakeThread:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(launcher.socketserver, "ThreadingTCPServer", FakeServer)
    monkeypatch.setattr(launcher.threading, "Thread", FakeThread)
    launcher.serve(tmp_path)

    design = tmp_path / "design"
    design.mkdir()
    assert launcher.serve.resolve_path(design, "ui/sakura.css") == design / "ui" / "sakura.css"
    assert launcher.serve.resolve_path(design, "../secret.txt") is None
    assert launcher.serve.resolve_path(design, "%2e%2e/secret.txt") is None
