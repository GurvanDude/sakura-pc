const $ = selector => document.querySelector(selector);

function make(tag, className = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  return element;
}

function createCard(card) {
  const article = make('article', `card ${card.level}`);
  article.dataset.card = card.id;
  const head = make('div', 'card-head');
  const icon = make('span', 'card-icon');
  const heading = make('div');
  const title = make('h3');
  const role = make('p', 'role');
  const gauge = make('div', 'gauge');
  gauge.append(make('span'));
  const summary = make('p', 'summary');
  summary.append(make('span', 'word'), make('span', 'big-percent'));
  const figures = make('div', 'figures');
  card.figures.forEach(() => {
    const row = make('div', 'figure');
    row.append(make('span', 'figure-label'), make('span', 'figure-value'), make('span', 'figure-hint'));
    figures.append(row);
  });
  article.append(head, gauge, summary, figures, make('p', 'sentence'));
  heading.append(title, role);
  head.append(icon, heading);
  return article;
}

function renderCards(cards) {
  const box = $('#cards');
  const structure = cards.map(card => `${card.id}:${card.figures.map(figure => figure.label).join(',')}`).join('|');
  if (box.dataset.structure !== structure) {
    box.dataset.structure = structure;
    box.replaceChildren(...cards.map(createCard));
  }
  cards.forEach(card => {
    const element = [...box.children].find(child => child.dataset.card === card.id);
    element.className = `card ${card.level}`;
    element.querySelector('.card-icon').textContent = card.icon;
    element.querySelector('h3').textContent = card.title;
    element.querySelector('.role').textContent = card.role;
    element.querySelector('.word').textContent = card.word;
    const percent = Number(card.percent).toLocaleString('fr-FR', { maximumFractionDigits: 1 });
    element.querySelector('.big-percent').textContent = ` · ${card.level === 'inconnu' ? '—' : `${percent} %`}`;
    element.querySelector('.sentence').textContent = card.sentence;
    element.querySelector('.gauge span').style.width = `${Math.max(0, Math.min(100, card.percent || 0))}%`;
    [...element.querySelectorAll('.figure')].forEach((row, index) => {
      const figure = card.figures[index];
      row.querySelector('.figure-label').textContent = figure.label;
      row.querySelector('.figure-value').textContent = figure.value;
      row.querySelector('.figure-hint').textContent = figure.hint;
      row.querySelector('.figure-hint').hidden = !figure.hint;
    });
  });
}

function createAppRow() {
  const row = make('div', 'app-row');
  const bar = make('span', 'app-bar');
  bar.append(make('span'));
  const copy = make('div', 'app-copy');
  copy.append(make('span', 'app-numbers'), make('span', 'app-what'));
  row.append(make('span', 'app-name'), bar, copy);
  return row;
}

function renderApps(apps) {
  const box = $('#apps');
  const structure = String(apps.length);
  if (box.dataset.structure !== structure) {
    box.dataset.structure = structure;
    box.replaceChildren(...(apps.length ? apps.map(createAppRow) : [make('p', 'empty')]));
  }
  if (!apps.length) {
    box.querySelector('.empty').textContent = 'Aucun programme gourmand en ce moment.';
    return;
  }
  const maxWeight = Math.max(1, ...apps.map(app => app.cpu_percent + app.ram_gb * 3));
  [...box.querySelectorAll('.app-row')].forEach((element, index) => {
    const app = apps[index];
    element.querySelector('.app-name').textContent = app.name;
    element.querySelector('.app-numbers').textContent = `${app.cpu_text} · ${app.ram_text}`;
    element.querySelector('.app-what').textContent = app.what;
    element.querySelector('.app-bar span').style.width = `${Math.max(4, (app.cpu_percent + app.ram_gb * 3) / maxWeight * 100)}%`;
  });
}

function renderTips(tips) {
  const panel = $('#tips-panel');
  const box = $('#tips');
  panel.hidden = !tips.length;
  if (box.dataset.structure !== String(tips.length)) {
    box.dataset.structure = String(tips.length);
    box.replaceChildren(...tips.map(() => {
      const row = make('div', 'tip');
      row.append(make('span', 'tip-icon'), make('span', 'tip-text'));
      return row;
    }));
  }
  [...box.children].forEach((row, index) => {
    row.querySelector('.tip-icon').textContent = tips[index].icon;
    row.querySelector('.tip-text').textContent = tips[index].text;
  });
}

function number(value, unit) {
  if (value === null || value === undefined || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `${parsed.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} ${unit}` : '—';
}

function detailData(view, status) {
  const cpu = status.cpu && typeof status.cpu === 'object' ? status.cpu : {};
  const disk = status.disk && typeof status.disk === 'object' ? status.disk : {};
  const cores = Array.isArray(cpu.per_core) ? cpu.per_core : [];
  const physical = disk.per_disk && typeof disk.per_disk === 'object' ? Object.entries(disk.per_disk) : [];
  const notes = [];
  if (status.temps?.reason) notes.push(status.temps.reason);
  if (status.errors && typeof status.errors === 'object') {
    Object.entries(status.errors).forEach(([key, value]) => notes.push(`${key} : ${value}`));
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
      const bar = make('span', 'core-bar');
      bar.append(make('span'));
      row.append(make('span', 'core-name'), bar, make('span', 'core-value'));
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
  const structure = `${data.cards.length}|${data.cores.length}|${data.physical.map(([name]) => name).join(',')}|${data.notes.length}`;
  if (box.dataset.structure !== structure) {
    box.dataset.structure = structure;
    rebuildDetails(box, sensorBox, data);
  }
  [...box.querySelectorAll('.card-detail')].forEach((row, index) => {
    const card = data.cards[index];
    row.textContent = `${card.title} · ${card.detail}`;
  });
  box.querySelector('.frequency-detail').textContent = `Fréquence du processeur · ${number(data.cpu.freq_mhz, 'MHz')}`;
  [...box.querySelectorAll('.core-row')].forEach((row, index) => {
    const rawValue = data.cores[index];
    const value = rawValue === null || rawValue === undefined || rawValue === '' ? NaN : Number(rawValue);
    row.querySelector('.core-name').textContent = `Cœur ${index + 1}`;
    row.querySelector('.core-value').textContent = Number.isFinite(value) ? `${value.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %` : '—';
    row.querySelector('.core-bar span').style.width = `${Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0}%`;
  });
  [...box.querySelectorAll('.disk-detail')].forEach((row, index) => {
    const [name, rawValues] = data.physical[index];
    const values = rawValues && typeof rawValues === 'object' ? rawValues : {};
    row.textContent = `${name} · lecture ${number(values.read_mb_s, 'Mo/s')} · écriture ${number(values.write_mb_s, 'Mo/s')}`;
  });
  [...sensorBox.children].forEach((row, index) => { row.textContent = data.notes[index]; });
}

function render({ view, status }) {
  $('#verdict').className = `verdict ${view.verdict.mood}`;
  $('#verdict-emoji').textContent = view.verdict.emoji;
  $('#verdict-title').textContent = view.verdict.title;
  $('#verdict-text').textContent = view.verdict.text;
  renderCards(view.cards);
  renderApps(view.apps);
  renderTips(view.tips);
  renderDetails(view, status);
}

async function refresh() {
  try { render(await window.pywebview.api.get_view()); } catch (_) { /* nouvel essai bientôt */ }
}

$('#details-button').addEventListener('click', () => {
  const open = $('#details').hidden;
  $('#details').hidden = !open;
  $('#details-button').textContent = open ? 'Masquer les détails' : 'Afficher les détails';
  $('#details-button').setAttribute('aria-expanded', String(open));
});
window.addEventListener('pywebviewready', () => { refresh(); setInterval(refresh, 1500); });
