// Bulk actions

async function deleteAll() {
  if (!(await pass('deleteAll'))) return;
  if (!confirm('Delete ALL clients? This cannot be undone!')) return;
  Promise.all(Object.keys(clientState.clients).map(function(user) {
    return fetch(ROUTES.clientDelete, {
      method: 'POST',
      body: 'username=' + encodeURIComponent(user),
      headers: {'Content-Type': 'application/x-www-form-urlencoded'}
    });
  })).then(function() {
    if (typeof sendAudit === 'function') {
      sendAudit('delete_all', 'system', {count: Object.keys(clientState.clients).length}, true);
    }
  }).then(loadClients);
}

async function redirectAllActive() {
  if (!(await pass('redirectAll'))) return;
  var url = prompt("Enter URL to redirect all active clients to:", "https://example.com");
  if (!url) return;

  fetch(ROUTES.clientsJson).then(r => r.json()).then(function(clients) {
    var promises = [];
    var activeCount = 0;
    for (var [user, data] of Object.entries(clients)) {
      if (data.recent) {
        activeCount++;
        promises.push(fetch(ROUTES.clientRedirect, {
          method: 'POST',
          body: 'username=' + encodeURIComponent(user) + '&u=' + encodeRouteValue(url),
          headers: {'Content-Type': 'application/x-www-form-urlencoded'}
        }));
      }
    }
    Promise.all(promises).then(function() {
      if (typeof sendAudit === 'function') {
        sendAudit('redirect_all', 'system', {url: url, count: activeCount}, true);
      }
    }).then(loadClients);
  });
}

async function messageAllActive() {
  if (!(await pass('messageAll'))) return;
  var msg = prompt("Enter message to send to all active clients:");
  if (!msg) return;

  fetch(ROUTES.clientsJson).then(r => r.json()).then(function(clients) {
    var promises = [];
    var activeCount = 0;
    for (var [user, data] of Object.entries(clients)) {
      if (data.recent) {
        activeCount++;
        promises.push(fetch(ROUTES.clientMessage, {
          method: 'POST',
          body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent(msg),
          headers: {'Content-Type': 'application/x-www-form-urlencoded'}
        }));
      }
    }
    Promise.all(promises).then(function() {
      if (typeof sendAudit === 'function') {
        sendAudit('message_all', 'system', {message_len: msg.length, count: activeCount}, true);
      }
    }).then(loadClients);
  });
}

async function showIdAllClients() {
  if (!(await pass('showIdAll'))) return;
  if (!confirm("Show each client's ID on their screen for 5 seconds?")) return;

  fetch(ROUTES.clientsJson).then(r => r.json()).then(function(clients) {
    var promises = [];
    var activeCount = 0;
    for (var [user, data] of Object.entries(clients)) {
      if (data.recent) {
        activeCount++;
        promises.push(fetch(ROUTES.clientMessage, {
          method: 'POST',
          body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent('Your ID: ' + user),
          headers: {'Content-Type': 'application/x-www-form-urlencoded'}
        }));
      }
    }
    Promise.all(promises).then(function() {
      if (typeof sendAudit === 'function') {
        sendAudit('show_id_all', 'system', {count: activeCount}, true);
      }
    }).then(loadClients);
  });
}

async function sendImageFileToAllActive(input) {
  if (!(await pass('sendImageAll'))) return;
  var f = input.files[0];
  if (!f) return;
  if (!confirm("Send this image to all active clients?")) return;

  var reader = new FileReader();
  reader.onload = function(e) {
    var base64 = e.target.result;
    fetch(ROUTES.clientsJson).then(r => r.json()).then(function(clients) {
      var promises = [];
      var activeCount = 0;
      for (var [user, data] of Object.entries(clients)) {
        if (data.recent) {
          activeCount++;
          promises.push(fetch(ROUTES.clientImage, {
            method: 'POST',
            body: 'username=' + encodeURIComponent(user) + '&image=' + encodeURIComponent(base64),
            headers: {'Content-Type': 'application/x-www-form-urlencoded'}
          }));
        }
      }
      Promise.all(promises).then(function() {
        if (typeof sendAudit === 'function') {
          sendAudit('image_all', 'system', {filename: f.name, size: f.size, count: activeCount}, true);
        }
      }).then(loadClients);
    });
  };
  reader.readAsDataURL(f);
}
