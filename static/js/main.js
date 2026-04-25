// Main initialization

function init() {
  // Initialize UI
  initTableListeners();
  initFilterSortListeners();
  updateAuthStatus();

  // Sync the server session in the background and keep it fresh.
  if (typeof bootstrapAuthState === 'function') {
    bootstrapAuthState().then(function() {
      if (!isSessionValid()) {
        loadClients().catch(function() {});
      }
    }).catch(function() {});
    setInterval(function() {
      refreshAuthState(true).catch(function() {});
    }, 30000);
  } else {
    loadClients().catch(function() {});
  }

  updateLockdownBtn();
  setInterval(updateLockdownBtn, 30000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
