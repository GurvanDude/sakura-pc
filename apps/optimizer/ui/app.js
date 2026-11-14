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

  function createDiagnosisFinding() {
    const card = make('article', 'sk-card diagnosis-finding');
    const head = make('div', 'diagnosis-finding-head');
    head.append(make('h3'), make('span', 'sk-stat-state'));
    const evidence = make('div', 'diagnosis-evidence');
    const advice = make('ul', 'diagnosis-advice');
    card.append(head, make('p', 'diagnosis-explanation'), evidence, advice);
    return card;
  }

  function renderDiagnosis(result) {
    const verdict = result.verdict || {};
    const presentation = verdicts[verdict.mood] || verdicts.ok;
    $('#diagnosis-mood').textContent = presentation.emoji;
    $('#diagnosis-tag').textContent = result.enough_data
      ? 'ANALYSE TERMINÉE' : 'ANALYSE MOINS SÛRE';
    $('#diagnosis-title').textContent = verdict.title || 'Analyse terminée';
    $('#diagnosis-text').textContent = verdict.text || '';
    const minutes = Number(result.minutes) || 5;
    const minuteText = minutes.toLocaleString('fr-FR', { maximumFractionDigits: 1 });
    $('#diagnosis-period').textContent = 'Analysé : les ' + minuteText + ' dernières minutes'
      + (result.app ? ', pendant ' + result.app : '') + '.';

    const findings = Array.isArray(result.findings) ? result.findings : [];
    const box = $('#diagnosis-findings');
    if (box.children.length !== findings.length) {
      box.replaceChildren(...findings.map(createDiagnosisFinding));
    }
    [...box.children].forEach((card, index) => {
      const finding = findings[index];
      card.querySelector('h3').textContent = finding.title;
      const state = card.querySelector('.sk-stat-state');
      state.textContent = finding.severity === 'grave' ? 'Important'
        : (finding.severity === 'attention' ? 'Attention' : 'Information');
      state.className = 'sk-stat-state ' + (finding.severity === 'info' ? 'is-ok' : 'is-warn');
      card.querySelector('.diagnosis-explanation').textContent = finding.explanation;
      const evidence = card.querySelector('.diagnosis-evidence');
      evidence.replaceChildren(...finding.evidence.map(item => {
        const row = make('div', 'diagnosis-evidence-row');
        const label = make('span');
        const value = make('strong');
        label.textContent = item.label + ' ·';
        value.textContent = item.value;
        row.append(label, value);
        return row;
      }));
      const advice = card.querySelector('.diagnosis-advice');
      advice.replaceChildren(...finding.advice.map(text => {
        const item = make('li');
        item.textContent = text;
        return item;
      }));
    });
    $('#diagnosis-loading').hidden = true;
    $('#diagnosis-result').hidden = false;
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

  const HISTORY_PERIODS = new Set(['15m', '1h', '6h', '24h', '7j']);
  const HISTORY_SECONDS = { '15m': 900, '1h': 3600, '6h': 21600, '24h': 86400, '7j': 604800 };
  let historyPeriod = '1h';
  let diagnosisMinutes = 5;

  const chartConfigs = {
    cpu: { field: 'cpu', kind: 'cpu', label: 'Processeur', unit: '%', max: 100 },
    gpu: { field: 'gpu', kind: 'gpu', label: 'Carte graphique', unit: '%', max: 100 },
    ram: { field: 'ram', kind: 'ram', label: 'Mémoire', unit: '%', max: 100 },
    cpuTemp: { field: 'cpu_temp', kind: 'cpu', label: 'Température du processeur', unit: '°C', temperature: true },
    gpuTemp: { field: 'gpu_temp', kind: 'gpu', label: 'Température de la carte graphique', unit: '°C', temperature: true }
  };

  const historyCharts = Object.fromEntries(Object.entries(chartConfigs).map(([name, config]) => {
    const options = {
      values: [], kind: config.kind, label: config.label, unit: config.unit, height: 104
    };
    if (config.max) options.max = config.max;
    return [name, Sakura.chart($('#history-' + name.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase())), options)];
  }));

  function finite(value) {
    const parsed = Number(value);
    return value !== null && value !== undefined && value !== '' && Number.isFinite(parsed) ? parsed : null;
  }

  function historyTime(timestamp) {
    return new Date(timestamp * 1000).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  }

  function historyRange(series) {
    const times = series.map(point => Number(point.t)).filter(Number.isFinite).sort((a, b) => a - b);
    if (!times.length) return '';
    let text = 'De ' + historyTime(times[0]) + ' à ' + historyTime(times[times.length - 1]);
    const differences = times.slice(1).map((time, index) => time - times[index]).filter(gap => gap > 0);
    if (!differences.length) return text;
    const sorted = [...differences].sort((a, b) => a - b);
    const measuredStep = sorted[Math.floor(sorted.length / 2)];
    const usualStep = Math.min(measuredStep, HISTORY_SECONDS[historyPeriod] / 120);
    const gaps = times.slice(1).map((time, index) => [times[index], time]).filter(([start, end]) => end - start > usualStep * 3);
    if (gaps.length > 2) return text + ' · quelques trous dans les mesures';
    if (gaps.length) {
      text += gaps.map(([start, end]) => ' · pas de mesures entre ' + historyTime(start) + ' et ' + historyTime(end) + ' (PC éteint ou rien n\'enregistrait)').join('');
    }
    return text;
  }

  function renderHistory(payload) {
    const series = Array.isArray(payload.series) ? payload.series : [];
    const view = payload.view && typeof payload.view === 'object' ? payload.view : {};
    $('#history-sentence').textContent = view.sentence || 'Aucun souvenir pour cette période.';
    const facts = Array.isArray(view.facts) ? view.facts : [];
    const factsBox = $('#history-facts');
    if (factsBox.children.length !== facts.length) {
      factsBox.replaceChildren(...facts.map(() => {
        const row = make('div', 'history-fact');
        row.append(make('span', 'history-fact-label'), make('strong'), make('small'));
        return row;
      }));
    }
    [...factsBox.children].forEach((row, index) => {
      row.querySelector('.history-fact-label').textContent = facts[index].label;
      row.querySelector('strong').textContent = facts[index].value;
      row.querySelector('small').textContent = facts[index].hint;
    });
    Object.entries(chartConfigs).forEach(([name, config]) => {
      const values = series.map(point => finite(point[config.field])).filter(value => value !== null);
      const host = $('#history-' + name.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase()));
      if (config.temperature) host.hidden = values.length === 0;
      historyCharts[name].update(values);
    });
    const range = $('#history-range');
    range.textContent = historyRange(series);
    range.hidden = !range.textContent;
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
      try { historyPeriod = await bridge.get_history_period(); } catch (_) { /* période par défaut */ }
    }
    if (!HISTORY_PERIODS.has(historyPeriod)) historyPeriod = '1h';
    [...$('#history-periods').children].forEach(button => {
      button.classList.toggle('is-active', button.dataset.period === historyPeriod);
    });
    const read = bridge
      ? () => bridge.get_view()
      : () => fetch('/api/view', { cache: 'no-store' }).then(response => {
          if (!response.ok) throw new Error('Aperçu indisponible');
          return response.json();
        });
    const readHistory = bridge
      ? () => bridge.get_history(historyPeriod)
      : () => fetch('/api/history?period=' + encodeURIComponent(historyPeriod), { cache: 'no-store' }).then(response => {
          if (!response.ok) throw new Error('Historique indisponible');
          return response.json();
        });
    const readDiagnosis = () => bridge
      ? bridge.diagnose(diagnosisMinutes)
      : fetch('/api/diagnose?minutes=' + encodeURIComponent(diagnosisMinutes), { cache: 'no-store' })
        .then(response => {
          if (!response.ok) throw new Error('Diagnostic indisponible');
          return response.json();
        });
    const refresh = async () => {
      try { render(await read()); } catch (_) { /* nouvel essai au prochain cycle */ }
    };
    const refreshHistory = async () => {
      try { renderHistory(await readHistory()); } catch (_) { /* nouvel essai au prochain cycle */ }
    };
    refresh();
    refreshHistory();
    window.setInterval(refresh, 1500);
    window.setInterval(refreshHistory, 10000);
    $('#history-periods').addEventListener('click', async event => {
      const period = event.target.dataset ? event.target.dataset.period : null;
      if (!HISTORY_PERIODS.has(period)) return;
      historyPeriod = period;
      [...$('#history-periods').children].forEach(button => {
        button.classList.toggle('is-active', button.dataset.period === historyPeriod);
      });
      if (bridge) {
        try { await bridge.set_history_period(historyPeriod); } catch (_) { /* affichage quand même */ }
      }
      refreshHistory();
    });
    $('#diagnosis-periods').addEventListener('click', event => {
      const minutes = Number(event.target.dataset ? event.target.dataset.minutes : NaN);
      if (![2, 5, 15].includes(minutes)) return;
      diagnosisMinutes = minutes;
      [...$('#diagnosis-periods').children].forEach(button => {
        button.classList.toggle('is-active', Number(button.dataset.minutes) === diagnosisMinutes);
      });
    });
    $('#run-diagnosis').addEventListener('click', async () => {
      const panel = $('#diagnosis');
      panel.hidden = false;
      $('#diagnosis-result').hidden = true;
      $('#diagnosis-loading').textContent = "J'analyse les dernières minutes…";
      $('#diagnosis-loading').hidden = false;
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      try {
        renderDiagnosis(await readDiagnosis());
      } catch (_) {
        $('#diagnosis-loading').textContent = "Je n'arrive pas à analyser les dernières minutes pour le moment.";
      }
    });
  }

  $('#close-diagnosis').addEventListener('click', () => {
    $('#diagnosis').hidden = true;
    $('#diagnosis-result').hidden = true;
    $('#diagnosis-loading').hidden = true;
    $('#diagnosis-loading').textContent = "J'analyse les dernières minutes…";
  });

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
