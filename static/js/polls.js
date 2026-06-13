// Poll management — manager side

var _pollsInFlight = false;
var _lastPollsFp = null;

function loadPolls() {
  if (!isSessionValid()) return Promise.resolve();
  if (_pollsInFlight) return Promise.resolve();
  _pollsInFlight = true;
  return fetch(ROUTES.pollsJson, { cache: 'no-store' })
    .then(function(r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    })
    .then(function(data) {
      _pollsInFlight = false;
      renderPolls(data);
      return data;
    })
    .catch(function(err) {
      _pollsInFlight = false;
      console.warn('Polls load failed:', err);
    });
}

function renderPolls(data) {
  var container = document.getElementById('polls-container');
  if (!container) return;

  // Skip entirely if nothing changed
  var fp = JSON.stringify(data);
  if (fp === _lastPollsFp) return;
  _lastPollsFp = fp;

  // Snapshot form inputs before wiping
  var savedQ = (document.getElementById('poll-question') || {}).value || '';
  var savedOpts = [];
  for (var i = 1; i <= 4; i++) {
    savedOpts.push((document.getElementById('poll-opt' + i) || {}).value || '');
  }

  var activeIds = data.active_poll_ids || [];
  var polls = data.polls || {};
  var totalClients = Object.keys(clientState.clients).length;

  var html = '';

  // ── Active polls (one card per active poll) ────────────────────────────
  if (activeIds.length > 0) {
    html += '<div class="poll-section">';
    html += '<div class="poll-section-label">Active Polls (' + activeIds.length + ')</div>';
    activeIds.forEach(function(pid) {
      var activePoll = polls[pid];
      if (!activePoll) return;
      var responses = activePoll.responses || {};
      var totalResponses = Object.keys(responses).length;

      html += '<div class="poll-active-card" style="margin-bottom:10px">';
      html += '<div class="poll-active-question">' + escapeHtml(activePoll.question) + '</div>';

      activePoll.options.forEach(function(opt) {
        var count = 0;
        var voters = [];
        Object.entries(responses).forEach(function(e) {
          if (e[1] === opt) { count++; voters.push(e[0]); }
        });
        var pct = totalResponses > 0 ? Math.round(count / totalResponses * 100) : 0;
        html += '<div class="poll-result-row" title="' + escapeHtml(voters.join(', ') || 'No votes yet') + '">';
        html += '<div class="poll-result-meta">';
        html += '<span class="poll-result-opt">' + escapeHtml(opt) + '</span>';
        html += '<span class="poll-result-count">' + count + ' (' + pct + '%)</span>';
        html += '</div>';
        html += '<div class="poll-bar-track"><div class="poll-bar-fill" style="width:' + pct + '%"></div></div>';
        html += '</div>';
      });

      var pending = totalClients - totalResponses;
      var summaryText = totalResponses + ' of ' + totalClients + ' answered';
      if (pending <= 0) summaryText += ' · everyone answered!';
      else summaryText += ' · ' + pending + ' pending';
      html += '<div class="poll-meta-line">' + summaryText + '</div>';
      html += '<div class="poll-actions">';
      html += '<button class="entry entry-orange" onclick="closePoll(\'' + escapeHtml(pid) + '\')">Close</button>';
      html += '<button class="entry entry-red" onclick="deletePoll(\'' + escapeHtml(pid) + '\')">Delete</button>';
      html += '</div>';
      html += '</div>';
    });
    html += '</div>';
  }

  // ── Create form ────────────────────────────────────────────────────────
  html += '<div class="poll-section">';
  html += '<div class="poll-section-label">Create Poll</div>';
  html += '<div class="poll-create-card">';

  html += '<div class="poll-create-field">';
  html += '<label class="poll-field-label" for="poll-question">Question</label>';
  html += '<input id="poll-question" class="poll-input" placeholder="What do you want to ask?" maxlength="200" autocomplete="off">';
  html += '</div>';

  html += '<div class="poll-opts-header">';
  html += '<span class="poll-field-label">Options</span>';
  html += '<span class="poll-opts-hint">at least 2 required</span>';
  html += '</div>';

  for (var i = 1; i <= 4; i++) {
    html += '<div class="poll-opt-row">';
    html += '<span class="poll-opt-num">' + i + '</span>';
    html += '<input id="poll-opt' + i + '" class="poll-input" placeholder="' + (i <= 2 ? 'Option ' + i : 'Option ' + i + ' (optional)') + '" maxlength="100" autocomplete="off">';
    html += '</div>';
  }

  html += '<button class="poll-submit-btn" onclick="createPoll()">Send Poll to All Clients</button>';
  html += '</div></div>';

  // ── Past polls ─────────────────────────────────────────────────────────
  var past = Object.values(polls).filter(function(p) { return activeIds.indexOf(p.id) === -1; });
  if (past.length > 0) {
    past.sort(function(a, b) { return (b.created_at || 0) - (a.created_at || 0); });
    html += '<div class="poll-section">';
    html += '<div class="poll-section-label" style="color:#999;">Past Polls</div>';
    past.forEach(function(p) {
      var rc = Object.keys(p.responses || {}).length;
      html += '<div class="poll-past-row">';
      html += '<div class="poll-past-q">' + escapeHtml(p.question) + '</div>';
      html += '<div class="poll-past-meta">' + escapeHtml(p.options.join(' · ')) + ' — ' + rc + ' response' + (rc !== 1 ? 's' : '') + '</div>';
      html += '<div class="poll-past-actions">';
      html += '<button class="action-button" onclick="reactivatePoll(\'' + escapeHtml(p.id) + '\')">Reactivate</button>';
      html += '<button class="action-button btn-delete" onclick="deletePoll(\'' + escapeHtml(p.id) + '\')">Delete</button>';
      html += '</div>';
      html += '</div>';
    });
    html += '</div>';
  }

  container.innerHTML = html;

  // Restore form inputs
  var qEl = document.getElementById('poll-question');
  if (qEl) qEl.value = savedQ;
  for (var i = 1; i <= 4; i++) {
    var optEl = document.getElementById('poll-opt' + i);
    if (optEl) optEl.value = savedOpts[i - 1];
  }
}

async function createPoll() {
  if (!(await pass('poll'))) return;

  var question = ((document.getElementById('poll-question') || {}).value || '').trim();
  if (!question) { alert('Enter a question'); return; }
  var options = [];
  for (var i = 1; i <= 4; i++) {
    var v = ((document.getElementById('poll-opt' + i) || {}).value || '').trim();
    if (v) options.push(v);
  }
  if (options.length < 2) { alert('Enter at least 2 options'); return; }

  var btn = document.querySelector('.poll-submit-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }

  var body = 'question=' + encodeURIComponent(question);
  options.forEach(function(opt, idx) {
    body += '&option' + (idx + 1) + '=' + encodeURIComponent(opt);
  });

  fetch(ROUTES.pollCreate, {
    method: 'POST', body: body,
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      ['poll-question','poll-opt1','poll-opt2','poll-opt3','poll-opt4'].forEach(function(id) {
        var el = document.getElementById(id); if (el) el.value = '';
      });
      _lastPollsFp = null;
      loadPolls();
    } else {
      alert(d.error || 'Failed to create poll');
      if (btn) { btn.disabled = false; btn.textContent = 'Send Poll to All Clients'; }
    }
  }).catch(function() {
    alert('Request failed');
    if (btn) { btn.disabled = false; btn.textContent = 'Send Poll to All Clients'; }
  });
}

async function closePoll(pollId) {
  if (!(await pass('poll'))) return;
  fetch(ROUTES.pollClose, {
    method: 'POST',
    body: pollId ? 'poll_id=' + encodeURIComponent(pollId) : '',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { _lastPollsFp = null; loadPolls(); })
    .catch(function() {});
}

async function deletePoll(pollId) {
  if (!(await pass('poll'))) return;
  if (!confirm('Delete this poll and all its responses?')) return;
  fetch(ROUTES.pollDelete, {
    method: 'POST', body: 'poll_id=' + encodeURIComponent(pollId),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function() { _lastPollsFp = null; loadPolls(); })
    .catch(function() {});
}

async function reactivatePoll(pollId) {
  if (!(await pass('poll'))) return;
  fetch(ROUTES.pollActivate, {
    method: 'POST', body: 'poll_id=' + encodeURIComponent(pollId),
    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) { _lastPollsFp = null; loadPolls(); }
    else alert(d.error || 'Failed to activate poll');
  }).catch(function() {});
}

// Reload immediately when tab becomes visible
document.addEventListener('visibilitychange', function() {
  if (document.visibilityState === 'visible') {
    _lastPollsFp = null;
    loadPolls().catch(function() {});
  }
});

// Background refresh every 4s — skipped if fingerprint unchanged
setInterval(function() {
  if (document.visibilityState !== 'visible') return;
  loadPolls().catch(function() {});
}, 4000);
