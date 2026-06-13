// Main initialization

function init() {
  initTableListeners();
  initFilterSortListeners();
  updateAuthStatus();

  if (typeof bootstrapAuthState === 'function') {
    bootstrapAuthState().then(function() {
      if (!isSessionValid()) {
        loadClients().catch(function() {});
      }
    }).catch(function() {});
    setInterval(function() {
      if (document.visibilityState !== 'visible') return;
      refreshAuthState(true).catch(function() {});
    }, 3000);
  } else {
    loadClients().catch(function() {});
  }

  updateLockdownBtn();
  if (typeof loadPolls === 'function') loadPolls().catch(function() {});

  // When tab becomes visible again, force a fresh fetch immediately
  document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
      _pollInFlight = false;
      loadClients().catch(function() {});
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
