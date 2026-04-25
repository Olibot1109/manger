// Server auth transport helpers

var AUTH_ROUTES = Object.freeze({
  login: '/auth/login',
  logout: '/auth/logout',
  session: '/auth/session'
});

function parseJsonResponse(response) {
  return response.text().then(function(text) {
    var data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = { raw: text };
      }
    }
    return { ok: response.ok, status: response.status, data: data };
  });
}

function requestAuthSession() {
  return fetch(AUTH_ROUTES.session, {
    cache: 'no-store',
    credentials: 'same-origin'
  }).then(parseJsonResponse);
}

function requestAuthLogin(password) {
  return fetch(AUTH_ROUTES.login, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: password })
  }).then(parseJsonResponse);
}

function requestAuthLogout() {
  return fetch(AUTH_ROUTES.logout, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin'
  }).then(parseJsonResponse);
}
