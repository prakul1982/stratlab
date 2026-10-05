"""Keys for StratLab in your AI assistant (the MCP server, mcp_server.py): each user's revocable keys and the log of
every tool call made with them.

A key is shown once when it's made; only its SHA-256 is kept. app_settings rows:
  mcpkey:<sha256>  = {"uid", "id"}                         finds the account a key belongs to
  mcp:<uid>        = {"keys": [{id, name, paper, hint, created_at, last_used_at, revoked_at}]}
  mcplog:<uid>     = {"items": [{at, key_id, key, tool, args, result, detail, ms}]}  newest first, capped
Revoking deletes the mcpkey: row and marks the key revoked; a key works only while both say it's live."""
import hashlib
import json
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from . import db

PREFIX = "slm_"
KEY_INDEX = "mcpkey:"
KEY_USER = "mcp:"
KEY_LOG = "mcplog:"
MAX_KEYS = 5                 # live keys per account
MAX_KEPT = 20                # keys listed, revoked ones included (the oldest revoked ones go first)
MAX_LOG = 300                # tool calls kept in the log
NAME_MAX = 40
TOUCH_EVERY = 300            # seconds between saves of a key's "last used" time
TOKEN_RX = re.compile(r"^slm_[A-Za-z0-9_-]{40,60}$")
ID_RX = re.compile(r"^[a-f0-9]{12}$")

_lock = threading.Lock()
_touched: dict[str, float] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _row(uid: str) -> dict:
    raw = db.json_value(db.get_setting(KEY_USER + uid), {})
    keys = raw.get("keys")
    return {"keys": [k for k in keys if isinstance(k, dict)] if isinstance(keys, list) else []}


def _save(uid: str, row: dict) -> None:
    db.set_setting(KEY_USER + uid, json.dumps(row))


def view(k: dict) -> dict:
    """A key as the Account page shows it: never its hash."""
    return {f: k.get(f) for f in ("id", "name", "paper", "hint", "created_at", "last_used_at", "revoked_at")}


def keys(uid: str) -> list[dict]:
    """Live keys first (newest first), then revoked ones."""
    ks = _row(uid)["keys"]
    live = sorted((k for k in ks if not k.get("revoked_at")), key=lambda k: k.get("created_at") or "", reverse=True)
    gone = sorted((k for k in ks if k.get("revoked_at")), key=lambda k: k.get("revoked_at") or "", reverse=True)
    return [view(k) for k in live + gone]


def clean_name(name: str) -> str:
    """A key's label: printable text, trimmed; control characters and angle brackets dropped."""
    s = "".join(ch for ch in str(name or "") if ch.isprintable() and ch not in "<>")
    return " ".join(s.split())[:NAME_MAX]


class KeyLimit(Exception):
    pass


def create(uid: str, name: str, paper: bool) -> tuple[str, dict]:
    """A new key: (the key itself, shown once; its row). Raises KeyLimit past MAX_KEYS live keys."""
    label = clean_name(name) or "AI assistant"
    with _lock:
        row = _row(uid)
        if sum(1 for k in row["keys"] if not k.get("revoked_at")) >= MAX_KEYS:
            raise KeyLimit(f"You can have {MAX_KEYS} keys at a time. Revoke one first.")
        token = PREFIX + secrets.token_urlsafe(36)
        k = {"id": secrets.token_hex(6), "name": label, "paper": bool(paper), "hint": token[-4:], "hash": digest(token),
             "created_at": _now(), "last_used_at": None, "revoked_at": None}
        db.set_setting(KEY_INDEX + k["hash"], json.dumps({"uid": uid, "id": k["id"]}))
        row["keys"].append(k)
        live = [x for x in row["keys"] if not x.get("revoked_at")]
        gone = sorted((x for x in row["keys"] if x.get("revoked_at")), key=lambda x: x.get("revoked_at") or "", reverse=True)
        row["keys"] = live + gone[:max(0, MAX_KEPT - len(live))]
        _save(uid, row)
    return token, view(k)


def revoke(uid: str, kid: str) -> bool:
    """Revoke one of the user's keys at once. False when they have no such live key."""
    if not ID_RX.match(kid or ""):
        return False
    with _lock:
        row = _row(uid)
        k = next((x for x in row["keys"] if x.get("id") == kid and not x.get("revoked_at")), None)
        if not k:
            return False
        db.delete_setting(KEY_INDEX + str(k.get("hash")))
        k["revoked_at"] = _now()
        _save(uid, row)
    return True


def resolve(token: str) -> tuple[str, dict] | None:
    """(user id, key) for a live key, else None. Anything not shaped like a key never reaches the database."""
    if not isinstance(token, str) or not TOKEN_RX.match(token):
        return None
    h = digest(token)
    idx = db.json_value(db.get_setting(KEY_INDEX + h), {})
    uid, kid = idx.get("uid"), idx.get("id")
    if not isinstance(uid, str) or not isinstance(kid, str):
        return None
    k = next((x for x in _row(uid)["keys"] if x.get("id") == kid), None)
    if not k or k.get("revoked_at") or not secrets.compare_digest(str(k.get("hash") or ""), h):
        return None
    return uid, k


def touch(uid: str, kid: str) -> None:
    """Note when a key was last used, at most every few minutes."""
    now = time.time()
    with _lock:
        if now - _touched.get(kid, 0) < TOUCH_EVERY:
            return
        _touched[kid] = now
        if len(_touched) > 5000:
            _touched.clear()
        row = _row(uid)
        k = next((x for x in row["keys"] if x.get("id") == kid and not x.get("revoked_at")), None)
        if not k:
            return
        k["last_used_at"] = _now()
        _save(uid, row)


def log(uid: str, key: dict, tool: str, args, result: str, detail: str = "", ms: int = 0) -> None:
    """Add a tool call to the user's log (newest first). A failure to log never fails the call."""
    try:
        text = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str) if args else ""
    except (TypeError, ValueError):
        text = ""
    entry = {"at": _now(), "key_id": key.get("id"), "key": key.get("name"), "tool": str(tool)[:64],
             "args": text[:300], "result": result, "detail": str(detail or "")[:200], "ms": int(ms)}
    try:
        with _lock:
            items = entries(uid)
            db.set_setting(KEY_LOG + uid, json.dumps({"items": ([entry] + items)[:MAX_LOG]}))
    except Exception as e:
        print("assistant log failed:", str(e)[:120])


def entries(uid: str) -> list[dict]:
    raw = db.json_value(db.get_setting(KEY_LOG + uid), {})
    items = raw.get("items")
    return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []
