"""Tax report: capital gains on listed Indian shares, from the user's own tradebooks and tax P&L files, worked out
the way the Income Tax Act does it, as an estimate.

Buys and sales are matched first in, first out, per company; a tax P&L line, a sale already with its own buy, stays
as the broker matched it. A sale more than 12 months after its buy is long term.
Sales from 23 July 2024 pay the new rates (STCG 20%, LTCG 12.5%); earlier ones the old (15%, 10%). Long-term gains
are exempt up to ₹1.25 lakh a financial year from FY 2024-25 (₹1 lakh before). Shares held on 31 Jan 2018 cost at
least their price that day (grandfathering), and before 1 April 2018 long-term gains were exempt. Buying and selling
the same shares on the same day is intraday (speculative business income), shown apart. A bonus issue adds shares
that cost nothing and are held from the bonus date; a split changes the number of shares, not the cost or the date.

F&O, commodity and currency results (non-speculative business income) are kept as totals per segment and year, not
line by line, and go into the total tax estimate (tax_total.py) with the intraday result and the user's other income.

Stored per user in app_settings (taxlots:<uid>), seen only by that user, and deleted in one step. Facts and
arithmetic on the user's own trades; never a view on what to do."""
import json
import math
import re
from datetime import date, datetime, timedelta, timezone

from . import db, tax_total
from .engine.costs import IN_LTCG, IN_LTCG_EXEMPT, IN_STCG

KEY = "taxlots:"
FMV_KEY = "fmv2018:"              # fmv2018:<symbol> = {"v": the 31 Jan 2018 high a share, or null, "at": when looked up}
RATE_CHANGE = "2024-07-23"        # sales from this day pay the Budget 2024 rates
OLD_STCG, OLD_LTCG, OLD_EXEMPT = 0.15, 0.10, 100000
GF_DATE = "2018-01-31"            # shares held on this day: grandfathered at their price that day
LTCG_START = "2018-04-01"         # long-term gains on listed shares were exempt (section 10(38)) before this
CESS = 0.04
MAX_TRADES = 20000
MAX_FILES = 40
MAX_ROWS = 2000                   # realised lines sent for one year (the CSV has all of them)
EPS = 1e-6

DISCLAIMER = ("An estimate from the files you uploaded and the income you entered, not tax advice. It covers only "
              "the income you enter or import here, for an individual of the age band and residency you choose. Slab "
              "tax depends on your full income, and advance tax and TDS already paid aren't included. Check it with a "
              "chartered accountant (CA) before you file or pay tax.")
SEGMENTS = ("fno", "commodity", "currency")
SEGMENT_NAMES = {"fno": "F&O", "commodity": "Commodity", "currency": "Currency"}
MAX_BUSINESS = 120                # segment-year totals kept (three segments, many years, a few files each)
SETOFF_RULES = [
    "Short-term capital losses can be set off against both short-term and long-term gains.",
    "Long-term capital losses can only be set off against long-term gains.",
    "The long-term exemption (₹1.25 lakh a year from FY 2024-25, ₹1 lakh before) applies to the long-term gains "
    "left after set-off, once per financial year.",
    "Losses left over can be carried forward for 8 years, but only if the return is filed by its due date. "
    "Carried forward, they follow the same two rules.",
    "Capital losses can't be set off against salary or other income.",
    "Intraday (speculative) losses can only be set off against speculative income, and carried forward for 4 years.",
    "F&O, commodity and currency losses (non-speculative business losses) can be set off against any income except "
    "salary in the same year, and carried forward for 8 years against business income.",
]
NOTES = [
    "Rates before 4% cess and any surcharge. Your basic exemption limit and rebate can change the amount.",
    "Buys and sales are matched first in, first out, per company, across every file you uploaded.",
    "Brokerage and other charges in the files are added to the cost or taken off the sale. STT is not deductible.",
    "A bonus share costs nothing and is held from the bonus date. A split keeps the cost and the buy date.",
    "Intraday trades (bought and sold the same day) are speculative business income, taxed at your slab rate.",
    "F&O, commodity and currency trades are non-speculative business income, taxed at your slab rate. The charges in "
    "your broker's file (including STT and CTT, which business income can deduct) are taken off the result.",
    "Turnover is the total of profits and losses, trade by trade. Brokers' summaries often net them per contract "
    "first, which gives a smaller figure; both are shown.",
    "The estimate is for an individual of the age band and residency you choose (resident and below 60 until you say "
    "otherwise). The 87A rebate, surcharge (with its marginal relief) and cess follow each year's rules; the slab tax "
    "on the rest of your income is only as good as the figure you enter.",
    "It covers only income you enter or import here: house property, foreign income, other capital assets and "
    "anything else not entered aren't in it.",
]


class Lot(dict):
    """An open lot: {d (bought), qty, cost (total, with charges), fmv (31 Jan 2018 value, total), src, bonus}."""


# ---------- dates and rates ----------
def fy_of(d: str) -> int:
    """The financial year a date falls in, by its first year: 2024-07-22 -> 2024 (FY 2024-25)."""
    y, m = int(d[:4]), int(d[5:7])
    return y if m >= 4 else y - 1


def fy_label(y: int) -> str:
    return f"FY {y}-{str(y + 1)[2:]}"


def _date(d: str) -> date:
    return date.fromisoformat(d)


def anniversary(d: str) -> date:
    """12 months after a buy: the same day a year on (29 Feb -> 28 Feb)."""
    b = _date(d)
    try:
        return b.replace(year=b.year + 1)
    except ValueError:
        return b.replace(year=b.year + 1, day=28)


def long_term(buy: str, sell: str) -> bool:
    """Held for more than 12 months: sold after the first anniversary of the buy."""
    return _date(sell) > anniversary(buy)


def long_from(buy: str) -> str:
    """The first day a sale would be long term."""
    return (anniversary(buy) + timedelta(days=1)).isoformat()


def rates(sell: str) -> tuple[float, float]:
    """(short-term rate, long-term rate) for a sale on this day."""
    if sell >= RATE_CHANGE:
        return IN_STCG, IN_LTCG
    return OLD_STCG, (OLD_LTCG if sell >= LTCG_START else 0.0)


def exemption(fy: int) -> float:
    """The long-term exemption for a financial year (none before section 112A, from FY 2018-19)."""
    return float(IN_LTCG_EXEMPT) if fy >= 2024 else float(OLD_EXEMPT) if fy >= 2018 else 0.0


# ---------- the trades, stored ----------
def lot_key(t: dict) -> str:
    """Which company a trade is in: its listed symbol once matched, else its ISIN, else what the file called it."""
    raw = re.sub(r"^(NSE|BSE)[:\s]+|(-EQ|\.NS|\.BO)$", "", str(t.get("symbol") or "").strip().upper())
    return t.get("sym") or t.get("isin") or raw or str(t.get("name") or "").strip().upper()[:40] or "?"


def _dedup(t: dict) -> tuple:
    if t.get("tid"):
        return (t["d"], t["side"], lot_key(t), t["tid"])
    return (t["d"], t["side"], lot_key(t), round(float(t["qty"]), 4), round(float(t["price"]), 4), t.get("t") or "")


def merge(old: list[dict], new: list[dict]) -> tuple[list[dict], int, int]:
    """(trades, added, duplicates): the new file's trades added to the saved ones, without any already saved. Two
    identical lines in one file both count (two fills at the same price); the same file uploaded again adds nothing."""
    have: dict[tuple, int] = {}
    for t in old:
        k = _dedup(t)
        have[k] = have.get(k, 0) + 1
    out, added, dup = list(old), 0, 0
    for t in new:
        k = _dedup(t)
        if have.get(k, 0) > 0:
            have[k] -= 1
            dup += 1
            continue
        out.append(t)
        added += 1
    return out, added, dup


def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def _chunk_ok(c) -> bool:
    """A stored F&O, commodity or currency total that is whole: its segment, year, dates and numbers."""
    if not isinstance(c, dict) or c.get("seg") not in SEGMENTS or not isinstance(c.get("fy"), int) or not 2000 <= c["fy"] <= 2100:
        return False
    if not all(isinstance(c.get(k), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", c[k]) for k in ("first", "last")):
        return False
    return all(isinstance(c.get(k), (int, float)) and not isinstance(c.get(k), bool) and math.isfinite(c[k])
               for k in ("pnl", "turnover", "turnover_contract", "charges", "stt", "trades"))


def load(uid: str) -> dict:
    """{"trades": [...], "files": [{name, broker, kind, trades, at}], "fmv": {symbol: price}, "business": [segment-year
    totals], "updated_at"}."""
    got = db.json_value(db.get_setting(_key(uid)), {})
    got = got if isinstance(got, dict) else {}
    ok = []
    for t in got.get("trades") or []:
        if (isinstance(t, dict) and t.get("side") in ("B", "S") and isinstance(t.get("qty"), (int, float)) and t["qty"] > 0
                and isinstance(t.get("price"), (int, float)) and t["price"] >= 0 and isinstance(t.get("d"), str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["d"])):
            ok.append(t)
    fmv = got.get("fmv") if isinstance(got.get("fmv"), dict) else {}
    return {"trades": ok, "files": [f for f in got.get("files") or [] if isinstance(f, dict)],
            "fmv": {k: v for k, v in fmv.items() if isinstance(v, (int, float)) and v > 0},
            "business": [c for c in got.get("business") or [] if _chunk_ok(c)], "updated_at": got.get("updated_at")}


def save(uid: str, trades: list[dict], files: list[dict], fmv: dict | None = None, business: list[dict] | None = None):
    keep = ("d", "t", "side", "qty", "price", "charges", "isin", "symbol", "name", "sym", "exchange", "tid", "fmv", "src")
    slim = [{k: t[k] for k in keep if t.get(k) not in (None, "")} for t in trades[:MAX_TRADES]]
    db.set_setting(_key(uid), json.dumps({"trades": slim, "files": files[-MAX_FILES:], "fmv": fmv or {},
                                          "business": (business or [])[-MAX_BUSINESS:],
                                          "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, separators=(",", ":")))


def merge_business(old: list[dict], new: list[dict]) -> tuple[list[dict], int, int, int]:
    """(totals, added, replaced, same): a new file's F&O, commodity and currency totals beside the saved ones. Lines
    aren't kept, so a file can't be matched line by line: a segment's year from a file whose dates overlap a saved
    one replaces it (the same file again, or a full year after a quarter), and one that doesn't overlap is added (the
    next quarter)."""
    out = list(old)
    added = replaced = same = 0
    for c in new:
        hits = [o for o in out if o["seg"] == c["seg"] and o["fy"] == c["fy"] and not (c["last"] < o["first"] or c["first"] > o["last"])]
        if any(_same(o, c) for o in hits):
            same += 1
            continue
        out = [o for o in out if not any(o is h for h in hits)]
        out.append(c)
        if hits:
            replaced += 1
        else:
            added += 1
    return out, added, replaced, same


def _same(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in ("seg", "fy", "first", "last", "trades", "pnl", "charges"))


def business_year(fy: int, chunks: list[dict]) -> dict:
    """One year's F&O, commodity and currency totals, by segment: the result before and after charges, turnover and
    the biggest underlyings."""
    segs = []
    for seg in SEGMENTS:
        cs = [c for c in chunks if c["seg"] == seg and c["fy"] == fy]
        if not cs:
            continue
        by: dict[str, dict] = {}
        for c in cs:
            for b in c.get("by") or []:
                if isinstance(b, dict) and isinstance(b.get("pnl"), (int, float)):
                    cur = by.setdefault(str(b.get("u") or "?")[:20], {"pnl": 0.0, "turnover": 0.0, "trades": 0})
                    cur["pnl"] += b["pnl"]
                    cur["turnover"] += b.get("turnover") or 0
                    cur["trades"] += int(b.get("trades") or 0)
        pnl, charges = sum(c["pnl"] for c in cs), sum(c["charges"] for c in cs)
        segs.append({"seg": seg, "label": SEGMENT_NAMES[seg], "trades": int(sum(c["trades"] for c in cs)), "pnl": _r(pnl),
                     "charges": _r(charges), "stt": _r(sum(c["stt"] for c in cs)), "net": _r(pnl - charges),
                     "turnover": _r(sum(c["turnover"] for c in cs)), "turnover_contract": _r(sum(c["turnover_contract"] for c in cs)),
                     "first": min(c["first"] for c in cs), "last": max(c["last"] for c in cs),
                     "options": {k: _r(sum((c.get("options") or {}).get(k) or 0 for c in cs)) for k in ("pnl", "turnover", "trades")},
                     "futures": {k: _r(sum((c.get("futures") or {}).get(k) or 0 for c in cs)) for k in ("pnl", "turnover", "trades")},
                     "by": sorted(({"u": u, **{k: _r(v) for k, v in x.items()}} for u, x in by.items()),
                                  key=lambda x: (x["u"] == "Others", -abs(x["pnl"])))[:30]})
    return {"segments": segs, "pnl": _r(sum(x["pnl"] for x in segs)), "charges": _r(sum(x["charges"] for x in segs)),
            "net": _r(sum(x["net"] for x in segs)), "turnover": _r(sum(x["turnover"] for x in segs)),
            "turnover_contract": _r(sum(x["turnover_contract"] for x in segs)), "trades": sum(x["trades"] for x in segs)}


def with_total(y: dict, business: list[dict], inputs: dict | None, dividends: float = 0.0) -> dict:
    """A year from year() with its F&O totals, the total tax estimate on the user's inputs (and the other regime's
    figure on the same inputs, as a fact), and the return and audit facts. `dividends`: the year's dividend income
    the user included (from Tax tools)."""
    biz = business_year(y["fy"], business)
    parts = {s["seg"]: s["net"] for s in biz["segments"]}
    v = tax_total.clean(inputs) if inputs else tax_total.default_inputs()
    total = tax_total.estimate(y["fy"], v, y["buckets"], y["intraday"]["pnl"], biz["net"], parts, dividends=dividends)
    other = tax_total.estimate(y["fy"], {**v, "regime": "old" if v["regime"] == "new" else "new"}, y["buckets"],
                               y["intraday"]["pnl"], biz["net"], parts, dividends=dividends)
    turnover = (y["intraday"].get("turnover") or 0) + biz["turnover"]
    return {**y, "business": biz, "total": total, "inputs": {**v, "saved": bool(inputs)},
            "other_regime": {"regime": other["regime"], "total": other.get("total")} if other.get("available") else None,
            "filing": tax_total.filing_facts(y["fy"], turnover, bool(biz["segments"]) or y["intraday"]["count"] > 0),
            "turnover": _r(turnover)}


def delete(uid: str):
    db.delete_setting(_key(uid))


# ---------- matching buys to sales ----------
def _bonus(lots: list[Lot], a: dict) -> Lot | None:
    """The new lot a bonus issue adds: n shares for every h held before the ex-date, costing nothing. Whole shares
    only, as the company pays fractions in cash."""
    n, h = a["ratio"]
    held = sum(l["qty"] for l in lots if l["src"] != "pnl" and l["d"] < a["ex_date"])
    extra = held * n / h
    if abs(held - round(held)) < EPS:
        extra = math.floor(extra + 1e-9)
    if extra <= EPS:
        return None
    return Lot(d=a["ex_date"], qty=extra, cost=0.0, fmv=None, src="trades", bonus=True)


def _apply(lots: list[Lot], a: dict):
    """A bonus or split on the open lots. Lots from a tax P&L file are left alone: the broker has already counted it."""
    if a.get("kind") == "bonus" and a.get("ratio") and len(a["ratio"]) == 2 and all(isinstance(x, (int, float)) and x > 0 for x in a["ratio"]):
        new = _bonus(lots, a)
        if new:
            lots.append(new)
        return
    f = a.get("factor")
    if not isinstance(f, (int, float)) or not math.isfinite(f) or f <= 0:
        return
    for l in lots:
        if l["src"] != "pnl" and l["d"] < a["ex_date"]:
            l["qty"] = round(l["qty"] * f, 6)


def _pairs(trades: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """(pairs, the rest): a tax P&L line is a sale with its own buy (their ids end ":b" and ":s"), so the two are kept
    together rather than matched first in, first out against other files' lots."""
    groups: dict[str, dict[str, list[dict]]] = {}
    rest: list[dict] = []
    for t in trades:
        tid = str(t.get("tid") or "")
        if t.get("src") == "pnl" and tid.startswith("pnl:") and tid[-2:] in (":b", ":s"):
            groups.setdefault(tid[:-2], {"B": [], "S": []})[t["side"]].append(t)
        else:
            rest.append(t)
    pairs = []
    for g in groups.values():
        n = min(len(g["B"]), len(g["S"]))
        pairs += list(zip(g["B"][:n], g["S"][:n]))
        rest += g["B"][n:] + g["S"][n:]      # half a line (an edited file): matched the usual way
    return pairs, rest


def _pair(key: str, buy: dict, sale: dict, fmv: float | None, out: dict):
    """One tax P&L line: intraday when bought and sold the same day, else a realised gain as the broker matched it,
    grandfathered like any other lot."""
    q = min(buy["qty"], sale["qty"])
    cost = q * buy["price"] + (buy.get("charges") or 0) * q / buy["qty"]
    gross = q * sale["price"]
    net = gross - (sale.get("charges") or 0) * q / sale["qty"]
    d, bd = sale["d"], buy["d"]
    if d == bd:
        out["intraday"].append({"key": key, "d": d, "fy": fy_of(d), "qty": q, "buy": cost, "sell": net, "pnl": net - cost})
        return
    lt = long_term(bd, d)
    gf = None
    if lt and bd <= GF_DATE and d >= LTCG_START:
        each = buy.get("fmv") or fmv
        if each:
            gf = "applied"
            cost = max(cost, min(each * q, gross))
        else:
            gf = "missing"
    out["realised"].append({"key": key, "bought": bd, "sold": d, "fy": fy_of(d), "qty": q, "cost": cost, "sale": net,
                            "gain": net - cost, "term": "LT" if lt else "ST", "bonus": False, "gf": gf})


def _one(key: str, trades: list[dict], actions: list[dict], fmv: float | None, today: str, out: dict):
    """Every buy and sale of one company, in date order, with its bonuses and splits in between."""
    if not trades:
        return
    days: dict[str, list[dict]] = {}
    for t in trades:
        days.setdefault(t["d"], []).append(t)
    first = min(days)
    events = [(d, 2, d) for d in days]
    seen = set()
    for a in actions:
        ex = a.get("ex_date") or ""
        if first < ex <= today and (ex, a.get("kind")) not in seen:
            seen.add((ex, a.get("kind")))
            events.append((ex, 0, a))
    if first <= GF_DATE:
        events.append((GF_DATE, 3, None))   # at that day's close: after its trades, before anything on 1 Feb
    events.sort(key=lambda e: (e[0], e[1]))
    lots: list[Lot] = []
    for d, kind, payload in events:
        if kind == 0:
            _apply(lots, payload)
            continue
        if kind == 3:                       # grandfathering: each lot held now is valued at the 31 Jan 2018 price
            for l in lots:
                if l["fmv"] is None and fmv:
                    l["fmv"] = fmv * l["qty"]
            continue
        _day(key, d, days[d], lots, out)
    for l in lots:
        if l["qty"] > EPS:
            out["open"].append({"key": key, **l})


def _day(key: str, d: str, trades: list[dict], lots: list[Lot], out: dict):
    """One day's trades in one company: what was bought and sold the same day is intraday; the rest opens a lot or
    is matched to the oldest lots."""
    buys = [t for t in trades if t["side"] == "B"]
    sells = [t for t in trades if t["side"] == "S"]
    bq, sq = sum(t["qty"] for t in buys), sum(t["qty"] for t in sells)
    bval, sval = sum(t["qty"] * t["price"] for t in buys), sum(t["qty"] * t["price"] for t in sells)
    bchg, schg = sum(t.get("charges") or 0 for t in buys), sum(t.get("charges") or 0 for t in sells)
    intra = min(bq, sq)
    if intra > EPS:
        buy = intra * bval / bq + bchg * intra / bq
        sell = intra * sval / sq - schg * intra / sq
        out["intraday"].append({"key": key, "d": d, "fy": fy_of(d), "qty": intra, "buy": buy, "sell": sell, "pnl": sell - buy})
    if bq - intra > EPS:
        q = bq - intra
        fmvs = [t["fmv"] * t["qty"] for t in buys if t.get("fmv")]
        out_fmv = sum(fmvs) / bq * q if fmvs and len(fmvs) == len(buys) else None
        src = "trades" if any(t.get("src") != "pnl" for t in buys) else "pnl"
        lots.append(Lot(d=d, qty=q, cost=q * bval / bq + bchg * q / bq, fmv=out_fmv, src=src, bonus=False))
    left = sq - intra
    if left <= EPS:
        return
    each, chg_each = sval / sq, schg / sq
    while left > EPS and lots:
        l = lots[0]
        q = min(l["qty"], left)
        frac = q / l["qty"]
        cost, f = l["cost"] * frac, (l["fmv"] * frac if l["fmv"] is not None else None)
        l["qty"] -= q
        l["cost"] -= cost
        if l["fmv"] is not None:
            l["fmv"] -= f
        if l["qty"] <= EPS:
            lots.pop(0)
        left -= q
        gross, net = q * each, q * (each - chg_each)
        lt = long_term(l["d"], d)
        gf = None
        if lt and l["d"] <= GF_DATE and d >= LTCG_START:
            if f is not None:
                gf = "applied"
                cost = max(cost, min(f, gross))
            else:
                gf = "missing"
        out["realised"].append({"key": key, "bought": l["d"], "sold": d, "fy": fy_of(d), "qty": q, "cost": cost, "sale": net,
                                "gain": net - cost, "term": "LT" if lt else "ST", "bonus": l.get("bonus", False), "gf": gf})
    if left > EPS:
        out["unmatched"].append({"key": key, "d": d, "qty": left, "sale": left * (each - chg_each)})


def compute(trades: list[dict], actions: dict[str, list[dict]] | None = None, fmv: dict[str, float] | None = None,
            today: str | None = None) -> dict:
    """{"realised", "intraday", "open", "unmatched", "names"} for every company in the trades. `actions` are each
    company's bonuses and splits (by its key), `fmv` its 31 Jan 2018 price a share."""
    today = today or date.today().isoformat()
    by: dict[str, list[dict]] = {}
    names: dict[str, dict] = {}
    for t in trades:
        k = lot_key(t)
        by.setdefault(k, []).append(t)
        n = names.setdefault(k, {"symbol": t.get("sym") or t.get("symbol") or t.get("isin") or k, "name": t.get("name") or "",
                                 "isin": t.get("isin") or "", "listed": bool(t.get("sym"))})
        n["name"] = n["name"] or t.get("name") or ""
        n["isin"] = n["isin"] or t.get("isin") or ""
    out = {"realised": [], "intraday": [], "open": [], "unmatched": [], "names": names}
    for k, ts in by.items():
        pairs, rest = _pairs(ts)
        for b, s in pairs:
            _pair(k, b, s, (fmv or {}).get(k), out)
        rest.sort(key=lambda t: (t["d"], t.get("t") or ""))
        _one(k, rest, (actions or {}).get(k) or [], (fmv or {}).get(k), today, out)
    out["intraday"] = _by_day(out["intraday"])
    return out


def _by_day(rows: list[dict]) -> list[dict]:
    """Intraday results as one line per company and day, however many files and lines they came from."""
    days: dict[tuple, dict] = {}
    for r in rows:
        cur = days.get((r["key"], r["d"]))
        if cur is None:
            days[(r["key"], r["d"])] = dict(r)
        else:
            for f in ("qty", "buy", "sell", "pnl"):
                cur[f] += r[f]
    return list(days.values())


# ---------- one financial year ----------
BUCKETS = [("st_new", "Short-term, sold from 23 Jul 2024", IN_STCG), ("st_old", "Short-term, sold before 23 Jul 2024", OLD_STCG),
           ("lt_new", "Long-term, sold from 23 Jul 2024", IN_LTCG), ("lt_old", "Long-term, sold before 23 Jul 2024", OLD_LTCG),
           # mutual funds that aren't equity-oriented (money_mf.py): no exemption; slab-rate gains go to slab income
           ("st_slab", "Short-term at your slab rate (debt and other funds)", 0.0),
           ("lt_112", "Long-term, other funds, 12.5% without indexation", 0.125),
           ("lt_112i", "Long-term, other funds, 20% with indexation", 0.20)]
SLAB = {"st_slab"}
ST_ORDER, LT_ORDER = ["st_new", "st_old", "st_slab"], ["lt_112i", "lt_new", "lt_112", "lt_old"]


STEP_NAMES = {"st_new": "short-term gains taxed at 20% (sold from 23 Jul 2024)", "st_old": "short-term gains taxed at 15% (sold before 23 Jul 2024)",
              "lt_new": "long-term gains taxed at 12.5% (sold from 23 Jul 2024)", "lt_old": "long-term gains taxed at 10% (sold before 23 Jul 2024)",
              "st_slab": "short-term gains taxed at your slab rate (mutual funds)", "lt_112": "long-term fund gains taxed at 12.5% without indexation",
              "lt_112i": "long-term fund gains taxed at 20% with indexation"}


def _bucket(r: dict) -> str | None:
    if r.get("bucket"):                     # a mutual fund sale under the non-equity rules
        return r["bucket"]
    if r["term"] == "LT" and r["sold"] < LTCG_START:
        return None                         # exempt then, gains and losses alike
    return f"{'st' if r['term'] == 'ST' else 'lt'}_{'new' if r['sold'] >= RATE_CHANGE else 'old'}"


def money(v: float) -> str:
    """₹ in the Indian way: ₹1,25,000."""
    neg, v = v < 0, abs(round(v))
    s = str(int(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"{'-' if neg else ''}₹{s}"


def year(fy: int, realised: list[dict], intraday: list[dict], limit: int | None = MAX_ROWS) -> dict:
    """One financial year: gains and losses by kind and rate, set-off in the order that leaves the least tax (losses
    against the highest-rate gains first), the exemption, the estimated tax and what is left to carry forward."""
    rows = [r for r in realised if r["fy"] == fy]
    gains = {b: 0.0 for b, _, _ in BUCKETS}
    st_loss = lt_loss = exempt_gain = 0.0
    for r in rows:
        b = _bucket(r)
        if b is None:
            exempt_gain += r["gain"]
        elif r["gain"] >= 0:
            gains[b] += r["gain"]
        elif b.startswith("st"):
            st_loss -= r["gain"]
        else:
            lt_loss -= r["gain"]
    net = dict(gains)
    steps: list[str] = []

    def use(order: list[str], loss: float, what: str) -> float:
        for b in order:
            take = min(net[b], loss)
            if take > EPS:
                net[b] -= take
                loss -= take
                steps.append(f"{what} of {money(take)} set off against {STEP_NAMES[b]}.")
        return loss
    st_left = use(ST_ORDER, st_loss, "Short-term losses")
    lt_left = use(LT_ORDER, lt_loss, "Long-term losses")
    st_left = use(LT_ORDER, st_left, "Short-term losses")
    cap = exemption(fy)
    ex_left, exempt = cap, {b: 0.0 for b in net}
    for b in ("lt_new", "lt_old"):
        take = min(net[b], ex_left)
        if take > EPS:
            exempt[b] = take
            ex_left -= take
    used = cap - ex_left
    if used > EPS:
        steps.append(f"{money(used)} of long-term gains is exempt (the {money(cap)} a year limit).")
    buckets, tax = [], 0.0
    for b, label, rate in BUCKETS:
        taxable = max(0.0, net[b] - exempt[b])
        t = taxable * rate
        tax += t
        if gains[b] or net[b]:
            buckets.append({"key": b, "label": label, "rate": rate, "gains": _r(gains[b]), "after_setoff": _r(net[b]),
                            "exempt": _r(exempt[b]), "taxable": _r(taxable), "tax": _r(t), **({"slab": True} if b in SLAB else {})})
    if st_left > EPS or lt_left > EPS:
        steps.append(f"Left to carry forward: {money(st_left)} short-term and {money(lt_left)} long-term loss.")
    st_rows = [r for r in rows if r["term"] == "ST"]
    lt_rows = [r for r in rows if r["term"] == "LT" and _bucket(r)]
    intra = [i for i in intraday if i["fy"] == fy]
    rows_out = sorted(rows, key=lambda r: (r["sold"], r["key"]))
    return {
        "fy": fy, "label": fy_label(fy),
        "stcg": {"gains": _r(sum(r["gain"] for r in st_rows if r["gain"] > 0)), "losses": _r(-sum(r["gain"] for r in st_rows if r["gain"] < 0)),
                 "net": _r(sum(r["gain"] for r in st_rows)), "sales": _r(sum(r["sale"] for r in st_rows))},
        "ltcg": {"gains": _r(sum(r["gain"] for r in lt_rows if r["gain"] > 0)), "losses": _r(-sum(r["gain"] for r in lt_rows if r["gain"] < 0)),
                 "net": _r(sum(r["gain"] for r in lt_rows)), "sales": _r(sum(r["sale"] for r in lt_rows))},
        "exempt_old": _r(exempt_gain) if any(_bucket(r) is None for r in rows) else None,
        "exemption": {"limit": cap, "used": _r(used), "left": _r(ex_left)},
        "buckets": buckets, "steps": steps, "tax": _r(tax), "tax_with_cess": _r(tax * (1 + CESS)),
        "carry_forward": {"st": _r(st_left), "lt": _r(lt_left)},
        "intraday": {"count": len(intra), "buy": _r(sum(i["buy"] for i in intra)), "sell": _r(sum(i["sell"] for i in intra)),
                     "pnl": _r(sum(i["pnl"] for i in intra)), "turnover": _r(sum(abs(i["pnl"]) for i in intra))},
        "gf_missing": sum(1 for r in rows if r["gf"] == "missing"), "gf_applied": sum(1 for r in rows if r["gf"] == "applied"),
        "count": len(rows), "rows": [_row(r) for r in rows_out[:limit]],
    }


def _r(v, dp=2):
    return None if v is None else round(v, dp)


def _row(r: dict) -> dict:
    return {"key": r["key"], "bought": r["bought"], "sold": r["sold"], "qty": round(r["qty"], 4), "cost": _r(r["cost"]),
            "sale": _r(r["sale"]), "gain": _r(r["gain"]), "term": r["term"], "bonus": r["bonus"], "gf": r["gf"],
            "rate": r["rate"] if "rate" in r else (rates(r["sold"])[0] if r["term"] == "ST" else rates(r["sold"])[1]),
            **({"mf": True, "kind": r.get("kind")} if r.get("src") == "mf" else {})}


# ---------- open lots below cost ----------
def below_cost(open_lots: list[dict], quotes: dict[str, dict], today: str) -> dict:
    """Open lots worth less than they cost at today's price: how much below, how long held, and whether a sale today
    would be short or long term. Facts only."""
    rows, unpriced = [], 0
    for l in open_lots:
        price = (quotes.get(l["key"]) or {}).get("price")
        if not price:
            unpriced += 1
            continue
        value = l["qty"] * price
        diff = value - l["cost"]
        if diff >= -0.005:
            continue
        lt = long_term(l["d"], today)
        rows.append({"key": l["key"], "bought": l["d"], "qty": round(l["qty"], 4), "cost": _r(l["cost"]),
                     "cost_each": _r(l["cost"] / l["qty"]) if l["qty"] else None, "price": _r(price), "value": _r(value),
                     "loss": _r(diff), "loss_pct": _r(diff / l["cost"] * 100, 1) if l["cost"] else None,
                     "days": (_date(today) - _date(l["d"])).days, "term": "LT" if lt else "ST",
                     "long_from": None if lt else long_from(l["d"]), "bonus": l.get("bonus", False)})
    rows.sort(key=lambda r: r["loss"])
    return {"rows": rows, "unpriced": unpriced, "open": len(open_lots),
            "st": _r(sum(r["loss"] for r in rows if r["term"] == "ST")), "lt": _r(sum(r["loss"] for r in rows if r["term"] == "LT"))}


def holdings_check(open_lots: list[dict], items: list[dict]) -> list[dict]:
    """Companies where the shares left open by the trade files differ from My Holdings (a file missing, a transfer
    in, or a bonus not yet in the data)."""
    have: dict[str, float] = {}
    for l in open_lots:
        have[l["key"]] = have.get(l["key"], 0) + l["qty"]
    held = {i["symbol"]: float(i["qty"]) for i in items if i.get("symbol")}
    out = []
    for k in sorted(have):                  # only companies in the files: a holding from another broker isn't a gap
        a, b = round(have[k], 4), round(held.get(k, 0), 4)
        if k in held and abs(a - b) > 1e-3:
            out.append({"key": k, "files": a, "holdings": b})
    return out[:50]


def report(trades: list[dict], actions: dict, fmv: dict, quotes: dict, items: list[dict], today: str,
           business: list[dict] | None = None, inputs: dict[int, dict] | None = None, extra: list[dict] | None = None,
           dividends: dict[int, float] | None = None) -> dict:
    """The whole page: every financial year with trades or F&O (and the current one), each with its total tax
    estimate, open lots below cost, and the lines that couldn't be worked out."""
    c = compute(trades, actions, fmv, today)
    c["realised"] += extra or []              # mutual fund sales (money_mf.realised), worked out there
    business, inputs = business or [], inputs or {}
    fys = sorted({r["fy"] for r in c["realised"]} | {i["fy"] for i in c["intraday"]} | {b["fy"] for b in business} | {fy_of(today)}
                 | set(dividends or {}),
                 reverse=True)
    unmatched = {}
    for u in c["unmatched"]:
        cur = unmatched.setdefault(u["key"], {"key": u["key"], "qty": 0.0, "first": u["d"]})
        cur["qty"] = round(cur["qty"] + u["qty"], 4)
        cur["first"] = min(cur["first"], u["d"])
    return {"years": [with_total(year(y, c["realised"], c["intraday"]), business, inputs.get(y), (dividends or {}).get(y, 0.0)) for y in fys], "current_fy": fy_of(today),
            "below_cost": below_cost(c["open"], quotes, today), "names": c["names"],
            "unmatched_sales": sorted(unmatched.values(), key=lambda u: u["first"])[:100],
            "holdings_check": holdings_check(c["open"], items) if items else [],
            "pre_2018": sorted({l["key"] for l in c["open"] if l["d"] <= GF_DATE} | {r["key"] for r in c["realised"] if r["gf"]}),
            "rules": SETOFF_RULES, "notes": NOTES, "disclaimer": DISCLAIMER}
