"""One record per user for everything they connected, in app_settings under connect:<uid>:

  {"inbox": {"local", "created_at", "pw" (sealed), "last": {at, status, kind, detail}, "confirm": {code, at}, "reminded_at"},
   "kite":  {"token" (sealed), "kite_user", "day", "refreshed_at", "status", "detail"},
   "ibkr":  {"token" (sealed), "query", "synced_at", "status", "detail", "positions", "trades"},
   "docs":  {"epf": {...figures the user confirmed}, "nps": {...}, "ais": {...}}}

An index row connect-inbox:<local> = uid finds the account a forwarding address belongs to. Secrets are sealed (vault.py)
before they get here, and every view that leaves the server goes through public(), which never includes them."""
import json
import threading
from datetime import datetime, timezone

from .. import db

KEY = "connect:"
INDEX = "connect-inbox:"
SECTIONS = ("inbox", "kite", "ibkr", "docs")
_lock = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(uid: str) -> dict:
    got = db.json_value(db.get_setting(KEY + uid), {})
    return {k: v for k, v in got.items() if k in SECTIONS and isinstance(v, dict)}


def save(uid: str, rec: dict) -> None:
    rec = {k: v for k, v in rec.items() if k in SECTIONS and v}
    if rec:
        db.set_setting(KEY + uid, json.dumps(rec, separators=(",", ":")))
    else:
        db.delete_setting(KEY + uid)


def section(uid: str, name: str) -> dict:
    return dict(load(uid).get(name) or {})


def update(uid: str, name: str, **fields) -> dict:
    """Change some fields of one section (None removes a field)."""
    with _lock:
        rec = load(uid)
        sec = dict(rec.get(name) or {})
        for k, v in fields.items():
            if v is None:
                sec.pop(k, None)
            else:
                sec[k] = v
        rec[name] = sec
        save(uid, rec)
        return sec


def drop(uid: str, name: str) -> None:
    """Delete one connection with everything stored for it: tokens, passwords and its address."""
    with _lock:
        rec = load(uid)
        old = rec.pop(name, None)
        if name == "inbox" and old and old.get("local"):
            db.delete_setting(INDEX + old["local"])
        save(uid, rec)


def drop_all(uid: str) -> None:
    for name in SECTIONS:
        drop(uid, name)
    db.delete_setting(KEY + uid)


def everyone() -> list[tuple[str, dict]]:
    """(uid, record) for every user with something connected (for the daily jobs)."""
    out = []
    for key, raw in db.all_settings_with_prefix(KEY):
        uid = key[len(KEY):]
        try:
            rec = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if isinstance(rec, dict) and uid:
            out.append((uid, {k: v for k, v in rec.items() if k in SECTIONS and isinstance(v, dict)}))
    return out
