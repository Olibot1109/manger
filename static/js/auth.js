// Authentication state and UI

var authSession = {
  authenticated: false,
  currentLabel: null,
  currentPermissions: {
    mode: 'deny',
    allowedActions: [],
    deniedActions: []
  },
  loginTime: null,
  sessionFingerprint: null
};

var authRefreshPromise = null;

function clonePermissionsFromSession(payload) {
  return {
    mode: payload && payload.mode ? payload.mode : 'deny',
    allowedActions: Array.isArray(payload && payload.allowedActions) ? payload.allowedActions.slice() : [],
    deniedActions: Array.isArray(payload && payload.deniedActions) ? payload.deniedActions.slice() : []
  };
}

function applyAuthState(payload) {
  if (!payload || !payload.authenticated) {
    authSession.authenticated = false;
    authSession.currentLabel = null;
    authSession.currentPermissions = {
      mode: 'deny',
      allowedActions: [],
      deniedActions: []
    };
    authSession.loginTime = null;
    authSession.sessionFingerprint = null;
    return authSession;
  }

  authSession.authenticated = true;
  authSession.currentLabel = payload.label || null;
  authSession.currentPermissions = clonePermissionsFromSession(payload);
  authSession.loginTime = payload.loginAt ? payload.loginAt * 1000 : Date.now();
  authSession.sessionFingerprint = payload.fingerprint || null;
  return authSession;
}

function isSessionValid() {
  return !!authSession.authenticated;
}

function isActionAllowed(actionName) {
  if (!authSession.authenticated) return false;
  var perms = authSession.currentPermissions || {};
  var allowedActions = Array.isArray(perms.allowedActions) ? perms.allowedActions : [];
  var deniedActions = Array.isArray(perms.deniedActions) ? perms.deniedActions : [];
  if (perms.mode === "allow") {
    return allowedActions.length > 0 && allowedActions.indexOf(actionName) !== -1;
  }
  return deniedActions.indexOf(actionName) === -1;
}

async function refreshAuthState(force) {
  if (authRefreshPromise) return authRefreshPromise;
  var wasAuthenticated = authSession.authenticated;

  authRefreshPromise = (async function() {
    try {
      var result = await requestAuthSession();
      if (result.ok && result.data && result.data.authenticated) {
        applyAuthState(result.data);
      } else if (result.ok || result.status === 401) {
        applyAuthState(null);
      }
    } catch (err) {
      console.warn('Auth refresh failed:', err);
    } finally {
      authRefreshPromise = null;
      updateAuthStatus();
    }
    if (wasAuthenticated !== authSession.authenticated && typeof loadClients === 'function') {
      loadClients().catch(function() {});
    }
    if (typeof updateLockdownBtn === 'function') {
      updateLockdownBtn();
    }
    return authSession;
  })();

  return authRefreshPromise;
}

async function bootstrapAuthState() {
  return refreshAuthState(true);
}

async function loginWithPassword(password) {
  var result = await requestAuthLogin(password);
  if (!result.ok) {
    if (result.status === 403) {
      return null;
    }
    throw new Error((result.data && result.data.error) || 'Login failed');
  }

  var sessionPayload = (result.data && result.data.session) ? result.data.session : result.data;
  applyAuthState(sessionPayload);
  updateAuthStatus();
  if (typeof loadClients === 'function') {
    loadClients().catch(function() {});
  }
  if (typeof updateLockdownBtn === 'function') {
    updateLockdownBtn();
  }
  return sessionPayload;
}

async function handleManualLogin() {
  await refreshAuthState(true);
  if (authSession.authenticated) {
    updateAuthStatus();
    return true;
  }

  var userInput = prompt('Enter password:');
  if (!userInput) return false;

  try {
    var sessionPayload = await loginWithPassword(userInput);
    if (!sessionPayload) {
      alert('Wrong password.');
      return false;
    }
    return true;
  } catch (err) {
    alert(err && err.message ? err.message : 'Unable to sign in right now.');
    return false;
  }
}

async function logout() {
  try {
    await requestAuthLogout();
  } catch (err) {
    console.warn('Logout request failed:', err);
  }
  applyAuthState(null);
  updateAuthStatus();
  if (typeof loadClients === 'function') {
    loadClients().catch(function() {});
  }
  if (typeof updateLockdownBtn === 'function') {
    updateLockdownBtn();
  }
}

function updateAuthStatus() {
  var el = document.getElementById('auth-bar');
  if (!el) return;

  if (authSession.authenticated && isSessionValid()) {
    el.classList.add('authenticated');
    var label = escapeHtml(authSession.currentLabel || 'Signed in');
    el.innerHTML =
      '<span class="auth-label">Logged in as ' +
      label +
      '</span> <button class="auth-logout" onclick="logout()">Logout</button>';
  } else {
    el.classList.remove('authenticated');
    el.innerHTML =
      '<span class="auth-label">Not logged in</span> <button class="auth-login" onclick="handleManualLogin()">Login</button>';
  }
}

async function pass(actionName) {
  if (!authSession.authenticated) {
    await refreshAuthState(true);
  }

  if (authSession.authenticated && isSessionValid()) {
    if (!isActionAllowed(actionName)) {
      alert('Access Denied: Your account (' + authSession.currentLabel + ') cannot do this.');
      return false;
    }
    return true;
  }

  var userInput = prompt('Enter password to perform this action:');
  if (!userInput) return false;

  try {
    var sessionPayload = await loginWithPassword(userInput);
    if (!sessionPayload) {
      alert('Wrong password.');
      return false;
    }
  } catch (err) {
    alert(err && err.message ? err.message : 'Unable to sign in right now.');
    return false;
  }

  if (!isActionAllowed(actionName)) {
    alert('Authenticated as ' + authSession.currentLabel + ' — but this action is blocked for you.');
    return false;
  }

  return true;
}
