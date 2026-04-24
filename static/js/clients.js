// Client management functions

function loadClients() {
  var current = ++requestSeq;
  return fetch(ROUTES.clientsJson + '?_=' + Date.now(), { cache: 'no-store' })
    .then(function(r) {
      if (!r.ok) throw new Error('Failed to load clients');
      return r.json();
    })
    .then(function(data) {
      if (current !== requestSeq) return data;
      renderClients(data);
      return data;
    })
    .catch(function(err) {
      console.error(err);
      if (current === requestSeq) {
        var stats = document.getElementById('clientStats');
        if (stats) stats.textContent = 'Unable to load clients';
      }
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
    row.className = data.recent ? 'recent' : 'inactive';
    var statusText = '';

    var statusInfo = '';
    var statusBg = '';
    if (data.banned) {
      statusInfo = '<span style="color:blue;font-weight:bold;">Banned</span>';
      statusBg = '#ccddff';
    } else if (data.timeout_active) {
      statusInfo = '<span style="color:orange;font-weight:bold;">Timeout ' + formatDurationLabel(data.timeout_remaining_seconds || 0) + '</span>';
      statusBg = '#ffe4b5';
    }
    if (statusInfo) {
      var onlineStatus = data.recent ? 'Online' : 'Offline';
      statusText = '<span style="color:' + (data.recent ? 'green' : 'gray') + ';">' + onlineStatus + '</span> (' + statusInfo + ')';
      row.style.backgroundColor = statusBg;
    } else {
      statusText = (data.recent ? '<span style="color:green;">Active</span>' : 'Inactive');
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
      '<td>' + (data.current_url ? '<a href="' + escapeHtml(data.current_url) + '" target="_blank">' + escapeHtml(data.current_url) + '</a>' : '<span style="color:gray;">Unknown</span>') + '</td>' +
      '<td>' + escapeHtml(effectLabel(data.effect || '')) + '</td>' +
      '<td>' + (data.question ? escapeHtml(data.question) : '<span style="color:gray;">None</span>') + '</td>' +
      '<td>' + (answerVal ? '<strong>' + escapeHtml(answerVal) + '</strong>' : '<span style="color:gray;">Pending</span>') + '</td>' +
      '<td data-user="' + escapeHtml(user) + '">' +
        '<div class="action-group ban-group" style="background-color: #ffcccc;"><button class="btn-toggle-ban" style="background-color:#ff4444;color:white;" ' + (data.timeout_active ? 'disabled' : '') + '>' + (data.banned ? 'Unban' : 'Ban') + '</button></div>' +
        '<div class="action-group redirect-group" style="background-color: #cce5ff;"><input class="inp-url" placeholder="URL" value="' + escapeHtml(urlVal) + '"><button class="btn-redirect" style="background-color:#0066cc;color:white;">Redirect</button></div>' +
        '<div class="action-group image-group" style="background-color: #e6ccff;"><input type="file" class="inp-img"><button class="btn-img" style="background-color:#9900cc;color:white;">Image</button></div>' +
        '<div class="action-group message-group" style="background-color: #ccffcc;"><input class="inp-msg" placeholder="Message" value="' + escapeHtml(msgVal) + '"><button class="btn-msg" style="background-color:#00cc00;color:white;">Message</button></div>' +
        '<div class="action-group question-group" style="background-color: #ffe0cc;"><input class="inp-question" placeholder="Yes/No question" value="' + escapeHtml(questionVal) + '"><button class="btn-question" style="background-color:#cc6600;color:white;">Ask</button> <button class="btn-clear-question" style="background-color:#cc9933;color:white;">Clear Ask</button></div>' +
        '<div class="action-group timeout-group" style="background-color: #ffcccc;">' + (data.timeout_active ? '<button class="btn-untimeout" style="background-color:#cc0066;color:white;">Untimeout</button>' : '<input class="inp-timeout-duration" placeholder="2m 20s" value="' + escapeHtml(timeoutDurationVal) + '"><input class="inp-timeout-reason" placeholder="Timeout reason" value="' + escapeHtml(timeoutReasonVal) + '"><button class="btn-timeout" style="background-color:#cc0066;color:white;" ' + (data.banned ? 'disabled' : '') + '>Timeout</button>') + '</div>' +
        '<div class="action-group note-group" style="background-color: #ccffcc;"><input class="inp-note" placeholder="Note" value="' + escapeHtml(noteVal) + '"><button class="btn-note" style="background-color:#009900;color:white;">Save Note</button></div>' +
        '<div class="action-group effect-group" style="background-color: #e6ccff;"><select class="inp-effect">' + effectOptionsHtml(effectValue) + '</select><button class="btn-effect" style="background-color:#6600cc;color:white;">Apply Effect</button> <button class="btn-effect-clear" style="background-color:#9966cc;color:white;">Reset Effect</button></div>' +
        '<div class="action-group delete-group" style="background-color: #ffcccc;"><button class="btn-delete" style="background-color:#cc0000;color:white;">Delete</button></div>' +
      '</td>';
    table.appendChild(row);
  });

  document.getElementById('clientStats').textContent = 'Active: ' + activeCount + ' | Banned: ' + bannedCount + ' | Timed Out: ' + timeoutCount + ' | Total: ' + totalCount;
}

function banClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  var body = 'username=' + encodeURIComponent(user) + '&performer=' + encodeURIComponent(authSession.currentLabel || '');
  return fetch(ROUTES.clientBan, {method: 'POST', body: body, headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(loadClients);
}

function unbanClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  var body = 'username=' + encodeURIComponent(user) + '&performer=' + encodeURIComponent(authSession.currentLabel || '');
  return fetch(ROUTES.clientUnban, {method: 'POST', body: body, headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(loadClients);
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
    body: 'username=' + encodeURIComponent(user) + '&performer=' + encodeURIComponent(authSession.currentLabel || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendMessage(btn, msg) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!msg) return;
  return fetch(ROUTES.clientMessage, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent(msg) + '&performer=' + encodeURIComponent(authSession.currentLabel || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendRedirect(btn, url) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!url) return;
  return fetch(ROUTES.clientRedirect, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&u=' + encodeRouteValue(url) + '&performer=' + encodeURIComponent(authSession.currentLabel || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendEffect(btn, effect) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientEffect, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&effect=' + encodeURIComponent(effect || '') + '&performer=' + encodeURIComponent(authSession.currentLabel || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendNote(btn, note) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientNote, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&note=' + encodeURIComponent(note || '') + '&performer=' + encodeURIComponent(authSession.currentLabel || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendQuestion(btn, question) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientQuestion, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&question=' + encodeURIComponent(question || '') + '&performer=' + encodeURIComponent(authSession.currentLabel || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function sendTimeout(btn, duration, reason) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!duration) return;
  return fetch(ROUTES.clientTimeout, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&duration=' + encodeURIComponent(duration) + '&reason=' + encodeURIComponent(reason || '') + '&performer=' + encodeURIComponent(authSession.currentLabel || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}

function clearClientTimeout(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  return fetch(ROUTES.clientTimeoutClear, {
    method: 'POST',
    body: 'username=' + encodeURIComponent(user) + '&performer=' + encodeURIComponent(authSession.currentLabel || ''),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(loadClients);
}
