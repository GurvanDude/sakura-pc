"""Moteur Windows du Sakura Launcher : lance les programmes, retrouve leurs fenêtres,
les place sur le bon écran dans le bon ordre, puis surveille que rien ne passe devant."""
import ctypes
import json
import os
import subprocess
import threading
import time
from ctypes import wintypes

import psutil

user32 = ctypes.WinDLL('user32', use_last_error=True)
dwmapi = ctypes.WinDLL('dwmapi')

SW_RESTORE, SW_MAXIMIZE = 9, 3
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x4, 0x10, 0x40
HWND_TOP, HWND_TOPMOST, HWND_NOTOPMOST = 0, -1, -2
GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x80
DWMWA_CLOAKED = 14
VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x2

user32.GetWindowLongW.restype = ctypes.c_long
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# Processus qui ouvrent des fenêtres mais ne sont jamais « le jeu » (launchers, navigateur, nous-mêmes…)
NOT_A_GAME = {
    'steam.exe', 'steamwebhelper.exe', 'epicgameslauncher.exe', 'eadesktop.exe', 'ealauncher.exe', 'eabackgroundservice.exe',
    'galaxyclient.exe', 'overwolf.exe', 'overwolfbrowser.exe', 'opera.exe', 'msedgewebview2.exe', 'msedge.exe',
    'python.exe', 'pythonw.exe', 'explorer.exe', 'discord.exe', 'spotify.exe', 'claude.exe', 'code.exe',
    'textinputhost.exe', 'shellexperiencehost.exe', 'searchhost.exe', 'startmenuexperiencehost.exe',
    'applicationframehost.exe', 'crashreportclient.exe', 'unitycrashhandler64.exe', 'riotclientservices.exe',
}


class Win:
    __slots__ = ('hwnd', 'pid', 'proc', 'title', 'rect')

    def __init__(self, hwnd, pid, proc, title, rect):
        self.hwnd, self.pid, self.proc, self.title, self.rect = hwnd, pid, proc, title, rect

    @property
    def area(self):
        l, t, r, b = self.rect
        return max(0, r - l) * max(0, b - t)

    def center(self):
        l, t, r, b = self.rect
        return (l + r) // 2, (t + b) // 2


_names = {}


def proc_name(pid):
    if pid not in _names:
        try:
            _names[pid] = psutil.Process(pid).name().lower()
        except psutil.Error:
            _names[pid] = ''
    return _names[pid]


def windows():
    """Fenêtres principales visibles (pas les fenêtres outils ni les fenêtres « fantômes » d'UWP)."""
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # 4 = GW_OWNER
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        found.append(Win(hwnd, pid.value, proc_name(pid.value), buf.value, (r.left, r.top, r.right, r.bottom)))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def media_play_pause():
    """Touche multimédia Lecture/Pause (agit sur l'appli qui joue, ici Spotify)."""
    VK_MEDIA_PLAY_PAUSE = 0xB3
    user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
    user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_KEYUP, 0)


def foreground():
    return user32.GetForegroundWindow()


def alive(hwnd):
    return bool(user32.IsWindow(hwnd))


# ------------------------------------------------------------------ lancement

def start(launch, browser):
    """Lance une entrée de config : {exe, args, cwd} | {uri} | {url} (dans le navigateur)."""
    if 'exe' in launch:
        exe = launch['exe']
        subprocess.Popen([exe, *launch.get('args', [])], cwd=launch.get('cwd') or os.path.dirname(exe),
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    elif 'url' in launch:
        subprocess.Popen([browser, '--new-window', launch['url']],
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    elif 'uri' in launch:
        os.startfile(launch['uri'])
    elif 'file' in launch:
        os.startfile(launch['file'])
    else:
        raise ValueError(f'lancement inconnu : {launch}')


def wait_window(process=None, title=None, before=(), big_on=None, timeout=30, stop=lambda: False):
    """Attend une fenêtre :
    - d'un processus donné (et dont le titre contient `title` si précisé), ou
    - à défaut, une NOUVELLE grande fenêtre (absente de `before`) qui n'est pas un launcher : c'est le jeu."""
    process = process and process.lower()
    end = time.time() + timeout
    while time.time() < end and not stop():
        for w in windows():
            if process:
                if w.proc == process and (not title or title.lower() in w.title.lower()):
                    return w
            elif w.hwnd not in before and w.proc not in NOT_A_GAME and big_on and _covers(w, big_on, .4):
                return w
        time.sleep(.25)
    return None


def _covers(w, mon, ratio):
    l, t, r, b = w.rect
    x, y, mw, mh = mon
    ix = max(0, min(r, x + mw) - max(l, x))
    iy = max(0, min(b, y + mh) - max(t, y))
    return ix * iy >= ratio * mw * mh


def _title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def wallpaper_windows():
    """Fenêtres de rendu de Wallpaper Engine accrochées au bureau (une par écran quand le fond est chargé)."""
    found = []

    def child(hwnd, _):
        if _class(hwnd).startswith('WPEDesktop') and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    def top(hwnd, _):
        if _class(hwnd) in ('Progman', 'WorkerW'):
            user32.EnumChildWindows(hwnd, WNDENUMPROC(child), 0)
        return True

    user32.EnumWindows(WNDENUMPROC(top), 0)
    return found


def wait_wallpaper(screens, timeout=45, settle=2.5):
    """Attend que Wallpaper Engine affiche ses fonds sur tous les écrans (s'il tourne), puis lui laisse
    `settle` secondes pour finir le premier rendu. Rend la main dans tous les cas après `timeout`."""
    if not any((p.info['name'] or '').lower().startswith('wallpaper') for p in psutil.process_iter(['name'])):
        time.sleep(3)   # pas encore lancé : on lui laisse une chance de démarrer
    end = time.time() + timeout
    while time.time() < end:
        if len(wallpaper_windows()) >= screens:
            time.sleep(settle)
            return True
        time.sleep(.3)
    return False


# ------------------------------------------------------------------ fenêtres

def place(hwnd, mon):
    """Met la fenêtre sur l'écran `mon` (x, y, w, h) et l'agrandit, sans l'activer."""
    x, y, w, h = mon
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, None, x + 40, y + 40, w - 80, h - 80, SWP_NOZORDER | SWP_NOACTIVATE)
    user32.ShowWindow(hwnd, SW_MAXIMIZE)


def restack(app_hwnds, focus_hwnd=None):
    """Empile les applis (de la moins prioritaire à la n°1) puis rend le focus à `focus_hwnd`.
    Windows refuse de réordonner les fenêtres d'un programme qui n'est pas au premier plan : on s'attache
    donc au fil de la fenêtre active le temps de l'opération (seule méthode qui marche à coup sûr)."""
    fg = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(fg, None)
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    attached = bool(tid and tid != me and user32.AttachThreadInput(me, tid, True))
    try:
        for h in app_hwnds:
            if alive(h):
                user32.BringWindowToTop(h)
    finally:
        if attached:
            user32.AttachThreadInput(me, tid, False)
    if focus_hwnd:
        focus(focus_hwnd)


def signal_shell_ready():
    """Dit à Windows que la « coquille » est prête : l'écran Bienvenue (photo, nom, rond qui tourne) disparaît.
    D'habitude c'est l'Explorateur qui envoie ce signal ; en mode coquille, c'est au launcher de le faire."""
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenEventW.restype = wintypes.HANDLE
    for name in ('ShellDesktopSwitchEvent', r'Global\ShellDesktopSwitchEvent'):
        h = kernel32.OpenEventW(0x0002, False, name)   # EVENT_MODIFY_STATE
        if h:
            kernel32.SetEvent(h)
            kernel32.CloseHandle(h)
            return True
    return False


def cover(hwnd, mon, activate=True):
    """Fenêtre du launcher : occupe tout l'écran, au-dessus de tout, barre des tâches comprise."""
    x, y, w, h = mon
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_SHOWWINDOW | (0 if activate else SWP_NOACTIVATE))


def cover_all(covers):
    """Remet le launcher par-dessus tout, même si une autre appli vient de passer au premier plan
    (écran de démarrage de FL Studio…) : comme pour `restack`, on s'attache au fil de la fenêtre active."""
    fg = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(fg, None)
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    attached = bool(tid and tid != me and user32.AttachThreadInput(me, tid, True))
    try:
        for hwnd, mon in covers:
            if alive(hwnd):
                cover(hwnd, mon, activate=False)
                user32.BringWindowToTop(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, tid, False)


def focus(hwnd):
    """Donne le premier plan à une fenêtre (avec l'astuce de la touche Alt que Windows exige)."""
    if not alive(hwnd):
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)


def arrange(app_hwnds, focus_hwnd):
    """app_hwnds : de la moins prioritaire à la n°1. La n°1 finit au-dessus, puis le focus va au jeu."""
    restack(app_hwnds, focus_hwnd)


def in_order(app_hwnds):
    """Vrai si les applis sont empilées comme voulu : la n°1 (dernière de la liste) tout en haut."""
    z = {w.hwnd: i for i, w in enumerate(windows())}   # EnumWindows parcourt du haut vers le bas
    pos = [z[h] for h in reversed(app_hwnds) if h in z]
    return pos == sorted(pos)


def on_screen(hwnd, mon):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    x, y, w, h = mon
    return x <= cx < x + w and y <= cy < y + h


def keep_on(app_hwnds, mon):
    """Remet sur l'écran voulu les applis qui se sont replacées ailleurs (Claude retourne à sa dernière position)."""
    moved = False
    for h in app_hwnds:
        if alive(h) and not on_screen(h, mon):
            place(h, mon)
            moved = True
    return moved


class InputWatch:
    """Repère les vrais gestes de l'utilisateur (clics et touches), pas les simples mouvements de souris,
    grâce aux crochets bas niveau de Windows (dans un fil à part, avec sa propre boucle de messages)."""
    WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
    CLICKS = {0x201, 0x204, 0x207, 0x20A, 0x20B}   # boutons gauche/droit/milieu, molette, boutons latéraux
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    def __init__(self):
        self.last = 0.0
        self._procs = []
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, self.HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        threading.Thread(target=self._run, daemon=True).start()

    def seconds_since(self):
        return time.time() - self.last

    def _run(self):
        # on ignore les clics et touches simulés par un programme (dont la touche Alt du gardien lui-même)
        def mouse(code, wparam, lparam):
            if code >= 0 and wparam in self.CLICKS:
                flags = ctypes.cast(lparam, ctypes.POINTER(wintypes.DWORD))[3]      # MSLLHOOKSTRUCT.flags
                if not flags & 0x1:                                                   # LLMHF_INJECTED
                    self.last = time.time()
            return user32.CallNextHookEx(None, code, wparam, lparam)

        def key(code, wparam, lparam):
            if code >= 0 and wparam in (0x100, 0x104):   # touche enfoncée (y compris Alt+Tab)
                flags = ctypes.cast(lparam, ctypes.POINTER(wintypes.DWORD))[2]      # KBDLLHOOKSTRUCT.flags
                if not flags & 0x10:                                                  # LLKHF_INJECTED
                    self.last = time.time()
            return user32.CallNextHookEx(None, code, wparam, lparam)

        self._procs = [self.HOOKPROC(mouse), self.HOOKPROC(key)]
        user32.SetWindowsHookExW(self.WH_MOUSE_LL, self._procs[0], None, 0)
        user32.SetWindowsHookExW(self.WH_KEYBOARD_LL, self._procs[1], None, 0)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


def guard(app_hwnds, focus_hwnd, seconds, side=None, log=lambda *a: None):
    """Pendant `seconds` :
    - si une appli choisie quitte l'écran de droite, on l'y remet ;
    - si une fenêtre qui n'existait pas encore (mise à jour Discord, Steam, launcher EA…) passe au premier plan,
      on remet l'ordre voulu et le focus ;
    - si une des applis choisies se réaffiche par-dessus une autre (Discord le fait au démarrage),
      on rétablit l'empilement sans toucher au focus.
    Dès que tu agis toi-même (clic, clavier), le gardien te laisse faire."""
    known = {w.hwnd for w in windows()}
    ours = set(app_hwnds) | ({focus_hwnd} if focus_hwnd else set())
    end = time.time() + seconds
    enforce_order = keep_side = True
    user = InputWatch()
    procs = {}
    for w in windows():
        if w.hwnd in app_hwnds:
            procs[w.hwnd] = w.proc
    app_hwnds = list(app_hwnds)
    while time.time() < end:
        # une appli a remplacé sa fenêtre (Spotify recrée la sienne au démarrage) : on suit la nouvelle
        for i, h in enumerate(app_hwnds):
            if not alive(h) and procs.get(h):
                new = max((w for w in windows() if w.proc == procs[h]), key=lambda w: w.area, default=None)
                if new:
                    log('gardien : %s a changé de fenêtre, on suit la nouvelle', procs[h])
                    procs[new.hwnd] = procs[h]
                    app_hwnds[i] = new.hwnd
                    ours.add(new.hwnd)
        fg = foreground()
        if focus_hwnd and not alive(focus_hwnd) and fg and fg not in known:
            # le jeu a remplacé sa fenêtre (écran de chargement → fenêtre finale) : on suit la nouvelle
            focus_hwnd = fg
            ours.add(fg)
        user_acted = user.seconds_since() < 1.5   # clic ou touche à l'instant : c'est toi, on te laisse faire
        if fg and fg not in ours and fg not in known:
            if not user_acted:
                log('gardien : nouvelle fenêtre au premier plan (%s), ordre rétabli', _title(fg))
                time.sleep(.15)
                arrange(app_hwnds, focus_hwnd)
            known = {w.hwnd for w in windows()}
        elif keep_side and side and any(alive(h) and not on_screen(h, side) for h in app_hwnds):
            if user_acted:
                keep_side = False
                log('gardien : tu as déplacé une appli, on te laisse faire')
            else:
                log("gardien : appli revenue sur l'écran de droite")
                keep_on(app_hwnds, side)
                restack(app_hwnds, focus_hwnd)
        elif enforce_order and len(app_hwnds) > 1 and not in_order(app_hwnds):
            if user_acted:
                enforce_order = False
                log("gardien : tu as changé d'appli au premier plan, on te laisse faire")
            else:
                log('gardien : une appli est passée devant (%s), ordre rétabli', _title(user32.GetForegroundWindow()))
                restack(app_hwnds, focus_hwnd)
        time.sleep(.3)


# ------------------------------------------------------------------ son

class Muter:
    """Coupe le son de toutes les applis sauf celui du launcher (ses processus WebView2 sont ses enfants),
    y compris les sons qui démarrent pendant le chargement ; stop() rend le son à tout ce qu'on a coupé.
    Ce qu'on coupe est noté dans `memo` : si le launcher a été tué avant de rendre le son,
    le lancement suivant le rend en premier."""

    def __init__(self, own_pid, memo):
        self.own = own_pid
        self.memo = memo            # fichier .json des sessions coupées
        self.muted = set()          # identifiants des sessions qu'on a rendues muettes
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, pause=()):
        """`pause` : processus à mettre en pause s'ils jouent du son au moment où on le rend (ex. Spotify)."""
        self._pause = {p.lower() for p in pause}
        if self._thread and self._thread.is_alive():
            self._stop.set()
            self._thread.join(5)

    def _ours(self, pid):
        """Le son du launcher, c'est celui de SES fenêtres WebView2 ; les applis qu'il lance restent muettes."""
        try:
            p = psutil.Process(pid)
            return p.name().lower() == 'msedgewebview2.exe' and any(a.pid == self.own for a in p.parents())
        except psutil.Error:
            return False

    def _run(self):
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        seen = set()
        self._restore_leftovers(AudioUtilities)
        try:
            while not self._stop.is_set():
                for s in AudioUtilities.GetAllSessions():
                    key = s.InstanceIdentifier
                    pid = s.ProcessId
                    if key in seen:
                        continue
                    seen.add(key)
                    if pid and self._ours(pid):   # pid 0 = sons système de Windows (connexion de périphérique…)
                        continue
                    vol = s.SimpleAudioVolume
                    if not vol.GetMute():   # déjà muet avant nous : on n'y touchera pas
                        vol.SetMute(1, None)
                        self.muted.add(key)
                        self.memo.write_text(json.dumps(sorted(self.muted)), encoding='utf-8')
                self._stop.wait(.4)
        finally:
            playing = {(s.Process.name().lower() if s.Process else '') for s in AudioUtilities.GetAllSessions() if s.State == 1}
            if playing & getattr(self, '_pause', set()):
                media_play_pause()
            for s in AudioUtilities.GetAllSessions():
                if s.InstanceIdentifier in self.muted:
                    s.SimpleAudioVolume.SetMute(0, None)
            self.memo.unlink(missing_ok=True)
            comtypes.CoUninitialize()

    def _restore_leftovers(self, AudioUtilities):
        try:
            left = set(json.loads(self.memo.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            return
        for s in AudioUtilities.GetAllSessions():
            if s.InstanceIdentifier in left:
                s.SimpleAudioVolume.SetMute(0, None)
        self.memo.unlink(missing_ok=True)


# ------------------------------------------------------------------ applis indésirables au démarrage

class Sweeper:
    """Au démarrage en mode coquille, certaines applis se lancent malgré les réglages (Discord, Teams…),
    parfois plus d'une minute après le bureau. Pendant au moins `boot` secondes, et tant que le launcher
    est ouvert plus `linger` secondes, on ferme celles de la liste `blocked`, sauf celles que le launcher
    a lui-même lancées (allowed)."""

    def __init__(self, blocked, linger=30, boot=150):
        self.blocked = {b.lower() for b in blocked}
        self.allowed = set()
        self.linger = linger
        self.closed_at = None
        self.until_boot = time.time() + boot
        self.killed = []
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def allow(self, names):
        self.allowed |= {n.lower() for n in names if n}

    def launcher_closed(self):
        self.closed_at = time.time()

    def wait(self):
        self._thread.join(max(self.until_boot - time.time(), self.linger) + 5)

    def _run(self):
        while self.closed_at is None or time.time() < max(self.closed_at + self.linger, self.until_boot):
            for p in psutil.process_iter(['name']):
                name = (p.info['name'] or '').lower()
                if name in self.blocked and name not in self.allowed:
                    try:
                        p.kill()
                        self.killed.append(name)
                    except psutil.Error:
                        pass
            time.sleep(1)
