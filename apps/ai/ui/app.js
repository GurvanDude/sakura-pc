const $ = selector => document.querySelector(selector);
const appWindow = $('#app-window');
const conversation = $('#conversation');
const input = $('#message');
const sendButton = $('#send');
let answering = false;
let currentAnswer = null;
let currentChatId = null;
let followBottom = true;

function escapeHtml(text) {
  return String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function inlineMarkdown(text) {
  const code = [];
  let rendered = text.replace(/`([^`\n]+)`/g, (_, value) => {
    code.push(`<code>${value}</code>`);
    return `\u0000${code.length - 1}\u0000`;
  });
  rendered = rendered.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  rendered = rendered.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  return rendered.replace(/\u0000(\d+)\u0000/g, (_, index) => code[Number(index)]);
}

function textMarkdown(text) {
  const output = [];
  let list = '';
  const closeList = () => { if (list) output.push(`</${list}>`); list = ''; };
  text.split('\n').forEach(line => {
    const unordered = line.match(/^\s*[-+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    const wanted = unordered ? 'ul' : (ordered ? 'ol' : '');
    if (wanted) {
      if (list !== wanted) { closeList(); output.push(`<${wanted}>`); list = wanted; }
      output.push(`<li>${inlineMarkdown((unordered || ordered)[1])}</li>`);
    } else {
      closeList();
      output.push(line ? inlineMarkdown(line) : '<br>');
      if (line) output.push('<br>');
    }
  });
  closeList();
  if (output.at(-1) === '<br>') output.pop();
  return output.join('');
}

function markdown(source) {
  return escapeHtml(source).split('```').map((part, index) => {
    if (index % 2) return `<pre><code>${part.replace(/^\w*\n/, '')}</code></pre>`;
    return textMarkdown(part);
  }).join('');
}

function scrollIfNeeded(force = false) {
  if (force || followBottom) conversation.scrollTop = conversation.scrollHeight;
}

function addMessage(role, content, streaming = false, actions = []) {
  const message = document.createElement('div');
  const bubble = document.createElement('div');
  const answer = document.createElement('div');
  bubble.className = 'sk-bubble';
  bubble.appendChild(answer);
  if (role === 'user') {
    message.className = 'sk-msg sk-msg--me';
    message.appendChild(bubble);
  } else {
    message.className = 'sk-msg sk-msg--sakura';
    const avatar = document.createElement('div');
    avatar.className = 'sk-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.textContent = '🌸';
    const body = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'sk-msg-name';
    name.textContent = 'Sakura';
    body.append(name, bubble);
    message.append(avatar, body);
  }
  conversation.appendChild(message);
  const state = { message, bubble, answer, content, hasExtras: actions.length > 0 };
  answer.innerHTML = streaming
    ? '<div class="sk-typing" aria-label="Sakura écrit"><i></i><i></i><i></i></div>'
    : markdown(content);
  actions.forEach(text => addActionLine(state, text));
  scrollIfNeeded(true);
  return state;
}

function addActionLine(state, text) {
  const line = document.createElement('p');
  line.className = 'sk-hint';
  line.textContent = `✦ ${text}`;
  state.bubble.appendChild(line);
  state.hasExtras = true;
}

function showWelcome() { addMessage('assistant', 'Coucou Gurvan 🌸 Je suis Sakura. Pose-moi une question !'); }

function renderConversation(messages) {
  conversation.replaceChildren();
  followBottom = true;
  if (messages.length) messages.forEach(message => addMessage(message.role, message.content, false, message.actions || []));
  else showWelcome();
  scrollIfNeeded(true);
}

function setAnswering(value) {
  answering = value;
  sendButton.textContent = value ? '■' : '↑';
  sendButton.setAttribute('aria-label', value ? 'Arrêter la réponse' : 'Envoyer le message');
  input.disabled = value;
  if (!value) input.focus();
}

function resizeInput() {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight + input.offsetHeight - input.clientHeight, parseFloat(getComputedStyle(input).maxHeight))}px`;
}

function showNotice(message) { $('#notice-text').textContent = message; $('#notice').hidden = false; }
function warn(message) { Sakura.toast(message, { kind: 'warn' }); }
function askConfirm(bubble, options) { return Sakura.confirm({ into: bubble, ...options }); }

async function checkStatus() {
  $('#retry').disabled = true;
  try {
    const status = await window.pywebview.api.status();
    $('#notice').hidden = status.ok;
    if (!status.ok) showNotice(status.message);
  } catch (_) { showNotice("Sakura n'arrive pas à vérifier si Ollama est prêt."); }
  finally { $('#retry').disabled = false; }
}

async function send() {
  if (answering) { await window.pywebview.api.stop(); return; }
  const text = input.value.trim();
  if (!text) return;
  addMessage('user', text);
  currentAnswer = addMessage('assistant', '', true);
  input.value = '';
  resizeInput();
  setAnswering(true);
  try {
    const result = await window.pywebview.api.send(text);
    if (!result.ok) window.onError(result.message);
    else window.onChatsChanged();
  } catch (_) { window.onError("Sakura n'a pas pu envoyer ton message. Réessaie."); }
}

async function newChat() {
  try {
    const result = await window.pywebview.api.new_chat();
    if (!result.ok) { warn(result.message); return; }
    currentChatId = result.id;
    renderConversation([]);
    await loadChats();
    closeMobileSidebar();
  } catch (_) { warn("La nouvelle discussion n'a pas pu être créée. Réessaie."); }
}

function groupName(updated) {
  const value = new Date(updated);
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  const difference = Math.floor((start - day) / 86400000);
  if (difference <= 0) return "Aujourd'hui";
  if (difference === 1) return 'Hier';
  if (difference < 7) return '7 derniers jours';
  return 'Plus tôt';
}

function beginRename(row, chat) {
  const inputTitle = document.createElement('input');
  inputTitle.className = 'sk-input chat-rename';
  inputTitle.value = chat.title;
  inputTitle.setAttribute('aria-label', 'Nouveau titre');
  row.replaceChildren(inputTitle);
  inputTitle.focus();
  inputTitle.select();
  let finished = false;
  const finish = async save => {
    if (finished) return;
    finished = true;
    if (save) {
      const result = await window.pywebview.api.rename_chat(chat.id, inputTitle.value);
      if (!result.ok) warn(result.message);
    }
    await loadChats();
  };
  inputTitle.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); finish(true); }
    if (event.key === 'Escape') { event.preventDefault(); finish(false); }
  });
  inputTitle.addEventListener('blur', () => finish(true));
}

async function deleteChat(chat) {
  const accepted = await Sakura.confirm({
    into: $('#chat-confirm'),
    title: 'Supprimer cette discussion ?',
    text: 'Elle part dans la corbeille de Sakura, tu pourras la récupérer.',
    yes: 'Oui, supprime-la',
    no: 'Non, laisse',
  });
  if (!accepted) return;
  const result = await window.pywebview.api.delete_chat(chat.id);
  if (!result.ok) { warn(result.message); return; }
  currentChatId = result.id;
  renderConversation(result.messages);
  await loadChats();
}

async function openChat(chatId) {
  try {
    const result = await window.pywebview.api.open_chat(chatId);
    if (!result.ok) { warn(result.message); return; }
    currentChatId = result.id;
    renderConversation(result.messages);
    await loadChats();
    closeMobileSidebar();
  } catch (_) { warn("La discussion n'a pas pu être ouverte."); }
}

async function loadChats() {
  try {
    currentChatId = await window.pywebview.api.current();
    const chats = await window.pywebview.api.chats();
    const groups = new Map();
    chats.forEach(chat => {
      const group = groupName(chat.updated);
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(chat);
    });
    const list = $('#chat-list');
    list.replaceChildren();
    ["Aujourd'hui", 'Hier', '7 derniers jours', 'Plus tôt'].forEach(name => {
      if (!groups.has(name)) return;
      const section = document.createElement('section');
      section.className = 'chat-group';
      const title = document.createElement('h2');
      title.className = 'chat-group-title';
      title.textContent = name;
      section.appendChild(title);
      groups.get(name).forEach(chat => {
        const row = document.createElement('div');
        row.className = `chat-row${chat.id === currentChatId ? ' is-active' : ''}`;
        const open = document.createElement('button');
        open.type = 'button';
        open.className = 'chat-open';
        open.textContent = chat.title;
        open.title = chat.title;
        open.addEventListener('click', () => openChat(chat.id));
        const actions = document.createElement('span');
        actions.className = 'chat-actions';
        const rename = document.createElement('button');
        rename.type = 'button';
        rename.className = 'sk-btn sk-btn--icon chat-action';
        rename.textContent = '✎';
        rename.setAttribute('aria-label', `Renommer ${chat.title}`);
        rename.addEventListener('click', () => beginRename(row, chat));
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'sk-btn sk-btn--icon chat-action';
        remove.textContent = '🗑';
        remove.setAttribute('aria-label', `Supprimer ${chat.title}`);
        remove.addEventListener('click', () => deleteChat(chat));
        actions.append(rename, remove);
        row.append(open, actions);
        section.appendChild(row);
      });
      list.appendChild(section);
    });
  } catch (_) { warn("La liste des discussions n'a pas pu être chargée."); }
}

function isNarrow() { return window.matchMedia('(max-width: 760px)').matches; }
function closeMobileSidebar() { if (isNarrow()) appWindow.classList.remove('sidebar-open'); }
function toggleSidebar() {
  if (isNarrow()) { appWindow.classList.toggle('sidebar-open'); return; }
  const collapsed = appWindow.classList.toggle('sidebar-collapsed');
  try { localStorage.setItem('sakura-ai-sidebar-collapsed', String(collapsed)); } catch (_) { /* stockage indisponible */ }
}

window.onChunk = chunk => {
  if (!currentAnswer) currentAnswer = addMessage('assistant', '', true);
  currentAnswer.content += chunk;
  currentAnswer.answer.innerHTML = markdown(currentAnswer.content);
  scrollIfNeeded();
};

window.onConfirm = async (id, options) => {
  if (!currentAnswer) currentAnswer = addMessage('assistant', '', true);
  currentAnswer.hasExtras = true;
  scrollIfNeeded(true);
  let accepted = false;
  try { accepted = await askConfirm(currentAnswer.bubble, options); }
  finally {
    try { await window.pywebview.api.answer_confirm(id, accepted); } catch (_) { /* réponse déjà arrêtée */ }
  }
};

window.onCancelConfirm = () => {
  const cancel = currentAnswer?.bubble.querySelector('.sk-confirm .sk-btn--secondary');
  if (cancel) cancel.click();
};

window.onAction = text => {
  if (!currentAnswer) currentAnswer = addMessage('assistant', '', true);
  addActionLine(currentAnswer, text);
  scrollIfNeeded(true);
};

window.onDone = () => {
  if (currentAnswer && !currentAnswer.content && !currentAnswer.hasExtras) currentAnswer.message.remove();
  else if (currentAnswer && !currentAnswer.content) currentAnswer.answer.remove();
  currentAnswer = null;
  setAnswering(false);
  window.onChatsChanged();
};

window.onError = message => {
  if (currentAnswer && !currentAnswer.content && !currentAnswer.hasExtras) currentAnswer.message.remove();
  else if (currentAnswer && !currentAnswer.content) currentAnswer.answer.remove();
  currentAnswer = null;
  setAnswering(false);
  warn(message);
};

window.onChatsChanged = async () => { await loadChats(); };

const titlebar = Sakura.titlebar({
  title: 'Sakura AI',
  actions: [
    { label: '☰', onClick: toggleSidebar },
    { label: '＋ Nouvelle discussion', onClick: newChat },
  ],
});
const titleActions = titlebar.querySelectorAll('.sk-titlebar-actions .sk-btn');
titleActions[0]?.setAttribute('aria-label', 'Afficher ou masquer les discussions');
appWindow.insertBefore(titlebar, appWindow.firstChild);
Sakura.decor(appWindow, { torii: 'faint' });

try {
  if (localStorage.getItem('sakura-ai-sidebar-collapsed') === 'true') appWindow.classList.add('sidebar-collapsed');
} catch (_) { /* stockage indisponible */ }

conversation.addEventListener('scroll', () => {
  followBottom = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 80;
});
input.addEventListener('input', resizeInput);
input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); }
});
sendButton.addEventListener('click', send);
$('#retry').addEventListener('click', checkStatus);
$('#sidebar-backdrop').addEventListener('click', closeMobileSidebar);

window.addEventListener('pywebviewready', async () => {
  try {
    currentChatId = await window.pywebview.api.current();
    renderConversation(await window.pywebview.api.history());
    await loadChats();
  } catch (_) { showWelcome(); }
  resizeInput();
  input.focus();
  checkStatus();
});
