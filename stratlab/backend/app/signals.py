"""Forward-testing outside signals: each user's secret webhook URL, the small JSON a signal is, and the log of what
arrived. A signal only ever moves a paper position in one of the user's own signal sessions (signal_session.py); it
never places a real order, never runs anything it carries, and never fetches anything it names.

The URL: /hooks/signal/<token>, one per user, made with secrets.token_urlsafe (256 bits). Only a SHA-256 of the token
is stored (app_settings signal_hook:<hash> -> the user; signal_hooks:<uid> -> the hash, when it was made and its first
four characters to recognise it by), so the database never holds a working URL. Making a new one stops the old one at
once; so does turning it off.

A signal: a JSON object of at most MAX_BODY bytes, with only these keys:
    {"session": "<the session's id>", "action": "buy" | "sell" | "exit", "qty": 1,
     "symbol": "NIFTY 50", "id": "tv-123", "price": 24510.5, "time": "2026-10-05T09:20:00Z", "note": "breakout"}
session and action are required; qty is required for buy and sell (shares, or lots for F&O) and not allowed for
exit; symbol, when sent, must be the session's (a guard against pasting the URL into the wrong alert); id is the
alert's own id, and a repeat of one already seen is ignored; price and time are what the alert says, kept only to
compare with StratLab's own fill and arrival time. Anything else (another key, a nested value, NaN, a duplicate key,
a number where text belongs) rejects the whole signal.

Limits per URL: PER_MINUTE signals a minute and PER_DAY a day; per address, MISSES_PER_MINUTE requests with a wrong
token. Over a limit the request is refused (429) without touching the session."""
import hashlib
import json
import math
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from . import db

HOOK = "signal_hook:"            # signal_hook:<sha256 of the token> -> {"uid", "created"}
USER = "signal_hooks:"           # signal_hooks:<uid> -> {"hash", "created", "hint", "last_used"}
LOG = "signal_log:"              # signal_log:<uid> -> the latest deliveries that never reached a session
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
MAX_BODY = 2048
PER_MINUTE = 30
PER_DAY = 1000
MISSES_PER_MINUTE = 20
LOG_KEEP = 100
KEYS = {"session", "action", "qty", "symbol", "id", "price", "time", "note"}
ACTIONS = ("buy", "sell", "exit")
ID = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
SESSION = re.compile(r"^[0-9a-fA-F-]{36}$")
STALE_SECONDS = 600              # an alert this old on arrival is refused (a replayed or queued one)
LATE_SECONDS = 60                # one older than this is filled but marked late
MAX_QTY = 1_000_000


class SignalError(Exception):
    """A refused signal: the HTTP status, a short code and the reason in words (shown in the user's log)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---------- the URL ----------
def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current(uid: str) -> dict | None:
    """The user's URL as the page shows it (never the token itself): when it was made, its first characters, and when a
    signal last arrived."""
    row = db.json_value(db.get_setting(USER + uid), {})
    if not isinstance(row.get("hash"), str):
        return None
    return {"created": row.get("created"), "hint": row.get("hint"), "last_used": row.get("last_used")}


def issue(uid: str) -> str:
    """A new URL token for the user; the old one stops working at once. The token is returned this once only."""
    revoke(uid)
    token = secrets.token_urlsafe(32)
    h = digest(token)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.set_setting(HOOK + h, json.dumps({"uid": uid, "created": now}))
    db.set_setting(USER + uid, json.dumps({"hash": h, "created": now, "hint": token[:4], "last_used": None}))
    return token


def revoke(uid: str) -> bool:
    """Turn the user's URL off. True when there was one."""
    row = db.json_value(db.get_setting(USER + uid), {})
    if not row:
        return False
    if isinstance(row.get("hash"), str):
        db.delete_setting(HOOK + row["hash"])
    db.delete_setting(USER + uid)
    return True


def owner(token: str) -> str | None:
    """The user a token belongs to, or None (a malformed, wrong or turned-off token)."""
    if not isinstance(token, str) or not TOKEN.match(token):
        return None
    h = digest(token)
    row = db.json_value(db.get_setting(HOOK + h), {})
    if not isinstance(row.get("uid"), str):
        return None
    mine = db.json_value(db.get_setting(USER + row["uid"]), {})       # turned off or replaced: both rows must agree
    if not secrets.compare_digest(str(mine.get("hash", "")), h):
        return None
    return row["uid"]


def touch(uid: str):
    """Note when a signal last arrived (shown beside the URL)."""
    row = db.json_value(db.get_setting(USER + uid), {})
    if row.get("hash"):
        row["last_used"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.set_setting(USER + uid, json.dumps(row))


# ---------- limits ----------
class Limits:
    """Signals per URL (a minute and a day) and wrong tokens per address, counted in memory."""

    def __init__(self):
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _take(self, key: str, n: int, window: float, now: float) -> bool:
        with self._lock:
            if len(self._hits) > 20000:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < 86400}
            hits = [t for t in self._hits.get(key, []) if now - t < window]
            ok = len(hits) < n
            if ok:
                hits.append(now)
            self._hits[key] = hits
            return ok

    def signal(self, token_hash: str, now: float | None = None) -> str | None:
        """None when this URL may deliver one more signal now, else why not."""
        now = time.time() if now is None else now
        if not self._take("m:" + token_hash, PER_MINUTE, 60, now):
            return f"More than {PER_MINUTE} signals in a minute on this URL."
        if not self._take("d:" + token_hash, PER_DAY, 86400, now):
            return f"More than {PER_DAY} signals in a day on this URL."
        return None

    def miss(self, address: str, now: float | None = None) -> bool:
        """Count a wrong token from an address; False once it has sent too many this minute."""
        return self._take("x:" + address, MISSES_PER_MINUTE, 60, time.time() if now is None else now)

    def misses_left(self, address: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            return len([t for t in self._hits.get("x:" + address, []) if now - t < 60]) < MISSES_PER_MINUTE

    def clear(self):
        with self._lock:
            self._hits.clear()


limits = Limits()


# ---------- the payload ----------
def _no_constants(name: str):
    raise ValueError(f"{name} isn't a number")


def _pairs(items: list) -> dict:
    out = {}
    for k, v in items:
        if k in out:
            raise ValueError(f"{k} appears twice")
        out[k] = v
    return out


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _text(v, n: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", v).strip()[:n]


def parse(body: bytes) -> dict:
    """The signal in a request body, checked strictly. Raises SignalError (400) with the reason."""
    if len(body) > MAX_BODY:
        raise SignalError(413, "too_large", f"A signal is at most {MAX_BODY} bytes.")
    if not body.strip():
        raise SignalError(400, "empty", "The signal was empty.")
    try:
        text = body.decode("utf-8")
        data = json.loads(text, parse_constant=_no_constants, object_pairs_hook=_pairs)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise SignalError(400, "not_json", "The signal isn't valid JSON. Send an object such as {\"session\": \"…\", \"action\": \"buy\", \"qty\": 1}.") from None
    if not isinstance(data, dict):
        raise SignalError(400, "not_object", "The signal must be a JSON object.")
    extra = sorted(set(data) - KEYS)
    if extra:
        raise SignalError(400, "unknown_key", f"Unknown field{'s' if len(extra) > 1 else ''}: {', '.join(k[:20] for k in extra[:3])}.")
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            raise SignalError(400, "bad_value", f"{k} must be a single value.")
    sid = data.get("session")
    if not isinstance(sid, str) or not SESSION.match(sid):
        raise SignalError(400, "no_session", "session must be the id of one of your signal sessions.")
    action = data.get("action")
    if not isinstance(action, str) or action.strip().lower() not in ACTIONS:
        raise SignalError(400, "bad_action", "action must be buy, sell or exit.")
    action = action.strip().lower()
    out: dict = {"session": sid.lower(), "action": action}
    qty = data.get("qty")
    if action == "exit":
        if qty is not None:
            raise SignalError(400, "bad_qty", "exit closes the whole position, so it takes no qty.")
    else:
        if not _num(qty) or qty <= 0 or qty > MAX_QTY:
            raise SignalError(400, "bad_qty", f"qty must be a number above 0 and at most {MAX_QTY:,}.")
        out["qty"] = float(qty)
    if "symbol" in data:
        if not isinstance(data["symbol"], str) or not 0 < len(data["symbol"].strip()) <= 40:
            raise SignalError(400, "bad_symbol", "symbol must be text of up to 40 characters.")
        out["symbol"] = _text(data["symbol"], 40).upper()
    if "id" in data:
        if not isinstance(data["id"], str) or not ID.match(data["id"]):
            raise SignalError(400, "bad_id", "id must be up to 64 letters, digits or . _ : -")
        out["id"] = data["id"]
    if "price" in data:
        if not _num(data["price"]) or data["price"] <= 0 or data["price"] > 1e9:
            raise SignalError(400, "bad_price", "price must be a number above 0.")
        out["price"] = float(data["price"])
    if "time" in data:
        out["time"] = _when(data["time"])
    if "note" in data:
        if not isinstance(data["note"], str):
            raise SignalError(400, "bad_note", "note must be text.")
        out["note"] = _text(data["note"], 120)
    return out


def _when(v) -> str:
    """The alert's own time as ISO 8601 UTC, from ISO text with an offset or seconds/milliseconds since 1970."""
    try:
        if _num(v):
            secs = v / 1000 if v > 1e11 else v
            t = datetime.fromtimestamp(secs, timezone.utc)
        elif isinstance(v, str) and len(v) <= 40:
            t = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            if t.tzinfo is None:
                raise ValueError
        else:
            raise ValueError
    except (ValueError, OverflowError, OSError):
        raise SignalError(400, "bad_time", "time must be ISO 8601 with a time zone (as TradingView's {{timenow}}) or seconds since 1970.") from None
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def lateness(sig: dict, arrived: datetime) -> float | None:
    """Seconds between the alert's own time and its arrival (None when it sent no time)."""
    if not sig.get("time"):
        return None
    return (arrived - datetime.fromisoformat(sig["time"])).total_seconds()


# ---------- the log of signals that reached no session ----------
def log_miss(uid: str, entry: dict):
    """Keep a refused delivery where the user can see it (the session's own log keeps the ones that reached it)."""
    rows = db.json_value(db.get_setting(LOG + uid), [])
    rows = (rows if isinstance(rows, list) else [])[-(LOG_KEEP - 1):] + [entry]
    db.set_setting(LOG + uid, json.dumps(rows, separators=(",", ":")))


def misses(uid: str) -> list[dict]:
    rows = db.json_value(db.get_setting(LOG + uid), [])
    return [r for r in rows if isinstance(r, dict)][-LOG_KEEP:] if isinstance(rows, list) else []


def forget(uid: str):
    """The URL and the log, for "delete my data"."""
    revoke(uid)
    db.delete_setting(LOG + uid)
