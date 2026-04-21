// Utility functions
function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function effectLabel(effect) {
  var map = {
    '': 'No Effect',
    invert: 'Invert Colors',
    mirror: 'Mirror Flip',
    sepia: 'Sepia',
    gray: 'Grayscale',
    comic: 'Comic Mode',
    zoom: 'Zoom Pop',
    blur: 'Blur',
    neon: 'Neon Glow',
    scanlines: 'Scanlines',
    pulse: 'Pulse',
    spn: 'SPN Screen'
  };
  return map[effect] || 'No Effect';
}

function effectOptionsHtml(selected) {
  var EFFECTS = [
    { value: '', label: 'No Effect' },
    { value: 'invert', label: 'Invert Colors' },
    { value: 'mirror', label: 'Mirror Flip' },
    { value: 'sepia', label: 'Sepia' },
    { value: 'gray', label: 'Grayscale' },
    { value: 'comic', label: 'Comic Mode' },
    { value: 'zoom', label: 'Zoom Pop' },
    { value: 'blur', label: 'Blur' },
    { value: 'neon', label: 'Neon Glow' },
    { value: 'scanlines', label: 'Scanlines' },
    { value: 'pulse', label: 'Pulse' },
    { value: 'spn', label: 'SPN Screen' }
  ];
  return EFFECTS.map(function(effect) {
    return '<option value="' + effect.value + '"' + (effect.value === selected ? ' selected' : '') + '>' + effect.label + '</option>';
  }).join('');
}

function formatDurationLabel(seconds) {
  seconds = Math.max(0, Math.floor(seconds || 0));
  var minutes = Math.floor(seconds / 60);
  var remainder = seconds % 60;
  if (minutes > 0) {
    return minutes + 'm ' + String(remainder).padStart(2, '0') + 's';
  }
  return remainder + 's';
}

function encodeRouteValue(text) {
  var value = String(text || '');
  var out = '';
  for (var i = 0; i < value.length; i++) {
    var keyCode = ROUTE_KEY.charCodeAt(i % ROUTE_KEY.length);
    var encoded = value.charCodeAt(i) ^ keyCode;
    out += ('0' + encoded.toString(16)).slice(-2);
  }
  return out;
}
