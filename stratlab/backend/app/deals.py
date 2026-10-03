"""Deals and insider trades for Indian companies, from exchange disclosures: trades by promoters, directors and key
staff (insider-trading disclosures, with pledges), substantial acquisitions and sales (the takeover code), and the
day's bulk and block deals with the named buyer or seller.

Facts only, as filed: who, which way, how many, at what value, when, and the link to the disclosure. Nothing here
calls a trade a signal, ranks companies by it or says what to do about it.

A company's own list is read live (cached for an hour). Once every evening a job reads the whole market's latest
disclosures in a few calls and uses them three ways: the stock alerts on deals and insider trades, the screens'
"a promoter or insider bought in the last N days" filter (one stored date per company), and the My Stocks
newsletter (the last few days' disclosures, stored by the day they were filed)."""
import json
import threading
from datetime import date, datetime, timedelta

from . import db
from .intel.filings import DEAL_KINDS, DEALS_DAYS, RELATIONS, ist_now, sort_deals
from .intel.net import SourceError, TTLCache
from .newsletter import job as news_job

KINDS = ("insider", "sast", "bulk", "block")
METHOD = {"insider": "insider_trades", "sast": "sast", "bulk": "bulk_deals", "block": "block_deals"}
FLOW_DAYS = 180                      # the checklist's window, as for US insiders
SCREEN_DAYS = (30, 90, 180, 365)     # the screens' "bought in the last N days" choices
BUYS_KEY = "deals:buys:IN"           # {"from", "to", "buys": {symbol: ISO date of the latest open-market purchase}}
DAY_KEY = "deals:day:IN:"            # deals:day:IN:<ISO day> = [deals filed that day], the whole market
KEEP_DAYS = 10                       # filed days kept for the newsletter
RECENT_DAYS = 4                      # each evening run reads the last few days again: disclosures arrive late
BACKFILL_DAYS = 30                   # the screens' history is filled a month at a time, back to a year
SOURCE = "exchange disclosures"
SIDE_WORD = {"bought": "bought", "sold": "sold", "pledged": "pledged", "released": "released a pledge on",
             "invoked": "had a pledge invoked on"}
_cache = TTLCache(max_items=200)


# ---------- one company ----------
def fetch(feed, kind: str, symbol: str | None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
    return getattr(feed, METHOD[kind])(symbol, days, to)


def report(feed, symbol: str, days: int = DEALS_DAYS) -> dict:
    """A company's deals and insider trades over the last year, newest first. A feed that's down leaves its kind
    out (named in `problems`); all of them down is an error."""
    items, problems, last = [], [], None
    for kind in KINDS:
        try:
            items += fetch(feed, kind, symbol, days)
        except SourceError as e:
            problems.append(DEAL_KINDS[kind])
            last = e
    if last is not None and len(problems) == len(KINDS):
        raise last
    items = sort_deals(items)
    return {"symbol": symbol, "days": days, "items": items[:300], "count": len(items), "problems": problems,
            "flow": flow(items), "flow_days": FLOW_DAYS, "source": SOURCE}


def flow(items: list[dict], today: date | None = None, days: int = FLOW_DAYS) -> dict | None:
    """Shares promoters and insiders bought and sold on the open market in the last `days`. Off-market transfers,
    employee stock options and pledges aren't decisions to buy or sell, so they're left out. None when there were
    no such trades."""
    today = today or ist_now().date()
    cut = (today - timedelta(days=days)).isoformat()
    out = {"bought": 0.0, "sold": 0.0, "bought_value": 0.0, "sold_value": 0.0}
    people: dict[str, set] = {"bought": set(), "sold": set()}
    for d in items or []:
        if d.get("kind") != "insider" or d.get("mode") != "market" or d.get("side") not in people or str(d.get("date")) < cut:
            continue
        side = d["side"]
        out[side] += d.get("qty") or 0
        out[f"{side}_value"] += d.get("value") or 0
        people[side].add(d.get("who"))
    if not out["bought"] and not out["sold"]:
        return None
    return {**out, "buyers": len(people["bought"]), "sellers": len(people["sold"]), "days": days}


def _group_in(n: float) -> str:
    from .stock_alerts import _group_in as g
    return g(str(int(round(n))))


def rupees(v: float | None) -> str:
    """₹2.4 crore, ₹35.0 lakh or ₹48,000: how amounts this size are usually written in India."""
    if v is None:
        return "–"
    if v >= 1e7:
        return f"₹{v / 1e7:,.1f} crore"
    if v >= 1e5:
        return f"₹{v / 1e5:,.1f} lakh"
    return "₹" + _group_in(v)


def flow_text(f: dict) -> str:
    """"2 bought 15,000 shares (₹1.2 crore) · 1 sold 3,000": only the sides that happened."""
    def side(n, verb, qty, value):
        return f"{n} {'person' if n == 1 else 'people'} {verb} {_group_in(qty)} shares" + (f" ({rupees(value)})" if value else "")
    parts = [side(f["buyers"], "bought", f["bought"], f["bought_value"]) if f["bought"] else None,
             side(f["sellers"], "sold", f["sold"], f["sold_value"]) if f["sold"] else None]
    return " · ".join(p for p in parts if p)


def _day(iso: str) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{d.day} {d:%b %Y}"


def describe(d: dict) -> str:
    """One deal in a sentence: "Promoter A Shah bought 10,000 shares on the open market (₹29.0 lakh) on 2 Oct 2026"."""
    who = d["who"]
    if d.get("relation"):
        who = f"{RELATIONS.get(d['relation'], 'Other')} {who}" if d["relation"] != "other" else who
    qty = f" {_group_in(d['qty'])} shares" if d.get("qty") else " shares"
    how = {"market": " on the open market", "off_market": " off market", "esop": " through employee stock options"}.get(d.get("mode"), "")
    if d["kind"] in ("bulk", "block"):
        how = ""
        price = f" at ₹{d['price']:,.2f}" if d.get("price") else ""
    else:
        price = f" ({rupees(d['value'])})" if d.get("value") else ""
    head = f"{d['label']}: " if d["kind"] != "insider" else "Insider trade: "
    return f"{head}{who} {SIDE_WORD.get(d['side'], d['side'])}{qty}{how}{price} on {_day(d['date'])}"


# ---------- the whole market, once an evening ----------
def latest(feed, today: date) -> tuple[list[dict], list[str]]:
    """Every kind of deal the exchange published in the last few days, for the whole market (one call per kind)."""
    to = datetime.combine(today, datetime.min.time())
    rows, problems = [], []
    for kind in KINDS:
        try:
            rows += fetch(feed, kind, None, RECENT_DAYS, to)
        except SourceError as e:
            problems.append(f"{DEAL_KINDS[kind]}: {e}")
    return sort_deals(rows), problems


def store_days(rows: list[dict], today: date) -> None:
    """Keep the deals by the day they were filed, merged with what was kept before; days past KEEP_DAYS go."""
    by_day: dict[str, list[dict]] = {}
    for d in rows:
        by_day.setdefault(d["filed"], []).append(d)
    cut = (today - timedelta(days=KEEP_DAYS)).isoformat()
    for day, ds in by_day.items():
        if day < cut or day > today.isoformat():
            continue
        old = db.json_value(db.get_setting(DAY_KEY + day), [])
        db.set_setting(DAY_KEY + day, json.dumps(sort_deals([d for d in old if isinstance(d, dict) and d.get("id")] + ds)))
    for key, _ in db.all_settings_with_prefix(DAY_KEY):
        if key[len(DAY_KEY):] < cut:
            db.delete_setting(key)
    _cache.clear()


def note_buys(rows: list[dict], frm: date, to: date, today: date | None = None) -> dict:
    """Add the open-market purchases by promoters and insiders in `rows` (read for frm..to) to the stored dates the
    screens filter on, and widen the stored span. Dates older than a year are dropped."""
    today = today or ist_now().date()
    st = buys_state()
    buys = st["buys"]
    for d in rows:
        if d.get("kind") == "insider" and d.get("mode") == "market" and d.get("side") == "bought":
            if d["date"] > buys.get(d["symbol"], ""):
                buys[d["symbol"]] = d["date"]
    cut = (today - timedelta(days=366)).isoformat()
    st["buys"] = {s: day for s, day in buys.items() if day >= cut}
    st["from"] = min(filter(None, (st.get("from"), frm.isoformat())))
    st["to"] = max(filter(None, (st.get("to"), to.isoformat())))
    db.set_setting(BUYS_KEY, json.dumps(st))
    _cache.clear()
    return st


def buys_state() -> dict:
    st = db.json_value(db.get_setting(BUYS_KEY), {})
    buys = st.get("buys") if isinstance(st.get("buys"), dict) else {}
    return {"from": st.get("from") if isinstance(st.get("from"), str) else None,
            "to": st.get("to") if isinstance(st.get("to"), str) else None,
            "buys": {str(k): v for k, v in buys.items() if isinstance(v, str)}}


def buys() -> dict:
    """The stored purchase dates for the screens, from memory for ten minutes; empty when storage can't be read."""
    hit = _cache.get("buys")
    if hit is not None:
        return hit
    try:
        st = buys_state()
    except Exception:
        return {"from": None, "to": None, "buys": {}}
    _cache.set("buys", st, 600)
    return st


def backfill_step(feed, today: date) -> bool:
    """Read one more month of the market's insider trades, further back, until the screens' dates cover a year.
    True when it read something."""
    st = buys_state()
    start = date.fromisoformat(st["from"]) if st.get("from") else today
    if start <= today - timedelta(days=max(SCREEN_DAYS)):
        return False
    to = datetime.combine(start, datetime.min.time())
    rows = fetch(feed, "insider", None, BACKFILL_DAYS, to)
    note_buys(rows, start - timedelta(days=BACKFILL_DAYS), start if st.get("to") else today, today)
    return True


def recent_for(symbol: str, since: str, today: date | None = None) -> list[dict]:
    """A company's deals filed from the day `since` (ISO) to today, from the stored days; newest first."""
    today = today or ist_now().date()
    try:
        start = max(date.fromisoformat(str(since)[:10]), today - timedelta(days=KEEP_DAYS))
    except ValueError:
        return []
    out, d = [], start
    while d <= today:
        day = d.isoformat()
        rows = _cache.get(("day", day))
        if rows is None:
            rows = db.json_value(db.get_setting(DAY_KEY + day), [])
            _cache.set(("day", day), rows, 600)
        out += [r for r in rows if isinstance(r, dict) and r.get("symbol") == symbol]
        d += timedelta(days=1)
    return sort_deals(out)


class Job(news_job.Job):
    """Every evening after the exchange's day of disclosures: read the market's latest deals, keep them for the
    newsletter and the screens, and fire the stock alerts on them. Between runs, fill the screens' year of history a
    month at a time. Uses the newsletter job's run markers (newsjob:deals), so a restart never fires alerts twice."""
    AT = ("Asia/Kolkata", "20:40")

    def __init__(self, feed_fn, fire):
        super().__init__()
        self.feed_fn, self.fire = feed_fn, fire
        self.status.update(rows=0, problems=[], backfill_to=None)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="deals").start()

    def tick(self, now: datetime) -> int:
        tz, at = self.AT
        day = self.due("deals", now, tz, at)
        if not day:
            try:
                if backfill_step(self.feed_fn(), ist_now().date()):
                    self.status["backfill_to"] = buys_state().get("from")
            except Exception as e:                  # busy or down: next time
                self.status["last_error"] = f"history: {str(e)[:160]}"
            return 0
        self.mark("deals", day)
        rows, problems = latest(self.feed_fn(), day)
        store_days(rows, day)
        if not any(p.startswith(DEAL_KINDS["insider"]) for p in problems):
            note_buys(rows, day - timedelta(days=RECENT_DAYS), day, day)
        sent = self.fire(rows, now)
        self.status.update(last_run=now.isoformat(), sent=sent, rows=len(rows), problems=problems[:4],
                           last_error=None if not problems else problems[0][:200])
        return sent

