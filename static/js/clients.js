// Client management functions

function loadClients() {
  if (!isSessionValid()) {
    var stats = document.getElementById('clientStats');
    if (stats) {
      stats.textContent = 'Login required to view clients.';
    }
    return Promise.resolve({});
  }

  var current = ++requestSeq;
  return fetch(ROUTES.clientsJson + '?_=' + Date.now(), { cache: 'no-store' })
    .then(function(r) {
      if (!r.ok) {
        var err = new Error('Failed to load clients');
        err.status = r.status;
        throw err;
      }
      return r.json();
    })
    .then(function(data) {
      if (current !== requestSeq) return data;
      renderClients(data);
      return data;
    })
    .catch(function(err) {
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
      if (err && err.status === 401) {
        return {};
      }
      console.error(err);
      throw err;
    });
}

function renderClients(clients) {
  clientState.clients = clients;
  var table = document.getElementById('clientsTable');
  var existingRows = {};
  table.querySelectorAll('tr').forEach(function(row) {
    var username = row.cells[0]?.textContent;
    if (username) existingRows[username] = row;
  });

  var filtered = Object.entries(clients);

  if (clientState.filter === 'active') {
    filtered = filtered.filter(function(entry) { return !entry[1].banned && entry[1].recent; });
  } else if (clientState.filter === 'banned') {
    filtered = filtered.filter(function(entry) { return entry[1].banned; });
  } else if (clientState.filter === 'inactive') {
    filtered = filtered.filter(function(entry) { return !entry[1].recent; });
  }

  if (clientState.sortBy === 'recent') {
    filtered.sort(function(a, b) { return (b[1].last_ping || '').localeCompare(a[1].last_ping || ''); });
  } else if (clientState.sortBy === 'name') {
    filtered.sort(function(a, b) { return a[0].localeCompare(b[0]); });
  } else if (clientState.sortBy === 'url') {
    filtered.sort(function(a, b) { return (a[1].current_url || '').localeCompare(b[1].current_url || ''); });
  }

  var activeCount = Object.values(clients).filter(function(d) { return !d.banned && d.recent; }).length;
  var bannedCount = Object.values(clients).filter(function(d) { return d.banned; }).length;
  var timeoutCount = Object.values(clients).filter(function(d) { return d.timeout_active; }).length;
  var totalCount = Object.keys(clients).length;

  table.innerHTML = '<tr><th>Username</th><th>Status</th><th>Last Ping</th><th>Current URL</th><th>Effect</th><th>Question</th><th>Response</th><th>Actions</th></tr>';

  filtered.forEach(function(entry) {
    var user = entry[0];
    var data = entry[1];
    var row = document.createElement('tr');
    row.className = (data.recent ? 'recent' : 'inactive');
    var statusText = '';

    var statusInfo = '';
    if (data.banned) {
      statusInfo = '<span class="status-text status-banned">Banned</span>';
      row.classList.add('status-banned-row');
    } else if (data.timeout_active) {
      statusInfo = '<span class="status-text status-timeout">Timeout ' + formatDurationLabel(data.timeout_remaining_seconds || 0) + '</span>';
      row.classList.add('status-timeout-row');
    }
    if (statusInfo) {
      var onlineStatus = data.recent ? 'Online' : 'Offline';
      statusText = '<span class="status-text ' + (data.recent ? 'status-online' : 'status-offline') + '">' + onlineStatus + '</span> (' + statusInfo + ')';
    } else {
      statusText = '<span class="status-text ' + (data.recent ? 'status-active' : 'status-offline') + '">' + (data.recent ? 'Active' : 'Inactive') + '</span>';
    }

    var existing = existingRows[user];
    var effectValue = existing ? (existing.querySelector('.inp-effect')?.value || data.effect || '') : (data.effect || '');
    var urlVal = existing ? (existing.querySelector('.inp-url')?.value || '') : '';
    var msgVal = existing ? (existing.querySelector('.inp-msg')?.value || '') : '';
    var noteVal = existing ? (existing.querySelector('.inp-note')?.value || data.note || '') : (data.note || '');
    var questionVal = existing ? (existing.querySelector('.inp-question')?.value || data.question || '') : (data.question || '');
    var timeoutDurationVal = existing ? (existing.querySelector('.inp-timeout-duration')?.value || '') : '';
    var timeoutReasonVal = existing ? (existing.querySelector('.inp-timeout-reason')?.value || data.timeout_reason || '') : (data.timeout_reason || '');
    var answerVal = data.question_answer || '';

    row.setAttribute('data-user', user);
    row.innerHTML =
      '<td>' + escapeHtml(user) + '</td>' +
      '<td>' + statusText + '</td>' +
      '<td>' + escapeHtml(data.last_ping || 'Never') + '</td>' +
      '<td>' + (data.current_url ? '<a href="' + escapeHtml(data.current_url) + '" target="_blank">' + escapeHtml(data.current_url) + '</a>' : '<span class="cell-muted">Unknown</span>') + '</td>' +
      '<td>' + escapeHtml(effectLabel(data.effect || '')) + '</td>' +
      '<td>' + (data.question ? escapeHtml(data.question) : '<span class="cell-muted">None</span>') + '</td>' +
      '<td>' + (answerVal ? '<strong>' + escapeHtml(answerVal) + '</strong>' : '<span class="cell-muted">Pending</span>') + '</td>' +
      '<td data-user="' + escapeHtml(user) + '">' +
        '<div class="action-cell">' +
        '<div class="action-group ban-group"><button class="action-button btn-toggle-ban" ' + (data.timeout_active ? 'disabled' : '') + '>' + (data.banned ? 'Unban' : 'Ban') + '</button></div>' +
        '<div class="action-group redirect-group"><input class="inp-url" placeholder="URL" value="' + escapeHtml(urlVal) + '"><button class="action-button btn-redirect">Redirect</button></div>' +
        '<div class="action-group image-group"><input type="file" class="inp-img"><button class="action-button btn-img">Image</button></div>' +
        '<div class="action-group message-group"><input class="inp-msg" placeholder="Message" value="' + escapeHtml(msgVal) + '"><button class="action-button btn-msg">Message</button></div>' +
        '<div class="action-group clear-group"><button class="action-button btn-clear-cookies" title="Ask this client to clear its cookies and reload">Clear Cookies</button></div>' +
        '<div class="action-group question-group"><input class="inp-question" placeholder="Yes/No question" value="' + escapeHtml(questionVal) + '"><button class="action-button btn-question">Ask</button> <button class="action-button btn-clear-question">Clear Ask</button></div>' +
        '<div class="action-group timeout-group">' + (data.timeout_active ? '<button class="action-button btn-untimeout">Untimeout</button>' : '<input class="inp-timeout-duration" placeholder="2m 20s" value="' + escapeHtml(timeoutDurationVal) + '"><input class="inp-timeout-reason" placeholder="Timeout reason" value="' + escapeHtml(timeoutReasonVal) + '"><button class="action-button btn-timeout" ' + (data.banned ? 'disabled' : '') + '>Timeout</button>') + '</div>' +
        '<div class="action-group note-group"><input class="inp-note" placeholder="Note" value="' + escapeHtml(noteVal) + '"><button class="action-button btn-note">Save Note</button></div>' +
        '<div class="action-group effect-group"><select class="inp-effect">' + effectOptionsHtml(effectValue) + '</select><button class="action-button btn-effect">Apply Effect</button> <button class="action-button btn-effect-clear">Reset Effect</button></div>' +
        '<div class="action-group delete-group"><button class="action-button btn-delete">Delete</button></div>' +
        '</div>' +
      '</td>';
    table.appendChild(row);
  });

  document.getElementById('clientStats').textContent = 'Active: ' + activeCount + ' | Banned: ' + bannedCount + ' | Timed Out: ' + timeoutCount + ' | Total: ' + totalCount;
}

function banClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientBan, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function unbanClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientUnban, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
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
  }).then(loadClients);
}

function sendMessage(btn, msg) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!msg) return;
  return fetch(ROUTES.clientMessage, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent(msg),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendClearCookies(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientMessage, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent('__MANGER_CLEAR_COOKIES__'),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() {
    if (typeof sendAudit === 'function') {
      return sendAudit('clear_cookies', user, {}, true);
    }
  }).then(loadClients);
}

function sendRedirect(btn, url) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!url) return;
  return fetch(ROUTES.clientRedirect, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&u=' + encodeRouteValue(url),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendEffect(btn, effect) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientEffect, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&effect=' + encodeURIComponent(effect || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendNote(btn, note) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientNote, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&note=' + encodeURIComponent(note || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendQuestion(btn, question) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientQuestion, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&question=' + encodeURIComponent(question || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendTimeout(btn, duration, reason) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!duration) return;
  return fetch(ROUTES.clientTimeout, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&duration=' + encodeURIComponent(duration) + '&reason=' + encodeURIComponent(reason || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function clearClientTimeout(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientTimeoutClear, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}
