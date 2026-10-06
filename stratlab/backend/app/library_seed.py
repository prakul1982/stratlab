"""StratLab's own strategies in the public library: well-known rule sets, each built from the rules engine, run through
the app's own backtest and verdict on the standard groups of stocks, and published as "StratLab" with a badge.

Every verdict is published as the engine gave it, "No edge here" and "Probably luck" as plainly as "Likely a real
edge": the library says what each rule set did on that group over that period, nothing more. Nothing here is advice or a
recommendation, and a verdict about the past says nothing about what a strategy will do next.

The entries have fixed ids (seed-<strategy>-<group>), so running the seed again updates them in place and never
duplicates one: their copies count, moderation and first publication date stay. Run it from the admin page
(POST /admin/library/seed), from a shell (`python -m app.library_seed`) or let the server do it once, a while after
starting, when the library has no StratLab entries yet. Each group's candles are read once per strategy, paced by the
data source's own limits."""
import time
from datetime import datetime, timezone

from . import library, research, universes
from .models import Strategy

OWNER = "stratlab"
AUTHOR = "StratLab"
BADGE = "StratLab"
SEED_VERSION = 1
DAYS = {"1d": 1825, "15m": 180}          # the period each timeframe is tested over (shortened to what the source has)
STOP_SENTENCES = ("Worth paper trading before real money.",)

RISK = {"capital": 500000, "riskPct": 1, "maxAlloc": 10, "sl": 8, "tgt": 0, "brokerage": 20, "slippage": 0.05}


def _c(l, op, r):
    return {"l": l, "op": op, "r": r}


def _num(v):
    return {"t": "num", "v": v}


PRICE = {"t": "price"}

# slug: (name, one-line description of the rules, strategy body, groups to run on: [(market, preset id)])
STRATEGIES: dict[str, dict] = {
    "st-s2": {
        "name": "ST S2: Stage 2 + Supertrend",
        "text": "Enters when a stock is in Stage 2 (price above a rising 150-day average) and its price is above the Supertrend (10, 3); "
                "leaves when the price crosses back below the Supertrend.",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c({"t": "stage", "p": 150, "m": 20}, "eq", _num(2)), _c(PRICE, "gt", {"t": "supertrend", "p": 10, "m": 3})],
                 "exit": [_c(PRICE, "xb", {"t": "supertrend", "p": 10, "m": 3})], "risk": {"sl": 12}}},
    "ema-20-50": {
        "name": "20/50 EMA cross",
        "text": "Enters when the 20-day exponential average crosses above the 50-day one; leaves when it crosses back below.",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c({"t": "ema", "p": 20}, "xa", {"t": "ema", "p": 50})],
                 "exit": [_c({"t": "ema", "p": 20}, "xb", {"t": "ema", "p": 50})]}},
    "rsi2-revert": {
        "name": "RSI(2) mean reversion",
        "text": "Enters after a sharp short-term drop (2-day RSI under 10) while the price is above its 200-day average; leaves when "
                "the 2-day RSI is back above 70.",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c({"t": "rsi", "p": 2}, "lt", _num(10)), _c(PRICE, "gt", {"t": "sma", "p": 200})],
                 "exit": [_c({"t": "rsi", "p": 2}, "gt", _num(70))], "risk": {"sl": 6}}},
    "breakout-52w": {
        "name": "52-week breakout with ATR stop",
        "text": "Enters when the price closes above the highest high of the previous 252 trading days (about 52 weeks); the stop is 3 "
                "times the 14-day ATR below the entry; leaves when the price closes below its 50-day average.",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c(PRICE, "xa", {"t": "dc_upper", "p": 252})],
                 "exit": [_c(PRICE, "xb", {"t": "sma", "p": 50})], "risk": {"stopType": "atr", "sl": 3}}},
    "boll-squeeze": {
        "name": "Bollinger squeeze breakout",
        "text": "A quiet spell followed by a breakout: enters when the price closes above the upper Bollinger band (20, 2) after the "
                "previous day's ATR was under 2% of the price; leaves when the price closes below the middle band. The quiet spell "
                "is measured by ATR, a stand-in for a narrow band.",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c(PRICE, "xa", {"t": "bb_upper", "p": 20, "m": 2}), _c({"t": "atr_pct", "p": 14, "ago": 1}, "lt", _num(2))],
                 "exit": [_c(PRICE, "xb", {"t": "bb_mid", "p": 20, "m": 2})], "risk": {"sl": 6}}},
    "orb-15m": {
        "name": "Opening-range breakout (intraday)",
        "text": "On 15-minute candles, from 09:45 to 11:30, enters when a candle closes above the day's high so far (after the first "
                "half hour); one trade a day, a 0.6% stop, a 1.2% target, and everything is closed at 15:15.",
        "tf": "15m", "groups": [("IN", "fno_liquid")],
        "body": {"entry": [_c(PRICE, "xa", {"t": "day_high", "ago": 1})],
                 "exit": [], "session": {"start": "09:45", "end": "11:30", "squareoff": "15:15", "maxTradesDay": 1},
                 "risk": {"sl": 0.6, "tgt": 1.2, "maxAlloc": 20}, "product": "intraday"}},
    "golden-cross": {
        "name": "Golden cross",
        "text": "Enters when the 50-day average crosses above the 200-day average; leaves when it crosses back below (the death cross).",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c({"t": "sma", "p": 50}, "xa", {"t": "sma", "p": 200})],
                 "exit": [_c({"t": "sma", "p": 50}, "xb", {"t": "sma", "p": 200})], "risk": {"sl": 15}}},
    "donchian-20-10": {
        "name": "Donchian 20/10 (turtle-style)",
        "text": "Enters when the price closes above the highest high of the previous 20 days; leaves when it closes below the lowest low "
                "of the previous 10 days; the stop is 2 times the 14-day ATR below the entry.",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c(PRICE, "xa", {"t": "dc_upper", "p": 20})],
                 "exit": [_c(PRICE, "xb", {"t": "dc_lower", "p": 10})], "risk": {"stopType": "atr", "sl": 2}}},
    "macd-cross": {
        "name": "MACD signal cross",
        "text": "Enters when the MACD line (12, 26) crosses above its 9-day signal line while the price is above its 200-day average; "
                "leaves when the MACD line crosses back below the signal line.",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c({"t": "macd", "p": 12, "m": 26}, "xa", {"t": "macd_signal", "p": 12, "m": 26}),
                           _c(PRICE, "gt", {"t": "sma", "p": 200})],
                 "exit": [_c({"t": "macd", "p": 12, "m": 26}, "xb", {"t": "macd_signal", "p": 12, "m": 26})]}},
    "supertrend": {
        "name": "Supertrend flip",
        "text": "Enters when the price crosses above the Supertrend (10, 3); leaves when it crosses back below.",
        "tf": "1d", "groups": [("IN", "nifty50"), ("US", "us_mega")],
        "body": {"entry": [_c(PRICE, "xa", {"t": "supertrend", "p": 10, "m": 3})],
                 "exit": [_c(PRICE, "xb", {"t": "supertrend", "p": 10, "m": 3})], "risk": {"sl": 12}}},
}
NOTE = ("Run by StratLab on its own rules, with its own tests, on every stock in the group over the period shown. The verdict is "
        "what the tests found about the past; it says nothing about the future.")


class SeedError(Exception):
    pass


SHORT = {"nifty50": "in", "us_mega": "us", "fno_liquid": "fo"}


def entry_id(slug: str, preset: str) -> str:
    """seed-golden-cross-in: fixed, so a second run updates the entry instead of adding one (the library's ids are 24 long at most)."""
    return f"seed-{slug}-{SHORT.get(preset, preset[:6])}"


def strategy_of(spec: dict, name: str) -> Strategy:
    body = {k: v for k, v in spec["body"].items() if k != "risk"}
    risk = {**RISK, **spec["body"].get("risk", {})}
    return Strategy(name=name, tf=spec["tf"], text=spec["text"], risk=risk, **body)


def preset_of(market: str, pid: str) -> dict:
    return next(p for p in universes.PRESETS[market] if p["id"] == pid)


def plain(summary: str) -> str:
    """The verdict's summary without its one forward-looking sentence: the library states what was found, not what to do."""
    for s in STOP_SENTENCES:
        summary = summary.replace(" " + s, "").replace(s, "")
    return summary.strip()


def run_group(registry, strategy: Strategy, market: str, preset: dict, now: str, max_open: int = 10) -> tuple[dict, dict]:
    """The strategy on every stock of the preset as one pot of capital, with the app's own verdict: (experiment, group)."""
    prov = registry.provider(market)
    if prov is None or not prov.ready():
        raise SeedError(f"Market data for {market} is offline.")
    group = {"id": preset["id"], "name": preset["name"], "market": market, "maxOpen": max_open,
             "members": [{"symbol": s} for s in preset["symbols"]]}
    ids, missing = universes.resolve(registry, market, group["members"])
    days = DAYS[strategy.tf]
    datasets, problems = universes.load_all(registry, strategy, ids, days)
    if len(datasets) < 2:
        raise SeedError(f"Fewer than two stocks of {preset['name']} had data.")
    max_days = min(d["max_days"] for d in datasets)
    result = research.run_group(datasets, strategy, group, min(days, max_days), max_days)
    problems = [f"{m}: not listed any more" for m in missing] + problems
    rec = research.record_group(result, strategy, f"StratLab, {preset['name']}", 1, now, group, datasets, problems)
    return rec, group


def publish(slug: str, spec: dict, market: str, preset: dict, rec: dict, group: dict) -> dict:
    """The library entry for one run: StratLab's, badged, with the engine's verdict as it came out."""
    eid = entry_id(slug, preset["id"])
    old = library.load(eid)
    nb = {"id": None, "name": f"{spec['name']} · {preset['name']}",
          "question": f"How did {spec['name']} do on {preset['name']}?", "group": group}
    e = library.entry(nb, rec, OWNER, AUTHOR, f"{spec['text']} {NOTE}", entry_id=eid)
    e["verdict"]["summary"] = plain(e["verdict"].get("summary") or "")
    e.update(official=True, badge=BADGE, seed={"slug": slug, "version": SEED_VERSION, "universe": preset["id"], "market": market,
                                              "days": rec.get("days"), "from": (rec.get("range") or {}).get("from"),
                                              "to": (rec.get("range") or {}).get("to")})
    if old:
        e["copies"], e["published_at"] = old.get("copies", 0), old.get("published_at", e["published_at"])
        e = library.carry_moderation(old, e)
    library.save(e)
    return e


def seed(registry, only: list[str] | None = None, now: str | None = None, sleep=time.sleep, gap: float = 1.0,
         max_open: int = 10) -> dict:
    """Run every StratLab strategy (or those in `only`) on its groups and publish the results. A strategy whose data
    isn't available is reported and skipped; the others still publish. Returns {"published": [...], "failed": [...]}."""
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    out, failed = [], []
    for slug, spec in STRATEGIES.items():
        if only and slug not in only:
            continue
        strat = strategy_of(spec, spec["name"])
        for market, pid in spec["groups"]:
            if out or failed:
                sleep(gap)
            try:
                preset = preset_of(market, pid)
                rec, group = run_group(registry, strat, market, preset, now, max_open if spec["tf"] == "1d" else 5)
                e = publish(slug, spec, market, preset, rec, group)
                out.append({"id": e["id"], "name": e["name"], "verdict": e["verdict"]["verdict"], "trades": (e["stats"] or {}).get("trades")})
            except Exception as ex:                                  # one group's trouble never stops the rest
                failed.append({"id": entry_id(slug, pid), "error": str(ex)[:160] or ex.__class__.__name__})
    return {"published": out, "failed": failed}


def seeded() -> list[dict]:
    return [e for e in library.all_entries() if e.get("official")]


if __name__ == "__main__":          # python -m app.library_seed
    from . import main
    print(seed(main.markets))
