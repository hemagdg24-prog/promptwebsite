// ─── Notification System ──────────────────────────────────────────────────
const notifBtn  = document.getElementById('notif-btn');
const notifDrop = document.getElementById('notif-dropdown');
const notifCount = document.getElementById('notif-count');

if (notifBtn && notifDrop) {
  notifBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    notifDrop.classList.toggle('show');
    if (notifDrop.classList.contains('show')) loadNotifications();
  });

  document.addEventListener('click', (e) => {
    if (!notifDrop.contains(e.target) && e.target !== notifBtn) {
      notifDrop.classList.remove('show');
    }
  });
}

function loadNotifications() {
  fetch('/notifications/data')
    .then(r => r.json())
    .then(data => {
      // Update badge
      const badge = document.querySelector('.notif-dot');
      if (badge) badge.style.display = data.count > 0 ? 'block' : 'none';
      if (notifCount) notifCount.textContent = data.count || '';

      const list = document.getElementById('notif-list');
      if (!list) return;
      if (data.notifications.length === 0) {
        list.innerHTML = '<div class="empty-state" style="padding:24px"><i class="ri-notification-line"></i><p>No notifications</p></div>';
        return;
      }

      const typeIcons = { info: 'ri-information-line', warning: 'ri-alert-line', deadline: 'ri-time-line', grade: 'ri-star-line' };
      list.innerHTML = data.notifications.map(n => `
        <div class="notif-item ${n.is_read ? '' : 'unread'}" data-id="${n.id}" onclick="markRead(${n.id}, this)">
          <div class="notif-icon ${n.type}">
            <i class="${typeIcons[n.type] || 'ri-notification-line'}"></i>
          </div>
          <div class="notif-body">
            <div class="title">${n.title}</div>
            <div class="msg">${n.message}</div>
            <div class="time">${n.created_at}</div>
          </div>
        </div>
      `).join('');
    });
}

function markRead(id, el) {
  fetch(`/notifications/mark-read/${id}`, { method: 'POST', headers: { 'X-CSRFToken': getCSRF() } })
    .then(() => { el.classList.remove('unread'); loadNotifications(); });
}

function markAllRead() {
  fetch('/notifications/mark-all-read', { method: 'POST', headers: { 'X-CSRFToken': getCSRF() } })
    .then(() => loadNotifications());
}

// ─── CSRF Token Helper ─────────────────────────────────────────────────────
function getCSRF() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

// ─── Flash Messages Auto-hide ──────────────────────────────────────────────
document.querySelectorAll('.flash-msg').forEach(el => {
  setTimeout(() => el.remove(), 5000);
});

// ─── Active Nav Highlight ──────────────────────────────────────────────────
const currentPath = window.location.pathname;
document.querySelectorAll('.nav-item').forEach(item => {
  const href = item.getAttribute('href') || item.dataset.href;
  if (href && currentPath.startsWith(href) && href !== '/') {
    item.classList.add('active');
  }
});

// ─── File Upload Drag & Drop ───────────────────────────────────────────────
document.querySelectorAll('.file-upload-area').forEach(area => {
  const input = area.querySelector('input[type="file"]');

  area.addEventListener('click', () => input && input.click());
  area.addEventListener('dragover', e => { e.preventDefault(); area.classList.add('drag-over'); });
  area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
  area.addEventListener('drop', e => {
    e.preventDefault();
    area.classList.remove('drag-over');
    if (input && e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      updateFileLabel(area, e.dataTransfer.files[0].name);
    }
  });

  if (input) {
    input.addEventListener('change', () => {
      if (input.files.length) updateFileLabel(area, input.files[0].name);
    });
  }
});

function updateFileLabel(area, name) {
  const p = area.querySelector('p');
  if (p) p.innerHTML = `<strong style="color:var(--accent)">${name}</strong> selected`;
}

// ─── Confirm Delete Dialogs ────────────────────────────────────────────────
document.querySelectorAll('[data-confirm]').forEach(btn => {
  btn.addEventListener('click', e => {
    if (!confirm(btn.dataset.confirm)) e.preventDefault();
  });
});

// ─── Tab Navigation ────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
    btn.classList.add('active');
    const panel = document.getElementById(target);
    if (panel) panel.style.display = 'block';
  });
});

// ─── Modal Helpers ─────────────────────────────────────────────────────────
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add('show');
}
function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove('show');
}

document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.classList.remove('show');
  });
});

// ─── Animate Progress Bars on Load ────────────────────────────────────────
function animateProgressBars() {
  document.querySelectorAll('.progress-bar-fill').forEach(bar => {
    const target = bar.dataset.width || bar.style.width;
    bar.style.width = '0%';
    setTimeout(() => { bar.style.width = target; }, 200);
  });
}
window.addEventListener('load', animateProgressBars);

// ─── Poll Notification Count ───────────────────────────────────────────────
function pollNotifications() {
  fetch('/notifications/data')
    .then(r => r.json())
    .then(data => {
      const dot = document.querySelector('.notif-dot');
      if (dot) dot.style.display = data.count > 0 ? 'block' : 'none';
      if (notifCount) notifCount.textContent = data.count > 0 ? data.count : '';
    })
    .catch(() => {});
}
setInterval(pollNotifications, 30000);
pollNotifications();
