"""The first-steps checklist on Home for new accounts: five things to try, each ticked from what the user has really
done (not from clicking the step). Dismissed for good from Home; gone by itself once every step is done or the
account is a month old. Stored in app_settings as firststeps:<uid> (dismissed, and whether a deep dive was opened)."""
import json
import threading
from datetime import datetime, timedelta, timezone

from . import db, holdings, newsletter_prefs, push
from .plans import _dt

KEY = "firststeps:"
NEW_FOR = timedelta(days=30)
EVER = "2000-01-01T00:00:00+00:00"

# id, what to do, where to do it
STEPS = [
    ("backtest", "Run a backtest on a ready-made idea", "/new"),
    ("watchlist", "Add a stock to your watchlist", "/research"),
    ("deepdive", "Open a company deep dive", "/research/IN/RELIANCE/deep"),
    ("paper", "Start paper trading", "/paper"),
    ("alerts", "Set up newsletters or phone alerts", "/account#newsletters"),
]

_marked: set[tuple[str, str]] = set()      # (uid, step) already stored, so a busy page doesn't write on every visit
_lock = threading.Lock()


def state(uid: str) -> dict:
    try:
        v = json.loads(db.get_setting(KEY + uid) or "{}")
    except (ValueError, TypeError):
        v = {}
    return v if isinstance(v, dict) else {}


def _save(uid: str, changes: dict) -> dict:
    with _lock:
        st = {**state(uid), **changes}
        db.set_setting(KEY + uid, json.dumps(st))
        return st


def mark(uid: str, step: str):
    """Remember a step that leaves no other trace (opening a deep dive)."""
    if (uid, step) in _marked:
        return
    if not state(uid).get(step):
        _save(uid, {step: True})
    if len(_marked) > 50000:
        _marked.clear()
    _marked.add((uid, step))


def dismiss(uid: str, dismissed: bool = True) -> dict:
    return _save(uid, {"dismissed": bool(dismissed)})


def _watchlist(uid: str) -> bool:
    try:
        return bool(json.loads(db.get_setting(f"watchlist:{uid}") or "{}").get("items"))
    except (ValueError, TypeError, AttributeError):
        return False


def has_activity(uid: str) -> bool:
    """Whether the account has done anything yet: holdings, a notebook, a paper session or a watchlist. The "What brings
    you here?" question is for an empty account only; an established one is never asked. A failed look counts as activity
    (better to skip the question than to ask someone who has been here for months)."""
    try:
        return bool(holdings.load(uid)["items"]) or _watchlist(uid) or db.has_strategy(uid) or bool(db.user_sessions(uid, 1))
    except Exception:
        return True


def done(profile: dict, st: dict | None = None) -> dict[str, bool]:
    """Which steps the user has done, from their own data."""
    uid = profile["id"]
    st = state(uid) if st is None else st
    news = newsletter_prefs.get(uid)
    return {
        "backtest": db.count_usage(uid, "backtest", EVER) > 0,
        "watchlist": _watchlist(uid),
        "deepdive": bool(st.get("deepdive")),
        "paper": bool(db.user_sessions(uid, 1)),
        "alerts": (any(v != "off" for v in news.values()) or bool(profile.get("telegram_chat_id"))
                   or bool(push.devices(uid))),
    }


def is_new(profile: dict, now: datetime | None = None) -> bool:
    try:
        return (now or datetime.now(timezone.utc)) - _dt(profile["created_at"]) < NEW_FOR
    except (KeyError, TypeError, ValueError):
        return False


def view(profile: dict, now: datetime | None = None) -> dict:
    """What Home shows: the steps with their ticks, and whether to show the checklist at all."""
    st = state(profile["id"])
    dismissed = bool(st.get("dismissed"))
    if dismissed or not is_new(profile, now):
        return {"show": False, "dismissed": dismissed, "done": 0, "steps": []}
    ticks = done(profile, st)
    steps = [{"id": i, "title": t, "to": to, "done": ticks[i]} for i, t, to in STEPS]
    n = sum(s["done"] for s in steps)
    return {"show": n < len(steps), "dismissed": False, "done": n, "steps": steps}
