"""A theme's deep dive, worked out from figures the app already holds (THEME-1): no source is called for the figures, and the
AI writes none of them.

Everything here is a function of plain data so it can be checked against what it was given:
- `company_row` takes one company's stored public-page facts (stock_pages) and gives its latest full-year revenue, EBITDA
  margin, net margin, return on capital employed, growth, valuation and balance-sheet figures, each as that page shows
  it (the screens' checks for a stale year, an extreme margin or a failed market value apply);
- `layer_block`, `chain_table` and the section builders take those rows by value-chain layer or sub-theme and give the
  tables, medians, ranges and the lines that say what they show;
- `build` puts them together for a map whose companies have already been checked against their own descriptions
  (theme_check.py), reading the stored holdings, results, corporate actions, red flags, management report cards and
  insider purchases through the callables in `Sources`.

Facts and arithmetic only: no ranking of what to own, no advice wording, no forecast."""
import re
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from datetime import date, timedelta
from statistics import median

from .. import stock_pages
from .. import screens

# a company that runs several businesses: its figures are the whole company's, not those of one layer's work
DIVERSIFIED = {"RELIANCE", "ADANIENT", "M&M", "LT", "ITC", "GRASIM", "SIEMENS", "TATASONS", "BAJAJHLDNG", "JSWHL", "AEGISLOG", "GODREJIND",
               "BRK-B", "BRK.B", "GE", "HON", "MMM", "CMI", "DHR"}
_PART_YEAR = re.compile(r"\s\d+m$")
_YEAR = re.compile(r"^([A-Za-z]{3})\s+(\d{4})$")
NOTABLE_GAP = 10.0            # points between the highest and lowest layer median EBITDA margin that make a post worth drafting
NOTABLE_MOVE = 5.0            # points a layer's EBITDA margin moved over three years
MIN_LAYER = 2                 # companies a layer needs for its median to be called a layer's figure in a post
FINANCIAL_KEYS = ("ebitda", "roce", "debt_equity")


def num(v):
    return screens._num(v)


def stat(values) -> dict | None:
    """{"n", "median", "min", "max"} of the numbers among `values`; None when there is none."""
    xs = [x for x in (num(v) for v in values) if x is not None]
    if not xs:
        return None
    return {"n": len(xs), "median": round(median(xs), 2), "min": round(min(xs), 2), "max": round(max(xs), 2)}


def r1(v):
    return None if v is None else round(float(v), 1)


def f1(v: float) -> str:
    """One decimal, a half rounded up as the browser's toFixed does, so a sentence here and a table cell there never differ in the last digit."""
    return str(Decimal(float(v)).quantize(Decimal("0.1"), ROUND_HALF_UP))


def pts(v: float) -> str:
    """12.3% (one decimal, a real minus)."""
    return f"{f1(v)}%".replace("-", "−")


def full_years(f: dict) -> list[dict]:
    """The page's reported years, oldest first, without a company's first part-year report."""
    out = []
    for y in f.get("years") or []:
        label = str(y.get("year") or "").strip()
        if label and not _PART_YEAR.search(label) and label.upper() != "TTM":
            out.append({**y, "year": label})
    return out


def _next_year(a: str, b: str) -> bool:
    """Whether year label `b` is the year after `a` ("Mar 2025" then "Mar 2026")."""
    ma, mb = _YEAR.match(a), _YEAR.match(b)
    return bool(ma and mb and ma.group(1) == mb.group(1) and int(mb.group(2)) == int(ma.group(2)) + 1)


def growth_between(years: list[dict], key: str, back: int) -> float | None:
    """The yearly compound growth of `key` over `back` years to the newest year, only when the years are consecutive."""
    if len(years) <= back:
        return None
    tail = years[-1 - back:]
    if not all(_next_year(tail[i]["year"], tail[i + 1]["year"]) for i in range(back)):
        return None
    new, old = num(tail[-1].get(key)), num(tail[0].get(key))
    if new is None or old is None or new <= 0 or old <= 0:
        return None
    return ((new / old) ** (1 / back) - 1) * 100


def company_row(region: str, symbol: str, f: dict | None) -> dict | None:
    """One company's line, from its stored page facts; None when the page holds nothing to show."""
    if not isinstance(f, dict) or not f or f.get("not_company"):
        return None
    base = screens.row(region, symbol, f)
    if not base:
        return None
    old, wild = stock_pages.figures_stale(f), stock_pages.extreme(f)
    years = full_years(f)
    last = years[-1] if years and not old else None
    lender = bool(f.get("bank"))
    sales = num(last.get("sales")) if last else None
    profit = num(last.get("profit")) if last else None
    net = (profit / sales * 100) if sales and sales > 0 and profit is not None else None
    ebitda = num(last.get("opm")) if last and not lender else None
    cfo = num(last.get("cfo")) if last else None
    cap, debt, cash = base.get("market_cap"), num(f.get("debt")), num(f.get("cash"))
    ebitda_amt = sales * ebitda / 100 if sales and ebitda is not None and sales > 0 else None
    # enterprise value over EBITDA: market value plus debt less cash, over the year's EBITDA; n/a where any of the four is missing, or EBITDA isn't positive
    ev = (cap + debt - cash) / ebitda_amt if None not in (cap, debt, cash) and ebitda_amt and ebitda_amt > 0 and not wild and not lender else None
    yoy = f.get("latest_yoy") if isinstance(f.get("latest_yoy"), dict) and f["latest_yoy"].get("basis") == "quarter" else None
    return {
        "symbol": symbol, "name": base["name"], "year": last["year"] if last else None, "unit": f.get("unit"), "bank": lender,
        "revenue": sales if sales and sales > 0 else None, "profit": profit,
        "ebitda": None if wild or ebitda is None or abs(ebitda) > stock_pages.EXTREME else r1(ebitda),
        "net": None if wild or net is None or abs(net) > stock_pages.EXTREME else r1(net),
        "roce": None if lender or old else r1(num(f.get("roce"))),
        "cap": cap, "pe": base.get("pe"), "pb": None if old else r1(num(f.get("pb"))),
        "interest_cover": None if lender or old else r1(num(f.get("interest_cover"))), "ev_ebitda": r1(ev),
        "quarter": {"of": yoy.get("of"), "sales": r1(num(yoy.get("sales"))), "profit": r1(num(yoy.get("profit")))} if yoy else None,
        "debt_equity": None if lender else base.get("debt_equity"),
        "cfo_to_profit": round(cfo / profit, 2) if cfo is not None and profit and profit > 0 else None,
        "sales_1y": r1(growth_between(years, "sales", 1)) if not old else None,
        "sales_3y": r1(num(base.get("sales_cagr_3y"))) if not old else None,
        "sales_5y": r1(num((f.get("growth") or {}).get("sales_cagr_5y"))) if not old else None,
        "profit_1y": r1(growth_between(years, "profit", 1)) if not old else None,
        "profit_3y": r1(num((f.get("growth") or {}).get("profit_cagr_3y"))) if not old else None,
        "profit_5y": r1(num((f.get("growth") or {}).get("profit_cagr_5y"))) if not old else None,
        "stage": base.get("stage"), "from_high": base.get("from_high"), "price": num(f.get("price")), "price_at": base.get("price_at"),
        "high52": num(f.get("high52")), "low52": num(f.get("low52")), "st_up": f.get("st_up"),
        "red_flags": base.get("red_flags"), "basis": f.get("basis"), "industry": f.get("industry") or [],
        "years": [{"year": y["year"], "sales": num(y.get("sales")), "profit": num(y.get("profit")), "opm": None if lender else num(y.get("opm"))} for y in years],
    }


def is_diversified(row: dict, layers_in: int) -> bool:
    """Whether a company's figures are the whole company's, not one layer's: a group that runs several businesses, a company the
    exchange files as diversified, or one that does the work of several layers of this map."""
    ind = " ".join(row.get("industry") or []).lower()
    return row["symbol"] in DIVERSIFIED or "diversified" in ind or "conglomerate" in ind or layers_in > 1


def basis_text(rows: list[dict], region: str) -> str:
    unit = next((r.get("unit") for r in rows if r.get("unit")), None) or ("₹ crore" if region == "IN" else "$ million")
    fy = "financial year ended March" if region == "IN" else "latest fiscal year"
    return (f"Each company's latest full {fy}, in {unit}. Revenue, EBITDA margin (operating profit before depreciation as a share of revenue) "
            "and net margin (net profit as a share of revenue) are that year's; return on capital employed (ROCE) is the latest reported. "
            "Consolidated accounts where the company files them. Banks and lenders have no EBITDA margin or ROCE.")


# ---------- layers and sub-themes ----------
def layer_block(name: str, rows: list[dict], wide: set[str]) -> dict:
    """A layer's table and its median and range for each figure. A company-wide figure (a group that runs other businesses too) is
    marked and left out of the median when the layer has any company that is its own; the layer says how many were left out."""
    own = [r for r in rows if r["symbol"] not in wide]
    pool = own or rows
    keys = ("ebitda", "net", "roce")
    stats = {k: stat(r.get(k) for r in pool) for k in keys}
    return {"layer": name, "companies": rows, "stats": stats, "n": len(rows),
            "revenue": sum(r["revenue"] for r in rows if r.get("revenue")) or None,
            "company_wide": sorted(r["symbol"] for r in rows if r["symbol"] in wide),
            "stats_over": "all" if not own and rows else "own", "left_out": len(rows) - len(pool)}


def margin_line(block: dict, chain_median: float | None, several: bool = True) -> str | None:
    """What a layer's table doesn't say by itself: how its median EBITDA margin stands against the whole map's, and which figures are the whole
    company's. (The median and range are rows of the table, not said again.) None when there is nothing more to say."""
    e = block["stats"].get("ebitda")
    parts = []
    if e and chain_median is not None and several:
        d = e["median"] - chain_median
        if abs(d) >= 0.05:
            parts.append(f"The median EBITDA margin ({pts(e['median'])}) is {f1(abs(d))} points {'above' if d > 0 else 'below'} the median of the whole map ({pts(chain_median)}).")
    if block["left_out"]:
        parts.append(f"{block['left_out']} figure{'s are' if block['left_out'] > 1 else ' is'} the whole company's and left out of the medians"
                     " because the company runs other businesses too.")
    elif block["stats_over"] == "all" and block["companies"]:
        parts.append("Every figure here is the whole company's, since each runs other businesses too.")
    return " ".join(parts) or None


def chain_table(blocks: list[dict]) -> dict:
    """The whole chain in one table: a row per layer, with the layer that has the highest median EBITDA margin and the one with the
    lowest named. The table's order is the chain's."""
    rows = []
    for b in blocks:
        e, n, c = (b["stats"].get(k) for k in ("ebitda", "net", "roce"))
        rows.append({"layer": b["layer"], "n": b["n"], "revenue": b["revenue"], "ebitda": e["median"] if e else None, "net": n["median"] if n else None,
                     "roce": c["median"] if c else None, "ebitda_n": e["n"] if e else 0})
    have = [r for r in rows if r["ebitda"] is not None and r["ebitda_n"] >= 1]
    line = None
    if len(have) >= 2:
        hi, lo = max(have, key=lambda r: r["ebitda"]), min(have, key=lambda r: r["ebitda"])
        if hi["layer"] != lo["layer"] and hi["ebitda"] != lo["ebitda"]:
            line = (f"Median EBITDA margin is highest in {hi['layer']} ({pts(hi['ebitda'])}) and lowest in {lo['layer']} ({pts(lo['ebitda'])}), "
                    f"a gap of {f1(hi['ebitda'] - lo['ebitda'])} points.")
    spread = len(have) >= 2 and max(r["ebitda"] for r in have) != min(r["ebitda"] for r in have)       # layers with the same figure have no highest or lowest
    return {"rows": rows, "line": line, "highest": max(have, key=lambda r: r["ebitda"])["layer"] if spread else None,
            "lowest": min(have, key=lambda r: r["ebitda"])["layer"] if spread else None}


def layer_history(rows: list[dict]) -> dict | None:
    """A layer's aggregate EBITDA margin (operating profit over revenue, all its companies together) for each year in which at least
    two of its companies report, with the same companies throughout: {"years": [...], "ebitda": [...], "net": [...], "n"}."""
    rows = [r for r in rows if r.get("years") and not r.get("bank")]
    if len(rows) < MIN_LAYER:
        return None
    labels = sorted({y["year"] for r in rows for y in r["years"]}, key=_year_key)
    best = None
    for start in range(len(labels)):
        span = labels[start:]
        keep = [r for r in rows if all(any(y["year"] == lb and y["sales"] and y["opm"] is not None for y in r["years"]) for lb in span)]
        if len(keep) >= MIN_LAYER and len(span) >= 2 and (best is None or len(span) > len(best[0])):
            best = (span, keep)
    if not best:
        return None
    span, keep = best
    ebitda, net = [], []
    for lb in span:
        ys = [next(y for y in r["years"] if y["year"] == lb) for r in keep]
        s = sum(y["sales"] for y in ys)
        ebitda.append(round(sum(y["sales"] * y["opm"] for y in ys) / s, 1) if s else None)
        net.append(round(sum(y["profit"] for y in ys if y["profit"] is not None) / s * 100, 1) if s and all(y["profit"] is not None for y in ys) else None)
    return {"years": span, "ebitda": ebitda, "net": net, "n": len(keep), "companies": [r["symbol"] for r in keep]}


def _year_key(label: str):
    m = _YEAR.match(label)
    return (int(m.group(2)), m.group(1)) if m else (0, label)


# ---------- the theme as a whole ----------
def size_section(rows: list[dict]) -> dict:
    caps = sorted(((r["cap"], r) for r in rows if r.get("cap")), key=lambda t: -t[0])
    total = sum(c for c, _ in caps)
    return {"companies": len(rows), "with_value": len(caps), "total_cap": total or None,
            "biggest": [{"symbol": r["symbol"], "name": r["name"], "cap": c, "share": round(c / total * 100, 1)} for c, r in caps[:5]] if total else [],
            "top3_share": round(sum(c for c, _ in caps[:3]) / total * 100, 1) if total and len(caps) >= 3 else None}


def aggregate_growth(rows: list[dict]) -> dict:
    """Revenue and profit growth of the theme's companies together over one and three years (the companies that report both ends),
    and the median of the companies' own one, three and five-year rates."""
    out = {"aggregate": {}, "median": {}}
    for key, label in (("sales", "revenue"), ("profit", "profit")):
        for back, tag in ((1, "1y"), (3, "3y")):
            pairs = []
            for r in rows:
                ys = r.get("years") or []
                if len(ys) > back and all(_next_year(ys[-1 - back + i]["year"], ys[-back + i]["year"]) for i in range(back)):
                    a, b = num(ys[-1 - back][key]), num(ys[-1][key])
                    if a and b and a > 0 and b > 0:
                        pairs.append((a, b, ys[-1]["year"]))
            if pairs:
                year = Counter(p[2] for p in pairs).most_common(1)[0][0]          # the companies whose newest year is the usual one
                pairs = [p for p in pairs if p[2] == year]
            if len(pairs) >= 2:
                a, b = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
                out["aggregate"][f"{label}_{tag}"] = {"value": round(((b / a) ** (1 / back) - 1) * 100, 1), "n": len(pairs), "year": year}
        for tag in ("1y", "3y", "5y"):
            s = stat(r.get(f"{key}_{tag}") for r in rows)
            if s:
                out["median"][f"{label}_{tag}"] = s
    return out


def margin_history(rows: list[dict]) -> dict | None:
    """The theme's aggregate EBITDA and net margin for each year the same companies all report (see layer_history)."""
    h = layer_history(rows)
    if not h:
        return None
    return h


def valuation_section(rows: list[dict], market: list[dict]) -> dict:
    pe = stat(r["pe"] for r in rows if r.get("pe"))
    mkt = stat(m.get("pe") for m in market if m.get("pe") and 0 < m["pe"] <= stock_pages.PE_MAX)
    pb = stat(r["pb"] for r in rows if r.get("pb") is not None and r["pb"] > 0)
    mpb = stat(m.get("pb") for m in market if m.get("pb") and m["pb"] > 0)
    ev = stat(r["ev_ebitda"] for r in rows)
    return {"pe": pe, "market_pe": mkt, "market_n": mkt["n"] if mkt else 0, "pb": pb, "market_pb": mpb, "ev_ebitda": ev,
            "ev_missing": sum(1 for r in rows if r.get("ev_ebitda") is None and not r.get("bank"))}


def balance_section(rows: list[dict]) -> dict:
    de = stat(r["debt_equity"] for r in rows)
    own = [r for r in rows if r.get("debt_equity") is not None]
    cfo = [r["cfo_to_profit"] for r in rows if r.get("cfo_to_profit") is not None]
    return {"debt_equity": de, "above_1": sum(1 for r in own if r["debt_equity"] > 1), "with_debt_equity": len(own),
            "cfo_to_profit": stat(cfo), "cfo_n": len(cfo), "interest_cover": stat(r.get("interest_cover") for r in rows),
            "cover_under_2": sum(1 for r in rows if r.get("interest_cover") is not None and r["interest_cover"] < 2)}


def quarter_section(rows: list[dict]) -> dict:
    """The latest reported quarter of each company against the same quarter a year before (revenue and net profit change), as the company page's
    "Latest YoY" gives it, with how many are up and down. Facts only: it compares a company with its own year-ago quarter, not with anyone's estimate."""
    have = [r for r in rows if r.get("quarter") and (r["quarter"]["sales"] is not None or r["quarter"]["profit"] is not None)]
    return {"companies": [{"symbol": r["symbol"], "name": r["name"], "of": r["quarter"]["of"], "sales": r["quarter"]["sales"], "profit": r["quarter"]["profit"]} for r in have],
            "sales_up": sum(1 for r in have if (r["quarter"]["sales"] or 0) > 0), "sales_down": sum(1 for r in have if (r["quarter"]["sales"] or 0) < 0),
            "profit_up": sum(1 for r in have if (r["quarter"]["profit"] or 0) > 0), "profit_down": sum(1 for r in have if (r["quarter"]["profit"] or 0) < 0),
            "sales": stat(r["quarter"]["sales"] for r in have), "profit": stat(r["quarter"]["profit"] for r in have)}


def stored_price_section(rows: list[dict]) -> dict:
    """Breadth inside the theme from each company's stored page: the share in Stage 2, with the Supertrend up, and within 5% of the
    52-week high or 10% above the 52-week low."""
    def share(pred, pool):
        pool = [r for r in pool]
        n = len(pool)
        return {"n": n, "count": sum(1 for r in pool if pred(r)), "share": round(sum(1 for r in pool if pred(r)) / n * 100) if n else None}
    staged = [r for r in rows if r.get("stage") is not None]
    trend = [r for r in rows if r.get("st_up") is not None]
    ranged = [r for r in rows if r.get("price") and r.get("high52") and r.get("low52")]
    return {"stage2": share(lambda r: r["stage"] == 2, staged), "supertrend_up": share(lambda r: bool(r["st_up"]), trend),
            "near_high": share(lambda r: r["price"] >= r["high52"] * 0.95, ranged),
            "near_low": share(lambda r: r["price"] <= r["low52"] * 1.10, ranged)}


def leaders(rows: list[dict]) -> list[dict]:
    """The table of every company in the theme with the figures to sort it by."""
    return [{k: r.get(k) for k in ("symbol", "name", "cap", "revenue", "year", "ebitda", "net", "roce", "sales_1y", "sales_3y", "profit_1y", "profit_3y",
                                    "pe", "pb", "ev_ebitda", "debt_equity", "stage", "from_high")} for r in rows]


# ---------- stored events, holdings and cards ----------
def ownership_section(symbols: list[str], names: dict, src) -> dict:
    """The promoter group's stake (the sum of the named promoter holders' stakes in the exchange's shareholding filing) in the latest
    quarter, and its change since the quarter before; the named funds, insurers and foreign investors above 1% in the same filing;
    promoter and insider purchases the exchange's disclosures show in the last 90 days; and the pledges and fund raises among the
    red-flag filings."""
    rows, bought, pledges = [], [], []
    for sym in symbols:
        co = None
        try:
            co = src.shareholding(sym)
        except Exception as e:
            print("theme data: holdings not read:", sym, type(e).__name__, str(e)[:100])
        qs = sorted((co or {}).get("q") or {})
        if not qs:
            continue

        def split(q):
            rows_ = (co["q"].get(q) or {}).get("rows") or []
            prom = sum(float(r[4]) for r in rows_ if len(r) >= 5 and r[2] == "promoter")
            inst = sum(float(r[4]) for r in rows_ if len(r) >= 5 and r[2] != "promoter" and str(r[1]).lower() in INSTITUTION_KINDS)
            return round(prom, 2), round(inst, 2)
        now_p, now_i = split(qs[-1])
        before = split(qs[-2]) if len(qs) > 1 else None
        rows.append({"symbol": sym, "name": names.get(sym) or sym, "quarter": qs[-1], "promoter": now_p or None, "institutions": now_i or None,
                     "promoter_change": round(now_p - before[0], 2) if before and now_p and before[0] else None,
                     "institutions_change": round(now_i - before[1], 2) if before and now_i and before[1] else None})
    try:
        buys = src.insider_buys() or {}
    except Exception:
        buys = {}
    cut = (src.today - timedelta(days=90)).isoformat()
    for sym in symbols:
        if str(buys.get(sym) or "") >= cut:
            bought.append({"symbol": sym, "name": names.get(sym) or sym, "at": buys[sym]})
    try:
        flagged = src.red_flags(set(symbols), src.today - timedelta(days=90), src.today) or []
    except Exception as e:
        print("theme data: red flags not read:", type(e).__name__, str(e)[:100])
        flagged = []
    for i in flagged:
        if str(i.get("category") or "") in PLEDGE_CATEGORIES:
            pledges.append({"symbol": i["symbol"], "name": names.get(i["symbol"]) or i.get("company") or i["symbol"], "at": i["at"], "label": i.get("label") or i.get("category"),
                            "url": i.get("url")})
    return {"holdings": rows, "promoter_up": sum(1 for r in rows if (r["promoter_change"] or 0) > 0), "promoter_down": sum(1 for r in rows if (r["promoter_change"] or 0) < 0),
            "promoter_median": stat(r["promoter"] for r in rows), "insider_buys": bought, "pledges": pledges, "red_flags": flagged_rows(flagged, names)}


INSTITUTION_KINDS = {"mutual fund", "insurance company", "provident or pension fund", "alternative investment fund", "foreign portfolio investor",
                     "foreign direct investor", "bank", "bank or financial institution", "other institution", "foreign institution", "sovereign wealth fund"}
PLEDGE_CATEGORIES = {"pledge"}


def flagged_rows(items: list[dict], names: dict) -> list[dict]:
    return [{"symbol": i["symbol"], "name": names.get(i["symbol"]) or i.get("company") or i["symbol"], "at": i["at"], "label": i.get("label") or i.get("category"),
             "severity": i.get("severity"), "subject": i.get("subject") or i.get("title") or "", "url": i.get("url")}
            for i in sorted(items, key=lambda i: (i["at"], i["symbol"]), reverse=True)[:15]]


def events_section(symbols: list[str], names: dict, src) -> dict:
    today = src.today
    due = []
    try:
        for r in sorted(src.results(today, today + timedelta(days=28), set(symbols)), key=lambda r: (r["date"], r["symbol"])):
            if not r.get("out"):
                due.append({"symbol": r["symbol"], "name": names.get(r["symbol"]) or r.get("name") or r["symbol"], "date": r["date"], "purpose": r.get("purpose")})
        filed = []
        for r in sorted(src.results(today - timedelta(days=30), today, set(symbols)), key=lambda r: (r["date"], r["symbol"]), reverse=True):
            if r.get("out"):
                filed.append({"symbol": r["symbol"], "name": names.get(r["symbol"]) or r.get("name") or r["symbol"], "date": r["date"],
                              "numbers": [x for x in (r["out"].get("numbers") or []) if isinstance(x, dict)][:3], "url": r["out"].get("url")})
    except Exception as e:
        print("theme data: results not read:", type(e).__name__, str(e)[:100])
        due, filed = [], []
    actions = []
    try:
        for a in sorted(src.actions(today - timedelta(days=30), today + timedelta(days=60), set(symbols)), key=lambda a: (a.get("ex_date") or "", a["symbol"])):
            actions.append({"symbol": a["symbol"], "name": names.get(a["symbol"]) or a["symbol"], "date": a.get("ex_date"), "kind": a.get("kind"),
                            "label": a.get("label") or "", "text": a.get("text") or ""})
    except Exception as e:
        print("theme data: corporate actions not read:", type(e).__name__, str(e)[:100])
    return {"results_due": due, "results_filed": filed, "actions": actions[:30]}


def management_section(symbols: list[str], names: dict, rows_by: dict, src) -> dict:
    """The stored management report cards of the theme's companies, rolled up: the targets that have been checked against reported years,
    met or missed. A company with no stored card isn't counted."""
    cards, met, missed = [], 0, 0
    for sym in symbols:
        try:
            v = src.card(sym, rows_by.get(sym))
        except Exception as e:
            print("theme data: report card not read:", sym, type(e).__name__, str(e)[:100])
            continue
        if v and (v["met"] or v["missed"]):
            cards.append({"symbol": sym, "name": names.get(sym) or sym, "met": v["met"], "missed": v["missed"]})
            met, missed = met + v["met"], missed + v["missed"]
    return {"companies": cards, "met": met, "missed": missed, "with_card": len(cards)}


# ---------- what a post could say ----------
def notable_items(blocks: list[dict], chain: dict, histories: dict) -> list[dict]:
    """What the data shows that is worth a post, each with its figures: one layer's median EBITDA margin far above (or below) the others',
    and a layer whose aggregate EBITDA margin moved a lot over three years. Empty when nothing is."""
    out = []
    have = [r for r in chain["rows"] if r["ebitda"] is not None and r["ebitda_n"] >= MIN_LAYER]
    if len(have) >= 2:
        hi, lo = max(have, key=lambda r: r["ebitda"]), min(have, key=lambda r: r["ebitda"])
        if hi["ebitda"] - lo["ebitda"] >= NOTABLE_GAP:
            out.append({"kind": "gap", "high": hi["layer"], "high_value": hi["ebitda"], "low": lo["layer"], "low_value": lo["ebitda"],
                        "gap": round(hi["ebitda"] - lo["ebitda"], 1)})
    for layer, h in histories.items():
        if h and len(h["years"]) >= 4 and h["ebitda"][-1] is not None and h["ebitda"][-4] is not None:
            move = h["ebitda"][-1] - h["ebitda"][-4]
            if abs(move) >= NOTABLE_MOVE:
                out.append({"kind": "move", "layer": layer, "from_year": h["years"][-4], "to_year": h["years"][-1], "from": h["ebitda"][-4], "to": h["ebitda"][-1],
                            "move": round(move, 1), "n": h["n"]})
    return out


# ---------- the sources, and the whole dive ----------
class Sources:
    """Where a dive reads its stored figures. Each is a callable, so a test passes its own:
    facts(symbol) -> a company's stored page facts or None; index_rows() -> the screens' index rows (the market, for comparison);
    shareholding(symbol) -> the stored shareholding quarters; insider_buys() -> {symbol: the latest purchase's day};
    results(frm, to, symbols), actions(frm, to, symbols), red_flags(symbols, frm, to) -> stored rows;
    card(symbol, row) -> the management report card checked against the reported years ({met, missed}) or None;
    history(key, point) -> the theme's kept points after adding `point` (a day's median P/E and the like), oldest first."""

    def __init__(self, today: date, facts, index_rows=lambda: [], shareholding=lambda s: None, insider_buys=lambda: {},
                 results=lambda a, b, s: [], actions=lambda a, b, s: [], red_flags=lambda s, a, b: [], card=lambda s, r: None,
                 history=lambda k, p: [p]):
        self.today, self.facts, self.index_rows, self.shareholding, self.insider_buys = today, facts, index_rows, shareholding, insider_buys
        self.results, self.actions, self.red_flags, self.card, self.history = results, actions, red_flags, card, history


def slug(theme: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(theme or "").lower()).strip("-")[:60]


def build(region: str, theme: str, checked: dict, src: Sources) -> dict:
    """The dive for a checked map (see theme_check.check_placements): the tables by layer, the whole chain in one table, the sub-themes'
    companies, and the sections for the theme as a whole. Every figure is from the stored facts; nothing here calls a source."""
    layers_in: Counter = Counter()
    for v in checked.get("value_chain") or []:
        for t in {c["ticker"] for c in v.get("companies") or []}:
            layers_in[t] += 1
    placed: dict[str, dict] = {}
    for grp in (checked.get("value_chain") or []) + (checked.get("sub_themes") or []):
        for c in grp.get("companies") or []:
            placed.setdefault(c["ticker"], c)
    facts = {s: src.facts(s) for s in placed}
    rows = {s: r for s, r in ((s, company_row(region, s, f)) for s, f in facts.items()) if r}
    for s, c in placed.items():
        if s in rows:
            rows[s]["name"] = c.get("name") or rows[s]["name"]
    wide = {s for s, r in rows.items() if is_diversified(r, layers_in[s])}
    names = {s: r["name"] for s, r in rows.items()}
    market = [m for m in (src.index_rows() or []) if isinstance(m, dict)]

    blocks, histories = [], {}
    for v in checked.get("value_chain") or []:
        mine = [rows[c["ticker"]] for c in v.get("companies") or [] if c["ticker"] in rows]
        what = {c["ticker"]: c.get("what") for c in v.get("companies") or []}
        b = layer_block(v.get("layer") or "", [{**r, "what": what.get(r["symbol"]), "company_wide": r["symbol"] in wide} for r in mine], wide)
        b["description"] = v.get("description") or ""
        b["policy"] = v.get("policy")
        blocks.append(b)
        histories[b["layer"]] = layer_history([r for r in mine if r["symbol"] not in wide] or mine)
    chain = chain_table(blocks)
    pool = [r for b in blocks for r in b["companies"] if not r["company_wide"]] or [r for b in blocks for r in b["companies"]]
    allm = stat(r["ebitda"] for r in {r["symbol"]: r for r in pool}.values())
    for b in blocks:
        b["line"] = margin_line(b, allm["median"] if allm else None, several=sum(1 for x in blocks if x["stats"].get("ebitda")) > 1)
        b["history"] = histories.get(b["layer"])
    subs = []
    for s in checked.get("sub_themes") or []:
        cos = []
        for c in s.get("companies") or []:
            r = rows.get(c["ticker"])
            if r:
                cos.append({"symbol": r["symbol"], "name": r["name"], "what": c.get("what"), "cap": r["cap"], "sales_1y": r["sales_1y"], "ebitda": r["ebitda"],
                            "company_wide": r["symbol"] in wide, "year": r["year"]})
        subs.append({"name": s.get("name") or "", "detail": s.get("detail") or "", "companies": cos})
    members = sorted(rows.values(), key=lambda r: -(r.get("cap") or 0))
    syms = [r["symbol"] for r in members]
    own = [r for r in members if r["symbol"] not in wide] or members
    val = valuation_section(members, market)
    point = {"d": src.today.isoformat(), "pe": val["pe"]["median"] if val["pe"] else None, "n": len(members)}
    try:
        val["history"] = [p for p in src.history(slug(theme), point) if p.get("pe") is not None]
    except Exception as e:
        print("theme data: history not kept:", type(e).__name__, str(e)[:100])
        val["history"] = []
    market_med = {k: stat(m.get(k) for m in market) for k in ("opm", "net_margin", "roce", "sales_cagr_3y")} if market else {}
    as_of = max((r["price_at"] for r in members if r.get("price_at")), default=None)
    own_set = {r["symbol"] for r in own}
    out = {
        "region": region, "sector": checked.get("sector") or theme, "as_of": as_of, "unit": next((r["unit"] for r in members if r.get("unit")), None),
        "basis": basis_text(members, region), "layers": blocks, "chain": chain, "subs": subs, "members": len(members), "company_wide": sorted(wide & set(syms)),
        "sections": {
            "size": size_section(members), "medians": {k: stat(r.get(k) for r in own) for k in ("ebitda", "net", "roce")}, "growth": aggregate_growth(own), "margins": margin_history(own), "valuation": val, "quarter": quarter_section(members),
            "balance": balance_section(own), "price": stored_price_section(members), "market": market_med,
            "ownership": ownership_section(syms, names, src), "events": events_section(syms, names, src),
            "management": management_section(syms, names, rows, src), "leaders": leaders(members)},
        "growth_basis_n": len(own_set),
    }
    out["notable"] = notable_items(blocks, chain, histories)
    return out


# ---------- operating figures from business updates ----------
def business_rows(symbols: list[str], names: dict, read) -> list[dict]:
    """The operating figure each company files between results (monthly sales, traffic, output, capacity, deposits...), as `read(symbol)` gives
    it: {metric, unit, span, period, value, prev, year_ago, change_prev, change_year, filed, url, page, exchange, points}. A company with no
    read figure isn't listed. All through one function, so a wider source slots in without changing the page."""
    out = []
    for sym in symbols:
        try:
            r = read(sym)
        except Exception as e:
            print("theme data: business update not read:", sym, type(e).__name__, str(e)[:100])
            continue
        if r and r.get("value") is not None and r.get("period"):
            out.append({**r, "symbol": sym, "name": names.get(sym) or sym})
    return out


def business_section(blocks: list[dict], subs: list[dict], names: dict, read) -> dict:
    """Operating figures by layer and sub-theme, plus how many of the theme's companies have one."""
    every = {}
    for b in blocks:
        b["business"] = business_rows([c["symbol"] for c in b["companies"]], names, read)
        every.update({r["symbol"]: r for r in b["business"]})
    for s in subs:
        s["business"] = business_rows([c["symbol"] for c in s["companies"]], names, read)
        every.update({r["symbol"]: r for r in s["business"]})
    total = len({c["symbol"] for b in blocks for c in b["companies"]} | {c["symbol"] for s in subs for c in s["companies"]})
    return {"layers": [{"layer": b["layer"], "rows": b["business"]} for b in blocks], "subs": [{"name": s["name"], "rows": s["business"]} for s in subs],
            "companies": len(every), "of": total}
