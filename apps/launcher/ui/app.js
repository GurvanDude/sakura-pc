(function () {
  const q = new URLSearchParams(location.search);
  const SCREEN = q.get('screen') === 'apps' ? 'apps' : 'games';
  const MAIN = SCREEN === 'games';
  const hour = new Date().getHours();
  const THEME = q.get('theme') || (hour >= 8 && hour < 18 ? 'day' : 'night');
  const BGI = +q.get(MAIN ? 'bg' : 'sbg') || 0;
  const data = window.LAUNCHER_DATA;
  const api = () => window.pywebview && window.pywebview.api;
  const $ = s => document.querySelector(s);
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  document.body.classList.add('theme-' + THEME, 'screen-' + SCREEN);

  // ---- décor : photo détaillée sur l'écran principal, version simple sur le secondaire
  const bgList = LAUNCHER_BG[THEME][MAIN ? 'main' : 'side'];
  $('#scene .photo').style.backgroundImage = `url(assets/bg/${bgList[BGI % bgList.length]}.jpg)`;
  const petals = new Petals($('#petals'), THEME);

  // ---- ouverture : une tempête de pétales part du bord droit de l'écran de droite et traverse les deux
  // écrans d'un seul mouvement continu (démarrage et arrivée en douceur, vitesse quasi constante au milieu,
  // donc aucune cassure au passage d'un écran à l'autre). Elle révèle l'appli derrière elle ;
  // la chute normale des pétales s'installe dans son sillage.
  // Au démarrage, un message de bienvenue s'affiche d'abord sur le voile ; la tempête l'emporte avec lui.
  // Après un changement jour/nuit (?wave=1), la tempête repart tout de suite, sans message.
  (function intro() {
    if (q.get('nointro')) { document.body.classList.remove('preintro'); return; }
    const WAVE = !!q.get('wave'), DELAY = WAVE ? 250 : 3200;
    const SIDE_W = +(q.get('sideW') || 1920), MAIN_W = +(q.get('mainW') || 2560);
    const W = innerWidth, offset = MAIN ? SIDE_W : 0, total = SIDE_W + MAIN_W + 700, T = 4800;
    // linéaire au milieu, adouci seulement sur les 15 % du début et de la fin
    const ease = t => {
      const a = .15, v = 1 / (1 - a);
      if (t < a) return v * t * t / (2 * a);
      if (t > 1 - a) return 1 - v * (1 - t) ** 2 / (2 * a);
      return v * (t - a / 2);
    };
    const veil = document.body.appendChild(Object.assign(document.createElement('div'), { id: 'reveal' }));
    const front = document.body.appendChild(Object.assign(document.createElement('div'), { className: 'reveal-front' }));
    if (MAIN && !WAVE) {
      veil.innerHTML = `<div class="welcome"><div class="jp">ようこそ</div>
        <div class="hello">${[...'Bienvenue'].map((c, i) => `<span style="animation-delay:${(.3 + i * .05).toFixed(2)}s">${c}</span>`).join('')}</div>
        <div class="who">${esc(data.name || '')}</div></div>`;
      setTimeout(() => Sfx.welcome(), 300);
    }
    // lumières du PC : la tempête démarre avec celle de l'écran (envoyée par un seul des deux écrans)
    const leadsLights = MAIN ? !+(q.get('sideW') || 1920) : true;
    petals.ambient = 0; petals.minX = W;
    let t0 = Infinity, released = false, started = false, lastX = -400, lastT = 0;
    function begin() {
      if (started) return;
      started = true;
      t0 = lastT = performance.now();
      if (!MAIN) Sfx.intro();
      // tempête lumineuse aussi lors d'un passage jour/nuit : elle se termine sur le style du nouveau thème
      if (leadsLights && api()) api().rgb('storm', THEME);
    }
    // Dans l'appli (?hold=1), le launcher donne le départ quand les lumières du PC sont prêtes (iCUE compris),
    // pour que la tempête lumineuse et celle de l'écran partent ensemble ; le message de bienvenue patiente.
    if (q.get('hold') && !WAVE) { window.__introGo = begin; setTimeout(begin, 45000); }
    else setTimeout(begin, DELAY);
    (function frame(now) {
      const p = Math.max(0, Math.min(1, (now - t0) / T));
      const x = ease(p) * total - 350 - offset;     // distance du front au bord droit de cet écran
      const speed = Math.max(0, (x - lastX) / Math.max(.001, (now - lastT) / 1000));
      lastX = x; lastT = now;
      document.body.style.setProperty('--x', x + 'px');
      if (x > -300 && x < W + 300) {
        // plus le front va vite, plus la tempête est dense
        const n = 4 + Math.min(10, speed / 260);
        for (let i = 0; i < n; i++) {
          petals.fling(W - x + Math.random() * 380 - 60, Math.random() * innerHeight,
            -(250 + speed * (.7 + Math.random() * .9)), (Math.random() - .5) * 260, .8 + Math.random() * 1.2);
        }
      }
      petals.minX = Math.max(0, W - x + 200);
      petals.ambient = Math.max(0, Math.min(1, (x - 200) / W));
      if (!released && x > W * .3) { released = true; document.body.classList.remove('preintro'); }
      if (p < 1) requestAnimationFrame(frame);
      else { veil.remove(); front.remove(); document.body.classList.remove('preintro'); petals.ambient = 1; petals.minX = 0; }
    })(performance.now());
  })();

  // ---- communication entre les deux écrans (Python dans l'appli, page parente dans l'aperçu)
  const Bus = {
    send(msg) {
      if (api()) api().broadcast(SCREEN, msg);
      else if (parent !== window) parent.postMessage({ sakura: msg, from: SCREEN }, '*');
    },
  };
  window.__sakuraReceive = msg => onMessage(msg);
  addEventListener('message', e => e.data && e.data.sakura && e.data.from !== SCREEN && onMessage(e.data.sakura));

  // ---- bascule jour / nuit : une vague de pétales recouvre l'écran, puis la tempête révèle le thème opposé
  const OTHER = THEME === 'day' ? 'night' : 'day';
  $('#themeBtn').innerHTML = THEME === 'day'
    ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" fill="currentColor"/></svg>'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5" fill="currentColor"/><g stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></g></svg>';
  $('#themeBtn').title = THEME === 'day' ? 'Passer en mode nuit' : 'Passer en mode jour';
  $('#themeBtn').onclick = () => { Sfx.unlock(); Bus.send({ type: 'theme' }); switchTheme(); };
  let switching = false;
  function switchTheme() {
    if (switching) return;
    switching = true;
    Sfx.exit();
    petals.gust(1.2, 160);
    const cover = document.body.appendChild(Object.assign(document.createElement('div'), { className: 'switch-veil ' + OTHER }));
    requestAnimationFrame(() => cover.classList.add('on'));
    const url = new URL(location.href);
    url.searchParams.set('theme', OTHER);
    url.searchParams.set('wave', '1');
    url.searchParams.delete('nointro');
    setTimeout(() => location.replace(url), 1100);
  }

  // ---- horloge
  function tick() {
    const d = new Date(), h = d.getHours();
    $('#time').textContent = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    $('#date').textContent = d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
    $('#greet').textContent = h >= 5 && h < 11 ? 'おはよう' : h >= 11 && h < 18 ? 'こんにちは' : 'こんばんは';
  }
  tick(); setInterval(tick, 10000);

  // ---- titre lettre par lettre
  const titles = { games: ['今日は何で遊ぶ？', "À quoi on joue aujourd'hui ?"], apps: ['お供のアプリは？', 'Quelle application à côté ?'] };
  $('#title-jp').textContent = titles[SCREEN][0];
  $('#title').innerHTML = [...titles[SCREEN][1]].map((c, i) => `<span class="ch" style="animation-delay:${(.55 + i * .028).toFixed(3)}s">${c}</span>`).join('');
  document.fonts.ready.then(() => {
    const ch = $('#title').querySelectorAll('.ch'), first = ch[0], last = ch[ch.length - 1];
    const w = last.offsetLeft + last.offsetWidth - first.offsetLeft;
    $('.title').style.setProperty('--bw', w + innerHeight / 90 * 3 + 'px');
  });

  // ---- cartes
  // ordre « dernier lancé en premier » : config.json dans l'appli, stockage du navigateur dans l'aperçu
  const RECENT_KEY = 'sakura.recent';
  const store = {
    get() {
      if (data.recent && data.recent.length) return data.recent;
      try { return JSON.parse(localStorage.getItem(RECENT_KEY)) || []; } catch { return []; }
    },
    set(v) {
      if (api()) api().set_recent(v);
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(v)); } catch {}
    },
  };
  const recent = store.get();
  const rank = id => { const i = recent.indexOf(id); return i < 0 ? Infinity : i; };
  const items = MAIN ? data.games.map((g, i) => [g, i]).sort((a, b) => rank(a[0].id) - rank(b[0].id) || a[1] - b[1]).map(x => x[0]) : data.apps;
  const grid = $('#grid');
  const appIcon = a => a.icon ? `<img class="ico" src="${a.icon}" alt="">` : `<span class="ico letter">${esc(a.name[0] || '?')}</span>`;
  // jeu sans jaquette (ajouté à la main) : carte avec son nom
  const coverArt = g => g.cover ? `<img class="cover" src="${g.cover}" alt="" loading="lazy">` : `<div class="noart"><span>遊</span><b>${esc(g.name)}</b></div>`;

  grid.innerHTML = items.map((it, i) => {
    if (!MAIN) {
      return `<button class="card" data-id="${it.id}" role="option" style="animation-delay:${(.8 + i * .06).toFixed(2)}s">
        <div class="art">${appIcon(it)}</div><div class="name">${esc(it.name)}</div>${it.sub ? `<div class="sub">${esc(it.sub)}</div>` : ''}</button>`;
    }
    return `<button class="card" data-id="${it.id}" role="option" style="animation-delay:${(.7 + Math.min(i, 30) * .025).toFixed(3)}s">
      <div class="art">${coverArt(it)}</div><div class="shine"></div>
      <div class="name">${esc(it.name)}</div><div class="hanko">選</div></button>`;
  }).join('') + `<button class="card add" data-add="1" style="animation-delay:1.2s"><div class="plus">＋</div><span>${MAIN ? 'Ajouter<br>un jeu' : 'Ajouter une appli'}</span></button>`;

  // nom du jeu au survol
  const tip = document.body.appendChild(Object.assign(document.createElement('div'), { className: 'hovername' }));
  function showTip(card) {
    if (!MAIN || !card || card.dataset.add) { tip.classList.remove('on'); return; }
    const r = card.getBoundingClientRect();
    tip.textContent = items.find(x => x.id === card.dataset.id).name;
    tip.style.left = r.left + r.width / 2 + 'px'; tip.style.top = r.top - 10 + 'px';
    tip.classList.add('on');
  }

  // ---- sélection
  let game = null;
  const order = [];       // applis dans l'ordre de clic : order[0] = premier plan
  let remoteApps = [];    // côté écran principal : ordre reçu de l'écran secondaire

  function renderRanks() {
    grid.querySelectorAll('.rank').forEach(r => r.remove());
    grid.querySelectorAll('.card').forEach(c => c.classList.toggle('selected', order.includes(c.dataset.id)));
    order.forEach((id, i) => {
      const card = grid.querySelector(`[data-id="${id}"]`);
      card.insertAdjacentHTML('beforeend', `<div class="rank">${i + 1}${i === 0 ? '<small>1er plan</small>' : ''}</div>`);
    });
  }

  grid.addEventListener('click', e => {
    const card = e.target.closest('.card'); if (!card) return;
    Sfx.unlock();
    if (card.dataset.add) {
      Sfx.select(3);
      if (!api()) { toast("Dans l'appli, ce bouton ouvre le sélecteur de fichier (.exe, raccourci, ROM…)"); return; }
      api().add_item(SCREEN).then(name => {
        if (!name) return;
        toast(`${name} ajouté`);
        setTimeout(() => location.replace(location.href.replace(/&nointro=1/, '') + '&nointro=1'), 900);
      });
      return;
    }
    const id = card.dataset.id, r = card.getBoundingClientRect();
    if (MAIN) {
      const was = game === id;
      grid.querySelectorAll('.card.selected').forEach(c => c.classList.remove('selected'));
      game = was ? null : id;
      if (!was) { card.classList.add('selected'); Sfx.select(items.findIndex(x => x.id === id)); petals.burst(r.left + r.width / 2, r.top + r.height / 3, 6, .55); }
      else Sfx.deselect();
      renderPick();
    } else {
      const k = order.indexOf(id);
      if (k >= 0) { order.splice(k, 1); Sfx.unpick(); }
      else { order.push(id); Sfx.pick(order.length); petals.burst(r.left + r.width / 2, r.top + r.height / 3, 10, .7); }
      renderRanks();
      Bus.send({ type: 'apps', ids: [...order] });
    }
    grid.classList.toggle('has-choice', MAIN ? !!game : order.length > 0);
    renderFooter();
  });
  grid.addEventListener('mouseover', e => { const c = e.target.closest('.card'); if (c && !c.contains(e.relatedTarget)) { Sfx.hover(); showTip(c); } });
  grid.addEventListener('mouseleave', () => showTip(null));
  grid.addEventListener('scroll', () => showTip(null));
  grid.addEventListener('focusin', e => showTip(e.target.closest('.card')));
  addEventListener('pointerdown', () => Sfx.unlock(), { once: true });

  const gameOf = id => data.games.find(x => x.id === id);
  const appOf = id => data.apps.find(x => x.id === id);

  function renderPick() {
    const g = gameOf(game), st = $('#stage');
    st.innerHTML = g ? `<div class="pick">${g.cover ? `<img src="${g.cover}" alt="">` : ''}<div><div class="kj">On joue à</div><div class="nm">${esc(g.name)}</div></div></div>` : '';
  }

  // ---- bas d'écran
  function renderFooter() {
    const left = $('.bottom .left'), center = $('.bottom .center');
    if (MAIN) {
      if (!left.firstChild) {
        left.innerHTML = `<button class="music" id="music" type="button"><span class="eq"><i></i><i></i><i></i><i></i></span>
          <span>Je suis d'humeur musicale aujourd'hui<small>音楽の気分 · lance FL Studio</small></span></button>`;
        center.innerHTML = `<button class="go" id="go" type="button"><span class="kj">出発</span>C'est parti</button>`;
        $('#music').onclick = () => { Sfx.unlock(); musicMode(); };
        $('#go').onclick = () => { Sfx.unlock(); go(); };
      }
      $('#go').classList.toggle('idle', !game && !remoteApps.length);
    }
  }
  renderFooter();
  if (!MAIN) $('#classic').remove();
  else $('#classic').onclick = () => { Sfx.unlock(); classic(); };

  $('#ambient').onclick = () => {
    Sfx.unlock();
    const on = $('#ambient').getAttribute('aria-pressed') !== 'true';
    $('#ambient').setAttribute('aria-pressed', on);
    Sfx.ambient(on);
  };

  // ---- séquence de lancement
  const ov = $('#overlay');
  function overlay(kind, html) {
    ov.className = 'ov-' + kind; ov.innerHTML = `<div class="veil"></div>${html}`;
    requestAnimationFrame(() => ov.classList.add('on'));
  }
  function inkRing(x, y) {
    document.body.appendChild(Object.assign(document.createElement('div'), { className: 'ink-ring', style: `left:${x}px;top:${y}px` }));
  }
  const stepHtml = s => `<li data-id="${s.id}" data-state="wait" style="animation-delay:${s.delay || 0}s"><span class="st"></span>
    ${s.icon ? `<img src="${s.icon}" alt="">` : ''}<span>${esc(s.name)}</span><em>${esc(s.note || '')}</em></li>`;

  // Plan « C'est parti » : applis de la moins prioritaire à la n°1 (ouverte en dernier, donc au-dessus), puis le jeu.
  // Musique et lancement classique : pas de liste d'étapes, juste leur écran spécial jusqu'à ce que tout soit prêt.
  function buildPlan(kind) {
    if (kind === 'music') return { kind, steps: [{ id: 'flstudio', name: 'FL Studio 2026' }] };
    if (kind === 'classic') return { kind, steps: data.classic };
    const steps = [...remoteApps].reverse().map(id => {
      const a = appOf(id), rank = remoteApps.indexOf(id);
      return { id, name: a.name, icon: a.icon, note: rank === 0 ? 'écran droit · 1er plan' : `écran droit · plan ${rank + 1}` };
    });
    const g = gameOf(game);
    if (g) steps.push({ id: g.id, name: g.name, icon: g.cover, note: 'attente de l\'écran titre…', game: true });
    return { kind, title: g ? g.name : 'Tes applis', cover: g && g.cover, steps };
  }

  function showLaunch(plan) {
    document.body.classList.add('launching');
    if (MAIN) {
      overlay('launch', `<div class="launch">
        ${plan.cover ? `<div class="hero"><img src="${plan.cover}" alt=""></div>` : `<div class="hero kj">出</div>`}
        <div class="info"><div class="jp">準備中 · préparation</div><h2>${esc(plan.title)}</h2>
        <ul class="steps">${plan.steps.map((s, i) => stepHtml({ ...s, delay: .3 + i * .08 })).join('')}</ul></div></div>`);
    } else {
      const mine = plan.steps.filter(s => !s.game);
      overlay('launch', `<div class="msg"><div class="big-kj" style="font-size:9rem">お供</div>
        <div class="line">${mine.length ? 'Tes applis arrivent' : 'Bon jeu !'}</div>
        <ul class="steps" style="margin-top:2.5rem;text-align:left">${mine.map((s, i) => stepHtml({ ...s, delay: .3 + i * .08 })).join('')}</ul></div>`);
    }
  }

  function setStep(id, state) {
    const li = ov.querySelector(`.steps li[data-id="${id}"]`);
    if (!li) return;
    li.dataset.state = state;
    if (state === 'ok') Sfx.step();
  }

  // Dans l'appli, Python lance tout, renvoie la progression puis « ready » ; dans l'aperçu, on simule.
  async function runPlan(plan) {
    if (window.pywebview && window.pywebview.api) return window.pywebview.api.launch(plan);
    if (plan.kind !== 'go') { await wait(plan.kind === 'music' ? 8000 : 5000); Bus.send({ type: 'ready' }); exit(); return; }
    await wait(1100);
    for (const s of plan.steps) {
      Bus.send({ type: 'progress', id: s.id, state: 'run' }); setStep(s.id, 'run');
      await wait(s.game ? 2600 : 850);
      Bus.send({ type: 'progress', id: s.id, state: 'ok' }); setStep(s.id, 'ok');
    }
    await wait(600);
    Bus.send({ type: 'ready' }); exit();
  }

  let kind = 'go';
  async function exit() {
    Sfx.stopMusic();
    Sfx.exit();
    petals.setMode('fall');
    petals.gust(1.8, 160);
    if (kind === 'go') document.body.insertAdjacentHTML('beforeend', `<div class="bye"><span>またね</span><small>À très vite</small></div>`);
    document.body.classList.add('exiting');
    await wait(2700);
    document.body.classList.add('gone');
    await wait(900);
    if (window.pywebview && window.pywebview.api) window.pywebview.api.close();
    else location.reload();   // aperçu : on revient au début
  }

  function go() {
    if (!game && !remoteApps.length) {
      const b = $('#go'); b.classList.remove('shake'); void b.offsetWidth; b.classList.add('shake');
      toast('Choisis au moins un jeu ou une appli');
      return;
    }
    Sfx.go();
    if (api()) api().rgb('flash');
    const b = $('#go').getBoundingClientRect();
    inkRing(b.left + b.width / 2, b.top + b.height / 2);
    petals.burst(b.left + b.width / 2, b.top + b.height / 2, 70, 1.6);
    const plan = buildPlan('go');
    if (game) store.set([game, ...recent.filter(id => id !== game)].slice(0, 100));
    Bus.send({ type: 'plan', plan });
    showLaunch(plan);
    flyCover().then(() => { ov.querySelector('.launch').classList.add('landed'); runPlan(plan); });
  }

  // la grande jaquette (au-dessus de l'étagère) s'envole jusqu'à la place exacte de celle de l'écran de lancement,
  // en gardant son contour rose ; la vraie jaquette prend le relais à l'arrivée
  function flyCover() {
    const src = $('#stage .pick img'), hero = ov.querySelector('.launch .hero');
    if (!src || !hero) { hero && ov.querySelector('.launch').classList.add('landed'); return wait(500); }
    hero.style.visibility = 'hidden';
    const a = src.getBoundingClientRect(), b = hero.getBoundingClientRect();
    const fly = src.cloneNode();
    fly.className = 'fly-cover';
    Object.assign(fly.style, { left: a.left + 'px', top: a.top + 'px', width: a.width + 'px', height: a.height + 'px' });
    document.body.appendChild(fly);
    src.style.visibility = 'hidden';
    const mid = { left: (a.left + b.left) / 2 + 'px', top: Math.min(a.top, b.top) - innerHeight * .08 + 'px', width: (a.width + b.width) / 2 + 'px', height: (a.height + b.height) / 2 + 'px' };
    const anim = fly.animate([
      { left: a.left + 'px', top: a.top + 'px', width: a.width + 'px', height: a.height + 'px', transform: 'rotate(-3deg)' },
      { ...mid, transform: 'rotate(-8deg)', offset: .5 },
      { left: b.left + 'px', top: b.top + 'px', width: b.width + 'px', height: b.height + 'px', transform: 'rotate(0deg)' },
    ], { duration: 1100, easing: 'cubic-bezier(.55,0,.25,1)', fill: 'forwards' });
    return anim.finished.then(() => { hero.style.visibility = ''; fly.remove(); });
  }

  // ---- mode musique : reste sur « Place à la musique » jusqu'à ce que FL Studio soit lancé
  function musicMode() {
    Bus.send({ type: 'music' });
    musicOverlay();
    runPlan(buildPlan('music'));
  }
  function musicOverlay() {
    kind = 'music';
    Sfx.musicLoop();
    petals.setMode('dance');
    for (let i = 0; i < 4; i++) setTimeout(() => petals.burst(innerWidth * Math.random(), innerHeight * .9, 20, 1.2), i * 500);
    let bars = '', notes = '';
    for (let i = 0; i < 48; i++) bars += `<i style="--dl:${(-Math.random()).toFixed(2)}s;--h:${(.3 + Math.random() * .7).toFixed(2)};animation-duration:${(.2 + Math.random() * .3).toFixed(2)}s"></i>`;
    for (let i = 0; i < 18; i++) notes += `<span class="note" style="left:${(5 + Math.random() * 90).toFixed(0)}%;top:${(70 + Math.random() * 25).toFixed(0)}%;--d:${(2.5 + Math.random() * 2.5).toFixed(1)}s;--x:${((Math.random() - .5) * 20).toFixed(0)}vw;animation-delay:${(Math.random() * 6).toFixed(1)}s;animation-iteration-count:infinite">${'♪♫♩♬'[(Math.random() * 4) | 0]}</span>`;
    document.body.classList.add('launching');
    overlay('music', `<div class="bars">${bars}</div>${notes}<div class="msg"><div class="big-kj">音楽の時間</div>
      <div class="line">${MAIN ? 'Place à la musique' : 'Laisse parler le son'}</div></div>`);
  }

  // ---- lancement classique : un ensō (cercle zen) se trace en boucle
  function classic() {
    Bus.send({ type: 'classic' });
    classicOverlay();
    runPlan(buildPlan('classic'));
  }
  function classicOverlay() {
    kind = 'classic';
    Sfx.classic();
    petals.setMode('dance');
    document.body.classList.add('launching');
    overlay('classic', `<svg class="enso" viewBox="0 0 200 200" aria-hidden="true">
        <path d="M100 18 C150 16 184 55 182 102 C180 150 142 183 98 182 C52 180 18 146 19 99 C20 62 44 33 78 22"/></svg>
      <div class="msg"><div class="big-kj" style="font-size:8rem">いつもの</div><div class="line">${MAIN ? 'Lancement classique' : 'Comme d\'habitude'}</div></div>`);
  }

  function onMessage(msg) {
    if (msg.type === 'apps') { remoteApps = msg.ids; renderFooter(); }
    else if (msg.type === 'plan') { if (!MAIN) { Sfx.go(); petals.burst(innerWidth / 2, innerHeight / 2, 50, 1.3); } showLaunch(msg.plan); }
    else if (msg.type === 'progress') setStep(msg.id, msg.state);
    else if (msg.type === 'ready') exit();
    else if (msg.type === 'music') musicOverlay();
    else if (msg.type === 'classic') classicOverlay();
    else if (msg.type === 'theme') switchTheme();
    else if (msg.type === 'intro') window.__introGo && window.__introGo();
  }

  // ---- petit message
  let toastEl;
  function toast(text) {
    toastEl = toastEl || document.body.appendChild(Object.assign(document.createElement('div'), { className: 'toast' }));
    toastEl.textContent = text; toastEl.classList.remove('show'); void toastEl.offsetWidth; toastEl.classList.add('show');
  }

  // ---- clavier et manette
  function move(dx, dy) {
    const list = [...grid.querySelectorAll('.card')]; let i = list.indexOf(document.activeElement);
    if (i < 0) { list[0].focus(); return; }
    const step = { x: 1, y: getComputedStyle(grid).gridTemplateColumns.split(' ').length };
    i = Math.max(0, Math.min(list.length - 1, i + dx * step.x + dy * step.y));
    list[i].focus(); list[i].scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' }); Sfx.hover();
  }
  addEventListener('keydown', e => {
    const k = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (k) { e.preventDefault(); move(...k); }
    if (e.key === 'Enter' && e.ctrlKey && MAIN) go();
    if (e.key === 'Escape' && api()) api().quit();   // quitter sans rien lancer
  });
  let padPrev = {};
  (function pollPad() {
    const pad = navigator.getGamepads && [...navigator.getGamepads()].find(Boolean);
    if (pad) {
      const b = i => pad.buttons[i] && pad.buttons[i].pressed;
      const now = { l: b(14) || pad.axes[0] < -.6, r: b(15) || pad.axes[0] > .6, u: b(12) || pad.axes[1] < -.6, d: b(13) || pad.axes[1] > .6, a: b(0), start: b(9), y: b(3) };
      const hit = k => now[k] && !padPrev[k];
      if (hit('l')) move(-1, 0); if (hit('r')) move(1, 0); if (hit('u')) move(0, -1); if (hit('d')) move(0, 1);
      if (hit('a') && document.activeElement.classList.contains('card')) document.activeElement.click();
      if (hit('start') && MAIN) go();
      if (hit('y') && MAIN) $('#music').click();
      padPrev = now;
    }
    requestAnimationFrame(pollPad);
  })();
})();
