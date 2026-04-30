from flask import jsonify, request

from account_auth import (
    clear_authenticated_account,
    find_account_by_password,
    get_authenticated_account,
    load_accounts,
    serialize_account_session,
    set_authenticated_account,
)


def register_routes(app, state):
    audit_mod = state.get("audit")
    accounts_path = state.get("accounts_json_path")

    def audit_log(performer, action, target="system", details=None, success=True):
        if not audit_mod:
            return
        try:
            audit_mod.append_audit(
                performer, action, target, details or {}, success, request
            )
        except Exception as exc:
            print("Audit log error:", exc)

    @app.route("/auth/login", methods=["POST"])
    def auth_login():
        if not request.is_json:
            return jsonify({"error": "JSON required"}), 400

        data = request.get_json() or {}
        password = (data.get("password") or "").strip()
        if not password:
            return jsonify({"error": "Password required"}), 400

        accounts = load_accounts(accounts_path)
        account = find_account_by_password(password, accounts)
        if not account:
            audit_log(
                "anonymous",
                "login_attempt",
                "system",
                {"reason": "wrong_password"},
                False,
            )
            return jsonify({"error": "Invalid password"}), 403

        session_payload = set_authenticated_account(account)
        audit_log(
            account["label"],
            "login",
            "system",
            {"permissions": account["mode"], "admin": account["admin"]},
            True,
        )
        response = jsonify({"ok": True, "session": session_payload})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/auth/session")
    def auth_session():
        account = get_authenticated_account(accounts_path)
        if not account:
            response = jsonify({"authenticated": False})
            response.headers["Cache-Control"] = "no-store"
            return response

        response = jsonify(serialize_account_session(account, login_at=account.get("loginAt")))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/auth/logout", methods=["POST", "GET"])
    def auth_logout():
        account = get_authenticated_account(accounts_path)
        clear_authenticated_account()
        if account:
            audit_log(account["label"], "logout", "system", {}, True)
        response = jsonify({"ok": True})
        response.headers["Cache-Control"] = "no-store"
        return response
