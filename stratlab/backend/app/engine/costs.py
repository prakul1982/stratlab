"""What each order really costs, per market, plus a rough tax estimate.

Rates are the published ones as of 2025 and change from time to time; they live here
only, so updating them is a one-file change. Brokerage is the user's own setting
(a flat amount per order, in the market's currency); everything else is statutory
or a typical exchange fee."""
import math
from datetime import datetime

# India, per side, as a fraction of the traded value
IN_EQUITY = {"stt": 0.001, "exchange": 0.0000297, "sebi": 0.000001, "stamp_buy": 0.00015}
IN_EQUITY_MIS = {"stt_sell": 0.00025, "exchange": 0.0000297, "sebi": 0.000001, "stamp_buy": 0.00003}   # intraday
IN_FUTURES = {"stt_sell": 0.0002, "exchange": 0.0000173, "sebi": 0.000001, "stamp_buy": 0.00002}
IN_OPTIONS = {"stt_sell": 0.001, "exchange": 0.0003503, "sebi": 0.000001, "stamp_buy": 0.00003}
IN_MCX_OPTIONS = {"stt_sell": 0.0005, "exchange": 0.000418, "sebi": 0.000001, "stamp_buy": 0.00003}   # CTT, not STT
IN_MCX_FUTURES = {"stt_sell": 0.0001, "exchange": 0.000021, "sebi": 0.000001, "stamp_buy": 0.00002}   # CTT on non-agri sells
GST = 0.18
IN_STCG, IN_LTCG, IN_LTCG_EXEMPT = 0.20, 0.125, 125000

US_SEC_FEE = 0.0000278           # on sells
US_FINRA_TAF, US_FINRA_CAP = 0.000166, 8.30   # per share sold, capped per trade
CRYPTO_FEE = 0.001               # typical taker fee, each side
UK_STAMP = 0.005                 # stamp duty (SDRT) on share purchases
FX_SPREAD = 0.0001               # about one pip on a major pair, each side
CMDTY_SPREAD = 0.0002            # global futures: about a tick of spread plus commission, each side

LABELS = {
    "brokerage": "Brokerage", "stt": "STT / CTT", "exchange": "Exchange + SEBI fees", "stamp": "Stamp duty",
    "gst": "GST", "sec": "SEC fee", "finra": "FINRA fee", "fee": "Exchange fee", "spread": "Spread",
}


def kind_of(inst: dict | None) -> str:
    """Which cost model applies to an instrument."""
    inst = inst or {}
    market = inst.get("market", "IN")
    if market == "MCX":
        return "in_mcx_fut"
    if market == "IN":
        t = inst.get("type")
        return "in_fut" if t == "FUT" else "in_opt" if t in ("CE", "PE") else "in_eq"
    if market == "UK":
        return "uk_etf" if inst.get("type") == "ETF" else "uk"
    return {"US": "us", "CRYPTO": "crypto", "FX": "fx", "CMDTY": "cmdty"}.get(market, "flat")


def order_costs(kind: str, side: str, qty: float, price: float, brokerage: float) -> dict[str, float]:
    """Itemised costs of one order, in the market's currency."""
    value = qty * price
    c = {"brokerage": brokerage}
    if kind.startswith("in_"):
        r = {"in_eq": IN_EQUITY, "in_eq_mis": IN_EQUITY_MIS, "in_fut": IN_FUTURES, "in_opt": IN_OPTIONS,
             "in_mcx_opt": IN_MCX_OPTIONS, "in_mcx_fut": IN_MCX_FUTURES}[kind]
        stt = r.get("stt", 0) + (r.get("stt_sell", 0) if side == "sell" else 0)
        c["stt"] = value * stt
        exch = value * (r["exchange"] + r["sebi"])
        c["exchange"] = exch
        c["stamp"] = value * r["stamp_buy"] if side == "buy" else 0.0
        c["gst"] = GST * (brokerage + exch)
    elif kind == "us" and side == "sell":
        c["sec"] = value * US_SEC_FEE
        c["finra"] = min(qty * US_FINRA_TAF, US_FINRA_CAP)
    elif kind == "crypto":
        c["fee"] = value * CRYPTO_FEE
    elif kind == "uk" and side == "buy":
        c["stamp"] = value * UK_STAMP
    elif kind == "fx":
        c["spread"] = value * FX_SPREAD
    elif kind == "cmdty":
        c["spread"] = value * CMDTY_SPREAD
    return c


def total(costs: dict[str, float]) -> float:
    return float(sum(costs.values()))


def breakdown(items: dict[str, float]) -> list[dict]:
    """Totals per cost line, largest first, for display."""
    merged: dict[str, float] = {}
    for k, v in items.items():
        label = LABELS.get(k, k)
        merged[label] = merged.get(label, 0.0) + v
    return [{"label": k, "amount": round(v, 2)} for k, v in sorted(merged.items(), key=lambda x: -x[1]) if v > 0.005]


def _days(a: str, b: str) -> float:
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 86400
    except (TypeError, ValueError):
        return 0.0


def tax_estimate(kind: str, trades: list[dict]) -> dict:
    """A rough capital-gains estimate on the net profit. Only India equity is estimated."""
    if kind != "in_eq":
        note = ("F&O profit is taxed as business income at your slab rate, so it isn't estimated here."
                if kind in ("in_fut", "in_opt", "in_mcx_fut", "in_mcx_opt") else "Tax depends on where you live, so it isn't estimated for this market.")
        return {"amount": None, "note": note}
    short = sum(t["pnl"] for t in trades if _days(t.get("entry_t"), t.get("exit_t")) < 365)
    long_ = sum(t["pnl"] for t in trades if _days(t.get("entry_t"), t.get("exit_t")) >= 365)
    amount = max(0.0, short) * IN_STCG + max(0.0, long_ - IN_LTCG_EXEMPT) * IN_LTCG
    return {"amount": round(amount, 2),
            "note": "Estimate: 20% on short-term gains, 12.5% on long-term gains above ₹1.25 lakh. Losses and your other income can change it."}


def floor_to(q: float, step: float) -> float:
    """Round a quantity down to the instrument's step (1 share, a lot of 75, 0.0001 BTC)."""
    if not math.isfinite(q) or q <= 0:
        return 0.0
    n = math.floor(q / step + 1e-9)
    v = round(n * step, 10)
    return int(v) if v == int(v) else v  # whole shares and lots stay integers
