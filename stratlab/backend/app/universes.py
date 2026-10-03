"""Groups of instruments to test one strategy on together, and turning them into data.

Preset lists are well-known indices as of 2025. Index members change from time to time; anything
the market no longer lists is skipped and reported, and you can always build your own group."""
from concurrent.futures import ThreadPoolExecutor

from .kite_service import NSE_SERIES
from .research import ResearchError, load

MAX_MEMBERS = 50
PRESETS = {
    "IN": [
        {"id": "nifty50", "name": "NIFTY 50 stocks", "symbols": [
            "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL",
            "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
            "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK",
            "LT", "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
            "SUNPHARMA", "TATACONSUM", "TMPV", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO"]},
        {"id": "banknifty", "name": "NIFTY Bank stocks", "symbols": [
            "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA", "PNB", "CANBK",
            "FEDERALBNK", "IDFCFIRSTB", "AUBANK"]},
        {"id": "fno_liquid", "name": "25 most liquid F&O stocks", "symbols": [
            "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "AXISBANK", "KOTAKBANK", "LT", "BHARTIARTL",
            "ITC", "BAJFINANCE", "TMPV", "TATASTEEL", "MARUTI", "M&M", "SUNPHARMA", "HINDALCO", "ADANIENT",
            "JSWSTEEL", "TITAN", "HCLTECH", "WIPRO", "ONGC", "COALINDIA"]},
    ],
    "US": [
        {"id": "us_mega", "name": "20 US large caps", "symbols": [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "JPM", "LLY", "V", "UNH", "XOM",
            "MA", "JNJ", "PG", "HD", "COST", "WMT"]},
    ],
    "CRYPTO": [
        {"id": "top_coins", "name": "10 large coins", "symbols": [
            "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "LINK-USD", "LTC-USD", "AVAX-USD", "DOT-USD"]},
    ],
    "MCX": [
        {"id": "mcx_minis", "name": "MCX mini contracts (metals and energy)", "symbols": [
            "GOLDM", "SILVERM", "CRUDEOILM", "NATGASMINI", "ZINCMINI", "ALUMINI", "LEADMINI"]},
        {"id": "mcx_main", "name": "MCX main contracts", "symbols": [
            "GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD"]},
    ],
    "CDS": [
        {"id": "cds_all", "name": "The four rupee pairs", "symbols": ["USDINR", "EURINR", "GBPINR", "JPYINR"]},
    ],
    "CMDTY": [
        {"id": "global_commodities", "name": "14 global commodity futures", "symbols": [
            "GC=F", "SI=F", "PL=F", "HG=F", "CL=F", "BZ=F", "NG=F", "ZC=F", "ZW=F", "ZS=F", "KC=F", "SB=F", "CC=F", "CT=F"]},
        {"id": "global_metals_energy", "name": "Global metals and energy", "symbols": ["GC=F", "SI=F", "PL=F", "HG=F", "CL=F", "BZ=F", "NG=F"]},
    ],
}


def presets(market: str) -> list[dict]:
    return [{**p, "market": market, "count": len(p["symbols"])} for p in PRESETS.get(market, [])]


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
            hit = next((r for r in prov.search(sym, allow_fno=False, limit=8)       # NSE, or listed only on BSE
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
