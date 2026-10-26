"""Groups of instruments to test one strategy on together, and turning them into data.

Preset lists are well-known indices' current members (a list with a known date carries it as "as_of"). Index members change from time to time; anything
the market no longer lists is skipped and reported, and you can always build your own group."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo
from functools import lru_cache
from pathlib import Path

from . import db
from .kite_service import NSE_SERIES
from .research import ResearchError, load

MAX_MEMBERS = 100
PRESETS = {
    "IN": [
        {"id": "nifty50", "name": "NIFTY 50 stocks", "symbols": [
            "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BSE",
            "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
            "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK",
            "LT", "M&M", "MARUTI", "MAXHEALTH", "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
            "SUNPHARMA", "TATACONSUM", "TMPV", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT", "ULTRACEMCO"]},
        {"id": "banknifty", "name": "NIFTY Bank stocks", "symbols": [
            "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA", "PNB", "CANBK",
            "FEDERALBNK", "IDFCFIRSTB", "AUBANK", "UNIONBANK", "YESBANK"]},
        {"id": "fno_liquid", "name": "25 most liquid F&O stocks", "symbols": [
            "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "AXISBANK", "KOTAKBANK", "LT", "BHARTIARTL",
            "ITC", "BAJFINANCE", "TMPV", "TATASTEEL", "MARUTI", "M&M", "SUNPHARMA", "HINDALCO", "ADANIENT",
            "JSWSTEEL", "TITAN", "HCLTECH", "WIPRO", "ONGC", "COALINDIA"]},
    ],
    "US": [
        {"id": "us_mega", "name": "20 of the largest US companies", "symbols": [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "JPM", "LLY", "V", "UNH", "XOM",
            "MA", "JNJ", "PG", "HD", "COST", "WMT"]},
    ],
    # (MO-5b) ready-made groups for the markets whose data the backtester reads but that had none: the library's StratLab
    # samples run on them (app/library_seed.py), and the group picker lists them like the others
    "UK": [
        {"id": "uk_large", "name": "12 large UK companies", "symbols": [
            "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "GSK.L", "RIO.L", "DGE.L", "BATS.L", "LSEG.L", "BARC.L", "VOD.L"]},
    ],
    "EU": [
        {"id": "eu_large", "name": "12 large European companies", "symbols": [
            "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "MC.PA", "OR.PA", "AIR.PA", "SAN.PA", "TTE.PA", "ASML.AS", "INGA.AS", "IBE.MC"]},
    ],
    "JP": [
        {"id": "jp_large", "name": "12 large Japanese companies", "symbols": [
            "7203.T", "6758.T", "9984.T", "6861.T", "8306.T", "9432.T", "8035.T", "7974.T", "9983.T", "4063.T", "8316.T", "6098.T"]},
    ],
    "FX": [
        {"id": "fx_majors", "name": "7 major currency pairs", "symbols": [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"]},
    ],
    "CRYPTO": [
        {"id": "top_coins", "name": "10 large coins", "symbols": [
            "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "LINK-USD", "LTC-USD", "AVAX-USD", "DOT-USD"]},
    ],
    "MCX": [
        {"id": "mcx_minis", "name": "7 MCX mini contracts (metals and energy)", "symbols": [
            "GOLDM", "SILVERM", "CRUDEOILM", "NATGASMINI", "ZINCMINI", "ALUMINI", "LEADMINI"]},
        {"id": "mcx_main", "name": "MCX main contracts", "symbols": [
            "GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD"]},
    ],
    "CDS": [
        {"id": "cds_all", "name": "4 rupee currency pairs", "symbols": ["USDINR", "EURINR", "GBPINR", "JPYINR"]},
    ],
    "CMDTY": [
        {"id": "global_commodities", "name": "14 global commodity futures", "symbols": [
            "GC=F", "SI=F", "PL=F", "HG=F", "CL=F", "BZ=F", "NG=F", "ZC=F", "ZW=F", "ZS=F", "KC=F", "SB=F", "CC=F", "CT=F"]},
        {"id": "global_metals_energy", "name": "Global metals and energy", "symbols": ["GC=F", "SI=F", "PL=F", "HG=F", "CL=F", "BZ=F", "NG=F"]},
    ],
}


# ---------- the big groups, worked out once a day (scan_presets) rather than read stock by stock ----------
SP500_FILE = Path(__file__).parent / "data" / "sp500.json"       # a committed list: its source and date are inside; never read from the web
BIG = {"IN": [{"id": "nifty500", "name": "NIFTY 500"}], "US": [{"id": "sp500", "name": "S&P 500"}]}


@lru_cache(maxsize=1)
def sp500_doc() -> dict:
    """The committed S&P 500 list: {"name", "source", "as_of", "rows": [[symbol, name, sector, cik]]}."""
    return json.loads(SP500_FILE.read_text(encoding="utf-8"))


def sp500_symbols() -> list[str]:
    return [r[0] for r in sp500_doc()["rows"]]


def sp500_names() -> dict[str, str]:
    return {r[0]: r[1] for r in sp500_doc()["rows"]}


def sp500_ciks() -> dict[str, int]:
    return {r[0]: int(r[3]) for r in sp500_doc()["rows"] if r[3]}


def us_universe() -> list[str]:
    """Every US stock the app keeps daily jobs for: the S&P 500 and the ready-made groups, once each."""
    out = list(sp500_symbols())
    for p in PRESETS["US"]:
        out += [s for s in p["symbols"] if s not in out]
    return list(dict.fromkeys(out))


def members_note(group: dict) -> str | None:
    """A run note for a ready-made group of stocks: its members are today's list, so a test over earlier years trades
    companies that joined it later and leaves out those that left it. None for any other group."""
    market = (group.get("market") or "IN").upper()
    if market not in ("IN", "US"):
        return None
    p = next((current(p) for p in PRESETS[market] if p["id"] == group.get("id")), None)
    if p is None:
        return None
    # the list's own date when it carries one, never a fixed year that goes stale (R38-004: "as of 2025" in Oct 2026)
    when = f" (the list as of {p['as_of']})" if p.get("as_of") else ""
    # the members on the day of the run, which a run read later still says truly (R52-001: "today's members" months on)
    return (f"{p['name']} are the list's members on the day this test ran{when}: earlier years include companies that joined the list later "
            "and leave out those that left it.")


# a ready-made group that follows an index: its members are the exchange's own current list (its constituent file, read once a day
# by the breadth run and kept, with the day it was read), and until one has been read, the list written above with the index
# provider's announced changes applied once they take effect (R50-004: BSE in and WIPRO out of the NIFTY 50 from 30 Sep). RC2A-020: the
# written list was months behind (WIPRO, HEROMOTOCO and INDUSINDBK where the exchange had BSE, INDIGO and MAXHEALTH, so MAXHEALTH, 2.3%
# above its 52-week low, was missing from "Near 52-week low"), and the announced changes did not cover all of it.
FOLLOWS = {"nifty50": "Nifty 50", "banknifty": "Nifty Bank"}
EXCHANGE_NAME = {"nifty50": "NIFTY 50", "banknifty": "NIFTY BANK"}       # how the exchange's constituent files name the index (intel/filings.py INDEX_FILES)
FOLLOWED_KEY = "universe:members:"           # universe:members:<id> = {"symbols": [...], "as_of": "YYYY-MM-DD"}: the exchange's list as last read
MIN_FOLLOWED = {"nifty50": 45, "banknifty": 10}      # a shorter list is taken as a broken answer, not an index's members


def keep_followed(pid: str, symbols: list[str], today: date | None = None) -> bool:
    """Store the exchange's current list of a followed index (`symbols`, as its file gives them) with the day it was read (India's). False
    when the list is too short to be the index's."""
    syms = [s for s in dict.fromkeys(str(x).strip().upper() for x in symbols or []) if s]
    if len(syms) < MIN_FOLLOWED.get(pid, 20):
        return False
    day = (today or datetime.now(ZoneInfo("Asia/Kolkata")).date()).isoformat()
    db.set_setting(FOLLOWED_KEY + pid, json.dumps({"symbols": syms, "as_of": day}, separators=(",", ":")))
    return True


def refresh_followed(index_members, today: date | None = None) -> list[str]:
    """Read each followed index's current members through `index_members(name)` (the breadth run's, cached for the day) and keep them.
    Returns the ids refreshed; an index the exchange does not answer for keeps its last list."""
    done = []
    for pid, name in EXCHANGE_NAME.items():
        try:
            if keep_followed(pid, index_members(name), today):
                done.append(pid)
        except Exception as e:
            print("universes: members of", name, str(e)[:100])
    return done


def followed(pid: str) -> dict | None:
    """The stored list of a followed index: {"symbols", "as_of"}, or None before one has been read."""
    try:
        got = db.json_value(db.get_setting(FOLLOWED_KEY + pid), {})
    except Exception:
        return None
    syms = [s for s in got.get("symbols") or [] if isinstance(s, str)] if isinstance(got, dict) else []
    return {"symbols": syms, "as_of": got.get("as_of")} if len(syms) >= MIN_FOLLOWED.get(pid, 20) else None


def current(p: dict, today=None) -> dict:
    """A preset's members today. A group that follows an index: the exchange's own list as last read (dated), else the written list with the
    announced index changes that have taken effect applied, and as_of the latest one's date."""
    index = FOLLOWS.get(p.get("id"))
    if not index:
        return p
    got = followed(p["id"])
    if got:
        when = date.fromisoformat(got["as_of"]) if got.get("as_of") else None
        return {**p, "symbols": got["symbols"], **({"as_of": f"{when.day} {when:%b %Y}"} if when else {})}
    try:
        from . import market_events
        day = (today or market_events.ist_now().date()).isoformat()
        changes = sorted((c for c in market_events.index_changes() if c.get("effective") and str(c["effective"])[:10] <= day),
                         key=lambda c: str(c["effective"])[:10])
    except Exception as e:                      # no stored changes (tests, a fresh database): the list as written
        print("index changes unavailable for", p.get("id"), str(e)[:80])
        return p
    syms, when = list(p["symbols"]), None
    for c in changes:
        for sec in c.get("sections") or []:
            if sec.get("index") != index:
                continue
            out = {x[0] for x in sec.get("out") or []}
            syms = [x for x in syms if x not in out] + [x[0] for x in sec.get("in") or [] if x[0] not in syms]
            when = str(c["effective"])[:10]
    if when is None:
        return p
    d = date.fromisoformat(when)
    return {**p, "symbols": syms, "as_of": f"{d.day} {d:%b %Y}"}


def symbols(market: str, pid: str) -> list[str]:
    """A ready-made group's members today."""
    p = next(p for p in PRESETS[market] if p["id"] == pid)
    return list(current(p)["symbols"])


def presets(market: str) -> list[dict]:
    return [{**q, "market": market, "count": len(q["symbols"])} for q in (current(p) for p in PRESETS.get(market, []))]


def resolve(registry, market: str, members: list[dict]) -> tuple[list[str], list[str]]:
    """Instrument ids for a group's members (each {"id"} or {"symbol"}), and the symbols that weren't found."""
    prov = registry.provider(market)
    ids, missing = [], []
    for m in members[:MAX_MEMBERS]:
        if m.get("id"):
            ids.append(m["id"])
            continue
        sym = str(m.get("symbol") or "").upper()
        if market == "IN":
            # the exact symbol first: a short one ("BI", "AKI") has dozens of longer ones starting with it, and a search's
            # first eight could leave out the stock itself when it trades as SYMBOL-BE or -BZ
            exact = prov.equity(sym) if hasattr(prov, "equity") else None
            hit = exact if exact and exact.get("type") == "EQ" and exact.get("exchange") in ("NSE", "BSE") else None
            hit = hit or next((r for r in prov.search(sym, allow_fno=False, limit=8)       # NSE, or listed only on BSE
                        if (r["symbol"] in (sym, *(f"{sym}-{x}" for x in NSE_SERIES)) or r.get("bse_code") == sym)
                        and r.get("type") == "EQ" and r.get("exchange") in ("NSE", "BSE")), None)
            iid = hit["id"] if hit else None
        else:
            iid = f"{market}:{sym}"
            try:
                if registry.resolve(iid)[1] is None:
                    iid = None
            except Exception:
                iid = None
        (ids.append(iid) if iid else missing.append(sym))
    return list(dict.fromkeys(ids)), missing


class _Req:
    def __init__(self, instrument: str, days: int):
        self.instrument, self.days, self.bars, self.upload = instrument, days, None, None


_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="universe")


def load_all(registry, strategy, ids: list[str], days: int) -> tuple[list[dict], list[str]]:
    """Candles for every member (four at a time). Members whose data can't load are skipped and named."""
    def one(iid):
        try:
            return load(registry, strategy, _Req(iid, days)), None
        except ResearchError as e:
            return None, f"{iid.split(':', 1)[-1]}: {e.message}"
        except Exception as e:  # one member's data problem mustn't sink the rest
            return None, f"{iid.split(':', 1)[-1]}: couldn't load ({e.__class__.__name__})"
    got, problems = [], []
    for data, problem in _pool.map(one, ids):
        (got.append(data) if data else problems.append(problem))
    return got, problems
