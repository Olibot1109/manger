import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

BASE_DIR = Path(__file__).resolve().parent
AUDIT_FILE = BASE_DIR / "audit.jsonl"
MAX_AUDIT_ENTRIES = 3000
_data_lock = RLock()

# System actions we keep: auth events (except auto_login) + bulk admin operations
_SYSTEM_KEEP = {
    "login",
    "logout",
    "login_attempt",
    "delete_all",
    "redirect_all",
    "message_all",
    "question_all",
    "image_all",
    "show_id_all",
}


def load_audit_entries(limit=1000, offset=0, exclude_system=False):
    entries = []
    if not AUDIT_FILE.exists():
        return entries
    with _data_lock:
        try:
            with open(AUDIT_FILE, "r") as f:
                all_lines = [line.strip() for line in f if line.strip()]
            # Keep only last MAX_AUDIT_ENTRIES
            lines = all_lines[-MAX_AUDIT_ENTRIES:]
            start = max(0, len(lines) - offset - limit)
            end = len(lines) - offset
            for line in lines[start:end]:
                try:
                    entry = json.loads(line)
                    if exclude_system:
                        target = entry.get("target")
                        action = entry.get("action")
                        # Skip system entries unless they're in the keep list
                        if target == "system" and action not in _SYSTEM_KEEP:
                            continue
                    entries.append(entry)
                except Exception:
                    continue
        except Exception as e:
            print("Error loading audit log:", e)
    return entries


def append_audit(
    performer, action, target="system", details=None, success=True, request=None
):
    # Filter out noisy system-targeted events — only keep auth & bulk admin actions
    if target == "system":
        # Allow auth security events and bulk admin operations
        # Note: auto_login is excluded (session restoration noise)
        if action not in {
            "login",
            "logout",
            "login_attempt",
            "delete_all",
            "redirect_all",
            "message_all",
            "question_all",
            "image_all",
            "show_id_all",
        }:
            return
    entry = {
        "id": f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "performer": str(performer)[:100],
        "action": str(action)[:100],
        "target": str(target)[:200],
        "details": details or {},
        "success": bool(success),
        "ip": "",
    }
    if request:
        entry["ip"] = request.remote_addr or request.environ.get("REMOTE_ADDR", "")[:45]
    try:
        with _data_lock:
            with open(AUDIT_FILE, "a") as f:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
            # Rotate if too large
            _rotate_if_needed()
    except Exception as e:
        print("Failed to write audit entry:", e)


def _rotate_if_needed():
    try:
        if AUDIT_FILE.exists() and AUDIT_FILE.stat().st_size > 50 * 1024 * 1024:
            # Archive old and clear
            backup = AUDIT_FILE.with_suffix(".jsonl.bak")
            AUDIT_FILE.rename(backup)
            # Keep only last MAX_AUDIT_ENTRIES in backup and rewrite trimmed
            with open(backup, "r") as f:
                lines = [l for l in f if l.strip()]
            trimmed = (
                lines[-MAX_AUDIT_ENTRIES // 2 :]
                if len(lines) > MAX_AUDIT_ENTRIES // 2
                else lines
            )
            with open(AUDIT_FILE, "w") as f:
                f.writelines(trimmed)
    except Exception as e:
        print("Audit rotate error:", e)
