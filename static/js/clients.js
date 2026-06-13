// Client management functions

var lastPingMs = null;
var _pollInFlight = false;
var _lastDataFp = null;
var _refreshTimer = null;

function loadClients() {
  if (!isSessionValid()) {
    var stats = document.getElementById('clientStats');
    if (stats) stats.textContent = 'Login required to view clients.';
    return Promise.resolve({});
  }

  if (_pollInFlight) return Promise.resolve(clientState.clients);
  _pollInFlight = true;

  var current = ++requestSeq;
  var t0 = Date.now();
  return fetch(ROUTES.clientsJson + '?_=' + t0, { cache: 'no-store' })
    .then(function(r) {
      if (!r.ok) {
        var err = new Error('Failed to load clients');
        err.status = r.status;
        throw err;
      }
      lastPingMs = Date.now() - t0;
      return r.json();
    })
    .then(function(data) {
      _pollInFlight = false;
      if (current !== requestSeq) return data;
      var fp = JSON.stringify(data);
      if (fp !== _lastDataFp) {
        _lastDataFp = fp;
        renderClients(data);
        if (typeof updateLockdownBtn === 'function') updateLockdownBtn();
      }
      return data;
    })
    .catch(function(err) {
      _pollInFlight = false;
      if (current === requestSeq) {
        var stats = document.getElementById('clientStats');
        if (stats) {
          stats.textContent = err && err.status === 401 ? 'Login required to view clients.' : 'Unable to load clients';
        }
        if (err && err.status === 401 && typeof applyAuthState === 'function') {
          applyAuthState(null);
          updateAuthStatus();
        }
      }
      if (err && err.status === 401) return {};
      console.error(err);
      throw err;
    });
}

// Debounced post-action refresh — clears in-flight flag so a fresh fetch always fires
function scheduleClientRefresh(delayMs) {
  clearTimeout(_refreshTimer);
  _refreshTimer = setTimeout(function() {
    _pollInFlight = false;
    loadClients().catch(function() {});
  }, delayMs != null ? delayMs : 200);
}

function applyRender() {
  renderClients(clientState.clients);
}

function buildRowHtml(user, data, prev) {
  var effectValue      = prev ? (prev.effect || data.effect || '') : (data.effect || '');
  var urlVal           = prev ? prev.url : '';
  var msgVal           = prev ? prev.msg : '';
  var noteVal          = prev ? (prev.note || data.note || '') : (data.note || '');
  var timeoutDurVal    = prev ? prev.timeoutDuration : '';
  var timeoutReasonVal = prev ? (prev.timeoutReason || data.timeout_reason || '') : (data.timeout_reason || '');

  var statusClass = data.recent ? 'status-active' : 'status-inactive';
  var statusLabel = data.recent ? 'Active' : 'Inactive';
  if (data.banned) {
    statusClass = 'status-banned'; statusLabel = 'Banned';
  } else if (data.timeout_active) {
    statusClass = 'status-timeout';
    statusLabel = 'Timeout ' + formatDurationLabel(data.timeout_remaining_seconds || 0);
  }

  return '<td>' + escapeHtml(user) + '</td>' +
    '<td class="status-cell"><div><span class="status-text ' + statusClass + '">' + escapeHtml(statusLabel) + '</span>' +
    (data.poll_answers && data.poll_answers.length > 0 ? '<div>' + data.poll_answers.map(function(a){ return '<span class="poll-badge">' + escapeHtml(a) + '</span>'; }).join(' ') + '</div>' : '') +
    '</div></td>' +
    '<td data-last-ping="' + escapeHtml(data.last_ping || '') + '">' + escapeHtml(formatRelativeTime(data.last_ping)) + '</td>' +
    '<td>' + (data.current_url
      ? '<a href="' + escapeHtml(data.current_url) + '" target="_blank">' + escapeHtml(data.current_url) + '</a>'
      : '<span class="cell-muted">Unknown</span>') + '</td>' +
    '<td>' + escapeHtml(effectLabel(data.effect || '')) + '</td>' +
    '<td data-user="' + escapeHtml(user) + '">' +
      '<div class="action-cell">' +
      '<div class="action-group ban-group"><button class="action-button btn-toggle-ban"' + (data.timeout_active ? ' disabled' : '') + '>' + (data.banned ? 'Unban' : 'Ban') + '</button></div>' +
      '<div class="action-group redirect-group"><input class="inp-url" placeholder="URL" value="' + escapeHtml(urlVal) + '"><button class="action-button btn-redirect">Redirect</button></div>' +
      '<div class="action-group image-group"><input type="file" class="inp-img"></div>' +
      '<div class="action-group message-group"><input class="inp-msg" placeholder="Message" value="' + escapeHtml(msgVal) + '"><button class="action-button btn-msg">Message</button></div>' +
      '<div class="action-group clear-group"><button class="action-button btn-clear-cookies" title="Ask this client to clear its cookies and reload">Unauth</button><button class="action-button btn-add-cookies">Auth</button><button class="action-button btn-img">Image ^</button></div>' +
      '<div class="action-group clear-group"><button class="action-button btn-reload" title="Reload their tab">Reload</button><button class="action-button btn-close" title="Close their tab">Close</button></div>' +
      '<div class="action-group timeout-group">' + (data.timeout_active
        ? '<button class="action-button btn-untimeout">Untimeout</button>'
        : '<input class="inp-timeout-duration" placeholder="2m 20s" value="' + escapeHtml(timeoutDurVal) + '"><input class="inp-timeout-reason" placeholder="Timeout reason" value="' + escapeHtml(timeoutReasonVal) + '"><button class="action-button btn-timeout"' + (data.banned ? ' disabled' : '') + '>Timeout</button>') + '</div>' +
      '<div class="action-group note-group"><input class="inp-note" placeholder="Note" value="' + escapeHtml(noteVal) + '"><button class="action-button btn-note">Save Note</button></div>' +
      '<div class="action-group effect-group"><select class="inp-effect">' + effectOptionsHtml(effectValue) + '</select><button class="action-button btn-effect">Apply Effect</button></div>' +
      '<div class="action-group delete-group"><button class="action-button btn-delete">Delete</button></div>' +
      '</div>' +
    '</td>';
}

function renderClients(clients) {
  clientState.clients = clients;
  var tbody = document.getElementById('clientsTableBody');
  if (!tbody) return;

  // Snapshot inputs and index existing rows before touching the DOM
  var saved = {};
  var existingRows = new Map();
  tbody.querySelectorAll('tr[data-user]').forEach(function(row) {
    var user = row.getAttribute('data-user');
    if (!user) return;
    saved[user] = {
      effect: (row.querySelector('.inp-effect') || {}).value || '',
      url:    (row.querySelector('.inp-url')    || {}).value || '',
      msg:    (row.querySelector('.inp-msg')    || {}).value || '',
      note:   (row.querySelector('.inp-note')   || {}).value || '',
      timeoutDuration: (row.querySelector('.inp-timeout-duration') || {}).value || '',
      timeoutReason:   (row.querySelector('.inp-timeout-reason')   || {}).value || ''
    };
    existingRows.set(user, row);
  });

  var filtered = Object.entries(clients);

  // Search
  var searchInput = document.getElementById('searchInput');
  if (searchInput && searchInput.value.trim()) {
    var term = searchInput.value.trim().toLowerCase();
    filtered = filtered.filter(function(entry) {
      var user = entry[0], data = entry[1];
      return (user && user.toLowerCase().includes(term)) ||
             (data.current_url && data.current_url.toLowerCase().includes(term)) ||
             (data.note && data.note.toLowerCase().includes(term));
    });
  }

  // Filter
  if (clientState.filter === 'active') {
    filtered = filtered.filter(function(e) { return !e[1].banned && e[1].recent; });
  } else if (clientState.filter === 'banned') {
    filtered = filtered.filter(function(e) { return e[1].banned; });
  } else if (clientState.filter === 'inactive') {
    filtered = filtered.filter(function(e) { return !e[1].recent; });
  }

  // Sort
  if (clientState.sortBy === 'recent') {
    filtered.sort(function(a, b) { return (b[1].last_ping || '').localeCompare(a[1].last_ping || ''); });
  } else if (clientState.sortBy === 'name') {
    filtered.sort(function(a, b) { return a[0].localeCompare(b[0]); });
  } else if (clientState.sortBy === 'url') {
    filtered.sort(function(a, b) { return (a[1].current_url || '').localeCompare(b[1].current_url || ''); });
  }

  // Stats counts (over all clients, not just filtered)
  var allVals = Object.values(clients);
  var activeCount  = allVals.filter(function(d) { return !d.banned && d.recent; }).length;
  var bannedCount  = allVals.filter(function(d) { return d.banned; }).length;
  var timeoutCount = allVals.filter(function(d) { return d.timeout_active; }).length;
  var totalCount   = Object.keys(clients).length;

  // Remove rows for users no longer in the filtered set
  var visibleUsers = new Set(filtered.map(function(e) { return e[0]; }));
  existingRows.forEach(function(row, user) {
    if (!visibleUsers.has(user)) row.remove();
  });

  // Upsert rows in sorted order. Appending a node already in the DOM moves it,
  // so this handles both insertion and reordering without a full wipe.
  filtered.forEach(function(entry) {
    var user = entry[0];
    var data = entry[1];
    var fp = JSON.stringify(data);
    var existing = existingRows.get(user);

    if (existing && existing.dataset.rowFp === fp) {
      tbody.appendChild(existing);  // Reorder: move unchanged row to end (cheap)
      return;
    }

    var row = document.createElement('tr');
    row.setAttribute('data-user', user);
    row.className = data.recent ? 'recent' : 'inactive';
    if (data.banned) row.classList.add('status-banned-row');
    else if (data.timeout_active) row.classList.add('status-timeout-row');
    row.dataset.rowFp = fp;
    row.innerHTML = buildRowHtml(user, data, saved[user]);

    if (existing) existing.remove();
    tbody.appendChild(row);
  });

  var statsText = 'Active: ' + activeCount + ' | Banned: ' + bannedCount + ' | Timed Out: ' + timeoutCount + ' | Total: ' + totalCount;
  if (lastPingMs !== null) statsText += ' | Ping: ' + lastPingMs + 'ms';
  var statsEl = document.getElementById('clientStats');
  if (statsEl) statsEl.textContent = statsText;
}

// Live-update relative timestamps without fetching
setInterval(function() {
  document.querySelectorAll('td[data-last-ping]').forEach(function(td) {
    td.textContent = formatRelativeTime(td.getAttribute('data-last-ping') || '');
  });
}, 5000);

function banClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientBan, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}

function unbanClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientUnban, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}

function toggleBan(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  var data = clientState.clients[user];
  if (data && data.banned) {
    unbanClient(btn);
  } else {
    banClient(btn);
  }
}

function deleteClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!confirm('Delete ' + user + '?')) return;
  return fetch(ROUTES.clientDelete, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}

function sendMessage(btn, msg) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!msg) return;
  return fetch(ROUTES.clientMessage, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent(msg),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}

function sendClearCookies(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientMessage, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent('__MANGER_CLEAR_COOKIES__'),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() {
    if (typeof sendAudit === 'function') return sendAudit('clear_cookies', user, {}, true);
  }).then(function() { scheduleClientRefresh(); });
}

function sendAddCookies(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientMessage, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent('__MANGER_ADD_COOKIES__'),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() {
    if (typeof sendAudit === 'function') return sendAudit('add_cookies', user, {}, true);
  }).then(function() { scheduleClientRefresh(); });
}

function sendReload(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientMessage, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent('__RELOAD__'),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() {
    if (typeof sendAudit === 'function') return sendAudit('reload', user, {}, true);
  }).then(function() { scheduleClientRefresh(); });
}

function sendClose(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientMessage, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent('__CLOSE__'),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() {
    if (typeof sendAudit === 'function') return sendAudit('close', user, {}, true);
  }).then(function() { scheduleClientRefresh(); });
}

function sendRedirect(btn, url) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!url) return;
  return fetch(ROUTES.clientRedirect, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&u=' + encodeRouteValue(url),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}

function sendEffect(btn, effect) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientEffect, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&effect=' + encodeURIComponent(effect || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}

function sendNote(btn, note) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientNote, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&note=' + encodeURIComponent(note || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}

function sendTimeout(btn, duration, reason) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!duration) return;
  return fetch(ROUTES.clientTimeout, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&duration=' + encodeURIComponent(duration) + '&reason=' + encodeURIComponent(reason || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}

function clearClientTimeout(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientTimeoutClear, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { scheduleClientRefresh(); });
}
