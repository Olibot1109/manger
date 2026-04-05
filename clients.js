var clientState = {
  clients: {},
  filter: 'all',
  sortBy: 'recent',
  autoRefresh: false,
  autoRefreshInterval: null
};

function renderClients(clients) {
  clientState.clients = clients;
  const table = document.getElementById('clientsTable');
  const existingRows = {};
  table.querySelectorAll('tr').forEach(row => {
    const username = row.cells[0]?.textContent;
    if (username) existingRows[username] = row;
  });
  
  let filtered = Object.entries(clients);
  
  if (clientState.filter === 'active') {
    filtered = filtered.filter(([u, d]) => !d.banned && d.recent);
  } else if (clientState.filter === 'banned') {
    filtered = filtered.filter(([u, d]) => d.banned);
  } else if (clientState.filter === 'inactive') {
    filtered = filtered.filter(([u, d]) => !d.recent);
  }
  
  if (clientState.sortBy === 'recent') {
    filtered.sort((a, b) => (b[1].last_ping || '').localeCompare(a[1].last_ping || ''));
  } else if (clientState.sortBy === 'name') {
    filtered.sort((a, b) => a[0].localeCompare(b[0]));
  } else if (clientState.sortBy === 'url') {
    filtered.sort((a, b) => (a[1].current_url || '').localeCompare(b[1].current_url || ''));
  }
  
  const activeCount = Object.values(clients).filter(d => !d.banned && d.recent).length;
  const bannedCount = Object.values(clients).filter(d => d.banned).length;
  const totalCount = Object.keys(clients).length;
  
  table.innerHTML = '<tr><th>Username</th><th>Status</th><th>Last Ping</th><th>Current URL</th><th>Actions</th></tr>';
  
  filtered.forEach(([user, data]) => {
    const row = document.createElement('tr');
    row.className = data.recent ? 'recent' : 'inactive';
    if (data.banned) row.style.backgroundColor = '#ffcccc';
    
    if (existingRows[user]) {
      const actionsCell = existingRows[user].cells[4];
      const urlInput = actionsCell.querySelector('input[class="inp-url"]');
      const msgInput = actionsCell.querySelector('input[class="inp-msg"]');
      const urlVal = urlInput ? urlInput.value : '';
      const msgVal = msgInput ? msgInput.value : '';
      row.setAttribute('data-user', user);
      row.innerHTML = '<td>' + user + '</td>' +
        '<td>' + (data.banned ? '<span style="color:red;font-weight:bold;">BANNED</span>' : (data.recent ? '<span style="color:green;">Active</span>' : 'Inactive')) + '</td>' +
        '<td>' + (data.last_ping || 'Never') + '</td>' +
        '<td>' + (data.current_url ? '<a href="' + data.current_url + '" target="_blank">' + data.current_url + '</a>' : '<span style="color:gray;">Unknown</span>') + '</td>' +
        '<td data-user="' + user + '">' +
          '<button class="btn-ban" ' + (data.banned ? 'disabled' : '') + '>Ban</button> ' +
          '<button class="btn-unban" ' + (!data.banned ? 'disabled' : '') + '>Unban</button> ' +
          '<input class="inp-url" placeholder="URL" value="' + urlVal + '"><button class="btn-redirect">Redirect</button> ' +
          '<input type="file" class="inp-img"><button class="btn-img">Image</button> ' +
          '<button class="btn-delete" style="color:white;background-color:red;">Delete</button> ' +
          '<input class="inp-msg" placeholder="Message" value="' + msgVal + '"><button class="btn-msg">Message</button>' +
        '</td></tr>';
    } else {
      row.setAttribute('data-user', user);
      row.innerHTML = '<td>' + user + '</td>' +
        '<td>' + (data.banned ? '<span style="color:red;font-weight:bold;">BANNED</span>' : (data.recent ? '<span style="color:green;">Active</span>' : 'Inactive')) + '</td>' +
        '<td>' + (data.last_ping || 'Never') + '</td>' +
        '<td>' + (data.current_url ? '<a href="' + data.current_url + '" target="_blank">' + data.current_url + '</a>' : '<span style="color:gray;">Unknown</span>') + '</td>' +
        '<td data-user="' + user + '">' +
          '<button class="btn-ban">Ban</button> ' +
          '<button class="btn-unban" disabled>Unban</button> ' +
          '<input class="inp-url" placeholder="URL"><button class="btn-redirect">Redirect</button> ' +
          '<input type="file" class="inp-img"><button class="btn-img">Image</button> ' +
          '<button class="btn-delete" style="color:white;background-color:red;">Delete</button> ' +
          '<input class="inp-msg" placeholder="Message"><button class="btn-msg">Message</button>' +
        '</td></tr>';
    }
    table.appendChild(row);
  });
  
  document.getElementById('clientStats').innerHTML = 'Active: ' + activeCount + ' | Banned: ' + bannedCount + ' | Total: ' + totalCount;
}

function loadClients() {
  fetch('/clients.json').then(r => r.json()).then(renderClients);
}

function banClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  fetch('/clients/ban', {method: 'POST', body: 'username=' + encodeURIComponent(user), headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(loadClients);
}

function unbanClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  fetch('/clients/unban', {method: 'POST', body: 'username=' + encodeURIComponent(user), headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(loadClients);
}

function deleteClient(btn) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!confirm('Delete ' + user + '?')) return;
  fetch('/clients/delete', {method: 'POST', body: 'username=' + encodeURIComponent(user), headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(loadClients);
}

function sendMessage(btn, msg) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!msg) return;
  fetch('/clients/message', {method: 'POST', body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent(msg), headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(loadClients);
}

function sendRedirect(btn, url) {
  var user = btn.closest('td').getAttribute('data-user');
  if (!url) return;
  fetch('/clients/redirect', {method: 'POST', body: 'username=' + encodeURIComponent(user) + '&url=' + encodeURIComponent(url), headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(loadClients);
}

function banAllActive() {
  if (!confirm('Ban all active clients?')) return;
  Object.entries(clientState.clients).forEach(([user, data]) => {
    if (data.recent && !data.banned) {
      fetch('/clients/ban', {method: 'POST', body: 'username=' + encodeURIComponent(user), headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
    }
  });
  setTimeout(loadClients, 500);
}

function unbanAll() {
  if (!confirm('Unban all clients?')) return;
  Object.entries(clientState.clients).forEach(([user, data]) => {
    if (data.banned) {
      fetch('/clients/unban', {method: 'POST', body: 'username=' + encodeURIComponent(user), headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
    }
  });
  setTimeout(loadClients, 500);
}

function deleteAll() {
  if (!confirm('Delete ALL clients? This cannot be undone!')) return;
  Object.keys(clientState.clients).forEach(user => {
    fetch('/clients/delete', {method: 'POST', body: 'username=' + encodeURIComponent(user), headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
  });
  setTimeout(loadClients, 500);
}

function toggleAutoRefresh() {
  clientState.autoRefresh = !clientState.autoRefresh;
  var btn = document.getElementById('btn-auto');
  if (clientState.autoRefresh) {
    btn.textContent = 'Stop Auto';
    btn.style.backgroundColor = 'red';
    clientState.autoRefreshInterval = setInterval(loadClients, 3000);
  } else {
    btn.textContent = 'Auto Refresh';
    btn.style.backgroundColor = '';
    clearInterval(clientState.autoRefreshInterval);
  }
}

function lockdown(url) {
  var targetUrl = url || 'https://www.google.com';
  if (!confirm('LOCKDOWN: Redirect all to ' + targetUrl + '?')) return;
  Object.entries(clientState.clients).forEach(([user, data]) => {
    fetch('/clients/redirect', {method: 'POST', body: 'username=' + encodeURIComponent(user) + '&url=' + encodeURIComponent(targetUrl), headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
  });
  setTimeout(loadClients, 500);
}

function lockdownGoogle() {
  lockdown('https://www.google.com');
}

function toggleLockdown(url) {
  var targetUrl = url || 'https://www.google.com';
  fetch('/lockdown', {method: 'POST', body: 'action=on&url=' + encodeURIComponent(targetUrl), headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(r => r.json()).then(d => {
    loadClients();
    updateLockdownBtn();
  });
}

function disableLockdown() {
  fetch('/lockdown', {method: 'POST', body: 'action=off', headers: {'Content-Type': 'application/x-www-form-urlencoded'}}).then(r => r.json()).then(d => {
    loadClients();
    updateLockdownBtn();
  });
}

function updateLockdownBtn() {
  fetch('/lockdown.json').then(r => r.json()).then(d => {
    var btn = document.getElementById('btn-lockdown');
    if (d.active) {
      btn.textContent = 'UNLOCK';
      btn.style.backgroundColor = 'green';
    } else {
      btn.textContent = 'LOCKDOWN';
      btn.style.backgroundColor = '#ff00ff';
    }
  });
}

loadClients();
updateLockdownBtn();

document.getElementById('clientsTable').addEventListener('click', function(e) {
  var btn = e.target;
  var td = btn.closest('td');
  if (!td) return;
  var user = td.getAttribute('data-user');
  if (!user) return;
  
  if (btn.classList.contains('btn-ban')) {
    banClient(btn);
  } else if (btn.classList.contains('btn-unban')) {
    unbanClient(btn);
  } else if (btn.classList.contains('btn-delete')) {
    deleteClient(btn);
  } else if (btn.classList.contains('btn-redirect')) {
    var url = td.querySelector('.inp-url').value;
    sendRedirect(btn, url);
  } else if (btn.classList.contains('btn-msg')) {
    var msg = td.querySelector('.inp-msg').value;
    sendMessage(btn, msg);
  } else if (btn.classList.contains('btn-img')) {
    var f = td.querySelector('.inp-img').files[0];
    if (f) {
      var fd = new FormData();
      fd.append('username', user);
      fd.append('image_file', f);
      fetch('/clients/image', {method: 'POST', body: fd}).then(loadClients);
    }
  }
});

document.getElementById('filterSelect')?.addEventListener('change', function(e) {
  clientState.filter = e.target.value;
  loadClients();
});

document.getElementById('sortSelect')?.addEventListener('change', function(e) {
  clientState.sortBy = e.target.value;
  loadClients();
});
