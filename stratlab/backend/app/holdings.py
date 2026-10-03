"""My Holdings: the stocks a user holds, imported from their broker's export or typed in, matched to listed
companies, and valued at today's prices.

Stored per user in app_settings (holdings:<uid>), seen only by that user, and deleted in one step. Everything shown
is a fact about the user's own positions: value, gain or loss, sector mix, and what the other pages already report
for each stock. Never a view on what to do with them."""
import json
import re
from datetime import datetime, timezone

from . import db

KEY = "holdings:"
SOURCES = ("Zerodha Console", "Zerodha Kite", "Groww", "Upstox", "Angel One", "ICICI Direct", "HDFC Securities", "CSV", "Manual")
# the sector indices' names, in the exchange's own broad sector names, so both kinds of label add up together
SECTOR_OF_INDEX = {"NIFTY BANK": "Financial Services", "NIFTY PSU BANK": "Financial Services", "NIFTY PVT BANK": "Financial Services",
                   "NIFTY FIN SERVICE": "Financial Services", "NIFTY IT": "Information Technology",
                   "NIFTY FMCG": "Fast Moving Consumer Goods", "NIFTY PHARMA": "Healthcare", "NIFTY HEALTHCARE": "Healthcare",
                   "NIFTY METAL": "Commodities", "NIFTY AUTO": "Consumer Discretionary", "NIFTY ENERGY": "Energy",
                   "NIFTY OIL AND GAS": "Energy"}
UNCLASSIFIED = "Not classified"


def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def load(uid: str) -> dict:
    """{"items": [...], "source", "updated_at"}; empty when the user has none (or the row is damaged)."""
    try:
        got = json.loads(db.get_setting(_key(uid)) or "{}")
    except (ValueError, TypeError):
        got = {}
    items = got.get("items") if isinstance(got, dict) else None
    clean = [i for i in items or [] if isinstance(i, dict) and i.get("symbol") and isinstance(i.get("qty"), (int, float))]
    return {"items": clean, "source": got.get("source") if isinstance(got, dict) else None,
            "updated_at": got.get("updated_at") if isinstance(got, dict) else None}


ADJUST_KEYS = ("since", "applied", "dismissed", "adjusted")      # what corporate actions keep on a holding


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


def save(uid: str, items: list[dict], source: str, stamped: bool = False) -> dict:
    """Save the holdings. Unless they're `stamped` already, each one's `since` is set (see stamp)."""
    if not stamped:
        from zoneinfo import ZoneInfo
        items = stamp(items, load(uid)["items"], datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat())
    data = {"items": items, "source": source if source in SOURCES else "CSV",
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    db.set_setting(_key(uid), json.dumps(data))
    return data


def delete(uid: str):
    db.delete_setting(_key(uid))


def symbols(uid: str) -> list[str]:
    """The user's holdings, largest first by cost, for the My Stocks newsletter."""
    items = load(uid)["items"]
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
        if not self.online:
            return None, "Market data is offline, so only NSE stocks could be checked. Try again later."
        if row.get("isin") and not row["isin"].startswith("INE"):
            return None, "Not a company's shares (a fund, bond or other security)."
        return None, "No listed company on NSE or BSE matches this line."


def merge(rows: list[dict]) -> list[dict]:
    """One holding per company: lines for the same stock (on NSE and on BSE, or split by the broker) add up, and the
    average price is weighted by quantity."""
    out: dict[str, dict] = {}
    for r in rows:
        k = f"{r['exchange']}:{r['symbol']}"
        cur = out.get(k)
        if not cur:
            out[k] = dict(r)
            continue
        q = cur["qty"] + r["qty"]
        if cur.get("avg") and r.get("avg"):
            cur["avg"] = (cur["avg"] * cur["qty"] + r["avg"] * r["qty"]) / q
        else:
            cur["avg"] = cur.get("avg") or r.get("avg")
        cur["qty"] = q
    return list(out.values())


def match_all(rows: list[dict], matcher: Matcher) -> tuple[list[dict], list[dict]]:
    """(holdings, unmatched lines) for a file's rows."""
    found, missed = [], []
    for r in rows:
        hit, why = matcher.match(r)
        if not hit:
            missed.append({"line": r.get("line"), "text": r.get("text") or r.get("symbol") or r.get("name") or "", "reason": why})
            continue
        found.append({**hit, "isin": r.get("isin") or None, "qty": round(float(r["qty"]), 4),
                      "avg": round(float(r["avg"]), 4) if r.get("avg") else None})
    return merge(found), missed


def sector_label(index: str | None, exchange_path: list[str] | None) -> str:
    """The exchange's broad sector for a stock, or its sector index's, in the same words."""
    if exchange_path:
        return exchange_path[0]
    if index:
        from .rotation import _label
        return SECTOR_OF_INDEX.get(index) or re.sub(r"^Nifty\s+", "", _label("IN", index, None))
    return UNCLASSIFIED


# ---------- the page ----------
def _r(v, dp=2):
    return None if v is None else round(v, dp)


def view(items: list[dict], quotes: dict[str, dict]) -> dict:
    """Each position at today's price (when there is one), the totals and the mix by sector. A position without a
    price keeps its cost, so the page still adds up; one without an average price has no gain or loss."""
    rows, value, cost, cost_priced, day = [], 0.0, 0.0, 0.0, 0.0
    for i in items:
        q = quotes.get(i["symbol"]) or {}
        price, qty, avg = q.get("price"), i["qty"], i.get("avg")
        val = qty * price if price else None
        inv = qty * avg if avg else None
        pnl = val - inv if val is not None and inv is not None else None
        chg = qty * q["change"] if price and q.get("change") is not None else None
        rows.append({"symbol": i["symbol"], "exchange": i.get("exchange") or "NSE", "name": i.get("name") or i["symbol"],
                     "sector": i.get("sector") or UNCLASSIFIED, "qty": qty, "avg": _r(avg), "price": _r(price),
                     "value": _r(val), "invested": _r(inv), "pnl": _r(pnl), "pnl_pct": _r(pnl / inv * 100) if pnl is not None and inv else None,
                     "day": _r(chg), "day_pct": _r(q.get("change_pct"))})
        value += val if val is not None else (inv or 0)
        cost += inv or 0
        if pnl is not None:
            cost_priced += inv
        day += chg or 0
    priced = [r for r in rows if r["pnl"] is not None]
    pnl = sum(r["pnl"] for r in priced) if priced else None
    days = [r for r in rows if r["day"] is not None]
    day_total = day if days else None
    before = sum(r["value"] - r["day"] for r in days)
    for r in rows:
        weight = r["value"] if r["value"] is not None else r["invested"]
        r["weight"] = _r((weight or 0) / value * 100, 1) if value else None
    rows.sort(key=lambda r: -(r["value"] if r["value"] is not None else r["invested"] or 0))
    sectors: dict[str, float] = {}
    for r in rows:
        sectors[r["sector"]] = sectors.get(r["sector"], 0) + (r["value"] if r["value"] is not None else r["invested"] or 0)
    allocation = [{"sector": s, "value": _r(v), "pct": _r(v / value * 100, 1) if value else None, "count": sum(1 for r in rows if r["sector"] == s)}
                  for s, v in sorted(sectors.items(), key=lambda kv: -kv[1])]
    return {"rows": rows, "allocation": allocation,
            "totals": {"value": _r(value), "invested": _r(cost), "pnl": _r(pnl), "pnl_pct": _r(pnl / cost_priced * 100) if pnl is not None and cost_priced else None,
                       "day": _r(day_total), "day_pct": _r(day_total / before * 100) if day_total is not None and before else None,
                       "count": len(rows), "priced": sum(1 for r in rows if r["price"] is not None)}}


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
