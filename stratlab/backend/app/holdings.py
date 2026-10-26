"""My Holdings: the stocks a user holds, imported from their broker's export or typed in, matched to listed
companies, and valued at today's prices.

Stored per user in app_settings (holdings:<uid>), seen only by that user, and deleted in one step. Everything shown
is a fact about the user's own positions: value, gain or loss, sector mix, and what the other pages already report
for each stock. Never a view on what to do with them."""
import json
import re
from datetime import date, datetime, timedelta, timezone

from . import db, instrument_kinds

KEY = "holdings:"
SOURCES = ("Zerodha Console", "Zerodha Kite", "Zerodha Kite file", "Statement", "Interactive Brokers", "Groww", "Upstox", "Angel One", "ICICI Direct", "HDFC Securities", "CSV", "Manual")
# the sector indices' names, in the exchange's own broad sector names, so both kinds of label add up together
SECTOR_OF_INDEX = {"NIFTY BANK": "Financial Services", "NIFTY PSU BANK": "Financial Services", "NIFTY PVT BANK": "Financial Services",
                   "NIFTY FIN SERVICE": "Financial Services", "NIFTY IT": "Information Technology",
                   "NIFTY FMCG": "Fast Moving Consumer Goods", "NIFTY PHARMA": "Healthcare", "NIFTY HEALTHCARE": "Healthcare",
                   "NIFTY METAL": "Commodities", "NIFTY AUTO": "Consumer Discretionary", "NIFTY ENERGY": "Energy",
                   "NIFTY OIL AND GAS": "Energy"}
UNCLASSIFIED = "Not classified"
# a US sector fund's sector in the exchange's broad sector names, so an Indian and a US technology company are one sector
# on the sector card ("Technology" and "Information Technology" were two)
SECTOR_OF_US = {"Technology": "Information Technology", "Financials": "Financial Services", "Health care": "Healthcare",
                "Consumer staples": "Fast Moving Consumer Goods", "Consumer discretionary": "Consumer Discretionary",
                "Materials": "Commodities", "Communication": "Telecommunication", "Real estate": "Realty"}
MARKET_TZ = {"IN": "Asia/Kolkata", "US": "America/New_York"}


def sector_name(s: str | None) -> str:
    """One name per sector, whichever market's words a holding was saved with."""
    return SECTOR_OF_US.get(s or "", s) or UNCLASSIFIED


def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def _parse(raw: str | None) -> dict:
    try:
        got = json.loads(raw or "{}")
    except (ValueError, TypeError):
        got = {}
    items = got.get("items") if isinstance(got, dict) else None
    clean = [i for i in items or [] if isinstance(i, dict) and i.get("symbol") and isinstance(i.get("qty"), (int, float))]
    return {"items": clean, "source": got.get("source") if isinstance(got, dict) else None,
            "updated_at": got.get("updated_at") if isinstance(got, dict) else None}


def load(uid: str) -> dict:
    """{"items": [...], "source", "updated_at"}; empty when the user has none (or the row is damaged)."""
    return _parse(db.get_setting(_key(uid)))


ADJUST_KEYS = ("since", "applied", "dismissed", "adjusted")      # what corporate actions keep on a holding


def pct_split(values: list[float]) -> list[float]:
    """Shares of the total in tenths of a percent, rounded by largest remainder so they add to exactly 100."""
    total = sum(values)
    raw = [v / total * 1000 for v in values]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[:1000 - sum(out)]:
        out[i] += 1
    return [x / 10 for x in out]


def stamp(items: list[dict], before: list[dict], day: str) -> list[dict]:
    """Each holding with the day its quantity was saved (`since`): kept from before while the quantity is the same,
    today's date when it is new or changed. A bonus or split from that day on is offered as an adjustment."""
    old = {i["symbol"]: i for i in before}
    out = []
    for i in items:
        o = old.get(i["symbol"])
        if o and o.get("since") and abs(float(o["qty"]) - float(i["qty"])) < 1e-9:
            out.append({**i, **{k: o[k] for k in ADJUST_KEYS if k in o}})
        else:
            out.append({**{k: v for k, v in i.items() if k not in ADJUST_KEYS}, "since": day})
    return out


def saved_day(now: datetime | None = None) -> date:
    """The day a quantity saved now stands for: today on a trading day, else the last session before it. A file saved
    on a Saturday holds Friday's positions, and a bonus or split that went ex on Friday isn't in it yet (the new shares
    are credited days after the record date), so it is still offered as an adjustment."""
    from zoneinfo import ZoneInfo
    from .data import calendar
    d = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Kolkata")).date()
    for _ in range(10):
        if calendar.is_trading_day("IN", d):
            break
        d -= timedelta(days=1)
    return d


def _data(before: list[dict], items: list[dict], source: str, stamped: bool, since: str | None) -> dict:
    if not stamped:
        items = stamp(items, before, min(since, saved_day().isoformat()) if since else saved_day().isoformat())
    return {"items": items, "source": source if source in SOURCES else "CSV",
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")}   # a stale-list check tells saves apart


def save(uid: str, items: list[dict], source: str, stamped: bool = False, since: str | None = None) -> dict:
    """Save the holdings. Unless they're `stamped` already, each one's `since` is set (see stamp): `since` when the
    quantities are as of an earlier day (a statement's last day), else the day they're saved."""
    data = _data(load(uid)["items"] if not stamped else [], items, source, stamped, since)
    db.set_setting(_key(uid), json.dumps(data))
    return data


def update(uid: str, fn) -> dict | None:
    """Change the holdings atomically, so a daily broker sync and a hand edit can't lose each other's save.
    fn(load's result) returns (items, source[, stamped[, since]]) as save takes them, None to leave the holdings, or
    db.REMOVE to delete them. It runs again on the new holdings if another save got in first, so keep side effects
    out of it. Returns what was saved (None when nothing was)."""
    out = []

    def go(raw):
        before = _parse(raw)
        got = fn(before)
        if got is None or got is db.REMOVE:
            out[:] = [None]
            return got
        items, source, *more = got
        out[:] = [_data(before["items"], items, source, *(more + [False, None][len(more):]))]
        return json.dumps(out[0])
    db.update_setting(_key(uid), go)
    return out[0]


def delete(uid: str):
    db.delete_setting(_key(uid))


def market_of(i: dict) -> str:
    """"IN" for a stock listed in India (every holding saved before US stocks could be added), or "US"."""
    return "US" if i.get("market") == "US" else "IN"


def indian(items: list[dict]) -> list[dict]:
    """The holdings listed in India: the only ones the exchange's filings, corporate actions and tax rules cover."""
    return [i for i in items if market_of(i) == "IN"]


def symbols(uid: str) -> list[str]:
    """The user's Indian holdings, largest first by cost, for the My Stocks newsletter."""
    items = indian(load(uid)["items"])
    return [i["symbol"] for i in sorted(items, key=lambda i: -(i["qty"] * (i.get("avg") or 0)))]


# ---------- matching a broker's rows to listed companies ----------
def clean_symbol(s: str) -> str:
    """A symbol as brokers write it, without the exchange around it: "NSE:SBIN", "SBIN-EQ", "SBIN.NS" -> "SBIN"."""
    s = re.sub(r"^(NSE|BSE)[:\s]+", "", (s or "").strip().upper())
    s = re.sub(r"(\.NS|\.BO|-EQ)$", "", s)
    return s if re.fullmatch(r"[A-Z0-9&\-._]{1,20}", s) else ""


class Matcher:
    """Finds the listed company for one row: by ISIN, then by symbol (NSE, an NSE restricted series, or listed only
    on BSE by its symbol or six-digit code), then by company name.

    equity(symbol) and by_name(name) return the app's instrument or None; isin(code) gives the NSE symbol for an ISIN
    from the exchange's list. With market data offline (online False), only the exchange's list is used."""

    def __init__(self, equity, by_name, isin, listed: dict[str, str], online: bool):
        self.equity, self.by_name, self.isin, self.listed, self.online = equity, by_name, isin, listed, online

    def _inst(self, sym: str) -> dict | None:
        if not sym:
            return None
        if self.online:
            hit = self.equity(sym)
            return {"symbol": hit["symbol"], "exchange": hit["exchange"], "name": hit.get("name") or hit["symbol"]} if hit else None
        return {"symbol": sym, "exchange": "NSE", "name": self.listed[sym]} if sym in self.listed else None

    def _unit(self, row: dict) -> dict | None:
        """An ETF, REIT, InvIT or gold bond not in the day's lists: kept as the file names it (by symbol, else its
        ISIN), without a price until one is found."""
        if instrument_kinds.base(instrument_kinds.classify(row.get("symbol"), row.get("isin"), row.get("name"))) == "stock":
            return None
        sym = clean_symbol(row.get("symbol") or "") or (row.get("isin") or "")
        return {"symbol": sym, "exchange": "NSE", "name": (row.get("name") or sym)[:80]} if sym else None

    def match(self, row: dict) -> tuple[dict | None, str | None]:
        """(the company, None) or (None, why it couldn't be matched)."""
        if row.get("isin"):
            hit = self._inst(self.isin(row["isin"]) or "")
            if hit:
                return hit, None
        hit = self._inst(clean_symbol(row.get("symbol") or ""))
        if hit:
            return hit, None
        if row.get("name") and self.online:
            got = self.by_name(row["name"])
            if got:
                return {"symbol": got["symbol"], "exchange": got["exchange"], "name": got.get("name") or got["symbol"]}, None
        kept = self._unit(row)
        if kept:
            return kept, None
        if not self.online:
            # DG-004: said as what was checked, so a made-up symbol (ZZZNOTREAL) isn't blamed on the market data alone
            return None, ("No NSE company on the stored list matches this line. BSE-only companies can be checked once "
                          "market data is back; try again later.")
        if row.get("isin") and not row["isin"].startswith("INE"):
            return None, "Not a company's shares (a fund, bond or other security)."
        return None, "No listed company on NSE or BSE matches this line."


US_TICKER = re.compile(r"[A-Z][A-Z0-9]{0,5}(?:-[A-Z])?")


def match_us(rows: list[dict], find) -> tuple[list[dict], list[dict]]:
    """(holdings, unmatched lines) for US tickers typed in. find(ticker) gives {"symbol", "name"} for a listed US
    company's common shares, or None."""
    found, missed = [], []
    for r in rows:
        sym = (r.get("symbol") or "").strip().upper().replace(".", "-")
        hit = find(sym) if US_TICKER.fullmatch(sym) else None
        if not hit:
            missed.append({"line": r.get("line"), "text": r.get("text") or sym, "symbol": sym, "isin": r.get("isin"),
                           "reason": "No US-listed company has that ticker."})
            continue
        found.append({"symbol": hit["symbol"], "exchange": "US", "name": hit.get("name") or hit["symbol"], "market": "US",
                      "currency": "USD", "isin": None, "qty": round(float(r["qty"]), 4),
                      "avg": round(float(r["avg"]), 4) if r.get("avg") else None})
    return found, missed


ADDED = "added"          # the part of a source's holding added from a file or by hand ("accts" key), kept through its syncs


def _add_part(base: dict, r: dict) -> dict:
    """A source's holding (base, with "via") with shares from a file or typed in (r) on top: the source's next read sets
    only its own part, so these shares stay. The quantity is kept per part in "accts" (the source's own part under its
    name, or a statement's per-account parts) and the added part's cost in "added_cost" (a bonus or split changes the
    quantity, never the cost)."""
    out = dict(base)
    accts = dict(base.get("accts") or {base["via"]: base["qty"]})
    had = accts.get(ADDED, 0)
    accts[ADDED] = round(had + r["qty"], 4)
    cost = base.get("added_cost") if had else 0.0
    out["added_cost"] = round(cost + r["qty"] * r["avg"], 4) if cost is not None and r.get("avg") else None
    q = base["qty"] + r["qty"]
    out["avg"] = (base["avg"] * base["qty"] + r["avg"] * r["qty"]) / q if base.get("avg") and r.get("avg") else None
    out["qty"], out["accts"] = round(q, 4), accts
    return out


def merge(rows: list[dict]) -> list[dict]:
    """One holding per company: lines for the same stock (on NSE and on BSE, or split by the broker) add up, and the
    average price is weighted by quantity (none if any line has none). A line from a file or typed in that adds to a
    holding a broker or statement keeps ("via") is kept as its own part, so that source's next read doesn't drop it."""
    out: dict[str, dict] = {}
    for r in rows:
        k = f"{r['exchange']}:{r['symbol']}"
        cur = out.get(k)
        if not cur:
            out[k] = dict(r)
            continue
        if bool(cur.get("via")) != bool(r.get("via")):
            out[k] = _add_part(cur, r) if cur.get("via") else _add_part(r, cur)
            continue
        if r.get("file_close"):            # the later file's close stands (DG-002)
            cur["file_close"], cur["file_close_day"] = r["file_close"], r.get("file_close_day")
        q = cur["qty"] + r["qty"]
        if cur.get("avg") and r.get("avg"):
            cur["avg"] = (cur["avg"] * cur["qty"] + r["avg"] * r["qty"]) / q
        else:
            cur["avg"] = None   # one line has no cost, so the combined cost is unknown
        cur["qty"] = q
    return drop_stale_accts(list(out.values()))


VIA_NAMES = {"kite": "Kite", "ibkr": "IBKR", "cas": "the statement"}
SYNCED = ("kite", "ibkr")      # a broker that syncs; a statement's quantity typed over is replaced by the next statement


def set_qty(old: dict, qty: float, avg: float | None) -> tuple[dict, str | None]:
    """(row, note) for a quantity typed over a broker's holding (old, with "via" in SYNCED). The source's own part
    stays the source's; the difference becomes the user's added part (holdings.ADDED), so the next read keeps the
    total typed. Its cost is the typed total cost (quantity x the average, the one typed or else the one shown) less the
    source's part's cost, so the average stays as shown until the source's own average moves. Below the source's part
    there's nothing to keep it by: the quantity is saved as typed, and the note says the next read sets it back."""
    accts = dict(old.get("accts") or {old["via"]: old["qty"]})
    had = accts.pop(ADDED, 0)
    own = round(sum(accts.values()), 4)
    out = {k: v for k, v in old.items() if k not in ("accts", "added_cost")}
    out["qty"], out["avg"] = qty, avg
    extra = round(qty - own, 4)
    if extra < 0:
        name = VIA_NAMES.get(old["via"], old["via"])
        return out, (f"{old['symbol']}: {qty:g} is below the {own:g} {name} holds, so the next {name} read sets it "
                     f"back to {own:g}. Sell or move the shares there to lower it for good.")
    if not extra:
        return {**out, "accts": accts} if old.get("accts") and set(accts) != {old["via"]} else out, None
    own_cost = None
    if old.get("avg") is not None:
        if not had:
            own_cost = old["avg"] * own
        elif old.get("added_cost") is not None:
            own_cost = old["avg"] * old["qty"] - old["added_cost"]
    cost = qty * avg - own_cost if avg is not None and own_cost is not None else None
    if cost is None or cost < 0:          # the source's part's cost unknown (or above the total typed)
        cost = extra * avg if avg is not None else None
    out["accts"] = {**accts, ADDED: extra}
    out["added_cost"] = round(cost, 4) if cost is not None else None
    return out, None


def drop_stale_accts(rows: list[dict]) -> list[dict]:
    """The rows without "accts" where its parts no longer add up to the quantity (typed or added over a statement's
    per-account one: no hidden second quantity; the next statement sets it again)."""
    return [{k: v for k, v in r.items() if k not in ("accts", "added_cost")}
            if r.get("accts") and abs(sum(r["accts"].values()) - r["qty"]) > 1e-9 else r for r in rows]


def cap(items: list[dict], before: list[dict], limit: int) -> tuple[list[dict], list[str]]:
    """(kept, symbols left out) for a list about to be saved under the plan's limit. Stocks already held are always
    kept (a downgrade never deletes them); new ones fill only the room left under the limit."""
    held = {(market_of(i), i["symbol"]) for i in before}
    old = [i for i in items if (market_of(i), i["symbol"]) in held]
    new = [i for i in items if (market_of(i), i["symbol"]) not in held]
    room = max(0, limit - len(old))
    return old + new[:room], [i["symbol"] for i in new[room:]]


def match_all(rows: list[dict], matcher: Matcher, close_day: str | None = None) -> tuple[list[dict], list[dict]]:
    """(holdings, unmatched lines) for a file's rows. `close_day`: the session a close in the file is of (the latest
    completed one when it was uploaded: a "previous closing price" read on a Saturday is Friday's)."""
    found, missed = [], []
    for r in rows:
        hit, why = matcher.match(r)
        if not hit:
            missed.append({"line": r.get("line"), "text": r.get("text") or r.get("symbol") or r.get("name") or "",
                           "symbol": r.get("symbol"), "isin": r.get("isin"), "reason": why})
            continue
        kind = instrument_kinds.classify(hit["symbol"], r.get("isin"), r.get("name") or hit.get("name"))
        # the file's own close is kept with the day it is of, for while live prices are off (DG-002)
        close = {"file_close": round(float(r["close"]), 4), "file_close_day": close_day} if r.get("close") and close_day else {}
        found.append({**hit, "isin": r.get("isin") or None, "qty": round(float(r["qty"]), 4),
                      "avg": round(float(r["avg"]), 4) if r.get("avg") else None, **({"kind": kind} if instrument_kinds.base(kind) != "stock" else {}),
                      **close})
    return merge(found), missed


def sector_label(index: str | None, exchange_path: list[str] | None) -> str:
    """The exchange's broad sector for a stock, or its sector index's, in the same words."""
    if exchange_path:
        return exchange_path[0]
    if index:
        from .rotation import _label
        return SECTOR_OF_INDEX.get(index) or re.sub(r"^Nifty\s+", "", _label("IN", index, None))
    return UNCLASSIFIED


def us_sector(fund: str | None) -> str:
    """A US stock's sector, from the sector fund it's in (XLK: Technology), in the same words as the US pages."""
    if not fund:
        return UNCLASSIFIED
    from .rotation import _label
    return sector_name(_label("US", fund, None))


# ---------- the page ----------
def latest_trade(quotes: list[dict], now: datetime) -> datetime | None:
    """The time of the latest trade among some quotes (each has an ISO `at`; one without a zone is read as India's),
    never later than `now`. None when no quote carries one."""
    from zoneinfo import ZoneInfo
    best = None
    for q in quotes:
        at = q.get("at")
        try:
            t = datetime.fromisoformat(at) if isinstance(at, str) else None
        except ValueError:
            t = None
        if t is None:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        t = min(t, now)
        if best is None or t > best:
            best = t
    return best


def _r(v, dp=2):
    return None if v is None else round(v, dp)


def session_day(q: dict, market: str) -> str | None:
    """The day (in the market's own zone) of the session a quote's price and change are from, or None when the quote
    carries no trade time. A quote whose change was worked out for the last completed session (`change_day`, set while the
    market hasn't traded today) is of that session, whatever its last trade's time says (R41A)."""
    from zoneinfo import ZoneInfo
    if q.get("change_day"):
        return str(q["change_day"])[:10]
    at = q.get("at")
    try:
        t = datetime.fromisoformat(at) if isinstance(at, str) else None
    except ValueError:
        return None
    if t is None:
        return None
    zone = ZoneInfo(MARKET_TZ.get(market, "Asia/Kolkata"))
    return (t.replace(tzinfo=zone) if t.tzinfo is None else t.astimezone(zone)).date().isoformat()


def _position(i: dict, q: dict) -> dict:
    """One holding at today's price, in its own currency."""
    price, qty, avg = q.get("price"), i["qty"], i.get("avg")
    val = qty * price if price else None
    inv = qty * avg if avg else None
    pnl = val - inv if val is not None and inv is not None else None
    chg = qty * q["change"] if price and q.get("change") is not None else None
    us = market_of(i) == "US"
    code = "stock" if us else i.get("kind") or instrument_kinds.classify(i["symbol"], i.get("isin"), i.get("name"))
    kind = instrument_kinds.base(code)
    return {"symbol": i["symbol"], "exchange": i.get("exchange") or ("US" if us else "NSE"), "name": i.get("name") or i["symbol"],
            "market": "US" if us else "IN", "currency": "USD" if us else "INR", "kind": kind,
            "kind_label": None if kind == "stock" else instrument_kinds.label(code),
            "sector": instrument_kinds.sector(code) or sector_name(i.get("sector")), "qty": qty, "avg": _r(avg), "price": _r(price),
            "value": _r(val), "invested": _r(inv), "pnl": _r(pnl), "pnl_pct": _r(pnl / inv * 100) if pnl is not None and inv else None,
            "day": _r(chg), "day_pct": _r(q.get("change_pct")), "session": session_day(q, "US" if us else "IN") if price else None,
            "via": i.get("via"), "price_from": q.get("from") if price else None}


def _counted(r: dict) -> bool:
    """Whether a position is in the value, cost and gain-or-loss totals: one with a buy price is (at its price, or at
    cost when it has no price); one with a price but no buy price is not, since its gain or loss is unknown and counting
    only its value would make value minus cost differ from the gain or loss."""
    return r["invested"] is not None or r["value"] is None


def _totals(rows: list[dict], rate, session: str | None = None) -> dict:
    """Value, cost, gain or loss and the day's change of the same positions, each converted with rate(row) (None leaves
    a position out). A position without a price counts at cost; one without a buy price is left out (see `_counted`).
    `session` is the day the day's change is for: a position whose price is from another session (a US stock's last
    session, seen during India's) is left out of the day's change."""
    value = cost = cost_priced = day = before = 0.0
    pnl, days, n = None, False, 0
    for r in rows:
        fx = rate(r)
        if fx is None:
            continue
        if _counted(r):
            n += 1
            value += fx * (r["value"] if r["value"] is not None else r["invested"] or 0)
            cost += fx * (r["invested"] or 0)
            if r["pnl"] is not None:
                pnl = (pnl or 0) + fx * r["pnl"]
                cost_priced += fx * r["invested"]
        if r["day"] is not None and (session is None or r.get("session") in (None, session)):
            days = True
            day += fx * r["day"]
            before += fx * (r["value"] - r["day"])
    day_total = day if days else None
    priced = sum(1 for r in rows if r["price"] is not None and rate(r) is not None and _counted(r))
    # DG-001: a gain or loss of some of the lines (the others at cost, with no price) is said to be of those lines, never
    # passed off as the whole portfolio's (AAPL's +131.8% stood for 9 lines, 8 of them unpriced)
    return {"value": _r(value), "invested": _r(cost), "pnl": _r(pnl), "pnl_pct": _r(pnl / cost_priced * 100) if pnl is not None and cost_priced else None,
            "day": _r(day_total), "day_pct": _r(day_total / before * 100) if day_total is not None and before else None,
            "count": n, "priced": priced, "pnl_partial": {"priced": priced, "lines": n} if pnl is not None and priced < n else None}


def day_session(rows: list[dict]) -> str | None:
    """The session the day's change is for: the latest one among the Indian positions (the page is India's), else the
    latest among all."""
    ind = [r["session"] for r in rows if r.get("session") and r["market"] == "IN" and r["day"] is not None]
    every = [r["session"] for r in rows if r.get("session") and r["day"] is not None]
    return max(ind or every) if (ind or every) else None


def view(items: list[dict], quotes: dict[str, dict], us_quotes: dict[str, dict] | None = None, usd_inr: float | None = None) -> dict:
    """Each position at today's price (when there is one), the totals and the mix by sector. A position without a
    price keeps its cost, so the page still adds up; one without an average price has no gain or loss.

    US stocks are valued in dollars (prices from `us_quotes`) and counted in the rupee totals at `usd_inr` rupees a
    dollar; without a rate they're left out of the rupee totals and shown on their own. `us` has their dollar totals."""
    us_quotes = us_quotes or {}
    rows = [_position(i, (us_quotes if market_of(i) == "US" else quotes).get(i["symbol"]) or {}) for i in items]
    rate = (lambda r: 1.0 if r["market"] == "IN" else usd_inr)
    session = day_session(rows)
    totals = _totals(rows, rate, session)
    # positions with a price but no buy price: shown, and named under the totals, but not in them
    left = [r for r in rows if not _counted(r) and rate(r) is not None]
    totals["no_cost"] = {"count": len(left), "symbols": [r["symbol"] for r in left],
                         "value": _r(sum(r["value"] * rate(r) for r in left))} if left else None
    totals["session"] = session
    # the other session's moves, left out of the day's change: named, so the page can say so
    totals["other_session"] = sorted({r["symbol"] for r in rows if session and r.get("session") and r["session"] != session
                                      and r["day"] is not None and rate(r) is not None})
    # weights and the sector mix are shares of everything held that has a value (a position without a buy price too)
    value = sum((r["value"] if r["value"] is not None else r["invested"] or 0) * rate(r) for r in rows if rate(r) is not None)
    shown = [r for r in rows if rate(r) is not None]
    shares = pct_split([((r["value"] if r["value"] is not None else r["invested"]) or 0) * rate(r) for r in shown]) if value else []
    for r in rows:
        r["weight"] = None
    for r, w in zip(shown, shares):
        r["weight"] = w
    rows.sort(key=lambda r: -((r["value"] if r["value"] is not None else r["invested"] or 0) * (rate(r) or 0)))
    sectors: dict[str, float] = {}
    for r in rows:
        if rate(r) is not None:
            sectors[r["sector"]] = sectors.get(r["sector"], 0) + (r["value"] if r["value"] is not None else r["invested"] or 0) * rate(r)
    ordered = sorted(sectors.items(), key=lambda kv: (kv[0] == UNCLASSIFIED, -kv[1]))      # "Not classified" last, whatever its size
    pcts = pct_split([v for _, v in ordered]) if value and ordered else [None] * len(ordered)
    allocation = [{"sector": s, "value": _r(v), "pct": p, "count": sum(1 for r in rows if r["sector"] == s and rate(r) is not None)}
                  for (s, v), p in zip(ordered, pcts)]
    us = [r for r in rows if r["market"] == "US"]
    totals["count"] = len(rows)
    return {"rows": rows, "allocation": allocation, "totals": totals,
            "us": {**_totals(us, lambda r: 1.0, session), "in_total": usd_inr is not None} if us else None,
            "usd_inr": _r(usd_inr, 4) if us and usd_inr else None}


def facts(trend: dict | None, filings: list[dict] | None, today, upcoming) -> dict:
    """What the other pages already say about one held stock: its stage and Supertrend, red and amber filings in the
    last 3 months, the latest filings and a scheduled results meeting. Facts only."""
    from .intel.filings import summarise
    out = {"stage": None, "st_up": None, "signal": None, "red": None, "amber": None, "flags": [], "recent": [], "results": None}
    if trend:
        out.update(stage=trend.get("stage"), st_up=trend.get("st_up"), signal=trend.get("signal"))
    if filings is not None:
        s = summarise(filings)
        out.update(red=s["red"], amber=s["amber"], flags=[f["label"] for f in s["flags"]][:4],
                   recent=[{"at": i["at"], "label": i["label"], "severity": i["severity"], "subject": i["subject"], "url": i.get("url")}
                           for i in filings[:3]],
                   results=upcoming(filings, today))
    return out
