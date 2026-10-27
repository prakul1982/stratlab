"""What each order really costs, per market, plus a rough tax estimate.

Rates are the published ones as of the dates in rules.py (F&O STT as raised by Budget 2026 from 1 April 2026, the
exchange charges as revised from 1 March 2026, the SEC fee from 4 April 2026) and change from time to time; they live
here only, so updating them is a one-file change, and rules.py lists each with its source and the day it was checked.
Brokerage is the user's own setting (a flat amount per order, in the market's currency); everything else is statutory
or a typical exchange fee."""
import math
from datetime import datetime

# India, per side, as a fraction of the traded value. "exchange" is the exchange's transaction charge with its investor
# protection fund (IPFT) contribution: NSE from 1 Mar 2026, ₹306.99 + ₹0.01 a crore in cash, ₹182.99 + ₹0.01 in
# equity futures, ₹3,512.99 + ₹0.01 a crore of premium in equity options (the same total as the ₹297/173/3,503
# charge plus ₹10 IPFT before). SEBI's fee is ₹10 a crore. Stamp duty on buys (Indian Stamp Act, from 1 Jul 2020).
IN_EQUITY = {"stt": 0.001, "exchange": 0.0000307, "sebi": 0.000001, "stamp_buy": 0.00015}
# DG-031: ETF units bought for delivery carry no STT; selling units of an equity-oriented fund on the exchange carries
# 0.001% (Securities Transaction Tax, Finance (No. 2) Act 2004 as amended; checked 25 Oct 2026). Fees and stamp duty as shares
IN_ETF = {"stt_sell": 0.00001, "exchange": 0.0000307, "sebi": 0.000001, "stamp_buy": 0.00015}
IN_EQUITY_MIS = {"stt_sell": 0.00025, "exchange": 0.0000307, "sebi": 0.000001, "stamp_buy": 0.00003}   # intraday
IN_FUTURES = {"stt_sell": 0.0005, "exchange": 0.0000183, "sebi": 0.000001, "stamp_buy": 0.00002}     # STT 0.05% on sells (0.02% before 1 Apr 2026)
IN_OPTIONS = {"stt_sell": 0.0015, "exchange": 0.0003513, "sebi": 0.000001, "stamp_buy": 0.00003}    # STT 0.15% of premium on sells (0.1% before 1 Apr 2026)
IN_BSE_OPTIONS = {**IN_OPTIONS, "exchange": 0.000325}   # BSE index options (SENSEX, BANKEX): ₹3,250 a crore of premium
IN_MCX_OPTIONS = {"stt_sell": 0.0005, "exchange": 0.000418, "sebi": 0.000001, "stamp_buy": 0.00003}   # CTT, not STT
IN_MCX_FUTURES = {"stt_sell": 0.0001, "exchange": 0.000021, "sebi": 0.000001, "stamp_buy": 0.00002}   # CTT on non-agri sells
IN_CDS_FUTURES = {"stt_sell": 0.0, "exchange": 0.0000035, "sebi": 0.000001, "stamp_buy": 0.000001}  # no STT on currency
IN_CDS_OPTIONS = {"stt_sell": 0.0, "exchange": 0.000311, "sebi": 0.000001, "stamp_buy": 0.000001}   # on premium; no STT
IN_RATES = {"in_eq": IN_EQUITY, "in_etf": IN_ETF, "in_eq_mis": IN_EQUITY_MIS, "in_fut": IN_FUTURES, "in_opt": IN_OPTIONS, "in_bse_opt": IN_BSE_OPTIONS,
            "in_mcx_opt": IN_MCX_OPTIONS, "in_mcx_fut": IN_MCX_FUTURES, "in_cds_fut": IN_CDS_FUTURES, "in_cds_opt": IN_CDS_OPTIONS}
GST = 0.18
# The depository (DP) charge on a sale of delivered shares: once per stock sold from a demat account on a day, whatever the
# quantity: CDSL's ₹3.50 plus a discount broker's ₹9.50 (the ₹0-delivery, ₹20-an-order broker the defaults follow), plus
# GST, ₹15.34 (DB-040: a delivery sale's charges left it out, about 30% under on a small trade). Intraday and F&O have none.
IN_DP_SELL = 13.0


def dp_charge() -> float:
    """The DP charge on one stock's delivery sales of a day, GST included."""
    return round(IN_DP_SELL * (1 + GST), 2)


DP_KINDS = ("in_eq", "in_etf")       # shares and fund units held in a demat account; intraday, futures and options pay none
IN_STCG, IN_LTCG, IN_LTCG_EXEMPT = 0.20, 0.125, 125000

US_SEC_FEE = 0.0000206           # on sells: $20.60 a million from 4 Apr 2026 (SEC fee rate advisory, fiscal 2026)
US_FINRA_TAF, US_FINRA_CAP = 0.000195, 9.79   # per share sold, capped per trade (FINRA, from 1 Jan 2026)
CRYPTO_FEE = 0.001               # typical taker fee, each side
UK_STAMP = 0.005                 # stamp duty (SDRT) on share purchases
FX_SPREAD = 0.0001               # about one pip on a major pair, each side
CMDTY_SPREAD = 0.0002            # global futures: about a tick of spread plus commission, each side

LABELS = {
    "brokerage": "Brokerage", "stt": "STT / CTT", "exchange": "Exchange + SEBI fees", "stamp": "Stamp duty",
    "gst": "GST", "sec": "SEC fee", "finra": "FINRA fee", "fee": "Exchange fee", "spread": "Spread",
    "slippage": "Slippage", "dp": "Depository (DP) charge",
}


def is_india_etf(inst: dict | None) -> bool:
    """Whether an Indian cash instrument is an exchange-traded fund. The instrument list files ETFs as plain "EQ"
    (NIFTYBEES comes back as a share), so the symbol, ISIN and name tell (instrument_kinds.py, as the SIP test reads them):
    a backtest of one was charged a share's 0.1% STT on both sides (RC3T-001; DG-031 had fixed the SIP test only)."""
    inst = inst or {}
    if inst.get("type") == "ETF":
        return True
    if inst.get("type") not in ("EQ", None, "") or inst.get("exchange") not in ("NSE", "BSE"):
        return False
    from .. import instrument_kinds
    return instrument_kinds.base(instrument_kinds.classify(inst.get("symbol"), inst.get("isin"), inst.get("name"))) == "etf"


def kind_of(inst: dict | None) -> str:
    """Which cost model applies to an instrument."""
    inst = inst or {}
    market = inst.get("market", "IN")
    opt = inst.get("type") in ("CE", "PE")
    if market == "MCX":
        return "in_mcx_opt" if opt else "in_mcx_fut"
    if market == "CDS":
        cur = inst.get("currency") or "INR"
        base = "in_cds_opt" if opt else "in_cds_fut"
        return f"{base}_{cur.lower()}" if cur in ("USD", "JPY") else base
    if market == "IN":
        t = inst.get("type")
        if t in ("CE", "PE"):
            return "in_bse_opt" if inst.get("exchange") == "BFO" else "in_opt"
        if t == "FUT":
            return "in_fut"
        return "in_etf" if is_india_etf(inst) else "in_eq"
    if market == "UK":
        return "uk_etf" if inst.get("type") == "ETF" else "uk"
    return {"US": "us", "CRYPTO": "crypto", "FX": "fx", "CMDTY": "cmdty"}.get(market, "flat")


FALLBACK_RUPEES = {"USD": 88.0, "JPY": 0.6}      # until the day's rates have been read


def rupees_per(currency: str) -> float:
    """Rupees per unit of a currency, from the daily rates (a recent typical value until they're read)."""
    try:
        from ..pricing import rates
        v = float(rates().get(currency) or 0)
    except Exception:
        v = 0.0
    return v if v > 0 else FALLBACK_RUPEES[currency]


def order_costs(kind: str, side: str, qty: float, price: float, brokerage: float) -> dict[str, float]:
    """Itemised costs of one order, in the market's currency. Currency cross pairs (EURUSD, USDJPY) are priced in
    dollars or yen while brokerage is set in rupees, so it's converted at the day's rate."""
    if kind.startswith("in_cds_") and kind[-4:] in ("_usd", "_jpy"):
        brokerage = brokerage / rupees_per(kind[-3:].upper())
        kind = kind[:-4]
    value = qty * price
    c = {"brokerage": brokerage}
    if kind.startswith("in_"):
        r = IN_RATES[kind]
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


def _long_term(a: str, b: str) -> bool:
    """Held for more than 12 months: sold after the same date a year on."""
    try:
        d = datetime.fromisoformat(a).date()
        e = datetime.fromisoformat(b).date()
    except (TypeError, ValueError):
        return False
    try:
        return e > d.replace(year=d.year + 1)
    except ValueError:  # 29 Feb
        return e > d.replace(year=d.year + 1, day=28)


def _fy(exit_t) -> int:
    """The financial year (April to March) a sale falls in, by its starting year; 0 when the date can't be read."""
    try:
        d = datetime.fromisoformat(str(exit_t)).date()
    except (TypeError, ValueError):
        return 0
    return d.year if d.month >= 4 else d.year - 1


def tax_estimate(kind: str, trades: list[dict]) -> dict:
    """A rough capital-gains estimate on the net profit, STT added back (capital-gains rules don't allow it as a
    deduction). Only India equity is estimated. The ₹1.25 lakh of long-term gains that is free of tax is for each
    financial year, and a loss no gain of its year could absorb carries on to the next year (RC3T-003: a ten-year test
    had the exemption once)."""
    if kind != "in_eq":
        note = ("F&O profit is taxed as business income at your slab rate, so it isn't estimated here."
                if kind in ("in_fut", "in_opt", "in_bse_opt", "in_mcx_fut", "in_mcx_opt")
                else "Currency F&O profit is taxed as business income at your slab rate, so it isn't estimated here."
                if kind.startswith("in_cds_")
                else "Intraday equity profit is taxed as speculative business income at your slab rate, so it isn't estimated here."
                if kind == "in_eq_mis"
                else "Tax on fund units depends on what the fund holds, so it isn't estimated here." if kind == "in_etf"
                else "Tax depends on where you live, so it isn't estimated for this market.")
        return {"amount": None, "note": note}
    # the gain before STT: the trade's P&L is after it, and capital-gains rules don't deduct it (rev10a)
    gain = lambda t: t["pnl"] + IN_EQUITY["stt"] * (t.get("qty") or 0) * ((t.get("entry") or 0) + (t.get("exit") or 0))  # noqa: E731
    years: dict[int, list[float]] = {}
    for t in trades:
        got = years.setdefault(_fy(t.get("exit_t")), [0.0, 0.0])
        got[1 if _long_term(t.get("entry_t"), t.get("exit_t")) else 0] += gain(t)
    amount, lost_short, lost_long = 0.0, 0.0, 0.0
    for fy in sorted(years):
        short, long_ = years[fy][0] - lost_short, years[fy][1] - lost_long
        if short < 0 < long_:   # a short-term loss also sets off long-term gains; a long-term loss only long-term ones
            absorbed = min(-short, long_)
            short, long_ = short + absorbed, long_ - absorbed
        amount += max(0.0, short) * IN_STCG + max(0.0, long_ - IN_LTCG_EXEMPT) * IN_LTCG
        lost_short, lost_long = max(0.0, -short), max(0.0, -long_)
    return {"amount": round(amount, 2),
            "note": ("Rough estimate: 20% on short-term gains, 12.5% on long-term gains above ₹1.25 lakh in each financial year, "
                     "on gains before STT (STT isn't deductible from capital gains). Losses and your other income can change it.")}


def floor_to(q: float, step: float) -> float:
    """Round a quantity down to the instrument's step (1 share, a lot of 65, 0.0001 BTC)."""
    if not math.isfinite(q) or q <= 0:
        return 0.0
    n = math.floor(q / step + 1e-9)
    v = round(n * step, 10)
    return int(v) if v == int(v) else v  # whole shares and lots stay integers
