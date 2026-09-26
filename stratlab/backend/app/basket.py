"""The "does it travel?" check: run one experiment's rules on similar instruments in the
same market. An edge that only works on one stock is more likely luck than an edge."""
import statistics
from concurrent.futures import ThreadPoolExecutor

from .engine.core import backtest
from .research import ResearchError, load

BASKETS = {
    "IN": ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC", "LT", "SBIN", "BHARTIARTL", "AXISBANK", "KOTAKBANK", "HINDUNILVR"],
    "US": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM", "JNJ", "WMT", "SPY", "QQQ"],
    "CRYPTO": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "LINK-USD", "LTC-USD", "AVAX-USD", "DOT-USD", "BCH-USD"],
    "UK": ["SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "GSK.L", "RIO.L", "BARC.L", "LLOY.L", "VOD.L", "ISF.L"],
    "EU": ["SAP.DE", "ASML.AS", "MC.PA", "SIE.DE", "TTE.PA", "ALV.DE", "SAN.PA", "OR.PA", "AIR.PA", "BNP.PA", "EXS1.DE"],
    "JP": ["7203.T", "6758.T", "9984.T", "8306.T", "6861.T", "9432.T", "7974.T", "8035.T", "6501.T", "4063.T", "1306.T"],
    "MCX": ["GOLDM", "SILVERM", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD", "GOLD", "SILVER", "CRUDEOILM"],
    "CMDTY": ["GC=F", "SI=F", "PL=F", "HG=F", "CL=F", "BZ=F", "NG=F", "ZC=F", "ZW=F", "ZS=F", "KC=F"],
    "FX": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X", "EURGBP=X", "EURJPY=X", "USDINR=X"],
}
SIZE = 10
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="basket")


class _Req:
    def __init__(self, instrument: str, days: int):
        self.instrument, self.days, self.bars, self.upload = instrument, days, None, None


def _ids(registry, market: str, exclude: str | None) -> list[str]:
    ids = []
    prov = registry.provider(market)
    for sym in BASKETS.get(market, []):
        if len(ids) >= SIZE:
            break
        if market == "IN":
            # Kite ids are tokens: look the cash stock up by symbol
            hit = next((r for r in prov.search(sym, allow_fno=False, limit=5) if r["symbol"] == sym and r.get("type") == "EQ" and r.get("exchange") == "NSE"), None)
            iid = hit["id"] if hit else None
        else:
            iid = f"{market}:{sym}"
        if not iid or iid == exclude:
            continue
        try:  # skip anything the market no longer lists, and use the spares instead
            if registry.resolve(iid)[1] is None:
                continue
        except Exception:
            continue
        ids.append(iid)
    return ids


def _one(registry, strategy, iid: str, days: int) -> dict:
    try:
        data = load(registry, strategy, _Req(iid, days))
        out = backtest(data["bars"], strategy, data["start"], data["lot"], data["kind"])
    except ResearchError as e:
        return {"id": iid, "symbol": iid.split(":", 1)[-1], "error": e.message}
    except Exception as e:  # one instrument's data problem mustn't sink the rest
        return {"id": iid, "symbol": iid.split(":", 1)[-1], "error": f"Couldn't test it ({e.__class__.__name__})."}
    st = out["stats"]
    return {"id": iid, "symbol": data["inst"]["symbol"], "name": data["inst"].get("name"),
            "ret": st["ret"], "buy_hold": st["buy_hold_ret"], "n": st["n"], "win": st["win"], "mdd": st["mdd"]}


def run(registry, strategy, market: str, exclude: str | None, days: int) -> dict:
    if market not in BASKETS:
        raise ResearchError(400, "no_basket", "This check needs a market with a list of similar instruments; uploaded data doesn't have one.")
    prov = registry.provider(market)
    if prov is None or not prov.ready():
        raise ResearchError(503, "data_offline", "Market data for this market is offline right now. Try again soon.")
    ids = _ids(registry, market, exclude)
    rows = list(_pool.map(lambda i: _one(registry, strategy, i, days), ids))
    tested = [r for r in rows if "error" not in r and r["n"] > 0]
    profitable = [r for r in tested if r["ret"] > 0]
    beat = [r for r in tested if r["ret"] > r["buy_hold"]]
    share = len(profitable) / len(tested) if tested else 0
    if len(tested) < 4:
        status, headline = "warn", "Too few instruments could be tested to judge."
    elif share >= 0.6:
        status, headline = "pass", f"It travels: profitable on {len(profitable)} of {len(tested)} similar instruments."
    elif share >= 0.4:
        status, headline = "warn", f"Mixed: profitable on {len(profitable)} of {len(tested)} similar instruments."
    else:
        status, headline = "fail", f"It doesn't travel: profitable on only {len(profitable)} of {len(tested)} similar instruments."
    return {"status": status, "headline": headline, "market": market, "days": days,
            "tested": len(tested), "profitable": len(profitable), "beat_buy_hold": len(beat),
            "median_ret": statistics.median([r["ret"] for r in tested]) if tested else None,
            "rows": sorted(rows, key=lambda r: -(r.get("ret") if r.get("ret") is not None else -1e9))}
