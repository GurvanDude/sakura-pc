(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = value => Sakura.esc(value ?? '');
  const api = () => window.pywebview?.api;
  const coverStyles = new Map();
  let state = null;
  let original = '';
  let dirty = false;
  let savebar;

  const titles = {
    games: ['Jeux', 'Choisis les jeux affichés sur l’écran principal.', 'cover'],
    apps: ['Applis', 'Choisis les applications proposées sur le second écran.', 'icon'],
    classic: ['Classiques', 'Choisis les programmes lancés par le mode classique.', 'icon'],
  };

  function toast(message, error = false) { Sakura.toast(message, {kind: error ? 'warn' : 'ok'}); }
  function changed() { dirty = true; savebar.show(); }
  function clean() { dirty = false; original = JSON.stringify(state); savebar.hide(); }
  function imageUrl(path) { return path ? path.replaceAll('\\', '/') : ''; }
  function launchParts(item) {
    const launch = item.launch || {};
    const type = ['exe', 'url', 'uri', 'file'].find(key => launch[key] != null) || 'exe';
    return [type, launch[type] || ''];
  }
  function setLaunch(item, type, value) {
    const next = {...(item.launch || {})};
    ['exe', 'url', 'uri', 'file'].forEach(key => delete next[key]);
    next[type] = value;
    item.launch = next;
  }

  function renderHours() {
    for (const id of ['dayStart', 'dayEnd']) {
      const select = $('#' + id);
      select.innerHTML = Array.from({length: 24}, (_, hour) => `<option value="${hour}">${hour} h</option>`).join('');
    }
    $('#dayStart').value = state.settings.day_start;
    $('#dayEnd').value = state.settings.day_end;
    updateSentence();
  }
  function updateSentence() {
    const start = +$('#dayStart').value;
    const end = +$('#dayEnd').value;
    state.settings.day_start = start;
    state.settings.day_end = end;
    $('#hoursSentence').textContent = `Le jour va de ${start} h à ${end} h, et la nuit prend le relais le reste du temps.`;
  }
  function renderBackgrounds() {
    const labels = {day: 'Jour', night: 'Nuit', main: 'Écran principal', side: 'Écran secondaire'};
    $('#backgrounds').innerHTML = ['day', 'night'].flatMap(theme => ['main', 'side'].map(screen => {
      const name = state.settings.backgrounds[theme][screen];
      return `<article class="sk-card background-card" data-theme="${theme}" data-screen="${screen}">
        <img src="assets/bg/${esc(name)}.jpg" alt="Aperçu du fond ${labels[theme].toLowerCase()}">
        <div><h3>${labels[theme]} · ${labels[screen]}</h3><p>${esc(name)}</p><button class="sk-btn sk-btn--secondary sk-btn--small change-bg" type="button">Changer</button></div>
      </article>`;
    })).join('');
  }

  function itemHtml(item, kind, index, total) {
    const imageKey = titles[kind][2];
    const path = item[imageKey] || '';
    const painted = kind === 'games' || Boolean(path);
    const [launchType, target] = launchParts(item);
    const extra = {...item};
    ['id', 'name', imageKey, 'launch', 'process', 'auto'].forEach(key => delete extra[key]);
    const thumb = path
      ? `<img class="thumb ${imageKey === 'icon' ? 'icon' : ''}" src="${esc(imageUrl(path))}" alt="Image de ${esc(item.name)}">`
      : `<div class="thumb thumb-fallback" aria-hidden="true">${esc((item.name || '?')[0])}</div>`;
    return `<article class="sk-row item" data-index="${index}" data-image="${esc(path)}" ${painted ? 'data-sk-brush' : ''}>
      ${thumb}
      <div class="sk-row-main item-main">
        <input class="sk-input item-name" value="${esc(item.name)}" aria-label="Nom">
        <details><summary>Avancé</summary><div class="advanced">
          <label>Type <select class="sk-select launch-type">${['exe', 'url', 'uri', 'file'].map(value => `<option value="${value}" ${value === launchType ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
          <label>Cible <input class="sk-input launch-target" value="${esc(target)}"></label>
          <label>Processus <input class="sk-input process" value="${esc(item.process || '')}" placeholder="exemple.exe"></label>
          <label>Ajout auto <input class="sk-input auto" value="${esc(item.auto || '')}" placeholder="Laisse vide si tu n’en as pas besoin"></label>
          <label>Autres options (JSON) <textarea class="extra">${esc(JSON.stringify(extra, null, 2))}</textarea></label>
        </div></details>
      </div>
      <div class="item-actions">
        <button class="sk-chip change-image" type="button">Image</button>
        <button class="sk-chip move up" type="button" aria-label="Monter ${esc(item.name)}" title="Monter" ${index === 0 ? 'disabled' : ''}>↑</button>
        <button class="sk-chip move down" type="button" aria-label="Descendre ${esc(item.name)}" title="Descendre" ${index === total - 1 ? 'disabled' : ''}>↓</button>
        <button class="sk-btn sk-btn--danger sk-btn--small remove" type="button">Retirer</button>
      </div>
    </article>`;
  }

  async function paintRows(panel) {
    const rows = Array.from(panel.querySelectorAll('[data-sk-brush]'));
    await Promise.all(rows.map(async (row, index) => {
      const path = row.dataset.image;
      const image = $('.thumb', row);
      if (!path || image.tagName !== 'IMG') {
        await Sakura.brush(row, {color: 'var(--sk-accent-soft)', variant: index});
      } else {
        if (!coverStyles.has(path)) coverStyles.set(path, Sakura.coverColor(image));
        const style = await coverStyles.get(path);
        await Sakura.brush(row, {color: style.color, variant: index});
        row.classList.toggle('is-dark', style.dark);
        row.style.setProperty('--sk-n', style.dark ? 'var(--sk-cover-dark)' : style.color);
      }
      row.classList.toggle('sk-neon', Sakura.getTheme() === 'night');
    }));
  }

  function renderList(kind) {
    const [title, subtitle] = titles[kind];
    const panel = $('#' + kind);
    const list = state[kind];
    panel.innerHTML = `<div class="heading"><div><h2 class="sk-section-title">${title}</h2><p class="sk-sub">${subtitle}</p></div></div>
      <div class="add-area"><button class="sk-btn sk-btn--primary add-file" type="button">Choisir un programme .exe</button><button class="sk-btn sk-btn--secondary add-link" type="button">Coller une adresse</button>
        <div class="link-form"><input class="sk-input new-name" placeholder="Nom affiché"><input class="sk-input new-address" placeholder="https://… ou steam://…"><button class="sk-btn sk-btn--primary confirm-link" type="button">Ajouter</button></div>
      </div><div class="item-list">${list.length ? list.map((item, index) => itemHtml(item, kind, index, list.length)).join('') : '<div class="empty">Tu n’as encore rien ajouté ici.</div>'}</div>`;
    paintRows(panel);
  }

  function tagEditor(id, key) {
    const values = state.settings[key];
    $('#' + id).innerHTML = `<div class="tag-editor"><input class="sk-input" placeholder="nom-du-programme.exe"><button class="sk-btn sk-btn--secondary sk-btn--small" type="button">Ajouter</button></div><div class="tags">${values.map((value, index) => `<span class="tag">${esc(value)}<button data-i="${index}" type="button" aria-label="Retirer ${esc(value)}">×</button></span>`).join('')}</div>`;
  }
  function renderStartup() {
    tagEditor('bootBlock', 'boot_block');
    tagEditor('pausePlaying', 'pause_if_playing');
    const music = state.music || (state.music = {});
    const [type, target] = launchParts(music);
    $('#musicEditor').innerHTML = `<div class="music-fields"><label>Nom<input class="sk-input" id="musicName" value="${esc(music.name || '')}"></label><label>Programme ou adresse<input class="sk-input" id="musicTarget" value="${esc(target)}"></label><label>Processus<input class="sk-input" id="musicProcess" value="${esc(music.process || '')}" placeholder="musique.exe"></label></div><input type="hidden" id="musicType" value="${type}">`;
  }
  function renderAll() {
    renderHours(); renderBackgrounds(); Object.keys(titles).forEach(renderList); renderStartup();
  }

  async function chooseImage(kind, item) {
    const imageKind = kind === 'games' ? 'cover' : kind === 'background' ? 'background' : 'icon';
    const result = await api().choose_image(imageKind);
    if (!result) return;
    if (result.error) return toast(result.error, true);
    if (kind === 'background') state.settings.backgrounds[item.theme][item.screen] = result.value;
    else item[titles[kind][2]] = result.value;
    changed();
    kind === 'background' ? renderBackgrounds() : renderList(kind);
  }

  $('#dayStart').addEventListener('change', () => { updateSentence(); changed(); });
  $('#dayEnd').addEventListener('change', () => { updateSentence(); changed(); });
  $('#backgrounds').addEventListener('click', event => {
    const card = event.target.closest('.background-card');
    if (event.target.closest('.change-bg') && card) chooseImage('background', card.dataset);
  });

  for (const kind of Object.keys(titles)) {
    const panel = $('#' + kind);
    panel.addEventListener('click', async event => {
      if (event.target.closest('.add-link')) return $('.link-form', panel).classList.toggle('open');
      if (event.target.closest('.add-file')) {
        const result = await api().choose_program(kind, state[kind].map(item => item.id));
        if (!result) return;
        if (result.error) return toast(result.error, true);
        state[kind].push(result); changed(); renderList(kind); return;
      }
      if (event.target.closest('.confirm-link')) {
        const result = await api().make_link($('.new-name', panel).value, $('.new-address', panel).value, state[kind].map(item => item.id));
        if (result.error) return toast(result.error, true);
        state[kind].push(result); changed(); renderList(kind); return;
      }
      const row = event.target.closest('.item');
      if (!row) return;
      const index = +row.dataset.index;
      const item = state[kind][index];
      if (event.target.closest('.change-image')) return chooseImage(kind, item);
      if (event.target.closest('.remove')) {
        const accepted = await Sakura.confirm({title: `Retirer « ${item.name} » ?`, text: 'Le programme reste installé sur ton PC.', yes: 'Oui, retire-le', no: 'Non, laisse'});
        if (accepted) { state[kind].splice(index, 1); changed(); renderList(kind); }
        return;
      }
      const delta = event.target.closest('.up') ? -1 : event.target.closest('.down') ? 1 : 0;
      if (delta && state[kind][index + delta]) {
        [state[kind][index], state[kind][index + delta]] = [state[kind][index + delta], state[kind][index]];
        changed(); renderList(kind);
      }
    });
    panel.addEventListener('input', event => {
      const row = event.target.closest('.item');
      if (!row) return;
      const item = state[kind][+row.dataset.index];
      if (event.target.classList.contains('item-name')) item.name = event.target.value;
      else if (event.target.classList.contains('process')) item.process = event.target.value;
      else if (event.target.classList.contains('auto')) { if (event.target.value) item.auto = event.target.value; else delete item.auto; }
      else if (event.target.classList.contains('launch-target')) setLaunch(item, $('.launch-type', row).value, event.target.value);
      changed();
    });
    panel.addEventListener('change', event => {
      const row = event.target.closest('.item');
      if (!row) return;
      const item = state[kind][+row.dataset.index];
      if (event.target.classList.contains('launch-type')) setLaunch(item, event.target.value, $('.launch-target', row).value);
      if (event.target.classList.contains('extra')) {
        try {
          const extra = JSON.parse(event.target.value || '{}');
          const core = new Set(['id', 'name', titles[kind][2], 'launch', 'process', 'auto']);
          Object.keys(item).forEach(key => { if (!core.has(key)) delete item[key]; });
          Object.entries(extra).forEach(([key, value]) => { if (!core.has(key)) item[key] = value; });
          event.target.setCustomValidity('');
        } catch (_) {
          event.target.setCustomValidity('JSON invalide');
          toast('Corrige les autres options : leur format est invalide.', true);
        }
      }
      changed();
    });
  }

  function wireTags(containerId, key) {
    const box = $('#' + containerId);
    box.addEventListener('click', event => {
      if (event.target.matches('.tag button')) { state.settings[key].splice(+event.target.dataset.i, 1); changed(); tagEditor(containerId, key); return; }
      if (event.target.matches('.tag-editor button')) {
        const input = $('.tag-editor input', box);
        const value = input.value.trim();
        if (value) { state.settings[key].push(value); changed(); tagEditor(containerId, key); }
      }
    });
    box.addEventListener('keydown', event => { if (event.key === 'Enter' && event.target.matches('input')) { event.preventDefault(); $('.tag-editor button', box).click(); } });
  }
  wireTags('bootBlock', 'boot_block');
  wireTags('pausePlaying', 'pause_if_playing');
  $('#musicEditor').addEventListener('input', event => {
    if (event.target.id === 'musicName') state.music.name = event.target.value;
    if (event.target.id === 'musicProcess') state.music.process = event.target.value;
    if (event.target.id === 'musicTarget') {
      const value = event.target.value;
      const type = /^https?:\/\//i.test(value) ? 'url' : /^[a-z][\w+.-]*:/i.test(value) ? 'uri' : 'exe';
      setLaunch(state.music, type, value);
    }
    changed();
  });

  async function save() {
    document.querySelectorAll('.extra').forEach(area => area.dispatchEvent(new Event('change', {bubbles: true})));
    if (document.querySelector(':invalid')) return toast('Corrige les options avancées invalides.', true);
    const button = $('.sk-btn--primary', savebar.element);
    button.disabled = true;
    button.textContent = 'Enregistrement…';
    const result = await api().save(state);
    button.disabled = false;
    button.textContent = 'Enregistrer';
    if (result.ok) { clean(); toast('Tes réglages sont enregistrés. Ils seront visibles au prochain démarrage.'); }
    else toast(result.error || "Impossible d’enregistrer.", true);
  }
  function cancel() {
    state = JSON.parse(original);
    renderAll(); clean(); toast('Tes modifications sont annulées.', true);
  }

  addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });

  async function start() {
    try { state = await api().load(); original = JSON.stringify(state); renderAll(); }
    catch (error) { toast('Impossible de lire config.json : ' + error, true); }
  }

  const windowNode = $('#settingsWindow');
  windowNode.insertBefore(Sakura.titlebar({title: 'Réglages du Launcher'}), windowNode.firstChild);
  Sakura.init();
  Sakura.tabs($('#tabs'));
  Sakura.onThemeChange(theme => document.querySelectorAll('[data-sk-brush]').forEach(row => row.classList.toggle('sk-neon', theme === 'night')));
  savebar = Sakura.savebar({onSave: save, onCancel: cancel, message: 'Tu as des changements à enregistrer'});
  document.body.appendChild(savebar.element);  // hors de .sk-window, sinon le kit la rend « relative » et elle sort de l'écran
  if (window.pywebview) start(); else addEventListener('pywebviewready', start, {once: true});
})();
