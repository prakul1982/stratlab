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
