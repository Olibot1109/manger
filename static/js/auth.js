// Authentication system
var PASSWORD_CONFIG = {
  sessionTimeoutMinutes: 0,
  passwords: []
};

var accountsPromise = null;
var accountsLoaded = false;

function loadAccounts() {
  if (accountsPromise) return accountsPromise;
  accountsPromise = new Promise(function(resolve, reject) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/accounts.json', true);
    xhr.onload = function() {
      if (xhr.status === 200) {
        try {
          var accounts = JSON.parse(xhr.responseText);
          PASSWORD_CONFIG.passwords = Array.isArray(accounts) ? accounts : [];
          console.log('Loaded', PASSWORD_CONFIG.passwords.length, 'accounts from accounts.json');
          accountsLoaded = true;
          resolve();
        } catch (e) {
          console.error('JSON parse error:', e);
          accountsLoaded = true;
          reject(e);
        }
      } else {
        console.warn('accounts.json not found (status:', xhr.status, '), using empty password list');
        accountsLoaded = true;
        reject(new Error('HTTP ' + xhr.status));
      }
    };
    xhr.onerror = function() {
      accountsLoaded = true;
      reject(new Error('Network error'));
    };
    xhr.send(null);
  });
  return accountsPromise;
}

function refreshAccounts() {
  accountsPromise = null;
  accountsLoaded = false;
  return loadAccounts();
}

// Start loading accounts immediately
loadAccounts();


var authSession = {
  authenticated: false,
  currentLabel: null,
  currentPermissions: null,
  loginTime: null,
  timer: null,
  accountPassword: null  // Store password hash/identifier to detect changes
};

function isSessionValid() {
  if (!authSession.authenticated) return false;
  if (PASSWORD_CONFIG.sessionTimeoutMinutes <= 0) return true;
  var elapsed = (Date.now() - authSession.loginTime) / 1000 / 60;
  return elapsed < PASSWORD_CONFIG.sessionTimeoutMinutes;
}

function isAccountStillValid() {
  if (!authSession.authenticated || !authSession.accountPassword) return false;
  // Check if the password still exists in loaded accounts
  var stillExists = PASSWORD_CONFIG.passwords.some(function(acc) {
    return acc.password === authSession.accountPassword;
  });
  if (!stillExists) {
    // Account removed or password changed - log out
    logout();
    return false;
  }
  return true;
}

function isActionAllowed(actionName) {
  if (!authSession.authenticated || !isSessionValid()) return false;
  var perms = authSession.currentPermissions;
  if (perms.mode === "allow") {
    if (perms.allowedActions.length === 0) return false;
    return perms.allowedActions.indexOf(actionName) !== -1;
  } else {
    return perms.deniedActions.indexOf(actionName) === -1;
  }
}

function pass(actionName) {
  if (authSession.authenticated && isSessionValid() && isAccountStillValid()) {
    if (!isActionAllowed(actionName)) {
      alert("Access Denied: Your account (" + authSession.currentLabel + ") cannot do this.");
      return false;
    }
    return true;
  }

  var userInput = prompt("Enter password to perform this action:");
  if (!userInput) return false;

  var matched = null;
  for (var i = 0; i < PASSWORD_CONFIG.passwords.length; i++) {
    if (PASSWORD_CONFIG.passwords[i].password === userInput) {
      matched = PASSWORD_CONFIG.passwords[i];
      break;
    }
  }

  if (!matched) {
    // Audit log: failed login attempt
    if (typeof sendAudit === 'function') {
      sendAudit('login_attempt', 'system', {passwordAttempt: userInput.substring(0, 10), reason: 'wrong_password'}, false);
    }
    alert("Wrong password.");
    return false;
  }

  authSession.authenticated = true;
  authSession.currentLabel = matched.label;
  authSession.accountPassword = matched.password;
  authSession.currentPermissions = {
    mode: matched.mode,
    allowedActions: matched.allowedActions.slice(),
    deniedActions: matched.deniedActions.slice()
  };
  authSession.loginTime = Date.now();

  if (authSession.timer) clearTimeout(authSession.timer);
  if (PASSWORD_CONFIG.sessionTimeoutMinutes > 0) {
    authSession.timer = setTimeout(function() {
      authSession.authenticated = false;
      authSession.accountPassword = null;
      alert("Session expired.");
      updateAuthStatus();
    }, PASSWORD_CONFIG.sessionTimeoutMinutes * 60 * 1000);
  }

  if (!isActionAllowed(actionName)) {
    alert("Authenticated as " + matched.label + " — but this action is blocked for you.");
    return false;
  }

  // Audit log: successful login
  if (typeof sendAudit === 'function') {
    sendAudit('login', 'system', {label: matched.label, permissions: matched.mode}, true);
  }

  updateAuthStatus();
  return true;
}

function logout() {
  authSession.authenticated = false;
  authSession.currentLabel = null;
  authSession.currentPermissions = null;
  authSession.loginTime = null;
  if (authSession.timer) clearTimeout(authSession.timer);
  authSession.timer = null;
  try { localStorage.removeItem('manger_auth'); } catch(e) {}
  updateAuthStatus();
  // Also clear audit session cookie
  try {
    fetch('/audit/logout', {method: 'GET', credentials: 'same-origin'}).catch(() => {});
  } catch(e) {}
}

function updateAuthStatus() {
  var el = document.getElementById('auth-bar');
  if (!el) return;
  
  // Check if account still exists (password changed or account removed)
  if (authSession.authenticated) {
    if (!isAccountStillValid()) {
      // Account invalid, already logged out by isAccountStillValid
      el.classList.remove('authenticated');
      el.innerHTML = 'Client Manager | <span class="status-dot"></span> <span class="auth-label">Not logged in</span> <button class="auth-login" onclick="handleManualLogin()">Login</button>';
      return;
    }
  }
  
  if (authSession.authenticated && isSessionValid()) {
    el.classList.add('authenticated');
    var remaining = "";
    if (PASSWORD_CONFIG.sessionTimeoutMinutes > 0) {
      var mins = Math.max(0, Math.round(PASSWORD_CONFIG.sessionTimeoutMinutes - (Date.now() - authSession.loginTime) / 1000 / 60));
      remaining = " (" + mins + "m)";
    }
    el.innerHTML = 'Client Manager | <span class="status-dot"></span> <span class="auth-label">' + escapeHtml(authSession.currentLabel) + remaining + '</span> <button class="auth-logout" onclick="logout()">Logout</button>';
  } else {
    el.classList.remove('authenticated');
    el.innerHTML = 'Client Manager | <span class="status-dot"></span> <span class="auth-label">Not logged in</span> <button class="auth-login" onclick="handleManualLogin()">Login</button>';
  }
}

async function handleManualLogin() {
  // Ensure accounts are loaded before verifying
  if (typeof loadAccounts === 'function' && !accountsLoaded) {
    try {
      await loadAccounts();
    } catch (e) {
      alert('Failed to load accounts. Please try again later.');
      return;
    }
  }

  var userInput = prompt("Enter password:");
  if (!userInput) return;

  var matched = null;
  for (var i = 0; i < PASSWORD_CONFIG.passwords.length; i++) {
    if (PASSWORD_CONFIG.passwords[i].password === userInput) {
      matched = PASSWORD_CONFIG.passwords[i];
      break;
    }
  }

   if (!matched) {
     // Audit log: failed login attempt
     if (typeof sendAudit === 'function') {
       sendAudit('login_attempt', 'system', {passwordAttempt: userInput.substring(0, 10), reason: 'wrong_password'}, false);
     }
     alert("Wrong password.");
     return;
   }

   // Store password for validation on subsequent requests
   authSession.authenticated = true;
   authSession.currentLabel = matched.label;
   authSession.accountPassword = matched.password;
   authSession.currentPermissions = {
     mode: matched.mode,
     allowedActions: matched.allowedActions.slice(),
     deniedActions: matched.deniedActions.slice()
   };
   authSession.loginTime = Date.now();

   if (authSession.timer) clearTimeout(authSession.timer);
   if (PASSWORD_CONFIG.sessionTimeoutMinutes > 0) {
     authSession.timer = setTimeout(function() {
       authSession.authenticated = false;
       alert("Session expired.");
       updateAuthStatus();
     }, PASSWORD_CONFIG.sessionTimeoutMinutes * 60 * 1000);
   }

   // Audit log: successful manual login
   if (typeof sendAudit === 'function') {
     sendAudit('login', 'system', {label: matched.label, permissions: matched.mode}, true);
   }

   try {
    localStorage.setItem('manger_auth', JSON.stringify({
      password: matched.password,
      label: matched.label
    }));
  } catch (e) {}

  updateAuthStatus();
}

function attemptAutoLogin() {
  try {
    var stored = localStorage.getItem('manger_auth');
    if (!stored) return;
    var creds = JSON.parse(stored);
    if (!creds || !creds.password) return;

    // If accounts not loaded yet, skip
    if (!accountsLoaded) {
      console.warn('Auto-login skipped: accounts not loaded yet');
      return;
    }

    var matched = null;
    for (var i = 0; i < PASSWORD_CONFIG.passwords.length; i++) {
      if (PASSWORD_CONFIG.passwords[i].password === creds.password) {
        matched = PASSWORD_CONFIG.passwords[i];
        break;
      }
    }

    if (!matched) {
      // Account removed or password changed - clear stored credentials and log out
      localStorage.removeItem('manger_auth');
      authSession.authenticated = false;
      authSession.currentLabel = null;
      authSession.accountPassword = null;
      updateAuthStatus();
      return;
    }

    authSession.authenticated = true;
    authSession.currentLabel = matched.label;
    authSession.accountPassword = matched.password;
    authSession.currentPermissions = {
      mode: matched.mode,
      allowedActions: matched.allowedActions.slice(),
      deniedActions: matched.deniedActions.slice()
    };
    authSession.loginTime = Date.now();

    if (authSession.timer) clearTimeout(authSession.timer);
    if (PASSWORD_CONFIG.sessionTimeoutMinutes > 0) {
      authSession.timer = setTimeout(function() {
        authSession.authenticated = false;
        authSession.accountPassword = null;
        alert("Session expired.");
        updateAuthStatus();
      }, PASSWORD_CONFIG.sessionTimeoutMinutes * 60 * 1000);
    }

    updateAuthStatus();
    // Audit log: auto-login
    if (typeof sendAudit === 'function') {
      sendAudit('auto_login', 'system', {label: matched.label, permissions: matched.mode}, true);
    }
  } catch (e) {
    console.error('Auto-login error:', e);
  }
}
