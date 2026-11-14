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

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const HISTORY_PERIODS = new Set(['15m', '1h', '6h', '24h', '7j']);
  const HISTORY_SECONDS = { '15m': 900, '1h': 3600, '6h': 21600, '24h': 86400, '7j': 604800 };
  let historyPeriod = '1h';
  let diagnosisMinutes = 5;

  const chartConfigs = {
    activity: {
      max: 100,
      lines: [
        { field: 'cpu', label: 'processeur', unit: '%', color: 'cpu' },
        { field: 'gpu', label: 'carte graphique', unit: '%', color: 'gpu' }
      ],
      tooltip: [
        { field: 'cpu', label: 'processeur', unit: '%' },
        { field: 'cpu_temp', label: '', unit: '°C' },
        { field: 'gpu', label: 'carte graphique', unit: '%' }
      ]
    },
    temperature: {
      max: 100,
      lines: [
        { field: 'cpu_temp', label: 'processeur', unit: '°C', color: 'cpu' },
        { field: 'gpu_temp', label: 'carte graphique', unit: '°C', color: 'gpu' }
      ]
    },
    memory: {
      max: 100,
      lines: [{ field: 'ram', label: 'mémoire', unit: '%', color: 'ram' }]
    }
  };

  function svgElement(tag, attributes = {}) {
    const element = document.createElementNS(SVG_NS, tag);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
    return element;
  }

  function finite(value) {
    const parsed = Number(value);
    return value !== null && value !== undefined && Number.isFinite(parsed) ? parsed : null;
  }

  function historyTime(timestamp) {
    return new Date(timestamp * 1000).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  }

  function linePath(points) {
    return points.map((point, index) => (index ? 'L' : 'M') + point[0].toFixed(1) + ',' + point[1].toFixed(1)).join(' ');
  }

  function chartSegments(series, field, x, y, gapLimit) {
    const result = [];
    let current = [];
    series.forEach((point, index) => {
      const value = finite(point[field]);
      const previous = index ? series[index - 1] : null;
      const gap = previous ? Number(point.t) - Number(previous.t) : 0;
      if (value === null || (current.length && gap > gapLimit)) {
        if (current.length) result.push(current);
        current = [];
      }
      if (value !== null) current.push([x(Number(point.t)), y(value)]);
    });
    if (current.length) result.push(current);
    return result;
  }

  function tooltipText(point, fields) {
    const pieces = fields.map(field => {
      const value = finite(point[field.field]);
      if (value === null) return null;
      const formatted = value.toLocaleString('fr-FR', { maximumFractionDigits: 1 });
      return (field.label ? field.label + ' ' : '') + formatted + ' ' + field.unit;
    }).filter(Boolean);
    return historyTime(point.t) + (pieces.length ? ' · ' + pieces.join(' · ') : '');
  }

  function prepareChartHover(card) {
    const svg = card.querySelector('svg');
    const tooltip = card.querySelector('.chart-tooltip');
    svg.addEventListener('pointermove', event => {
      const data = card._chartData;
      if (!data || !data.series.length) return;
      const bounds = svg.getBoundingClientRect();
      const svgX = (event.clientX - bounds.left) / bounds.width * 620;
      const ratio = Math.max(0, Math.min(1, (svgX - 36) / (608 - 36)));
      const wanted = data.first + ratio * data.span;
      const point = data.series.reduce((closest, candidate) =>
        Math.abs(Number(candidate.t) - wanted) < Math.abs(Number(closest.t) - wanted) ? candidate : closest
      , data.series[0]);
      tooltip.textContent = tooltipText(point, data.fields);
      tooltip.hidden = false;
      tooltip.style.left = Math.max(6, Math.min(bounds.width - tooltip.offsetWidth - 6, event.clientX - bounds.left + 9)) + 'px';
      tooltip.style.top = Math.max(4, event.clientY - bounds.top - 36) + 'px';
    });
    svg.addEventListener('pointerleave', () => { tooltip.hidden = true; });
  }

  function renderChart(card, config, series) {
    const svg = card.querySelector('svg');
    const validSeries = series.filter(point => Number.isFinite(Number(point.t)));
    const times = validSeries.map(point => Number(point.t));
    const last = times.length ? Math.max(...times) : Date.now() / 1000;
    const first = times.length ? Math.min(...times) : last - HISTORY_SECONDS[historyPeriod];
    const span = Math.max(1, last - first);
    const left = 36, right = 608, top = 10, bottom = 154;
    const x = value => left + (value - first) / span * (right - left);
    const y = value => bottom - Math.max(0, Math.min(config.max, value)) / config.max * (bottom - top);
    const nodes = [];
    [0, 50, 100].forEach(value => {
      nodes.push(svgElement('line', { x1: left, x2: right, y1: y(value), y2: y(value), class: 'chart-guide' }));
    });
    const differences = times.slice(1).map((value, index) => value - times[index]).filter(value => value > 0).sort((a, b) => a - b);
    const measuredStep = differences.length ? differences[Math.floor(differences.length / 2)] : HISTORY_SECONDS[historyPeriod] / 120;
    const usualStep = Math.min(measuredStep, HISTORY_SECONDS[historyPeriod] / 120);
    config.lines.forEach(line => {
      chartSegments(validSeries, line.field, x, y, Math.max(1, usualStep * 3)).forEach(points => {
        if (points.length > 1) {
          const area = linePath(points) + ' L' + points[points.length - 1][0].toFixed(1) + ',' + bottom + ' L' + points[0][0].toFixed(1) + ',' + bottom + ' Z';
          nodes.push(svgElement('path', { d: area, class: 'chart-area history-' + line.color }));
        }
        nodes.push(svgElement('path', { d: linePath(points), class: 'chart-line history-' + line.color }));
      });
    });
    [0, 1 / 3, 2 / 3, 1].forEach(position => {
      const timestamp = first + span * position;
      const label = svgElement('text', {
        x: x(timestamp), y: 181, class: 'chart-axis',
        'text-anchor': position === 0 ? 'start' : (position === 1 ? 'end' : 'middle')
      });
      label.textContent = historyTime(timestamp);
      nodes.push(label);
    });
    svg.replaceChildren(...nodes);
    const fields = config.tooltip || config.lines;
    card._chartData = { series: validSeries, first, span, fields };
    const gpuKnown = validSeries.some(point => finite(point.gpu_temp) !== null);
    if (card.dataset.chart === 'temperature') {
      card.querySelector('.legend-gpu').hidden = !gpuKnown;
      // aucune température sur la période : on cache la carte plutôt que d'afficher un graphe vide
      card.hidden = !gpuKnown && !validSeries.some(point => finite(point.cpu_temp) !== null);
    }
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
    document.querySelectorAll('.history-chart').forEach(card => {
      renderChart(card, chartConfigs[card.dataset.chart], series);
    });
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

  document.querySelectorAll('.history-chart').forEach(prepareChartHover);
  start();
}());
