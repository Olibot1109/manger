from base64 import b64encode
from datetime import datetime
from html import escape
from pathlib import Path
import re
import time
import json
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
    send_from_directory,
    url_for,
    abort,
)


BASE_DIR = Path(__file__).resolve().parent
ROUTE_KEY = "manger"
CLIENTS_HTML = (BASE_DIR / "client-manger.html").read_text()
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
  <style>
    body { font-family: Arial, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; }
    input { padding: 8px; font-size: 16px; width: 200px; }
    button { padding: 8px 16px; font-size: 16px; cursor: pointer; }
    .error { color: red; margin-top: 10px; }
  </style>
</head>
<body>
  <h2>Audit Log Access</h2>
  <p>Enter admin password to view audit logs:</p>
  <form id="loginForm">
    <input type="password" id="password" placeholder="Password" required autofocus>
    <button type="submit">Login</button>
  </form>
  <p class="error" id="errorMsg" style="display:none;"></p>
  <p><a href="/clients">Back to Client Manager</a></p>
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
    polls = state.get("polls", {})
    polls_json_path = state.get("polls_json_path")

    def audit_log(performer, action, target="system", details=None, success=True):
        if audit_mod:
            try:
                audit_mod.append_audit(
                    performer, action, target, details or {}, success, request
                )
            except Exception as e:
                print("Audit log error:", e)

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
        return render_template_string(CLIENTS_HTML)

    @app.route("/clients.json")
    def clients_json():
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
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")
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
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")
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
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")
        with data_lock:
            if username in clients:
                del clients[username]
                save_json(clients_json_path, clients)
        audit_log(performer, "delete", username, {}, True)
        return redirect(url_for("clients_index"))

    @app.route("/clients/image", methods=["POST"])
    def send_image_to_client():
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")
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
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")
        message = request.form.get("message", "").strip()

        if username and message:
            with data_lock:
                clients.setdefault(username, {})["message"] = message
                save_json(clients_json_path, clients)
            audit_log(performer, "message", username, {"length": len(message)}, True)

        return redirect(url_for("clients_index"))

    @app.route("/clients/question", methods=["POST"])
    def send_question_to_client():
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")
        question = request.form.get("question", "").strip()
        answer = request.form.get("answer", "").strip().lower()

        if not username:
            return redirect(url_for("clients_index"))

        action_name = None
        details = {}
        with data_lock:
            client = clients.setdefault(username, {})
            if question:
                client["question"] = question
                client["question_answer"] = None
                client["question_asked_at"] = datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                client["question_answered_at"] = None
                save_json(clients_json_path, clients)
                action_name = "question"
                details = {"question": question}
            elif not question and not answer:
                # Clear question if empty question sent
                client["question"] = None
                client["question_answer"] = None
                client["question_asked_at"] = None
                client["question_answered_at"] = None
                save_json(clients_json_path, clients)
                action_name = "question_clear"
            elif answer in {"yes", "no"}:
                client["question_answer"] = answer
                client["question"] = None
                client["question_answered_at"] = datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                save_json(clients_json_path, clients)
                action_name = "question_answer"
                details = {"answer": answer}

        if action_name:
            audit_log(performer, action_name, username, details, True)

        return redirect(url_for("clients_index"))

    @app.route("/clients/timeout", methods=["POST"])
    def send_timeout_to_client():
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")
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
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")

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
        username = request.form.get("username", "").strip()
        performer = request.form.get("performer", "anonymous")
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

    @app.route("/accounts.json")
    def accounts_json():
        accounts_path = BASE_DIR / "accounts.json"
        if accounts_path.exists():
            return send_from_directory(
                BASE_DIR, "accounts.json", mimetype="application/json"
            )
        return jsonify([])

    @app.route("/clients/redirect", methods=["POST"])
    def redirect_client():
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
        username = request.form.get("username", "").strip()
        effect = normalize_client_effect(request.form.get("effect", ""))

        if username:
            with data_lock:
                clients.setdefault(username, {})["effect"] = effect
                save_json(clients_json_path, clients)

        return redirect(url_for("clients_index"))

    @app.route("/clients/<path:subpath>", methods=["POST"])
    def clients_fallback(subpath):
        username = request.form.get("username", "").strip()
        if not username:
            return redirect(url_for("clients_index"))

        if "note" in request.form:
            note = request.form.get("note", "").strip()
            with data_lock:
                clients.setdefault(username, {})["note"] = note
                save_json(clients_json_path, clients)
        elif "effect" in request.form:
            effect = normalize_client_effect(request.form.get("effect", ""))
            with data_lock:
                clients.setdefault(username, {})["effect"] = effect
                save_json(clients_json_path, clients)
        elif "message" in request.form:
            message = request.form.get("message", "").strip()
            if message:
                with data_lock:
                    clients.setdefault(username, {})["message"] = message
                    save_json(clients_json_path, clients)
        elif "question" in request.form:
            question = request.form.get("question", "").strip()
            with data_lock:
                client = clients.setdefault(username, {})
                if question:
                    client["question"] = question
                    client["question_answer"] = None
                    client["question_asked_at"] = datetime.utcnow().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    client["question_answered_at"] = None
                    save_json(clients_json_path, clients)
                else:
                    client["question"] = None
                    client["question_answer"] = None
                    client["question_asked_at"] = None
                    client["question_answered_at"] = None
                    save_json(clients_json_path, clients)
        elif "answer" in request.form:
            answer = request.form.get("answer", "").strip().lower()
            if answer in {"yes", "no"}:
                with data_lock:
                    client = clients.setdefault(username, {})
                    client["question_answer"] = answer
                    client["question"] = None
                    client["question_answered_at"] = datetime.utcnow().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    save_json(clients_json_path, clients)
        elif "timeout" in request.form or "duration" in request.form:
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
        data = request.get_json() or {}
        performer = data.get("performer", "anonymous")
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
        accounts_path = BASE_DIR / "accounts.json"
        if not accounts_path.exists():
            return jsonify({"error": "Accounts not configured"}), 500
        try:
            with open(accounts_path, "r") as f:
                accounts = json.load(f)
            if not isinstance(accounts, list):
                accounts = []
        except Exception:
            accounts = []
        valid = any(
            isinstance(acc, dict) and acc.get("password") == password
            for acc in accounts
        )
        if not valid:
            return jsonify({"error": "Invalid password"}), 403
        token = str(uuid.uuid4())
        expiry = time.time() + (60 * 60 * 8)  # 8 hours
        with _audit_lock:
            _audit_sessions[token] = expiry
        resp = jsonify({"ok": True})
        resp.set_cookie(
            "audit_session", token, max_age=60 * 60 * 8, httponly=True, samesite="Lax"
        )
        return resp

    @app.route("/audit/logout")
    def audit_logout():
        resp = make_response(redirect(url_for("audit_viewer")))
        resp.set_cookie("audit_session", "", max_age=0, expires=0)
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
                    "audio": None,
                    "message": None,
                    "note": None,
                    "question": None,
                    "question_answer": None,
                    "question_asked_at": None,
                    "question_answered_at": None,
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
                    "audio": None,
                    "message": None,
                    "note": "",
                    "question": None,
                    "question_answer": None,
                    "question_asked_at": None,
                    "question_answered_at": None,
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

            audio_b64 = status.get("audio")
            if audio_b64:
                clients[user]["audio"] = None

            message_text = status.get("message")
            if message_text:
                clients[user]["message"] = None

            note_text = status.get("note")
            question_text = status.get("question")
            question_answer = status.get("question_answer")

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
                "audio": audio_b64,
                "message": message_text,
                "note": note_text,
                "question": question_text,
                "question_answer": question_answer,
                "question_asked_at": status.get("question_asked_at"),
                "question_answered_at": status.get("question_answered_at"),
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
        action = request.form.get("action")
        duration_minutes = request.form.get("duration", "").strip()

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
        lockdown_state["active"] = False
        return jsonify(
            {
                "active": lockdown_state["active"]
            }
        )
