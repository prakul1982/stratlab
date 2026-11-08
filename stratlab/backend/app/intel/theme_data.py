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
from . import sector_metrics

# a company that runs several businesses: its figures are the whole company's, not those of one layer's work
DIVERSIFIED = {"RELIANCE", "ADANIENT", "M&M", "LT", "ITC", "GRASIM", "SIEMENS", "TATASONS", "BAJAJHLDNG", "JSWHL", "AEGISLOG", "GODREJIND",
               "BRK-B", "BRK.B", "GE", "HON", "MMM", "CMI", "DHR"}
_PART_YEAR = re.compile(r"\s\d+m$")
_YEAR = re.compile(r"^([A-Za-z]{3})\s+(\d{4})$")
NOTABLE_GAP = 10.0            # points between the highest and lowest layer median EBITDA margin that make a post worth drafting
NOTABLE_MOVE = 5.0            # points a layer's EBITDA margin moved over three years
MIN_BASE = 3                  # companies a median needs to be shown as one, and a layer to be called highest or lowest (R20: no finding on a base under 3)
FEW_BASE = 4                  # a highest or lowest median on this many companies or fewer says its count
# R25 (owner's outside review): one floor for every comparison of layers in a deck (a highest or lowest median, a fastest or slowest, green
# and red marks): a layer with fewer companies than this behind its median is shown, never ranked; with fewer than two layers over
# it, no comparison is said at all
COMPARE_MIN = MIN_BASE
# R27 (headline eligibility): a comparison is said as a headline only on a figure for at least this share of the companies of each group it
# compares (a layer, a family); one with less is shown as data, never ranked (the live R26 Semis deck: "RPO growth -3.9%" of 21 of 53)
COVERAGE_MIN = 0.5
MIN_LAYER = 2                 # companies a layer needs for its median to be called a layer's figure (a post, the chain's highest and lowest)
ROUNDING = 1.0                # points: EBITDA margins are filed in whole points, so two medians this close may be the same figure rounded
FINANCIAL_KEYS = ("ebitda", "roce", "debt_equity")
# a lender's own measures (R18, the owner: banks' EBITDA margin, ROCE and EV/EBITDA were "–" everywhere): return on equity, net interest income
# and profit over assets, gross and net NPA and price to book, each where the company's stored figures have it
LENDER_KEYS = ("roe", "nii_assets", "roa", "gnpa", "nnpa", "nii_growth", "deposit_growth", "pb")
STAT_KEYS = ("ebitda", "net", "roce") + LENDER_KEYS
# R25 (the live R24 Insurance deck showed "NII / assets" for insurers): a bank's and a lender's own measures, never an insurer's, so a layer of
# insurers has no median of them and its tables no column for them
BANK_ONLY = ("nii_assets", "roa", "gnpa", "nnpa", "nii_growth", "deposit_growth")
# each family's filed figures a value-chain row carries (its layers' medians), shown only where a layer of that family has them
FAMILY_CHAIN = ("cet1", "solvency", "combined_ratio", "sbc_share", "fcf_margin")

# the metric profile of a company's industry family, in one place (R21: an insurer's EBITDA margin and ROCE showed as medians of 1 company):
# banks, other lenders and insurers are read on lenders' measures (ROE, P/B, net margin; their own ratios where stored), never on EBITDA
# margin, ROCE, EV/EBITDA, debt to equity or interest cover; every other company on those
FAMILIES = (("insurer", re.compile(r"\binsur", re.I)),
            ("lender", re.compile(r"\bnbfc\b|non[- ]?bank|housing finance|microfinance|\blending\b|credit institution|business credit|mortgage banker|"
                                  r"financial institution|consumer finance|vehicle finance", re.I)),
            ("bank", re.compile(r"^(?:banks?|private sector bank|public sector bank|other bank|(?:national|state) commercial banks|commercial banks, nec|"
                                r"savings institution.*)$", re.I)))
PROFILES = {"bank": ("roe", "nii_assets", "gnpa", "nnpa", "deposit_growth", "pb", "net"), "lender": ("roe", "nii_assets", "gnpa", "nnpa", "pb", "net"),
            "insurer": ("roe", "pb", "net"), "other": ("ebitda", "net", "roce", "ev_ebitda", "pe")}


def profile_of(f: dict, industry: str = "") -> str:
    """"bank", "lender", "insurer" or "other": from the company's own industry path and the exchange's industry, else its page's flag."""
    names = [str(x).strip() for x in (f.get("industry") or []) if x] + ([industry] if industry else [])
    for fam, rx in FAMILIES:
        if any(rx.search(n) for n in names):
            return fam
    return "lender" if f.get("bank") else "other"


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


def pts(v: float, whole: bool = False) -> str:
    """12.3% (one decimal, a real minus); `whole`, for margins filed in whole points, prints 13% for 13.0 (a median's half stays: 16.5%)."""
    text = f"{f1(v)}%".replace("-", "−")
    return text.replace(".0%", "%") if whole else text


def whole_points(rows) -> bool:
    """Whether every EBITDA margin among these companies is filed in whole points (company_row's ebitda_dp)."""
    have = [r for r in rows if r.get("ebitda") is not None]
    return bool(have) and all(r.get("ebitda_dp") == 0 for r in have)


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


THEME_CURRENCY = {"US": ("USD", "$ million"), "IN": ("INR", "₹ crore")}
_UNIT_CUR = re.compile(r"^([A-Z]{3}) million$")
_RATE_A = re.compile(r"1 ([A-Z]{3}) = ([\d.,]+) USD")
_RATE_B = re.compile(r"1 USD = ([\d.,]+) ([A-Z]{3})")


def report_fx(f: dict, region: str) -> tuple[str, float | None, str | None]:
    """(the currency a company reports in, the theme's currency for one unit of it, the rate's day) (R22: TSMC's NT$ revenue shown as US
    dollars, $3,809 bn). From the page's own record of it (report_currency and fx, or its unit "TWD million" and its currency note's rate);
    1.0 for the theme's own currency, None when no rate is known."""
    home, _ = THEME_CURRENCY.get(region, ("USD", "$ million"))
    m = _UNIT_CUR.match(str(f.get("unit") or ""))
    cur = str(f.get("report_currency") or (m.group(1) if m else "") or home).upper()
    if cur == home:
        return home, 1.0, None
    fx = f.get("fx") if isinstance(f.get("fx"), dict) else {}
    rate, at = num(fx.get("rate")), fx.get("at")
    note = str(f.get("currency_note") or "")
    if not rate and (a := _RATE_A.search(note)) and a.group(1) == cur:
        rate = num(a.group(2).replace(",", ""))
    if not rate and (b := _RATE_B.search(note)) and b.group(2) == cur:
        back = num(b.group(1).replace(",", ""))
        rate = 1 / back if back else None
    if home != "USD":                      # the app keeps dollar rates only: a company reporting in another currency in an Indian theme has none
        return cur, None, None
    return cur, rate, (str(at)[:10] if at else (str(f.get("built_at") or "")[:10] or None))


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
    profile = profile_of(f)
    lender = profile != "other"
    # every money figure in the theme's one currency (R22): a company reporting in another is converted at the rate its page states; with no
    # rate its money figures are left out (margins, growth and returns don't depend on the currency and stay)
    cur, k, fx_at = report_fx(f, region)
    money = (lambda v: None if v is None or k is None else v * k)      # noqa: E731
    sales = money(num(last.get("sales"))) if last else None
    profit = money(num(last.get("profit"))) if last else None
    net = (profit / sales * 100) if sales and sales > 0 and profit is not None else None
    ebitda = num(last.get("opm")) if last and not lender else None
    cfo = money(num(last.get("cfo"))) if last else None
    if k is None and last:                 # no rate: its margin from its own figures, its money figures out
        s_, p_ = num(last.get("sales")), num(last.get("profit"))
        net = (p_ / s_ * 100) if s_ and s_ > 0 and p_ is not None else None
    cap, debt, cash = base.get("market_cap"), money(num(f.get("debt"))), money(num(f.get("cash")))
    ebitda_amt = sales * ebitda / 100 if sales and ebitda is not None and sales > 0 else None
    # enterprise value over EBITDA: market value plus debt less cash, over the year's EBITDA; n/a where any of the four is missing, or EBITDA isn't positive
    ev = (cap + debt - cash) / ebitda_amt if None not in (cap, debt, cash) and ebitda_amt and ebitda_amt > 0 and not wild and not lender else None
    yoy = f.get("latest_yoy") if isinstance(f.get("latest_yoy"), dict) and f["latest_yoy"].get("basis") == "quarter" else None
    opms = [num(y.get("opm")) for y in years if num(y.get("opm")) is not None]
    shown_e = None if wild or ebitda is None or abs(ebitda) > stock_pages.EXTREME else r1(ebitda)
    shown_n = None if wild or net is None or abs(net) > stock_pages.EXTREME else r1(net)
    return validate_row({
        "symbol": symbol, "name": base["name"], "year": last["year"] if last else None, "bank": lender, "profile": profile, "sector": base.get("sector"),
        "unit": THEME_CURRENCY.get(region, ("", f.get("unit")))[1] if cur != THEME_CURRENCY.get(region, ("USD",))[0] else f.get("unit"),
        "currency": cur, "fx": {"rate": k, "at": fx_at} if cur != THEME_CURRENCY.get(region, ("USD",))[0] else None,
        "revenue": sales if sales and sales > 0 else None, "profit": profit,
        "ebitda": shown_e, "net": shown_n,
        # net margin above the EBITDA margin: profit beyond what the business earned before depreciation, interest and tax, so a one-off
        # gain (a demerger, an asset sale) is in it (the owner, 7 Nov: Tata Motors PV's 24.6% net on a 6% EBITDA margin)
        "one_off": one_off(shown_e, shown_n),
        # the page files the EBITDA margin in whole points (13, never 13.04): printed as 13%, not 13.0% (false precision)
        "ebitda_dp": 0 if opms and all(float(x).is_integer() for x in opms) else 1,
        "roce": None if lender or old else r1(num(f.get("roce"))),
        "cap": cap, "pe": base.get("pe"), "pb": None if old else r1(num(f.get("pb"))),
        "roe": None if old or wild else r1(num(f.get("roe"))),
        **{k: (None if old else num((f.get("lender") or {}).get(k))) for k in ("nii_assets", "roa", "gnpa", "nnpa", "nii_growth", "deposit_growth")},
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
        "years": [{"year": y["year"], "sales": money(num(y.get("sales"))), "profit": money(num(y.get("profit"))), "opm": None if lender else num(y.get("opm"))}
                  for y in years],
        # R30: capital (book equity and debt) for each unit of revenue, how asset-heavy the business is (a layer-vs-layer headline needs it comparable)
        "capital_rev": None if lender else capital_per_revenue(cap, num(f.get("pb")), debt, base.get("debt_equity"), sales),
    }, f, last)


def capital_per_revenue(cap, pb, debt, de, sales) -> float | None:
    """Capital (book equity plus debt) over the year's revenue: book equity is the market value over the price-to-book (else debt over debt to
    equity); None when neither gives a positive equity or there is no revenue (R30)."""
    debt = num(debt)
    eq = cap / pb if cap and pb and pb > 0 else (debt / de if debt and num(de) and de > 0 else None)
    if not eq or eq <= 0 or not sales or sales <= 0:
        return None
    return round((eq + (debt or 0)) / sales, 2)


# ---------- R30: each figure checked before it is used (the owner's review of the live R28 Telecom deck: "77% net, 42% EBITDA") ----------
# A figure that fails a check is shown as "–", kept with its check in `held`, and left out of every median and ranking; the data-confidence page
# names the company, the figure and the check, never a cause.
NET_UNUSUAL = 60.0            # a net margin beyond ±60% of revenue
EBITDA_UNUSUAL = 90.0         # an EBITDA margin above 90%, outside the models that earn fees or royalties with few costs (EBITDA_FREE)
EBITDA_FREE = {"royalties", "financial_fees", "lending", "underwriting", "life_insurance", "general_insurance", "reinsurance", "property"}
OTHER_INCOME_SHARE = 0.5      # income outside operations above half the year's net profit, where the source carries it
CHECKS = {"sign": "net profit positive, return on capital negative", "sign_page": "net margin and net profit of opposite signs",
          "other_income": "income outside operations above half the net profit", "net_unusual": f"net margin beyond ±{NET_UNUSUAL:.0f}%",
          "ebitda_unusual": f"EBITDA margin above {EBITDA_UNUSUAL:.0f}%", "neg_equity": "return on equity with negative equity",
          "neg_book": "price to book with negative equity"}


def hold(r: dict, key: str, check: str) -> None:
    """Take a figure out of the row (shown "–", out of every median and ranking), kept with the check(s) it failed."""
    h = r.setdefault("held", {})
    if key in h:
        h[key]["checks"].append(CHECKS[check])
        return
    if r.get(key) is None:
        return
    h[key] = {"value": r[key], "checks": [CHECKS[check]]}
    r[key] = None
    if key == "net":
        r["one_off"] = False


def validate_row(r: dict, f: dict, last: dict | None) -> dict:
    """The checks a company's figures pass before they are used (R30): sign consistency (a positive net profit beside a negative return on
    capital; the net margin's sign against the page's own), income outside operations above half the net profit when the source carries it,
    a return on equity or price to book on negative equity, and a net margin beyond ±NET_UNUSUAL%. (An EBITDA margin above EBITDA_UNUSUAL% is
    checked with the company's model: validate_model.)"""
    prof, net = r.get("profit"), r.get("net")
    if net is not None and prof is not None and prof > 0 and (r.get("roce") or 0) < 0:
        hold(r, "net", "sign")
    page = num(f.get("net_margin"))
    if net is not None and page is not None and page * net < 0:
        hold(r, "net", "sign_page")
    oi, p_ = num((last or {}).get("other_income")), num((last or {}).get("profit"))
    if oi is not None and p_ is not None and p_ > 0 and oi > p_ * OTHER_INCOME_SHARE:
        hold(r, "net", "other_income")
    if net is not None and abs(net) > NET_UNUSUAL:
        hold(r, "net", "net_unusual")
    bv = num(f.get("book_value"))
    if bv is not None and bv < 0 or f.get("net_worth_negative"):
        hold(r, "roe", "neg_equity")
        hold(r, "pb", "neg_book")
    return r


def validate_model(r: dict, family: str) -> None:
    """An EBITDA margin above EBITDA_UNUSUAL% outside the models whose costs are few (EBITDA_FREE) is held (R30)."""
    if r.get("ebitda") is not None and r["ebitda"] > EBITDA_UNUSUAL and family not in EBITDA_FREE:
        hold(r, "ebitda", "ebitda_unusual")
        r["one_off"] = False


def held_rows(rows: list[dict]) -> list[dict]:
    """Every figure held by a check, for the data-confidence page: company, figure, value and the checks it failed."""
    return [{"symbol": r["symbol"], "name": r["name"], "key": k, "value": h["value"], "checks": h["checks"]}
            for r in rows if r.get("status") != "unverified" for k, h in (r.get("held") or {}).items()]


def has_figures(r: dict) -> bool:
    """Whether a company's key figures exist: its latest year's revenue or profit (R20)."""
    return r.get("revenue") is not None or r.get("profit") is not None


def one_off(ebitda, net) -> bool:
    """Whether a year's net margin is above its EBITDA margin (both shown, the net positive): only a gain outside the business does that."""
    return ebitda is not None and net is not None and net > 0 and net > ebitda


MAIN_SEGMENT = 66.0           # a company whose largest business segment brings in less than this share of revenue runs several businesses


def is_diversified(row: dict, segments: list | None = None) -> bool:
    """Whether a company's figures are the whole company's, not one layer's, from its own data: the segments its documents report (no one
    segment brings in MAIN_SEGMENT% of revenue), else the exchange filing it as diversified or a conglomerate. Only a company with no segments
    read falls back to the groups known to run several businesses (DIVERSIFIED). A company placed in two layers is not diversified for that:
    it is kept in its first layer only (one layer per company)."""
    ind = " ".join(row.get("industry") or []).lower()
    if "diversified" in ind or "conglomerate" in ind:
        return True
    shares = [num(x.get("share_pct")) for x in segments or [] if isinstance(x, dict)]
    shares = [x for x in shares if x is not None and x > 0]
    if len(shares) >= 2:
        return max(shares) < MAIN_SEGMENT
    return row["symbol"] in DIVERSIFIED


def basis_text(rows: list[dict], region: str) -> str:
    unit = next((r.get("unit") for r in rows if r.get("unit")), None) or ("₹ crore" if region == "IN" else "$ million")
    fy = "financial year ended March" if region == "IN" else "fiscal year"
    return (f"Each company's latest full {fy}, in {unit}. Revenue, EBITDA margin (operating profit before depreciation as a share of revenue) "
            "and net margin (net profit as a share of revenue) are that year's; return on capital employed (ROCE) is the latest reported. "
            "Consolidated accounts where the company files them. Banks and lenders have no EBITDA margin or ROCE.")


# ---------- layers and sub-themes ----------
def model_fields(layer: dict, sym: str) -> dict:
    """A company's revenue model as its layer holds it (R27, theme_base.by_model): "model" (a theme_check.MODELS id, "" unknown), "model_tags"
    (its secondary ways of earning), "model_confidence" (high, medium, low; "" unknown), and "model_out" when it is left out of the layer's
    figures and rankings. {} for a map whose layers carry no models."""
    c = next((c for c in layer.get("companies") or [] if c.get("ticker") == sym), None) or {}
    if "model" not in c:
        return {}
    return {"model": c.get("model") or "", "model_tags": list(c.get("model_tags") or []), "model_confidence": c.get("model_confidence") or "",
            **({"model_out": True} if c.get("model_out") else {})}


def layer_block(name: str, rows: list[dict], wide: set[str]) -> dict:
    """A layer's table and its median and range for each figure. A company-wide figure (a group that runs other businesses too) is
    marked and left out of the median when the layer has any company that is its own; the layer says how many were left out. A company
    whose membership isn't confirmed (status "unverified") is listed but left out of the medians and the revenue total; a net margin with a
    one-off gain in it is left out of the net margin's median (`net_all` keeps the median with it). R27: a company whose revenue model is
    unknown or of low confidence in a layer that has models (`model_out`, theme_base.by_model) is listed but left out of the layer's figures
    the same way (`model_out`: their symbols)."""
    sure = [r for r in rows if r.get("status") != "unverified" and not r.get("model_out")]
    own = [r for r in sure if r["symbol"] not in wide]
    pool = own or sure
    mark_bases(pool)
    stats = {k: stat(r.get(k) for r in pool if not (k == "net" and r.get("one_off")) and not (k == "pb" and (r.get(k) or 0) <= 0)
                     and not (k in BANK_ONLY and r.get("profile") == "insurer")) for k in STAT_KEYS}
    stats.update({k: stat(r.get(k) for r in pool) for k in sector_metrics.KEYS if any(r.get(k) is not None for r in pool)})    # R23: filed sector figures
    return {"layer": name, "companies": rows, "stats": stats, "n": len(sure), "listed": len(rows),
            "net_all": stat(r.get("net") for r in pool), "one_off": sorted(r["symbol"] for r in pool if r.get("one_off")),
            "revenue": sum(r["revenue"] for r in sure if r.get("revenue")) or None,
            "company_wide": sorted(r["symbol"] for r in sure if r["symbol"] in wide),
            "unverified": sorted(r["symbol"] for r in rows if r.get("status") == "unverified"),
            "model_out": sorted(r["symbol"] for r in rows if r.get("model_out") and r.get("status") != "unverified"),
            "stats_over": "all" if not own and sure else "own", "left_out": len(sure) - len(pool),
            # R30: the median company's capital for each unit of revenue (capital_per_revenue), for headline comparability
            "intensity": (stat(r.get("capital_rev") for r in pool) or {}).get("median")}


# R27: a figure whose filed value (sector_metrics.REPLACES) is on another basis than the stored pages' own (NII / assets: the filed half year
# annualised against the latest full year's accounts): where a layer has filed values, a company with only the page's own is "not comparable"
SPLIT_BASIS = ("nii_assets",)


def mark_bases(pool: list[dict]) -> None:
    """Mark each company's figure that is on another basis than its layer's (SPLIT_BASIS): moved to `nc_values`, named in `nc`, out of the median."""
    for k in SPLIT_BASIS:
        if not any(k in (r.get("filed_basis") or ()) and r.get(k) is not None for r in pool):
            continue
        for r in pool:
            if r.get(k) is not None and k not in (r.get("filed_basis") or ()):
                r.setdefault("nc_values", {})[k] = r[k]
                r[k] = None
                r["nc"] = sorted(set(r.get("nc") or ()) | {k})


def margin_line(block: dict, chain_median: float | None, several: bool = True, whole: bool = False) -> str | None:
    """What a layer's table doesn't say by itself: which figures are the whole company's. (The median and range are rows of the table, not said
    again.) None when there is nothing more to say. R27: no sentence quotes the whole map's median EBITDA margin, a figure no table shows (the
    deck check dropped it on every new structure); the value chain's table sets the layers side by side. `chain_median`, `several` and `whole`
    are kept for the callers."""
    parts = []
    if block["left_out"]:
        parts.append(f"{block['left_out']} figure{'s are' if block['left_out'] > 1 else ' is'} the whole company's (it runs other businesses too) "
                     "and left out of the medians.")
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
                     "roce": c["median"] if c else None, "ebitda_n": e["n"] if e else 0, "official": bool(b.get("official")), "rest": b.get("basis") == "rest",
                     **{k: (b["stats"].get(k) or {}).get("median") for k in LENDER_KEYS}, "roe_n": (b["stats"].get("roe") or {}).get("n", 0),
                     **{f"{k}_n": (b["stats"].get(k) or {}).get("n", 0) for k in STAT_KEYS if k not in ("ebitda", "roe")},
                     **{k: (b["stats"].get(k) or {}).get("median") for k in FAMILY_CHAIN}, **{f"{k}_n": (b["stats"].get(k) or {}).get("n", 0) for k in FAMILY_CHAIN},
                     "model": b.get("model"), "intensity": b.get("intensity"), "basis": period_basis([c for c in b.get("companies") or [] if c.get("status") != "unverified"])})
    # only the map's own layers (an official industry's leftover companies overlap them: "Vehicle assembly" and "Commercial Vehicles"), each
    # with MIN_BASE companies in its median, and only a gap wider than the rounding of whole-point margins, name a highest and a lowest
    # the "Other ..." group (companies that fit none of the map's layers) is never compared (R22)
    # R27: and each a headline figure (headline_ok: the sample, a figure for at least half the layer's companies, one business model), all on one
    # period basis; a layer that fails is shown in the table, never named
    ok = lambda r, k: r[k] is not None and headline_ok(r[f"{k}_n"], r["n"], r["model"])      # noqa: E731
    have = [r for r in rows if ok(r, "ebitda") and not r["official"]]
    if len(have) < 2:          # a map whose layers are the official industries themselves: they are its layers (R17-011)
        have = [r for r in rows if ok(r, "ebitda") and not r["rest"]]
    if not same_basis([r["basis"] for r in have]):
        have = []
    have = one_family(have, lambda r: model_family_of(r["model"]))          # R29: layers of one business-model family only
    line, hi, lo = None, None, None
    apart = have if len(have) >= 2 and not comparable_intensity(have, lambda r: r["intensity"]) else []
    if apart:
        # R30 (the owner's review of the live R28 Utilities deck: "renewable producers 83% vs cables 10%"): layers that need very different
        # capital for each unit of revenue are described, each with its own figure, never ranked
        whole = whole_points([c for b in blocks for c in b["companies"]])
        each = [f"{r['layer']} {pts(r['ebitda'], whole)}" + (f" ({w[2:]})" if (w := few(r["ebitda_n"], r["n"])) else "") for r in apart]
        line = ("Median EBITDA margin by layer: " + "; ".join(each)
                + f". Capital for each unit of revenue differs more than {INTENSITY_WORD} between these layers, so they are not ranked.")
        return {"rows": rows, "line": line, "highest": None, "lowest": None, "measure": "ebitda", "compared": [], "gap": None,
                "not_ranked": [r["layer"] for r in apart]}
    if len(have) >= 2:
        hi, lo = max(have, key=lambda r: r["ebitda"]), min(have, key=lambda r: r["ebitda"])
        if hi["layer"] == lo["layer"] or hi["ebitda"] - lo["ebitda"] <= ROUNDING:
            gap = gap_of(max(r["ebitda"] for r in have), min(r["ebitda"] for r in have))         # as printed (R25)
            hi = lo = None
            # R27: a tie (no gap as printed) is no comparison: no sentence, never "within 0.0 points"
            line = (f"The median EBITDA margins of the {len(have)} layers with at least {COMPARE_MIN} companies are within {gap} "
                    "points of each other, the rounding of whole points.") if float(gap) > 0 else None
        else:
            whole = whole_points([c for b in blocks for c in b["companies"]])
            line = (f"Median EBITDA margin is highest in {hi['layer']} ({pts(hi['ebitda'], whole)}{few(hi['ebitda_n'], hi['n'])}) and lowest in {lo['layer']} "
                    f"({pts(lo['ebitda'], whole)}{few(lo['ebitda_n'], lo['n'])}), "
                    f"a gap of {gap_of(hi['ebitda'], lo['ebitda'])} points.")
    measure = "ebitda"
    if len(have) < 2:
        # lenders have no EBITDA margin: their layers are set side by side on return on equity (R18)
        lend = [r for r in rows if ok(r, "roe") and not r["official"]]
        if len(lend) < 2:
            lend = [r for r in rows if ok(r, "roe") and not r["rest"]]
        if not same_basis([r["basis"] for r in lend]):
            lend = []
        lend = one_family(lend, lambda r: model_family_of(r["model"]))
        if not comparable_intensity(lend, lambda r: r["intensity"]):
            lend = []
        if len(lend) >= 2:
            measure, have = "roe", lend
            hi, lo = max(lend, key=lambda r: r["roe"]), min(lend, key=lambda r: r["roe"])
            if hi["layer"] == lo["layer"] or hi["roe"] - lo["roe"] < 0.05:
                hi = lo = None
                line = f"The median return on equity of the {len(lend)} layers with at least {COMPARE_MIN} companies is the same."
            else:
                line = (f"Median return on equity is highest in {hi['layer']} ({pts(hi['roe'], True)}{few(hi['roe_n'], hi['n'])}) and lowest in {lo['layer']} "
                        f"({pts(lo['roe'], True)}{few(lo['roe_n'], lo['n'])}), "
                        f"a gap of {gap_of(hi['roe'], lo['roe'])} points.").replace(".0 points", " points")
        else:
            line = None             # nothing to set side by side: no line at all (R18: the deck said it couldn't be done)
    if line and hi and any(r["rest"] for r in rows):
        line = line.rstrip(".") + "; among the map's layers, the \"Other\" group left out."
    return {"rows": rows, "line": line, "highest": hi["layer"] if hi else None, "lowest": lo["layer"] if lo else None, "measure": measure,
            "compared": [r["layer"] for r in have], "gap": round(hi[measure] - lo[measure], 1) if hi else None}


def gap_of(a: float, b: float) -> str:
    """The gap between two figures as they are printed, to one decimal (R25: a gap said beside its two figures is their difference)."""
    return f1(float(f1(a)) - float(f1(b)))


def few(n: int, of: int | None = None) -> str:
    """", 3 companies" after a layer's median when it rests on FEW_BASE companies or fewer (R22: a 50% median of 3 called highest); ", 3 of 5
    companies" when the layer has more companies than its median is of (R25: one way of counting in tables, charts and headlines)."""
    if of and n and n < of:
        return f", {n} of {of} companies"
    return f", {n} companies" if n and n <= FEW_BASE else ""


def of_words(n: int, of: int | None, one: str = "company", many: str = "companies") -> str:
    """"3 companies", or "3 of 5 companies" when the figure is of fewer companies than the group has (R25)."""
    if of and n < of:
        return f"{n} of {of} {many}"
    return f"{n} {one if n == 1 else many}"


def headline_ok(n: int, of: int | None = None, model: dict | None = None, floor: int | None = None) -> bool:
    """Whether one group's figure may be ranked in a headline (R27): its sample is at least `floor` companies (COMPARE_MIN), it covers at least
    COVERAGE_MIN of the group's `of` companies, and the group is of one business model (theme_base.by_model's `model`: a layer whose companies'
    models are mostly unknown, "sparse", is not; no model read at all says nothing either way). A failing group is shown, never ranked."""
    if (n or 0) < (COMPARE_MIN if floor is None else floor):
        return False
    if of and n < of * COVERAGE_MIN:
        return False
    return not (isinstance(model, dict) and model.get("sparse"))


def period_basis(rows: list[dict]) -> str:
    """The period basis of a group's annual figures: "full" (full years), "part" (a part year, "Mar 2026 9m"), "mixed" or "" (none)."""
    kinds = {"part" if _PART_YEAR.search(str(r.get("year"))) else "full" for r in rows if r.get("year")}
    return "" if not kinds else kinds.pop() if len(kinds) == 1 else "mixed"


def same_basis(groups: list) -> bool:
    """Whether the groups a comparison sets side by side are on one period basis (R27): each "full" or each "part", never a mix."""
    kinds = {g for g in groups if g}
    return len(kinds) <= 1 and "mixed" not in kinds


def one_family(rows: list, family) -> list:
    """The rows that may be set side by side in a headline (R29, the owner's review: no headline compares layers of different business-model
    families, a regulated network beside a generator or a miner beside a fabricator): those of the family most of them have (`family(row)`,
    theme_base.by_model's), a row of no family left out; every row when none has a family; [] when the most common family is tied."""
    from collections import Counter
    fams = [family(r) or "" for r in rows]
    c = Counter(f for f in fams if f).most_common()
    if not c:
        return list(rows)
    if len(c) > 1 and c[0][1] == c[1][1]:
        return []
    return [r for r, f in zip(rows, fams) if f == c[0][0]]


INTENSITY_FACTOR = 3.0        # R30: two layers whose median capital for each unit of revenue differs more than threefold are not ranked
INTENSITY_WORD = "threefold"


def comparable_intensity(rows: list, intensity) -> bool:
    """Whether the rows a headline would rank are alike in asset intensity (R30): the highest median capital for each unit of revenue
    (`intensity(row)`, capital_per_revenue's) at most INTENSITY_FACTOR times the lowest. Rows with no figure say nothing either way; True when
    fewer than two have one."""
    xs = [x for x in (intensity(r) for r in rows) if x is not None and x > 0]
    return len(xs) < 2 or max(xs) <= min(xs) * INTENSITY_FACTOR


def model_family_of(model) -> str:
    return (model or {}).get("family") or "" if isinstance(model, dict) else ""


def rank_pair(rows: list, value, count, floor: int = COMPARE_MIN, of=None, model=None, basis=None, intensity=None):
    """(highest, lowest) of `rows` by `value(row)` among those whose figure is of at least `floor` companies (`count(row)`) (R25: one floor for
    every comparison of layers) and, given `of`, `model` and `basis` (each a function of the row), passes headline_ok and shares one period
    basis (R27), and given `intensity`, are alike in asset intensity (R30); None when fewer than two qualify, or when the highest or the lowest is tied (no layer is named for a tie)."""
    have = sorted((r for r in rows if value(r) is not None and headline_ok(count(r) or 0, of(r) if of else None, model(r) if model else None, floor)),
                  key=value)
    if model:                       # R29: one business-model family only
        have = one_family(have, lambda r: model_family_of(model(r)))
    if basis and not same_basis([basis(r) for r in have]):
        return None
    if intensity and not comparable_intensity(have, intensity):         # R30: alike in asset intensity
        return None
    if len(have) < 2 or value(have[-1]) == value(have[-2]) or value(have[0]) == value(have[1]):
        return None
    return have[-1], have[0]


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

    def year_of(r, lb):
        return next(y for y in r["years"] if y["year"] == lb)
    # a company with a one-off gain in any year of the span (net margin above its EBITDA margin) is left out of the net line, so the theme's
    # net margin never tops its EBITDA margin on a demerger gain (the owner, 7 Nov: 12.0% net on 11.8% EBITDA in Mar 2026)
    clean = [r for r in keep if not any(one_off(year_of(r, lb)["opm"], year_of(r, lb)["profit"] / year_of(r, lb)["sales"] * 100
                                                if year_of(r, lb)["profit"] is not None else None) for lb in span)]
    ebitda, net = [], []
    for lb in span:
        ys = [year_of(r, lb) for r in keep]
        s = sum(y["sales"] for y in ys)
        ebitda.append(round(sum(y["sales"] * y["opm"] for y in ys) / s, 1) if s else None)
        ns = [year_of(r, lb) for r in clean]
        sn = sum(y["sales"] for y in ns)
        net.append(round(sum(y["profit"] for y in ns) / sn * 100, 1) if sn and all(y["profit"] is not None for y in ns) else None)
    return {"years": span, "ebitda": ebitda, "net": net, "n": len(keep), "net_n": len(clean), "companies": [r["symbol"] for r in keep],
            "one_off": sorted(r["symbol"] for r in keep if r not in clean)}


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


def margin_drivers(hist: dict | None, rows: dict, layer_of: dict) -> dict | None:
    """What moved the aggregate EBITDA margin between the last two years of `hist` (margin_history: the same companies every year): each
    company's part of the change, (its EBITDA ÷ everyone's revenue) this year less the same a year before, in points, so the parts add up to
    the change; the companies that moved it most and each layer's part (R17-015). Arithmetic on reported figures only."""
    if not hist or len(hist.get("years") or []) < 2:
        return None
    y0, y1 = hist["years"][-2], hist["years"][-1]

    def year(sym, lb):
        return next((y for y in rows[sym].get("years") or [] if y.get("year") == lb), None)
    have = [s_ for s_ in hist.get("companies") or [] if s_ in rows and year(s_, y0) and year(s_, y1)]
    r0 = sum(year(s_, y0)["sales"] for s_ in have)
    r1 = sum(year(s_, y1)["sales"] for s_ in have)
    if not have or not r0 or not r1:
        return None
    parts = []
    for s_ in have:
        a, b = year(s_, y0), year(s_, y1)
        part = (b["sales"] * b["opm"] / r1 - a["sales"] * a["opm"] / r0)
        parts.append({"symbol": s_, "name": rows[s_]["name"], "layer": layer_of.get(s_), "part": round(part, 2),
                      "margin_from": a["opm"], "margin_to": b["opm"], "share_from": round(a["sales"] / r0 * 100, 1), "share_to": round(b["sales"] / r1 * 100, 1)})
    start = sum(year(s_, y0)["sales"] * year(s_, y0)["opm"] for s_ in have) / r0
    end = sum(year(s_, y1)["sales"] * year(s_, y1)["opm"] for s_ in have) / r1
    by_layer: dict = {}
    for x in parts:
        by_layer[x["layer"] or "Other"] = by_layer.get(x["layer"] or "Other", 0.0) + x["part"]
    return {"from": y0, "to": y1, "start": round(start, 1), "end": round(end, 1), "change": round(end - start, 1), "n": len(have),
            "companies": sorted(parts, key=lambda x: -abs(x["part"]))[:6],
            "layers": sorted(({"layer": k, "part": round(v, 2)} for k, v in by_layer.items()), key=lambda x: -abs(x["part"]))}


PEER_BAND = 2.0               # companies of similar market value: between half and twice a company's own
PEER_MIN = 10                 # comparable peers a company needs for its relative comparison; with fewer it has none (R27: no whole-market set)
PEER_SETS = {"sector": "own sector, similar market value, outside the theme", "sector_theme": "own sector, similar market value, the theme's other companies counted",
             "none": "no comparable peer set"}


def comparable_peers(r: dict, market: list[dict], theme: set) -> tuple[list[dict], str]:
    """(a company's comparable peers, which set they are), in the order comparability is judged (R27, the owner's outside review): the business
    first (its own sector, the same kind of accounts: a lender beside lenders), then size (half to twice its market value), then geography and
    accounting basis (the same market and currency of filing, the market list being the theme's own market). Outside the theme where PEER_MIN
    are, else the theme's other companies of that sector counted ("sector_theme"). Never the whole market: with fewer than PEER_MIN the
    company has "none", and its relative comparison is left out."""
    cap, sector = num(r.get("cap")), r.get("sector")
    if not cap or not sector:
        return [], "none"
    same = [m for m in market if m.get("sector") == sector and m.get("symbol") != r.get("symbol")
            and ("bank" not in m or bool(m["bank"]) == bool(r.get("bank"))) and (not m.get("region") or not r.get("region") or m.get("region") == r.get("region"))]
    band = [m for m in same if num(m.get("market_cap")) and cap / PEER_BAND <= num(m.get("market_cap")) <= cap * PEER_BAND]
    out_ = [m for m in band if m.get("symbol") not in theme]
    if len(out_) >= PEER_MIN:
        return out_, "sector"
    return (band, "sector_theme") if len(band) >= PEER_MIN else ([], "none")


def _peer_median(r: dict, market: list[dict], key: str, ok, theme: set) -> tuple[float | None, str]:
    """(the median of `key` over a company's comparable peers that have it, the set's name); (None, "none") with fewer than PEER_MIN."""
    peers, basis = comparable_peers(r, market, theme)
    xs = [x for x in (num(m.get(key)) for m in peers) if x is not None and ok(x)]
    return (median(xs), basis) if basis != "none" and len(xs) >= PEER_MIN else (None, "none")


def peers_section(rows: list[dict], market: list[dict]) -> dict:
    """Each company against its comparable peers (comparable_peers: its own sector first, then similar market value, the same market and
    accounts): its P/E, its revenue growth over three years and its ROCE beside their medians, and the theme's median company of each (the
    owner, 7 Nov: "valuation premium vs same-size peers beside growth and ROCE"). `sets` counts the companies compared with each set, and
    "none" those with the figure but no comparable peer set (R27: left out, never set against the whole market). Facts: a comparison, never
    a view of what is cheap."""
    theme = {r["symbol"] for r in rows}
    out = {}
    for key, mkey, ok in (("pe", "pe", lambda x: 0 < x <= stock_pages.PE_MAX), ("sales_3y", "sales_cagr_3y", lambda x: True), ("roce", "roce", lambda x: True)):
        own, peer, prem, sets = [], [], [], {}
        for r in rows:
            v = num(r.get(key))
            if v is None or not ok(v):
                continue
            pm, basis = _peer_median(r, market, mkey, ok, theme)
            sets[basis] = sets.get(basis, 0) + 1
            if pm is None:
                continue
            own.append(v)
            peer.append(pm)
            if key == "pe" and pm > 0:
                prem.append((v / pm - 1) * 100)
        if own:
            # the P/E gap is the ratio of the two medians over the same companies, the two numbers a table shows (R17-010: the median of each
            # company's own gap, 8.2%, sat beside medians 3.4% apart)
            mo, mp = median(own), median(peer)
            out[key] = {"n": len(own), "theme": round(mo, 1), "peers": round(mp, 1), "sets": sets, "none": sets.get("none", 0),
                        "premium": round((round(mo, 1) / round(mp, 1) - 1) * 100, 1) if prem and round(mp, 1) > 0 else None}
        elif sets.get("none"):
            out[key] = {"n": 0, "theme": None, "peers": None, "sets": sets, "none": sets["none"], "premium": None}
    return out


def valuation_section(rows: list[dict], market: list[dict]) -> dict:
    """The theme's median P/E, P/B and EV/EBITDA, each over the companies that have one (a loss-maker has no P/E and is left out, and the
    count says so), beside companies of similar market value (peers_section) and the whole market's median."""
    pe = stat(r["pe"] for r in rows if r.get("pe"))
    mkt = stat(m.get("pe") for m in market if m.get("pe") and 0 < m["pe"] <= stock_pages.PE_MAX)
    pb = stat(r["pb"] for r in rows if r.get("pb") is not None and r["pb"] > 0)
    mpb = stat(m.get("pb") for m in market if m.get("pb") and m["pb"] > 0)
    ev = stat(r["ev_ebitda"] for r in rows)
    losses = sum(1 for r in rows if r.get("profit") is not None and r["profit"] <= 0)
    return {"pe": pe, "market_pe": mkt, "market_n": mkt["n"] if mkt else 0, "pb": pb, "market_pb": mpb, "ev_ebitda": ev,
            "ev_missing": sum(1 for r in rows if r.get("ev_ebitda") is None and not r.get("bank")), "losses": losses, "peers": peers_section(rows, market),
            "n": len(rows)}                 # the population every count here is of (R22: 11 with a P/E and 6 loss-makers of 15)


def relative_ok(val: dict) -> bool:
    """Whether a theme's valuation may be relative (R29, the owner's review of the live R27 Telecom deck: 24 companies with a P/E, none with a
    comparable peer set): comparable peers cover at least half of the companies with a P/E. Otherwise the valuation is descriptive (the
    theme's own medians and spread, by layer and over time), never set against peers or the whole market."""
    pe_n = (val.get("pe") or {}).get("n") or 0
    with_peers = (((val.get("peers") or {}).get("pe") or {}).get("n")) or 0
    return bool(pe_n) and with_peers * 2 >= pe_n


def layer_valuation(blocks: list[dict], counted: set) -> list[dict]:
    """Each layer's own median P/E, P/B and EV/EBITDA with their counts and ranges (R29: the descriptive valuation), over its confirmed
    companies with figures that are in its figures (never one whose model is left out, `model_out`); a layer with none of the three is left out."""
    out = []
    for b in blocks:
        out_ = set(b.get("model_out") or [])
        cos = [c for c in b.get("companies") or [] if c.get("symbol") in counted and c["symbol"] not in out_]
        st = {"pe": stat(c.get("pe") for c in cos if c.get("pe")), "pb": stat(c.get("pb") for c in cos if c.get("pb") is not None and c["pb"] > 0),
              "ev_ebitda": stat(c.get("ev_ebitda") for c in cos)}
        if any(st.values()):
            out.append({"layer": b.get("layer") or "", "n": len(cos), "official": bool(b.get("official")), **st})
    return out


def balance_section(rows: list[dict]) -> dict:
    de = stat(r["debt_equity"] for r in rows)
    own = [r for r in rows if r.get("debt_equity") is not None]
    cfo = [r["cfo_to_profit"] for r in rows if r.get("cfo_to_profit") is not None]
    return {"debt_equity": de, "above_1": sum(1 for r in own if r["debt_equity"] > 1), "with_debt_equity": len(own),
            "cfo_to_profit": stat(cfo), "cfo_n": len(cfo), "interest_cover": stat(r.get("interest_cover") for r in rows),
            "cover_under_2": sum(1 for r in rows if r.get("interest_cover") is not None and r["interest_cover"] < 2)}


_MON = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def quarter_end(label) -> date | None:
    """The last day of the quarter a label like "Sep 2026 vs Sep 2025" or "Sep 2026" names, or None."""
    m = re.match(r"\s*([A-Za-z]{3})\w*\s+(\d{4})", str(label or ""))
    if not m or m.group(1).title() not in _MON:
        return None
    y, mo = int(m.group(2)), _MON[m.group(1).title()]
    return (date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1))


def quarter_section(rows: list[dict], filed: list[dict] | None = None) -> dict:
    """The latest reported quarter of each company against the same quarter a year before (revenue and net profit change), as the company page's
    "Latest YoY" gives it, with how many are up and down. One quarter per median (the owner, 7 Nov: June and September mixed in one median): the
    newest quarter at least MIN_LAYER companies report is the median's; a company still on an earlier quarter is listed apart, and one whose
    newer results were filed (`filed`: the events' results filed) but aren't in its figures yet is marked with the filing's day. Facts only: it
    compares a company with its own year-ago quarter, not with anyone's estimate."""
    have = [r for r in rows if r.get("quarter") and (r["quarter"]["sales"] is not None or r["quarter"]["profit"] is not None)]
    ends = Counter(quarter_end(r["quarter"]["of"]) for r in have)
    ends.pop(None, None)
    usual = max((d for d, k in ends.items() if k >= MIN_LAYER), default=None) or (max(ends, key=lambda d: (ends[d], d)) if ends else None)
    cur = [r for r in have if quarter_end(r["quarter"]["of"]) == usual] if usual else have
    late = {f["symbol"]: f["date"] for f in filed or [] if f.get("date")}
    earlier = []
    for r in have:
        if r in cur:
            continue
        end = quarter_end(r["quarter"]["of"])
        newer = late.get(r["symbol"])
        earlier.append({"symbol": r["symbol"], "name": r["name"], "of": r["quarter"]["of"], "sales": r["quarter"]["sales"], "profit": r["quarter"]["profit"],
                        "filed_unread": newer if newer and end and str(newer) > end.isoformat() else None})
    return {"companies": [{"symbol": r["symbol"], "name": r["name"], "of": r["quarter"]["of"], "sales": r["quarter"]["sales"], "profit": r["quarter"]["profit"]} for r in cur],
            "quarter": usual.strftime("%b %Y") if usual else None, "earlier": earlier,
            "sales_up": sum(1 for r in cur if (r["quarter"]["sales"] or 0) > 0), "sales_down": sum(1 for r in cur if (r["quarter"]["sales"] or 0) < 0),
            "profit_up": sum(1 for r in cur if (r["quarter"]["profit"] or 0) > 0), "profit_down": sum(1 for r in cur if (r["quarter"]["profit"] or 0) < 0),
            "sales": stat(r["quarter"]["sales"] for r in cur), "profit": stat(r["quarter"]["profit"] for r in cur)}


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
                                    "pe", "pb", "ev_ebitda", "debt_equity", "stage", "from_high", "one_off", "ebitda_dp", "status", "bank", "profit") + LENDER_KEYS} for r in rows]


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
            "promoter_median": stat(r["promoter"] for r in rows), "insider_buys": bought, "pledges": pledges, "red_flags": flagged_rows(flagged, names),
            "fund_raises": fund_raises(flagged, names)}


INSTITUTION_KINDS = {"mutual fund", "insurance company", "provident or pension fund", "alternative investment fund", "foreign portfolio investor",
                     "foreign direct investor", "bank", "bank or financial institution", "other institution", "foreign institution", "sovereign wealth fund"}
PLEDGE_CATEGORIES = {"pledge"}


FUND_RAISE = re.compile(r"rights issue|fund ?rais|preferential|qip\b|qualified institution", re.I)


def flagged_rows(items: list[dict], names: dict) -> list[dict]:
    """The red-flag filings, newest first: one row for a company's same flag on the same day (an exchange posts a filing twice), and a rights
    issue or other fund raise left out (it is a corporate action, not a warning on its own: fund_raises lists them)."""
    seen, out = set(), []
    for i in sorted(items, key=lambda i: (i["at"], i["symbol"]), reverse=True):
        label = i.get("label") or i.get("category")
        if FUND_RAISE.search(f"{label} {i.get('category') or ''}"):
            continue
        key = (i["symbol"], str(i["at"])[:10], label)
        if key in seen:
            continue
        seen.add(key)
        out.append({"symbol": i["symbol"], "name": names.get(i["symbol"]) or i.get("company") or i["symbol"], "at": i["at"], "label": label,
                    "severity": i.get("severity"), "subject": i.get("subject") or i.get("title") or "", "url": i.get("url")})
    return out[:15]


def fund_raises(items: list[dict], names: dict) -> list[dict]:
    """Rights issues and other fund raises among the filings, once per company and day."""
    seen, out = set(), []
    for i in sorted(items, key=lambda i: (i["at"], i["symbol"]), reverse=True):
        label = i.get("label") or i.get("category")
        if not FUND_RAISE.search(f"{label} {i.get('category') or ''}") or (i["symbol"], str(i["at"])[:10]) in seen:
            continue
        seen.add((i["symbol"], str(i["at"])[:10]))
        out.append({"symbol": i["symbol"], "name": names.get(i["symbol"]) or i.get("company") or i["symbol"], "at": i["at"], "label": label, "url": i.get("url")})
    return out[:10]


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
    and a layer whose aggregate EBITDA margin moved a lot over three years. Empty when nothing is. A group of the theme's companies that no
    layer took (an official industry's, or "Named in the theme's list": "official" in theme_base.with_base) isn't a layer of the chain, so it
    is never the high or the low end of a gap and its margin's move isn't a layer's (R11: the cybersecurity post set "Named in the theme's
    list" against a layer). The decks' floors hold (R25): a gap is between layers of COMPARE_MIN companies with the figure or more, and a move
    is of an aggregate of MIN_BASE companies or more."""
    out = []
    apart = {b.get("layer") for b in blocks if b.get("official")} | {r["layer"] for r in chain["rows"] if r.get("official")}
    have = [r for r in chain["rows"] if r["ebitda"] is not None and headline_ok(r["ebitda_n"], r["n"], r.get("model")) and r["layer"] not in apart]
    if len(have) >= 2:
        hi, lo = max(have, key=lambda r: r["ebitda"]), min(have, key=lambda r: r["ebitda"])
        if hi["ebitda"] - lo["ebitda"] >= NOTABLE_GAP:
            out.append({"kind": "gap", "high": hi["layer"], "high_value": hi["ebitda"], "low": lo["layer"], "low_value": lo["ebitda"],
                        "gap": round(hi["ebitda"] - lo["ebitda"], 1)})
    for layer, h in histories.items():
        if layer in apart:
            continue
        if h and (h.get("n") or 0) >= MIN_BASE and len(h["years"]) >= 4 and h["ebitda"][-1] is not None and h["ebitda"][-4] is not None:
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
    history(key, point) -> the theme's kept points after adding `point` (a day's median P/E and the like), oldest first;
    segments(symbol) -> the business segments the company's documents report ([{name, share_pct}]) or None (is_diversified);
    corp_history(symbol) -> the company's stored corporate actions (every kind, each with "kind" and "ex_date"), never read from a source;
    metrics(symbol, family) -> the company's filed sector figures (sector_metrics: a stored piece, read now or queued) or None (R23)."""

    def __init__(self, today: date, facts, index_rows=lambda: [], shareholding=lambda s: None, insider_buys=lambda: {},
                 results=lambda a, b, s: [], actions=lambda a, b, s: [], red_flags=lambda s, a, b: [], card=lambda s, r: None,
                 history=lambda k, p: [p], segments=lambda s: None, corp_history=lambda s: [], metrics=lambda s, fam: None):
        self.today, self.facts, self.index_rows, self.shareholding, self.insider_buys = today, facts, index_rows, shareholding, insider_buys
        self.results, self.actions, self.red_flags, self.card, self.history, self.segments = results, actions, red_flags, card, history, segments
        self.corp_history, self.metrics = corp_history, metrics


_STOP = {"company", "companies", "limited", "india", "indian", "sector", "theme", "other", "others", "product", "products", "service", "services",
         "industry", "industries", "these", "their", "which", "with", "from", "that", "this", "make", "makes", "made", "sell", "sells", "large", "small",
         "main", "rising", "growth", "levers", "market", "markets", "demand", "through", "largely", "also", "several", "rest", "chain", "layer", "brand",
         "brands", "global", "leading", "business", "businesses", "decide", "much", "each", "sale", "sales", "move", "moving", "towards", "into",
         "tied", "mostly", "mainly", "most", "more", "than", "they", "them", "have", "work", "include", "including", "range", "wide", "firm", "firms",
         "household", "households", "income", "incomes", "financing", "profit", "share", "scale", "cycle", "change", "changes", "depend", "depends",
         "availability", "activity", "replacement", "network", "networks", "dealer", "dealers", "retained", "listed", "official", "equipments"}


def _stems(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z]+", str(text or "").lower()):
        if len(w) < 4 or w in _STOP:
            continue
        out.add(w[:-2] if w.endswith("es") and len(w) > 5 else w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def theme_words(checked: dict, theme: str) -> set[str]:
    """The words that say a company does the theme's work: the theme's, its official industries', its layers' and its sub-themes' names, and
    the sub-themes' one-line details."""
    parts = [theme, checked.get("sector") or ""] + list((checked.get("placements") or {}).get("industries") or [])
    # each layer's name and the AI's own description of its work (R17-012: "trucks and buses" is the commercial-vehicle layer's work even
    # when no name says it)
    parts += [f"{v.get('layer') or ''} {v.get('description') or ''}" for v in checked.get("value_chain") or []]
    parts += [f"{s.get('name') or ''} {s.get('detail') or ''}" for s in checked.get("sub_themes") or []]
    return _stems(" ".join(parts))


def does_the_work(what: str, words: set[str]) -> bool:
    """Whether a company's own sentence uses one of the theme's words (a word of the sentence starting with one of them)."""
    mine = _stems(what)
    return any(m == w or (len(w) >= 4 and m.startswith(w)) for m in mine for w in words)


# words a sentence uses when it says what a company does (any trade): a sentence with none of them says nothing about the work
BUSINESS = re.compile(r"\b(?:manufactur\w*|mak(?:e|es|er|ers|ing)|produc\w*|sell\w*|suppl\w*|provid\w*|offer\w*|engaged|develop\w*|"
                      r"design\w*|distribut\w*|operat\w*|speciali[sz]\w*|deal(?:s|er|ers|ing)?\s+in|portfolio|business\s+of|services?)\b", re.I)


# kinds of work far from making or doing a theme's own thing: a company of the theme's own industry whose own words name one of these, and
# none of the theme's words, describes other work ("supplies software to insurance companies" filed under auto parts). A company whose words
# simply don't repeat the theme's vocabulary ("one of India's first motorcycle manufacturers", "storage batteries", "aluminium die casting")
# stays: the exchange's classification is the base and nothing in its words says otherwise (R18: Hero MotoCorp, Exide, Endurance and
# Escorts Kubota were "not confirmed" in the Automotive deck)
OTHER_WORK = re.compile(r"\b(?:software|saas|it services|information technology|staffing|recruitment|manpower|insurance|insurer|banking|bank|"
                        r"lending|lender|nbfc|microfinance|broking|brokerage|stock ?broker|asset management|mutual fund|real estate|realty|"
                        r"hotels?|hospitality|restaurants?|education|schools?|edtech|consulting|consultancy|advertising|media|broadcast\w*|"
                        r"entertainment|films?|hospitals?|healthcare services|diagnostics|pharmaceutical\w*|drugs?|telecom\w*|"
                        r"e-?commerce|retail stores?|trading company|logistics|courier|shipping line)\b", re.I)


def other_work(what: str, words: set[str]) -> bool:
    """Whether a company's own sentence names a kind of work that isn't the theme's (OTHER_WORK, unless the theme's own words name it too)."""
    for m in OTHER_WORK.finditer(str(what or "")):
        if not does_the_work(m.group(0), words):
            return True
    return False


def membership(c: dict, words: set[str]) -> str:
    """How sure the theme is of a company (the owner, 7 Nov: a membership check for official-industry companies too, so an insurance software
    house filed under auto parts isn't in the auto figures): "core", a company of the theme's own industries or list whose own words (or a
    checked quote) show the work; "exposure", a company from another industry whose own words were checked to show the work; "unverified",
    the rest: listed, but left out of every median and total."""
    if c.get("base") is None and c.get("verified") is None:
        return "core"                                 # a map from before the checks: as it was
    if c.get("base"):
        if c.get("basis") == "list" or c.get("verified") or does_the_work(c.get("what") or "", words):
            return "core"
        # own words that say nothing of the work ("The Company was established in 1981", "flagship company of the group"), or that describe
        # a business without the theme's words but no other kind of work ("motorcycle manufacturers"): nothing contradicts the exchange's
        # classification, so it stands (R17-012, R18)
        if not BUSINESS.search(c.get("what") or "") or not other_work(c.get("what") or "", words) or c.get("fit"):
            # (a company the placement found a layer for, from its own words, is the theme's: R22, a CRO in a pharma theme)
            return "core"
        return "unverified"
    return "exposure" if c.get("verified") else "unverified"


def slug(theme: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(theme or "").lower()).strip("-")[:60]


def by_industry(checked: dict) -> dict:
    """A theme with no AI map whose only layer is its own named list (R18: Cybersecurity, one layer "Named in the theme's list") gets its
    layers from its companies' own official industries: each industry with MIN_LAYER companies or more is a layer, the rest one layer of
    "Other industries" (when it has MIN_LAYER too). Unchanged when that doesn't give two layers, or the map has layers of its own."""
    vc = checked.get("value_chain") or []
    if len(vc) != 1 or not vc[0].get("official") or vc[0].get("basis") != "list":
        return checked
    from .theme_base import plain_industry
    groups: dict[str, list] = {}
    for c in vc[0].get("companies") or []:          # by the industry's plain name, so two codes of one trade are one layer (R20)
        groups.setdefault(plain_industry(c.get("industry") or "").strip(), []).append(c)
    big = {k: v for k, v in groups.items() if k and len(v) >= MIN_LAYER}
    rest = [c for k, v in groups.items() if k not in big for c in v]
    if len(big) + (1 if len(rest) >= MIN_LAYER else 0) < 2 or (rest and len(rest) < MIN_LAYER):
        return checked
    cap = lambda cos: -sum(c.get("cap") or 0 for c in cos)      # noqa: E731
    layers = [{"layer": k, "description": "", "official": True, "basis": "list", "by_industry": True, "companies": v}
              for k, v in sorted(big.items(), key=lambda kv: (cap(kv[1]), kv[0]))]
    if rest:
        layers.append({"layer": "Other industries", "description": "", "official": True, "basis": "list", "by_industry": True, "companies": rest})
    return {**checked, "value_chain": layers}


def build(region: str, theme: str, checked: dict, src: Sources) -> dict:
    """The dive for a checked map (see theme_check.check_placements): the tables by layer, the whole chain in one table, the sub-themes'
    companies, and the sections for the theme as a whole. Every figure is from the stored facts; nothing here calls a source."""
    checked = by_industry(checked)
    # one layer per company: a company the map puts in two layers stays in the first (the owner, 7 Nov), so no company is counted twice
    first: dict[str, str] = {}
    for v in checked.get("value_chain") or []:
        for c in v.get("companies") or []:
            first.setdefault(c["ticker"], v.get("layer") or "")
    checked = {**checked, "value_chain": [{**v, "companies": [c for c in v.get("companies") or [] if first.get(c["ticker"]) == (v.get("layer") or "")]}
                                          for v in checked.get("value_chain") or []]}
    placed: dict[str, dict] = {}
    for grp in (checked.get("value_chain") or []) + (checked.get("sub_themes") or []):
        for c in grp.get("companies") or []:
            placed.setdefault(c["ticker"], c)
    words = theme_words(checked, theme)
    every_status = {s: membership(c, words) for s, c in placed.items()}
    facts = {s: src.facts(s) for s in placed}
    rows = {s: r for s, r in ((s, company_row(region, s, f)) for s, f in facts.items()) if r}
    for s, c in placed.items():
        if s in rows:
            rows[s]["name"] = c.get("name") or rows[s]["name"]
            rows[s]["status"] = membership(c, words)
            rows[s]["map_industry"] = c.get("industry") or ""          # the exchange's (or the SEC's) industry the map gives (R27: metric_registry)
            rows[s]["map_what"] = c.get("what") or ""                  # what the map says the company does (an insurer's type: metric_registry)

    def segs(sym):
        try:
            return src.segments(sym)
        except Exception as e:
            print("theme data: segments not read:", sym, type(e).__name__, str(e)[:100])
            return None
    pending, pending_fam = [], {}
    for s, r in rows.items():               # each company's filed sector figures (R23): a bank's, an insurer's, a US company's
        fam = sector_metrics.family_of(region, r)
        if not fam:
            continue
        try:
            piece = src.metrics(s, fam)
        except Exception as e:
            print("theme data: sector figures not read:", s, type(e).__name__, str(e)[:100])
            piece = None
        if piece is None:
            pending.append(s)
            pending_fam[s] = fam
        sector_metrics.apply(r, piece)
    wide = {s for s, r in rows.items() if is_diversified(r, segs(s))}
    names = {s: r["name"] for s, r in rows.items()}
    market = [m for m in (src.index_rows() or []) if isinstance(m, dict)]

    blocks, histories = [], {}
    for v in checked.get("value_chain") or []:
        mine = [rows[c["ticker"]] for c in v.get("companies") or [] if c["ticker"] in rows]
        what = {c["ticker"]: c.get("what") for c in v.get("companies") or []}
        ind = {c["ticker"]: c.get("industry") for c in v.get("companies") or []}          # the exchange's industry, a column of an AI layer (R20)
        from .theme_check import model_family
        for r in mine:                     # R30: an EBITDA margin checked against how the company earns
            validate_model(r, model_family(model_fields(v, r["symbol"]).get("model") or "") or ((v.get("model") or {}).get("family") or ""))
        b = layer_block(v.get("layer") or "", [{**r, "what": what.get(r["symbol"]), "company_wide": r["symbol"] in wide, "official_industry": ind.get(r["symbol"]) or "",
                                                **model_fields(v, r["symbol"])} for r in mine], wide)
        b["description"] = v.get("description") or ""
        b["policy"] = v.get("policy")
        b["official"], b["basis"] = bool(v.get("official")), v.get("basis")     # a layer that is one official industry's companies the AI didn't place (theme_base.py)
        b["by_industry"] = bool(v.get("by_industry"))
        b["model"] = v.get("model") or None                 # what the layer's companies have in common: how they earn (theme_base.by_model, R25)
        if b["model"]:                                       # R28: counted over the companies the page shows, not every company the map placed
            from .theme_base import shown_model
            b["model"] = shown_model(b["model"], [r for r in b["companies"] if r.get("status") != "unverified"])
        blocks.append(b)
        out_ = set(b.get("model_out") or [])            # R27: left out of the layer's figures (model unknown or of low confidence)
        sure = [r for r in mine if r.get("status") != "unverified" and r["symbol"] not in out_]
        histories[b["layer"]] = layer_history([r for r in sure if r["symbol"] not in wide] or sure)
    chain = chain_table(blocks)
    counted = [r for b in blocks for r in b["companies"] if r.get("status") != "unverified"]
    pool = [r for r in counted if not r["company_wide"]] or counted
    allm = stat(r["ebitda"] for r in {r["symbol"]: r for r in pool}.values())
    for b in blocks:
        b["line"] = margin_line(b, allm["median"] if allm else None, several=sum(1 for x in blocks if x["stats"].get("ebitda")) > 1, whole=whole_points(pool))
        b["history"] = histories.get(b["layer"])
    subs = []
    for s in checked.get("sub_themes") or []:
        cos = []
        for c in s.get("companies") or []:
            r = rows.get(c["ticker"])
            if r:
                cos.append({"symbol": r["symbol"], "name": r["name"], "what": c.get("what"), "cap": r["cap"], "sales_1y": r["sales_1y"], "ebitda": r["ebitda"],
                            "company_wide": r["symbol"] in wide, "year": r["year"], "bank": r.get("bank"), "net": r.get("net"), "roe": r.get("roe")})
        subs.append({"name": s.get("name") or "", "detail": s.get("detail") or "", "companies": cos})
    for r in rows.values():                 # a merger or demerger broke the company's series: no growth figure for it, none in the growth totals
        r["demerger"] = demerger_on(src, r["symbol"])
        if series_break(r) or r["demerger"]:
            r["series_break"] = True
            for k in ("sales_1y", "sales_3y", "sales_5y", "profit_1y", "profit_3y", "profit_5y"):
                r[k] = None
    listed = sorted(rows.values(), key=lambda r: -(r.get("cap") or 0))
    syms = [r["symbol"] for r in listed]
    # every total and median: the confirmed companies with their key figures (R22: one population, so no count is larger than the one stated)
    members = [r for r in listed if r.get("status") != "unverified" and has_figures(r)]
    own = [r for r in members if r["symbol"] not in wide] or members
    val = valuation_section(members, market)
    val["by_layer"] = layer_valuation(blocks, {r["symbol"] for r in members})
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
        "basis": basis_text(members, region), "layers": blocks, "chain": chain, "subs": subs, "company_wide": sorted(wide & set(syms)),
        # "with figures" means the key figures exist (revenue or profit), not just a stored page (R20: a bank with dashes in every field
        # counted among "20 of 20 with figures")
        "members": sum(1 for r in members if has_figures(r)),
        "sections": {
            "size": size_section(members), "medians": {k: stat(r.get(k) for r in own if not (k == "net" and r.get("one_off"))) for k in ("ebitda", "net", "roce", "roe")},
            "growth": aggregate_growth([r for r in own if not r.get("series_break")]), "margins": margin_history(own), "valuation": val,
            "balance": balance_section(own), "price": stored_price_section(members), "market": market_med,
            "ownership": ownership_section(syms, names, src), "events": events_section(syms, names, src),
            "management": management_section(syms, names, rows, src), "leaders": leaders(listed)},
        "growth_basis_n": len(own_set),
        # the theme's companies by how sure the theme is of each (R17-012), every placed company, with figures or not; "with_figures" is of the
        # confirmed ones only (R28: an unconfirmed company is listed but never in the figures, so "with figures 15" beside "confirmed 14" was wrong)
        "membership": {"placed": len(every_status), "confirmed": sum(1 for x in every_status.values() if x != "unverified"),
                       "not_confirmed": sum(1 for x in every_status.values() if x == "unverified")},
        "status": {r["symbol"]: r.get("status") or "core" for r in listed}, "with_figures": sum(1 for r in listed if has_figures(r) and r.get("status") != "unverified"),
        "without_figures": [{"symbol": r["symbol"], "name": r["name"]} for r in listed if not has_figures(r) and r.get("status") != "unverified"],
    }
    out["sections"]["medians"]["net_all"] = stat(r.get("net") for r in own)
    layer_of = {c["symbol"]: b["layer"] for b in blocks for c in b["companies"]}
    out["sections"]["margin_drivers"] = margin_drivers(out["sections"]["margins"], rows, layer_of)
    out["sections"]["quarter"] = quarter_section(members, out["sections"]["events"].get("results_filed"))
    # each company's revenue model family: its layer's (theme_base.by_model), unless the layer's model rests on too few of its companies
    model_of = {c["symbol"]: b["model"]["family"] for b in blocks for c in b["companies"]
                if (b.get("model") or {}).get("family") and not b["model"].get("sparse")}
    out["sections"]["sector"] = sector_metrics.section([r for r in own if r.get("status") != "unverified"], region, layer_of, pending, stat, model_of)
    out["metrics_pending"] = sorted(pending)
    out["metrics_families"] = pending_fam           # R29: each one's family, so a kept dive can queue a read the worker dropped again
    out["checks"] = data_checks(listed, blocks, out)
    out["notable"] = notable_items(blocks, chain, histories)
    return out


# ---------- headlines worth a line ----------
# a quote page, a derivatives table, a list of picks or a price-move roundup is not news about the business (the owner, 7 Nov: "Share Price -
# Live", "Option Chain", put counts, Diwali picks)
NOISE = re.compile(r"share price|stock price|price today|price live|\blive\b.*\bchart\b|option chain|\b(?:put|call) contracts?\b|open interest|"
                   r"stock picks?|stocks? to (?:buy|watch)|top (?:gainers|losers)|gainers (?:&|and) losers|technical (?:signals|view|outlook)|"
                   r"\bquote(?:,| and)|price,? news|multibagger|target price|\bbuy or sell\b|share price target|\bmuhurat\b", re.I)
HOME = {"IN": re.compile(r"\bindia|\bindian\b|\bnse\b|\bbse\b|\bsebi\b|\brbi\b|\bgst\b|₹|\brs\.? ?\d|\bcrore|\blakh", re.I),
        "US": re.compile(r"\bu\.?s\.?\b|\bamerica|\bunited states|\bsec\b|\bnyse\b|\bnasdaq\b|\bfed\b|\$", re.I)}


def headline_kept(item: dict, region: str) -> bool:
    """Whether a headline is about the business: not a quote page, a derivatives table, a list of picks or a price roundup; and a headline
    about the theme in general (no company of the theme in it) must be about the theme's own market (the owner, 7 Nov: Mexico's tax plan,
    Schaeffler's job cuts in Europe in an India theme). An exchange filing is always kept."""
    text = str(item.get("headline") or "")
    if item.get("kind") == "filing" or str(item.get("source") or "").lower() in ("exchange filing", "sec filing"):
        return True
    if NOISE.search(text):
        return False
    if not item.get("company") and region in HOME and not HOME[region].search(text):
        return False
    return True


# ---------- what the figures can and can't carry ----------
SERIES_JUMP = 60.0            # a year's revenue this many % above or below the year before: a merger or demerger has changed the company


def series_break(r: dict) -> bool:
    """Whether a company's years don't make one series: too few full years to compare (a new listing or a company formed by a demerger), or
    a year's revenue jumping or falling by SERIES_JUMP% or more on the one before (a merger or demerger moved a business in or out)."""
    ys = [y for y in r.get("years") or [] if y.get("sales")]
    if r.get("revenue") and len(ys) < 2:
        return True
    for a, b in zip(ys[-3:], ys[-2:]):
        if a["sales"] and b["sales"] and a["sales"] > 0 and abs(b["sales"] / a["sales"] - 1) * 100 >= SERIES_JUMP:
            return True
    return False


DEMERGER_YEARS = 3            # a demerger this recent splits the years a growth figure is worked out from


def demerger_on(src, symbol: str) -> str | None:
    """The ex-date of a demerger (or scheme of arrangement) in the company's stored corporate actions within the last DEMERGER_YEARS, or
    None (R17-005: a demerger was found only from a jump in revenue, so a company whose years moved less than SERIES_JUMP kept its growth
    figures across the split)."""
    try:
        acts = src.corp_history(symbol) or []
    except Exception as e:
        print("theme data: corporate actions not read:", symbol, type(e).__name__, str(e)[:100])
        return None
    since = (src.today - timedelta(days=365 * DEMERGER_YEARS)).isoformat()
    hits = sorted(str(a.get("ex_date") or a.get("record_date") or "")[:10] for a in acts
                  if isinstance(a, dict) and (a.get("kind") == "demerger" or re.search(r"demerger|scheme of arrangement|spin[- ]?off", str(a.get("text") or a.get("purpose") or ""), re.I)))
    hits = [d for d in hits if d and since <= d <= src.today.isoformat()]
    return hits[-1] if hits else None


def data_checks(rows: list[dict], blocks: list[dict], dive: dict) -> dict:
    """The checks every figure in the dive went through, with what was found (the deck's "data confidence" page; facts, each with its
    companies): one-off earnings, broken series, membership not confirmed, a quarter apart from the median's, and the count each median is on."""
    sec = dive["sections"]
    q = sec.get("quarter") or {}
    meds = sec.get("medians") or {}
    return {
        "one_off": [{"symbol": r["symbol"], "name": r["name"], "ebitda": r["ebitda"], "net": r["net"]} for r in rows if r.get("one_off") and r.get("status") != "unverified"],
        "held": held_rows(rows),            # R30: figures a check held back (validate_row, validate_model)
        "net_with": (meds.get("net_all") or {}).get("median"), "net_without": (meds.get("net") or {}).get("median"),
        "series": [{"symbol": r["symbol"], "name": r["name"], **({"demerger": r["demerger"]} if r.get("demerger") else {})} for r in rows if r.get("series_break") or series_break(r)],
        "unverified": [{"symbol": r["symbol"], "name": r["name"]} for r in rows if r.get("status") == "unverified"],
        "earlier_quarter": q.get("earlier") or [], "quarter": q.get("quarter"),
        "n": {k: (meds.get(k) or {}).get("n", 0) for k in ("ebitda", "net", "roce", "roe")},
        "lenders": sum(1 for r in rows if r.get("bank") and r.get("status") != "unverified"),
        # companies reporting in another currency (R22): converted at the stated rate, or left out of money totals when there is none
        "currency": [{"symbol": r["symbol"], "name": r["name"], "currency": r["currency"], "rate": (r.get("fx") or {}).get("rate"), "at": (r.get("fx") or {}).get("at")}
                     for r in rows if r.get("fx")],
        "whole_points": sum(1 for r in rows if r.get("ebitda_dp") == 0), "with_ebitda": sum(1 for r in rows if r.get("ebitda") is not None),
    }


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


MOVE_HELD = 50.0              # % a month's (or quarter's) figure moved on the one before, or 150% on a year before: held for checking


def hold_suspect(rows: list[dict]) -> list[dict]:
    """Operating figures held for checking before they're shown (the owner, 7 Nov): a previous or year-ago figure that is the same number for
    two different companies (Tata Motors PV's and Tata Motors CV's 37,530: one filing read for both), and a change so large it is more likely a
    misread column than a real move (Mahindra's −66.4% on the month). The figure as filed stays; the compared figure and its change are
    blanked and `held` says why."""
    seen: Counter = Counter()
    for r in rows:
        for k in ("prev", "year_ago"):
            if r.get(k) is not None:
                seen[(r.get("unit"), r[k])] += 1
    out = []
    for r in rows:
        r = dict(r)
        held = []
        wild = "%" not in (r.get("unit") or "") and ((r.get("change_prev") is not None and abs(r["change_prev"]) >= MOVE_HELD) or
                                                     (r.get("change_year") is not None and abs(r["change_year"]) >= 3 * MOVE_HELD))
        for k, ck in (("prev", "change_prev"), ("year_ago", "change_year")):
            v = r.get(k)
            if v is not None and seen[(r.get("unit"), v)] > 1 and len({x["symbol"] for x in rows if v in (x.get("prev"), x.get("year_ago"))}) > 1:
                held.append(f"the {'previous' if k == 'prev' else 'year-ago'} figure is the same as another company's")
                r[k], r[ck] = None, None
        if "%" not in (r.get("unit") or ""):
            if r.get("change_prev") is not None and abs(r["change_prev"]) >= MOVE_HELD:
                held.append(f"a {r['change_prev']:+.1f}% move on the previous period")
                r["prev"], r["change_prev"] = None, None
            if r.get("change_year") is not None and abs(r["change_year"]) >= 3 * MOVE_HELD:
                held.append(f"a {r['change_year']:+.1f}% move on the year")
                r["year_ago"], r["change_year"] = None, None
        if wild:
            # a move too large to take as filed puts the latest figure itself in doubt: neither comparison is shown (R18: Mahindra's 38,563 held
            # for −66.4% on the month still showed a year ago of 1,00,298 and −61.6% on the year)
            r["prev"] = r["change_prev"] = r["year_ago"] = r["change_year"] = None
            r["held_latest"] = True
        r["held"] = "; ".join(held) or None
        out.append(r)
    return out


def business_section(blocks: list[dict], subs: list[dict], names: dict, read) -> dict:
    """Operating figures by layer and sub-theme, plus how many of the theme's companies have one; figures that need checking are held
    (hold_suspect) across the whole theme, since two companies can share a misread filing."""
    every = {}
    for b in blocks:
        b["business"] = business_rows([c["symbol"] for c in b["companies"]], names, read)
        every.update({r["symbol"]: r for r in b["business"]})
    for s in subs:
        s["business"] = business_rows([c["symbol"] for c in s["companies"]], names, read)
        every.update({r["symbol"]: r for r in s["business"]})
    checked = {r["symbol"]: r for r in hold_suspect(list(every.values()))}
    for g in blocks + subs:
        g["business"] = [checked.get(r["symbol"], r) for r in g["business"]]
    total = len({c["symbol"] for b in blocks for c in b["companies"]} | {c["symbol"] for s in subs for c in s["companies"]})
    return {"layers": [{"layer": b["layer"], "rows": b["business"]} for b in blocks], "subs": [{"name": s["name"], "rows": s["business"]} for s in subs],
            "companies": len(every), "of": total, "held": [{"symbol": r["symbol"], "name": r["name"], "why": r["held"]} for r in checked.values() if r.get("held")]}


# ---------- R25: every number a sentence states is one the tables show ----------
# a deck's headlines and findings are written from the same rows as its tables; before a deck is stored each of their percentages, multiples,
# gaps in points and counts is looked for again among the figures its tables, charts and tiles show, and a sentence with one that isn't there
# is dropped, never shipped wrong (the owner's outside review, 7 Nov)
_C_PCT = re.compile(r"(?<![\w.,])([+−-]?)(\d[\d,]*(?:\.\d+)?)%")
_C_X = re.compile(r"(?<![\w.,])(\d[\d,]*(?:\.\d+)?)x\b")
_C_PTS = re.compile(r"(?<![\w.,])([+−-]?)(\d+(?:\.\d+)?) (?:pts|points?)\b")
_C_OF = re.compile(r"(?<![\w.,])(\d[\d,]*) of (?:the |all )?(\d[\d,]*)\b(?! ?%)")
_C_N = re.compile(r"(?<![\w.,])(\d[\d,]*) (?:more )?(?:compan(?:y|ies)|banks?|insurers?|general insurers|layers?|loss-makers?)\b|\((\d[\d,]*)\)")
_C_ANY = re.compile(r"(?<![\w.])([+−-]?)(\d[\d,]*(?:\.\d+)?)")
_C_MONEY = re.compile(r"(?<![\w.])(?:[₹$]\d[\d,]*(?:\.\d+)?(?: lakh)?(?: cr| bn| m| million| billion)?|[A-Z]{3} \d[\d,]*(?:\.\d+)? (?:bn|m|million|billion)\b)")


def _cnum(sign: str, digits: str) -> float:
    return float(digits.replace(",", "")) * (-1 if sign in ("−", "-") else 1)


def shown_numbers(texts) -> dict:
    """The figures a deck's tables, charts and tiles show, from their cells as printed (`texts`: strings and numbers): {"pct", "x", "pts",
    "n", "money", "gaps"}, each a set (money as printed: "₹8,855 cr"; "gaps" is filled by the caller: the differences within a column). A chart's plotted values come as numbers and count as percentages and multiples."""
    out = {"pct": set(), "x": set(), "pts": set(), "n": set(), "money": set(), "gaps": set()}
    for t in texts:
        if t is None or isinstance(t, bool):
            continue
        if isinstance(t, (int, float)):
            out["pct"].add(round(float(t), 2))
            out["x"].add(round(float(t), 2))
            if float(t).is_integer():
                out["n"].add(int(t))
            continue
        t = str(t)
        for sign, d in _C_PCT.findall(t):
            out["pct"].add(_cnum(sign, d))
        for d in _C_X.findall(t):
            out["x"].add(_cnum("", d))
        for sign, d in _C_PTS.findall(t):
            out["pts"].add(_cnum(sign, d))
        out["money"].update(_C_MONEY.findall(t))
        for sign, d in _C_ANY.findall(t):
            v = _cnum("", d)
            if v.is_integer():
                out["n"].add(int(v))
    return out


def _near(value: float, digits: str, pool) -> bool:
    """Whether a figure printed with `digits` is one of `pool` at that precision (a whole 19% is 19.0 to 19.4 and 18.5 shown whole)."""
    dp = len(digits.split(".")[1]) if "." in digits else 0
    tol = 0.5 if dp == 0 else 0.5 * 10 ** -dp + 1e-9
    return any(abs(p - value) <= tol + 1e-9 for p in pool)


def claim_mismatches(text: str, shown: dict, floor: int = COMPARE_MIN) -> list[str]:
    """The figures a headline or finding states that the deck's tables don't show (`shown`: shown_numbers): a percentage or multiple not among
    the table figures; a gap in points that is neither the difference of two percentages the sentence states, nor of two in one table column,
    nor a figure shown; a count of
    companies not among the shown counts; a money figure not printed in a table. Empty when every figure is there. Rules' own constants (5% of a high, 25% or more) are not figures."""
    bad = []
    pcts = []
    for sign, d in _C_PCT.findall(text):
        v = _cnum(sign, d)
        pcts.append(v)
        if not _near(v, d, shown["pct"]):
            bad.append(f"{sign}{d}%")
    for d in _C_X.findall(text):
        if not _near(_cnum("", d), d, shown["x"]):
            bad.append(f"{d}x")
    for sign, d in _C_PTS.findall(text):
        v = abs(_cnum(sign, d))
        gaps = {round(abs(a - b), 2) for a in pcts for b in pcts} | set(shown.get("gaps", ()))
        if not (_near(v, d, gaps) or _near(_cnum(sign, d), d, shown["pts"])):
            bad.append(f"{sign}{d} points")
    counts = [int(a.replace(",", "")) for pair in _C_OF.findall(text) for a in pair] + \
        [int((a or b).replace(",", "")) for a, b in _C_N.findall(text)]
    for n in counts:
        if n not in shown["n"] and n != floor:
            bad.append(str(n))
    for a, b in _C_OF.findall(text):
        if int(a.replace(",", "")) > int(b.replace(",", "")):
            bad.append(f"{a} of {b}")
    bad += [m for m in _C_MONEY.findall(text) if m not in shown.get("money", ())]
    return bad
