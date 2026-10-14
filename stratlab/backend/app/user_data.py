"""Erase one user's app data: the one place that knows every store a person's data lives in.

Used by Admin -> Users, "Delete this user's data". It removes what the app keeps for the person (drawings, Connect
records with their sealed tokens, inbox address and statement password, holdings, net worth, notebooks, alerts,
preferences and the like). It does not delete the sign-in account or the billing record: those stay with the auth
provider and the payment records the law asks us to keep. Usage counts (usage_events, the plan's monthly quotas) and
the invite reward records another user's reward caps count (reward:<uid>, rewardgrant:) stay too.

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


def _rows(table: str, uid: str, cols: str = "*") -> list[dict]:
    """Every row of the user's in a table, a page at a time (the server caps one read)."""
    return db.paged(lambda: db.sb().table(table).select(cols).eq("user_id", uid))


def _connect(uid: str) -> int:
    """Sealed broker tokens, the statement-inbox address and the statement password: the whole connect/ record."""
    from .connect import kite_user, state
    for key, raw in db.all_settings_with_prefix(kite_user.PENDING):    # a Zerodha login waiting to be confirmed
        if db.json_value(raw, {}).get("uid") == uid:
            db.delete_setting(key)
    had = len(state.load(uid))
    try:
        if state.section(uid, "kite").get("token"):
            kite_user.disconnect(uid)         # also ends the login at the broker when it still lives
    except Exception as e:                    # the broker being down must not keep the record
        log.warning("user data: kite logout for %s failed: %s", uid, str(e)[:120])
    state.drop_all(uid)
    return had


def _notebooks(uid: str) -> int:
    from . import library
    rows = _rows("strategies", uid, "id,body")
    for r in rows:                            # their share links and library entries are public: they go first
        library.take_down((r.get("body") or {}).get("experiments") or [])
    for e in library.all_entries():           # also entries whose experiment is already gone
        if e.get("owner") == uid:
            library.remove(e.get("id"))
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


ALERT_KEYS = ("stock_alerts.KEY", "scan.ALERT_KEY", "results.ALERT_KEY", "corp_actions.ALERT_KEY", "intel.filings.ALERT_KEY",
              "breadth.ALERT_KEY", "fo_changes.ALERT_KEY", "shareholders.FOLLOW_KEY", "screens.KEY", "market_events.USER_KEY")
PREF_KEYS = ("daily_report.PREFS", "lifecycle.PREFS", "lifecycle.SEEN", "alerts.CONFIRMED", "alerts.ALERT_OFF", "push.PREFIX",
             "first_steps.KEY", "plan_interest.KEY", "newsletter_prefs.PREFIX")
WATCHLIST = "watchlist:"


def _keys(names) -> list[str]:
    """Prefixes named "module.CONSTANT", read from the modules that own them."""
    import importlib
    out = []
    for n in names:
        mod, _, const = n.rpartition(".")
        out.append(getattr(importlib.import_module(f".{mod}", __package__), const))
    return out


def _alerts(uid: str) -> int:
    return _setting_keys(*_keys(ALERT_KEYS))(uid)


def _prefs(uid: str) -> int:
    return _setting_keys(*_keys(PREF_KEYS))(uid)


def _watchlist(uid: str) -> int:
    return _setting_keys(WATCHLIST)(uid)


def _assistant(uid: str) -> int:
    """MCP keys: the index rows go first, so a key stops working before anything else is removed."""
    from . import mcp_keys
    ks = mcp_keys._row(uid)["keys"]
    for k in ks:
        if k.get("hash"):
            db.delete_setting(mcp_keys.KEY_INDEX + str(k["hash"]))
    for key, raw in db.all_settings_with_prefix(mcp_keys.KEY_INDEX):  # also one whose key is no longer listed
        if db.json_value(raw, {}).get("uid") == uid:
            db.delete_setting(key)
    db.delete_setting(mcp_keys.KEY_USER + uid)
    db.delete_setting(mcp_keys.KEY_LOG + uid)
    return len(ks)


def _referrals(uid: str) -> int:
    """The user's invite code (the link stops working), who invited them, whom they invited and their active days. The
    reward records (reward:<uid>, rewardgrant:, rewardpay:) and the inviter's ref:joined entry stay: the inviter's
    reward caps and history count them."""
    from . import invite_rewards
    code = db.get_setting(f"ref:user:{uid}")
    if code and db.get_setting(f"ref:code:{code}") == uid:
        db.delete_setting(f"ref:code:{code}")
    return _setting_keys("ref:user:", "ref:by:", "ref:joined:", invite_rewards.DAYS)(uid)


def _free_basic(uid: str) -> int:
    from . import plans
    return _setting_keys(plans.FREE_KEY)(uid)


def _cards(uid: str) -> int:
    """Shared company cards: public links, taken down."""
    from . import company_cards
    rows = db.json_value(db.get_setting(f"cards:user:{uid}"), [])
    for r in rows:
        if not isinstance(r, dict):
            continue
        if company_cards.TOKEN.match(str(r.get("t") or "")):
            db.delete_setting(f"card:{r['t']}")
            db.delete_setting(f"cardimg:{r['t']}")
        if str(r.get("k") or "").startswith(f"cardtok:{uid}:"):
            db.delete_setting(r["k"])
    db.delete_setting(f"cards:user:{uid}")
    return len(rows)


def _live(uid: str) -> int:
    """Paper and live sessions with their orders: the running ones are stopped here first."""
    import sys
    main = sys.modules.get(f"{__package__}.main")
    if main is not None:
        for s in main.manager.user_running(uid):
            main.manager.stop(s.id, "The account's data was deleted.")
    db.sb().table("live_orders").delete().eq("user_id", uid).execute()
    return len(db.sb().table("live_sessions").delete().eq("user_id", uid).execute().data or [])


def _profile_alerts(uid: str) -> None:
    db.update_profile(uid, telegram_chat_id=None, alert_email=None, alerts_enabled=False)


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
    ("watchlist", "Watchlist", _watchlist),
    ("assistant", "AI assistant keys and their log", _assistant),
    ("referrals", "Invite link and invites", _referrals),
    ("free_basic", "Free Basic time", _free_basic),
    ("cards", "Shared company cards", _cards),
    ("live", "Paper and live sessions and their orders", _live),
    ("profile_alerts", "Alert channels (Telegram chat, alert email)", _profile_alerts),
]
KEPT = "Kept: the sign-in account, plan and payment records (invoices, as the law asks), usage counts for the plan's limits."


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
    return _settings_of(*_keys(ALERT_KEYS))(uid)


def _x_prefs(uid: str) -> dict:
    return _settings_of(*_keys(n for n in PREF_KEYS if n != "push.PREFIX"))(uid)       # push keys are secrets


def _x_sessions(uid: str) -> dict:
    return {"sessions": _rows("live_sessions", uid), "orders": _rows("live_orders", uid)}


def _x_assistant(uid: str) -> dict:
    from . import mcp_keys
    return {"assistant_keys": mcp_keys.keys(uid), "calls": mcp_keys.entries(uid)}     # names only, never a key's hash


def _x_referrals(uid: str) -> dict:
    from . import invite_rewards, referrals
    return {"code": db.get_setting(f"ref:user:{uid}"), "invited_by": referrals.referred_by(uid),
            "invited": referrals.joined(uid), "reward": invite_rewards.row(uid),
            **_settings_of(invite_rewards.DAYS)(uid)}


def _x_usage(uid: str) -> dict:
    out: dict = {}
    for r in _rows("usage_events", uid, "id,kind"):
        out[r.get("kind")] = out.get(r.get("kind"), 0) + 1
    return out


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
    ("notebooks", "Notebooks and experiments", lambda uid: _rows("strategies", uid)),
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
    ("watchlist", "Watchlist", _settings_of(WATCHLIST)),
    ("sessions", "Paper and live sessions and their orders", _x_sessions),
    ("ai_assistant", "AI assistant key names and their log (no keys)", _x_assistant),
    ("referrals", "Invite link and invites", _x_referrals),
    ("free_basic", "Free Basic time", lambda uid: _settings_of(*_keys(("plans.FREE_KEY",)))(uid)),
    ("usage", "Usage counts", _x_usage),
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
    return {"done": done, "failed": failed, "kept": KEPT}
