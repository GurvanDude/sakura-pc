"""Lumières du Sakura Launcher : pilote le RGB de la tour (RAM Corsair via iCUE, carte mère GIGABYTE et
ce qui est branché dessus — ventirad MSI, ventilateurs — via OpenRGB). Clavier, souris et casque restent à iCUE.

Tourne en fond en permanence. Ordres sur http://127.0.0.1:48700 :
    /cmd?do=off | storm | flash | theme | auto   (&theme=day|night)     utilisé par le launcher
    /studio                                                               l'appli « Sakura Light »
    /api/...                                                              utilisé par l'appli
Réglages dans config.json → "lights" (modifiables depuis l'appli).

    pythonw lights.py           lancement (une seule instance à la fois)
"""
import ctypes
import json
import logging
import math
import random
import subprocess
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # racine du dépôt, pour core/
from core import paths  # noqa: E402

ROOT = Path(__file__).resolve().parent
CONFIG = paths.CONFIG
PORT = 48700
DESIGN_ROOT = (paths.REPO / 'design').resolve()
DESIGN_MIME_TYPES = {
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.woff2': 'font/woff2',
}
# OpenRGB n'est pas dans le dépôt : chemin dans config.json (settings → openrgb), sinon dans le dossier utilisateur
OPENRGB = Path(json.loads(CONFIG.read_text(encoding='utf-8'))['settings'].get(
    'openrgb', paths.USER / 'tools' / 'OpenRGB' / 'OpenRGB Windows 64-bit' / 'OpenRGB.exe'))
FPS = 30
logging.basicConfig(filename=paths.log('lights'), level=logging.INFO, encoding='utf-8',
                    format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('lights')

SAKURA, WHITE, NEON_BLUE, NEON_PINK = '#ff5fa8', '#ffffff', '#0a3cff', '#ff0f9b'

DEFAULT_SCENES = {
    # tempête d'ouverture : les zones « first » s'allument tout de suite, les zones « fill » se remplissent
    # LED par LED à partir de fill_delay ; à « hold » tout s'éteint en fondu, puis le style du moment apparaît
    'storm': {'color': '#ff1493', 'first': ['ram1', 'ram2', 'mb:PCI-E Accent'], 'fill': ['mb:D_LED1', 'mb:D_LED2'],
              'fill_delay': 2.0, 'fill_time': 2.5, 'hold': 5.5, 'fade_out': 1.3, 'fade_in': 1.3},
    'flash': {'color': '#ff3caf', 'fade': 2.7},
    # « C'est parti » du jour : flash blanc, onde sakura, pétales qui tombent
    'go_day': {'pink': '#ff4fa3', 'white': '#ffffff'},
    # « C'est parti » de nuit : néon qui démarre, comètes, surtension puis coupure sèche
    'go_night': {'pink': NEON_PINK, 'cyan': NEON_BLUE},   # le rose du ventirad et le bleu de la RAM (nuit)
}
GO_OUTRO = {'day': 1.2 + 1.5, 'night': .7 + 1.5}   # durée de la sortie (extinction + apparition du style)
GO_MAX = 180                                       # filet de sécurité : sortie automatique au bout de 3 min

# Style de chaque composant dans chaque ambiance (modifiable dans l'appli).
# « phase » décale l'effet d'un composant à l'autre pour qu'ils ne soient pas synchronisés.
DEFAULT_PROGRAMS = {
    'day': {
        'mb:PCI-E Accent': {'effect': 'static', 'a': WHITE},
        'mb:D_LED1': {'effect': 'static', 'a': WHITE},
        'ram1': {'effect': 'wave', 'a': SAKURA, 'b': WHITE, 'speed': 1.0, 'phase': 0.0},
        'ram2': {'effect': 'wave', 'a': WHITE, 'b': SAKURA, 'speed': .8, 'phase': .37},
        'mb:D_LED2': {'effect': 'comet', 'a': SAKURA, 'speed': 1.0},
    },
    'night': {
        'mb:PCI-E Accent': {'effect': 'static', 'a': NEON_BLUE},
        'mb:D_LED1': {'effect': 'rain', 'a': NEON_BLUE, 'b': '#bfe6ff', 'speed': 1.0},
        'ram1': {'effect': 'neon', 'a': NEON_BLUE, 'speed': 1.0, 'phase': 0.0},
        'ram2': {'effect': 'neon', 'a': NEON_BLUE, 'speed': 1.0, 'phase': .55},
        'mb:D_LED2': {'effect': 'static', 'a': NEON_PINK},
    },
}
FALLBACK = {'day': {'effect': 'static', 'a': WHITE}, 'night': {'effect': 'static', 'a': NEON_BLUE}}

# Galerie d'effets, à prévisualiser depuis l'appli
EFFECTS = {
    'static': ('Couleur fixe', 'Toutes les LED de la même couleur, sans mouvement.'),
    'breathing': ('Respiration', "La couleur s'allume et s'éteint lentement, comme une respiration."),
    'wave': ('Vague 2 couleurs', "Deux couleurs qui ondulent et glissent d'un composant à l'autre."),
    'rainbow': ('Arc-en-ciel', 'Toutes les couleurs défilent en continu sur toute la tour.'),
    'comet': ('Comète', 'Un point lumineux avec une traînée qui fait le tour de chaque ventilateur / bande.'),
    'sparkle': ('Pluie de pétales', "Des éclats apparaissent au hasard et s'éteignent doucement."),
    'fire': ('Feu', 'Flammes orange et rouges qui vacillent.'),
    'neon': ('Néon qui grésille', 'Couleur fixe avec un court grésillement de temps en temps (environ toutes les 10 s), comme une enseigne néon.'),
    'rain': ('Pluie', "Fond de couleur avec des gouttes plus claires qui tombent au hasard et s'estompent."),
    'police': ('Gyrophare', 'Alternance rapide de deux couleurs.'),
}


def resolve_design_path(url_path, design_root=DESIGN_ROOT):
    """Résout une URL /design/... sans jamais autoriser une sortie du dossier design."""
    decoded = urllib.parse.unquote(url_path)
    if not decoded.startswith('/design/'):
        return None
    root = Path(design_root).resolve()
    try:
        candidate = (root / decoded.removeprefix('/design/')).resolve()
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def scale(c, k):
    return tuple(v * k for v in c)


def storm_ease(t):
    """Même courbe que la tempête à l'écran : linéaire au milieu, adoucie au début et à la fin."""
    a, v = .15, 1 / .85
    if t < a:
        return v * t * t / (2 * a)
    if t > 1 - a:
        return 1 - v * (1 - t) ** 2 / (2 * a)
    return v * (t - a / 2)


def hsv(h):
    i, f = int(h * 6) % 6, h * 6 - int(h * 6)
    return [(1, f, 0), (1 - f, 1, 0), (0, 1, f), (0, 1 - f, 1), (f, 0, 1), (1, 0, 1 - f)][i]


class NeonClock:
    """Moments de grésillement de chaque composant : écarts aléatoires, un tirage indépendant par composant."""

    def __init__(self):
        self.state = {}                         # clé -> [début du dernier grésillement, début du prochain]
        self.rng = random.Random()

    def since_flicker(self, key, t, gap_min, gap_max):
        last, nxt = self.state.get(key, (t - 99, t + self.rng.uniform(gap_min, gap_max)))
        if t >= nxt:
            last, nxt = nxt, nxt + self.rng.uniform(gap_min, gap_max)
        self.state[key] = (last, nxt)
        return t - last


NEON = NeonClock()
LIGHTS = None          # instance en cours (la pluie garde le moment des gouttes de chaque LED)


class Zone:
    """Un groupe de LED pilotable : la RAM, ou une zone de la carte mère (prise ARGB, cache I/O…)."""

    def __init__(self, key, label, count, painter, cfg):
        self.key, self.label, self.count, self.painter, self.cfg = key, label, count, painter, cfg

    def us(self):
        """Position de chaque LED sur le trajet de la tempête (0 = là où elle commence, 1 = là où elle finit)."""
        u, span = self.cfg.get('u', .5), self.cfg.get('span', .1)
        n = max(1, self.count)
        return [u + span * k / n for k in range(self.count)]


class Lights:
    def __init__(self):
        self.lock = threading.Lock()
        self.mode, self.t0 = 'off', time.time()
        self.preview = None                    # (effet, paramètres, fin) pendant un aperçu depuis l'appli
        self.hw_stop = False                   # arrêter un aperçu d'effet matériel
        self.identify = None                   # (clé de zone, fin)
        self.colortest = None                  # (clé de zone, début) : rouge, vert puis bleu, 2 s chacun
        self.flash_end_t = None                # moment où le launcher s'est fermé pendant un « C'est parti »
        self.conflicts_paused_until = 0.0      # jusqu'à quand on laisse GIGABYTE Control Center ouvert
        self.drops = {}                        # pluie : (zone, LED) -> [dernière goutte, prochaine goutte]
        self.zones = {}                        # clé -> Zone
        self.sdk = self.orgb = None
        self.corsair_t = 0.0                   # moment où la RAM est passée sous notre contrôle
        self.ram_orgb, self.ram_buf, self.ram_last, self.ram_sent = [], {}, {}, 0.0   # RAM pilotée par OpenRGB
        self.ram_devs, self.ram_claim_t, self.ram_err = [], 0.0, None   # barrettes, dernière reprise de contrôle
        self.parked = False                    # Windows s'éteint : tout est noir, on n'envoie plus rien
        # carte mère : sa puce est lente, on lui envoie UN paquet pour tout l'appareil, 15 fois par seconde au plus,
        # et seulement si les couleurs ont changé (sinon OpenRGB accumule une file d'attente)
        self.mb_dev, self.mb_order, self.mb_buf, self.mb_last, self.mb_sent = None, [], {}, None, 0.0
        self.mb_force, self.mb_mode_t = True, 0.0
        self.load()
        self.theme = self.auto_theme()
        self.prev_theme, self.theme_t0, self.auto = self.theme, 0.0, True

    # ------------------------------------------------------------------ réglages
    def load(self):
        cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
        s = cfg['settings']
        self.apply(cfg.get('lights', {}), (s.get('day_start', 8), s.get('day_end', 18)))

    def apply(self, lights, day_hours):
        """Applique des réglages déjà lus, sans toucher à config.json."""
        self.day = day_hours
        self.scenes = {k: {**v, **lights.get('scenes', {}).get(k, {})} for k, v in DEFAULT_SCENES.items()}
        saved = lights.get('programs', {})
        self.programs = {th: {**DEFAULT_PROGRAMS[th], **saved.get(th, {})} for th in DEFAULT_PROGRAMS}
        self.zone_cfg = lights.get('zones', {})
        for z in self.zones.values():
            z.cfg = {**z.cfg, **self.zone_cfg.get(z.key, {})}

    def resize_configured_zones(self):
        for key, z in list(self.zones.items()):   # nombre de LED d'une prise ARGB changé
            want = z.cfg.get('leds')
            if want and want != z.count and key.startswith('mb:'):
                self.resize_zone(key, int(want))

    def live(self, lights):
        with self.lock:
            self.apply(lights, self.day)
        self.resize_configured_zones()

    def save(self, lights):
        cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
        cfg['lights'] = lights
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        with self.lock:
            self.load()
        self.resize_configured_zones()

    def auto_theme(self):
        h = datetime.now().hour
        return 'day' if self.day[0] <= h < self.day[1] else 'night'

    def set_theme(self, theme):
        if theme != self.theme:
            self.prev_theme, self.theme, self.theme_t0 = self.theme, theme, time.time()

    def command(self, do, theme=None):
        with self.lock:
            if theme in ('day', 'night'):
                self.set_theme(theme)
                self.auto = False
            if do == 'off':
                self.mode = 'off'
            elif do == 'storm':
                self.mode, self.t0 = do, time.time()
            elif do in ('flash', 'flash_day', 'flash_night'):
                # « C'est parti » : version du thème en cours (ou forcée depuis l'appli pour l'aperçu).
                # Il tourne en boucle jusqu'à « flash_end » (fermeture du launcher), puis joue sa sortie.
                self.mode, self.t0, self.flash_end_t = 'flash', time.time(), None
                self.flash_variant = do[6:] or self.theme
            elif do == 'flash_end':
                if self.mode == 'flash' and self.flash_end_t is None:
                    self.flash_end_t = time.time()
            elif do == 'theme':
                self.mode = 'ambient'
            elif do == 'auto':
                if self.mode == 'flash' and self.flash_end_t is None:
                    self.flash_end_t = time.time()
                self.auto = True
                self.set_theme(self.auto_theme())
                if self.mode == 'off':
                    self.mode = 'ambient'
        log.info('ordre %s (thème %s)', do, self.theme)

    # ------------------------------------------------------------------ couleurs
    def program(self, z, i, n, now, theme):
        p = self.programs[theme].get(z.key) or FALLBACK[theme]
        c = self.effect_color(p.get('effect', 'static'), 0, i, n, now, {**p, '_key': z.key})
        return scale(c, float(p.get('bright', 1.0)))

    def ambient(self, z, i, n, now):
        """Style du moment pour cette LED, avec un fondu quand on passe du jour à la nuit."""
        c = self.program(z, i, n, now, self.theme)
        k = min(1, (now - self.theme_t0) / 1.2)
        return c if k >= 1 else mix(self.program(z, i, n, now, self.prev_theme), c, k)

    def storm_end(self):
        sc = self.scenes['storm']
        return sc['hold'] + sc['fade_out'] + sc['fade_in']

    def scene_color(self, z, i, n, now):
        mode, dt = self.mode, now - self.t0
        if mode == 'off':
            return (0, 0, 0)
        if mode == 'storm':
            sc = self.scenes['storm']
            pink = hex2rgb(sc['color'])
            if dt >= sc['hold'] + sc['fade_out']:                       # le style du moment apparaît
                return scale(self.ambient(z, i, n, now), min(1, (dt - sc['hold'] - sc['fade_out']) / sc['fade_in']))
            if z.key in sc['first']:
                level = min(1, dt / .35)                                 # allumage net, sans à-coup
            elif z.key in sc['fill']:
                lit_at = sc['fill_delay'] + sc['fill_time'] * i / max(1, n)   # une LED après l'autre
                level = min(1, max(0, (dt - lit_at) / .12))
            else:
                level = 0
            if dt >= sc['hold']:                                         # tout s'éteint petit à petit
                level *= 1 - (dt - sc['hold']) / sc['fade_out']
            return scale(pink, level)
        if mode == 'flash':
            return self.go_color(z, i, n, dt, now)
        return self.ambient(z, i, n, now)

    def go_color(self, z, i, n, dt, now):
        """« C'est parti » en trois temps : intro au clic, boucle tant que le launcher travaille, sortie quand il se ferme.
        Barrettes de RAM = le cœur de l'effet ; ventilateurs et ventirad = les anneaux autour."""
        variant = getattr(self, 'flash_variant', self.theme)
        ring = not z.key.startswith('ram')
        x = i / max(1, n)
        end = None if self.flash_end_t is None else now - self.flash_end_t
        if variant == 'day':
            sc = self.scenes['go_day']
            pink, white = hex2rgb(sc['pink']), hex2rgb(sc['white'])
            if end is None and dt < .15:                            # flash blanc au cœur
                return white if not ring else (0, 0, 0)
            if end is None and dt < .9:                             # onde sakura qui remplit les anneaux
                if not ring:
                    return mix(white, pink, (dt - .15) / .75)
                front = (dt - .15) / .6 - x
                return (0, 0, 0) if front < 0 else mix(white, pink, min(1, front * 6))
            # boucle : pétales blancs qui tombent au hasard sur le rose
            petal = math.exp(-self.drop_since(z.key, i, now, .25, 1.6) * 5)
            loop = mix(scale(pink, .8), white, petal)
            if end is None:
                return loop
            if end < 1.2:                                           # sortie : tout s'éteint doucement
                return scale(loop, 1 - end / 1.2)
            return scale(self.ambient(z, i, n, now), min(1, (end - 1.2) / 1.5))
        sc = self.scenes['go_night']
        pink, cyan = hex2rgb(sc['pink']), hex2rgb(sc['cyan'])
        if end is None and dt < .75:                                # tube néon qui démarre (quelques à-coups)
            on = any(a <= dt < b for a, b in ((0, .06), (.2, .28), (.42, .75)))
            return pink if on else scale(pink, .06)
        # boucle calme : comètes lentes autour des anneaux, barrettes en fondu rose <-> cyan
        if ring:
            h1 = ((dt - .75) * .45) % 1
            c1 = scale(pink, math.exp(-((h1 - x) % 1) * 6))
            c2 = scale(cyan, math.exp(-(((h1 + .5) % 1 - x) % 1) * 6))
            loop = tuple(min(255, c1[k] + c2[k]) for k in range(3))   # pas de fond blanc : du néon pur
        else:
            k = .5 + .5 * math.sin((dt - .75) * 2.1 + (math.pi if z.key.endswith('2') else 0))
            loop = mix(pink, cyan, k)
        if end is None:
            return loop
        if end < .3:                                                # sortie : surtension rose
            return mix(loop, pink, end / .3)
        if end < .42:                                               # coupure sèche
            return scale(pink, 1 - (end - .3) / .12)
        if end < .7:
            return scale(cyan, .6) if .5 < end < .56 else (0, 0, 0)  # dernier éclat cyan
        return scale(self.ambient(z, i, n, now), min(1, (end - .7) / 1.5))

    def drop_since(self, key, i, now, gap_min, gap_max):
        """Secondes depuis la dernière « goutte » de cette LED ; chaque LED a ses propres moments, tirés au hasard."""
        last, nxt = self.drops.get((key, i), (now - 99, now + NEON.rng.uniform(0, gap_max)))
        if now >= nxt:
            last, nxt = nxt, nxt + NEON.rng.uniform(gap_min, gap_max)
        self.drops[(key, i)] = (last, nxt)
        return now - last

    @staticmethod
    def effect_color(name, u, i, n, t, p):
        a, b = hex2rgb(p.get('a', '#ff46a5')), hex2rgb(p.get('b', '#195aff'))
        sp = float(p.get('speed', 1.0))
        ph = float(p.get('phase', 0.0))
        x = i / max(1, n)
        if name == 'breathing':
            return scale(a, .5 + .5 * math.sin(t * 2 * sp + ph * 6.28))
        if name == 'wave':
            return mix(a, b, .5 + .5 * math.sin(2 * math.pi * (x + u - t * .25 * sp + ph)))
        if name == 'rainbow':
            return scale(hsv((x + u + t * .15 * sp + ph) % 1), 255)
        if name == 'comet':
            d = ((t * .6 * sp + ph) - x) % 1                # distance derrière la tête de la comète
            return scale(a, math.exp(-d * 7))
        if name == 'sparkle':
            step = t * 5 * sp
            random.seed(int(step) * 7919 + i)
            return scale(a, .12 + .88 * (random.random() > .8) * (1 - step % 1))
        if name == 'rain':
            # chaque LED reçoit ses gouttes à des moments aléatoires (aucun lien entre les LED) :
            # un « tac » net en couleur 2 qui s'efface vite, sur un fond couleur 1 tamisé
            since = LIGHTS.drop_since(p.get('_key', 'apercu'), i, t, .35 / sp, 3.0 / sp) if LIGHTS else 9
            return mix(scale(a, .4), b, math.exp(-since * 7))
        if name == 'fire':
            f = .55 + .45 * math.sin(t * 9 * sp + i * 1.7) * math.sin(t * 5.3 * sp + i)
            return mix((255, 30, 0), (255, 150, 10), max(0, f))
        if name == 'neon':
            # grésillements à des moments aléatoires (entre gap_min et gap_max secondes d'écart),
            # tirés indépendamment pour chaque composant : aucun lien entre les deux barrettes
            since = NEON.since_flicker(p.get('_key', 'apercu'), t, float(p.get('gap_min', 3)), float(p.get('gap_max', 10)))
            if since < .45:
                return scale(a, .08) if math.sin(since * 70) > -.2 else a
            return a
        if name == 'police':
            return a if int(t * 4 * sp) % 2 else b
        return a

    def zone_colors(self, z, now):
        """Couleurs de la zone, remises dans l'ordre que ses LED attendent (certaines prises ARGB sont en RBG, GRB…)."""
        order = z.cfg.get('order', 'RGB')
        cols = self._zone_colors(z, now)
        if order == 'RGB':
            return cols
        idx = ['RGB'.index(ch) for ch in order]
        return [tuple(c[i] for i in idx) for c in cols]

    def _zone_colors(self, z, now):
        if self.colortest:
            key, start = self.colortest
            dt = now - start
            if dt < 6:
                pure = [(255, 0, 0), (0, 255, 0), (0, 0, 255)][int(dt // 2)]
                return [pure if z.key == key else (0, 0, 0)] * z.count
            self.colortest = None
        if self.identify:
            key, end = self.identify
            if now < end:
                on = z.key == key and int(now * 3) % 2 == 0
                return [(255, 255, 255) if on else (0, 0, 0)] * z.count
            self.identify = None
        if not z.cfg.get('enabled', True):
            return [(0, 0, 0)] * z.count
        us = z.us()
        if self.preview:
            name, params, end = self.preview
            if now < end:
                return [self.effect_color(name, u, i, z.count, now, params) for i, u in enumerate(us)]
            self.preview = None
        return [self.scene_color(z, i, z.count, now) for i in range(z.count)]

    def tick(self):
        now = time.time()
        if self.parked:
            return
        self.claim_ram(now)
        with self.lock:
            if self.mode == 'storm' and now - self.t0 > self.storm_end():
                self.mode = 'ambient'
            if self.mode == 'flash':
                if self.flash_end_t is None and now - self.t0 > GO_MAX:
                    self.flash_end_t = now
                if self.flash_end_t and now - self.flash_end_t > GO_OUTRO.get(getattr(self, 'flash_variant', self.theme), 3):
                    self.mode = 'ambient'
            if self.auto and self.mode == 'ambient':
                self.set_theme(self.auto_theme())
        for z in list(self.zones.values()):
            try:
                z.painter(self.zone_colors(z, now))
            except Exception:
                log.exception('zone %s', z.key)
                self.drop(z.key)
        self.flush_mb(now)
        self.flush_ram(now)

    def flush_mb(self, now):
        if not (self.mb_dev and self.orgb) or now - self.mb_sent < 1 / 15:
            return
        from openrgb.utils import RGBColor
        colors = []
        for key, n in self.mb_order:
            cols = self.mb_buf.get(key) or [(0, 0, 0)] * n
            colors += [tuple(int(v) for v in c) for c in cols[:n]] + [(0, 0, 0)] * (n - len(cols))
        if colors == self.mb_last and now - self.mb_sent < 2:
            return
        try:
            dev = self.mb_dev
            # La puce peut être repassée dans ses propres effets (GIGABYTE Control Center, effet matériel…) sans
            # qu'OpenRGB le sache : on réimpose le contrôle direct régulièrement, et tout de suite si besoin.
            if self.mb_force or now - self.mb_mode_t > 5 or dev.modes[dev.active_mode].name != 'Direct':
                dev.set_mode('Direct')
                self.mb_force, self.mb_mode_t = False, now
            dev.set_colors([RGBColor(*c) for c in colors], fast=True)
            self.mb_last, self.mb_sent = colors, now
        except Exception:
            log.exception('envoi carte mère')
            self.drop('mb:')

    def drop(self, key):
        """Un appareil a décroché : on retire ses zones et on relance la connexion correspondante."""
        if key.startswith('ram') and self.sdk:
            self.sdk = None
            for k in [k for k in self.zones if k.startswith('ram')]:
                self.zones.pop(k)
            threading.Thread(target=self.reconnect_corsair, daemon=True).start()
        elif key.startswith('mb:') and self.orgb:
            self.orgb = self.mb_dev = None
            for k in [k for k in self.zones if k.startswith('mb:') or (self.ram_orgb and k.startswith('ram'))]:
                self.zones.pop(k)
            self.ram_orgb = []
            threading.Thread(target=self.connect_openrgb, daemon=True).start()

    # ------------------------------------------------------------------ RAM Corsair (iCUE)
    def connect_corsair(self):
        """On ne prend la main que sur la RAM : clavier, souris et casque gardent leurs effets iCUE."""
        from cuesdk import (CueSdk, CorsairSessionState, CorsairDeviceFilter, CorsairDeviceType,
                            CorsairAccessLevel, CorsairLedColor)
        sdk, states = CueSdk(), []

        def on_state(e):
            states.append(e.state)
            if e.state in (CorsairSessionState.CSS_Connected, CorsairSessionState.CSS_ConnectionLost):
                log.info('iCUE : %s', e.state)

        sdk.connect(on_state)   # le kit réessaie tout seul tant qu'iCUE n'est pas lancé : on attend, sans limite
        while True:
            try:
                while CorsairSessionState.CSS_Connected not in states:
                    time.sleep(.5)
                # juste après son lancement, iCUE est connecté mais n'a pas encore détecté les barrettes : on attend
                devices = []
                for _ in range(120):
                    devices, _ = sdk.get_devices(CorsairDeviceFilter(device_type_mask=CorsairDeviceType.CDT_MemoryModule))
                    if devices:
                        break
                    time.sleep(.5)
                if not devices:
                    raise RuntimeError('iCUE ne voit pas encore la RAM')
                ids = []
                for d in devices or []:
                    sdk.request_control(d.device_id, CorsairAccessLevel.CAL_ExclusiveLightingControl)
                    leds, _ = sdk.get_led_positions(d.device_id)
                    ids += [(d.device_id, l.id, l.cy, l.cx) for l in leds]
                    log.info('Corsair : %s (%d LED)', d.model, len(leds))
                # iCUE voit les 2 barrettes comme un seul appareil : on les sépare d'après la position des LED
                columns = sorted({round(cx) for _, _, _, cx in ids})
                old = self.zone_cfg.get('ram', {})
                self.sdk, self.corsair_t = sdk, time.time()
                self.ram_devs, self.ram_claim_t = [d.device_id for d in devices], time.time()
                for n, cx in enumerate(columns, 1):
                    mine = sorted([x for x in ids if round(x[3]) == cx], key=lambda x: x[2])   # du haut vers le bas

                    def paint(colors, mine=mine):
                        by_dev = {}
                        for (dev, led, _, _), (r, g, b) in zip(mine, colors):
                            by_dev.setdefault(dev, []).append(CorsairLedColor(id=led, r=int(r), g=int(g), b=int(b), a=255))
                        for dev, cols in by_dev.items():
                            self.note_ram(sdk.set_led_colors(dev, cols))

                    key = f'ram{n}'
                    base = {**old, 'name': f"{old.get('name', 'Barrette de RAM').rstrip('s')} {n}"} if old else {}
                    self.zones[key] = Zone(key, f'RAM Corsair : barrette {n}', len(mine), paint,
                                           {'u': .55 + (n - 1) * .03, 'span': .05, **base, **self.zone_cfg.get(key, {})})
                return
            except Exception as e:
                # on garde la session ouverte et on redemande la liste plus tard (pas de nouvel « Connected » à attendre)
                log.warning('iCUE : %s, nouvel essai dans 5 s', e)
                time.sleep(5)

    def note_ram(self, err):
        """Réponse d'iCUE à l'envoi des couleurs de la RAM : s'il l'a reprise (elle repasse à son blanc), on la redemande."""
        err = str(err).rsplit('.', 1)[-1]
        if err == 'CE_NoControl':
            self.ram_lost = getattr(self, 'ram_lost', 0) + 1
            if time.time() - getattr(self, 'ram_lost_log', 0) > 60:
                log.info('iCUE a repris la RAM (%d fois) : on la redemande', self.ram_lost)
                self.ram_lost_log = time.time()
        elif err != 'CE_Success' and err != self.ram_err:
            log.info('iCUE répond %s', err)
        self.ram_err = err

    def claim_ram(self, now):
        """Redemande le contrôle exclusif de la RAM quand iCUE l'a reprise (au plus une fois par seconde)."""
        if not self.sdk or self.ram_err != 'CE_NoControl' or now - self.ram_claim_t < 1:
            return
        from cuesdk import CorsairAccessLevel
        self.ram_claim_t = now
        for dev in self.ram_devs:
            try:
                self.sdk.request_control(dev, CorsairAccessLevel.CAL_ExclusiveLightingControl)
            except Exception:
                log.exception('reprise de la RAM')

    def reconnect_corsair(self):
        time.sleep(5)
        if not self.sdk:
            self.connect_corsair()

    # ------------------------------------------------------------------ logiciels qui se battent pour les LED
    def keep_rgb_alone(self):
        """GIGABYTE Control Center et son module d'éclairage réimposent leurs effets à la carte mère :
        on les ferme dès qu'ils (re)démarrent. Liste réglable dans config.json → settings → rgb_conflicts."""
        import psutil
        names = {n.lower() for n in json.loads(CONFIG.read_text(encoding='utf-8'))['settings']
                 .get('rgb_conflicts', ['GCC.exe', 'GBT_DL_LIB.exe'])}
        if RAM_DRIVER == 'openrgb':
            names |= {'icue.exe', 'icue launcher.exe'}   # iCUE se battrait avec OpenRGB pour la RAM
        while True:
            if time.time() < self.conflicts_paused_until:   # pause demandée depuis l'appli (régler GIGABYTE)
                time.sleep(3)
                continue
            for p in psutil.process_iter(['name']):
                if (p.info['name'] or '').lower() in names:
                    try:
                        p.kill()
                        log.info("fermé (conflit d'éclairage) : %s", p.info["name"])
                        self.mb_last, self.mb_force = None, True
                    except psutil.Error:
                        pass
            time.sleep(3)

    # ------------------------------------------------------------------ carte mère et ARGB (OpenRGB)
    def connect_openrgb(self):
        if not OPENRGB.exists():
            return
        import psutil
        from openrgb import OpenRGBClient
        from openrgb.utils import ZoneType, RGBColor, DeviceType
        def start_server(restart=False):
            running = [p for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower() == 'openrgb.exe']
            if restart:
                for p in running:
                    try:
                        p.kill()
                    except psutil.Error:      # lancé en administrateur : on passe par la tâche planifiée
                        subprocess.run(['schtasks', '/end', '/tn', 'SakuraOpenRGB'], capture_output=True,
                                       creationflags=0x08000000)
                time.sleep(1)
                running = []
            if not running:
                # De préférence par la tâche planifiée « SakuraOpenRGB » (droits administrateur, sans demande) :
                # sans eux, PawnIO refuse l'accès au bus SMBus et OpenRGB ne voit pas la RAM.
                if subprocess.run(['schtasks', '/run', '/tn', 'SakuraOpenRGB'], capture_output=True,
                                  creationflags=0x08000000).returncode == 0:
                    log.info('OpenRGB lancé par la tâche planifiée (administrateur)')
                    return
                # serveur sans fenêtre (en mode fenêtré, OpenRGB affiche un avertissement et peut se fermer)
                subprocess.Popen([str(OPENRGB), '--localconfig', '--noautoconnect', '--server', '--server-port', '6742'],
                                 cwd=OPENRGB.parent, creationflags=0x08000000)

        start_server()
        failures = 0
        while True:
            try:
                cli = OpenRGBClient('127.0.0.1', 6742, 'sakura-lights')
                # OpenRGB trouve les appareils les uns après les autres (la RAM avant la carte mère, en USB) :
                # on attend d'avoir tout le monde, 30 s au plus
                for _ in range(60):
                    cli.update()
                    types = {d.type for d in cli.devices}
                    if any(t != DeviceType.DRAM for t in types) and (RAM_DRIVER != 'openrgb' or DeviceType.DRAM in types):
                        break
                    time.sleep(.5)
                if RAM_DRIVER == 'openrgb':
                    self.attach_ram([d for d in cli.devices if d.type == DeviceType.DRAM])
                if not any(d.type != DeviceType.DRAM for d in cli.devices):
                    log.warning("OpenRGB ne voit pas la carte mère")
                for dev in [d for d in cli.devices if d.type != DeviceType.DRAM]:
                    dev.set_mode('Direct')
                    for zone in dev.zones:
                        want = int(self.zone_cfg.get(f'mb:{zone.name}', {}).get('leds', 40))
                        if zone.type == ZoneType.LINEAR and len(zone.leds) != want:
                            zone.resize(want)   # prises ARGB : nombre de LED branchées (réglable dans l'appli)
                    cli.update()
                    dev = next((d for d in cli.devices if d.name == dev.name and d.type != DeviceType.DRAM), dev)
                    self.mb_dev, self.mb_last = dev, None
                    self.mb_order = [(f'mb:{z.name}', len(z.leds)) for z in dev.zones]
                    for zi, zone in enumerate(dev.zones):
                        if not zone.leds:
                            continue
                        key = f'mb:{zone.name}'
                        linear = zone.type == ZoneType.LINEAR
                        self.zones[key] = Zone(
                            key, f'Carte mère : {zone.name}', len(zone.leds),
                            lambda cols, key=key: self.mb_buf.__setitem__(key, cols),
                            {'u': .7 + zi * .04, 'span': .25 if linear else .02, **({'leds': len(zone.leds)} if linear else {}),
                             **self.zone_cfg.get(key, {})})
                    log.info('OpenRGB : %s (%d zones)', dev.name, len(dev.zones))
                self.orgb = cli
                return
            except Exception:
                failures += 1
                log.warning('connexion OpenRGB impossible (essai %d)', failures)
                if failures % 3 == 0:          # serveur bloqué : on le relance
                    log.info('redémarrage du serveur OpenRGB')
                    start_server(restart=True)
                time.sleep(3)

    def attach_ram(self, rams):
        """Barrettes Corsair lues directement par OpenRGB (sans iCUE) : une zone par barrette."""
        self.ram_orgb = []
        for n, dev in enumerate(rams, 1):
            dev.set_mode('Direct')
            key = f'ram{n}'
            old = self.zone_cfg.get('ram', {})
            base = {**old, 'name': f"{old.get('name', 'Barrette de RAM').rstrip('s')} {n}"} if old else {}
            self.ram_orgb.append((key, dev))
            self.zones[key] = Zone(key, f'RAM Corsair : barrette {n}', len(dev.leds),
                                   lambda cols, key=key: self.ram_buf.__setitem__(key, cols),
                                   {'u': .55 + (n - 1) * .03, 'span': .05, **base, **self.zone_cfg.get(key, {})})
            log.info('OpenRGB : %s (%d LED) = %s', dev.name, len(dev.leds), key)
        if not rams:
            log.warning("OpenRGB ne voit pas la RAM (pilote PawnIO installé ? iCUE fermé ?)")
        self.corsair_t = time.time() - RAM_WARMUP

    def flush_ram(self, now):
        """La RAM passe par le bus SMBus, assez lent : 20 images/s au plus, et seulement si ça change (ou toutes les 2 s)."""
        if not (self.ram_orgb and self.orgb) or now - self.ram_sent < 1 / 20:
            return
        from openrgb.utils import RGBColor
        self.ram_sent = now
        for key, dev in self.ram_orgb:
            cols = [tuple(int(v) for v in c) for c in (self.ram_buf.get(key) or [])][:len(dev.leds)]
            cols += [(0, 0, 0)] * (len(dev.leds) - len(cols))
            last = self.ram_last.get(key)
            if last and cols == last[0] and now - last[1] < 2:
                continue
            try:
                dev.set_colors([RGBColor(*c) for c in cols], fast=True)
                self.ram_last[key] = (cols, now)
            except Exception:
                log.exception('envoi RAM')
                self.drop('mb:')
                return

    def resize_zone(self, key, n):
        if not self.orgb:
            return
        for dev in self.orgb.devices:
            for zone in dev.zones:
                if f'mb:{zone.name}' == key:
                    zone.resize(n)
                    self.orgb.update()
                    self.zones[key].count = n
                    self.mb_dev = dev
                    self.mb_order = [(f'mb:{z.name}', len(z.leds)) for z in self.mb_dev.zones]
                    self.mb_last = None

    def hw_modes(self):
        if not self.orgb:
            return []
        return [{'device': d.name, 'modes': [m.name for m in d.modes if m.name != 'Direct']} for d in [self.mb_dev] if d]

    def hw_preview(self, mode, color, seconds=8):
        """Aperçu d'un effet matériel de la carte mère (calculé par sa propre puce), puis retour au contrôle direct."""
        from openrgb.utils import RGBColor
        dev = self.mb_dev
        paused = {k: self.zones.pop(k) for k in [k for k in self.zones if k.startswith('mb:')]}
        try:
            dev.set_mode(mode)
            try:
                dev.set_color(RGBColor(*hex2rgb(color)))
            except Exception:
                pass                          # certains effets (arc-en-ciel…) n'ont pas de couleur
            end = time.time() + seconds
            while time.time() < end and not self.hw_stop:
                time.sleep(.1)
        finally:
            self.hw_stop = False
            dev.set_mode('Direct')
            self.mb_last = None
            self.zones.update(paused)

    # ------------------------------------------------------------------ état pour l'appli
    def state(self):
        return {
            'zones': [{'key': z.key, 'label': z.label, 'count': z.count, **z.cfg} for z in self.zones.values()],
            'scenes': self.scenes,
            'programs': self.programs,
            'effects': [{'id': k, 'name': n, 'desc': d} for k, (n, d) in EFFECTS.items()],
            'hw': self.hw_modes(),
            'theme': self.theme, 'mode': self.mode, 'auto': self.auto,
            # juste après la prise de contrôle, iCUE met quelques secondes à afficher nos couleurs sur la RAM
            'connected': {'corsair': bool(self.sdk or self.ram_orgb) and time.time() - self.corsair_t > RAM_WARMUP,
                          'openrgb': bool(self.orgb)},
        }

    # ------------------------------------------------------------------ extinction de Windows
    def park(self):
        """Avant que Windows s'éteigne : tout en noir. Au prochain allumage, la puce de la carte mère rejoue son
        dernier état (en « respiration ») jusqu'à la tempête : il doit donc être noir."""
        if self.parked:
            return
        self.parked = True
        try:
            from openrgb.utils import RGBColor
            for _, dev in self.ram_orgb:              # au mieux : Windows ferme peut-être OpenRGB en même temps
                dev.set_colors([RGBColor(0, 0, 0)] * len(dev.leds), fast=True)
        except Exception:
            pass
        # la carte mère reste noire à l'allumage grâce au BIOS (LEDs in System Power On State = Off) : on ne
        # touche plus à sa puce ici, car si l'extinction est annulée elle clignoterait en boucle
        log.info("Windows s'éteint : lumières en pause")

    def unpark(self):
        """L'extinction a été annulée : on reprend comme avant."""
        if not self.parked:
            return
        self.parked = False
        self.mb_last, self.mb_force = None, True
        self.ram_last = {}
        log.info("extinction annulée : lumières reprises")

    def watch_shutdown(self):
        """Une fenêtre invisible reçoit l'annonce d'extinction de Windows (WM_QUERYENDSESSION)."""
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        def proc(hwnd, msg, wp, lp):
            if msg in (0x0011, 0x0016):   # WM_QUERYENDSESSION, WM_ENDSESSION
                if msg == 0x0011 or wp:
                    self.park()
                else:                     # WM_ENDSESSION avec FALSE : extinction annulée
                    self.unpark()
                return 1 if msg == 0x0011 else 0
            return user32.DefWindowProcW(hwnd, msg, wp, lp)

        self._wndproc = WNDPROC(proc)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [('style', wintypes.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                        ('cbWndExtra', ctypes.c_int), ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON),
                        ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HBRUSH),
                        ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR)]

        wc = WNDCLASS(lpfnWndProc=self._wndproc, lpszClassName='SakuraLightsShutdown')
        user32.RegisterClassW(ctypes.byref(wc))
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW(0, 'SakuraLightsShutdown', 'Sakura Light', 0, 0, 0, 0, 0, None, None, None, None)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # ------------------------------------------------------------------ boucle et serveur
    def run(self):
        threading.Thread(target=self.keep_rgb_alone, daemon=True).start()
        threading.Thread(target=self.watch_shutdown, daemon=True).start()
        if RAM_DRIVER == 'icue':
            threading.Thread(target=self.connect_corsair, daemon=True).start()
        threading.Thread(target=self.connect_openrgb, daemon=True).start()
        lights = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code=204, body=None, ctype='application/json'):
                self.send_response(code)
                if body is None:
                    return self.end_headers()
                data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urllib.parse.urlparse(self.path)
                q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
                if url.path == '/cmd':
                    lights.command(q.get('do', ''), q.get('theme'))
                    return self.reply()
                if url.path in ('/', '/studio'):
                    return self.reply(200, (ROOT / 'ui' / 'studio.html').read_bytes(), 'text/html; charset=utf-8')
                if url.path.startswith('/design/'):
                    design_file = resolve_design_path(url.path)
                    if design_file is None or not design_file.is_file():
                        return self.reply(404)
                    content_type = DESIGN_MIME_TYPES.get(design_file.suffix.lower(), 'application/octet-stream')
                    return self.reply(200, design_file.read_bytes(), content_type)
                if url.path == '/api/state':
                    return self.reply(200, lights.state())
                if url.path == '/api/revert':
                    with lights.lock:
                        lights.load()
                    lights.resize_configured_zones()
                    return self.reply()
                if url.path == '/api/theme':
                    lights.preview = lights.identify = lights.colortest = None
                    theme = q.get('theme')
                    if theme in ('day', 'night'):
                        lights.command('theme', theme)
                    elif theme == 'auto':
                        lights.command('auto')
                    return self.reply()
                if url.path == '/api/scene':           # rejouer une scène du launcher
                    lights.preview = lights.identify = None
                    sc = q.get('scene')
                    if sc in ('day', 'night'):
                        lights.command('theme', sc)
                    elif sc in ('flash_day', 'flash_night'):
                        lights.command(sc)
                        threading.Timer(7, lights.command, ('flash_end',)).start()
                    elif sc == 'storm':
                        lights.command('off')
                        threading.Timer(1.2, lights.command, ('storm',)).start()
                    else:
                        lights.command(sc)
                    return self.reply()
                if url.path == '/api/effect':          # aperçu d'un effet de la galerie
                    lights.preview = (q['id'], json.loads(q.get('params', '{}')), time.time() + float(q.get('seconds', 12)))
                    return self.reply()
                if url.path == '/api/identify':        # faire clignoter une seule zone
                    lights.identify = (q['zone'], time.time() + 6)
                    return self.reply()
                if url.path == '/api/hw':              # effet matériel de la carte mère
                    threading.Thread(target=lights.hw_preview, args=(q['mode'], q.get('color', '#ff46a5')), daemon=True).start()
                    return self.reply()
                if url.path == '/api/colortest':
                    lights.colortest = (q['zone'], time.time())
                    return self.reply()
                if url.path == '/api/pause_conflicts':  # laisser GIGABYTE Control Center ouvert quelques minutes
                    lights.conflicts_paused_until = time.time() + 60 * float(q.get('minutes', 10))
                    log.info('GIGABYTE Control Center autorisé pendant %s min', q.get('minutes', 10))
                    return self.reply()
                if url.path == '/api/stoptest':        # arrête un aperçu ou une identification en cours
                    lights.preview = lights.identify = lights.colortest = None
                    lights.hw_stop = True
                    return self.reply()
                if url.path == '/api/stop':
                    lights.preview = lights.identify = None
                    lights.command('auto')
                    return self.reply()
                self.reply(404)

            def do_POST(self):
                if self.path == '/api/save':
                    lights.save(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                    return self.reply()
                if self.path == '/api/live':
                    lights.live(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                    return self.reply()
                self.reply(404)

        threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever, daemon=True).start()
        log.info('lumières prêtes')
        while True:
            start = time.time()
            self.tick()
            time.sleep(max(0, 1 / FPS - (time.time() - start)))


def send(do, theme=None):
    """Envoie un ordre au programme lumières (utilisé par le launcher). Ne bloque jamais."""
    import urllib.request
    q = {'do': do, **({'theme': theme} if theme else {})}

    def go():
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/cmd?{urllib.parse.urlencode(q)}', timeout=2).close()
        except OSError:
            pass
    threading.Thread(target=go, daemon=True).start()


def chip_reset():
    """Éteint toute la puce RGB de la carte mère (ITE, GIGABYTE) en lui parlant directement, sans OpenRGB.
    Les prises D_LED (ventilateurs, ventirad) gardent leur propre mémoire de couleurs LED par LED, que la carte
    rejoue en « respiration » à l'allumage : on la remplit de noir, puis on rend ces prises à leurs effets
    intégrés (0x32), qu'on remet tous à zéro (registres 0x20 à 0x27) avant de les appliquer."""
    import hid
    path = next(d['path'] for d in hid.enumerate(0x048D) if d['usage'] == 0xCC)
    dev = hid.device()
    dev.open_path(path)
    try:
        for hdr in (0x58, 0x59):                      # D_LED1, D_LED2 : 19 LED par paquet, jusqu'à 1024 LED
            for off in range(0, 1024 * 3, 19 * 3):
                dev.send_feature_report([0xCC, hdr, off & 0xFF, off >> 8, 19 * 3] + [0] * 59)
        dev.send_feature_report([0xCC, 0x32, 0, 0] + [0] * 60)
        for reg in range(0x20, 0x28):
            dev.send_feature_report([0xCC, reg, 0, 0] + [0] * 60)
        dev.send_feature_report([0xCC, 0x28, 0xFF, 0] + [0] * 60)
    finally:
        dev.close()


RAM_WARMUP = 4   # secondes
# qui pilote la RAM : 'openrgb' (direct, sans iCUE) ou 'icue' (kit Corsair) → config.json, settings, ram_driver
RAM_DRIVER = json.loads(CONFIG.read_text(encoding='utf-8'))['settings'].get('ram_driver', 'openrgb')


def ready():
    """Vrai quand le programme lumières pilote la RAM (iCUE) et la carte mère (OpenRGB)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/state', timeout=1) as r:
            c = json.load(r)['connected']
        return c['corsair'] and (c['openrgb'] or not OPENRGB.exists())
    except (OSError, ValueError, KeyError):
        return False


def start_icue():
    """Lance iCUE tout de suite s'il ne tourne pas (au démarrage, Windows ne le lance qu'avec le bureau, trop tard)."""
    import psutil
    exe = json.loads(CONFIG.read_text(encoding='utf-8'))['settings'].get(
        'icue', r'C:\Program Files\Corsair\Corsair iCUE5 Software\iCUE.exe')
    if RAM_DRIVER != 'icue':
        return
    if Path(exe).exists() and not any((p.info['name'] or '').lower() == 'icue.exe' for p in psutil.process_iter(['name'])):
        subprocess.Popen([exe, '--autorun'], cwd=str(Path(exe).parent), creationflags=0x00000008)
        log.info('iCUE lancé en avance')


def ensure_running():
    """Démarre le programme lumières s'il ne tourne pas déjà (le mutex évite les doublons)."""
    import sys
    pyw = Path(sys.executable).with_name('pythonw.exe')
    subprocess.Popen([str(pyw), str(ROOT / 'lights.py')], cwd=ROOT, creationflags=0x08000000)


if __name__ == '__main__':
    ctypes.windll.kernel32.CreateMutexW(None, False, 'SakuraLauncher.lights')
    if ctypes.windll.kernel32.GetLastError() == 183:   # déjà lancé
        raise SystemExit
    LIGHTS = Lights()
    LIGHTS.run()
