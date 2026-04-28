var AUDIT_KNOWN_ACTIONS = [
  'auto_login',
  'ban',
  'delete',
  'delete_all',
  'effect',
  'clear_cookies',
  'image',
  'image_all',
  'image_displayed',
  'login',
  'login_attempt',
  'logout',
  'message',
  'message_all',
  'message_displayed',
  'note',
  'page_load',
  'question',
  'question_all',
  'question_answer',
  'question_clear',
  'redirect',
  'redirect_all',
  'redirect_executed',
  'show_id_all',
  'status_check',
  'timeout',
  'timeout_triggered',
  'unban',
  'untimeout'
];

var auditEntries = [];
var auditLoadSeq = 0;
var auditLoadController = null;
var auditPollTimer = null;

function escapeActionClass(action) {
  return String(action || 'unknown')
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_');
}

function getActionClass(action) {
  return 'action-' + escapeActionClass(action);
}

function timeAgo(timestamp) {
  var date = new Date(timestamp);
  if (isNaN(date.getTime())) return 'unknown';

  var diff = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diff < 60) return 'now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h';
  return Math.floor(diff / 86400) + 'd';
}

function parseDetailsValue(details) {
  if (details === null || details === undefined) return null;
  if (typeof details === 'string') {
    var trimmed = details.trim();
    if (!trimmed) return null;
    if ((trimmed[0] === '{' && trimmed[trimmed.length - 1] === '}') ||
        (trimmed[0] === '[' && trimmed[trimmed.length - 1] === ']')) {
      try {
        return JSON.parse(trimmed);
      } catch (e) {
        return trimmed;
      }
    }
    return trimmed;
  }
  return details;
}

function formatDetailsValue(details) {
  var parsed = parseDetailsValue(details);
  if (parsed === null) return 'No details';

  if (typeof parsed === 'string') return parsed;
  if (typeof parsed === 'number' || typeof parsed === 'boolean') return String(parsed);

  if (Array.isArray(parsed)) {
    if (!parsed.length) return 'No details';
    return '[' + parsed.map(function(item) {
      return formatDetailsValue(item);
    }).join(', ') + ']';
  }

  if (typeof parsed === 'object') {
    var keys = Object.keys(parsed).sort();
    if (!keys.length) return 'No details';
    return keys.map(function(key) {
      return key + ': ' + formatDetailsValue(parsed[key]);
    }).join(', ');
  }

  return String(parsed);
}

function formatDetailsTitle(details) {
  var parsed = parseDetailsValue(details);
  if (parsed === null) return '';

  if (typeof parsed === 'string') return parsed;

  try {
    return JSON.stringify(parsed, null, 2);
  } catch (e) {
    return String(parsed);
  }
}

function createCell(text, className, title) {
  var td = document.createElement('td');
  if (className) td.className = className;
  if (title) td.title = title;
  td.textContent = text;
  return td;
}

function buildActionFilter() {
  var select = document.getElementById('actionFilter');
  if (!select) return;

  var currentValue = select.value;
  var actionSet = new Set(AUDIT_KNOWN_ACTIONS);
  auditEntries.forEach(function(entry) {
    if (entry && entry.action) {
      actionSet.add(String(entry.action));
    }
  });

  var actions = Array.from(actionSet).sort();
  select.innerHTML = '';

  var defaultOption = document.createElement('option');
  defaultOption.value = '';
  defaultOption.textContent = 'All Actions';
  select.appendChild(defaultOption);

  actions.forEach(function(action) {
    var option = document.createElement('option');
    option.value = action;
    option.textContent = action;
    select.appendChild(option);
  });

  if (currentValue && actions.indexOf(currentValue) !== -1) {
    select.value = currentValue;
  } else {
    select.value = '';
  }
}

function renderAuditRows(entries) {
  var tbody = document.querySelector('#auditTable tbody');
  if (!tbody) return;

  tbody.innerHTML = '';

  if (!entries.length) {
    var emptyRow = document.createElement('tr');
    emptyRow.className = 'audit-empty-row';
    var emptyCell = document.createElement('td');
    emptyCell.colSpan = 7;
    emptyCell.textContent = 'No audit entries match the current filters.';
    emptyRow.appendChild(emptyCell);
    tbody.appendChild(emptyRow);
    return;
  }

  entries.forEach(function(entry) {
    var tr = document.createElement('tr');
    var timestamp = entry && entry.timestamp ? new Date(entry.timestamp) : null;
    var timeText = timestamp && !isNaN(timestamp.getTime()) ? timeAgo(entry.timestamp) : 'unknown';
    var timeTitle = timestamp && !isNaN(timestamp.getTime()) ? timestamp.toLocaleString() : '';
    var performer = entry && entry.performer ? String(entry.performer) : 'system';
    var action = entry && entry.action ? String(entry.action) : 'unknown';
    var target = entry && entry.target ? String(entry.target) : 'system';
    var detailsText = formatDetailsValue(entry ? entry.details : null);
    var detailsTitle = formatDetailsTitle(entry ? entry.details : null);
    var success = !!(entry && entry.success);

    tr.appendChild(createCell(timeText, '', timeTitle));
    tr.appendChild(createCell(performer));
    tr.appendChild(createCell(action, getActionClass(action)));
    tr.appendChild(createCell(target));
    tr.appendChild(createCell(detailsText, 'details-col', detailsTitle));
    tr.appendChild(createCell(entry && entry.ip ? String(entry.ip) : '', 'audit-ip-col'));
    tr.appendChild(createCell(success ? 'Success' : 'Failed', success ? 'success' : 'failure'));

    tbody.appendChild(tr);
  });
}

function updateStats(total, shown) {
  var stats = document.getElementById('stats');
  if (!stats) return;
  stats.textContent = 'Total: ' + total + ' | Showing: ' + shown;
}

function applyFilters() {
  var searchInput = document.getElementById('search');
  var actionSelect = document.getElementById('actionFilter');
  var showSuccessInput = document.getElementById('showSuccess');
  var showFailureInput = document.getElementById('showFailure');

  var search = searchInput ? searchInput.value.trim().toLowerCase() : '';
  var action = actionSelect ? actionSelect.value : '';
  var showSuccess = showSuccessInput ? showSuccessInput.checked : true;
  var showFailure = showFailureInput ? showFailureInput.checked : true;

  var filtered = auditEntries.filter(function(entry) {
    if (!showSuccess && entry.success) return false;
    if (!showFailure && !entry.success) return false;
    if (action && entry.action !== action) return false;

    if (!search) return true;
    var searchable = [
      entry.performer,
      entry.action,
      entry.target,
      formatDetailsValue(entry.details)
    ].join(' ').toLowerCase();
    return searchable.indexOf(search) !== -1;
  });

  renderAuditRows(filtered);
  updateStats(auditEntries.length, filtered.length);
}

function loadAudit() {
  var requestId = ++auditLoadSeq;
  if (auditLoadController) {
    auditLoadController.abort();
  }
  auditLoadController = new AbortController();

  return fetch('/audit.json?limit=1000&offset=0&exclude_system=true', {
    cache: 'no-store',
    credentials: 'same-origin',
    signal: auditLoadController.signal
  })
    .then(function(response) {
      if (response.status === 401) {
        window.location.replace('/audit/view');
        return null;
      }
      if (!response.ok) {
        throw new Error('Failed to load audit log');
      }
      return response.json();
    })
    .then(function(data) {
      if (!data || requestId !== auditLoadSeq) return null;
      auditEntries = Array.isArray(data.entries) ? data.entries : [];
      buildActionFilter();
      applyFilters();
      return data;
    })
    .catch(function(err) {
      if (err && err.name === 'AbortError') return null;
      console.error('Failed to load audit:', err);
      if (requestId === auditLoadSeq) {
        updateStats(auditEntries.length, 0);
      }
      return null;
    });
}

function startAuditPolling() {
  if (auditPollTimer) {
    clearInterval(auditPollTimer);
  }
  auditPollTimer = setInterval(function() {
    if (!document.hidden) {
      loadAudit();
    }
  }, 10000);
}

function initAuditViewer() {
  loadAudit();
  startAuditPolling();
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
      loadAudit();
    }
  });
}

initAuditViewer();
