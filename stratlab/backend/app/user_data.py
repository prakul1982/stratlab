"""Erase one user's app data: the one place that knows every store a person's data lives in.

Used by Admin -> Users, "Delete this user's data", by Account -> "Delete all my data" and, with close_account below, by
Account -> "Delete my account" (RC2B-031). It removes what the app keeps for the person (drawings, Connect
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


PAGE = 50          # rows a read takes of the tables whose rows are large (a notebook, a session's state)


def _pages(table: str, uid: str, cols: str = "*"):
    """The user's rows in a table one small page at a time, so nothing holds them all at once."""
    return db.pages(lambda: db.sb().table(table).select(cols).eq("user_id", uid), PAGE)


def _rows(table: str, uid: str, cols: str = "*") -> list[dict]:
    """Every row of the user's in a table, a page at a time (the server caps one read)."""
    return [r for page in _pages(table, uid, cols) for r in page]


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
    n = 0
    for page in _pages("strategies", uid, "id,body"):
        n += len(page)
        for r in page:                        # their share links and library entries are public: they go first
            library.take_down((r.get("body") or {}).get("experiments") or [])
    for e in library.all_entries(everything=True):    # also entries whose experiment is already gone, past the newest 1000
        if isinstance(e, dict) and e.get("owner") == uid:
            library.remove(e.get("id"))
    if n:
        db.sb().table("strategies").delete(returning="minimal").eq("user_id", uid).execute()
    return n


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
              "breadth.ALERT_KEY", "fo_changes.ALERT_KEY", "shareholders.FOLLOW_KEY", "screens.KEY", "market_events.USER_KEY", "ipo.USER_KEY")
PREF_KEYS = ("daily_report.PREFS", "lifecycle.PREFS", "lifecycle.SEEN", "alerts.CONFIRMED", "alerts.ALERT_OFF", "push.PREFIX",
             "first_steps.KEY", "plan_interest.KEY", "newsletter_prefs.PREFIX", "alerts.TG_VERIFY")
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
    from . import lifecycle
    tips_off = not lifecycle.tips_on(uid)
    n = _setting_keys(*_keys(PREF_KEYS))(uid)
    if tips_off:
        lifecycle.set_tips(uid, False)          # the account stays, so a "no tips" choice does too
    return n


def _watchlist(uid: str) -> int:
    """The Research watchlist and every Market Watch list (the extra lists, and the first list's other markets: MWR1-012, they
    were left behind when a person erased their data or closed the account)."""
    from . import watch_store
    n = _setting_keys(WATCHLIST)(uid)
    n += len(watch_store._rows(uid)) + (1 if watch_store._extras_row(uid) else 0)
    watch_store.forget(uid)
    return n


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
    try:
        return _setting_keys(plans.FREE_KEY)(uid)
    finally:
        plans.forget_free_basic()             # the 30 s copy still has the row: they would keep Basic, and /me could save it back


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
    # sessions run on the leader only: from another server (or one this process doesn't hold) the stored row is the way to
    # stop one, which the leader follows (LiveManager.reconcile), so the rows are marked stopped before they go
    db.stop_user_sessions(uid, "The account's data was deleted.")
    db.sb().table("live_orders").delete(returning="minimal").eq("user_id", uid).execute()
    return db.sb().table("live_sessions").delete(count="exact", returning="minimal").eq("user_id", uid).execute().count or 0


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
# Never in an export, even sealed. Exact names: a field that merely contains a word (instrument_token, the number of an
# exchange's instrument, not a credential) is the person's own data and stays.
SECRET_NAMES = {"token", "tokens", "access_token", "kite_access_token", "refresh_token", "request_token", "exchange_token",
                "public_token", "password", "passwd", "pw", "inbox_password", "statement_password", "secret", "webhook_secret",
                "api_secret", "api_key", "apikey", "key", "keys", "auth", "p256dh", "endpoint", "address", "inbox", "sealed",
                "hash"}
KEEP = {"billing": {"address"}, "invoices": {"address"}}      # the person's own billing address is theirs to have
# and any name with one of these in it (bot_token, kite_api_key, client_secret, private_key), save the few named in SAFE
SECRET_PARTS = ("token", "password", "passwd", "secret", "api_key", "apikey", "private_key")
SAFE = {"instrument_token"}                                    # the number of an exchange's instrument, not a credential


def _secret(name, keep=()) -> bool:
    n = str(name).lower()
    if n in keep or n in SAFE:
        return False
    return n in SECRET_NAMES or any(p in n for p in SECRET_PARTS)


def _clean(v, keep=()):
    """JSON-safe, without any secret: sealed broker tokens, the statement password, push keys and the inbox address."""
    if isinstance(v, dict):
        return {str(k): _clean(x, keep) for k, x in v.items() if not _secret(k, keep)}
    if isinstance(v, (list, tuple, set)):
        return [_clean(x, keep) for x in v]
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
    from . import chart_data, drawings_store
    out = {}
    for name in drawings_store._index(uid):
        r, _, s = name.partition(":")
        out[name] = drawings_store.load(uid, r, s)
    for name in chart_data._all(uid):          # drawings only the older chart saved
        if name not in out:
            r, _, s = name.partition(":")
            out[name] = drawings_store.load(uid, r, s)
    return out


def _x_market_watch(uid: str) -> dict:
    """Market Watch's lists as the person sees them: each list's name and its instruments in order."""
    from . import watch_store
    return {"lists": [{"name": l["name"], "first_list": l["default"], "items": [{"market": i["market"], "symbol": i["symbol"], "name": i["name"]} for i in l["items"]]}
                      for l in watch_store.all_lists(uid)]}


def _x_alerts(uid: str) -> dict:
    return _settings_of(*_keys(ALERT_KEYS))(uid)


def _x_prefs(uid: str) -> dict:
    out = _settings_of(*_keys(n for n in PREF_KEYS if n != "push.PREFIX"))(uid)       # push keys are secrets
    tg = out.get("tgverify")
    if isinstance(tg, dict) and isinstance(tg.get("pending"), dict):                  # the Telegram code's hash is a secret
        tg["pending"] = {k: v for k, v in tg["pending"].items() if k != "code_hash"}
    return out


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
    for page in _pages("usage_events", uid, "id,kind"):     # kinds are open-ended (a deep dive's mark names the company), so a page at a time, totalled as it goes
        for r in page:
            out[r.get("kind")] = out.get(r.get("kind"), 0) + 1
    return out


def _x_invoices(uid: str) -> list:
    """The tax invoices billed to the person (kept as payment records, but theirs to download)."""
    import json
    nums = db.json_value(db.get_setting(f"invoices:{uid}"), [])
    out = []
    for n in nums:
        raw = db.get_setting(f"invoice:{n}")
        inv = json.loads(raw) if raw else None
        if isinstance(inv, dict) and inv.get("user_id") == uid:
            out.append(inv)
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
    ("market_watch", "Market Watch lists", _x_market_watch),
    ("sessions", "Paper and live sessions and their orders", _x_sessions),
    ("ai_assistant", "AI assistant key names and their log (no keys)", _x_assistant),
    ("referrals", "Invite link and invites", _x_referrals),
    ("free_basic", "Free Basic time", lambda uid: _settings_of(*_keys(("plans.FREE_KEY",)))(uid)),
    ("usage", "Usage counts", _x_usage),
    ("billing", "Billing details (name, address, GSTIN)", _settings_of("billing:")),
    ("invoices", "Tax invoices", _x_invoices),
    ("company_cards", "Shared company cards", _settings_of("cards:user:")),
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
            out[key] = _clean(fn(uid), KEEP.get(key, ()))
        except Exception as e:
            log.warning("user data export: %s for %s failed: %s", key, uid, str(e)[:160])
            out["not_included"].append({"key": key, "label": label})
    return out


# ---------- closing the account (RC2B-031) ----------
KEPT_CLOSED = "Kept: invoices and payment records, as tax law asks. Usage counts and the sign-in account are gone."


def _my_stocks_briefs(uid: str) -> int:
    """The user's own My Stocks briefs (news:my_stocks:<uid>:<day> and their index): built from their holdings."""
    from .newsletter import job
    n = 0
    for iid in job.ids("my_stocks", uid):
        parts = job.parse_id(iid)
        if parts:
            db.delete_setting(job._key(*parts))
            db.delete_setting(job.SENT + iid)          # who it was sent to
            n += 1
    db.delete_setting(job._index_key("my_stocks", uid))
    return n


def _billing_details(uid: str) -> int:
    """The name, address and GSTIN saved for invoices. Each invoice already issued carries its own copy and stays."""
    return _setting_keys("billing:")(uid)


def _email_records(uid: str) -> int:
    """Which account emails were sent and which are waiting, the "no tips" choice and the paper-trade alert count."""
    from . import lifecycle, live
    return _setting_keys(lifecycle.SENT, lifecycle.PENDING, lifecycle.PREFS, lifecycle.SEEN, live.TRADE_ALERTS)(uid)


CLOSE_STEPS: list[Step] = [
    ("my_stocks_briefs", "My Stocks briefs", _my_stocks_briefs),
    ("billing_details", "Billing details (name, address, GSTIN)", _billing_details),
    ("email_records", "Account email records", _email_records),
]


def close_account(uid: str) -> dict:
    """Delete the person's data in every store and then their sign-in account (the sign-in service's own record, which
    also removes the profile, usage counts, notebooks and sessions that hang from it). Invoices and the payment records
    behind them stay, as tax law asks. Nothing is closed unless every step before the sign-in account worked, so a failure
    leaves a whole account the person can try again on (every step is safe to repeat). Only ever one user's rows.
    Returns {"closed", "done", "failed", "kept"}."""
    out = erase(uid)
    for key, label, fn in CLOSE_STEPS:
        try:
            n = fn(uid)
            out["done"].append({"key": key, "label": label, "count": n if isinstance(n, int) else None})
        except Exception as e:
            log.warning("account closing: %s for %s failed: %s", key, uid, str(e)[:160])
            out["failed"].append({"key": key, "label": label, "error": type(e).__name__})
    out["kept"] = KEPT_CLOSED
    if out["failed"]:
        return {**out, "closed": False}
    try:
        db.sb().auth.admin.delete_user(uid)
    except Exception as e:
        log.warning("account closing: sign-in account of %s not deleted: %s", uid, str(e)[:160])
        return {**out, "closed": False, "failed": [{"key": "signin", "label": "The sign-in account", "error": type(e).__name__}]}
    try:
        db.sb().table("profiles").delete(returning="minimal").eq("id", uid).execute()      # already gone with the sign-in record
    except Exception as e:
        log.warning("account closing: profile row of %s: %s", uid, str(e)[:120])
    db.forget_profile(uid)
    from . import auth
    auth.forget_user(uid)
    return {**out, "closed": True}


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
