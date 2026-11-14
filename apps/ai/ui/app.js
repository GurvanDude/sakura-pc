const $ = selector => document.querySelector(selector);
const appWindow = $('#app-window');
const conversation = $('#conversation');
const input = $('#message');
const sendButton = $('#send');
let answering = false;
let currentAnswer = null;
let followBottom = true;

function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
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
  const lines = text.split('\n');
  const output = [];
  let list = '';
  const closeList = () => {
    if (list) output.push(`</${list}>`);
    list = '';
  };
  lines.forEach(line => {
    const unordered = line.match(/^\s*[-+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    const wanted = unordered ? 'ul' : (ordered ? 'ol' : '');
    if (wanted) {
      if (list !== wanted) {
        closeList();
        output.push(`<${wanted}>`);
        list = wanted;
      }
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
  const escaped = escapeHtml(source);
  return escaped.split('```').map((part, index) => {
    if (index % 2) return `<pre><code>${part.replace(/^\w*\n/, '')}</code></pre>`;
    return textMarkdown(part);
  }).join('');
}

function scrollIfNeeded(force = false) {
  if (force || followBottom) conversation.scrollTop = conversation.scrollHeight;
}

function addMessage(role, content, streaming = false) {
  const message = document.createElement('div');
  const bubble = document.createElement('div');
  bubble.className = 'sk-bubble';

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
  const state = { message, bubble, content };
  if (streaming) {
    bubble.innerHTML = '<div class="sk-typing" aria-label="Sakura écrit"><i></i><i></i><i></i></div>';
  } else {
    bubble.innerHTML = markdown(content);
  }
  scrollIfNeeded(true);
  return state;
}

function showWelcome() {
  addMessage('assistant', 'Coucou Gurvan 🌸 Je suis Sakura. Pose-moi une question !');
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

function showNotice(message) {
  $('#notice-text').textContent = message;
  $('#notice').hidden = false;
}

function warn(message) {
  Sakura.toast(message, { kind: 'warn' });
}

// Prévu pour les confirmations intégrées aux bulles lors de l'étape 2.
function askConfirm(bubble, { title, text, yes, no }) {
  return Sakura.confirm({ into: bubble, title, text, yes, no });
}

async function checkStatus() {
  $('#retry').disabled = true;
  try {
    const status = await window.pywebview.api.status();
    $('#notice').hidden = status.ok;
    if (!status.ok) showNotice(status.message);
  } catch (_) {
    showNotice("Sakura n'arrive pas à vérifier si Ollama est prêt.");
  } finally {
    $('#retry').disabled = false;
  }
}

async function send() {
  if (answering) {
    await window.pywebview.api.stop();
    return;
  }
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
  } catch (_) {
    window.onError("Sakura n'a pas pu envoyer ton message. Réessaie.");
  }
}

async function newChat() {
  try {
    const result = await window.pywebview.api.new_chat();
    if (!result.ok) {
      warn(result.message);
      return;
    }
    conversation.replaceChildren();
    showWelcome();
  } catch (_) {
    warn("La discussion n'a pas pu être effacée. Réessaie.");
  }
}

window.onChunk = chunk => {
  if (!currentAnswer) currentAnswer = addMessage('assistant', '', true);
  currentAnswer.content += chunk;
  currentAnswer.bubble.innerHTML = markdown(currentAnswer.content);
  scrollIfNeeded();
};

window.onDone = () => {
  if (currentAnswer && !currentAnswer.content) currentAnswer.message.remove();
  currentAnswer = null;
  setAnswering(false);
};

window.onError = message => {
  if (currentAnswer && !currentAnswer.content) currentAnswer.message.remove();
  currentAnswer = null;
  setAnswering(false);
  warn(message);
};

appWindow.insertBefore(Sakura.titlebar({
  title: 'Sakura AI',
  actions: [{ label: '＋ Nouvelle discussion', onClick: newChat }],
}), appWindow.firstChild);
Sakura.decor(appWindow, { torii: 'faint' });

conversation.addEventListener('scroll', () => {
  followBottom = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 80;
});
input.addEventListener('input', resizeInput);
input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    send();
  }
});
sendButton.addEventListener('click', send);
$('#retry').addEventListener('click', checkStatus);

window.addEventListener('pywebviewready', async () => {
  try {
    const messages = await window.pywebview.api.history();
    if (messages.length) messages.forEach(message => addMessage(message.role, message.content));
    else showWelcome();
  } catch (_) {
    showWelcome();
  }
  resizeInput();
  input.focus();
  checkStatus();
});
