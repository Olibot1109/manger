// Bulk actions

function deleteAll() {
  if (!pass('deleteAll')) return;
  if (!confirm('Delete ALL clients? This cannot be undone!')) return;
  var performer = authSession.currentLabel || '';
  Promise.all(Object.keys(clientState.clients).map(function(user) {
    return fetch(ROUTES.clientDelete, {
      method: 'POST',
      body: 'username=' + encodeURIComponent(user) + '&performer=' + encodeURIComponent(performer),
      headers: {'Content-Type': 'application/x-www-form-urlencoded'}
    });
  })).then(function() {
    if (typeof sendAudit === 'function') {
      sendAudit('delete_all', 'system', {count: Object.keys(clientState.clients).length}, true);
    }
  }).then(loadClients);
}

function redirectAllActive() {
  if (!pass('redirectAll')) return;
  var url = prompt("Enter URL to redirect all active clients to:", "https://example.com");
  if (!url) return;

  var performer = authSession.currentLabel || '';
  fetch(ROUTES.clientsJson).then(r => r.json()).then(function(clients) {
    var promises = [];
    var activeCount = 0;
    for (var [user, data] of Object.entries(clients)) {
      if (data.recent) {
        activeCount++;
        promises.push(fetch(ROUTES.clientRedirect, {
          method: 'POST',
          body: 'username=' + encodeURIComponent(user) + '&u=' + encodeRouteValue(url) + '&performer=' + encodeURIComponent(performer),
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

function messageAllActive() {
  if (!pass('messageAll')) return;
  var msg = prompt("Enter message to send to all active clients:");
  if (!msg) return;

  var performer = authSession.currentLabel || '';
  fetch(ROUTES.clientsJson).then(r => r.json()).then(function(clients) {
    var promises = [];
    var activeCount = 0;
    for (var [user, data] of Object.entries(clients)) {
      if (data.recent) {
        activeCount++;
        promises.push(fetch(ROUTES.clientMessage, {
          method: 'POST',
          body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent(msg) + '&performer=' + encodeURIComponent(performer),
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

function askAllActive() {
  if (!pass('askAll')) return;
  var question = prompt("Enter question to ask all active clients:");
  if (!question) return;
  if (!confirm("Ask all active clients this question?\n\n" + question)) return;

  var performer = authSession.currentLabel || '';
  fetch(ROUTES.clientsJson).then(r => r.json()).then(function(clients) {
    var promises = [];
    var activeCount = 0;
    for (var [user, data] of Object.entries(clients)) {
      if (data.recent) {
        activeCount++;
        promises.push(fetch(ROUTES.clientQuestion, {
          method: 'POST',
          body: 'username=' + encodeURIComponent(user) + '&question=' + encodeURIComponent(question) + '&performer=' + encodeURIComponent(performer),
          headers: {'Content-Type': 'application/x-www-form-urlencoded'}
        }));
      }
    }
    Promise.all(promises).then(function() {
      if (typeof sendAudit === 'function') {
        sendAudit('question_all', 'system', {question: question, count: activeCount}, true);
      }
    }).then(loadClients);
  });
}

function showIdAllClients() {
  if (!pass('showIdAll')) return;
  if (!confirm("Show each client's ID on their screen for 5 seconds?")) return;

  var performer = authSession.currentLabel || '';
  fetch(ROUTES.clientsJson).then(r => r.json()).then(function(clients) {
    var promises = [];
    var activeCount = 0;
    for (var [user, data] of Object.entries(clients)) {
      if (data.recent) {
        activeCount++;
        promises.push(fetch(ROUTES.clientMessage, {
          method: 'POST',
          body: 'username=' + encodeURIComponent(user) + '&message=' + encodeURIComponent('Your ID: ' + user) + '&performer=' + encodeURIComponent(performer),
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

function sendImageFileToAllActive(input) {
  if (!pass('sendImageAll')) return;
  var f = input.files[0];
  if (!f) return;
  if (!confirm("Send this image to all active clients?")) return;

  var reader = new FileReader();
  var performer = authSession.currentLabel || '';
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
            body: 'username=' + encodeURIComponent(user) + '&image=' + encodeURIComponent(base64) + '&performer=' + encodeURIComponent(performer),
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
