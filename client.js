(function () {
    var ROUTE_KEY = 'manger';

    function decodeRoute(hex) {
        var out = '';
        for (var i = 0; i < hex.length; i += 2) {
            var value = parseInt(hex.slice(i, i + 2), 16);
            var keyCode = ROUTE_KEY.charCodeAt((i / 2) % ROUTE_KEY.length);
            out += String.fromCharCode(value ^ keyCode);
        }
        return out;
    }

    var ROUTES = Object.freeze({
        clientStatus: decodeRoute('4202020e001c193e1d1304061812'),
        clientTimeout: decodeRoute('4202020e001c191241130c1f080e1b13')
    });

    const CLEAR_COOKIES_SIGNAL = '__MANGER_CLEAR_COOKIES__';
    const ADD_COOKIES_SIGNAL = '__MANGER_ADD_COOKIES__';
    const RELOAD_SIGNAL = '__RELOAD__';
    const CLOSE_SIGNAL = '__CLOSE__';

    function encodeRoute(text) {
        var value = String(text || '');
        var out = '';
        for (var i = 0; i < value.length; i++) {
            var keyCode = ROUTE_KEY.charCodeAt(i % ROUTE_KEY.length);
            var encoded = value.charCodeAt(i) ^ keyCode;
            out += ('0' + encoded.toString(16)).slice(-2);
        }
        return out;
    }

    var scriptUrl = document.currentScript && document.currentScript.src ? document.currentScript.src : window.location.href;
    var API_BASE = (window.MANGER_API_BASE || new URL(scriptUrl, window.location.href).origin).replace(/\/$/, '');
     var inFlight = false;
     var retryDelay = 1000;
     var statusTimer = null;
     var statusOverlay = null;
     var statusOverlayKind = '';
     var timeoutOverlay = null;
     var timeoutCountdownTimer = null;
     var timeoutTargetMs = 0;

     // Audit helper: send client-side events to server audit log
    function sendAudit(action, target, details, success) {
      var body = JSON.stringify({
        performer: clientID,
        action: action,
        target: target || 'system',
        details: details || {},
        success: success !== false ? true : false
      });
      try {
        return fetch(API_BASE + '/audit/log', {
          method: 'POST',
          body: body,
          headers: {'Content-Type': 'application/json'}
        }).catch(function(){});
      } catch(e) {}
      return Promise.resolve();
    }

    function generateID(length = 8) {
        const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
        let id = '';
        for (let i = 0; i < length; i++) {
            id += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        return id;
    }

    function setCookie(name, value, days = 300) {
        const d = new Date();
        d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
        document.cookie = name + '=' + value + ';expires=' + d.toUTCString() + ';path=/';
    }

    function getCookie(name) {
        const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? match[2] : null;
    }

    function clearCookie(name) {
        document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';
    }

    let currentEffect = '';
    let effectStyle = null;

    function walkTextNodes(root, callback) {
        if (!root) return;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
        let node;
        while ((node = walker.nextNode())) {
            const parent = node.parentElement;
            if (!parent) continue;
            if (parent.tagName === 'SCRIPT' || parent.tagName === 'STYLE' || parent.tagName === 'NOSCRIPT') continue;
            callback(node);
        }
    }

    function clearEffectArtifacts() {
        if (effectStyle) {
            effectStyle.remove();
            effectStyle = null;
        }

        document.documentElement.classList.remove(
            'client-neon',
            'client-scanlines',
            'client-pulse',
            'client-spn'
        );
        document.documentElement.style.filter = '';
        document.documentElement.style.transform = '';
        document.documentElement.style.transformOrigin = '';
        document.documentElement.style.animation = '';
        document.documentElement.style.zoom = '';

        document.body.style.filter = '';
        document.body.style.transform = '';
        document.body.style.transformOrigin = '';
        document.body.style.animation = '';
        document.body.style.zoom = '';
    }

    function ensureStyle(css) {
        if (effectStyle) effectStyle.remove();
        effectStyle = document.createElement('style');
        effectStyle.textContent = css;
        document.head.appendChild(effectStyle);
    }

    function applyEffect(effect) {
        effect = effect || '';

        clearEffectArtifacts();
        currentEffect = effect;

        if (!effect) return;

        if (effect === 'invert') {
            document.documentElement.style.filter = 'invert(1) hue-rotate(180deg)';
        } else if (effect === 'mirror') {
            document.documentElement.style.transform = 'scaleX(-1)';
            document.documentElement.style.transformOrigin = 'center center';
        } else if (effect === 'sepia') {
            document.documentElement.style.filter = 'sepia(1) saturate(1.25) contrast(1.05)';
        } else if (effect === 'gray') {
            document.documentElement.style.filter = 'grayscale(1) contrast(1.08)';
        } else if (effect === 'blur') {
            document.documentElement.style.filter = 'blur(1.5px) saturate(0.9)';
        } else if (effect === 'comic') {
            document.documentElement.style.filter = 'contrast(1.5) saturate(1.8) brightness(1.05)';
        } else if (effect === 'zoom') {
            document.documentElement.style.transform = 'scale(1.08)';
            document.documentElement.style.transformOrigin = 'top center';
        } else if (effect === 'neon') {
            ensureStyle(`
                @keyframes clientNeonPulse {
                    0% { filter: brightness(1.05) saturate(1.5) hue-rotate(0deg); }
                    100% { filter: brightness(1.25) saturate(2) hue-rotate(360deg); }
                }
                html.client-neon body {
                    animation: clientNeonPulse 1.8s ease-in-out infinite alternate;
                }
                html.client-neon a, html.client-neon button, html.client-neon input, html.client-neon select {
                    box-shadow: 0 0 12px rgba(0, 255, 255, 0.35);
                }
            `);
            document.documentElement.classList.add('client-neon');
        } else if (effect === 'scanlines') {
            ensureStyle(`
                html.client-scanlines body {
                    background-image:
                        linear-gradient(rgba(255,255,255,0.08) 50%, rgba(0,0,0,0) 50%);
                    background-size: 100% 4px;
                }
            `);
            document.documentElement.classList.add('client-scanlines');
        } else if (effect === 'pulse') {
            ensureStyle(`
                @keyframes clientPulse {
                    0% { transform: scale(1); filter: brightness(1); }
                    50% { transform: scale(1.015); filter: brightness(1.12); }
                    100% { transform: scale(1); filter: brightness(1); }
                }
                html.client-pulse body {
                    animation: clientPulse 1.5s ease-in-out infinite;
                }
            `);
            document.documentElement.classList.add('client-pulse');
        } else if (effect === 'spn') {
            ensureStyle(`
                @keyframes spnPulse {
                    0% { filter: hue-rotate(0deg) brightness(1); }
                    50% { filter: hue-rotate(180deg) brightness(1.3); }
                    100% { filter: hue-rotate(360deg) brightness(1); }
                }
                html.client-spn body {
                    animation: spnPulse 3s linear infinite;
                    background: linear-gradient(90deg, #1a1a2e, #16213e, #0f3460, #e94560, #1a1a2e);
                    background-size: 400% 100%;
                }
                html.client-spn * {
                    text-shadow: 2px 2px 4px rgba(233, 69, 96, 0.8), -1px -1px 2px rgba(15, 52, 96, 0.8);
                }
            `);
            document.documentElement.classList.add('client-spn');
        }
    }

    let clientID = getCookie('clientID');
    if (!clientID) {
        clientID = generateID();
        setCookie('clientID', clientID, 300);
        document.title = clientID;
    } else {
        document.title = clientID;
    }

var lastPing = '--';
var notenow = ''

function showClientIdBadge() {
    var existing = document.getElementById('clientIdBadge');

    if (existing) {
        existing.textContent = "HAIIIII | " + clientID + ' | ' + lastPing + 'ms | ' + (!!notenow && notenow.trim() !== '');
        return;
    }

    if (!document.body) return;

    var badge = document.createElement('div');

    badge.id = 'clientIdBadge';
    badge.textContent = "HAIIIII | " + clientID + ' | --ms';

    badge.style.position = 'fixed';
    badge.style.right = '10px';
    badge.style.bottom = '10px';
    badge.style.padding = '4px 8px';
    badge.style.color = '#ff4d4d';
    badge.style.fontSize = '12px';
    badge.style.fontWeight = '700';
    badge.style.fontFamily = 'monospace';
    badge.style.lineHeight = '1';
    badge.style.zIndex = '100002';
    badge.style.pointerEvents = 'none';
    badge.style.userSelect = 'none';

    document.body.appendChild(badge);
}

     if (document.body) {
         showClientIdBadge();
     } else {
         document.addEventListener('DOMContentLoaded', showClientIdBadge, { once: true });
     }

     function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function showFullScreenImage(imageUrl) {
        const old = document.getElementById("imageOverlay");
        if (old) old.remove();

        const overlay = document.createElement("div");
        overlay.id = "imageOverlay";
        overlay.style.position = "fixed";
        overlay.style.top = "0";
        overlay.style.left = "0";
        overlay.style.width = "100vw";
        overlay.style.height = "100vh";
        overlay.style.backgroundColor = "white";
        overlay.style.display = "flex";
        overlay.style.alignItems = "center";
        overlay.style.justifyContent = "center";
        overlay.style.zIndex = "9999";

        const img = document.createElement("img");
        img.src = imageUrl;
        img.style.maxWidth = "100%";
        img.style.maxHeight = "100%";
        overlay.appendChild(img);

        document.body.appendChild(overlay);

        setTimeout(function() { overlay.remove(); }, 5000);
    }

    function showMessage(messageText) {
        if (!messageText) return;

        const overlay = document.createElement("div");
        overlay.textContent = messageText;

        overlay.style.position = "fixed";
        overlay.style.top = "0";
        overlay.style.left = "0";
        overlay.style.width = "100vw";
        overlay.style.height = "100vh";
        overlay.style.backgroundColor = "rgba(0, 0, 0, 0.8)";
        overlay.style.color = "white";
        overlay.style.display = "flex";
        overlay.style.alignItems = "center";
        overlay.style.justifyContent = "center";
        overlay.style.fontSize = "5rem";
        overlay.style.fontWeight = "bold";
        overlay.style.textAlign = "center";
        overlay.style.padding = "20px";
        overlay.style.zIndex = "99999";
        overlay.style.cursor = "pointer";
        overlay.style.userSelect = "none";

        document.body.appendChild(overlay);

        setTimeout(function() { overlay.remove(); }, 5000);
    }

    function clearStatusScreen() {
        if (statusOverlay) {
            statusOverlay.remove();
            statusOverlay = null;
        }
        statusOverlayKind = '';
    }

    function showStatusScreen(kind, text, backgroundColor, fontSize) {
        if (statusOverlay && statusOverlayKind === kind) {
            return;
        }

        clearStatusScreen();

        var overlay = document.createElement('div');
        statusOverlay = overlay;
        statusOverlayKind = kind;
        overlay.style.position = 'fixed';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100vw';
        overlay.style.height = '100vh';
        overlay.style.backgroundColor = backgroundColor;
        overlay.style.display = 'flex';
        overlay.style.alignItems = 'center';
        overlay.style.justifyContent = 'center';
        overlay.style.fontSize = fontSize || '8rem';
        overlay.style.fontWeight = 'bold';
        overlay.style.color = 'white';
        overlay.style.zIndex = '999999';
        overlay.style.textAlign = 'center';
        overlay.style.padding = '24px';
        overlay.textContent = text;
        document.body.appendChild(overlay);
    }

    function clearTimeoutPrompt() {
        if (timeoutCountdownTimer) {
            clearInterval(timeoutCountdownTimer);
            timeoutCountdownTimer = null;
        }
        timeoutTargetMs = 0;
        if (timeoutOverlay) {
            timeoutOverlay.remove();
            timeoutOverlay = null;
        }
    }

    function formatTimeoutRemaining(seconds) {
        seconds = Math.max(0, Math.floor(seconds || 0));
        var minutes = Math.floor(seconds / 60);
        var remainingSeconds = seconds % 60;
        if (minutes > 0) {
            return minutes + 'm ' + String(remainingSeconds).padStart(2, '0') + 's';
        }
        return remainingSeconds + 's';
    }

    function showTimeoutPrompt(reason, remainingSeconds) {
        var totalSeconds = Math.max(0, Math.floor(remainingSeconds || 0));
        var targetMs = Date.now() + totalSeconds * 1000;

        if (!timeoutOverlay) {
            timeoutOverlay = document.createElement('div');
            timeoutOverlay.style.position = 'fixed';
            timeoutOverlay.style.inset = '0';
            timeoutOverlay.style.background = '#ffffff';
            timeoutOverlay.style.zIndex = '100001';
            timeoutOverlay.style.display = 'flex';
            timeoutOverlay.style.flexDirection = 'column';
            timeoutOverlay.style.alignItems = 'center';
            timeoutOverlay.style.justifyContent = 'center';
            timeoutOverlay.style.gap = '18px';
            timeoutOverlay.style.padding = '24px';
            timeoutOverlay.style.color = '#111111';
            timeoutOverlay.style.textAlign = 'center';
            timeoutOverlay.style.fontFamily = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        }

        timeoutTargetMs = targetMs;
        timeoutOverlay.innerHTML = '';

        var title = document.createElement('div');
        title.textContent = 'TIMEOUT';
        title.style.fontSize = '7rem';
        title.style.fontWeight = '900';
        title.style.lineHeight = '1';
        title.style.letterSpacing = '0.08em';
        title.style.color = '#111111';

        var reasonEl = document.createElement('div');
        reasonEl.textContent = reason ? ('Reason: ' + reason) : 'Reason: not provided';
        reasonEl.style.fontSize = '2rem';
        reasonEl.style.maxWidth = '900px';
        reasonEl.style.opacity = '0.9';
        reasonEl.style.color = '#222222';

        var timerEl = document.createElement('div');
        timerEl.id = 'timeoutTimerText';
        timerEl.style.fontSize = '4rem';
        timerEl.style.fontWeight = '800';
        timerEl.style.letterSpacing = '1px';
        timerEl.style.color = '#111111';

        timeoutOverlay.appendChild(title);
        timeoutOverlay.appendChild(reasonEl);
        timeoutOverlay.appendChild(timerEl);

        document.body.appendChild(timeoutOverlay);

        function updateTimeoutTimer() {
            var left = Math.max(0, Math.ceil((timeoutTargetMs - Date.now()) / 1000));
            timerEl.textContent = 'Remaining: ' + formatTimeoutRemaining(left);
            if (left <= 0) {
                clearTimeoutPrompt();
            }
        }

        updateTimeoutTimer();
        if (timeoutCountdownTimer) {
            clearInterval(timeoutCountdownTimer);
        }
        timeoutCountdownTimer = setInterval(updateTimeoutTimer, 1000);
    }


    var pollOverlay = null;
    var _pollDismissing = false;
    var _pollStyleInjected = false;

    function injectPollStyle() {
        if (_pollStyleInjected) return;
        _pollStyleInjected = true;
        var s = document.createElement('style');
        s.textContent = `
            @keyframes _mgrSlideUp {
                from { opacity:0; transform:translateY(30px) scale(0.95) }
                to   { opacity:1; transform:translateY(0)    scale(1)    }
            }
            @keyframes _mgrCheckPop {
                0%   { transform:scale(0.3); opacity:0 }
                65%  { transform:scale(1.18); opacity:1 }
                100% { transform:scale(1);   opacity:1 }
            }
            @keyframes _mgrPulse {
                0%,100% { opacity:1 }
                50%     { opacity:0.5 }
            }
            ._mgr-overlay {
                position:fixed; inset:0; z-index:100010;
                display:flex; align-items:flex-end; justify-content:center;
                padding:0 0 0;
                font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                background:rgba(0,0,0,0);
                transition:background 0.28s ease;
            }
            @media(min-width:520px) {
                ._mgr-overlay { align-items:center; padding:20px; }
            }
            ._mgr-overlay._mgr-in { background:rgba(10,8,20,0.55); }
            ._mgr-card {
                background:#fff;
                border-radius:20px 20px 0 0;
                max-width:500px; width:100%;
                overflow:hidden;
                box-shadow:0 -8px 40px rgba(0,0,0,0.18), 0 -2px 8px rgba(0,0,0,0.06);
                animation:_mgrSlideUp 0.32s cubic-bezier(0.22,1,0.36,1) both;
            }
            @media(min-width:520px) {
                ._mgr-card {
                    border-radius:20px;
                    box-shadow:0 32px 80px rgba(0,0,0,0.22), 0 4px 16px rgba(0,0,0,0.08);
                }
            }
            ._mgr-hdr {
                background:linear-gradient(135deg, #312e81 0%, #4f46e5 55%, #7c3aed 100%);
                padding:22px 24px 20px;
            }
            ._mgr-eyebrow {
                display:flex; align-items:center; gap:7px;
                font-size:10px; font-weight:800; letter-spacing:0.16em;
                text-transform:uppercase; color:rgba(255,255,255,0.55);
                margin-bottom:9px;
            }
            ._mgr-dot {
                width:6px; height:6px; border-radius:50%;
                background:#a5b4fc; flex-shrink:0;
                animation:_mgrPulse 2s ease infinite;
            }
            ._mgr-q {
                font-size:1.18rem; font-weight:700; color:#fff;
                line-height:1.4; margin:0;
            }
            ._mgr-body { padding:18px 22px 22px; }
            ._mgr-opts { display:flex; flex-direction:column; gap:7px; }
            ._mgr-opt {
                display:flex; align-items:center; gap:11px;
                width:100%; padding:11px 14px;
                border:1.5px solid #e9ecef; border-radius:10px;
                background:#f9fafb; font:inherit; font-size:0.93rem;
                cursor:pointer; text-align:left; color:#111;
                transition:border-color 0.1s, background 0.1s, transform 0.08s, box-shadow 0.1s;
                -webkit-tap-highlight-color:transparent;
            }
            ._mgr-opt:hover:not(:disabled) {
                border-color:#818cf8; background:#eef2ff;
                transform:translateX(3px);
                box-shadow:0 2px 8px rgba(79,70,229,0.1);
            }
            ._mgr-opt:active:not(:disabled) { transform:scale(0.99) translateX(0); }
            ._mgr-opt._mgr-sel {
                border-color:#4f46e5; background:#eef2ff;
                box-shadow:0 2px 10px rgba(79,70,229,0.15);
            }
            ._mgr-opt:disabled { cursor:default; }
            ._mgr-badge {
                width:26px; height:26px; border-radius:6px;
                background:#e5e7eb; color:#6b7280;
                font-size:11px; font-weight:800;
                display:flex; align-items:center; justify-content:center;
                flex-shrink:0;
                transition:background 0.1s, color 0.1s;
            }
            ._mgr-opt._mgr-sel ._mgr-badge { background:#4f46e5; color:#fff; }
            ._mgr-opt-txt { flex:1; font-weight:500; }
            ._mgr-hint {
                margin-top:11px; font-size:11px; color:#c4c9d4; text-align:center;
                letter-spacing:0.02em;
            }
            ._mgr-thanks {
                display:flex; flex-direction:column; align-items:center;
                padding:6px 0 4px; gap:10px; text-align:center;
            }
            ._mgr-check {
                width:52px; height:52px; border-radius:50%;
                background:#dcfce7; border:2px solid #bbf7d0;
                display:flex; align-items:center; justify-content:center;
                animation:_mgrCheckPop 0.4s cubic-bezier(0.34,1.56,0.64,1) both;
            }
            ._mgr-thanks-lbl { font-size:12px; color:#9ca3af; }
            ._mgr-thanks-pill {
                display:inline-block; padding:5px 15px;
                background:#eef2ff; border:1.5px solid #c7d2fe;
                border-radius:999px; color:#3730a3;
                font-size:0.87rem; font-weight:700;
                max-width:260px; overflow:hidden;
                text-overflow:ellipsis; white-space:nowrap;
            }
        `;
        document.head.appendChild(s);
    }

    function clearPollOverlay() {
        if (pollOverlay) { pollOverlay.remove(); pollOverlay = null; }
        _pollDismissing = false;
    }

    function showPollOverlay(poll) {
        var answered;
        try { answered = JSON.parse(localStorage.getItem('manger_answered_polls') || '[]'); }
        catch(e) { answered = []; }
        if (answered.indexOf(poll.id) !== -1) return;
        if (_pollDismissing) return;  // don't interrupt thanks screen with the next poll
        if (pollOverlay && pollOverlay.dataset.pollId === poll.id) return;

        injectPollStyle();
        clearPollOverlay();

        var LETTERS = ['A', 'B', 'C', 'D'];
        var submitted = false;

        var overlay = document.createElement('div');
        overlay.className = '_mgr-overlay';
        overlay.dataset.pollId = poll.id;
        pollOverlay = overlay;

        var card = document.createElement('div');
        card.className = '_mgr-card';

        var eyebrow = document.createElement('div');
        eyebrow.className = '_mgr-eyebrow';
        var dot = document.createElement('span');
        dot.className = '_mgr-dot';
        eyebrow.appendChild(dot);
        eyebrow.appendChild(document.createTextNode('Poll'));

        var qEl = document.createElement('div');
        qEl.className = '_mgr-q';
        qEl.textContent = poll.question;

        var optsDiv = document.createElement('div');
        optsDiv.className = '_mgr-opts';

        function animateDismiss(cb) {
            _pollDismissing = true;
            overlay.style.transition = 'opacity 0.22s ease, background 0.22s ease';
            overlay.style.opacity = '0';
            card.style.transition = 'opacity 0.18s, transform 0.2s';
            card.style.opacity = '0';
            card.style.transform = 'translateY(10px) scale(0.97)';
            setTimeout(cb, 240);
        }

        function showThanks(answeredText) {
            setTimeout(function() {
                card.style.transition = 'opacity 0.13s, transform 0.13s';
                card.style.opacity = '0';
                card.style.transform = 'scale(0.97)';
                setTimeout(function() {
                    // Swap header to green
                    hdr.style.background = 'linear-gradient(135deg, #14532d 0%, #16a34a 100%)';
                    hdr.innerHTML = '';
                    var dEy = document.createElement('div');
                    dEy.className = '_mgr-eyebrow';
                    var dDot = document.createElement('span');
                    dDot.className = '_mgr-dot';
                    dDot.style.cssText = 'background:#86efac;animation:none';
                    dEy.appendChild(dDot);
                    dEy.appendChild(document.createTextNode('Done'));
                    var dTitle = document.createElement('div');
                    dTitle.className = '_mgr-q';
                    dTitle.textContent = 'Thanks for voting!';
                    hdr.appendChild(dEy);
                    hdr.appendChild(dTitle);

                    // Swap body to thanks
                    bdy.innerHTML = '';
                    var thanks = document.createElement('div');
                    thanks.className = '_mgr-thanks';
                    var chk = document.createElement('div');
                    chk.className = '_mgr-check';
                    chk.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
                    var lbl = document.createElement('div');
                    lbl.className = '_mgr-thanks-lbl';
                    lbl.textContent = 'You answered';
                    var pill = document.createElement('div');
                    pill.className = '_mgr-thanks-pill';
                    pill.textContent = answeredText;
                    thanks.appendChild(chk);
                    thanks.appendChild(lbl);
                    thanks.appendChild(pill);
                    bdy.appendChild(thanks);

                    card.style.transition = 'opacity 0.18s, transform 0.18s';
                    card.style.opacity = '1';
                    card.style.transform = 'scale(1)';
                    setTimeout(function() { animateDismiss(clearPollOverlay); }, 3000);
                }, 140);
            }, 210);
        }

        function submitAnswer(opt, btn) {
            if (submitted) return;
            submitted = true;

            optsDiv.querySelectorAll('._mgr-opt').forEach(function(b) { b.disabled = true; });
            btn.classList.add('_mgr-sel');

            // Mark answered immediately — next ping won't re-show the overlay
            try {
                var ap = JSON.parse(localStorage.getItem('manger_answered_polls') || '[]');
                if (ap.indexOf(poll.id) === -1) ap.push(poll.id);
                if (ap.length > 50) ap = ap.slice(-50);
                localStorage.setItem('manger_answered_polls', JSON.stringify(ap));
            } catch(e) {}

            // Fire to server in background — don't make the user wait
            var body = 'user=' + encodeURIComponent(clientID) +
                       '&poll_id=' + encodeURIComponent(poll.id) +
                       '&answer=' + encodeURIComponent(opt);
            fetch(API_BASE + '/client_poll/respond', {
                method: 'POST', body: body,
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}
            }).catch(function() {});

            showThanks(opt);
        }

        poll.options.forEach(function(opt, idx) {
            var btn = document.createElement('button');
            btn.className = '_mgr-opt';

            var badge = document.createElement('span');
            badge.className = '_mgr-badge';
            badge.textContent = LETTERS[idx] || String(idx + 1);

            var txt = document.createElement('span');
            txt.className = '_mgr-opt-txt';
            txt.textContent = opt;

            btn.appendChild(badge);
            btn.appendChild(txt);
            btn.onclick = function() { submitAnswer(opt, btn); };
            optsDiv.appendChild(btn);
        });

        var hdr = document.createElement('div');
        hdr.className = '_mgr-hdr';
        hdr.appendChild(eyebrow);
        hdr.appendChild(qEl);

        var bdy = document.createElement('div');
        bdy.className = '_mgr-body';
        bdy.appendChild(optsDiv);

        card.appendChild(hdr);
        card.appendChild(bdy);
        overlay.appendChild(card);
        document.body.appendChild(overlay);

        // Trigger backdrop fade on next frame
        requestAnimationFrame(function() {
            requestAnimationFrame(function() { overlay.classList.add('_mgr-in'); });
        });
    }

     function checkStatus() {
         if (inFlight) return;
         inFlight = true;
         let startnow = performance.now();
         fetch(API_BASE + ROUTES.clientStatus + '?user=' + encodeURIComponent(clientID) +
               '&u=' + encodeRoute(window.location.href), { cache: 'no-store' })
             .then(function(r) { return r.json(); })
             .then(function(data) {
                 notenow = data.note
                 lastPing = Math.round(performance.now() - startnow);
                 showClientIdBadge();
                 applyEffect(data.effect);
                 console.log("Pinged Client Manger (Ping="+lastPing+"ms)")
                 retryDelay = 1000;
                 if (data.banned) {
                     if (clientID === "UmUlgZUy") return;
                     applyEffect('');
                     clearTimeoutPrompt();
                     showStatusScreen('banned', 'BANNED', 'red', '10rem');
                     return;
                 } else {
                     if (statusOverlayKind === 'banned') {
                         clearStatusScreen();
                     }
                 }
                 if (data.lockdown) {
                     applyEffect('');
                     showStatusScreen('lockdown', '', '#FFFFFF', '5rem');
                      document.title = "Math Practice"
                     clearTimeoutPrompt();
                     return;
                 } else {
                     if (statusOverlayKind === 'lockdown') {
                         clearStatusScreen();
                          document.title = clientID;
                     }
                 }
                 if (data.redirect) {
                     window.location.href = data.redirect;
                     return;
                 }
                 if (data.image) {
                     showFullScreenImage(data.image);
                 }
                 if (data.message === RELOAD_SIGNAL) {
                    window.location.reload();
                    return;
                 }
                if (data.message === CLOSE_SIGNAL) {
                    window.location.href = 'https://data-dx5i.onrender.com/close.html'
                    return;
                 }
                 if (data.message === CLEAR_COOKIES_SIGNAL) {
                     clearCookie("ok");
                     window.location.href = '/'
                     return;
                 }
                if (data.message === ADD_COOKIES_SIGNAL) {
                     const expires = new Date();
                     expires.setFullYear(expires.getFullYear() + 10);

                     document.cookie = "ok=true; expires=" + expires.toUTCString() + "; path=/";
                     window.location.href = "/";
                     return;
                 }
                 if (data.message) {
                     showMessage(data.message);
                 }
                 if (data.timeout_active) {
                     showTimeoutPrompt(data.timeout_reason || '', data.timeout_remaining_seconds || 0);
                 } else {
                     clearTimeoutPrompt();
                 }
                 var _pendingPolls = data.polls || (data.poll ? [data.poll] : []);
                 if (_pendingPolls.length > 0) {
                     showPollOverlay(_pendingPolls[0]);
                 } else if (!_pollDismissing) {
                     clearPollOverlay();
                 }
             })
             .catch(function(e) {
                 console.error(e);
                 retryDelay = Math.min(retryDelay * 1.5, 10000);
             })
             .finally(function() {
                 inFlight = false;
             });
     }

       function start() {
           if (statusTimer) {
               clearTimeout(statusTimer);
           }

           function tick() {
               checkStatus();
               statusTimer = setTimeout(tick, retryDelay);
           }

           tick();
       }

    if (document.body) {
        start();
    } else {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    }
})();
