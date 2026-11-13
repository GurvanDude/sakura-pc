const $ = selector => document.querySelector(selector);
const conversation = $('#conversation');
const input = $('#message');
const sendButton = $('#send');
const newChatButton = $('#new-chat');
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
  const article = document.createElement('article');
  article.className = `message ${role}`;
  const speaker = document.createElement('div');
  speaker.className = 'speaker';
  speaker.textContent = role === 'user' ? 'Gurvan' : 'Sakura';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  article.append(speaker, bubble);
  conversation.append(article);
  const state = { article, bubble, content };
  if (streaming) bubble.innerHTML = '<span class="thinking">Sakura réfléchit…</span>';
  else bubble.innerHTML = markdown(content);
  scrollIfNeeded(true);
  return state;
}

function showWelcome() {
  addMessage('assistant', 'Coucou Gurvan 🌸 Je suis Sakura. Pose-moi une question !');
}

function setAnswering(value) {
  answering = value;
  sendButton.textContent = value ? 'Stop' : 'Envoyer';
  sendButton.classList.toggle('stop', value);
  newChatButton.disabled = value;
  input.disabled = value;
  if (!value) input.focus();
}

function resizeInput() {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
}

function showNotice(message) {
  $('#notice-text').textContent = message;
  $('#notice').hidden = false;
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
    if (!result.ok) onError(result.message);
  } catch (_) {
    onError("Sakura n'a pas pu envoyer ton message. Réessaie.");
  }
}

window.onChunk = chunk => {
  if (!currentAnswer) currentAnswer = addMessage('assistant', '', true);
  currentAnswer.content += chunk;
  currentAnswer.bubble.innerHTML = markdown(currentAnswer.content);
  scrollIfNeeded();
};

window.onDone = () => {
  if (currentAnswer && !currentAnswer.content) currentAnswer.article.remove();
  currentAnswer = null;
  setAnswering(false);
};

window.onError = message => {
  if (currentAnswer && !currentAnswer.content) currentAnswer.article.remove();
  currentAnswer = null;
  setAnswering(false);
  showNotice(message);
};

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
newChatButton.addEventListener('click', async () => {
  const result = await window.pywebview.api.new_chat();
  if (result.ok) {
    conversation.replaceChildren();
    showWelcome();
  } else showNotice(result.message);
});

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

