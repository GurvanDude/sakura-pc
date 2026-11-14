(function () {
  'use strict';

  const $ = selector => document.querySelector(selector);
  const clamp = value => Math.max(0, Math.min(100, Number(value) || 0));

  function make(tag, className = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    return element;
  }

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  const shell = $('#optimizer-window');
  shell.insertBefore(Sakura.titlebar({
    title: 'Sakura Optimizer',
    onMinimize: () => { if (api()) api().minimize(); },
    onMaximize: () => { if (api()) api().toggle_maximize(); },
    onClose: () => { if (api()) api().close(); }
  }), shell.firstChild);
  Sakura.details($('#details-button'), $('#details'));
  Sakura.init();

  const verdicts = {
    ok: { emoji: '😊', tag: '調子いい · TOUT VA BIEN' },
    busy: { emoji: '💪', tag: 'がんばってる · ÇA TRAVAILLE' },
    warn: { emoji: '😟', tag: 'ちょっと注意 · ATTENTION' }
  };

  function renderVerdict(verdict) {
    const presentation = verdicts[verdict.mood] || verdicts.ok;
    $('#verdict-mood').textContent = presentation.emoji;
    $('#verdict-tag').textContent = presentation.tag;
    $('#verdict-title').textContent = verdict.title;
    $('#verdict-text').textContent = verdict.text;
  }

  function createFigure() {
    const row = make('div', 'stat-figure');
    const line = make('div', 'stat-figure-line');
    line.append(make('span', 'stat-figure-label'), make('span', 'stat-figure-value'));
    row.append(line, make('small', 'stat-figure-hint'));
    return row;
  }

  function renderStats(cards) {
    cards.forEach(card => {
      const element = document.querySelector('[data-card="' + card.id + '"]');
      if (!element) return;
      element.querySelector('.sk-stat-label').textContent = card.title;
      const value = card.level === 'inconnu'
        ? '—'
        : Number(card.percent).toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' %';
      element.querySelector('.sk-stat-value').textContent = value;
      const state = element.querySelector('.sk-stat-state');
      state.textContent = card.word;
      state.className = 'sk-stat-state ' + (card.level === 'fond' ? 'is-warn' : 'is-ok');

      const figures = element.querySelector('.stat-figures');
      const structure = card.figures.map(figure => figure.label).join('|');
      if (figures.dataset.structure !== structure) {
        figures.dataset.structure = structure;
        figures.replaceChildren(...card.figures.map(createFigure));
      }
      [...figures.children].forEach((row, index) => {
        const figure = card.figures[index];
        row.querySelector('.stat-figure-label').textContent = figure.label + ' ·';
        row.querySelector('.stat-figure-value').textContent = figure.value;
        const hint = row.querySelector('.stat-figure-hint');
        hint.textContent = figure.hint;
        hint.hidden = !figure.hint;
      });
    });
  }

  function createAppRow() {
    const row = make('article', 'sk-row');
    const main = make('div', 'sk-row-main');
    const meters = make('div', 'app-meters');
    meters.append(make('div', 'sk-meter sk-meter--cpu'), make('div', 'sk-meter sk-meter--ram'));
    main.append(make('div', 'sk-row-title'), make('div', 'sk-row-sub'), meters);
    row.append(make('div', 'sk-row-icon'), main, make('div', 'sk-row-end'));
    return row;
  }

  function renderApps(apps) {
    const box = $('#apps');
    if (box.dataset.structure !== String(apps.length)) {
      box.dataset.structure = String(apps.length);
      box.replaceChildren(...(apps.length ? apps.map(createAppRow) : [make('p', 'sk-sub empty')]));
    }
    if (!apps.length) {
      box.querySelector('.empty').textContent = 'Aucun programme gourmand en ce moment.';
      return;
    }
    [...box.children].forEach((row, index) => {
      const app = apps[index];
      row.querySelector('.sk-row-icon').textContent =
        app.name === 'Windows' ? '⚙' : (Array.from(app.name.trim())[0] || '?').toUpperCase();
      row.querySelector('.sk-row-title').textContent = app.name;
      row.querySelector('.sk-row-sub').textContent = app.cpu_text + ' · ' + app.ram_text;
      row.querySelector('.sk-meter--cpu').style.setProperty('--sk-value', clamp(app.cpu_percent) + '%');
      row.querySelector('.sk-meter--ram').style.setProperty('--sk-value', clamp(app.ram_percent) + '%');
      row.querySelector('.sk-row-end').textContent = app.what;
    });
  }

  function createTip() {
    const tip = make('aside', 'sk-tip');
    const body = make('div', 'sk-tip-body');
    body.append(make('div', 'sk-tip-title'), make('p'));
    tip.append(body);
    return tip;
  }

  function renderTips(tips) {
    const section = $('#tips-section');
    const box = $('#tips');
    section.hidden = !tips.length;
    if (box.dataset.structure !== String(tips.length)) {
      box.dataset.structure = String(tips.length);
      box.replaceChildren(...tips.map(createTip));
    }
    [...box.children].forEach((tip, index) => {
      tip.querySelector('.sk-tip-title').textContent = tips[index].icon + ' Conseil';
      tip.querySelector('p').textContent = tips[index].text;
    });
  }

  function number(value, unit) {
    if (value === null || value === undefined || value === '') return '—';
    const parsed = Number(value);
    return Number.isFinite(parsed)
      ? parsed.toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' ' + unit
      : '—';
  }

  function detailData(view, status) {
    const cpu = status.cpu && typeof status.cpu === 'object' ? status.cpu : {};
    const disk = status.disk && typeof status.disk === 'object' ? status.disk : {};
    const cores = Array.isArray(cpu.per_core) ? cpu.per_core : [];
    const physical = disk.per_disk && typeof disk.per_disk === 'object'
      ? Object.entries(disk.per_disk) : [];
    const notes = [];
    if (status.temps && status.temps.reason) notes.push(status.temps.reason);
    if (status.errors && typeof status.errors === 'object') {
      Object.entries(status.errors).forEach(([key, value]) => notes.push(key + ' : ' + value));
    }
    return { cpu, cores, physical, notes, cards: view.cards };
  }

  function rebuildDetails(box, sensorBox, data) {
    const rows = data.cards.map(() => make('div', 'detail-line card-detail'));
    rows.push(make('div', 'detail-line frequency-detail'));
    if (data.cores.length) {
      const section = make('div', 'detail-section cores-detail');
      const title = make('b');
      title.textContent = 'Charge par cœur';
      const grid = make('div', 'core-grid');
      data.cores.forEach(() => {
        const row = make('div', 'core-row');
        const meter = make('span', 'sk-meter sk-meter--cpu core-meter');
        row.append(make('span', 'core-name'), meter, make('span', 'core-value'));
        grid.append(row);
      });
      section.append(title, grid);
      rows.push(section);
    }
    data.physical.forEach(() => rows.push(make('div', 'detail-line disk-detail')));
    box.replaceChildren(...rows);
    sensorBox.replaceChildren(...data.notes.map(() => make('div', 'detail-line note-detail')));
  }

  function renderDetails(view, status) {
    const box = $('#card-details');
    const sensorBox = $('#sensor-details');
    const data = detailData(view, status || {});
    const structure = [
      data.cards.length, data.cores.length,
      data.physical.map(([name]) => name).join(','), data.notes.length
    ].join('|');
    if (box.dataset.structure !== structure) {
      box.dataset.structure = structure;
      rebuildDetails(box, sensorBox, data);
    }
    [...box.querySelectorAll('.card-detail')].forEach((row, index) => {
      const card = data.cards[index];
      row.textContent = card.title + ' · ' + card.detail;
    });
    box.querySelector('.frequency-detail').textContent =
      'Fréquence du processeur · ' + number(data.cpu.freq_mhz, 'MHz');
    [...box.querySelectorAll('.core-row')].forEach((row, index) => {
      const rawValue = data.cores[index];
      const value = rawValue === null || rawValue === undefined || rawValue === ''
        ? NaN : Number(rawValue);
      const known = Number.isFinite(value);
      row.querySelector('.core-name').textContent = 'Cœur ' + (index + 1);
      row.querySelector('.core-value').textContent = known
        ? value.toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' %' : '—';
      row.querySelector('.core-meter').style.setProperty('--sk-value', (known ? clamp(value) : 0) + '%');
    });
    [...box.querySelectorAll('.disk-detail')].forEach((row, index) => {
      const [name, rawValues] = data.physical[index];
      const values = rawValues && typeof rawValues === 'object' ? rawValues : {};
      row.textContent = name + ' · lecture ' + number(values.read_mb_s, 'Mo/s')
        + ' · écriture ' + number(values.write_mb_s, 'Mo/s');
    });
    [...sensorBox.children].forEach((row, index) => { row.textContent = data.notes[index]; });
  }

  function render(payload) {
    const view = payload.view;
    renderVerdict(view.verdict);
    renderStats(view.cards);
    renderApps(view.apps);
    renderTips(view.tips);
    renderDetails(view, payload.status || {});
  }

  async function waitForApi() {
    if (api()) return api();
    return new Promise(resolve => {
      let done = false;
      const finish = value => {
        if (done) return;
        done = true;
        resolve(value);
      };
      window.addEventListener('pywebviewready', () => finish(api()), { once: true });
      window.setTimeout(() => finish(api()), 1000);
    });
  }

  async function start() {
    const bridge = await waitForApi();
    if (bridge) {
      try { Sakura.setTheme(await bridge.get_theme()); } catch (_) { /* thème du kit conservé */ }
      Sakura.onThemeChange(theme => { bridge.set_theme(theme); });
    }
    const read = bridge
      ? () => bridge.get_view()
      : () => fetch('/api/view', { cache: 'no-store' }).then(response => {
          if (!response.ok) throw new Error('Aperçu indisponible');
          return response.json();
        });
    const refresh = async () => {
      try { render(await read()); } catch (_) { /* nouvel essai au prochain cycle */ }
    };
    refresh();
    window.setInterval(refresh, 1500);
  }

  $('#free-space').addEventListener('click', async () => {
    if (!api()) return;
    try {
      await api().free_space();
      Sakura.toast("J'ouvre les réglages de stockage de Windows.");
    } catch (_) {
      Sakura.toast("Je n'arrive pas à ouvrir les réglages de stockage.", { kind: 'warn' });
    }
  });

  start();
}());
