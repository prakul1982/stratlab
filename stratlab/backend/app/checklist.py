"""The investor checklist: fixed, written-down rules run on a company's reported numbers, its price trend, its filings
and its management report card. Each check says pass, watch or fail with the number behind it.

These are screening rules the user can read and disagree with, not a view on the stock; the page says so."""
from .intel.screener import summary

GROUPS = ["Trend", "Growth", "Quality", "Balance sheet", "Cash", "Promoters", "Filings", "Management"]


def _state(v, good, bad, higher_better=True) -> str:
    """pass beyond `good`, fail beyond `bad`, watch in between."""
    if v is None:
        return "na"
    if higher_better:
        return "pass" if v >= good else "fail" if v < bad else "watch"
    return "pass" if v <= good else "fail" if v > bad else "watch"


def _pct(v, signed=True) -> str:
    return "–" if v is None else f"{v:+.1f}%" if signed else f"{v:.1f}%"


def _row(table: dict | None, prefix: str) -> list:
    for label, vals in ((table or {}).get("rows") or {}).items():
        if label.lower().startswith(prefix.lower()):
            return [v for v in vals if v is not None]
    return []


def evaluate(p: dict, nums: dict, filings_summary: dict | None = None, trend: dict | None = None, card: dict | None = None) -> dict:
    s = summary(p)
    g = nums.get("growth") or {}
    years = [y for y in nums.get("years") or [] if y.get("sales") is not None]
    quarters = [q for q in nums.get("quarters") or [] if q.get("sales_yoy") is not None]
    out: list[dict] = []

    def add(group, label, state, value, rule):
        out.append({"group": group, "label": label, "state": state, "value": value, "rule": rule})

    # trend
    if trend:
        st = trend.get("stage")
        add("Trend", "Price in Stage 2", "na" if st is None else "pass" if st == 2 else "fail" if st == 4 else "watch",
            f"Stage {st}" if st else "–", "Stage 2: above a rising 150-day average. Stage 4: below a falling one.")
        add("Trend", "Supertrend up", "pass" if trend.get("st_up") else "fail",
            f"{'Up' if trend.get('st_up') else 'Down'} for {trend.get('st_days')} days", "Supertrend (10, 3) on daily candles.")

    # growth
    add("Growth", "Sales growth, 3 years", _state(g.get("sales_cagr_3y"), 10, 0), _pct(g.get("sales_cagr_3y")) + " a year",
        "Pass at 10% a year or more; fail if sales shrank.")
    add("Growth", "Profit growth, 3 years", _state(g.get("profit_cagr_3y"), 10, 0), _pct(g.get("profit_cagr_3y")) + " a year",
        "Pass at 10% a year or more; fail if profit shrank.")
    last_q = quarters[-1] if quarters else None
    add("Growth", "Latest quarter sales vs a year ago", _state(last_q and last_q["sales_yoy"], 5, 0),
        f"{_pct(last_q['sales_yoy'])} ({last_q['quarter']})" if last_q else "–", "Pass at +5% or more; fail if lower than a year ago.")

    # quality
    add("Quality", "Return on capital employed", _state(s.get("roce"), 15, 10), _pct(s.get("roce"), False),
        "Pass at 15% or more; fail below 10%.")
    opm_now = years[-1]["opm"] if years and years[-1].get("opm") is not None else None
    opm_then = years[-4]["opm"] if len(years) >= 4 and years[-4].get("opm") is not None else None
    d_opm = opm_now - opm_then if opm_now is not None and opm_then is not None else None
    add("Quality", "Operating margin holding up", _state(d_opm, -1, -4),
        f"{_pct(opm_now, False)}, from {_pct(opm_then, False)}" if d_opm is not None else "–",
        "Pass if within 1 point of three years ago or better; fail if down more than 4 points.")

    # balance sheet
    add("Balance sheet", "Debt to equity", _state(s.get("debt_equity"), 0.5, 1.0, higher_better=False),
        "–" if s.get("debt_equity") is None else f"{s['debt_equity']:.2f}", "Pass at 0.5 or less; fail above 1.")

    # cash
    last3 = years[-3:]
    cfo = [y["cfo"] for y in last3 if y.get("cfo") is not None]
    prof = [y["profit"] for y in last3 if y.get("profit") is not None]
    conv = sum(cfo) / sum(prof) if len(cfo) == 3 and len(prof) == 3 and sum(prof) > 0 else None
    add("Cash", "Profit turning into cash", _state(conv, 0.8, 0.5),
        "–" if conv is None else f"{conv:.2f}× profit over 3 years", "Cash from operations ÷ net profit over 3 years: pass at 0.8 or more; fail below 0.5.")
    fcf = [y["fcf"] for y in last3 if y.get("fcf") is not None]
    fcf_sum = sum(fcf) if len(fcf) == 3 else None
    add("Cash", "Free cash flow, 3 years", "na" if fcf_sum is None else "pass" if fcf_sum > 0 else "watch",
        "–" if fcf_sum is None else f"{'-' if fcf_sum < 0 else ''}₹{abs(fcf_sum):,.0f} crore", "Cash from operations minus estimated capex. Negative is common while building capacity: watch, not fail.")

    # promoters
    prom = _row(p.get("shareholding"), "Promoters")
    if prom:
        add("Promoters", "Promoter holding", _state(prom[-1], 50, 30), _pct(prom[-1], False), "Pass at 50% or more; fail below 30%.")
        if len(prom) >= 5:
            ch = prom[-1] - prom[-5]
            add("Promoters", "Promoter holding over a year", _state(ch, -0.5, -2), f"{ch:+.2f} points",
                "Pass if steady or rising; fail if down more than 2 points in four quarters.")

    # filings
    if filings_summary is not None:
        red = filings_summary.get("red", 0)
        add("Filings", "Red-flag filings, last 3 months", "pass" if red == 0 else "fail", str(red),
            "Fund raises, pledges, auditor resignations, defaults, regulator action, rating downgrades.")
        add("Filings", "Fund raise filed, last 3 months", "watch" if filings_summary.get("fund_raise") else "pass",
            "Yes" if filings_summary.get("fund_raise") else "None", "A QIP, preferential or rights issue can dilute holders.")

    # management
    if card and card.get("score") is not None:
        n = card["met"] + card["missed"]
        add("Management", "Delivered on targets", _state(card["score"], 70, 40), f"{card['met']} of {n} met",
            "From the management report card: pass at 70% of checkable targets met; fail below 40%.")

    counts = {k: sum(1 for c in out if c["state"] == k) for k in ("pass", "watch", "fail", "na")}
    return {"checks": out, "counts": counts, "scored": counts["pass"] + counts["watch"] + counts["fail"]}
