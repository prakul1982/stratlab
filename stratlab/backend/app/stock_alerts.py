"""Stock alerts people set for themselves: a price crossing a level, a big move in a day, an ETF's price this far
from its NAV (etf_nav.py), the price crossing a moving average, RSI crossing a level, a Stage change, a new 52-week
high or low.

Each user's alerts live in one app_settings row (stockalerts:<uid>). The checker runs inside the scan-alert job's
loop: every minute while India or the US is open, it reads every active alert for that market, fetches each symbol's
quote once (in batches), and daily candles only for the alerts that need them. Alerts on Indian companies' insider
trades and bulk or block deals are checked instead once every evening, against that day's exchange disclosures
(fire_events, called by the deals job).

An alert fires once and is then marked triggered, unless it repeats (then at most once a day). Messages are
factual ("RELIANCE crossed above ₹3,000 (now ₹3,012)"), never advice. One user gets at most a few messages an hour:
alerts that fire while they're over the limit wait and go out together in the next message."""
import json
import math
import secrets
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from . import db
from .data.markets import BY_ID
from .engine.indicators import rsi, stage

KEY = "stockalerts:"                 # app_settings: stockalerts:<uid> = {"uid", "items": [...], "sent": [...], "pending": [...]}
REGIONS = ("IN", "US")
KINDS = ("price", "move", "ma", "rsi", "stage", "high52", "low52", "insider", "deal", "surveillance", "etfgap")
NEEDS_BARS = {"ma", "rsi", "stage", "high52", "low52"}
EVENTS = {"insider": ("insider", "sast"), "deal": ("bulk", "block"),   # alerts on exchange disclosures, not on the price
          "surveillance": ("surveillance",)}                   # and on the exchange's surveillance lists
MAX_SEEN = 300                       # disclosure ids an event alert remembers, so none is sent twice
MA_PERIODS = (20, 50, 100, 150, 200)
RSI_PERIOD = 14
YEAR = 252                           # trading days in 52 weeks
AFTER_CLOSE = 10                     # minutes after the close to keep checking, so the closing price is seen (India's
                                     # closing auction ends at 15:35 for F&O stocks: data/sessions.py)

PER_HOUR = 5                         # messages one user can get in an hour
PER_DAY = 20                         # and in a day
MAX_PENDING = 50                     # fired alerts waiting for the next message
KEEP_TRIGGERED = 50                  # triggered alerts kept on the Alerts page
QUOTE_BATCH = 24

_lock = threading.Lock()             # one read-modify-write of a user's row at a time (the API and the checker)


class AlertError(ValueError):
    """An alert that can't be saved; the message says why in plain words."""


# ---------- formatting ----------
def _group_in(whole: str) -> str:
    """Indian digit grouping: 1,23,45,678."""
    if len(whole) <= 3:
        return whole
    head, tail = whole[:-3], whole[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def money(v: float, region: str) -> str:
    """₹3,000 or $187.25: whole numbers without decimals, others to two places."""
    sym = "₹" if region == "IN" else "$"
    dp = 0 if abs(v - round(v)) < 0.005 else 2
    s = f"{abs(v):,.{dp}f}"
    if region == "IN":
        whole, _, frac = s.replace(",", "").partition(".")
        s = _group_in(whole) + ("." + frac if frac else "")
    return ("-" if v < 0 else "") + sym + s


def _num(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v - round(v)) >= 0.05 else str(int(round(v)))


def describe(a: dict) -> str:
    """The condition in words, for the Alerts page and the email: "Price crosses above ₹3,000"."""
    k, op, v, region = a["kind"], a.get("op"), a.get("value"), a["region"]
    if k == "price":
        return f"Price crosses {op} {money(v, region)}"
    if k == "move":
        return {"up": f"Rises {_num(v)}% or more in a day", "down": f"Falls {_num(v)}% or more in a day"}.get(
            op, f"Moves {_num(v)}% or more either way in a day")
    if k == "ma":
        return f"Price crosses {op} its {a['period']}-day average"
    if k == "rsi":
        return f"{RSI_PERIOD}-day RSI crosses {op} {_num(v)}"
    if k == "stage":
        return f"Enters Stage {int(v)}" if v else "Stage changes"
    if k == "insider":
        return "A promoter or insider trade is disclosed"
    if k == "deal":
        return "A bulk or block deal is reported"
    if k == "etfgap":                   # an ETF's price against its NAV (etf_nav.py)
        return {"above": f"Trades {_num(v)}% or more above its last NAV", "below": f"Trades {_num(v)}% or more below its last NAV"}.get(
            op, f"Trades {_num(v)}% or more away from its last NAV, either way")
    if k == "surveillance":
        return "Enters or leaves an exchange surveillance list (ASM, GSM, ESM, trade-to-trade, F&O ban, price band)"
    return "Makes a new 52-week high" if k == "high52" else "Makes a new 52-week low"


# ---------- checking and cleaning what people send ----------
def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clean(req: dict) -> dict:
    """The alert's condition, checked: raises AlertError with a plain reason when it doesn't make sense."""
    region = str(req.get("region") or "").upper()
    if region not in REGIONS:
        raise AlertError("Alerts cover India (IN) and US stocks.")
    sym = str(req.get("symbol") or "").strip().upper()
    if not sym or len(sym) > 20 or not all(ch.isalnum() or ch in "&-._" for ch in sym):
        raise AlertError("That doesn't look like a ticker.")
    kind = req.get("kind")
    if kind not in KINDS:
        raise AlertError("Pick what the alert should watch for.")
    if kind in EVENTS and region != "IN":
        raise AlertError("Alerts on exchange disclosures and surveillance lists cover Indian stocks.")
    if kind == "etfgap" and region != "IN":
        raise AlertError("Alerts on an ETF's price against its NAV cover Indian ETFs.")
    op, v, period = req.get("op"), req.get("value"), req.get("period")
    out = {"region": region, "symbol": sym, "kind": kind, "op": None, "value": None, "period": None,
           "repeat": bool(req.get("repeat")), "note": str(req.get("note") or "").strip()[:120] or None}
    if kind in ("price", "ma", "rsi"):
        if op not in ("above", "below"):
            raise AlertError("Pick above or below.")
        out["op"] = op
    if kind == "price":
        if not _finite(v) or not 0 < v < 1e8:
            raise AlertError("Enter the price level, a number above zero.")
        out["value"] = round(float(v), 4)
    elif kind == "move":
        if op not in ("up", "down", "either"):
            raise AlertError("Pick up, down or either way.")
        if not _finite(v) or not 0.1 <= v <= 50:
            raise AlertError("Enter the day's move as a percent between 0.1 and 50.")
        out.update(op=op, value=round(float(v), 2))
    elif kind == "etfgap":
        if op not in ("above", "below", "either"):
            raise AlertError("Pick above its NAV, below it, or either way.")
        if not _finite(v) or not 0.1 <= v <= 50:
            raise AlertError("Enter the gap as a percent between 0.1 and 50.")
        out.update(op=op, value=round(float(v), 2))
    elif kind == "ma":
        if period not in MA_PERIODS:
            raise AlertError(f"Pick a moving average of {', '.join(map(str, MA_PERIODS))} days.")
        out["period"] = int(period)
    elif kind == "rsi":
        if not _finite(v) or not 1 <= v <= 99:
            raise AlertError("Enter an RSI level between 1 and 99.")
        out.update(value=round(float(v), 1), period=RSI_PERIOD)
    elif kind == "stage":
        if v in (None, 0):
            out["value"] = 0
        elif _finite(v) and int(v) == v and 1 <= v <= 4:
            out["value"] = int(v)
        else:
            raise AlertError("Pick Stage 1, 2, 3 or 4, or any change.")
    return out


# ---------- storage ----------
def _read(uid: str) -> dict:
    try:
        row = json.loads(db.get_setting(KEY + uid) or "{}")
    except (ValueError, TypeError):
        row = {}
    if not isinstance(row, dict):
        row = {}
    items = row.get("items")
    row["items"] = [a for a in items if isinstance(a, dict) and a.get("id")] if isinstance(items, list) else []
    for k in ("sent", "pending"):
        row[k] = row.get(k) if isinstance(row.get(k), list) else []
    row["uid"] = uid
    return row


def _write(uid: str, row: dict) -> None:
    triggered = [a for a in row["items"] if a.get("status") == "triggered"]
    if len(triggered) > KEEP_TRIGGERED:             # the oldest triggered ones go
        old = {a["id"] for a in sorted(triggered, key=lambda a: a.get("triggered_at") or "")[:len(triggered) - KEEP_TRIGGERED]}
        row["items"] = [a for a in row["items"] if a["id"] not in old]
    db.set_setting(KEY + uid, json.dumps(row))


def items(uid: str) -> list[dict]:
    return _read(uid)["items"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(uid: str, req: dict, limit: int, seed: dict | None = None) -> dict:
    """Add an alert. `seed` is the stock's quote now, so a price alert knows which side of its level it starts on."""
    a = clean(req)
    with _lock:
        row = _read(uid)
        if sum(1 for x in row["items"] if x.get("status") == "active") >= limit:
            raise LimitReached(limit)
        a.update(id=secrets.token_hex(6), status="active", created_at=_now(), triggered_at=None, fired=0,
                 last_text=None, rev=1, state=_seed(a, seed))
        row["items"].append(a)
        _write(uid, row)
    return a


def update(uid: str, aid: str, req: dict, limit: int, seed: dict | None = None) -> dict | None:
    """Change an alert's condition; it starts afresh (active again, its crossing state reset). None if not found."""
    a = clean(req)
    with _lock:
        row = _read(uid)
        old = next((x for x in row["items"] if x["id"] == aid), None)
        if not old:
            return None
        others = sum(1 for x in row["items"] if x.get("status") == "active" and x["id"] != aid)
        if others >= limit:
            raise LimitReached(limit)
        old.update(a, status="active", triggered_at=None, rev=int(old.get("rev") or 0) + 1, state=_seed(a, seed))
        _write(uid, row)
        return old


def delete(uid: str, aid: str | None = None, triggered: bool = False) -> int:
    """Remove one alert, or every triggered one. Returns how many went."""
    with _lock:
        row = _read(uid)
        keep = [a for a in row["items"] if not (a["id"] == aid or (triggered and a.get("status") == "triggered"))]
        gone = len(row["items"]) - len(keep)
        if gone:
            row["items"] = keep
            _write(uid, row)
    return gone


class LimitReached(Exception):
    def __init__(self, limit: int):
        super().__init__(limit)
        self.limit = limit


def _seed(a: dict, quote: dict | None) -> dict:
    """Where a price alert starts: on which side of its level the price is now."""
    p = (quote or {}).get("price")
    if a["kind"] == "price" and _finite(p):
        return {"side": _side(p, a["value"])}
    return {}


# ---------- the conditions ----------
def _side(x: float, level: float) -> str | None:
    return "above" if x > level else "below" if x < level else None


def series_with(bars: list[dict], price: float, today: str, tz: str) -> pd.Series:
    """Daily closes with today's live price as the last close (replacing today's candle when there is one)."""
    closes = [float(b["c"]) for b in bars]
    if bars and _day(bars[-1].get("t"), tz) == today:
        closes[-1] = price
    else:
        closes.append(price)
    return pd.Series(closes, dtype=float)


def _day(t, tz: str) -> str | None:
    try:
        if isinstance(t, (int, float)):
            d = datetime.fromtimestamp(t / 1000 if t > 1e11 else t, timezone.utc)
        else:
            d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        return (d.astimezone(ZoneInfo(tz)) if d.tzinfo else d).date().isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _prior_year(bars: list[dict], today: str, tz: str) -> list[dict]:
    """The last 52 weeks of candles before today."""
    done = bars[:-1] if bars and _day(bars[-1].get("t"), tz) == today else bars
    return done[-YEAR:]


def _cross(a: dict, state: dict, x: float, level: float) -> tuple[bool, dict]:
    """A crossing: x moved from one side of the level to the side the alert watches. The first look only arms it."""
    now = _side(x, level)
    before = state.get("side")
    if now is None:                     # exactly on the level: wait to see which way it goes
        return False, state
    state = {**state, "side": now}
    return (before is not None and before != now and now == a["op"]), state


def evaluate(a: dict, snap: dict) -> tuple[str | None, dict]:
    """Check one alert against a stock's numbers now. Returns the message when it fires (else None) and the alert's
    new state. `snap` has price, change_pct, and for the alerts that need them, daily bars; plus today (the market's
    date) and tz."""
    st = dict(a.get("state") or {})
    p, region, sym = snap.get("price"), a["region"], a["symbol"]
    if not _finite(p) or p <= 0:
        return None, st
    today = snap["today"]
    now = money(p, region)
    k, op, v = a["kind"], a.get("op"), a.get("value")
    text = None
    if k == "price":
        fired, st = _cross(a, st, p, v)
        if fired:
            text = f"{sym} crossed {op} {money(v, region)} (now {now})"
    elif k == "move":
        chg = snap.get("change_pct")
        if _finite(chg) and ((op == "up" and chg >= v) or (op == "down" and chg <= -v) or (op == "either" and abs(chg) >= v)):
            text = f"{sym} is {'up' if chg > 0 else 'down'} {abs(chg):.1f}% today (now {now})"
    elif k == "etfgap":
        g = snap.get("gap") or {}
        x = g.get("gap")
        if _finite(x) and ((op == "above" and x >= v) or (op == "below" and x <= -v) or (op == "either" and abs(x) >= v)):
            text = g.get("text") or f"{sym} is {abs(x):.2f}% {'above' if x > 0 else 'below'} its NAV (now {now})"
    else:
        bars = snap.get("bars") or []
        tz = snap.get("tz") or "UTC"
        if k in ("ma", "rsi", "stage"):
            c = series_with(bars, p, today, tz)
            if k == "ma":
                if len(c) < a["period"]:
                    return None, st
                avg = float(c.tail(a["period"]).mean())
                fired, st = _cross(a, st, p, avg)
                if fired:
                    text = f"{sym} crossed {op} its {a['period']}-day average of {money(round(avg, 2), region)} (now {now})"
            elif k == "rsi":
                r = rsi(c, RSI_PERIOD).iloc[-1]
                if pd.isna(r):
                    return None, st
                fired, st = _cross(a, st, float(r), v)
                if fired:
                    text = f"{sym}'s {RSI_PERIOD}-day RSI crossed {op} {_num(v)} (now {float(r):.1f}; price {now})"
            else:
                s = stage(c, 150, 20).iloc[-1]
                if pd.isna(s):
                    return None, st
                s, before = int(s), st.get("stage")
                st["stage"] = s
                if before is not None and s != before and (not v or s == v):
                    text = f"{sym} moved from Stage {before} to Stage {s} (now {now})"
        else:
            year = _prior_year(bars, today, tz)
            if len(year) < 20:
                return None, st
            if k == "high52":
                hi = max(float(b["h"]) for b in year)
                if p > hi:
                    text = f"{sym} traded above its 52-week high of {money(hi, region)} (now {now})"
            else:
                lo = min(float(b["l"]) for b in year)
                if p < lo:
                    text = f"{sym} traded below its 52-week low of {money(lo, region)} (now {now})"
    if text and a.get("repeat") and (a.get("state") or {}).get("day") == today:
        text = None                     # a repeating alert fires at most once a day (its crossings still count)
    if text:
        st["day"] = today
    return text, st


# ---------- market hours ----------
def market_open(region: str, now: datetime) -> str | None:
    """The market's date when it's open now (plus a few minutes after the close), else None."""
    from .data.calendar import is_trading_day
    m = BY_ID[region]
    local = now.astimezone(ZoneInfo(m["tz"]))
    hhmm = local.strftime("%H:%M")
    close = (datetime.strptime(m["hours"]["close"], "%H:%M") + timedelta(minutes=AFTER_CLOSE)).strftime("%H:%M")
    if not (m["hours"]["open"] <= hhmm <= close) or not is_trading_day(region, local.date()):
        return None
    return local.date().isoformat()


# ---------- throttling and delivery ----------
def _recent(sent: list, now: datetime, within: timedelta) -> int:
    n = 0
    for t in sent:
        try:
            if now - datetime.fromisoformat(t) < within:
                n += 1
        except (ValueError, TypeError):
            continue
    return n


def may_send(sent: list, now: datetime) -> bool:
    """Under the per-user limits: PER_HOUR messages an hour and PER_DAY a day."""
    return _recent(sent, now, timedelta(hours=1)) < PER_HOUR and _recent(sent, now, timedelta(days=1)) < PER_DAY


def message(texts: list[str]) -> tuple[str, str]:
    """(subject, text) for one or more fired alerts."""
    if len(texts) == 1:
        subject = "StratLab alert: " + texts[0]
    else:
        subject = f"StratLab: {len(texts)} of your alerts fired"
    shown = texts[:10] + ([f"and {len(texts) - 10} more on your Alerts page"] if len(texts) > 10 else [])
    body = "\n".join(shown) + "\n\nFrom the alerts you set on StratLab. Facts, not advice."
    return subject[:150], body


def deliver(profile: dict, subject: str, text: str) -> list[str]:
    """Phone and Telegram as set up in Account, and email only to an address the user confirmed."""
    from . import alerts
    from .config import settings
    sent = []
    for channel, job in alerts.jobs_for(profile, subject, text, "/alerts"):
        if channel == "email":
            continue
        try:
            job()
            sent.append(channel)
        except Exception as e:
            print("stock alert failed:", channel, str(e)[:120])
    to = alerts.newsletter_email(profile)
    if to and alerts.email_ready() and alerts.email_confirmed(profile):
        try:
            alerts.send_email(to, subject, f"{text}\n\nManage your alerts: {settings.PUBLIC_SITE_URL}/alerts")
            sent.append("email")
        except Exception as e:
            print("stock alert failed: email", str(e)[:120])
    return sent


def channels(profile: dict) -> list[str]:
    """Where this user's alerts would go now."""
    from . import alerts
    out = [c for c, _ in alerts.jobs_for(profile, "", "", "/alerts") if c != "email"]
    if alerts.newsletter_email(profile) and alerts.email_ready() and alerts.email_confirmed(profile):
        out.append("email")
    return out


# ---------- the checker ----------
class Checker:
    """Checks every active alert for the markets open now. Plugged into the scan-alert job's loop.

    quotes(region, symbols) -> {symbol: {"price", "change_pct", ...} | None}, in batches;
    bars(region, symbol) -> daily candles; limit(profile) -> active alerts the user's plan checks;
    send(profile, subject, text) -> channels reached; gaps(symbol, price) -> an ETF's gap to its NAV (etf_nav.gap_now);
    kind_ok(profile, kind) -> the user's plan checks that kind of alert."""

    def __init__(self, quotes, bars, limit, send=deliver, profile=None, gaps=None, kind_ok=None):
        self.quotes, self.bars, self.limit, self.send = quotes, bars, limit, send
        self.gaps, self.kind_ok = gaps or (lambda s, p: None), kind_ok or (lambda p, k: True)
        self.profile = profile or db.cached_profile
        self.status = {"last_run": None, "checked": 0, "fired": 0, "sent": 0, "last_error": None}

    def _quotes(self, region: str, syms: list[str]) -> dict:
        out = {}
        for i in range(0, len(syms), QUOTE_BATCH):
            try:
                out.update(self.quotes(region, syms[i:i + QUOTE_BATCH]) or {})
            except Exception as e:          # one batch failing mustn't stop the rest
                self.status["last_error"] = str(e)[:200]
        return out

    def tick(self, now: datetime) -> None:
        days = {r: d for r in REGIONS if (d := market_open(r, now))}
        if not days:
            return
        users: dict[str, list[dict]] = {}
        for key, raw in db.all_settings_with_prefix(KEY):
            uid = key[len(KEY):]
            try:
                row = json.loads(raw)
            except (ValueError, TypeError):
                continue
            mine = [a for a in (row.get("items") or []) if isinstance(a, dict) and a.get("status") == "active"]
            if mine or (isinstance(row, dict) and row.get("pending")):
                users[uid] = sorted(mine, key=lambda a: a.get("created_at") or "")
        # a plan's limit: alerts beyond it (after a downgrade) wait, the oldest are checked
        todo: dict[str, list[dict]] = {}
        profiles: dict[str, dict] = {}
        for uid, mine in users.items():
            try:
                profiles[uid] = self.profile(uid)
            except Exception:
                continue
            todo[uid] = [a for a in mine[:self.limit(profiles[uid])] if a.get("region") in days and a.get("kind") not in EVENTS
                         and self.kind_ok(profiles[uid], a.get("kind"))]
        fired: dict[str, dict[str, tuple]] = {}      # uid -> alert id -> (text, new state, rev)
        checked = 0
        for region, today in days.items():
            mine = [(uid, a) for uid, xs in todo.items() for a in xs if a["region"] == region]
            syms = sorted({a["symbol"] for _, a in mine})
            if not syms:
                continue
            quotes = self._quotes(region, syms)
            bars: dict[str, list] = {}
            for sym in sorted({a["symbol"] for _, a in mine if a["kind"] in NEEDS_BARS}):
                if (quotes.get(sym) or {}).get("price") is None:
                    continue
                try:
                    bars[sym] = self.bars(region, sym)
                except Exception:
                    bars[sym] = []
            tz = BY_ID[region]["tz"]
            for uid, a in mine:
                q = quotes.get(a["symbol"]) or {}
                snap = {"price": q.get("price"), "change_pct": q.get("change_pct"), "bars": bars.get(a["symbol"]),
                        "today": today, "tz": tz}
                if a["kind"] == "etfgap":
                    snap["gap"] = self.gaps(a["symbol"], q.get("price"))
                try:
                    text, st = evaluate(a, snap)
                except Exception as e:      # odd data for one stock mustn't stop the others
                    self.status["last_error"] = f"{a['symbol']}: {str(e)[:150]}"
                    continue
                checked += 1
                if text or st != (a.get("state") or {}):
                    fired.setdefault(uid, {})[a["id"]] = (text, st, a.get("rev"))
        n_fired = n_sent = 0
        for uid in users:
            changes = fired.get(uid, {})
            texts = apply(uid, changes, now)
            n_fired += sum(1 for t, _, _ in changes.values() if t)
            if texts and uid in profiles and flush(uid, profiles[uid], texts, now, self.send):
                n_sent += 1
        self.status.update(last_run=now.isoformat(), checked=checked, fired=n_fired, sent=n_sent)

    def _apply(self, uid: str, changes: dict, now: datetime) -> list[str]:
        return apply(uid, changes, now)


def flush(uid: str, profile: dict, texts: list[str], now: datetime, send=deliver) -> bool:
    """Send the texts waiting for one user in one message, and count it against their limits."""
    subject, body = message(texts)
    reached = bool(send(profile, subject, body))
    with _lock:
        row = _read(uid)
        row["sent"] = [t for t in row["sent"] if _recent([t], now, timedelta(days=1))] + [now.isoformat()]
        _write(uid, row)
    return reached


def apply(uid: str, changes: dict, now: datetime) -> list[str]:
    """Save each alert's new state, mark the fired ones triggered (or keep repeating ones on), and return the texts
    to send now: everything waiting, when the user is under the message limits."""
    with _lock:
        row = _read(uid)
        dirty = False
        for a in row["items"]:
            hit = changes.get(a["id"])
            if not hit or hit[2] != a.get("rev") or a.get("status") != "active":
                continue                # edited or deleted while this check ran: leave it
            text, st, _ = hit
            a["state"] = st
            dirty = True
            if text:
                a.update(last_text=text, triggered_at=now.isoformat(), fired=int(a.get("fired") or 0) + 1)
                if not a.get("repeat"):
                    a["status"] = "triggered"
                row["pending"] = (row["pending"] + [text])[-MAX_PENDING:]
        texts = []
        if row["pending"] and may_send(row["sent"], now):
            texts, row["pending"] = row["pending"], []
            dirty = True
        if dirty:
            _write(uid, row)
    return texts


# ---------- alerts on exchange disclosures (insider trades, bulk and block deals) ----------
def evaluate_event(a: dict, rows: list[dict]) -> tuple[str | None, dict]:
    """An alert on disclosures: the deals of its kind on its stock that it hasn't sent yet, filed since it was set.
    Returns the message (else None) and the alert's new state."""
    st = dict(a.get("state") or {})
    seen = [x for x in st.get("seen") or [] if isinstance(x, str)]
    since = str(a.get("created_at") or "")[:10]
    new = [d for d in rows if isinstance(d, dict) and d.get("kind") in EVENTS.get(a["kind"], ()) and d.get("symbol") == a["symbol"]
           and d.get("id") not in seen and str(d.get("filed") or d.get("date") or d.get("day") or "") >= since]
    if not new:
        return None, st
    st["seen"] = (seen + [d["id"] for d in new])[-MAX_SEEN:]
    if a["kind"] == "surveillance":
        from .surveillance import change_text
        return f"{a['symbol']} {'; '.join(change_text(d) for d in new[:4])}. From exchange surveillance lists", st
    from .deals import describe as say
    more = f"; and {len(new) - 1} more" if len(new) > 1 else ""
    return f"{a['symbol']}: {say(new[0])}{more}. From exchange disclosures", st


def fire_events(rows: list[dict], now: datetime, limit, send=deliver, profile=None) -> int:
    """Check every active alert on insider trades and deals against the disclosures in `rows` (the evening's read of
    the whole market) and send what fired, within each user's plan and message limits. Returns messages sent."""
    profile = profile or db.cached_profile
    by_sym: dict[str, list[dict]] = {}
    for d in rows:
        by_sym.setdefault(d.get("symbol"), []).append(d)
    sent = 0
    for key, raw in db.all_settings_with_prefix(KEY):
        uid = key[len(KEY):]
        row = db.json_value(raw, {})
        active = sorted((a for a in row.get("items") or [] if isinstance(a, dict) and a.get("status") == "active"),
                        key=lambda a: a.get("created_at") or "")
        if not any(a.get("kind") in EVENTS for a in active):
            continue
        try:
            p = profile(uid)
            mine = active[:limit(p)]                 # over the plan's limit (after a downgrade): the oldest count
        except Exception:
            continue
        changes = {}
        for a in mine:
            if a.get("kind") not in EVENTS or a.get("region") != "IN" or not a.get("id"):
                continue
            text, st = evaluate_event(a, by_sym.get(a.get("symbol"), []))
            if text or st != (a.get("state") or {}):
                changes[a["id"]] = (text, st, a.get("rev"))
        texts = apply(uid, changes, now)
        if texts and flush(uid, p, texts, now, send):
            sent += 1
    return sent
