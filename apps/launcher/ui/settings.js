(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const api = () => window.pywebview?.api;
  let state = null;
  let original = '';
  let dirty = false;

  const titles = {
    games: ['Jeux', 'Gérez les jeux affichés sur l’écran principal.', 'cover'],
    apps: ['Applis', 'Gérez les applications proposées sur le second écran.', 'icon'],
    classic: ['Classiques', 'Choisissez les programmes lancés par le mode classique.', 'icon'],
  };

  function toast(message, error = false) {
    const box = $('#toast');
    box.textContent = message; box.className = error ? 'show error' : 'show';
    clearTimeout(toast.timer); toast.timer = setTimeout(() => box.className = '', 3200);
  }
  function changed() { dirty = true; $('#savebar').classList.add('show'); }
  function clean() { dirty = false; original = JSON.stringify(state); $('#savebar').classList.remove('show'); }
  function imageUrl(path) { return path ? path.replaceAll('\\', '/') : ''; }
  function launchParts(item) {
    const launch = item.launch || {};
    const type = ['exe','url','uri','file'].find(k => launch[k] != null) || 'exe';
    return [type, launch[type] || ''];
  }
  function setLaunch(item, type, value) {
    const old = item.launch || {};
    const next = {...old}; ['exe','url','uri','file'].forEach(k => delete next[k]);
    next[type] = value; item.launch = next;
  }

  function renderHours() {
    for (const id of ['dayStart','dayEnd']) {
      const sel = $('#' + id);
      sel.innerHTML = Array.from({length:24}, (_, h) => `<option value="${h}">${h} h</option>`).join('');
    }
    $('#dayStart').value = state.settings.day_start;
    $('#dayEnd').value = state.settings.day_end;
    updateSentence();
  }
  function updateSentence() {
    const a = +$('#dayStart').value, b = +$('#dayEnd').value;
    state.settings.day_start = a; state.settings.day_end = b;
    $('#hoursSentence').textContent = `Le jour va de ${a} h à ${b} h, la nuit le reste du temps.`;
  }
  function renderBackgrounds() {
    const labels = {day:'Jour', night:'Nuit', main:'Écran principal', side:'Écran secondaire'};
    $('#backgrounds').innerHTML = ['day','night'].flatMap(theme => ['main','side'].map(screen => {
      const name = state.settings.backgrounds[theme][screen];
      return `<article class="card background-card" data-theme="${theme}" data-screen="${screen}">
        <img src="assets/bg/${esc(name)}.jpg" alt="Aperçu du fond">
        <div><h3>${labels[theme]} · ${labels[screen]}</h3><p>${esc(name)}</p><button class="secondary change-bg">Changer</button></div>
      </article>`;
    })).join('');
  }

  function itemHtml(item, kind, index, total) {
    const imageKey = titles[kind][2], path = item[imageKey] || '';
    const [launchType, target] = launchParts(item);
    const extra = {...item}; ['id','name',imageKey,'launch','process','auto'].forEach(k => delete extra[k]);
    const thumb = path ? `<img class="thumb ${imageKey === 'icon' ? 'icon' : ''}" src="${esc(imageUrl(path))}" alt="">` : `<div class="thumb thumb-fallback">${esc((item.name || '?')[0])}</div>`;
    return `<article class="item" data-index="${index}">
      ${thumb}
      <div class="item-main">
        <div class="name-row"><input class="item-name" value="${esc(item.name)}" aria-label="Nom"></div>
        <details><summary>Avancé</summary><div class="advanced">
          <label>Type <select class="launch-type">${['exe','url','uri','file'].map(x => `<option value="${x}" ${x===launchType?'selected':''}>${x}</option>`).join('')}</select></label>
          <label>Cible <input class="launch-target" value="${esc(target)}"></label>
          <label>Processus <input class="process" value="${esc(item.process || '')}" placeholder="exemple.exe"></label>
          <label>Ajout auto <input class="auto" value="${esc(item.auto || '')}" placeholder="vide"></label>
          <label>Autres options (JSON) <textarea class="extra">${esc(JSON.stringify(extra, null, 2))}</textarea></label>
        </div></details>
      </div>
      <div class="actions">
        <button class="small change-image">Image</button>
        <button class="small move up" title="Monter" ${index===0?'disabled':''}>↑</button>
        <button class="small move down" title="Descendre" ${index===total-1?'disabled':''}>↓</button>
        <button class="danger remove">Supprimer</button>
      </div>
    </article>`;
  }
  function renderList(kind) {
    const [title, subtitle] = titles[kind];
    const panel = $('#' + kind), list = state[kind];
    panel.innerHTML = `<div class="heading"><div><h2>${title}</h2><p>${subtitle}</p></div></div>
      <div class="add-area"><button class="primary add-file">+ Choisir un programme .exe</button><button class="secondary add-link">+ Coller une adresse</button>
        <div class="link-form"><input class="new-name" placeholder="Nom affiché"><input class="new-address" placeholder="https://… ou steam://…"><button class="primary confirm-link">Ajouter</button></div>
      </div><div class="item-list">${list.length ? list.map((it,i) => itemHtml(it,kind,i,list.length)).join('') : '<div class="empty">Aucun élément pour le moment.</div>'}</div>`;
  }

  function tagEditor(id, key) {
    const values = state.settings[key];
    $('#' + id).innerHTML = `<div class="tag-editor"><input placeholder="nom-du-programme.exe"><button class="secondary">Ajouter</button></div><div class="tags">${values.map((v,i) => `<span class="tag">${esc(v)}<button data-i="${i}" title="Retirer">×</button></span>`).join('')}</div>`;
  }
  function renderStartup() {
    tagEditor('bootBlock','boot_block'); tagEditor('pausePlaying','pause_if_playing');
    const music = state.music || (state.music = {}), [type,target] = launchParts(music);
    $('#musicEditor').innerHTML = `<div class="music-fields"><label>Nom<input id="musicName" value="${esc(music.name || '')}"></label><label>Programme ou adresse<input id="musicTarget" value="${esc(target)}"></label><label>Processus<input id="musicProcess" value="${esc(music.process || '')}" placeholder="musique.exe"></label></div><input type="hidden" id="musicType" value="${type}">`;
  }
  function renderAll() { renderHours(); renderBackgrounds(); Object.keys(titles).forEach(renderList); renderStartup(); }

  async function chooseImage(kind, item) {
    const imageKind = kind === 'games' ? 'cover' : kind === 'background' ? 'background' : 'icon';
    const result = await api().choose_image(imageKind);
    if (!result) return;
    if (result.error) return toast(result.error, true);
    if (kind === 'background') state.settings.backgrounds[item.theme][item.screen] = result.value;
    else item[titles[kind][2]] = result.value;
    changed(); kind === 'background' ? renderBackgrounds() : renderList(kind);
  }

  $('#tabs').addEventListener('click', e => {
    const button = e.target.closest('button[data-tab]'); if (!button) return;
    $('#tabs .active')?.classList.remove('active'); button.classList.add('active');
    $('.panel.active')?.classList.remove('active'); $('#' + button.dataset.tab).classList.add('active');
  });
  $('#dayStart').addEventListener('change', () => { updateSentence(); changed(); });
  $('#dayEnd').addEventListener('change', () => { updateSentence(); changed(); });
  $('#backgrounds').addEventListener('click', e => {
    const card = e.target.closest('.background-card'); if (e.target.closest('.change-bg') && card) chooseImage('background', card.dataset);
  });

  for (const kind of Object.keys(titles)) {
    const panel = $('#' + kind);
    panel.addEventListener('click', async e => {
      if (e.target.closest('.add-link')) return $('.link-form',panel).classList.toggle('open');
      if (e.target.closest('.add-file')) {
        const result = await api().choose_program(kind, state[kind].map(x => x.id));
        if (!result) return; if (result.error) return toast(result.error,true);
        state[kind].push(result); changed(); renderList(kind); return;
      }
      if (e.target.closest('.confirm-link')) {
        const result = await api().make_link($('.new-name',panel).value, $('.new-address',panel).value, state[kind].map(x => x.id));
        if (result.error) return toast(result.error,true);
        state[kind].push(result); changed(); renderList(kind); return;
      }
      const row = e.target.closest('.item'); if (!row) return;
      const index = +row.dataset.index, item = state[kind][index];
      if (e.target.closest('.change-image')) return chooseImage(kind,item);
      if (e.target.closest('.remove')) {
        if (confirm(`Supprimer « ${item.name} » de cette liste ?`)) { state[kind].splice(index,1); changed(); renderList(kind); }
        return;
      }
      const delta = e.target.closest('.up') ? -1 : e.target.closest('.down') ? 1 : 0;
      if (delta && state[kind][index + delta]) { [state[kind][index],state[kind][index+delta]]=[state[kind][index+delta],state[kind][index]]; changed(); renderList(kind); }
    });
    panel.addEventListener('input', e => {
      const row=e.target.closest('.item'); if(!row)return; const item=state[kind][+row.dataset.index];
      if(e.target.classList.contains('item-name')) item.name=e.target.value;
      else if(e.target.classList.contains('process')) item.process=e.target.value;
      else if(e.target.classList.contains('auto')) { if(e.target.value)item.auto=e.target.value;else delete item.auto; }
      else if(e.target.classList.contains('launch-target')) setLaunch(item,$('.launch-type',row).value,e.target.value);
      changed();
    });
    panel.addEventListener('change', e => {
      const row=e.target.closest('.item'); if(!row)return; const item=state[kind][+row.dataset.index];
      if(e.target.classList.contains('launch-type')) setLaunch(item,e.target.value,$('.launch-target',row).value);
      if(e.target.classList.contains('extra')) { try {
        const extra=JSON.parse(e.target.value||'{}');
        const core=new Set(['id','name',titles[kind][2],'launch','process','auto']);
        Object.keys(item).forEach(key=>{if(!core.has(key))delete item[key];});
        Object.entries(extra).forEach(([key,value])=>{if(!core.has(key))item[key]=value;});
        e.target.setCustomValidity('');
      } catch { e.target.setCustomValidity('JSON invalide'); toast('Les autres options contiennent du JSON invalide.',true); } }
      changed();
    });
  }

  function wireTags(containerId,key) {
    const box=$('#'+containerId);
    box.addEventListener('click',e=>{
      if(e.target.matches('.tag button')) { state.settings[key].splice(+e.target.dataset.i,1);changed();tagEditor(containerId,key);return; }
      if(e.target.matches('.tag-editor button')) { const input=$('.tag-editor input',box),value=input.value.trim();if(value){state.settings[key].push(value);changed();tagEditor(containerId,key);} }
    });
    box.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('input')){e.preventDefault();$('.tag-editor button',box).click();}});
  }
  wireTags('bootBlock','boot_block'); wireTags('pausePlaying','pause_if_playing');
  $('#musicEditor').addEventListener('input',e=>{
    if(e.target.id==='musicName')state.music.name=e.target.value;
    if(e.target.id==='musicProcess')state.music.process=e.target.value;
    if(e.target.id==='musicTarget'){const v=e.target.value;const type=/^https?:\/\//i.test(v)?'url':/^[a-z][\w+.-]*:/i.test(v)?'uri':'exe';setLaunch(state.music,type,v);}
    changed();
  });

  $('#cancelBtn').addEventListener('click',()=>{state=JSON.parse(original);renderAll();clean();toast('Modifications annulées.');});
  $('#saveBtn').addEventListener('click',async()=>{
    document.querySelectorAll('.extra').forEach(area=>area.dispatchEvent(new Event('change',{bubbles:true})));
    if(document.querySelector(':invalid'))return toast('Corrigez les options avancées invalides.',true);
    const button=$('#saveBtn');button.disabled=true;button.textContent='Enregistrement…';
    const result=await api().save(state);button.disabled=false;button.textContent='Enregistrer';
    if(result.ok){clean();toast('Réglages enregistrés. Ils seront visibles au prochain démarrage.');}else toast(result.error||"Impossible d'enregistrer.",true);
  });
  addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});

  async function start() {
    try { state=await api().load(); original=JSON.stringify(state); renderAll(); }
    catch(error) { toast('Impossible de lire config.json : '+error,true); }
  }
  if(window.pywebview) start(); else addEventListener('pywebviewready',start,{once:true});
})();
