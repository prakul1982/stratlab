"""fix98: a theme's members that are no longer listed (production, 26-27 Nov 2026: "sector metrics: not read: US EA ... isn't a company that
files with the SEC", and QRVO, TMHC, TPH and SPR, companies taken private or merged that have left the SEC's company_tickers.json, still
read for a dive at every run and one of them, Qorvo, in its layers' medians).

The rule: a member that its market's current company list doesn't name is "no longer listed": listed so in the dive, once, with why, and
in no figure, median, total or ranking (theme_data.build, as the floor's companies are). The lists are the ones the app already reads and
keeps each day: the SEC's company tickers for the US (sec.SEC.tickers, kept a day), and for India the day's list of listed companies the
company pages keep (stock_pages "stocks:list:IN": the exchange's equity list, EQUITY_L.csv, with the companies listed on BSE alone, by their
BSE trading symbols and codes).

Missing data never removes a member:
- when the list can't be read, or the kept one is older than LIST_FRESH_DAYS (its daily read failing), nobody is removed;
- a member whose own stored price is of the last TRADED_DAYS before the list still trades (a list without its listing, an SME board's
  company the equity list doesn't carry, a listing newer than the list), and is never removed by it;
- a US member the SEC lists under another ticker (Paramount Skydance's PSKY, now Skydance Corp, SKYD: the same registrant) is still a
  filer: `renamed` finds the one registrant its name is, and the dive reads that ticker's page and filings for it (never removed)."""
from __future__ import annotations

import re
import threading
from datetime import date, timedelta

LIST_FRESH_DAYS = 3        # a kept list older than this (days before today) isn't the current one: nobody is removed on it
# a member with a stored price this many days before the list's day or later still trades: never removed. India's list leaves out the SME
# boards' companies listed on NSE alone (EQUITY_L.csv is the main board; the BSE-only list carries BSE's), so a thinly traded one there gets
# a month before a list without it counts (the replay of 27 Nov: Laxmipati Engineering's last trade 11 Nov)
TRADED_DAYS = {"US": 10, "IN": 30}
NOT_LISTED_KIND = "no longer listed"
_NAME_DROP = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "the", "holdings", "holding", "group",
              "sa", "nv", "ag", "lp", "llc"}
# what the lists never carry, so a list without it is no proof it left: India's trusts (REITs and InvITs: the equity list is of companies),
# a foreign company's depositary receipts traded over the counter in the US (the SEC lists companies that file with it; an unsponsored
# ADR's company files nothing there)
NOT_ON_LISTS = {"IN": re.compile(r"\b(?:trust|reit|invit)\b", re.I), "US": re.compile(r"\b(?:adrs?|ads|unspon\w*)\b", re.I)}
_lock = threading.Lock()
_kept: dict = {}           # (region, day) -> the list as `current` gives it; the latest day of each market only (bounded: one a market)


def name_key(name) -> str:
    """A company's name for matching across lists: lower case, letters and digits only, without legal forms ("Skydance Corp" -> "skydance")."""
    # the SEC's state suffix ("TEXAS CAPITAL BANCSHARES INC/TX", "... CORP /DE/") is no part of the name
    plain = re.sub(r"(?:\s*/[a-z]{2,3}/?)+\s*$", "", str(name or "").lower())
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", plain.replace("&", " and ")).split() if w not in _NAME_DROP]
    return " ".join(words)


def from_sec(tickers: dict, day: str) -> dict | None:
    """The US list from the SEC's {TICKER: {cik, name}}: {"day", "symbols", "names": {name_key: {cik: [tickers]}}}; None for no list."""
    if not isinstance(tickers, dict) or len(tickers) < 1000:          # the real list has some ten thousand: fewer is a broken answer
        return None
    names: dict[str, dict[int, list[str]]] = {}
    ciks: dict[str, int] = {}
    titles: dict[int, str] = {}
    for t, v in tickers.items():
        if isinstance(v, dict) and v.get("cik") is not None:
            names.setdefault(name_key(v.get("name")), {}).setdefault(int(v["cik"]), []).append(str(t).upper())
            ciks[str(t).upper()] = int(v["cik"])          # data100: each ticker's registrant, in the SEC's order (its main ticker first)
            titles.setdefault(int(v["cik"]), str(v.get("name") or ""))
    return {"day": day, "symbols": {str(t).upper() for t in tickers}, "names": names, "ciks": ciks, "titles": titles}


def registrant_of(sym: str, lst: dict | None) -> int | None:
    """data100: the SEC number of the registrant the SEC's list names a ticker under (any way of writing a share class); None off the list."""
    ciks = (lst or {}).get("ciks") or {}
    return next((ciks[f] for f in _forms("US", sym) if f in ciks), None)


def same_registrant(region: str, syms, lst: dict | None, now_as: dict | None = None) -> dict[str, str]:
    """data100 (the deck audits' Electric utilities: Bright Horizon Energy kept under Black Hills, two rows of one company): {symbol left out:
    symbol kept} for members the SEC's current list names under one registrant (one SEC number: Black Hills Corp renamed itself Bright
    Horizon Energy Corp and the SEC lists it as HZN and BKH; a company's two classes of common stock). They are one company, kept once
    under the ticker the SEC lists first for it (its main one); a member read by its ticker now (`now_as`, renamed) counts as that one. {}
    for India or with no list (nobody is merged on a guess)."""
    if region != "US" or not lst or not lst.get("ciks"):
        return {}
    order = {t: i for i, t in enumerate(lst["ciks"])}
    groups: dict[int, list[str]] = {}
    for s in syms:
        cik = registrant_of((now_as or {}).get(s, s), lst)
        if cik is not None:
            groups.setdefault(cik, []).append(s)
    out = {}
    for cik, ss in groups.items():
        if len(ss) < 2:
            continue
        rank = lambda s: min((order.get(f, len(order)) for f in _forms("US", (now_as or {}).get(s, s))), default=len(order))   # noqa: E731
        keep = min(ss, key=lambda s: (rank(s), s))
        out.update({s: keep for s in ss if s != keep})
    return out


def from_kept(kept: dict | None, bse: dict | None, today: date) -> dict | None:
    """The Indian list from the company pages' kept day's list ({"at", "rows": {symbol or "BSE:<code>": name}}) and the BSE-only
    companies' trading symbols ({code: {"ts"}}); None when there is none, it is broken, or it is older than LIST_FRESH_DAYS."""
    rows = (kept or {}).get("rows") if isinstance(kept, dict) else None
    day = str((kept or {}).get("at") or "")[:10] if isinstance(kept, dict) else ""
    if not isinstance(rows, dict) or len(rows) < 100 or not day:
        return None
    try:
        if (today - date.fromisoformat(day)).days > LIST_FRESH_DAYS:
            return None
    except ValueError:
        return None
    syms = set()
    for s in rows:
        s = str(s).upper()
        if s.startswith("BSE:"):
            code = s.split(":", 1)[1]
            syms.add(code)
            ts = str(((bse or {}).get(code) or {}).get("ts") or "").upper()
            if ts:
                syms.add(ts)
        else:
            syms.add(s)
    return {"day": day, "symbols": syms, "names": {}}


def _forms(region: str, sym: str) -> set[str]:
    s = str(sym or "").strip().upper()
    if region == "US":
        return {s, s.replace(".", "-"), s.replace("-", "."), s.replace("/", "-")}
    out = {s}
    try:
        from ..us_ticker import canon_in
        out.add(canon_in(s))
    except Exception:
        pass
    return out


def renamed(region: str, sym: str, names, lst: dict | None, taken=()) -> str | None:
    """The ticker the market's list names a member by now, when its own isn't on the list but its name is that of exactly one registrant
    (US: PSKY, the SEC now listing Skydance Corp under SKYD); None otherwise, or when that ticker is another member's (`taken`)."""
    if not lst or region != "US" or _forms(region, sym) & lst["symbols"]:
        return None
    from .sec import non_common
    for n in names or ():
        k = name_key(n)
        hit = (lst.get("names") or {}).get(k) if k else None
        if hit and len(hit) == 1:
            tickers = [t for t in next(iter(hit.values())) if not non_common(t)]
            if tickers and tickers[0] not in taken:
                return tickers[0]
    return None


def gone(region: str, sym: str, price_at, lst: dict | None, names=()) -> dict | None:
    """{"day", "why"} when the member is no longer on its market's current list, by the rule in the module's note; None when it is listed,
    still trades, is of a kind the list never carries (NOT_ON_LISTS, by its `names`), or there is no current list to go by."""
    if not lst or _forms(region, sym) & lst["symbols"]:
        return None
    if region in NOT_ON_LISTS and any(NOT_ON_LISTS[region].search(str(n or "")) for n in names or ()):
        return None
    day = str(lst.get("day") or "")
    try:
        floor = (date.fromisoformat(day) - timedelta(days=TRADED_DAYS.get(region, 30))).isoformat()
    except ValueError:
        return None
    if price_at and str(price_at)[:10] >= floor:
        return None                                  # it traded lately: a list without it is no proof it left
    which = "the SEC's list of companies that file with it" if region == "US" else "the exchanges' lists of listed companies"
    last = f"; its last stored price is of {_dmy(str(price_at)[:10])}" if price_at else "; no price of it is stored"
    return {"day": day, "why": f"no longer listed: {which} of {_dmy(day)} doesn't name it{last}, so it is in no figure of the theme"}


def _dmy(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day} {d.strftime('%b %Y')}"


def reader(region: str, today: date, sec_tickers=None, kept=None, bse=None):
    """A dive's `listed()`: the market's current list (as `from_sec` or `from_kept` give it), or None when it can't be read (nobody is
    removed then). `sec_tickers()`, `kept()` and `bse()` read what the app keeps (the SEC feed's day-long copy, the company pages' day's
    list, the BSE-only list); a failure of any is no list. Worked out once a market a day."""
    def listed():
        key = (region, today.isoformat())
        with _lock:
            if key in _kept:
                return _kept[key]
        try:
            if region == "US":
                got = from_sec(sec_tickers(), today.isoformat()) if sec_tickers else None
            else:
                got = from_kept(kept() if kept else None, bse() if bse else None, today)
        except Exception as e:
            print("theme: the market's list of companies not read:", region, type(e).__name__, str(e)[:100])
            return None                          # not kept: asked again at the next dive
        with _lock:
            for k in [k for k in _kept if k[0] == region]:
                _kept.pop(k, None)
            if got is not None:
                _kept[key] = got
        return got
    return listed


def forget():
    """Drop the kept lists (between tests)."""
    with _lock:
        _kept.clear()
