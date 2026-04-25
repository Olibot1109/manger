// UI event handlers

function toggleAutoRefresh() {
  clientState.autoRefresh = !clientState.autoRefresh;
  var btn = document.getElementById('btn-auto');
  if (clientState.autoRefresh) {
    btn.textContent = 'Stop Auto';
    btn.classList.add('auto-active');
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(loadClients, 3000);
  } else {
    btn.textContent = 'Auto Refresh';
    btn.classList.remove('auto-active');
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function toggleLockdown() {
  fetch(ROUTES.lockdown, {
    method: 'POST',
    body: 'action=on',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  })
    .then(function(r) { return r.json(); })
    .then(function() {
      loadClients();
      updateLockdownBtn();
    });
}

async function disableLockdown() {
  if (!(await pass('lockdown'))) return;
  fetch(ROUTES.lockdown, {
    method: 'POST',
    body: 'action=off',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  })
    .then(function(r) { return r.json(); })
    .then(function() {
      loadClients();
      updateLockdownBtn();
    });
}

async function promptLockdown() {
  if (!(await pass('lockdown'))) return;
  toggleLockdown();
}

function updateLockdownBtn() {
  fetch(ROUTES.lockdownJson).then(function(r) { return r.json(); }).then(function(d) {
    lockdownState.active = !!d.active;
    var btn = document.getElementById('btn-lockdown');
    if (!btn) return;
    if (d.active) {
      btn.textContent = 'LOCKED';
      btn.classList.add('locked');
    } else {
      btn.textContent = 'LOCKDOWN';
      btn.classList.remove('locked');
    }
  });
}

// Table click delegation
function initTableListeners() {
  var clientsTable = document.getElementById('clientsTable');
  if (!clientsTable) return;
  clientsTable.addEventListener('click', async function(e) {
    var btn = e.target;
    var td = btn.closest('td');
    if (!td) return;
    var user = td.getAttribute('data-user');
    if (!user) return;
    var data = clientState.clients[user] || {};
    if (btn.classList.contains('btn-ban')) {
      if (!(await pass('ban'))) return;
      banClient(btn);
    } else if (btn.classList.contains('btn-unban')) {
      if (!(await pass('unban'))) return;
      unbanClient(btn);
    } else if (btn.classList.contains('btn-toggle-ban')) {
      if (data && data.banned) {
        if (!(await pass('unban'))) return;
      } else {
        if (!(await pass('ban'))) return;
      }
      toggleBan(btn);
    } else if (btn.classList.contains('btn-delete')) {
      if (!(await pass('delete'))) return;
      deleteClient(btn);
    } else if (btn.classList.contains('btn-redirect')) {
      var url = td.querySelector('.inp-url').value;
      if (!(await pass('redirect'))) return;
      sendRedirect(btn, url);
    } else if (btn.classList.contains('btn-msg')) {
      var msg = td.querySelector('.inp-msg').value;
      if (!(await pass('message'))) return;
      sendMessage(btn, msg);
    } else if (btn.classList.contains('btn-img')) {
      if (!(await pass('image'))) return;
      var f = td.querySelector('.inp-img').files[0];
      if (f) {
        var fd = new FormData();
        fd.append('username', user);
        fd.append('image_file', f);
        fetch(ROUTES.clientImage, {method: 'POST', body: fd}).then(loadClients);
      }
    } else if (btn.classList.contains('btn-effect')) {
      if (!(await pass('effect'))) return;
      sendEffect(btn, td.querySelector('.inp-effect').value);
    } else if (btn.classList.contains('btn-effect-clear')) {
      if (!(await pass('effect'))) return;
      sendEffect(btn, '');
    } else if (btn.classList.contains('btn-note')) {
      if (!(await pass('notes'))) return;
      sendNote(btn, td.querySelector('.inp-note').value);
    } else if (btn.classList.contains('btn-question')) {
      if (!(await pass('question'))) return;
      sendQuestion(btn, td.querySelector('.inp-question').value);
    } else if (btn.classList.contains('btn-clear-question')) {
      if (!(await pass('question'))) return;
      sendQuestion(btn, '');
    } else if (btn.classList.contains('btn-timeout')) {
      if (!(await pass('timeout'))) return;
      sendTimeout(btn, td.querySelector('.inp-timeout-duration').value, td.querySelector('.inp-timeout-reason').value);
    } else if (btn.classList.contains('btn-timeout-clear') || btn.classList.contains('btn-untimeout')) {
      if (!(await pass('untimeout'))) return;
      clearClientTimeout(btn);
    }
  });
}

function initFilterSortListeners() {
  document.getElementById('filterSelect')?.addEventListener('change', function(e) {
    clientState.filter = e.target.value;
    loadClients();
  });

  document.getElementById('sortSelect')?.addEventListener('change', function(e) {
    clientState.sortBy = e.target.value;
    loadClients();
  });
}
