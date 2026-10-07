"""Erase one user's app data: the one place that knows every store a person's data lives in.

Used by Admin -> Users, "Delete this user's data". It removes what the app keeps for the person (drawings, Connect
records with their sealed tokens, inbox address and statement password, holdings, net worth, notebooks, alerts,
preferences and the like). It does not delete the sign-in account or the billing record: those stay with the auth
provider and the payment records the law asks us to keep.

Every step runs on its own, so one store that fails does not leave the rest behind; the answer says which step failed
and the admin can run it again (every step is safe to repeat)."""
import logging
from collections.abc import Callable

from . import db

log = logging.getLogger("stratlab.user_data")

Step = tuple[str, str, Callable[[str], object]]


def _setting_keys(*prefixes: str) -> Callable[[str], int]:
    """Delete app_settings rows named <prefix><uid>; count the ones that were there."""
    def run(uid: str) -> int:
        n = 0
        for p in prefixes:
            if db.get_setting(p + uid) is not None:
                n += 1
            db.delete_setting(p + uid)
        return n
    return run


def _drawings(uid: str) -> int:
    from . import chart_data, drawings_store
    n = drawings_store.forget(uid)
    chart_data.forget(uid)                    # the older chart's drawings
    return n


def _connect(uid: str) -> int:
    """Sealed broker tokens, the statement-inbox address and the statement password: the whole connect/ record."""
    from .connect import kite_user, state
    had = len(state.load(uid))
    try:
        if state.section(uid, "kite").get("token"):
            kite_user.disconnect(uid)         # also ends the login at the broker when it still lives
    except Exception as e:                    # the broker being down must not keep the record
        log.warning("user data: kite logout for %s failed: %s", uid, str(e)[:120])
    state.drop_all(uid)
    return had


def _notebooks(uid: str) -> int:
    rows = db.list_notebook_rows(uid)
    if rows:
        db.sb().table("strategies").delete().eq("user_id", uid).execute()
    return len(rows)


def _holdings(uid: str) -> int:
    from . import holdings
    n = len(holdings.load(uid)["items"])
    holdings.delete(uid)
    return n


def _networth(uid: str) -> None:
    from . import money_networth
    money_networth.delete(uid)


def _tax(uid: str) -> None:
    from . import money_calendar, money_mf, money_routes, tax_lots, tax_total
    money_routes.delete_all(uid)              # dividends, advance tax and US trades
    tax_lots.delete(uid)
    money_mf.delete(uid)
    money_calendar.delete(uid)
    tax_total.delete_inputs(uid)


def _alerts(uid: str) -> int:
    from . import breadth, corp_actions, fo_changes, results, scan, shareholders, stock_alerts
    from .intel import filings
    return _setting_keys(stock_alerts.KEY, scan.ALERT_KEY, results.ALERT_KEY, corp_actions.ALERT_KEY, filings.ALERT_KEY,
                         breadth.ALERT_KEY, fo_changes.ALERT_KEY, shareholders.FOLLOW_KEY)(uid)


def _prefs(uid: str) -> int:
    from . import alerts, daily_report, first_steps, lifecycle, push
    return _setting_keys(daily_report.PREFS, lifecycle.PREFS, alerts.CONFIRMED, push.PREFIX, first_steps.KEY)(uid)


def _journal(uid: str) -> None:
    from . import journal
    journal.delete(uid)


def _replay(uid: str) -> None:
    from . import replay
    replay.forget(uid)


def _signals(uid: str) -> None:
    from . import signals
    signals.forget(uid)


STEPS: list[Step] = [
    ("drawings", "Chart drawings", _drawings),
    ("connect", "Connected accounts (tokens, inbox address, statement password)", _connect),
    ("holdings", "Holdings", _holdings),
    ("networth", "Net worth entries", _networth),
    ("notebooks", "Notebooks", _notebooks),
    ("alerts", "Alerts", _alerts),
    ("prefs", "Preferences", _prefs),
    ("tax", "Money tax tools", _tax),
    ("journal", "Trade journal", _journal),
    ("replay", "Chart replay sessions", _replay),
    ("signals", "Signal webhook", _signals),
]


# ---------- the user's own copy: "Download all my data" ----------
SECRET = ("token", "password", "secret", "api_key")                     # never in an export, even sealed
SECRET_NAMES = {"key", "keys", "auth", "p256dh", "endpoint", "address", "inbox", "sealed"}


def _secret(name) -> bool:
    n = str(name).lower()
    return n in SECRET_NAMES or any(s in n for s in SECRET)


def _clean(v):
    """JSON-safe, without any secret: sealed broker tokens, the statement password, push keys and the inbox address."""
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items() if not _secret(k)}
    if isinstance(v, (list, tuple, set)):
        return [_clean(x) for x in v]
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _settings_of(*prefixes: str) -> Callable[[str], dict]:
    def run(uid: str) -> dict:
        import json
        out = {}
        for p in prefixes:
            raw = db.get_setting(p + uid)
            if raw is not None:
                try:
                    out[p.rstrip(":")] = json.loads(raw)
                except (ValueError, TypeError):
                    out[p.rstrip(":")] = raw
        return out
    return run


def _x_drawings(uid: str) -> dict:
    from . import drawings_store
    out = {}
    for name in drawings_store._index(uid):
        r, _, s = name.partition(":")
        out[name] = drawings_store.load(uid, r, s)
    return out


def _x_alerts(uid: str) -> dict:
    from . import breadth, corp_actions, fo_changes, results, scan, shareholders, stock_alerts
    from .intel import filings
    return _settings_of(stock_alerts.KEY, scan.ALERT_KEY, results.ALERT_KEY, corp_actions.ALERT_KEY, filings.ALERT_KEY,
                        breadth.ALERT_KEY, fo_changes.ALERT_KEY, shareholders.FOLLOW_KEY)(uid)


def _x_prefs(uid: str) -> dict:
    from . import daily_report, first_steps, lifecycle
    return _settings_of(daily_report.PREFS, lifecycle.PREFS, first_steps.KEY)(uid)


def _x_connect(uid: str) -> dict:
    from .connect import state
    return {name: {k: v for k, v in (part or {}).items() if k in ("status", "detail", "day", "synced_at", "refreshed_at", "kite_user", "positions", "trades")}
            for name, part in (state.load(uid) or {}).items() if isinstance(part, dict)}


def _x_mod(module: str, fn: str) -> Callable[[str], object]:
    def run(uid: str):
        import importlib
        return getattr(importlib.import_module(f".{module}", __package__), fn)(uid)
    return run


EXPORT: list[tuple[str, str, Callable[[str], object]]] = [
    ("holdings", "Holdings", _x_mod("holdings", "load")),
    ("net_worth", "Net worth", _x_mod("money_networth", "load")),
    ("net_worth_history", "Net worth history", _x_mod("money_networth", "history")),
    ("notebooks", "Notebooks and experiments", lambda uid: db.sb().table("strategies").select("*").eq("user_id", uid).execute().data),
    ("trade_journal", "Trade journal", _x_mod("journal", "load")),
    ("tax_lots", "Tradebooks and tax lots", _x_mod("tax_lots", "load")),
    ("mutual_funds", "Mutual funds", _x_mod("money_mf", "load")),
    ("money_calendar", "Money calendar", _x_mod("money_calendar", "load")),
    ("tax_inputs", "Tax report inputs", _x_mod("tax_total", "load_inputs")),
    ("chart_drawings", "Chart drawings", _x_drawings),
    ("chart_replays", "Chart replay sessions", _x_mod("replay", "load_all")),
    ("alerts", "Alerts and follows", _x_alerts),
    ("preferences", "Preferences", _x_prefs),
    ("connected_accounts", "Connected accounts (no tokens or passwords)", _x_connect),
]


def export(profile: dict) -> dict:
    """Everything StratLab keeps for one user, as one JSON document: their profile and each kind of data, with every
    secret left out. A part that can't be read is named under "not_included" rather than failing the whole copy."""
    from datetime import datetime, timezone
    uid = profile["id"]
    out: dict = {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "profile": _clean({k: v for k, v in profile.items() if not k.startswith("_") and not k.startswith("razorpay_")}),
                 "not_included": []}
    for key, label, fn in EXPORT:
        try:
            out[key] = _clean(fn(uid))
        except Exception as e:
            log.warning("user data export: %s for %s failed: %s", key, uid, str(e)[:160])
            out["not_included"].append({"key": key, "label": label})
    return out


def erase(uid: str) -> dict:
    """Run every step for one user. Returns {"done": [{key, label, count}], "failed": [{key, label, error}]}."""
    done, failed = [], []
    for key, label, fn in STEPS:
        try:
            n = fn(uid)
            done.append({"key": key, "label": label, "count": n if isinstance(n, int) else None})
        except Exception as e:
            log.warning("user data: %s for %s failed: %s", key, uid, str(e)[:160])
            failed.append({"key": key, "label": label, "error": type(e).__name__})
    return {"done": done, "failed": failed}
