"""The demo world's company pages from the fundamentals source (the browser tests' world, tests/visual_server.py): one
for every Indian company in the price table (fake_prices), each with its own name, description, size and numbers, all
made up but consistent with each other and with the price table:

- the market value is the company's shares times the price everywhere (company page, screener, compare, holdings);
- P/E, book value, dividend yield and returns are worked out from the page's own tables at that price;
- the latest results are the June 2026 quarter and the year to March 2026, as a company would have reported them by
  October 2026 (the September quarter's results are due later in the month);
- TCS stands in for a company with three loss years (the charts' handling of losses), at its own scale.

The pages are built from the real (trimmed) RELIANCE page in fixtures, read by the app's own parser: its shape, rows
and columns, rescaled for each company. RELIANCE keeps its own numbers, a year on."""
import copy
import re
from datetime import timedelta

from tests import fake_prices as P

# symbol: (sales in the latest year, ₹ crore; net margin %; borrowings / net worth; dividend yield %; promoters %;
#          face value ₹; return on equity %; bank)
PROFILE = {
    "TCS": (255000, None, 0.05, 1.9, 71.8, 1, 50.0, False),
    "INFY": (165000, 17.5, 0.08, 2.7, 14.6, 5, 29.0, False),
    "HDFCBANK": (336000, 21.0, 6.0, 1.2, 0.0, 1, 14.5, True),
    "ICICIBANK": (186000, 25.0, 5.0, 0.8, 0.0, 2, 17.0, True),
    "SBIN": (490000, 15.0, 10.0, 1.9, 57.5, 1, 18.0, True),
    "AXISBANK": (127000, 21.0, 6.0, 0.1, 8.2, 2, 16.0, True),
    "ITC": (76000, 26.0, 0.0, 3.4, 0.0, 1, 28.0, False),
    "HINDUNILVR": (63000, 16.5, 0.0, 2.1, 61.9, 1, 21.0, False),
    "HCLTECH": (120000, 14.5, 0.05, 3.7, 60.8, 2, 24.0, False),
    "WIPRO": (90000, 14.6, 0.2, 2.4, 72.7, 2, 16.0, False),
    "LT": (255000, 6.0, 1.1, 0.9, 0.0, 2, 15.5, False),
    "BHARTIARTL": (175000, 12.0, 1.4, 0.5, 53.0, 5, 20.0, False),
    "TATASTEEL": (220000, 1.6, 1.0, 2.2, 33.2, 1, 4.0, False),
    "ONGC": (660000, 6.0, 0.5, 4.6, 58.9, 5, 12.0, False),
    "NTPC": (190000, 11.4, 1.4, 2.4, 51.1, 10, 13.0, False),
    "COALINDIA": (143000, 25.0, 0.1, 6.5, 63.1, 10, 40.0, False),
    "MARUTI": (152000, 9.4, 0.0, 1.0, 58.2, 5, 16.0, False),
    "JSWSTEEL": (170000, 2.2, 1.0, 0.7, 45.0, 1, 5.0, False),
    "NESTLEIND": (20000, 15.8, 0.1, 1.4, 62.8, 1, 85.0, False),
    "DABUR": (12500, 14.5, 0.1, 1.0, 66.2, 1, 18.0, False),
    "VEDL": (152000, 9.5, 1.5, 9.0, 56.4, 1, 30.0, False),
    "SAIL": (102000, 2.0, 0.6, 1.2, 65.0, 10, 4.0, False),
    "ULTRACEMCO": (76000, 8.0, 0.2, 0.6, 59.2, 10, 9.5, False),
    "AMBUJACEM": (35000, 12.0, 0.0, 0.3, 67.5, 2, 9.0, False),
    "TVSMOTOR": (45000, 5.7, 0.4, 0.3, 50.3, 1, 28.0, False),
}
ABOUT = {
    "TCS": "Tata Consultancy Services provides IT services, consulting and business solutions to companies around the world.",
    "INFY": "Infosys provides consulting, technology, outsourcing and digital services to companies around the world.",
}
WEBSITE = {"TCS": "https://www.tcs.com", "INFY": "https://www.infosys.com"}
# a company with three loss years, then profits (SML-like), at TCS's scale (₹ crore): the years to March 2021 to 2026
LOSS_SHAPE = [-8520, -53360, -40080, 8020, 43440, 48960]


def install(mp, screener) -> None:
    """Answer the fundamentals source with these pages (`mp`: a MonkeyPatch); companies the demo world has no page for
    still go to the fake source (RELIANCE's fixture, the BSE-only company)."""
    real = screener.company
    source = real("RELIANCE")
    mp.setattr(screener, "company", lambda sym: company(sym.upper(), source) or real(sym))


def _later(label: str) -> str:
    """A period a year later: "Jun 2025" -> "Jun 2026" (TTM stays TTM)."""
    m = re.fullmatch(r"(\w{3}) (\d{4})", str(label).strip())
    return f"{m.group(1)} {int(m.group(2)) + 1}" if m else label


def a_year_on(p: dict) -> dict:
    """The fixture page as the company would have reported a year later: every period moved on a year (the numbers are
    the page's own, so a page read in October 2026 has the June 2026 quarter and the year to March 2026)."""
    p = copy.deepcopy(p)
    for key in ("quarters", "pl", "balance", "cashflow", "ratios_table", "shareholding"):
        t = p.get(key)
        if t and t.get("cols"):
            t["cols"] = [_later(c) for c in t["cols"]]
    return p


def _fmt(v: float) -> str:
    return f"{v:,.2f}"


def _set_ratios(p: dict, sym: str, profit_ttm: float, net_worth: float, div_yield: float, face: float, roe: float):
    """The page's headline ratios at the price table's last close: market value = shares x price, and the rest from
    the page's own numbers."""
    price = P.last(sym)
    cap = P.market_cap(sym, price)
    shares = P.SHARES[sym]
    end = P.session_clock(None, "IN")
    closes = [P.price(sym, end - timedelta(days=d)) for d in range(0, 366)]
    p["ratios"] = {"Market Cap": f"₹ {cap:,.0f} Cr.", "Current Price": f"₹ {price:,.2f}",
                   "High / Low": f"₹ {max(closes):,.0f} / {min(closes):,.0f}",
                   "Stock P/E": f"{cap / profit_ttm:.1f}" if profit_ttm > 0 else "",
                   "Book Value": f"₹ {net_worth / shares:,.0f}", "Dividend Yield": f"{div_yield:.2f} %",
                   "ROCE": f"{roe * 1.15:.2f} %", "ROE": f"{roe:.2f} %", "Face Value": f"₹ {face:.1f}"}


def _price_growth(sym: str) -> dict:
    """The share price's compounded change over 1, 3, 5 and 10 years, from the price table."""
    end = P.session_clock(None, "IN")
    now = P.price(sym, end)
    out = {}
    for n, label in ((1, "1 Year"), (3, "3 Years"), (5, "5 Years"), (10, "10 Years")):
        then = P.price(sym, end - timedelta(days=365 * n))
        out[label] = f"{((now / then) ** (1 / n) - 1) * 100:.0f}%"
    return out


def _cagr(vals: list, n: int) -> str | None:
    if len(vals) <= n or not vals[-1 - n] or vals[-1 - n] <= 0 or vals[-1] <= 0:
        return None
    return f"{((vals[-1] / vals[-1 - n]) ** (1 / n) - 1) * 100:.0f}%"


def reliance(p: dict) -> dict:
    """RELIANCE: its own page a year on, priced at the price table's last close."""
    p = a_year_on(p)
    pl = p["pl"]["rows"]
    bal = p["balance"]["rows"]
    nw = bal["Equity Capital"][-1] + bal["Reserves"][-1]
    _set_ratios(p, "RELIANCE", pl["Net Profit"][-1], nw, 0.39, 10.0, 8.51)
    p["growth"]["price"] = _price_growth("RELIANCE")
    return p


def company(sym: str, rel: dict) -> dict | None:
    """`sym`'s page, built from RELIANCE's (`rel`, as the parser reads it); None for a company the demo world has no
    page for."""
    if sym == "RELIANCE":
        return reliance(rel)
    if sym not in PROFILE or sym not in P.SHARES:
        return None
    sales_now, margin, debt_x, dy, promoters, face, roe, bank = PROFILE[sym]
    p = a_year_on(rel)
    shares = P.SHARES[sym]
    pl, q = p["pl"], p["quarters"]
    cols = pl["cols"]
    full = [i for i, c in enumerate(cols) if str(c).upper() != "TTM"]
    rel_sales = pl["rows"]["Sales"]
    k = sales_now / rel_sales[full[-1]]
    sales = [round(v * k) for v in rel_sales]
    if margin is None:                       # the loss case
        profit = [None] * (len(full) - len(LOSS_SHAPE)) + LOSS_SHAPE
        profit = profit[-len(full):]
    else:
        profit = [round(s * margin / 100) for i, s in enumerate(sales) if i in full]
    # the trailing twelve months are the last four quarters, so the quarters and the year agree
    q_sales = [round(v * k) for v in q["rows"]["Sales"]]
    rel_qp = q["rows"]["Net Profit"]
    ttm_profit = round(profit[-1] * sales[-1] / sales[full[-1]]) if profit[-1] else 0
    scale_q = ttm_profit / sum(rel_qp[-4:])
    q_profit = [round(v * scale_q) for v in rel_qp]
    profit_row = profit + [ttm_profit] if len(cols) > len(full) else profit
    eps = [round(v / shares, 2) if v is not None else None for v in profit_row]
    rows = {("Revenue" if bank else "Sales"): sales, ("Financing Margin %" if bank else "OPM %"): pl["rows"]["OPM %"],
            "Net Profit": profit_row, "EPS in Rs": eps}
    pl["rows"] = rows
    qrows = {("Revenue" if bank else "Sales"): q_sales,
             ("Financing Profit" if bank else "Operating Profit"): [round(v * k) for v in q["rows"]["Operating Profit"]],
             ("Financing Margin %" if bank else "OPM %"): q["rows"]["OPM %"], "Net Profit": q_profit}
    q["rows"] = qrows
    # the balance sheet: net worth from the return on equity, growing as the source company's did
    bal = p["balance"]
    nw_now = max(profit[-1], sales_now * 0.05) / (roe / 100)
    rel_nw = [e + r for e, r in zip(bal["rows"]["Equity Capital"], bal["rows"]["Reserves"])]
    equity = round(shares * face, 2)
    nw = [nw_now * v / rel_nw[-1] for v in rel_nw]
    bal["rows"] = {"Equity Capital": [equity] * len(nw), "Reserves": [round(v - equity) for v in nw],
                   "Borrowings": [round(v * debt_x) for v in nw]}
    # cash from operations a little over the profit of each year (never a multiple of a tiny profit)
    cf = p["cashflow"]
    by_year = dict(zip([cols[i] for i in full], profit))
    cf["rows"] = {"Cash from Operating Activity": [round(max(by_year.get(c) or 0, sales_now * 0.02) * 1.1) for c in cf["cols"]]}
    # who owns it: the promoters' share, the rest split as the source's was
    sh = p["shareholding"]
    others = {k: v for k, v in sh["rows"].items() if k in ("FIIs", "DIIs", "Public")}
    left = 100 - promoters
    rest = {k: [round(x / (100 - pr) * left, 2) for x, pr in zip(v, sh["rows"]["Promoters"])] for k, v in others.items()}
    sh["rows"] = {"Promoters": [promoters] * len(sh["cols"]), **rest,
                  "No. of Shareholders": sh["rows"].get("No. of Shareholders", [])}
    name, sector = P.COMPANIES[sym]
    p.update(name=name, about=ABOUT.get(sym), website=WEBSITE.get(sym), pros=[], cons=[], industry_path=[sector],
             company_id=None, url=f"https://www.screener.in/company/{sym}/consolidated/")
    if not p.get("about"):
        p.pop("about")
    if not p.get("website"):
        p.pop("website")
    p["growth"] = {"sales": {k: v for k, v in (("3 Years", _cagr([sales[i] for i in full], 3)), ("5 Years", _cagr([sales[i] for i in full], 5))) if v},
                   "profit": {k: v for k, v in (("3 Years", _cagr(profit, 3)), ("5 Years", _cagr(profit, 5))) if v},
                   "price": _price_growth(sym)}
    _set_ratios(p, sym, ttm_profit, nw[-1], dy, face, roe)
    return p
