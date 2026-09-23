// ─── AI Chat Widget ────────────────────────────────────────────────────────
const chatBtn    = document.getElementById('ai-chat-btn');
const chatWindow = document.getElementById('ai-chat-window');
const chatClose  = document.getElementById('ai-chat-close');
const chatInput  = document.getElementById('ai-chat-input');
const chatSend   = document.getElementById('ai-chat-send');
const chatMsgs   = document.getElementById('ai-messages');

let chatOpen = false;

if (chatBtn) {
  chatBtn.addEventListener('click', () => {
    chatOpen = !chatOpen;
    if (chatOpen) {
      chatWindow.classList.add('open');
      chatInput && chatInput.focus();
      if (chatMsgs.children.length === 0) {
        appendBotMessage("Hello! 👋 I'm your AI Learning Assistant. I'm here to help you understand your courses, track assignments, and guide your studies. What would you like to know?");
      }
    } else {
      chatWindow.classList.remove('open');
    }
  });
}

if (chatClose) {
  chatClose.addEventListener('click', () => {
    chatOpen = false;
    chatWindow.classList.remove('open');
  });
}

if (chatSend) {
  chatSend.addEventListener('click', sendMessage);
}

if (chatInput) {
  chatInput.addEventListener('keypress', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

function sendMessage() {
  const msg = chatInput.value.trim();
  if (!msg) return;

  appendUserMessage(msg);
  chatInput.value = '';

  // Show typing indicator
  const typingEl = showTyping();

  fetch('/ai/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCSRFToken()
    },
    body: JSON.stringify({ message: msg })
  })
    .then(r => r.json())
    .then(data => {
      typingEl.remove();
      appendBotMessage(data.response || "I'm sorry, I couldn't process that. Please try again.");
    })
    .catch(() => {
      typingEl.remove();
      appendBotMessage("Oops! Something went wrong. Please try again in a moment.");
    });
}

function appendUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'ai-msg user';
  div.innerHTML = `
    <div class="ai-avatar user"><i class="ri-user-line"></i></div>
    <div class="ai-bubble">${escapeHtml(text)}</div>
  `;
  chatMsgs.appendChild(div);
  scrollToBottom();
}

function appendBotMessage(text) {
  const div = document.createElement('div');
  div.className = 'ai-msg bot';
  div.innerHTML = `
    <div class="ai-avatar bot"><i class="ri-robot-line"></i></div>
    <div class="ai-bubble">${formatBotMsg(text)}</div>
  `;
  chatMsgs.appendChild(div);
  scrollToBottom();
}

function showTyping() {
  const div = document.createElement('div');
  div.className = 'ai-msg bot';
  div.innerHTML = `
    <div class="ai-avatar bot"><i class="ri-robot-line"></i></div>
    <div class="ai-bubble">
      <div class="ai-typing"><span></span><span></span><span></span></div>
    </div>
  `;
  chatMsgs.appendChild(div);
  scrollToBottom();
  return div;
}

function scrollToBottom() {
  if (chatMsgs) chatMsgs.scrollTop = chatMsgs.scrollHeight;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function formatBotMsg(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

function getCSRFToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

// Quick suggestion chips
document.querySelectorAll('.ai-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    if (chatInput) {
      chatInput.value = chip.textContent;
      sendMessage();
    }
  });
});
