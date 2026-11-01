"""Synchronise la liste des jeux avec ce qui est installé sur le PC (Steam et Epic Games).

- Un jeu installé absent de la liste y est ajouté (en tête, marqué "auto").
- Un jeu ajouté automatiquement puis désinstallé est retiré. Les jeux ajoutés à la main ne sont jamais touchés.
- Jaquette : celle du cache local de Steam si elle existe, sinon téléchargée en arrière-plan depuis Steam.
"""
import json
import logging
import re
import shutil
import threading
import urllib.request
import winreg
from pathlib import Path

log = logging.getLogger('sakura')
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # racine du dépôt, pour core/
from core import paths  # noqa: E402

COVERS = paths.USER / 'covers'
COVERS.mkdir(parents=True, exist_ok=True)

# outils Steam qui ne sont pas des jeux
STEAM_NOT_GAMES = {'228980', '431960', '1070560', '1391110', '1628350', '1493710', '250820'}
EPIC_MANIFESTS = Path(r'C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests')


def steam_root():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
            return Path(winreg.QueryValueEx(k, 'SteamPath')[0])
    except OSError:
        return None


def steam_games():
    """{appid: nom} des jeux Steam complètement installés."""
    root = steam_root()
    if not root:
        return {}
    libs = {root}
    vdf = root / 'steamapps' / 'libraryfolders.vdf'
    if vdf.exists():
        libs |= {Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"(.+?)"', vdf.read_text(encoding='utf-8', errors='replace'))}
    games = {}
    for lib in libs:
        for acf in (lib / 'steamapps').glob('appmanifest_*.acf'):
            text = acf.read_text(encoding='utf-8', errors='replace')
            appid = re.search(r'"appid"\s+"(\d+)"', text)
            name = re.search(r'"name"\s+"(.+?)"', text)
            flags = re.search(r'"StateFlags"\s+"(\d+)"', text)
            if appid and name and flags and int(flags.group(1)) & 4 and appid.group(1) not in STEAM_NOT_GAMES:
                games[appid.group(1)] = name.group(1)
    return games


def epic_games():
    """{AppName: (nom, uri de lancement)} des jeux Epic installés (sans les contenus additionnels)."""
    games = {}
    for item in EPIC_MANIFESTS.glob('*.item'):
        try:
            m = json.loads(item.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not m.get('LaunchExecutable') or m.get('bIsIncompleteInstall') or 'games' not in m.get('AppCategories', ['games']):
            continue
        uri = (f"com.epicgames.launcher://apps/{m['CatalogNamespace']}%3A{m['CatalogItemId']}%3A{m['AppName']}"
               '?action=launch&silent=true')
        games[m['AppName']] = (m['DisplayName'], uri)
    return games


def local_steam_cover(appid):
    root = steam_root()
    cache = root and root / 'appcache' / 'librarycache' / appid
    if cache and cache.exists():
        found = next(cache.rglob('library_600x900*.jpg'), None)
        if found:
            dest = COVERS / f'{appid}.jpg'
            shutil.copyfile(found, dest)
            return f'assets/covers/{appid}.jpg'
    return None


def sync(cfg):
    """Met cfg['games'] à jour. Renvoie la liste des jeux dont la jaquette reste à télécharger."""
    games = cfg['games']
    by_id = {g['id']: g for g in games}
    known_uris = ' '.join(g.get('launch', {}).get('uri', '') for g in games)
    added, removed, to_fetch = [], [], []

    steam = steam_games()
    for appid, name in steam.items():
        if appid in by_id:
            continue
        g = {'id': appid, 'name': name, 'launch': {'uri': f'steam://rungameid/{appid}'}, 'auto': 'steam'}
        cover = local_steam_cover(appid)
        if cover:
            g['cover'] = cover
        else:
            to_fetch.append(g)
        games.insert(0, g)
        added.append(name)

    epic = epic_games()
    for app_name, (name, uri) in epic.items():
        if app_name in known_uris:
            continue
        gid = 'epic-' + re.sub(r'[^a-z0-9]+', '-', app_name.lower())
        games.insert(0, {'id': gid, 'name': name, 'launch': {'uri': uri}, 'auto': 'epic', 'epic': app_name})
        added.append(name)

    # jeux ajoutés automatiquement puis désinstallés
    for g in list(games):
        if (g.get('auto') == 'steam' and g['id'] not in steam) or (g.get('auto') == 'epic' and g.get('epic') not in epic):
            games.remove(g)
            removed.append(g['name'])

    if added or removed:
        log.info('bibliothèque : ajoutés %s, retirés %s', added, removed)
    return to_fetch, bool(added or removed)


def fetch_covers(games, on_done):
    """Télécharge en arrière-plan les jaquettes manquantes depuis le CDN de Steam (prises en compte au lancement suivant)."""
    def run():
        got = False
        for g in games:
            for url in (f"https://cdn.cloudflare.steamstatic.com/steam/apps/{g['id']}/library_600x900_2x.jpg",
                        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{g['id']}/library_600x900.jpg"):
                try:
                    with urllib.request.urlopen(url, timeout=15) as r:
                        data = r.read()
                    if len(data) > 10_000 and data[:2] == b'\xff\xd8':
                        (COVERS / f"{g['id']}.jpg").write_bytes(data)
                        g['cover'] = f"assets/covers/{g['id']}.jpg"
                        got = True
                        break
                except OSError:
                    continue
        if got:
            on_done()
    if games:
        threading.Thread(target=run, daemon=True).start()
