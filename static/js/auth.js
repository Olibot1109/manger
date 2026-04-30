// Authentication state and UI

var authSession = {
  authenticated: false,
  currentLabel: null,
  admin: false,
  currentPermissions: {
    admin: false,
    mode: 'deny',
    allowedActions: [],
    deniedActions: []
  },
  loginTime: null,
  sessionFingerprint: null
};

var authRefreshPromise = null;
var activePasswordDialog = null;

function clonePermissionsFromSession(payload) {
  return {
    admin: !!(payload && payload.admin),
    mode: payload && payload.mode ? payload.mode : 'deny',
    allowedActions: Array.isArray(payload && payload.allowedActions) ? payload.allowedActions.slice() : [],
    deniedActions: Array.isArray(payload && payload.deniedActions) ? payload.deniedActions.slice() : []
  };
}

function applyAuthState(payload) {
  if (!payload || !payload.authenticated) {
    authSession.authenticated = false;
    authSession.currentLabel = null;
    authSession.admin = false;
    authSession.currentPermissions = {
      admin: false,
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
  authSession.admin = !!payload.admin;
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
  if (authSession.admin) return true;
  var perms = authSession.currentPermissions || {};
  if (perms.admin) return true;
  var allowedActions = Array.isArray(perms.allowedActions) ? perms.allowedActions : [];
  var deniedActions = Array.isArray(perms.deniedActions) ? perms.deniedActions : [];
  if (perms.mode === "allow") {
    return allowedActions.length > 0 && allowedActions.indexOf(actionName) !== -1;
  }
  return deniedActions.indexOf(actionName) === -1;
}

function showPasswordDialog(options) {
  options = options || {};

  if (activePasswordDialog && activePasswordDialog.promise) {
    return activePasswordDialog.promise;
  }

  var resolveDialog;
  var dialogPromise = new Promise(function(resolve) {
    resolveDialog = resolve;
  });

  activePasswordDialog = {
    overlay: null,
    promise: dialogPromise
  };

  (function() {
    var existing = document.getElementById('passwordPromptOverlay');
    if (existing) {
      existing.remove();
    }

    var overlay = document.createElement('div');
    overlay.className = 'password-modal-overlay';
    overlay.id = 'passwordPromptOverlay';
    overlay.innerHTML =
      '<div class="password-modal" role="dialog" aria-modal="true" aria-labelledby="passwordPromptTitle" aria-describedby="passwordPromptMessage">' +
        '<h3 id="passwordPromptTitle">' + escapeHtml(options.title || 'Enter Password') + '</h3>' +
        '<p id="passwordPromptMessage">' + escapeHtml(options.message || 'Enter password:') + '</p>' +
        '<form class="password-modal-form">' +
          '<input type="password" class="password-modal-input" autocomplete="current-password" autocapitalize="off" spellcheck="false" required>' +
          '<div class="password-modal-actions">' +
            '<button type="button" class="password-modal-cancel">Cancel</button>' +
            '<button type="submit" class="password-modal-submit">' + escapeHtml(options.submitLabel || 'OK') + '</button>' +
          '</div>' +
        '</form>' +
      '</div>';

    var resolved = false;
    var previousActiveElement = document.activeElement;

    var cleanup = function(value) {
      if (resolved) return;
      resolved = true;

      if (overlay && overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('visibilitychange', onVisibilityChange, true);
      window.removeEventListener('pagehide', onPageHide, true);
      document.body.classList.remove('password-modal-open');

      if (previousActiveElement && typeof previousActiveElement.focus === 'function') {
        try {
          previousActiveElement.focus();
        } catch (e) {}
      }

      if (activePasswordDialog && activePasswordDialog.overlay === overlay) {
        activePasswordDialog = null;
      }

      resolveDialog(value);
    };

    var onKeyDown = function(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        cleanup(null);
      }
    };

    var onVisibilityChange = function() {
      if (document.hidden) {
        cleanup(null);
      }
    };

    var onPageHide = function() {
      cleanup(null);
    };

    var form = overlay.querySelector('.password-modal-form');
    var input = overlay.querySelector('.password-modal-input');
    var cancelBtn = overlay.querySelector('.password-modal-cancel');
    var submitBtn = overlay.querySelector('.password-modal-submit');

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var value = input.value;
      cleanup(value);
    });

    cancelBtn.addEventListener('click', function() {
      cleanup(null);
    });

    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) {
        cleanup(null);
      }
    });

    activePasswordDialog.overlay = overlay;

    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('visibilitychange', onVisibilityChange, true);
    window.addEventListener('pagehide', onPageHide, true);
    document.body.classList.add('password-modal-open');
    document.body.appendChild(overlay);
    requestAnimationFrame(function() {
      try {
        input.focus();
        if (typeof input.setSelectionRange === 'function') {
          input.setSelectionRange(0, input.value.length);
        }
      } catch (e) {}
    });
    submitBtn.type = 'submit';
  })();

  return dialogPromise;
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

  var userInput = await showPasswordDialog({
    title: 'Sign In',
    message: 'Enter password:'
  });
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
    var adminBadge = authSession.admin ? '<span class="auth-badge auth-badge-admin">Admin</span>' : '';
    el.innerHTML =
      '<span class="auth-label">Logged in as ' +
      label +
      '</span>' +
      adminBadge +
      ' <button class="auth-logout" onclick="logout()">Logout</button>';
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

  var userInput = await showPasswordDialog({
    title: 'Authentication Required',
    message: 'Enter password to perform this action:'
  });
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
