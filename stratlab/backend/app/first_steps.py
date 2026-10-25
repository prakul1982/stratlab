"""The first-steps checklist on Home for new accounts: four or five things to try, picked by what they came for, each
ticked from what the user has really done (not from clicking the step). Dismissed for good from Home; gone by itself once every step is done or the
account is a month old. Stored in app_settings as firststeps:<uid> (dismissed, and whether a deep dive was opened)."""
import json
import threading
from datetime import datetime, timedelta, timezone

from . import alerts, db, holdings, money_networth, newsletter_prefs, push, tax_lots
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
    ("alerts", "Set up newsletters or phone alerts", "/settings#notifications"),
    ("holdings", "Add your holdings from your broker's file", "/holdings"),
    ("networth", "Add something you own to your net worth", "/money/net-worth"),
    ("tax", "Upload a tradebook for this year's tax estimate", "/tax-report"),
]
# the steps for what the person said they came for (Settings → What you see first): someone here for their money is
# asked to add holdings, not to backtest (DI-008). Trade, and no answer yet, keep the strategy lab's five.
BY_FOCUS = {
    "trade": ("backtest", "watchlist", "deepdive", "paper", "alerts"),
    "invest": ("watchlist", "deepdive", "holdings", "alerts"),
    "money": ("holdings", "networth", "tax", "alerts"),
    "both": ("backtest", "watchlist", "deepdive", "holdings", "alerts"),
}

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
        return bool(holdings.load(uid)["items"]) or _watchlist(uid) or db.has_strategy(uid) or bool(db.user_sessions(uid, 1, running=False))
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
        "paper": bool(db.user_sessions(uid, 1, running=False)),
        # done once something will really arrive: a newsletter only goes to a confirmed email, a Telegram chat only once its
        # code is entered (DP2-030: Weekly chosen with an unconfirmed email ticked it)
        "alerts": ((any(v != "off" for v in news.values()) and alerts.email_confirmed(profile))
                   or (bool(profile.get("telegram_chat_id")) and alerts.telegram_verified(profile))
                   or bool(push.devices(uid))),
        "holdings": _has(lambda: holdings.load(uid)["items"]),
        "networth": _has(lambda: money_networth.load(uid)["items"]),
        "tax": _has(lambda: tax_lots.load(uid)["trades"]),
    }


def _has(read) -> bool:
    try:
        return bool(read())
    except Exception:
        return False


def is_new(profile: dict, now: datetime | None = None) -> bool:
    try:
        return (now or datetime.now(timezone.utc)) - _dt(profile["created_at"]) < NEW_FOR
    except (KeyError, TypeError, ValueError):
        return False


def view(profile: dict, now: datetime | None = None, focus: str | None = None) -> dict:
    """What Home shows: the steps for what the person came for (`focus`), with their ticks, and whether to show the
    checklist at all."""
    st = state(profile["id"])
    dismissed = bool(st.get("dismissed"))
    if dismissed or not is_new(profile, now):
        return {"show": False, "dismissed": dismissed, "done": 0, "steps": []}
    ticks = done(profile, st)
    pick = BY_FOCUS.get(focus or "trade", BY_FOCUS["trade"])
    steps = [{"id": i, "title": t, "to": to, "done": ticks[i]} for i, t, to in sorted((s for s in STEPS if s[0] in pick), key=lambda s: pick.index(s[0]))]
    n = sum(s["done"] for s in steps)
    return {"show": n < len(steps), "dismissed": False, "done": n, "steps": steps}
