import json
from pathlib import Path


def test_color_helpers(lights_module):
    assert lights_module.hex2rgb('#ff5fa8') == (255, 95, 168)
    assert lights_module.mix((0, 10, 20), (10, 30, 50), .5) == (5, 20, 35)
    assert lights_module.scale((10, 20, 30), .25) == (2.5, 5, 7.5)


def test_every_effect_returns_a_valid_rgb_tuple(lights_module):
    for effect_name in lights_module.EFFECTS:
        color = lights_module.Lights.effect_color(
            effect_name, .3, 2, 8, 12.5,
            {'a': '#ff46a5', 'b': '#195aff', 'speed': 1, '_key': 'test'},
        )
        assert isinstance(color, tuple), effect_name
        assert len(color) == 3, effect_name
        assert all(isinstance(channel, (int, float)) for channel in color), effect_name
        assert all(0 <= channel <= 255 for channel in color), effect_name


def test_apply_and_live_do_not_write_config_but_save_does(lights_module):
    original = lights_module.CONFIG.read_text(encoding='utf-8')
    controller = lights_module.Lights()
    payload = {
        'programs': {'day': {'ram1': {'effect': 'static', 'a': '#123456'}}},
        'zones': {'ram1': {'name': 'Mémoire'}},
        'scenes': {},
    }

    controller.apply(payload, (7, 19))
    assert lights_module.CONFIG.read_text(encoding='utf-8') == original

    controller.live(payload)
    assert lights_module.CONFIG.read_text(encoding='utf-8') == original

    controller.save(payload)
    written = json.loads(lights_module.CONFIG.read_text(encoding='utf-8'))
    assert written['lights'] == payload


def test_design_path_stays_inside_design(lights_module, tmp_path):
    design = tmp_path / 'design'
    design.mkdir()
    expected = design / 'ui' / 'sakura.js'

    assert lights_module.resolve_design_path('/design/ui/sakura.js', design) == expected.resolve()
    assert lights_module.resolve_design_path('/other/ui/sakura.js', design) is None
    assert lights_module.resolve_design_path('/design/../config.json', design) is None
    assert lights_module.resolve_design_path('/design/%2e%2e/config.json', design) is None
    assert lights_module.resolve_design_path('/design/%2e%2e%5cconfig.json', design) is None


def test_studio_uses_sakura_kit_and_window_api():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'ui' / 'studio.html').read_text(encoding='utf-8')
    studio = (root / 'studio.py').read_text(encoding='utf-8')

    assert 'href="/design/tokens.css"' in html
    assert 'href="/design/ui/sakura.css"' in html
    assert 'src="/design/ui/sakura.js"' in html
    assert 'Sakura.titlebar' in html
    assert 'Sakura.tabs' in html
    assert 'Sakura.savebar' in html
    assert 'Sakura.toast' in html
    assert 'frameless=True' in studio
    assert 'easy_drag=False' in studio
    assert 'js_api=api' in studio


def test_guard_restarts_service_that_died_after_cancelled_shutdown(lights_module):
    states = iter([True, False])
    restarts = []
    assert lights_module.guard(1, alive=lambda pid: next(states), restart=lambda: restarts.append(1),
                               sleep=lambda s: None, seconds=60) is True
    assert restarts == [1]


def test_guard_leaves_running_service_alone(lights_module):
    restarts = []
    assert lights_module.guard(1, alive=lambda pid: True, restart=lambda: restarts.append(1),
                               sleep=lambda s: None, seconds=60) is False
    assert restarts == []


def test_park_starts_guard_once(lights_module, monkeypatch):
    started = []
    monkeypatch.setattr(lights_module, 'start_guard', started.append)
    controller = lights_module.Lights()
    controller.park()
    controller.park()
    assert len(started) == 1


def test_process_alive_sees_itself(lights_module):
    import os
    assert lights_module.process_alive(os.getpid()) is True


def test_open_icue_launches_the_configured_exe(lights_module, tmp_path):
    exe = tmp_path / 'iCUE.exe'
    exe.write_bytes(b'')
    config = json.loads(lights_module.CONFIG.read_text(encoding='utf-8'))
    config['settings']['icue'] = str(exe)
    lights_module.CONFIG.write_text(json.dumps(config), encoding='utf-8')
    calls = []
    assert lights_module.open_icue(popen=lambda args, **kw: calls.append(args)) is True
    assert calls == [[str(exe)]]


def test_open_icue_says_no_when_missing(lights_module, tmp_path):
    config = json.loads(lights_module.CONFIG.read_text(encoding='utf-8'))
    config['settings']['icue'] = str(tmp_path / 'absent.exe')
    lights_module.CONFIG.write_text(json.dumps(config), encoding='utf-8')
    assert lights_module.open_icue(popen=lambda *a, **k: None) is False
