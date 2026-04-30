from base64 import b64encode
from datetime import datetime
from html import escape
from pathlib import Path
import re
import time
import uuid
from threading import RLock

from flask import (
    Response,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template_string,
    request,
    url_for,
)

from account_auth import (
    find_account_by_password,
    get_authenticated_account,
    is_action_allowed,
    load_accounts,
)


BASE_DIR = Path(__file__).resolve().parent
ROUTE_KEY = "manger"
CLIENT_SCRIPT_HTML = """
<!DOCTYPE html><html><head><title>Client Script</title></head><body>
<h1>Client Script Loader</h1>
<p>Copy this script to your website to connect with our client manager:</p>
<pre>
&lt;script src="http://localhost:5001/client_script.js"&gt;&lt;/script&gt;
</pre>
<p><a href="/">Back Home</a></p>
</body></html>
"""
CLIENT_SCRIPT_JS = (BASE_DIR / "client.js").read_text()

AUDIT_LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Audit Log Login</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="/static/css/audit.css">
</head>
<body class="audit-login">
  <div class="audit-login-card">
    <h2>Audit Log Access</h2>
    <p>Enter admin password to view audit logs:</p>
    <form id="loginForm">
      <label for="password" class="audit-password-label">Password</label>
      <input
        type="password"
        id="password"
        name="password"
        placeholder="Password"
        autocomplete="current-password"
        autocapitalize="off"
        spellcheck="false"
        inputmode="text"
        required
        autofocus
      >
      <button type="submit">Login</button>
    </form>
    <p class="audit-error" id="errorMsg"></p>
    <p><a href="/clients">Back to Client Manager</a></p>
  </div>
  <script>
    document.getElementById('loginForm').onsubmit = function(e) {
      e.preventDefault();
      var pwd = document.getElementById('password').value;
      fetch('/audit/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({password: pwd})
      })
      .then(r => {
        if (r.ok) {
          location.reload();
        } else {
          return r.json().then(d => { throw new Error(d.error || 'Invalid'); });
        }
      })
      .catch(err => {
        document.getElementById('errorMsg').textContent = err.message;
        document.getElementById('errorMsg').style.display = 'block';
      });
    };
  </script>
</body>
</html>
"""

# Audit viewer session storage (simple in-memory)
_audit_lock = RLock()
_audit_sessions = {}


def register_routes(app, state):
    clients = state["clients"]
    data_lock = state["data_lock"]
    save_json = state["save_json"]
    normalize_client_effect = state["normalize_client_effect"]
    clients_json_path = state["clients_json_path"]
    lockdown_state = state["lockdown"]
    audit_mod = state.get("audit")
    accounts_path = state.get("accounts_json_path")
    cookie_secure = bool(app.config.get("SESSION_COOKIE_SECURE"))

    def audit_log(performer, action, target="system", details=None, success=True):
        if audit_mod:
            try:
                audit_mod.append_audit(
                    performer, action, target, details or {}, success, request
                )
            except Exception as e:
                print("Audit log error:", e)

    def require_auth(action=None):
        account = get_authenticated_account(accounts_path)
        if not account:
            return None, (jsonify({"error": "Unauthorized"}), 401)
        if action and not is_action_allowed(action, account):
            return None, (jsonify({"error": "Forbidden"}), 403)
        return account, None

    def decode_xor_hex(value):
        if not value:
            return ""
        value = value.strip()
        if len(value) % 2:
            return value
        try:
            out = []
            for index in range(0, len(value), 2):
                byte = int(value[index : index + 2], 16)
                key_code = ord(ROUTE_KEY[(index // 2) % len(ROUTE_KEY)])
                out.append(chr(byte ^ key_code))
            return "".join(out)
        except ValueError:
            return value

    def parse_duration_seconds(value):
        text = (value or "").strip().lower()
        if not text:
            return 0
        if text.isdigit():
            return int(text)

        total = 0
        matched = False
        for amount, unit in re.findall(r"(\d+)\s*([smhd])", text):
            matched = True
            amount = int(amount)
            if unit == "s":
                total += amount
            elif unit == "m":
                total += amount * 60
            elif unit == "h":
                total += amount * 3600
            elif unit == "d":
                total += amount * 86400

        return total if matched and total > 0 else 0

    @app.route("/clients", methods=["GET"])
    def clients_index():
        return render_template_string((BASE_DIR / "client-manger.html").read_text())

    @app.route("/clients.json")
    def clients_json():
        account, error = require_auth()
        if error:
            return error
        now = datetime.utcnow()
        with data_lock:
            snapshot = dict(clients)
        clients_display = {}
        for user, data in snapshot.items():
            last_ping = data.get("last_ping")
            recent = False
            if last_ping:
                try:
                    last_dt = datetime.strptime(last_ping, "%Y-%m-%d %H:%M:%S")
                    recent = (now - last_dt).total_seconds() < 10
                except ValueError:
                    recent = False

            timeout_until = data.get("timeout_until")
            timeout_active = False
            timeout_remaining = None
            if timeout_until:
                try:
                    timeout_remaining = max(0, int(timeout_until - time.time()))
                    timeout_active = timeout_remaining > 0
                except (TypeError, ValueError):
                    timeout_until = None

            if timeout_until and not timeout_active:
                with data_lock:
                    if user in clients:
                        clients[user]["timeout_reason"] = None
                        clients[user]["timeout_set_at"] = None
                        clients[user]["timeout_until"] = None
                        clients[user]["timeout_duration_seconds"] = None
                        save_json(clients_json_path, clients)
                timeout_remaining = 0

            clients_display[user] = {**data, "recent": recent}
            clients_display[user]["timeout_remaining_seconds"] = timeout_remaining
            clients_display[user]["timeout_active"] = timeout_active
        resp = jsonify(clients_display)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.route("/clients/ban", methods=["POST"])
    def ban_client():
        account, error = require_auth("ban")
        if error:
            return error
        username = request.form.get("username", "").strip()
        performer = account["label"]
        if not username:
            return redirect(url_for("clients_index"))
        with data_lock:
            clients.setdefault(username, {})["banned"] = True
            save_json(clients_json_path, clients)
        audit_log(performer, "ban", username, {}, True)
        resp = make_response(redirect(url_for("clients_index")))
        resp.set_cookie(f"ban_{username}", "1")
        return resp

    @app.route("/clients/unban", methods=["POST"])
    def unban_client():
        account, error = require_auth("unban")
        if error:
            return error
        username = request.form.get("username", "").strip()
        performer = account["label"]
        with data_lock:
            if username in clients:
                clients[username]["banned"] = False
                save_json(clients_json_path, clients)
        audit_log(performer, "unban", username, {}, True)
        resp = make_response(redirect(url_for("clients_index")))
        resp.set_cookie(f"ban_{username}", "", expires=0)
        return resp

    @app.route("/clients/delete", methods=["POST"])
    def delete_client():
        account, error = require_auth("delete")
        if error:
            return error
        username = request.form.get("username", "").strip()
        performer = account["label"]
        with data_lock:
            if username in clients:
                del clients[username]
                save_json(clients_json_path, clients)
        audit_log(performer, "delete", username, {}, True)
        return redirect(url_for("clients_index"))

    @app.route("/clients/image", methods=["POST"])
    def send_image_to_client():
        account, error = require_auth("image")
        if error:
            return error
        username = request.form.get("username", "").strip()
        performer = account["label"]
        file = request.files.get("image_file")
        image_base64 = request.form.get("image", "").strip()

        if not username:
            flash("No username provided.")
            return redirect(url_for("clients_index"))

        image_data = None

        if image_base64:
            image_data = image_base64
        elif file:
            try:
                image_data = (
                    f"data:{file.content_type};base64,{b64encode(file.read()).decode()}"
                )
            except Exception as e:
                flash(f"Error reading image: {e}")
                return redirect(url_for("clients_index"))
        else:
            flash("No image file uploaded.")
            return redirect(url_for("clients_index"))

        if image_data:
            with data_lock:
                clients.setdefault(username, {})["image"] = image_data
                save_json(clients_json_path, clients)
            audit_log(
                performer,
                "image",
                username,
                {"type": "base64" if image_base64 else "file"},
                True,
            )
        return redirect(url_for("clients_index"))

    @app.route("/clients/message", methods=["POST"])
    def send_message_to_client():
        account, error = require_auth("message")
        if error:
            return error
        username = request.form.get("username", "").strip()
        performer = account["label"]
        message = request.form.get("message", "").strip()

        if username and message:
            with data_lock:
                clients.setdefault(username, {})["message"] = message
                save_json(clients_json_path, clients)
            audit_log(performer, "message", username, {"length": len(message)}, True)

        return redirect(url_for("clients_index"))

    @app.route("/clients/timeout", methods=["POST"])
    def send_timeout_to_client():
        account, error = require_auth("timeout")
        if error:
            return error
        username = request.form.get("username", "").strip()
        performer = account["label"]
        duration = request.form.get("duration", "").strip()
        reason = request.form.get("reason", "").strip()

        if not username:
            return redirect(url_for("clients_index"))

        seconds = parse_duration_seconds(duration)
        if seconds <= 0:
            return redirect(url_for("clients_index"))

        now = time.time()
        with data_lock:
            client = clients.setdefault(username, {})
            client["timeout_reason"] = reason
            client["timeout_set_at"] = now
            client["timeout_until"] = now + seconds
            client["timeout_duration_seconds"] = seconds
            save_json(clients_json_path, clients)

        audit_log(
            performer,
            "timeout",
            username,
            {"duration_seconds": seconds, "reason": reason},
            True,
        )
        return redirect(url_for("clients_index"))

    @app.route("/clients/timeout/clear", methods=["POST"])
    def clear_timeout_on_client():
        account, error = require_auth("untimeout")
        if error:
            return error
        username = request.form.get("username", "").strip()
        performer = account["label"]

        if not username:
            return redirect(url_for("clients_index"))

        with data_lock:
            client = clients.setdefault(username, {})
            client["timeout_reason"] = None
            client["timeout_set_at"] = None
            client["timeout_until"] = None
            client["timeout_duration_seconds"] = None
            save_json(clients_json_path, clients)

        audit_log(performer, "untimeout", username, {}, True)
        return redirect(url_for("clients_index"))

    @app.route("/clients/note", methods=["POST"])
    def set_client_note():
        account, error = require_auth("notes")
        if error:
            return error
        username = request.form.get("username", "").strip()
        performer = account["label"]
        note = request.form.get("note", "").strip()

        if username:
            with data_lock:
                clients.setdefault(username, {})["note"] = note
                save_json(clients_json_path, clients)
            audit_log(performer, "note", username, {"note_len": len(note)}, True)

        return redirect(url_for("clients_index"))

    @app.route("/client_script")
    def client_script_page():
        return render_template_string(CLIENT_SCRIPT_HTML)

    @app.route("/client_script.js")
    def client_script_js():
        return Response(CLIENT_SCRIPT_JS, content_type="application/javascript")

    @app.route("/clients/redirect", methods=["POST"])
    def redirect_client():
        account, error = require_auth("redirect")
        if error:
            return error
        username = request.form.get("username", "").strip()
        url = (
            decode_xor_hex(request.form.get("u", "").strip())
            or request.form.get("url", "").strip()
        )

        if username and url:
            with data_lock:
                clients.setdefault(username, {})["redirect"] = url
                save_json(clients_json_path, clients)

        return redirect(url_for("clients_index"))

    @app.route("/clients/effect", methods=["POST"])
    def set_client_effect():
        account, error = require_auth("effect")
        if error:
            return error
        username = request.form.get("username", "").strip()
        effect = normalize_client_effect(request.form.get("effect", ""))

        if username:
            with data_lock:
                clients.setdefault(username, {})["effect"] = effect
                save_json(clients_json_path, clients)

        return redirect(url_for("clients_index"))

    @app.route("/clients/<path:subpath>", methods=["POST"])
    def clients_fallback(subpath):
        account, error = require_auth()
        if error:
            return error
        username = request.form.get("username", "").strip()
        if not username:
            return redirect(url_for("clients_index"))

        if "note" in request.form:
            if not is_action_allowed("notes", account):
                return jsonify({"error": "Forbidden"}), 403
            note = request.form.get("note", "").strip()
            with data_lock:
                clients.setdefault(username, {})["note"] = note
                save_json(clients_json_path, clients)
        elif "effect" in request.form:
            if not is_action_allowed("effect", account):
                return jsonify({"error": "Forbidden"}), 403
            effect = normalize_client_effect(request.form.get("effect", ""))
            with data_lock:
                clients.setdefault(username, {})["effect"] = effect
                save_json(clients_json_path, clients)
        elif "message" in request.form:
            if not is_action_allowed("message", account):
                return jsonify({"error": "Forbidden"}), 403
            message = request.form.get("message", "").strip()
            if message:
                with data_lock:
                    clients.setdefault(username, {})["message"] = message
                    save_json(clients_json_path, clients)
        elif "timeout" in request.form or "duration" in request.form:
            if not is_action_allowed("timeout", account):
                return jsonify({"error": "Forbidden"}), 403
            duration = (
                request.form.get("timeout", "").strip()
                or request.form.get("duration", "").strip()
            )
            reason = request.form.get("reason", "").strip()
            seconds = parse_duration_seconds(duration)
            if seconds > 0:
                now = time.time()
                with data_lock:
                    client = clients.setdefault(username, {})
                    client["timeout_reason"] = reason
                    client["timeout_set_at"] = now
                    client["timeout_until"] = now + seconds
                    client["timeout_duration_seconds"] = seconds
                    save_json(clients_json_path, clients)
        else:
            if not is_action_allowed("redirect", account):
                return jsonify({"error": "Forbidden"}), 403
            url = (
                decode_xor_hex(request.form.get("u", "").strip())
                or request.form.get("url", "").strip()
            )
            if url:
                with data_lock:
                    clients.setdefault(username, {})["redirect"] = url
                    save_json(clients_json_path, clients)

        return redirect(url_for("clients_index"))

    @app.route("/audit/log", methods=["POST"])
    def audit_log_client():
        # Accept JSON from browser to log client-side events (login/logout, etc.)
        if not request.is_json:
            return jsonify({"error": "JSON required"}), 400
        account = get_authenticated_account(accounts_path)
        if not account:
            return jsonify({"error": "Unauthorized"}), 401
        data = request.get_json() or {}
        performer = account["label"]
        action = data.get("action", "")
        target = data.get("target", "system")
        details = data.get("details", {})
        success = data.get("success", True)
        if audit_mod:
            try:
                audit_mod.append_audit(
                    performer, action, target, details, success, request
                )
            except Exception as e:
                print("Audit log error:", e)
        return jsonify({"ok": True})

    @app.route("/audit/login", methods=["POST"])
    def audit_login():
        if not request.is_json:
            return jsonify({"error": "JSON required"}), 400
        data = request.get_json() or {}
        password = (data.get("password") or "").strip()
        if not password:
            return jsonify({"error": "Password required"}), 400
        accounts = load_accounts(accounts_path)
        account = find_account_by_password(password, accounts)
        if not account:
            return jsonify({"error": "Invalid password"}), 403
        token = str(uuid.uuid4())
        expiry = time.time() + (60 * 60 * 8)  # 8 hours
        with _audit_lock:
            _audit_sessions[token] = expiry
        resp = jsonify({"ok": True})
        resp.set_cookie(
            "audit_session",
            token,
            max_age=60 * 60 * 8,
            httponly=True,
            samesite="Lax",
            secure=cookie_secure,
        )
        return resp

    @app.route("/audit/logout")
    def audit_logout():
        resp = make_response(redirect(url_for("audit_viewer")))
        resp.set_cookie("audit_session", "", max_age=0, expires=0, secure=cookie_secure)
        return resp

    @app.route("/audit")
    def audit_page():
        # Require login; check for a valid session via clients cookie? No auth yet.
        # We'll use the same simple password check via query param? Better: reuse client-side logic,
        # but for simplicity we'll allow direct access (local only)
        return redirect(url_for("audit_viewer"))

    @app.route("/audit/view")
    def audit_viewer():
        # Check authentication
        token = request.cookies.get("audit_session")
        authenticated = False
        if token:
            with _audit_lock:
                expiry = _audit_sessions.get(token)
                if expiry and time.time() <= expiry:
                    authenticated = True
                    # Optionally refresh expiry
                    _audit_sessions[token] = time.time() + 60 * 60 * 8
                elif token in _audit_sessions:
                    _audit_sessions.pop(token, None)
        if not authenticated:
            return Response(AUDIT_LOGIN_HTML, content_type="text/html")
        with open(BASE_DIR / "audit_viewer.html") as f:
            return Response(f.read(), content_type="text/html")

    @app.route("/audit.json")
    def audit_json():
        # Require authentication
        token = request.cookies.get("audit_session")
        authenticated = False
        if token:
            with _audit_lock:
                expiry = _audit_sessions.get(token)
                if expiry and time.time() <= expiry:
                    authenticated = True
                    _audit_sessions[token] = time.time() + 60 * 60 * 8
                elif token in _audit_sessions:
                    _audit_sessions.pop(token, None)
        if not authenticated:
            return jsonify({"error": "Unauthorized"}), 401
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)
        exclude_system = request.args.get("exclude_system", "false").lower() == "true"
        entries = (
            audit_mod.load_audit_entries(limit, offset, exclude_system)
            if audit_mod
            else []
        )
        total = len(entries)
        return jsonify({"entries": entries, "total": total})

    @app.route("/client_status")
    def client_status():
        user = request.args.get("user", "").strip()
        current_url = (
            decode_xor_hex(request.args.get("u", "").strip())
            or request.args.get("url", "").strip()
        )

        if not user:
            return jsonify(
                {
                    "banned": False,
                    "redirect": None,
                    "image": None,
                    "message": None,
                    "note": None,
                    "timeout_reason": None,
                    "timeout_set_at": None,
                    "timeout_until": None,
                    "timeout_duration_seconds": None,
                    "timeout_remaining_seconds": None,
                    "timeout_active": False,
                    "effect": None,
                    "last_ping": None,
                    "current_url": None,
                    "lockdown": lockdown_state["active"],
                }
            )

        with data_lock:
            if user not in clients:
                clients[user] = {
                    "banned": False,
                    "redirect": None,
                    "image": None,
                    "message": None,
                    "note": "",
                    "timeout_reason": None,
                    "timeout_set_at": None,
                    "timeout_until": None,
                    "timeout_duration_seconds": None,
                    "effect": "",
                    "last_ping": None,
                    "current_url": None,
                }

            status = clients[user]

            timeout_until = status.get("timeout_until")
            timeout_active = False
            timeout_remaining = None
            if timeout_until:
                try:
                    timeout_remaining = max(0, int(timeout_until - time.time()))
                    timeout_active = timeout_remaining > 0
                except (TypeError, ValueError):
                    timeout_until = None

            if timeout_until and not timeout_active:
                clients[user]["timeout_reason"] = None
                clients[user]["timeout_set_at"] = None
                clients[user]["timeout_until"] = None
                clients[user]["timeout_duration_seconds"] = None
                timeout_remaining = 0
                save_json(clients_json_path, clients)

            redirect_url = status.get("redirect")
            if redirect_url:
                clients[user]["redirect"] = None

            image_b64 = status.get("image")
            if image_b64:
                clients[user]["image"] = None

            message_text = status.get("message")
            if message_text:
                clients[user]["message"] = None

            note_text = status.get("note")

            last_ping = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            clients[user]["last_ping"] = last_ping
            clients[user]["current_url"] = current_url or status.get("current_url")

            save_json(clients_json_path, clients)

            lockdown_active = lockdown_state["active"]
            
        return jsonify(
            {
                "banned": status.get("banned", False),
                "redirect": redirect_url,
                "image": image_b64,
                "message": message_text,
                "note": note_text,
                "timeout_reason": status.get("timeout_reason"),
                "timeout_set_at": status.get("timeout_set_at"),
                "timeout_until": status.get("timeout_until"),
                "timeout_duration_seconds": status.get("timeout_duration_seconds"),
                "timeout_remaining_seconds": timeout_remaining,
                "timeout_active": timeout_active,
                "effect": normalize_client_effect(status.get("effect")),
                "last_ping": last_ping,
                "current_url": clients[user]["current_url"],
                "lockdown": lockdown_active,
            }
        )

    @app.route("/lockdown", methods=["POST"])
    def lockdown():
        account, error = require_auth("lockdown")
        if error:
            return error
        action = request.form.get("action")

        if action == "on":
            lockdown_state["active"] = True
        else:
            lockdown_state["active"] = False

        return jsonify(
            {
                "success": True,
                "lockdown": lockdown_state["active"],
            }
        )

    @app.route("/lockdown.json")
    def lockdown_status():
        return jsonify(
            {
                "active": lockdown_state["active"]
            }
        )
