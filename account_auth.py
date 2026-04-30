from __future__ import annotations

import json
import threading
import time
from hmac import compare_digest
from hashlib import sha256
from pathlib import Path

from flask import session

BASE_DIR = Path(__file__).resolve().parent
AUTH_SESSION_KEY = "manger_auth"

_ACCOUNT_LOCK = threading.RLock()
_ACCOUNT_CACHE = {"path": None, "mtime": None, "accounts": []}

_ACTION_ALIASES = {
    "note": "notes",
    "notes": "notes",
}


def _canonical_action_name(action):
    action = (action or "").strip()
    return _ACTION_ALIASES.get(action, action)


def _canonical_action_list(values):
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        if value is None:
            continue
        text = _canonical_action_name(str(value))
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _fingerprint_account(account):
    payload = json.dumps(
        {
            "label": account["label"],
            "admin": account["admin"],
            "mode": account["mode"],
            "allowedActions": account["allowedActions"],
            "deniedActions": account["deniedActions"],
            "password": account["password"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _normalize_account(raw):
    if not isinstance(raw, dict):
        return None

    password = str(raw.get("password", "")).strip()
    label = str(raw.get("label", "")).strip()
    mode = str(raw.get("mode", "deny")).strip().lower()
    admin = bool(raw.get("admin", False))
    allowed_actions = _canonical_action_list(raw.get("allowedActions"))
    denied_actions = _canonical_action_list(raw.get("deniedActions"))

    if not password or not label:
        return None
    if mode not in {"allow", "deny"}:
        mode = "deny"

    account = {
        "password": password,
        "label": label,
        "admin": admin,
        "mode": mode,
        "allowedActions": allowed_actions,
        "deniedActions": denied_actions,
    }
    account["fingerprint"] = _fingerprint_account(account)
    return account


def load_accounts(accounts_path=None, force=False):
    path = Path(accounts_path) if accounts_path else BASE_DIR / "accounts.json"
    if not path.exists():
        return []

    with _ACCOUNT_LOCK:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return []

        cached_path = _ACCOUNT_CACHE["path"]
        cached_mtime = _ACCOUNT_CACHE["mtime"]
        if not force and cached_path == str(path) and cached_mtime == mtime:
            return list(_ACCOUNT_CACHE["accounts"])

        try:
            raw_accounts = json.loads(path.read_text())
        except Exception:
            raw_accounts = []

        accounts = []
        if isinstance(raw_accounts, list):
            for raw in raw_accounts:
                account = _normalize_account(raw)
                if account:
                    accounts.append(account)

        _ACCOUNT_CACHE["path"] = str(path)
        _ACCOUNT_CACHE["mtime"] = mtime
        _ACCOUNT_CACHE["accounts"] = accounts
        return list(accounts)


def find_account_by_password(password, accounts=None):
    password = str(password or "").strip()
    if not password:
        return None

    if accounts is None:
        accounts = load_accounts()

    for account in accounts:
        if compare_digest(account["password"], password):
            return account
    return None


def get_authenticated_account(accounts_path=None):
    payload = session.get(AUTH_SESSION_KEY)
    if not isinstance(payload, dict):
        return None

    accounts = load_accounts(accounts_path)
    fingerprint = payload.get("fingerprint")
    account = None
    for candidate in accounts:
        if candidate["fingerprint"] == fingerprint:
            account = candidate
            break

    if not account:
        session.pop(AUTH_SESSION_KEY, None)
        return None

    login_at = payload.get("loginAt")
    return {
        "label": account["label"],
        "admin": account["admin"],
        "mode": account["mode"],
        "allowedActions": list(account["allowedActions"]),
        "deniedActions": list(account["deniedActions"]),
        "fingerprint": account["fingerprint"],
        "loginAt": login_at,
    }


def serialize_account_session(account, login_at=None):
    return {
        "authenticated": True,
        "label": account["label"],
        "admin": account["admin"],
        "mode": account["mode"],
        "allowedActions": list(account["allowedActions"]),
        "deniedActions": list(account["deniedActions"]),
        "fingerprint": account["fingerprint"],
        "loginAt": login_at if login_at is not None else int(time.time()),
    }


def set_authenticated_account(account):
    payload = serialize_account_session(account, login_at=int(time.time()))
    session[AUTH_SESSION_KEY] = payload
    session.permanent = True
    return payload


def clear_authenticated_account():
    session.pop(AUTH_SESSION_KEY, None)


def is_action_allowed(action_name, account=None):
    account = account or get_authenticated_account()
    if not account:
        return False

    action_name = _canonical_action_name(action_name)
    if not action_name:
        return False

    if account.get("admin"):
        return True

    mode = account.get("mode", "deny")
    allowed_actions = account.get("allowedActions", [])
    denied_actions = account.get("deniedActions", [])

    if mode == "allow":
        return bool(allowed_actions) and action_name in allowed_actions
    return action_name not in denied_actions
