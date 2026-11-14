"""Sakura Launcher : deux fenêtres plein écran (une par écran) qui affichent l'interface de ui/,
puis lancent le jeu et les applis choisis, les rangent, et se ferment quand tout est prêt.

    pythonw launcher.py            lancement normal (c'est ce que le démarrage de Windows exécute)
    python launcher.py --debug     avec les outils de développement
    python launcher.py --dry       essai à blanc : toute l'interface, mais rien n'est lancé
    pythonw launcher.py --shell    mode « coquille » : lancé par Windows à la place du bureau (voir tools/shell_mode.py) ;
                                   le launcher démarre le bureau lui-même, caché derrière lui
    python launcher.py --data      régénère seulement ui/data.js depuis config.json (pour l'aperçu)
"""
import datetime
import functools
import http.server
import json
import logging
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # racine du dépôt, pour core/
from core import paths  # noqa: E402

ROOT = Path(__file__).resolve().parent
CONFIG = paths.CONFIG
sys.path.insert(0, str(paths.app('lights')))       # « import lights »
logging.basicConfig(filename=paths.log('launcher'), level=logging.INFO, encoding='utf-8',
                    format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('sakura')


def load_config():
    if not CONFIG.exists():                       # premier lancement : on part de l'exemple
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text((ROOT / 'config.example.json').read_text(encoding='utf-8'), encoding='utf-8')
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')


def write_data_js(cfg):
    """L'interface ne voit que ce dont elle a besoin (noms, images) ; les commandes restent côté Python."""
    pick = lambda it, keys: {k: it[k] for k in keys if k in it}
    data = {
        'games': [pick(g, ('id', 'name', 'cover')) for g in cfg['games']],
        'apps': [pick(a, ('id', 'name', 'sub', 'icon')) for a in cfg['apps']],
        'classic': [pick(c, ('id', 'name', 'icon')) for c in cfg['classic']],
        'recent': cfg.get('recent', []),
        'name': cfg['settings'].get('welcome_name', ''),
    }
    bg = {theme: {screen: [name] for screen, name in d.items()} for theme, d in cfg['settings']['backgrounds'].items()}
    (paths.USER / 'data.js').write_text(
        '// Généré automatiquement depuis config.json par launcher.py : modifier config.json, pas ce fichier.\n'
        f'window.LAUNCHER_DATA = {json.dumps(data, ensure_ascii=False, indent=2)};\n'
        f'window.LAUNCHER_BG = {json.dumps(bg, indent=2)};\n', encoding='utf-8')


def serve(root):
    """Petit serveur local pour l'interface (127.0.0.1 uniquement, port libre au hasard)."""
    import urllib.parse

    def resolve_path(base, relative):
        """Résout un chemin web sous base, ou renvoie None s'il essaie d'en sortir."""
        base = Path(base).resolve()
        candidate = (base / urllib.parse.unquote(relative).replace('\\', '/').lstrip('/')).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate

    serve.resolve_path = resolve_path

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def translate_path(self, path):
            # ce qui est propre à ce PC vient du dossier utilisateur (data.js, jaquettes, icônes d'applis)
            clean = path.split('?', 1)[0].split('#', 1)[0]
            if clean.startswith('/design/'):
                design_root = paths.REPO / 'design'
                target = resolve_path(design_root, clean[len('/design/'):])
                return str(target if target is not None else design_root / '.forbidden')
            if clean == '/ui/data.js':
                return str(paths.USER / 'data.js')
            for web, sub in (('/ui/assets/covers/', 'covers'), ('/ui/assets/icons/', 'icons')):
                if clean.startswith(web):
                    mine = paths.USER / sub / clean[len(web):]
                    if mine.exists():
                        return str(mine)
            return super().translate_path(path)

    srv = socketserver.ThreadingTCPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(root)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def slug(text, taken):
    s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-') or 'perso'
    base, n = s, 2
    while s in taken:
        s, n = f'{base}-{n}', n + 1
    return s


class Api:
    """Fonctions appelées depuis l'interface (window.pywebview.api.*), une instance par écran."""

    def __init__(self, app, screen):
        self._app, self._screen = app, screen

    def broadcast(self, screen, msg):
        self._app.send(msg, exclude=screen)

    def launch(self, plan):
        threading.Thread(target=self._app.run_plan, args=(plan,), daemon=True).start()

    def close(self):
        self._app.close_window(self._screen)

    def quit(self):
        self._app._wait_wallpaper()
        for name in list(self._app.windows):
            self._app.close_window(name)

    def rgb(self, do, theme=None):
        """Lumières du PC : off, storm, flash, theme, auto (voir lights.py)."""
        import lights
        lights.send(do, theme)

    def set_recent(self, ids):
        self._app.cfg['recent'] = ids[:100]
        save_config(self._app.cfg)

    def add_item(self, screen):
        return self._app.add_item(screen)


class App:
    def __init__(self, engine, dry=False, shell=False):
        self.engine, self.dry, self.shell = engine, dry, shell
        self.covers = []           # (fenêtre Windows du launcher, rectangle de son écran)
        self.sweeper = None        # mode coquille : ferme les applis qui démarrent sans qu'on les ait choisies
        self.cfg = load_config()
        # jeux installés ou désinstallés depuis la dernière fois (Steam, Epic)
        try:
            import library
            missing_covers, changed = library.sync(self.cfg)
            if changed:
                save_config(self.cfg)
            library.fetch_covers(missing_covers, lambda: (save_config(self.cfg), write_data_js(self.cfg)))
        except Exception:
            log.exception('synchronisation de la bibliothèque')
        write_data_js(self.cfg)
        self.windows, self.closed = {}, set()
        self.launching = False      # vrai pendant un lancement : le launcher reste devant tout
        self.result = ([], None)   # (fenêtres d'applis de la moins prioritaire à la n°1, fenêtre à mettre au premier plan)
        self.main_rect = self.side_rect = None

    # ---------------------------------------------------------------- fenêtres de l'interface
    def open(self, webview, debug):
        s = self.cfg['settings']
        hour = datetime.datetime.now().hour
        theme = 'day' if s['day_start'] <= hour < s['day_end'] else 'night'
        screens = list(webview.screens)
        main = next((sc for sc in screens if sc.x == 0 and sc.y == 0), screens[0])
        side = next((sc for sc in screens if sc is not main), None)
        self.main_rect = (main.x, main.y, main.width, main.height)
        self.side_rect = side and (side.x, side.y, side.width, side.height)
        port = serve(ROOT)
        qs = f'theme={theme}&mainW={main.width}&sideW={side.width if side else 0}&hold=1'
        bg = '#fff7fa' if theme == 'day' else '#07050e'
        for name, sc in (('apps', side), ('games', main)):
            if not sc:
                continue
            w = webview.create_window(
                'Sakura Launcher', f'http://127.0.0.1:{port}/ui/screen.html?screen={name}&{qs}', js_api=Api(self, name),
                screen=sc, fullscreen=True, frameless=True, easy_drag=False, resizable=False,
                shadow=False, on_top=not debug, focus=name == 'games', background_color=bg)
            if not debug:
                # plein écran « au-dessus de tout », barre des tâches comprise
                rect = (sc.x, sc.y, sc.width, sc.height)
                w.events.shown += functools.partial(self._cover, w, rect)
            self.windows[name] = w
        log.info('ouverture, thème %s, écrans %s / %s', theme, self.main_rect, self.side_rect)
        # pendant que le launcher est affiché, seuls ses propres sons s'entendent
        self.muter = self.engine.Muter(os.getpid(), paths.USER / '.muted.json')
        self.muter.start()

    def _cover(self, window, rect):
        try:
            hwnd = window.native.Handle.ToInt32()
            self.engine.cover(hwnd, rect)
            self.covers.append((hwnd, rect))
        except Exception:
            log.exception('plein écran')
        if self.shell and len(self.covers) == len(self.windows):
            # les deux écrans du launcher sont affichés : l'écran Bienvenue de Windows peut s'effacer
            log.info('signal « coquille prête » : %s', self.engine.signal_shell_ready())
        if self.shell and len(self.covers) == 1:
            threading.Thread(target=self._shell_boot, daemon=True).start()
        if len(self.covers) == len(self.windows):
            threading.Thread(target=self._release_intro, daemon=True).start()

    def _release_intro(self):
        """Le message de bienvenue reste au moins 3,2 s, et jusqu'à ce que les lumières soient prêtes (35 s au plus : iCUE peut mettre 20 s à voir la RAM) :
        la tempête part alors en même temps à l'écran et sur le PC."""
        import lights
        start = time.time()
        while time.time() - start < 35 and not lights.ready():
            time.sleep(.3)
        log.info('lumières %s après %.1f s', 'prêtes' if lights.ready() else 'pas prêtes', time.time() - start)
        time.sleep(max(0, 3.2 - (time.time() - start)))
        self.send({'type': 'intro'})

    def _shell_boot(self):
        """Mode coquille : le bureau (explorer) et les applis de fond démarrent maintenant, cachés derrière le launcher.
        Tant que le launcher est affiché, on le remet au-dessus de tout (la barre des tâches qui apparaît
        voudrait passer devant)."""
        self.sweeper = self.engine.Sweeper(self.cfg['settings'].get('boot_block', []))
        self.sweeper.start()
        time.sleep(1.5)
        start_explorer()
        for item in self.cfg['settings'].get('always', []):
            try:
                self.engine.start(item['launch'], self.cfg['settings']['browser'])
            except Exception:
                log.exception('démarrage de fond : %s', item.get('name'))
        while len(self.closed) < len(self.windows):
            for hwnd, rect in self.covers:
                if self.engine.alive(hwnd):
                    self.engine.cover(hwnd, rect, activate=False)
            time.sleep(.7)

    def send(self, msg, exclude=None):
        js = f'window.__sakuraReceive({json.dumps(msg, ensure_ascii=False)})'
        for name, w in list(self.windows.items()):
            if name != exclude and name not in self.closed:
                try:
                    w.evaluate_js(js)
                except Exception as e:  # fenêtre en train de se fermer
                    log.warning('envoi vers %s impossible : %s', name, e)

    def close_window(self, name):
        if name in self.closed:
            return
        self.closed.add(name)
        if self.sweeper and len(self.closed) == len(self.windows):
            self.sweeper.launcher_closed()
        self.windows[name].destroy()

    # ---------------------------------------------------------------- lancement
    def _allow(self, entry):
        """Ce que le launcher lance lui-même ne doit pas être fermé par le Sweeper."""
        if not self.sweeper:
            return
        launch = entry.get('launch', {})
        names = [entry.get('process')]
        if 'exe' in launch:
            names.append(os.path.basename(launch['exe']))
        uri = launch.get('uri', '')
        if uri.startswith('steam://'):
            names += ['steam.exe', 'steamwebhelper.exe']
        elif uri.startswith('com.epicgames'):
            names.append('epicgameslauncher.exe')
        self.sweeper.allow(names)

    def run_plan(self, plan):
        if self.dry:
            return self._dry_run(plan)
        e, s = self.engine, self.cfg['settings']
        browser = s['browser']
        kind = plan.get('kind')
        log.info('plan %s : %s', kind, [st['id'] for st in plan.get('steps', [])])
        self.launching = True
        threading.Thread(target=self._keep_covers, daemon=True).start()
        try:
            if kind == 'music':
                m = self.cfg['music']
                self._allow(m)
                e.start(m['launch'], browser)
                w = e.wait_window(m.get('process'), timeout=s['game_timeout'])
                time.sleep(2)
                self.result = ([], w and w.hwnd)
            elif kind == 'classic':
                for c in self.cfg['classic']:
                    self._allow(c)
                    try:
                        e.start(c['launch'], browser)
                    except Exception:
                        log.exception('lancement classique : %s', c['id'])
                    time.sleep(.4)
                time.sleep(4)
                self.result = ([], None)
            else:
                self.result = self._go(plan, browser, s)
        except Exception:
            log.exception('erreur pendant le lancement')
        self._wait_wallpaper()
        self.ready()

    def ready(self):
        """Tout est lancé : l'interface joue sa fermeture, et les lumières la sortie de leur « C'est parti »."""
        import lights
        self.launching = False
        lights.send('flash_end')
        self.send({'type': 'ready'})

    def _keep_covers(self):
        """Pendant les lancements, aucune appli ne doit passer devant le launcher (écrans de démarrage…)."""
        while self.launching:
            self.engine.cover_all(self.covers)
            time.sleep(.05)

    def _wait_wallpaper(self):
        """On ne rend la main qu'avec le fond d'écran animé déjà en place (sans rien afficher de plus)."""
        if self.shell:
            ok = self.engine.wait_wallpaper(2 if self.side_rect else 1)
            log.info("fond d'écran %s", 'chargé' if ok else 'pas détecté (on continue)')

    def _go(self, plan, browser, s):
        e = self.engine
        apps = {a['id']: a for a in self.cfg['apps']}
        games = {g['id']: g for g in self.cfg['games']}
        app_hwnds, game_hwnd = [], None
        for step in plan['steps']:
            sid = step['id']
            self.send({'type': 'progress', 'id': sid, 'state': 'run'})
            try:
                if step.get('game'):
                    g = games[sid]
                    self._allow(g)
                    before = {w.hwnd for w in e.windows()}
                    e.start(g['launch'], browser)
                    if g.get('wait', True):
                        w = e.wait_window(g.get('process'), g.get('title'), before, self.main_rect, s['game_timeout'])
                        log.info('jeu %s : fenêtre %s', sid, w and (w.proc, w.title))
                        if w:
                            game_hwnd = w.hwnd
                            time.sleep(g.get('ready_delay', s['ready_delay']))
                else:
                    a = apps[sid]
                    self._allow(a)
                    e.start(a['launch'], browser)
                    w = e.wait_window(a.get('process'), a.get('title'), timeout=s['app_timeout'])
                    log.info('appli %s : fenêtre %s', sid, w and (w.proc, w.title))
                    if w:
                        if self.side_rect:
                            e.place(w.hwnd, self.side_rect)
                        app_hwnds.append(w.hwnd)
            except Exception:
                log.exception('étape %s', sid)
            self.send({'type': 'progress', 'id': sid, 'state': 'ok'})
        return app_hwnds, game_hwnd or (app_hwnds[-1] if app_hwnds else None)

    def _dry_run(self, plan):
        """Essai à blanc : mêmes animations, mais rien n'est lancé."""
        log.info('essai à blanc : %s', plan.get('kind'))
        if plan.get('kind') == 'go':
            time.sleep(1.1)
            for step in plan['steps']:
                self.send({'type': 'progress', 'id': step['id'], 'state': 'run'})
                time.sleep(2.5 if step.get('game') else .9)
                self.send({'type': 'progress', 'id': step['id'], 'state': 'ok'})
            time.sleep(.6)
        else:
            time.sleep(6)
        self.ready()

    def after_close(self):
        """Les fenêtres du launcher sont fermées : on remet l'ordre voulu et on surveille un moment."""
        apps, focus = self.result
        if self.side_rect:
            self.engine.keep_on(apps, self.side_rect)
        self.engine.arrange(apps, focus)
        if apps or focus:
            self.engine.guard(apps, focus, self.cfg['settings']['guard_seconds'], self.side_rect, log.info)

    # ---------------------------------------------------------------- ajout d'un jeu / d'une appli
    def add_item(self, screen):
        import webview
        # pywebview n'accepte que lettres et espaces dans la description du filtre
        types = ('Programmes raccourcis et ROM (*.exe;*.lnk;*.url;*.3ds;*.cia;*.cci)', 'Tous les fichiers (*.*)')
        res = self.windows[screen].create_file_dialog(webview.FileDialog.OPEN, file_types=types)
        if not res:
            return None
        path = Path(res[0] if isinstance(res, (list, tuple)) else res)
        ext = path.suffix.lower()
        entry = {'name': path.stem}
        if ext in ('.3ds', '.cia', '.cci'):
            entry.update(launch={'exe': self.cfg['settings']['emulator_3ds'], 'args': [str(path)]}, process='azahar.exe')
        elif ext == '.exe':
            entry['launch'] = {'exe': str(path)}
            if screen == 'apps':
                entry['process'] = path.name
        else:
            entry['launch'] = {'file': str(path)}
        key = 'games' if screen == 'games' else 'apps'
        entry = {'id': slug(path.stem, {x['id'] for x in self.cfg[key]}), **entry}
        if key == 'games':
            self.cfg['games'].insert(0, entry)
        else:
            self.cfg['apps'].append(entry)
        save_config(self.cfg)
        write_data_js(self.cfg)
        log.info('ajout %s : %s', key, entry)
        return entry['name']


def start_explorer():
    """Démarre le bureau Windows s'il ne tourne pas déjà (mode coquille, ou filet de sécurité en cas d'erreur)."""
    import psutil
    if not any(p.info['name'] and p.info['name'].lower() == 'explorer.exe' for p in psutil.process_iter(['name'])):
        log.info('démarrage du bureau (explorer)')
        subprocess.Popen([os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'explorer.exe')])


def single_instance():
    """Un seul launcher à la fois (sinon le dossier Démarrage pourrait en ouvrir un second)."""
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, 'SakuraLauncher.single')
    return ctypes.windll.kernel32.GetLastError() != 183   # 183 = ERROR_ALREADY_EXISTS


def main():
    if '--data' in sys.argv:
        write_data_js(load_config())
        return
    debug, shell = '--debug' in sys.argv, '--shell' in sys.argv
    if not single_instance():
        log.info('déjà ouvert, on ne relance pas')
        return
    # son autorisé dès l'ouverture (sans attendre un clic)
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = '--autoplay-policy=no-user-gesture-required'
    # lumières : on les démarre en tout premier et on éteint tout jusqu'à la tempête
    import lights
    lights.ensure_running()
    lights.send('off')
    if shell:
        lights.start_icue()
    import webview
    import engine
    app = App(engine, dry='--dry' in sys.argv, shell=shell)
    try:
        app.open(webview, debug)
        webview.start(gui='edgechromium', debug=debug, private_mode=False, storage_path=str(paths.USER / '.webview'))
    except Exception:
        log.exception('le launcher a planté')
    finally:
        # quoi qu'il arrive : on rend le son aux autres applis, et en mode coquille le bureau doit exister
        if hasattr(app, 'muter'):
            app.muter.stop(pause=app.cfg['settings'].get('pause_if_playing', []))
        lights.send('auto')   # le launcher est fermé : style du moment selon l'heure
        if shell:
            start_explorer()
    if not app.dry:
        app.after_close()
    if app.sweeper:
        app.sweeper.wait()
        log.info('fermées au démarrage : %s', sorted(set(app.sweeper.killed)) or 'aucune')
    log.info('terminé')


if __name__ == '__main__':
    main()
