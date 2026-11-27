"""Try one idea without signing in (conv101, P1; funnel 27 Nov: nothing could be tried without an account, and 85% of visitors left after
one page). A visitor picks one of a few well-known rule sets (the public library's own: library_seed.STRATEGIES) and one of a few
well-known instruments, and the server runs StratLab's real backtest and verdict on five years of daily prices after costs, exactly as
for an account, then answers with the verdict and the figures. To keep it, change it or paper trade it, the visitor signs up.

Nothing is stored: no account, no notebook, no result in the database, and nothing about the visitor. The per-address limit is kept in
memory under a salted hash of the address (the salt is random per process and never written down), and goes when the day ends or the
process restarts. A result is the same for everyone who picks the same rules and instrument on the same day, so it is kept in memory
(bounded) and served again without running: a few dozen combinations at most, so the cost is a few backtests a day whatever the traffic.
Facts only: the verdict as the engine gives it, losses as plainly as gains; never advice."""
import hashlib
import secrets
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

from . import library, library_seed, research
from .responses import err

DAYS = 1825                       # five years of daily candles, as the library's daily rule sets are tested
PER_ADDRESS_PER_DAY = 3           # fresh tries from one address a day (a result already kept for the day is served without counting)
RUNS_PER_DAY = 120                # fresh backtests a day for all visitors together, whatever the addresses
KEPT = 64                         # results kept in memory (the day's combinations; at most len(IDEAS) * len(INSTRUMENTS) are possible)

# id: (library_seed slug, the words on the button)
IDEAS: dict[str, tuple[str, str]] = {
    "ema": ("ema-20-50", "20/50 EMA cross"),
    "supertrend": ("supertrend", "Supertrend flip"),
    "golden": ("golden-cross", "Golden cross (50/200-day)"),
    "rsi2": ("rsi2-revert", "RSI(2) dip in an uptrend"),
}
# instrument id (as the markets registry reads it): (market, the symbol shown, the name shown)
INSTRUMENTS: dict[str, tuple[str, str, str]] = {
    "IN:RELIANCE": ("IN", "RELIANCE", "Reliance Industries"),
    "IN:HDFCBANK": ("IN", "HDFCBANK", "HDFC Bank"),
    "IN:TCS": ("IN", "TCS", "Tata Consultancy Services"),
    "IN:INFY": ("IN", "INFY", "Infosys"),
    "US:AAPL": ("US", "AAPL", "Apple"),
    "US:NVDA": ("US", "NVDA", "NVIDIA"),
    "CRYPTO:BTC-USD": ("CRYPTO", "BTC/USD", "Bitcoin"),
}

_SALT = secrets.token_bytes(16)
_lock = threading.Lock()
_run_lock = threading.Lock()      # one visitor's backtest at a time: accounts' runs are never queued behind a crowd of visitors
_day = ""
_tries: dict[str, int] = {}       # salted address hash -> fresh tries today
_runs = 0
_kept: dict[tuple[str, str, str], dict] = {}


def options() -> dict:
    """The rule sets and instruments a visitor can pick, with each rule set's own words (what it does)."""
    return {"ideas": [{"id": k, "name": name, "text": library_seed.STRATEGIES[slug]["text"]} for k, (slug, name) in IDEAS.items()],
            "instruments": [{"id": k, "market": m, "symbol": s, "name": n} for k, (m, s, n) in INSTRUMENTS.items()],
            "per_day": PER_ADDRESS_PER_DAY, "days": DAYS}


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _roll(day: str) -> None:
    """A new day: every count starts again and yesterday's results go (prices moved)."""
    global _day, _runs
    if day != _day:
        _day, _runs = day, 0
        _tries.clear()
        _kept.clear()


def _who(address: str) -> str:
    return hashlib.sha256(_SALT + (address or "?").encode()).hexdigest()[:24]


def shaped(rec: dict, idea: str, inst_id: str) -> dict:
    """The answer: the library card's shape (verdict and figures), the rules in words, the instrument and the period; no trade list."""
    slug, name = IDEAS[idea]
    market, symbol, label = INSTRUMENTS[inst_id]
    e = library.entry({"name": f"{name} · {symbol}"}, rec, owner="guest", author="", description=library_seed.STRATEGIES[slug]["text"], entry_id="guest")
    return {"idea": {"id": idea, "name": name, "text": library_seed.STRATEGIES[slug]["text"]},
            "instrument": {"id": inst_id, "market": market, "symbol": symbol, "name": label, "currency": (rec.get("instrument") or {}).get("currency")},
            "range": rec.get("range"), "verdict": e["verdict"], "stats": e["stats"], "tf": "1d"}


def run(registry, runner, idea: str, inst_id: str, address: str, now: datetime | None = None) -> dict:
    """One try: the kept result for today when there is one (not counted), else a fresh run within the address's and the day's limits.
    `runner`: compute.run. Raises the API's errors (400 unknown pick, 429 over a limit, 503 busy or data offline)."""
    if idea not in IDEAS or inst_id not in INSTRUMENTS:
        err(400, "unknown_pick", "Pick one of the ideas and one of the instruments shown.")
    day = _today(now)
    who = _who(address)
    key = (day, idea, inst_id)
    global _runs
    with _lock:
        _roll(day)
        hit = _kept.get(key)
        used = _tries.get(who, 0)
        if hit is not None:
            return {**hit, "kept": True, "left": max(0, PER_ADDRESS_PER_DAY - used)}
        if used >= PER_ADDRESS_PER_DAY:
            from .plans import PLANS
            free = PLANS["free"]["backtests_per_month"]
            err(429, "guest_limit", f"That's {PER_ADDRESS_PER_DAY} tries today without an account. Sign up free to keep testing: "
                                    f"{free} backtests a month on Free, with your own rules, saved.")
        if _runs >= RUNS_PER_DAY:
            err(503, "guest_busy", "Lots of people are trying ideas today. Sign up free to run yours now, or try again tomorrow.")
        _tries[who] = used + 1
        _runs += 1
    if not _run_lock.acquire(timeout=20):
        with _lock:
            _tries[who] = max(0, _tries.get(who, 1) - 1)
        err(503, "guest_busy", "Another visitor's test is running. Try again in a minute.")
    try:
        slug, name = IDEAS[idea]
        market = INSTRUMENTS[inst_id][0]
        strategy = library_seed.strategy_of(library_seed.STRATEGIES[slug], name, market)
        req = SimpleNamespace(instrument=inst_id, days=DAYS, bars=None, upload=None, label="")
        try:
            data = research.load(registry, strategy, req)
            out = runner(strategy, data)
        except research.ResearchError as e:
            with _lock:
                _tries[who] = max(0, _tries.get(who, 1) - 1)      # a market that's offline doesn't use up a try
            err(e.status, e.code, e.message)
        rec = research.record(out, strategy, "", 1, datetime.now(timezone.utc).isoformat())
        answer = shaped(rec, idea, inst_id)
    finally:
        _run_lock.release()
    with _lock:
        _roll(day)
        if len(_kept) >= KEPT:
            _kept.clear()
        _kept[key] = answer
        left = max(0, PER_ADDRESS_PER_DAY - _tries.get(who, 0))
    return {**answer, "kept": False, "left": left}


def forget() -> None:
    """Tests: every count and kept result gone."""
    global _day, _runs
    with _lock:
        _day, _runs = "", 0
        _tries.clear()
        _kept.clear()
