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
from . import sector_metrics, sector_ops

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
# R31 (the owner's review of the live R30 decks): a layer-vs-layer headline (the value chain's line, findings, questions) needs at least this
# many companies with the figure in each layer it compares; tables still show every layer and mark (green, red) those of COMPARE_MIN or more
DIVE_TEXT = 22         # gl52 (R52): "none_found" and "unfit" reasons, no "read as" for a low-confidence model, one precision in a headline gap, halves ranked as one, the stock-pay rule, theme size by a conglomerate's theme segment; rv51 (R51): a layer's business model only from its own records (named_fit); a company of the theme's industries whose principal business fits it never screened out by its words (membership); gl50 (R50): a chain with no way of earning read shown, not ranked; a parent's listed subsidiary out of totals adding both; the latest quarter most companies report; a clinical-stage layer's commercial companies out of its figures; ex49 (R49): each company left out of a layer's figures with its precise reason (a different revenue model with both models, insufficient evidence with what is missing, the part of a partial one), the capital-intensity proxy labelled and its inputs checked, layers ranked only of one business model the map's words support, which net-above-EBITDA lines are still missing; vr48 (R48): figures reconciled with the year's lines before any is held, the comparison basis (updated on purpose); cl48 (R47): a company listed in its layer as another way of earning is said so in the layer's line, the coverage control (theme_changes.coverage_control); vf46 (R46): each checked figure's source record and statement lines, a net margin above EBITDA reconciled line by line; c1 (R44): each company's place in the theme with its reason ("theme": theme_record) apart from its comparison decision ("comparison"), a layer named by how its companies earn says why it is never ranked; R44.1: a loss in a verification reason printed with the real minus (deck 55, dive text 15, updated on purpose); R44 (lane v1): each unusual figure verified against its own filed figures, not reconciled or invalid (verify_net, figure_states), never dropped by a cutoff alone; the dive's coverage of informative layers; R43.1: the whole-point margins counted among the margins there are ("3 of the 1" on the live Insurance deck); d1: halves of a split layer never ranked, no ranking on a gap under a point, peers named and like for like, every company in a layer or "Other", the not-checked-yet mark; LIVE7A (lane t1): every company at the index's newest close and one price date, own words without encyclopedia leads or a cut word, whole-point margins and gaps printed whole, operating figures of old periods left out and listed once, click-bait headlines left out, "Dividend: Dividend" said once; R40: a layer the split named only by how its companies earn is never ranked ("a group by how they earn, of different businesses"), a market-value half with fewer than 3 companies in its figures undone; LIVE6-007: a company's "what" only when it is its own words about its work (theme_base.own_words); R36: one company under two symbols kept once; R36: a ranking headline says which layers it ranks and why a shown layer beyond it is not ranked; lane m1: each company row keeps its place in its layer's calculations ("calc") and a layer's "n" is taken from them; R35: sub-theme members by their whole description, the peers behind each peer median and their price date; part of a stored dive's key (theme_routes.dive_key): bump when the dive's own sentences change, so a kept dive is made again
HEADLINE_MIN = 5
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


def gpts(v: float) -> str:
    """A margin as stored ({:g}: 43%, 1.1%) with a real minus, as every figure in the decks is printed (R44.1)."""
    return f"{v:g}%".replace("-", "−")


def whole_points(rows) -> bool:
    """Whether the EBITDA margins among these companies are mostly filed in whole points (company_row's ebitda_dp), so a median or a gap
    built on them is no more precise than a whole point (LIVE7A-009: one Indian company filed to a decimal, 29.9%, and every median and gap
    of the theme's whole-point margins was printed to a decimal: "12.0%", "a gap of 3.0 points")."""
    have = [r for r in rows if r.get("ebitda") is not None]
    return mostly_whole(sum(1 for r in have if r.get("ebitda_dp") == 0), len(have))


def mostly_whole(whole_n, with_n) -> bool:
    """At least half of the EBITDA margins counted are filed in whole points (LIVE7A-009); the page and the deck say so the same way."""
    return bool(with_n) and 2 * int(whole_n or 0) >= int(with_n)


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


_IRISH_O = re.compile(r"\bO (?=[A-Z][a-z]{2,})")


def shown_name(*names) -> str:
    """A company's name as the theme shows it (LIVE7A-025: "O Reilly Automotive Inc", "Lowes Companies Inc", a filing's name with its
    apostrophe dropped): of the names given that are the same name (letters and digits alike), the one that keeps its apostrophe, else the
    first; an "O " before a capitalised name is the Irish "O'"."""
    cands = [" ".join(str(n).split()) for n in names if n and str(n).strip()]
    if not cands:
        return ""
    k = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())        # noqa: E731
    same = [c for c in cands if k(c) == k(cands[0])]
    best = next((c for c in same if "'" in c or "’" in c), cands[0])
    return _IRISH_O.sub("O'", best)


def at_close(f: dict | None, row: dict | None, region: str = "IN", symbol: str | None = None) -> dict | None:
    """A company's kept facts at the newer close its index row has (LIVE7A-003: a company's facts are kept once for every theme until a
    Refresh, so the live Semiconductors page said "prices to 11 Nov" beside NVIDIA's market value at an earlier close): the price and its day
    from the row, the market value and P/E scaled by the price's move and the dividend yield against it, as the price job moves a page
    (stock_pages.with_new_close). Unchanged when the row's close isn't newer, or the move can't be scaled (a split since, a move outside the
    bounds): then the company keeps its own, older day, and the dive counts it as at an earlier close."""
    if not isinstance(f, dict) or not f or not isinstance(row, dict):
        return f
    new_at, old_at = str(row.get("price_at") or "")[:10], str(f.get("price_at") or "")[:10]
    new_p, old_p = num(row.get("price")), num(f.get("price"))
    if not new_at or new_at <= old_at or not new_p or new_p <= 0 or not old_p or old_p <= 0:
        return f
    if not stock_pages.can_reprice(old_p, new_p, region, symbol, old_at or None):
        return f
    k = new_p / old_p
    out = {**f, "price": new_p, "price_at": new_at}
    for key in ("market_cap", "pe"):
        if num(f.get(key)) is not None:
            out[key] = round(num(f[key]) * k, 2)
    if num(f.get("div_yield")) is not None:
        out["div_yield"] = round(num(f["div_yield"]) / k, 2)
    if num(f.get("high52")) is not None and new_p > num(f["high52"]):
        out["high52"] = new_p
    if num(f.get("low52")) is not None and new_p < num(f["low52"]):
        out["low52"] = new_p
    return out


def price_day(members: list[dict]) -> tuple[str | None, int]:
    """(the theme's one price date: the latest close its companies are at, how many of them are at an earlier one) (LIVE7A-003)."""
    days = [str(r["price_at"])[:10] for r in members if r.get("price_at")]
    if not days:
        return None, 0
    top = max(days)
    return top, sum(1 for d in days if d < top)


def company_row(region: str, symbol: str, f: dict | None) -> dict | None:
    """One company's line, from its stored page facts; None when the page holds nothing to show."""
    if not isinstance(f, dict) or not f or f.get("not_company"):
        return None
    base = screens.row(region, symbol, f)
    if not base:
        return None
    old = stock_pages.figures_stale(f)
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
    ev = (cap + debt - cash) / ebitda_amt if None not in (cap, debt, cash) and ebitda_amt and ebitda_amt > 0 and not lender else None
    yoy = f.get("latest_yoy") if isinstance(f.get("latest_yoy"), dict) and f["latest_yoy"].get("basis") == "quarter" else None
    opms = [num(y.get("opm")) for y in years if num(y.get("opm")) is not None]
    # R44: a margin is judged on its own year by the checks of validate_row (verification states), never dropped because another year's
    # margin on the page was beyond ±100% (stock_pages.extreme blanked the EBITDA and net margins, ROE and EV/EBITDA of the whole row)
    shown_e, shown_n = r1(ebitda), r1(net)
    return validate_row({
        "symbol": symbol, "name": base["name"], "year": last["year"] if last else None, "bank": lender, "profile": profile, "sector": base.get("sector"),
        "unit": THEME_CURRENCY.get(region, ("", f.get("unit")))[1] if cur != THEME_CURRENCY.get(region, ("USD",))[0] else f.get("unit"),
        "currency": cur, "fx": {"rate": k, "at": fx_at} if cur != THEME_CURRENCY.get(region, ("USD",))[0] else None,
        "revenue": sales if sales and sales > 0 else None, "profit": profit,
        "other_income": money(num(last.get("other_income"))) if last else None,       # R44: what a net margin above EBITDA is checked against
        "ebitda": shown_e, "net": shown_n,
        # net margin above the EBITDA margin: profit beyond what the business earned before depreciation, interest and tax, so a one-off
        # gain (a demerger, an asset sale) is in it (the owner, 7 Nov: Tata Motors PV's 24.6% net on a 6% EBITDA margin)
        "one_off": one_off(shown_e, shown_n),            # R44: kept only when nothing stored explains it (verify_net)
        # R44: the year's own filed figures, in the filing's unit, that an unusual margin is reconciled with (verify_net)
        # R46: with the statement's lines between EBITDA and net profit the page keeps (operating profit, interest, depreciation, profit
        # before tax, tax rate); a line the page was built without is absent, one the source gives none for is None (bridge, source_lines)
        "filed": {"sales": num(last.get("sales")), "profit": num(last.get("profit")), "opm": num(last.get("opm")),
                  "other_income": num(last.get("other_income")), **{k: num(last.get(k)) for k in BRIDGE_KEYS if k in last},
                  "unit": f.get("unit")} if last else None,
        # R46 (the outside review of the live R45 decks): where the year's figures come from, for each checked figure's source record
        "source": source_record(region, symbol, f, last),
        # the page files the EBITDA margin in whole points (13, never 13.04): printed as 13%, not 13.0% (false precision)
        "ebitda_dp": 0 if opms and all(float(x).is_integer() for x in opms) else 1,
        "roce": None if lender or old else r1(num(f.get("roce"))),
        "cap": cap, "pe": base.get("pe"), "pb": None if old else r1(num(f.get("pb"))),
        "roe": None if old else r1(num(f.get("roe"))),
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
        "years": [{"year": y["year"], "sales": money(num(y.get("sales"))), "profit": money(num(y.get("profit"))), "opm": None if lender else num(y.get("opm")),
                   "other_income": money(num(y.get("other_income"))),
                   **{k: (num(y.get(k)) if k == "tax_pct" else money(num(y.get(k)))) for k in BRIDGE_KEYS if k in y}} for y in years],
        # R30: capital (book equity and debt) for each unit of revenue, how asset-heavy the business is (a layer-vs-layer headline needs it comparable)
        # ex49 (R48): a proxy, its inputs checked: both parts stored, debt and revenue of one year, a positive revenue; what is missing said
        **({} if lender else capital_inputs(cap, num(f.get("pb")), debt, base.get("debt_equity"), sales,
                                            money(num(last.get("debt"))) if last else None, last.get("year") if last else None)),
    }, f, last)


CAPITAL_PROXY = "book equity plus debt over revenue, a proxy for capital needs"      # ex49: how every page that uses it labels it


def capital_inputs(cap, pb, debt, de, sales, year_debt=None, year=None) -> dict:
    """ex49 (R48, the outside review of the live R48 decks: "the capital-intensity check is a proxy: label it as one, validate its inputs"):
    {"capital_rev": capital_per_revenue or None, "capital_missing": [the inputs missing or not usable]}. Both parts must be stored (book
    equity, from the market value over the price to book, else debt over debt to equity; and debt), the debt of the revenue's own year (the
    year's stored debt where the page keeps one), and the year's revenue positive."""
    missing = []
    if num(year_debt) is not None and num(debt) is not None and abs(num(year_debt) - num(debt)) > 0.01 * max(abs(num(debt)), 1.0):
        debt = year_debt                       # the revenue's own year: its stored debt, not a later balance sheet's
    elif num(debt) is None and num(year_debt) is not None:
        debt = year_debt
    if num(debt) is None:
        missing.append("debt")
    eq = cap / pb if cap and pb and pb > 0 else (num(debt) / de if num(debt) and num(de) and de > 0 else None)
    if not eq or eq <= 0:
        missing.append("book equity")
    if not sales or sales <= 0:
        missing.append(f"a positive revenue for {year}" if year else "a positive revenue for the latest full year")
    return {"capital_rev": None if missing else capital_per_revenue(cap, pb, debt, de, sales), "capital_missing": missing}


def capital_per_revenue(cap, pb, debt, de, sales) -> float | None:
    """Capital (book equity plus debt) over the year's revenue: book equity is the market value over the price-to-book (else debt over debt to
    equity); None when neither gives a positive equity or there is no revenue (R30)."""
    debt = num(debt)
    eq = cap / pb if cap and pb and pb > 0 else (debt / de if debt and num(de) and de > 0 else None)
    if not eq or eq <= 0 or not sales or sales <= 0:
        return None
    return round((eq + (debt or 0)) / sales, 2)


# ---------- R30: each figure checked before it is used (the owner's review of the live R28 Telecom deck: "77% net, 42% EBITDA") ----------
# R44 (the outside review of the live R43 decks: Micron's 63.8% net margin, its FY2026 filing's $84,969 million of net income on $133,188
# million of revenue, left out by a ±60% rule; 17 Real estate net margins above their EBITDA margins left out without a look at why): no
# figure is dropped by a cutoff alone. A figure a check finds unusual is reconciled with the company's own stored figures for the same year
# and unit, and given one of three states, kept in one record per company (`verify`: figure -> state, value, flags, why):
#   verified_extreme    unusual, and its own stored components for the year give it: kept in every median; the data-confidence page names
#                       it ("verified against its own filed figures") with the count
#   unverified_extreme  unusual, and its components are missing or don't give it: left out of every median with its reason; a net margin
#                       stays in its table marked †; an EBITDA margin, which every layer comparison reads, shows "–" there and its value
#                       on the data-confidence page
#   invalid             only on an established reporting or calculation defect (a margin on no positive revenue, a unit gap the year's own
#                       lines show, a return on negative capital employed): "–", left out, reason said
# R48 (the outside review of the live R46 decks: Chemicals p.4 marked a net margin invalid because the net profit was positive while the
# ROCE was negative): a sign or scale check alone never makes a figure invalid. Each is reconciled with the year's stored lines first
# (sign_reconcile, page_reconcile; a unit gap, a year's revenue jump and an EBITDA margin above 100% the same way), and its record says which
# explanation the lines give, or that they don't reconcile.
VERIFIED, UNVERIFIED, INVALID = "verified_extreme", "unverified_extreme", "invalid"
NET_UNUSUAL = 60.0            # a net margin beyond ±60% of revenue is reconciled before it is used (R44: never left out for that alone)
EBITDA_UNUSUAL = 90.0         # an EBITDA margin above 90%, outside the models that earn fees or royalties with few costs (EBITDA_FREE)
EBITDA_FREE = {"royalties", "financial_fees", "lending", "underwriting", "life_insurance", "general_insurance", "reinsurance", "property"}
OTHER_INCOME_SHARE = 0.5      # income outside operations above half the year's net profit, where the source carries it
MARGIN_MAX = 100.0            # R44: an EBITDA margin above 100% is operating profit above revenue (invalid); one below −100% is checked
UNIT_GAP = 10.0               # R44: a net profit ten times its revenue or more, either way, is checked as a unit gap (the two in different units)...
UNIT_SLIP = 100.0             # R48: ...and is one when the year's lines show it: the net profit ten times its profit before tax too, or with none
#                               stored a hundredfold its revenue or more (only a unit slip, a hundred or a thousand times, gives that)
YEAR_GAP = 500.0              # R44: a year's revenue 500 times the year before's, or a 500th of it: a unit slip between the years
RECONCILE_TOL = 0.5           # R44: points within which a margin's own components give it
CHECKS = {"sign": "net profit positive, return on capital negative", "sign_page": "net margin and net profit of opposite signs",
          "other_income": "income outside operations above half the net profit", "net_unusual": f"net margin beyond ±{NET_UNUSUAL:.0f}%",
          "ebitda_unusual": f"EBITDA margin above {EBITDA_UNUSUAL:.0f}%", "neg_equity": "return on equity with negative equity",
          "neg_book": "price to book with negative equity",
          "revenue_scale": "revenue above 200 times market value and out of scale with the company's own profit or loss",
          "net_above_ebitda": "net margin above the EBITDA margin", "ebitda_over_max": f"EBITDA margin above {MARGIN_MAX:.0f}% (operating profit above revenue)",
          "ebitda_under_max": f"EBITDA margin below −{MARGIN_MAX:.0f}%", "no_revenue": "a margin on no positive revenue",
          "unit_gap": f"net profit {UNIT_GAP:.0f} times its revenue or more (the two out of scale: a unit gap)",
          "year_gap": f"revenue {YEAR_GAP:.0f} times the year before's, or a {YEAR_GAP:.0f}th of it (a unit gap between years)",
          "neg_capital": "return on capital with negative capital employed", "ebitda_lines": "EBITDA margin that the year's operating profit over revenue doesn't give"}
STATE_WORDS = {VERIFIED: "verified against its own filed figures", UNVERIFIED: "not reconciled", INVALID: "invalid"}
REVENUE_CAP_MAX = 200         # lane n2: a revenue above this many times the market value...
REVENUE_PROFIT_MIN = 0.002    # ...whose years' profit or loss never reached this share of it is out of scale with the filing (a unit slip)


def hold(r: dict, key: str, check: str, state: str = INVALID, why: str = "") -> None:
    """Take a figure out of the row (shown "–", out of every median and ranking), kept with the check(s) it failed and its state (R44:
    invalid, or an EBITDA margin not reconciled) in the company's one record (`verify`)."""
    h = r.setdefault("held", {})
    if key in h:
        h[key]["checks"].append(CHECKS[check])
        return
    if r.get(key) is None:
        return
    h[key] = {"value": r[key], "checks": [CHECKS[check]], "state": state}
    r.setdefault("verify", {})[key] = {"state": state, "value": r[key], "checks": h[key]["checks"], "why": why or CHECKS[check]}
    r[key] = None
    if key == "net":
        r["one_off"] = False
    if key == "ebitda":
        r["ev_ebitda"] = None            # worked out on the EBITDA margin taken out


def in_median(r: dict, key: str):
    """A row's figure as every median and ranking takes it (R44): None when its state is not reconciled (a net margin shown with † but
    left out) or invalid (already "–")."""
    rec = (r.get("verify") or {}).get(key)
    if rec and rec.get("state") != VERIFIED or key == "net" and r.get("one_off"):      # (a row kept before R44 carries only its †)
        return None
    return r.get(key)


def amount(v, unit) -> str:
    """A filed amount in its unit: "$84,969 million", "₹1,234 crore" (R44: what a verified figure is worked out from)."""
    unit = str(unit or "").strip()
    sym, _, rest = unit.partition(" ")
    x = f"{abs(v):,.1f}" if abs(v) < 10 else f"{abs(v):,.0f}"
    return ("−" if v < 0 else "") + (f"{sym}{x} {rest}".strip() if sym in ("$", "₹", "€", "£", "¥") else f"{x} {unit}".strip())


BRIDGE_KEYS = ("op", "interest", "dep", "pbt", "tax_pct")      # R46: the lines between EBITDA and net profit a page keeps (stock_pages.YEAR_KEYS)
TAX_ROUND = 0.5               # R46: the tax rate is filed in whole points: the tax worked out from it is within this share of profit before tax
# R46: each line of a year's statement as a source record names it, in the order a reader works the net margin out
LINE_WORDS = {"sales": "revenue", "profit": "net profit", "op": "operating profit (EBITDA)", "opm": "EBITDA margin", "other_income": "other income",
              "interest": "interest", "dep": "depreciation", "pbt": "profit before tax", "tax_pct": "tax rate"}
# R46: what lifts a net profit above EBITDA, each as the stored lines show it
LIFT_WORDS = {"other_income": "income outside operations", "before_tax": "other items before tax (exceptional items)", "tax_credit": "a tax credit",
              "after_tax": "net profit beyond profit before tax less its tax (a share of associates' or joint ventures' profit, or another item after tax)"}


def bridge(y: dict | None) -> dict | None:
    """R46: a year's net profit above its EBITDA, line by line from the year's stored statement (the outside review of the live R45 decks: 17
    Real estate net margins above their EBITDA margins left out, other income the only line checked). EBITDA is the year's operating profit
    where stored, else revenue times the EBITDA margin (whole points); what lifts the net profit above it is each stored line that does:
    income outside operations, other items before tax (profit before tax beyond EBITDA, other income, interest and depreciation), a tax credit
    (a negative tax on the profit before tax) and net profit beyond profit before tax less its tax (a share of associates or joint ventures,
    or another item after tax). {"ebitda", "from_op", "gap", "items": [(key, amount)], "covered", "missing": [line keys not stored],
    "unkept": [line keys the page was built without]}; "covered" is True when the lifts cover the gap (or there is none, on an exact operating
    profit), False when they don't, None when no line beyond EBITDA is stored. None without a positive revenue, a net profit or an EBITDA."""
    if not isinstance(y, dict):
        return None
    s, p, e, op = num(y.get("sales")), num(y.get("profit")), num(y.get("opm")), num(y.get("op"))
    if s is None or p is None or s <= 0:
        return None
    ebitda = op if op is not None else (s * e / 100 if e is not None else None)
    if ebitda is None:
        return None
    o, i, d, b, t = (num(y.get(k)) for k in ("other_income", "interest", "dep", "pbt", "tax_pct"))
    tol = RECONCILE_TOL * s / 100
    items = []
    if o is not None and o > 0:
        items.append(("other_income", o))
    if b is not None and op is not None and None not in (o, i, d):
        pre = b - (op + o - i - d)
        if pre > tol:
            items.append(("before_tax", pre))
    if b is not None and t is not None:
        tax = b * t / 100
        if tax < 0:
            items.append(("tax_credit", -tax))
        tol += abs(b) * TAX_ROUND / 100
        after = p - (b - tax)
        if after > tol:
            items.append(("after_tax", after))
    gap = p - ebitda
    stored = o is not None or b is not None
    covered = True if op is not None and gap <= 0 else (sum(v for _, v in items) >= gap - tol if stored else None)
    return {"ebitda": ebitda, "from_op": op is not None, "gap": gap, "items": items, "covered": covered,
            "missing": [k for k in ("other_income", "pbt", "tax_pct") if num(y.get(k)) is None],
            "unkept": [k for k in ("op", "pbt", "tax_pct") if k not in y]}


def _and(xs: list) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def missing_said(br: dict | None) -> str:
    """ex49 (R48, the outside review of the live R48 Chemicals deck: 4 net margins above EBITDA left out "pending lines"): which of the
    year's lines a net margin above its EBITDA margin still needs, and why: "still missing: other income, profit before tax and tax rate (the
    stored page was built before profit before tax and tax rate were kept; read again once it is rebuilt)", or "(none stored for the year)"
    where the page keeps the line and the source gives none. The rule is unchanged (bridge); "" when no line is missing."""
    br = br or {}
    gone = [LINE_WORDS[k] for k in br.get("missing") or []]
    if not gone:
        return ""
    old = [LINE_WORDS[k] for k in ("pbt", "tax_pct") if k in (br.get("unkept") or [])]
    if old:
        return (f"still missing: {_and(gone)} (the stored page was built before {_and(old)} {'was' if len(old) == 1 else 'were'} kept; "
                "read again once it is rebuilt)")
    return f"still missing: {_and(gone)} (none stored for the year)"


def gap_explained(sales, profit, opm, other, **lines) -> bool | None:
    """Whether a year's net profit above its EBITDA is covered by its stored lines (R44: income outside operations; R46: with other items
    before tax, a tax credit and items after tax, where the year's statement is stored: bridge); None when no line beyond EBITDA is stored."""
    got = bridge({"sales": sales, "profit": profit, "opm": opm, "other_income": other, **lines})
    return got["covered"] if got else None


def source_record(region: str, symbol: str, f: dict, last: dict | None) -> dict | None:
    """R46 (the outside review of the live R45 decks: "verified extremes are kept, but the explanation does not always give a filing reference
    and a traceable extraction record"): where a company's year of figures comes from, as its stored page holds it: the document (an Indian
    company's annual results, consolidated or standalone; a US company's annual report filed with the SEC, its form and filing day where the
    page keeps them), the period, the page the figures were read from and the day it was built, the unit. A part the page doesn't hold is said
    to be not stored, never filled in."""
    if not isinstance(f, dict) or not last:
        return None
    if region == "US":
        form, filed = f.get("annual_form"), str(f.get("annual_filed") or "")[:10] or None
        doc = (f"{form} annual report filed with the SEC" if form else "annual report filed with the SEC (its form is not stored on the page)")
    else:
        basis, filed = f.get("basis"), None
        doc = (f"annual results, {basis}" if basis in ("consolidated", "standalone") else
               "annual results (consolidated or standalone is not stored on the page)")
    return {"document": doc, "period": last.get("year"), "filed": filed, "page": stock_pages.path(region, symbol),
            "built": str(f.get("built_at") or "")[:10] or None, "unit": f.get("unit")}


def source_lines(fd: dict | None) -> list[dict]:
    """R46: the year's statement lines a figure is worked out from, as stored, in the filing's unit (the tax rate in %): each with its name
    and value, a line the source gives none for or the page was built without said "not stored"."""
    fd = fd or {}
    out = []
    for k in ("sales", "profit", "op", "opm", "other_income", "interest", "dep", "pbt", "tax_pct"):
        v = num(fd.get(k))
        if v is None and k in ("op", "interest", "dep") and k not in fd:
            continue                      # (a page built before R46 keeps none of these; the record says so through pbt and tax_pct)
        out.append({"key": k, "line": LINE_WORDS[k], "value": v, **({"pct": True} if k in ("opm", "tax_pct") else {})})
    return out


def year_gap(r: dict) -> bool:
    """Whether the stored years' revenue jumps YEAR_GAP times either way between consecutive years (a unit slip between them, R44)."""
    s = [num(y.get("sales")) for y in r.get("years") or []]
    return any(a and b and a > 0 and b > 0 and max(a / b, b / a) >= YEAR_GAP for a, b in zip(s, s[1:]))


def capital_employed(f: dict, fd: dict | None = None) -> dict | None:
    """R48: the capital a ROCE is worked out on, as the stored page gives it: book equity (book value per share times the shares in issue, the
    market value over the price; else the market value over the price to book) plus debt (the latest balance sheet's, else the year's).
    {"equity", "debt", "value"}, each in the page's unit; None when no equity can be worked out (a page reporting in another currency than
    its market value says nothing here)."""
    if not isinstance(f, dict) or f.get("report_currency"):
        return None
    bv, cap, price, pb = num(f.get("book_value")), num(f.get("market_cap")), num(f.get("price")), num(f.get("pb"))
    debt = num(f.get("debt"))
    if debt is None:
        debt = num((fd or {}).get("debt")) if fd else None
    if debt is None:
        ys = f.get("years") or []
        debt = num(ys[-1].get("debt")) if ys and isinstance(ys[-1], dict) else None
    eq = bv * cap / price if bv is not None and cap and price and price > 0 else (cap / pb if cap and pb and pb > 0 else None)
    if eq is None:
        return None
    return {"equity": eq, "debt": debt or 0.0, "value": eq + (debt or 0.0)}


def year_ebit(y: dict | None) -> dict | None:
    """R48: a year's operating profit before interest and tax, from its stored lines, both ways a ROCE may take it: "value", with other
    income in it (profit before tax plus interest), and "operating", before other income (operating profit, or revenue times the EBITDA
    margin, less depreciation; the EBITDA alone when it is a loss, which depreciation only deepens: "loss_only"). Each None when the lines
    don't give it; None when neither is given."""
    if not isinstance(y, dict):
        return None
    s, e, op, dep, b, i = (num(y.get(k)) for k in ("sales", "opm", "op", "dep", "pbt", "interest"))
    ebit = b + i if b is not None and i is not None else None
    ebitda = op if op is not None else (s * e / 100 if s and s > 0 and e is not None else None)
    oper, how, only = None, None, False
    if ebitda is not None and dep is not None:
        oper, how = ebitda - dep, ("operating profit" if op is not None else "EBITDA") + " less depreciation"
    elif ebitda is not None and ebitda < 0:
        oper, how, only = ebitda, "EBITDA, before depreciation", True
    if ebit is None and oper is None:
        return None
    return {"value": ebit, "how": "profit before tax plus interest" if ebit is not None else None, "operating": oper, "operating_how": how,
            "loss_only": only, "other_income": num(y.get("other_income"))}


def sign_reconcile(r: dict, f: dict) -> dict:
    """R48 (the outside review of the live R46 decks: "net profit positive while ROCE is negative alone does not prove a wrong figure"): a
    positive net profit beside a negative ROCE reconciled with the year's stored lines (its EBIT, the capital employed and the other years).
    A ROCE is negative only when the EBIT and the capital employed are of opposite signs, so the lines give one of:
      negative_capital  the capital employed is negative (book equity below minus the debt): a return on it means nothing (the ROCE invalid)
      operating_loss    the year's EBIT is a loss (with other income in it, or before it), lifted to a net profit by the lines below it
                        (other income, items before or after tax, a tax credit): the ROCE agrees with the year's operating figures
      other_year        the year's EBIT and capital employed are positive and another stored year's EBIT is a loss: the ROCE is not of the
                        year (not reconciled)
      lines_disagree    the year's EBIT and capital employed are positive and no stored year is a loss (the ROCE not reconciled)
      not_stored        the lines that would tell are not stored (the net margin not reconciled)
    {"kind", "why", "ebit", "ebit_how", "capital", "roce", "year"}: amounts in the filing's unit."""
    fd = r.get("filed") or {}
    u, yr, roce = fd.get("unit"), r.get("year") or "the latest year", r.get("roce")
    ce = capital_employed(f, fd)
    eb = year_ebit(fd)
    cap_words = (f"capital employed of {amount(ce['value'], u)} (book equity {amount(ce['equity'], u)} and debt {amount(ce['debt'], u)})" if ce else "")
    out = {"roce": roce, "year": yr, "capital": ce, "ebit": None, "ebit_how": None}
    if ce and ce["value"] < 0:
        return {**out, "kind": "negative_capital", "why": f"the ROCE of {pts(roce)} is on {cap_words}, below zero: a return on negative capital "
                                                          "employed means nothing, and it does not question the net profit"}
    if eb and eb["value"] is not None and eb["value"] < 0:
        return {**out, "ebit": eb["value"], "ebit_how": eb["how"], "kind": "operating_loss",
                "why": f"the ROCE of {pts(roce)} agrees with {yr}'s operating loss: EBIT {amount(eb['value'], u)} ({eb['how']}), lifted to a net "
                       "profit by a tax credit or items after tax"}
    if eb and eb["operating"] is not None and eb["operating"] < 0:
        o = eb["other_income"]
        return {**out, "ebit": eb["operating"], "ebit_how": eb["operating_how"], "kind": "operating_loss",
                "why": f"the ROCE of {pts(roce)} agrees with {yr}'s operating loss before other income: {amount(eb['operating'], u)} ({eb['operating_how']})"
                       + (f", lifted to a net profit by other income of {amount(o, u)} and the lines below it" if o and o > 0 else
                          ", lifted to a net profit by the lines below it")}
    ebit, how = (eb["value"], eb["how"]) if eb and eb["value"] is not None else ((eb["operating"], eb["operating_how"]) if eb else (None, None))
    if ebit is not None and ce and ce["value"] > 0:
        others = []
        for y in (f.get("years") or [])[:-1]:
            x = year_ebit(y) if isinstance(y, dict) else None
            v = x and (x["value"] if x["value"] is not None else x["operating"])
            if v is not None and v < 0:
                others.append(f"{y.get('year')} EBIT {amount(v, u)}")
        gives = f"{yr}'s lines give EBIT {amount(ebit, u)} ({how}) on {cap_words}, a return of {pts(ebit / ce['value'] * 100)}"
        out = {**out, "ebit": ebit, "ebit_how": how}
        if others:
            return {**out, "kind": "other_year", "why": f"{gives}, not the ROCE of {pts(roce)}, and another stored year was a loss ({', '.join(others[-2:])}): "
                                                        "the ROCE is not of the year's lines"}
        return {**out, "kind": "lines_disagree", "why": f"{gives}, not the ROCE of {pts(roce)}: the ROCE does not reconcile with the year's lines"}
    gone = ([] if ebit is not None else ["profit before tax and interest, or depreciation"]) + ([] if ce else ["book value"]) or ["capital employed above zero"]
    return {**out, "ebit": ebit, "ebit_how": how, "kind": "not_stored",
            "why": f"positive net profit beside a ROCE of {pts(roce)}: no {' or '.join(gone)} stored for {yr} to reconcile them"}


def page_reconcile(r: dict, f: dict, page: float) -> dict:
    """R48: a net margin of the other sign from the page's own net margin, reconciled with the stored years: the page's figure is the net
    profit over revenue of one of its years (a different year from the row's), or of none. {"ok", "why", "year"}."""
    fd = r.get("filed") or {}
    u = fd.get("unit")
    for y in reversed(f.get("years") or []):
        if not isinstance(y, dict) or y.get("year") == r.get("year"):
            continue
        s, p = num(y.get("sales")), num(y.get("profit"))
        if s and s > 0 and p is not None and abs(p / s * 100 - page) <= RECONCILE_TOL:
            return {"ok": True, "year": y.get("year"), "why": f"the page's own net margin of {pts(page)} is {y.get('year')}'s (net profit {amount(p, u)} "
                                                             f"over revenue {amount(s, u)}), another year"}
    return {"ok": False, "year": None, "why": f"the page's own net margin of {pts(page)} is of the other sign and no stored year's net profit over "
                                              "revenue gives it: not reconciled"}


FINANCIAL_PROFILES = ("bank", "lender", "insurer")


def other_income_words(r: dict) -> str:
    """rv51 (R51): what a year's other income is called for this company: a bank's or lender's non-interest income (its fees, commissions
    and treasury gains are part of its operations), an insurer's other income, else income outside operations."""
    prof = r.get("profile") or ("lender" if r.get("bank") else "other")
    if prof in ("bank", "lender"):
        return "non-interest income (other income: fees, commissions and treasury gains)"
    return "other income" if prof in FINANCIAL_PROFILES else "income outside operations"


def checks_word(k: str, r: dict) -> str:
    """CHECKS[k], with a financial company's other income in its own terms (rv51)."""
    if k == "other_income" and other_income_words(r) != "income outside operations":
        return CHECKS[k].replace("income outside operations", other_income_words(r).split(" (")[0])
    return CHECKS[k]


def verify_net(r: dict) -> None:
    """R44: a net margin a check finds unusual (beyond ±NET_UNUSUAL%, above the year's EBITDA margin, or with income outside operations
    above half the net profit) reconciled with the company's own filed figures for the same year (`filed`: revenue, net profit, EBITDA
    margin and income outside operations as the page stores them, in the filing's unit). Verified when the year's net profit over its
    positive revenue gives the margin, and it sits at or below the year's EBITDA margin or the stored income outside operations covers the
    profit above EBITDA; not reconciled when a component is missing or doesn't give it; invalid on a unit gap. Worked out again when the
    EBITDA margin it is set against is taken out (validate_model)."""
    rec = (r.get("verify") or {}).get("net")
    if rec and (rec["state"] == INVALID or "net" in (r.get("held") or {})):      # R48: a held figure keeps its record (not reconciled too)
        return
    r.get("verify", {}).pop("net", None)
    r["one_off"] = False
    net, fd = r.get("net"), r.get("filed") or {}
    if net is None:
        return
    e = r.get("ebitda")
    s, p, o = num(fd.get("sales")), num(fd.get("profit")), num(fd.get("other_income"))
    sg, sp = r.get("sign"), r.get("sign_page")
    flags = (["net_unusual"] if abs(net) > NET_UNUSUAL else []) + (["net_above_ebitda"] if one_off(e, net) else []) \
        + (["other_income"] if o is not None and p and p > 0 and o > p * OTHER_INCOME_SHARE else []) \
        + (["sign"] if sg else []) + (["sign_page"] if sp else [])
    if not flags:
        return
    if s is not None and p is not None and s > 0 and abs(p) >= UNIT_GAP * s:
        # R48: a unit gap is established only when the filing's own lines show it: the net profit UNIT_GAP times its own profit before tax
        # too, or, with no profit before tax stored, UNIT_SLIP times its revenue or more; a profit its profit before tax gives (a gain on a sale)
        # is checked as any other
        b = num(fd.get("pbt"))
        if (abs(p) >= UNIT_GAP * abs(b)) if b else abs(p) >= UNIT_SLIP * s:
            return hold(r, "net", "unit_gap", why=f"{CHECKS['unit_gap']}: net profit {amount(p, fd.get('unit'))} on revenue {amount(s, fd.get('unit'))}"
                        + (f" and profit before tax {amount(b, fd.get('unit'))}: the year's stored lines don't give it" if b else "; no stored line gives it"))
    # R48: a year's revenue YEAR_GAP times the year before's no longer makes the margin invalid: the margin is the year's own net profit over
    # its own revenue, so a unit change between years doesn't touch it (the growth across the two years is left out: series_break)
    u, yr = fd.get("unit"), r.get("year") or "the latest year"
    base = (f"net profit {amount(p, u)} over revenue {amount(s, u)}, {yr}: {pts(net)}" if s and p is not None else "")
    why, ok, bits = [], True, {}
    if s is None or p is None or s <= 0:
        ok, why = False, ["the year's net profit or revenue is not stored"]
    elif abs(p / s * 100 - net) > RECONCILE_TOL:
        ok, why = False, [f"net profit over revenue gives {pts(p / s * 100)}, not {pts(net)}"]
    elif "net_above_ebitda" in flags:
        br = bridge(fd)
        need = br["gap"] if br else p - s * e / 100
        lifts = [f"{LIFT_WORDS[k]} of {amount(v, u)}" for k, v in (br or {}).get("items") or []]
        said = (", ".join(lifts[:-1]) + " and " + lifts[-1]) if len(lifts) > 1 else "".join(lifts)
        ebit = f"its {gpts(e)} EBITDA margin" + (f" (operating profit {amount(br['ebitda'], u)})" if br and br["from_op"] else "")
        bits = {"bridge": {"gap": need, "ebitda": br["ebitda"] if br else None, "from_op": bool(br and br["from_op"]),
                           "items": [{"key": k, "value": v} for k, v in (br or {}).get("items") or []], "missing": (br or {}).get("missing") or [],
                           "unkept": (br or {}).get("unkept") or []}}
        if br and br["covered"] and need <= 0:
            why.append(f"at or below {ebit}: net profit {amount(p, u)} against operating profit {amount(br['ebitda'], u)}")
        elif br and br["covered"]:
            why.append(f"above {ebit} by {amount(need, u)}, covered by {said}")
        else:
            ok = False
            gone = missing_said(br)               # ex49 (R48): which line is still missing, and why, per company
            why.append(f"net profit {amount(need, u)} above EBITDA ({pts(net)} net, {gpts(e)} EBITDA)" + (
                f"; {said} covers part of it" if lifts else "") + (
                "; no income outside operations, exceptional gain, tax credit or share of associates is stored to explain it"
                + (f"; {gone}" if gone else "") if br and br["covered"] is None else
                f"; {gone}" if gone else "; the year's stored lines don't add up to it"))
    elif "net_unusual" in flags:
        if e is None:
            ok, why = False, ["no EBITDA margin is stored for the year to check it against"]
        else:
            why.append(f"at or below its {gpts(e)} EBITDA margin" if net <= e else "")
    if ok and "other_income" in flags:          # the one-off that explains it, said
        # rv51 (R51, the outside review of the live Release 49 Private banks deck: twelve verified cases said "income outside operations" of a
        # bank's fee and treasury income): a financial company's other income in the accounting terms that fit it (other_income_words)
        why.append(f"{other_income_words(r)} of {amount(o, u)} is {o / p * 100:.0f}% of the net profit")
    if sg:                                      # R48: what the year's lines show of a positive net profit beside a negative ROCE
        why.append(sg["why"])
        ok = ok and sg["kind"] != "not_stored"
    if sp:                                      # R48: and of a net margin of the other sign from the page's own
        why.append(sp["why"])
        ok = ok and sp["ok"]
    why = [w for w in why if w]
    # rv51 (R51: "verified" must mean the calculation, accounting basis and supporting statement lines were checked): how far a kept figure
    # was checked: "lines" when each check that flagged it was answered by the year's statement lines (the lines between EBITDA and net
    # profit, the EBITDA margin it sits under, the lines a sign check reads), "arithmetic" when only net profit over revenue was worked out
    # again (a large other income, said and not explained)
    lined = [k for k in flags if k != "other_income"]
    checked = "lines" if lined and (("net_unusual" not in flags or e is not None) and ("net_above_ebitda" not in flags or bool(bits))) else "arithmetic"
    r.setdefault("verify", {})["net"] = {"state": VERIFIED if ok else UNVERIFIED, "value": net, "checks": [checks_word(k, r) for k in flags],
                                         **({"checked": checked} if ok else {}),
                                         "why": "; ".join(([base] if ok and base else []) + why), **(bits if "net_above_ebitda" in flags else {}),
                                         **({"sign": sg} if sg else {}), **({"sign_page": sp} if sp else {})}
    r["one_off"] = not ok                       # shown with †, out of every median (in_median)


def verify_ebitda(r: dict) -> None:
    """R44: an EBITDA margin beyond ±MARGIN_MAX%: above it, operating profit above revenue (invalid); below it, costs over twice revenue,
    verified when the year's net margin is a loss too (the two agree), else not reconciled."""
    e = r.get("ebitda")
    if e is None or abs(e) <= MARGIN_MAX:
        return
    if e > MARGIN_MAX:
        # R48: operating profit above revenue is invalid only when the year's own lines don't give the margin (a calculation defect); as filed,
        # it is not reconciled: shown on the data-confidence page with its lines, out of every median
        fd = r.get("filed") or {}
        s_, op = num(fd.get("sales")), num(fd.get("op"))
        u = fd.get("unit")
        if s_ and s_ > 0 and op is not None and abs(op / s_ * 100 - e) > RECONCILE_TOL + ROUNDING:
            return hold(r, "ebitda", "ebitda_lines", why=f"{CHECKS['ebitda_lines']}: operating profit {amount(op, u)} over revenue {amount(s_, u)} "
                                                          f"gives {pts(op / s_ * 100)}, not {gpts(e)}")
        return hold(r, "ebitda", "ebitda_over_max", state=UNVERIFIED,
                    why=f"{CHECKS['ebitda_over_max']}" + (f", as filed: operating profit {amount(op, u)} on revenue {amount(s_, u)}" if s_ and op is not None
                                                          else "; no operating profit is stored for the year to check it against") + "; not reconciled")
    net = r.get("net")
    if net is not None and net < 0:
        r.setdefault("verify", {})["ebitda"] = {"state": VERIFIED, "value": e, "checks": [CHECKS["ebitda_under_max"]], "checked": "lines",
                                                "why": f"a loss at both levels, {gpts(e)} EBITDA and {pts(net)} net, {r.get('year') or 'the latest year'}"}
        return
    hold(r, "ebitda", "ebitda_under_max", state=UNVERIFIED, why=f"{CHECKS['ebitda_under_max']} with no net loss stored for the year to agree with it")


def validate_row(r: dict, f: dict, last: dict | None) -> dict:
    """The checks a company's figures pass before they are used (R30), each figure given its state (R44): sign consistency (a positive net
    profit beside a negative return on capital; the net margin's sign against the page's own), each reconciled with the year's stored lines
    (R48: sign_reconcile, page_reconcile, never invalid for the signs alone), a margin on no positive revenue and a return on equity or price to
    book on negative equity (invalid: a calculation defect), a revenue out of scale with the market value and the company's own profit (not
    reconciled; invalid when the stored years show the slip), an EBITDA margin beyond ±MARGIN_MAX% (verify_ebitda), and an unusual net margin
    reconciled with its own filed figures (verify_net). (An EBITDA margin above EBITDA_UNUSUAL% is checked with the company's model:
    validate_model.)"""
    prof, net = r.get("profit"), r.get("net")
    # R48: a positive net profit beside a negative ROCE, and a net margin of the other sign from the page's own, are reconciled with the year's
    # stored lines (sign_reconcile, page_reconcile) and the net margin's record says what they show (verify_net); a ROCE is taken out only on
    # negative capital employed (invalid) or when the year's lines give it the other sign (not reconciled)
    r.pop("sign", None)
    r.pop("sign_page", None)
    if net is not None and prof is not None and prof > 0 and (r.get("roce") or 0) < 0:
        sg = r["sign"] = sign_reconcile(r, f)
        if sg["kind"] == "negative_capital":
            hold(r, "roce", "neg_capital", why=sg["why"])
        elif sg["kind"] in ("other_year", "lines_disagree"):
            hold(r, "roce", "sign", state=UNVERIFIED, why=sg["why"])
    page = num(f.get("net_margin"))
    if net is not None and page is not None and page * net < 0:
        r["sign_page"] = page_reconcile(r, f, page)
    s_ = num((last or {}).get("sales"))
    if s_ is not None and s_ <= 0:              # R44: a margin on revenue of zero or below
        hold(r, "ebitda", "no_revenue")
        hold(r, "net", "no_revenue")
    if revenue_out_of_scale(r):
        # lane n2 (the outside review of the live R33 decks: Tigo Energy, $103.5 bn of revenue beside a $57 m market value, its filing's
        # revenue tagged a thousand times too large): the revenue is kept out of every sum, median and ranking until it is read again,
        # with the margins and the capital worked out on it; the data-confidence page names the company and the check
        # R48: invalid only when the stored years show the slip (the revenue jumped YEAR_GAP times on the year before); otherwise not reconciled
        slip = year_gap(r)
        state = INVALID if slip else UNVERIFIED
        why = CHECKS["revenue_scale"] + ("; the stored years' revenue jumps 500 times or more between two years (a unit gap)" if slip else
                                         "; not reconciled: no stored line shows whether the revenue or the market value is out of scale")
        r["held_revenue"] = {"value": r["revenue"], "checks": [CHECKS["revenue_scale"]], "state": state}
        r["revenue"], r["capital_rev"] = None, None
        hold(r, "ebitda", "revenue_scale", state=state, why=why)
        hold(r, "net", "revenue_scale", state=state, why=why)
    bv = num(f.get("book_value"))
    if bv is not None and bv < 0 or f.get("net_worth_negative"):
        hold(r, "roe", "neg_equity")
        hold(r, "pb", "neg_book")
    verify_ebitda(r)
    verify_net(r)
    return r


def revenue_out_of_scale(r: dict) -> bool:
    """Whether a row's revenue is more than REVENUE_CAP_MAX times its market value and no year's profit or loss on its page reached
    REVENUE_PROFIT_MIN of it: a figure out of scale with the company's own filing (lane n2), not a thin-margin business."""
    rev, cap = num(r.get("revenue")), num(r.get("cap"))
    if not rev or not cap or cap <= 0 or rev <= REVENUE_CAP_MAX * cap:
        return False
    sizes = [abs(num(y.get("profit"))) for y in r.get("years") or [] if num(y.get("profit")) is not None]
    sizes += [abs(num(r.get("profit")))] if num(r.get("profit")) is not None else []
    return bool(sizes) and max(sizes) < REVENUE_PROFIT_MIN * rev


def validate_model(r: dict, family: str) -> None:
    """An EBITDA margin above EBITDA_UNUSUAL% outside the models whose costs are few (EBITDA_FREE) is not reconciled (R30; R44: its state
    said): the stored years hold the margin as a ratio, with no operating profit to check it against. The net margin set against it is
    checked again (verify_net)."""
    if r.get("ebitda") is not None and r["ebitda"] > EBITDA_UNUSUAL and family not in EBITDA_FREE:
        hold(r, "ebitda", "ebitda_unusual", state=UNVERIFIED,
             why=f"{CHECKS['ebitda_unusual']} for a company that does not earn fees or royalties; the stored years hold the margin as a ratio, "
                 "with no operating profit to check it against")
        verify_net(r)


# gl50 (R50, the rotating review of the live Biotech deck: Merck, Novartis and Amgen in "Clinical-stage platform developers", the headline's top
# layer at 35.0%): a layer whose name or description says its companies have no products on sale yet
PRE_REVENUE = r"\bpre-?revenue\b|\bclinical[- ]stage\b|\bdevelopment[- ]stage\b|\bpre-?commercial\b|\bpre-?clinical\b|\bno (?:approved )?products? on (?:the )?market\b"
STAGE_FACTOR = 10.0           # ...holds no company with an operating profit and revenue this many times the layer's median company's


def stage_check(layer: dict, rows: list[dict]) -> list[str]:
    """gl50 (R50): in a layer whose name or description states its companies are clinical-stage or pre-revenue (PRE_REVENUE), a company with a
    positive EBITDA margin and revenue STAGE_FACTOR times the layer's median company's or more is a commercial business, not of the layer's
    stage: listed, left out of its figures as another business ("model_out" other), with why ("stage_out"). The symbols marked."""
    said = " ".join(str(layer.get(k) or "") for k in ("layer", "was", "description"))
    m = re.search(PRE_REVENUE, said, re.I)
    if not m:
        return []
    revs = sorted(r["revenue"] for r in rows if (r.get("revenue") or 0) > 0)
    if len(revs) < 3:
        return []
    mid = revs[len(revs) // 2]
    out = []
    for r in rows:
        if (r.get("revenue") or 0) >= STAGE_FACTOR * mid and (r.get("ebitda") or 0) > 0:
            r["model_out"], r["out_why"] = "other", "stage"
            r["stage_out"] = (f"an operating profit (EBITDA margin {pts(r['ebitda'])}) on revenue {STAGE_FACTOR:g} times the layer's median company's "
                              f"or more: a commercial company, not of the {m.group(0).lower()} the layer's name or description states")
            out.append(r["symbol"])
    return out


def figure_states(rows: list[dict]) -> list[dict]:
    """Every figure a check looked at, with its state (R44), for the data-confidence page and the dive: company, figure, value, state,
    the checks that flagged it and why it is in or out, and (R46) its source record: the document, period and stored page, and the statement
    lines with their values and unit, so a reader can work the figure out again. One list, so every page counts the same records."""
    return [{"symbol": r["symbol"], "name": r["name"], "key": k, "value": x["value"], "state": x["state"], "checks": list(x.get("checks") or []),
             "why": x.get("why") or "", **({"ebitda": r.get("ebitda"), "net": r.get("net")} if k == "net" else {}),
             **({"checked": x["checked"]} if x.get("checked") else {}),
             # R46: its source record: the document, period and page the year's figures come from, and the statement lines used, as stored
             "source": r.get("source"), "lines": source_lines(r.get("filed")), **({"bridge": x["bridge"]} if x.get("bridge") else {}),
             # R48: what the year's lines show of a sign check (its EBIT and capital employed, or the page's own net margin's year)
             **({"sign": x.get("sign") or r.get("sign")} if (x.get("sign") or (k == "roce" and r.get("sign"))) else {}),
             **({"sign_page": x["sign_page"]} if x.get("sign_page") else {})}
            for r in rows if r.get("status") != "unverified" for k, x in (r.get("verify") or {}).items()]


def held_rows(rows: list[dict]) -> list[dict]:
    """Every figure taken out of its row ("–") by a check, for the data-confidence page: company, figure, value, the checks it failed and
    its state (R44: invalid, or an EBITDA margin not reconciled)."""
    return [{"symbol": r["symbol"], "name": r["name"], "key": k, "value": h["value"], "checks": h["checks"], "state": h.get("state", INVALID)}
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
    lm = layer.get("model") if isinstance(layer.get("model"), dict) else {}
    # ex49 (R48): why it is left out, precisely (theme_base.by_model's "out_why"), with the layer's own way of earning to state both models;
    # one in the figures as a seller of goods of its own design says so ("own_goods")
    out = {k: x for k, x in (("out_why", c.get("out_why")), ("layer_model", lm.get("id")), ("layer_family", lm.get("family")),
                             ("unfit_why", (c.get("unfit") or {}).get("why") if c.get("out_why") == "unfit" else "")) if x} \
        if c.get("model_out") else {}
    return {"model": c.get("model") or "", "model_tags": list(c.get("model_tags") or []), "model_confidence": c.get("model_confidence") or "",
            **({"model_out": c.get("model_out")} if c.get("model_out") else {}), **({"on_industry": True} if c.get("on_industry") else {}),
            **({"own_goods": True} if c.get("own_goods") else {}), **({"by_words": True} if c.get("by_words") else {}), **out}


def refit_of(layer: dict, sym: str) -> dict:
    """gl50 (R50): {"refit": {"from", "why"}} for a company moved by what its layer is (theme_base.definition_fit), or {}."""
    c = next((c for c in layer.get("companies") or [] if c.get("ticker") == sym), None) or {}
    r = c.get("refit")
    return {"refit": {"from": str(r.get("from") or ""), "why": str(r.get("why") or "")}} if isinstance(r, dict) and r.get("why") else {}


# ---------- one record of who is in a layer's calculations (lane m1: the outside review of the live R32 decks, "15 equipment companies" in
# the value-chain table beside "14 of 17" on the layer's page and in the appendix) ----------
# why a listed company is left out of its layer's calculations, in the order the pages say them
CALC_WHY = ("other business", "way of earning not shown", "not confirmed", "no revenue figure")


# ex49 (R48, the outside review of the live Release 48 decks: lululemon left out of "Apparel and consumer brand owners" as "another business";
# "distinguish a real difference in revenue model from insufficient evidence or partial comparability; never use them interchangeably"):
# each left-out company's one reason category, in the order the pages say them, and what exactly it is (calc_record "kind", "label", "detail")
CALC_KINDS = ("different revenue model", "another business", "insufficient evidence", "not confirmed in the theme", "no figure stored")
WHY_KIND = {"other business": "different revenue model", "way of earning not shown": "insufficient evidence", "not confirmed": "not confirmed in the theme",
            "no revenue figure": "no figure stored"}         # a kept key (CALC_WHY) -> its kind, for a record kept before ex49
KIND_SAID = {"different revenue model": "it earns another way than the layer's companies", "another business": "its own words describe another business",
             "insufficient evidence": "its evidence doesn't show clearly how it earns", "not confirmed in the theme": "its own words don't show this work",
             "no figure stored": "no figure of it is stored"}
EVIDENCE_GAP = {"no_words": ("not checked yet: no description of its own is stored", "not checked yet, no description of its own"),      # gl50
                "no_model": ("its own words don't state how it earns", "its words don't state how it earns"),
                "weak": ("its evidence shows how it earns only weakly (low confidence)", "how it earns read only weakly"),
                # gl52 (R52): looked for in every source and none found (theme_base.place_rest "none_found"), never "not checked yet"
                "none_found": ("no description of it was found in any source (its profile page, an encyclopedia, its own filings)",
                               "no description found in any source")}


def lower_kept(text: str) -> str:
    """gl52 (R52, the rotating review of Release 51: "managed and outsourced it services"): a label in lower case inside a sentence, its
    acronyms kept as written (IT, EPC, SaaS)."""
    return " ".join(w if sum(ch.isupper() for ch in w) >= 2 else w.lower() for w in str(text or "").split())


def _model_name(mid: str, family: str = "") -> str:
    from .theme_check import FAMILIES, MODELS
    return lower_kept(MODELS[mid][1] if mid in MODELS else FAMILIES.get(family, ("",))[0] or "")


def _model_title(mid: str, family: str = "") -> str:
    from .theme_check import FAMILIES, MODELS
    return MODELS[mid][1] if mid in MODELS else FAMILIES.get(family, ("",))[0] or ""


def _model_what(mid: str, family: str = "") -> str:
    from .theme_check import FAMILIES, MODELS
    return MODELS[mid][2] if mid in MODELS else FAMILIES.get(family, ("", ""))[1]


def out_reason(r: dict) -> dict:
    """ex49 (R48): a left-out company's precise reason: {"kind": one of CALC_KINDS, "label": the kind with what exactly (as a roll groups
    companies), "detail": one sentence}. A different revenue model states both models, the company's and the layer's; insufficient evidence
    says what is missing; another business, that its own words describe another business than its official industry files it under."""
    if r.get("status") == "unverified":
        return {"kind": "not confirmed in the theme", "label": "not confirmed in the theme",
                "detail": "its own words are not confirmed to show the theme's work, so it is in no figure of the theme"}
    why, mid, lid, lf = r.get("out_why") or "", r.get("model") or "", r.get("layer_model") or "", r.get("layer_family") or ""
    if r.get("model_out") == "other":
        if why == "off_industry":
            return {"kind": "another business", "label": "another business than its official industry",
                    "detail": "its own words describe another business than the one its official industry files it under"}
        if why == "unfit":             # gl52 (R52): its own words and official industry are not of what the layer is
            return {"kind": "another business", "label": "another business than the layer's",
                    "detail": r.get("unfit_why") or "its own words and its official industry are not of what the layer is"}
        if why == "stage" and r.get("stage_out"):         # gl50 (R50): a commercial company in a clinical-stage or pre-revenue layer
            return {"kind": "another business", "label": "another business: a commercial company, not of the layer's stage", "detail": r["stage_out"]}
        if mid and (lid or lf):
            return {"kind": "different revenue model", "label": f"different revenue model ({_model_name(mid)}, the layer's {_model_name(lid, lf)})",
                    "detail": f"the way of earning of “{_model_title(mid)}” ({_model_what(mid)}), not the layer's, that of "
                              f"“{_model_title(lid, lf)}” ({_model_what(lid, lf)})"}
        if mid:
            return {"kind": "different revenue model", "label": f"different revenue model ({_model_name(mid)})",
                    "detail": f"the way of earning of “{_model_title(mid)}” ({_model_what(mid)}), not the layer's companies'"}
        return {"kind": "different revenue model", "label": "different revenue model",
                "detail": "it earns another way than the layer's companies"}
    if r.get("model_out"):
        full, short = EVIDENCE_GAP.get(why) or ("its evidence doesn't show clearly how it earns", "")
        # gl52 (R52, the rotating review of Release 51: Labcorp, Quest and Fiserv "read as managed and outsourced it services, low
        # confidence"): a low-confidence model is no fact, so it is never printed as what the company was read as
        return {"kind": "insufficient evidence", "label": "insufficient evidence" + (f" ({short})" if short else ""), "detail": full}
    return {"kind": "no figure stored", "label": "no figure stored", "detail": "no revenue or other figure of it is stored"}


def calc_record(r: dict) -> dict:
    """One company's place in its layer's calculations: {"in": True, "why": ""}, or {"in": False, "why": one of CALC_WHY}. In: confirmed, how
    it earns shown and of the layer's kind, with a figure (a company with neither revenue nor any figure a median is taken of has none).
    Worked out once (layer_block) and kept on the company's row as "calc": every count of a layer (its "n", the value chain's and the
    economics' tables, the layer page's head, its roll and the appendix's) is taken from these rows, never worked out again by a page.
    ex49 (R48): a left-out one also carries its precise reason (out_reason: "kind", "label", "detail")."""
    if r.get("status") == "unverified":
        why = "not confirmed"
    elif r.get("model_out"):
        why = "other business" if r["model_out"] == "other" else "way of earning not shown"
    elif r.get("revenue") is None and not any(r.get(k) is not None for k in STAT_KEYS + tuple(sector_metrics.KEYS)):
        why = "no revenue figure"
    else:
        return {"in": True, "why": ""}
    return {"in": False, "why": why, **out_reason(r)}


def calc_of(c: dict) -> dict:
    """A company row's kept record (calc_record), worked out for a row of a dive kept before the record was."""
    rec = c.get("calc")
    if isinstance(rec, dict) and "in" in rec:
        return rec if rec["in"] or rec.get("kind") else {**rec, **out_reason(c)}      # ex49: a record kept before its precise reason
    return calc_record(c)


def in_calc(c: dict) -> bool:
    """Whether a company is in its layer's calculations (its kept record)."""
    return bool(calc_of(c)["in"])


def layer_counts(layer: dict) -> dict:
    """A layer's counts from its one list of rows: {"listed": every company its page lists, "n": those in its calculations, "out": {why: how
    many}}: listed = n + the left out, by construction."""
    from collections import Counter
    recs = [calc_of(c) for c in layer.get("companies") or []]
    return {"listed": len(recs), "n": sum(1 for x in recs if x["in"]), "out": dict(Counter(x["why"] for x in recs if not x["in"]))}


def one_row_each(rows: list[dict]) -> list[dict]:
    """One company listed under two symbols (a second listing or an old symbol with the same name and the same filed figures) kept once, so it
    is never counted, summed or shown twice (R36: the live R33 Retail deck printed "Leslie's, Inc." on two identical rows)."""
    import re as _re
    seen, out = set(), []
    for r in rows:
        name = _re.sub(r"[^a-z0-9]+", " ", str(r.get("name") or "").lower()).strip()
        key = (name, r.get("revenue"))          # the same filed revenue under the same name: one company (its market values may differ)
        if name and r.get("revenue") is not None and key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def consolidated_in(r: dict, rows: list[dict]) -> bool:
    """gl50: whether a company is a listed subsidiary (parents_of) whose parent is among `rows`."""
    p = r.get("parent") if isinstance(r.get("parent"), dict) else None
    return bool(p) and any(x.get("symbol") == p.get("parent") for x in rows)


def layer_block(name: str, rows: list[dict], wide: set[str]) -> dict:
    """A layer's table and its median and range for each figure. A company-wide figure (a group that runs other businesses too) is
    marked and left out of the median when the layer has any company that is its own; the layer says how many were left out. A company
    whose membership isn't confirmed (status "unverified") is listed but left out of the medians and the revenue total; a net margin with a
    one-off gain in it is left out of the net margin's median (`net_all` keeps the median with it). R27: a company whose revenue model is
    unknown or of low confidence in a layer that has models (`model_out`, theme_base.by_model) is listed but left out of the layer's figures
    the same way (`model_out`: their symbols). Lane m1: each row carries "calc" (calc_record), and "n" is the rows in the calculations: a
    company with no figure at all is listed, never counted in "n" (live: 15 in a table, 14 of 17 on the layer's page)."""
    rows = one_row_each(rows)
    for r in rows:              # the one record of who is in the layer's calculations, and why each other is not (calc_record)
        r["calc"] = calc_record(r)
    sure = [r for r in rows if r["calc"]["in"]]
    own = [r for r in sure if r["symbol"] not in wide]
    pool = own or sure
    mark_bases(pool)
    stats = {k: stat(in_median(r, k) for r in pool if not (k == "pb" and (r.get(k) or 0) <= 0)
                     and not (k in BANK_ONLY and r.get("profile") == "insurer")) for k in STAT_KEYS}
    stats.update({k: stat(r.get(k) for r in pool) for k in sector_metrics.KEYS if any(r.get(k) is not None for r in pool)})    # R23: filed sector figures
    return {"layer": name, "companies": rows, "stats": stats, "n": len(sure), "listed": len(rows),
            "net_all": stat(r.get("net") for r in pool), "one_off": sorted(r["symbol"] for r in pool if r.get("one_off")),
            # gl50: a listed subsidiary whose parent is in the layer's calculations too is left out of its revenue total (the parent's
            # figures consolidate it), and named ("double")
            "revenue": sum(r["revenue"] for r in sure if r.get("revenue") and not consolidated_in(r, sure)) or None,
            "double": [{"symbol": r["symbol"], "name": r["name"], "parent": r["parent"]["parent_name"], "pct": r["parent"]["pct"], "revenue": r["revenue"]}
                       for r in sure if r.get("revenue") and consolidated_in(r, sure)],
            "company_wide": sorted(r["symbol"] for r in sure if r["symbol"] in wide),
            "unverified": sorted(r["symbol"] for r in rows if r.get("status") == "unverified"),
            "model_out": sorted(r["symbol"] for r in rows if r.get("model_out") and r.get("status") != "unverified"),
            "stats_over": "all" if not own and sure else "own", "left_out": len(sure) - len(pool),
            # R30: the median company's capital for each unit of revenue (capital_per_revenue), for headline comparability
            "intensity": (stat(r.get("capital_rev") for r in pool) or {}).get("median"),
            # R48: how many companies that median is of, and who is in each median a comparison reads, by name (comparison_basis)
            "intensity_n": sum(1 for r in pool if r.get("capital_rev") is not None),
            # ex49: each company of that pool without the figure, and which input it lacks (capital_inputs)
            "intensity_missing": [[r["name"], list(r.get("capital_missing") or [])] for r in pool
                                  if r.get("capital_rev") is None and r.get("capital_missing")],
            "in_stats": {k: [r["name"] for r in pool if in_median(r, k) is not None] for k in ("ebitda", "net", "roce", "roe")}}


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
    """The whole chain in one table (_chain_table), with (R48) the basis of the comparison its line makes or declines to make
    (comparison_basis): the metric, each compared layer's companies by name and the eligibility rules with their figures."""
    out = _chain_table(blocks)
    names = out.get("compared") or out.get("not_ranked") or []
    if len(names) >= 2:
        key = out.get("measure") or "ebitda"
        by = {b["layer"]: b for b in blocks}
        groups = [{"layer": r["layer"], "value": r.get(key), "n": r.get(f"{key}_n") or 0, "of": r.get("n"), "model": r.get("model"),
                   "basis": r.get("basis"), "intensity": r.get("intensity"), "intensity_n": (by.get(r["layer"]) or {}).get("intensity_n"),
                   "intensity_missing": (by.get(r["layer"]) or {}).get("intensity_missing") or [],
                   "names": list(((by.get(r["layer"]) or {}).get("in_stats") or {}).get(key) or []),
                   "listed": listed_names(by.get(r["layer"]))}
                  for r in out["rows"] if r["layer"] in names]
        line = str(out.get("line") or "")
        why = ("" if out.get("highest") else UNREAD_WHY if out.get("unread") else "their commodities differ" if "commodities differ" in line else
               "their business models differ by the map's own words" if "business models differ" in line else
               f"capital for each unit of revenue differs more than {INTENSITY_WORD}" if INTENSITY_WORD in line else
               "their medians are within a point of each other" if "no layer stands apart" in line or "is the same" in line else "")
        out["basis"] = comparison_basis("chain", "return on equity" if key == "roe" else "EBITDA margin", groups, made=bool(out.get("highest")),
                                        why=why, left=out.get("unranked") or [], high=out.get("highest"), low=out.get("lowest"))
    return out


_HALF_NAME = re.compile(r" \((?:larger|smaller)\)$")


def _chain_table(blocks: list[dict]) -> dict:
    """The whole chain in one table: a row per layer, with the layer that has the highest median EBITDA margin and the one with the
    lowest named. The table's order is the chain's."""
    rows = []

    def row_of(b):
        e, n, c = (b["stats"].get(k) for k in ("ebitda", "net", "roce"))
        return {"layer": b["layer"], "n": b["n"], "listed": b.get("listed") or len(b.get("companies") or []), "revenue": b["revenue"], "ebitda": e["median"] if e else None, "net": n["median"] if n else None,
                     "roce": c["median"] if c else None, "ebitda_n": e["n"] if e else 0, "official": bool(b.get("official")), "rest": b.get("basis") == "rest",
                     **{k: (b["stats"].get(k) or {}).get("median") for k in LENDER_KEYS}, "roe_n": (b["stats"].get("roe") or {}).get("n", 0),
                     **{f"{k}_n": (b["stats"].get(k) or {}).get("n", 0) for k in STAT_KEYS if k not in ("ebitda", "roe")},
                     **{k: (b["stats"].get(k) or {}).get("median") for k in FAMILY_CHAIN}, **{f"{k}_n": (b["stats"].get(k) or {}).get("n", 0) for k in FAMILY_CHAIN},
                "model": b.get("model"), "intensity": b.get("intensity"), "basis": period_basis([c for c in b.get("companies") or [] if c.get("status") != "unverified"]),
                **({"scale": b["scale"]} if b.get("scale") else {})}
    rows = [row_of(b) for b in blocks]
    # gl52 (R52, the rotating review of Release 51: Cement's "Regional cement makers" and Airlines' "Hotels and resorts", each split into
    # halves by market value, left those themes with no ranking at all): the two halves of a layer split by market value are one layer, ranked
    # as one against the others (its companies together); the halves stay in the table as detail, never ranked on their own
    wholes = []
    for b in blocks:
        sib = next((x for x in blocks if b.get("scale") == "larger" and x.get("scale") == "smaller" and x["layer"] == b.get("sibling")), None)
        if sib is not None and model_family_of(b.get("model")) == model_family_of(sib.get("model")):
            both = layer_block(_HALF_NAME.sub("", b["layer"]), [{k: x for k, x in r.items() if k != "calc"} for r in b["companies"] + sib["companies"]],
                               set(b.get("company_wide") or []) | set(sib.get("company_wide") or []))
            wholes.append(row_of({**both, "model": b.get("model"), "official": b.get("official"), "basis": b.get("basis")}))
    # only the map's own layers (an official industry's leftover companies overlap them: "Vehicle assembly" and "Commercial Vehicles"), each
    # with MIN_BASE companies in its median, and only a gap wider than the rounding of whole-point margins, name a highest and a lowest
    # the "Other ..." group (companies that fit none of the map's layers) is never compared (R22)
    # R27: and each a headline figure (headline_ok: the sample, a figure for at least half the layer's companies, one business model), all on one
    # period basis; a layer that fails is shown in the table, never named
    # d1 (the outside review of the live Release 41 Banks deck: "13.5% vs 13.3%" between "(larger)", one half of a layer split by market
    # value, and another layer): a half of a layer split by market value is never ranked on its own, so no headline rests on the split
    ok = lambda r, k: r[k] is not None and headline_ok(r[f"{k}_n"], r["n"], r["model"]) and not r.get("scale")      # noqa: E731
    have = [r for r in rows + wholes if ok(r, "ebitda") and not r["official"]]
    if len(have) < 2:          # a map whose layers are the official industries themselves: they are its layers (R17-011)
        have = [r for r in rows + wholes if ok(r, "ebitda") and not r["rest"]]
    if not same_basis([r["basis"] for r in have]):
        have = []
    if len(have) >= 2 and not any(model_family_of(r["model"]) for r in have):
        # gl50 (R50, the rotating review of six unseen themes: the Biotech and Capital goods decks ranked their layers, "highest in
        # Clinical-stage platform developers (35.0%)", with no company's way of earning read): layers whose companies' ways of earning
        # were never read are described, each with its own figure, never ranked
        whole = whole_points([c for b in blocks for c in b["companies"]])
        each = [f"{r['layer']} {pts(r['ebitda'], whole)}" + (f" ({w[2:]})" if (w := few(r["ebitda_n"], r["n"])) else "") for r in have]
        line = "Median EBITDA margin by layer: " + "; ".join(each) + f". {UNREAD_SAID}"
        return {"rows": rows, "line": line, "highest": None, "lowest": None, "measure": "ebitda", "compared": [], "gap": None,
                "not_ranked": [r["layer"] for r in have], "unread": True}
    have = one_family(have, lambda r: model_family_of(r["model"]))          # R29: layers of one business-model family only
    line, hi, lo, out, beyond = None, None, None, [], ""
    if len(have) >= 2 and len(one_sub(have, lambda r: r["model"])) < 2:
        # R31: layers of one family that sell different commodities (its sub-basis) are described, each with its own figure, never ranked
        whole = whole_points([c for b in blocks for c in b["companies"]])
        each = [f"{r['layer']} {pts(r['ebitda'], whole)}" + (f" ({w[2:]})" if (w := few(r["ebitda_n"], r["n"])) else "") for r in have]
        line = "Median EBITDA margin by layer: " + "; ".join(each) + ". Their commodities differ, so these layers are not ranked."
        return {"rows": rows, "line": line, "highest": None, "lowest": None, "measure": "ebitda", "compared": [], "gap": None,
                "not_ranked": [r["layer"] for r in have]}
    have = one_sub(have, lambda r: r["model"])
    if len(have) >= 2 and len(one_business(have, lambda r: r["model"])) < 2:
        # ex49 (R48, the outside review of the live R48 Chemicals deck: custom synthesis ranked against commodity intermediates): layers whose
        # business models differ by the map's own words, none of them most, are described, each with its own figure, never ranked
        whole = whole_points([c for b in blocks for c in b["companies"]])
        each = [f"{r['layer']} {pts(r['ebitda'], whole)}" + (f" ({w[2:]})" if (w := few(r["ebitda_n"], r["n"])) else "") for r in have]
        line = ("Median EBITDA margin by layer: " + "; ".join(each) + ". Their business models differ ("
                + "; ".join(f"{r['layer']}: {business_words(r['model'])}" for r in have) + "), so these layers are not ranked.")
        return {"rows": rows, "line": line, "highest": None, "lowest": None, "measure": "ebitda", "compared": [], "gap": None,
                "not_ranked": [r["layer"] for r in have]}
    have = one_business(have, lambda r: r["model"])
    apart = have if len(have) >= 2 and not comparable_intensity(have, lambda r: r["intensity"]) else []
    if apart:
        # R30 (the owner's review of the live R28 Utilities deck: "renewable producers 83% vs cables 10%"): layers that need very different
        # capital for each unit of revenue are described, each with its own figure, never ranked
        whole = whole_points([c for b in blocks for c in b["companies"]])
        each = [f"{r['layer']} {pts(r['ebitda'], whole)}" + (f" ({w[2:]})" if (w := few(r["ebitda_n"], r["n"])) else "") for r in apart]
        line = ("Median EBITDA margin by layer: " + "; ".join(each)
                + f". Capital for each unit of revenue ({CAPITAL_PROXY}) differs more than {INTENSITY_WORD} between these layers, so they are not ranked.")
        return {"rows": rows, "line": line, "highest": None, "lowest": None, "measure": "ebitda", "compared": [], "gap": None,
                "not_ranked": [r["layer"] for r in apart]}
    pay = sbc_apart(have)
    if pay:
        # gl52 (R52, the rotating review of Release 51: the Software deck ranked "Data and developer infrastructure software" against "Design
        # and engineering software licences" on EBITDA margin, "a gap of 30.4 points", with stock-based pay 21.9% of revenue against 8.6%): an
        # EBITDA margin leaves stock pay in, so layers whose stock pay differs more than SBC_FACTOR times are described, never ranked on it
        whole = whole_points([c for b in blocks for c in b["companies"]])
        each = [f"{r['layer']} {pts(r['ebitda'], whole)}" + (f" ({w[2:]})" if (w := few(r["ebitda_n"], r["n"])) else "") for r in have]
        lo_, hi_ = pay
        line = ("Median EBITDA margin by layer: " + "; ".join(each) + f". Stock-based pay differs {hi_['sbc_share'] / lo_['sbc_share']:.1f} times between these "
                f"layers ({lo_['layer']} {lo_['sbc_share']:.1f}% of revenue, {hi_['layer']} {hi_['sbc_share']:.1f}%), and an EBITDA margin counts it as a "
                "cost, so they are not ranked on it.")
        return {"rows": rows, "line": line, "highest": None, "lowest": None, "measure": "ebitda", "compared": [], "gap": None,
                "not_ranked": [r["layer"] for r in have], "stock_pay": True}
    if len(have) >= 2:
        hi, lo = max(have, key=lambda r: r["ebitda"]), min(have, key=lambda r: r["ebitda"])
        if hi["layer"] == lo["layer"] or hi["ebitda"] - lo["ebitda"] <= ROUNDING:
            gap = gap_of(max(r["ebitda"] for r in have), min(r["ebitda"] for r in have), whole_points([c for b in blocks for c in b["companies"]]))  # as printed (R25)
            hi = lo = None
            # R27: a tie (no gap as printed) is no comparison: no sentence, never "within 0.0 points"
            line = (f"The median EBITDA margins of the {len(have)} layers with at least {HEADLINE_MIN} companies are within {gap} "
                    f"{'point' if float(gap) == 1 else 'points'} of each other: no layer stands apart.") if float(gap) > 0 else None      # d1: "1 point"
        else:
            whole = whole_points([c for b in blocks for c in b["companies"]])
            # m2 (outside review of the live R32 decks): every highest/lowest headline says, in its own sentence, which layers it ranks
            # (rank_scope: at least HEADLINE_MIN companies with the figure), and names each shown layer whose median is above the highest
            # or below the lowest with why it is not ranked (unranked_rows), so the headline and the table or chart beside it agree
            out = unranked_rows(rows, have, "ebitda")
            whole = one_precision(whole, hi["ebitda"], lo["ebitda"])          # gl52: both figures and the gap at one precision
            line = (f"{rank_scope(len(have), out)}, median EBITDA margin is highest in {hi['layer']} ({pts(hi['ebitda'], whole)}{few(hi['ebitda_n'], hi['n'])}) "
                    f"and lowest in {lo['layer']} ({pts(lo['ebitda'], whole)}{few(lo['ebitda_n'], lo['n'])}), "
                    f"a gap of {gap_of(hi['ebitda'], lo['ebitda'], whole)} points.")
            beyond = beyond_words(out, "ebitda", hi["ebitda"], lo["ebitda"], lambda x: pts(x, whole))
    measure = "ebitda"
    if len(have) < 2:
        # lenders have no EBITDA margin: their layers are set side by side on return on equity (R18)
        lend = [r for r in rows if ok(r, "roe") and not r["official"]]
        if len(lend) < 2:
            lend = [r for r in rows if ok(r, "roe") and not r["rest"]]
        if not same_basis([r["basis"] for r in lend]):
            lend = []
        if len(lend) >= 2 and not any(model_family_of(r["model"]) for r in lend):
            # gl50 (R50): lenders' layers with no way of earning read are described, never ranked, as the margin's (UNREAD_SAID)
            each = [f"{r['layer']} {pts(r['roe'], True)}" + (f" ({w[2:]})" if (w := few(r["roe_n"], r["n"])) else "") for r in lend]
            return {"rows": rows, "line": "Median return on equity by layer: " + "; ".join(each) + f". {UNREAD_SAID}", "highest": None,
                    "lowest": None, "measure": "roe", "compared": [], "gap": None, "not_ranked": [r["layer"] for r in lend], "unread": True}
        lend = one_basis(lend, lambda r: r["model"])
        if not comparable_intensity(lend, lambda r: r["intensity"]):
            lend = []
        if len(lend) >= 2:
            measure, have = "roe", lend
            hi, lo = max(lend, key=lambda r: r["roe"]), min(lend, key=lambda r: r["roe"])
            if hi["layer"] == lo["layer"] or hi["roe"] - lo["roe"] < ROUNDING:
                # d1 (the outside review of the live Release 41 Banks deck: "a gap of 0.2 points" as its headline): a gap under a point is
                # no comparison
                gap = gap_of(hi["roe"], lo["roe"])
                hi = lo = None
                line = (f"The median return on equity of the {len(lend)} layers with at least {HEADLINE_MIN} companies is within {gap} points: "
                        "no layer stands apart.") if float(gap) > 0 else f"The median return on equity of the {len(lend)} layers with at least {HEADLINE_MIN} companies is the same."
            else:
                out = unranked_rows(rows, lend, "roe")
                w_ = one_precision(True, hi["roe"], lo["roe"])          # gl52: one precision for both figures
                line = (f"{rank_scope(len(lend), out)}, median return on equity is highest in {hi['layer']} ({pts(hi['roe'], w_)}{few(hi['roe_n'], hi['n'])}) "
                        f"and lowest in {lo['layer']} ({pts(lo['roe'], w_)}{few(lo['roe_n'], lo['n'])}), "
                        f"a gap of {gap_of(hi['roe'], lo['roe'])} points.").replace(".0 points", " points")
                beyond = beyond_words(out, "roe", hi["roe"], lo["roe"], lambda x: pts(x, True))
        else:
            line = None             # nothing to set side by side: no line at all (R18: the deck said it couldn't be done)
    if line and hi and any(r["rest"] for r in rows):
        line = line.rstrip(".") + "; among the map's layers, the \"Other\" group left out."
    if line and hi and beyond:
        line += " " + beyond
    return {"rows": rows, "line": line, "highest": hi["layer"] if hi else None, "lowest": lo["layer"] if lo else None, "measure": measure,
            "compared": [r["layer"] for r in have], "gap": round(hi[measure] - lo[measure], 1) if hi else None,
            "unranked": [{"layer": r["layer"], "why": r["why"]} for r in out] if hi else []}


# why a layer a table shows is not ranked, in one short clause (m2); "few" is said with the floor itself (unranked_rows)
RANK_WHY = {"cover": "the figure for under half its companies",
            "sparse": "how most of its companies earn is not shown", "family": "a different kind of business", "sub": "a different commodity",
            "official": "an exchange industry, not one of the map's layers", "rest": "companies outside the map's layers",
            "how": "a group by how they earn, of different businesses", "other": "not comparable with the ranked layers",
            "half": "one half of a layer split by market value", "unread": "how its companies earn is not read"}
# gl50 (R50): what a chain of layers whose companies' ways of earning were never read says in place of a ranking
UNREAD_SAID = "How these layers' companies earn is not read, so they are shown, not ranked."
UNREAD_WHY = "how their companies earn is not read"


def rank_scope(n: int, out: list | None = None) -> str:
    """How a ranking headline opens (m2): "Among the 4 layers with at least 5 companies with the figure", and " and one kind of business"
    when a layer shown beside them is left out for how it earns. Said in the headline's own sentence, wherever the headline is shown."""
    kind = any(r.get("why") in (RANK_WHY["family"], RANK_WHY["sub"], RANK_WHY["sparse"], RANK_WHY["how"], RANK_WHY["unread"])
               or str(r.get("why") or "").startswith("a different business model") for r in out or [])
    return f"Among the {n} layers with at least {HEADLINE_MIN} companies with the figure" + (" and one kind of business" if kind else "")


def unranked_rows(rows: list, have: list, key: str) -> list[dict]:
    """The layers a table or chart shows a median of (COMPARE_MIN companies or more) that the headline beside it does not rank, each with
    why in one short clause (`why`, RANK_WHY), in the table's order (m2: Pharma's 26% layer beside a headline that called 21% the highest)."""
    names = {r["layer"] for r in have}
    fam = Counter(f for f in (model_family_of(r["model"]) for r in have) if f).most_common(1)
    sub = Counter(x for x in (sub_of(r["model"]) for r in have) if x).most_common(1)
    biz = Counter(x for x in (business_of(r["model"]) for r in have) if x).most_common(1)
    own = any(not r["official"] for r in have)
    out = []
    for r in rows:
        n = r.get(f"{key}_n") or 0
        if r["layer"] in names or r.get(key) is None or n < COMPARE_MIN or (r.get("scale") and _HALF_NAME.sub("", r["layer"]) in names):
            continue
        m = r.get("model")
        if r.get("rest"):
            why = "rest"
        elif r.get("scale"):
            why = "half"
        elif r.get("official") and own:
            why = "official"
        elif n < HEADLINE_MIN:
            why = "few"
        elif r.get("n") and n < r["n"] * COVERAGE_MIN:
            why = "cover"
        elif not model_family_of(m) and not (isinstance(m, dict) and m.get("sparse")):
            why = "unread"
        elif isinstance(m, dict) and m.get("sparse"):
            why = "sparse"
        elif isinstance(m, dict) and m.get("by_how"):
            why = "how"
        elif fam and model_family_of(m) != fam[0][0]:
            why = "family"
        elif sub and sub_of(m) != sub[0][0]:
            why = "sub"
        elif biz and business_of(m) != biz[0][0] and (named_model(m) or any(named_model(x["model"]) for x in have)):
            why = f"a different business model: {business_words(m)}"          # ex49: said with where it is read
        else:
            why = "other"
        out.append({**r, "why": RANK_WHY.get(why) or (why if why.startswith("a different business model") else
                                                      f"fewer than {HEADLINE_MIN} companies with the figure")})
    return out


def beyond_words(out: list, key: str, hi: float, lo: float, fmt) -> str:
    """"Shown, not ranked: A (26%), a different kind of business; B (4.9%) and C (3%), fewer than 5 companies with the figure." for the
    unranked layers (unranked_rows) whose median is above the headline's highest or below its lowest; "" when none is. The "Other" group
    has its own clause in the headline."""
    by: dict = {}
    for r in out:
        v = r.get(key)
        if v is None or lo <= v <= hi or r["why"] == RANK_WHY["rest"]:
            continue
        by.setdefault(r["why"], []).append(f"{r['layer']} ({fmt(v)})")
    if not by:
        return ""
    join = lambda xs: xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]      # noqa: E731
    return "Shown, not ranked: " + "; ".join(f"{join(xs)}, {why}" for why, xs in by.items()) + "."


def one_precision(whole: bool, *values) -> bool:
    """gl52 (R52, the rotating review of Release 51: "25.8% ... 20% ..., a gap of 5.8 points"): whole points only when every figure said
    together prints whole; else every one of them, and their gap, to one decimal."""
    return bool(whole) and all(v is not None and float(f1(v)).is_integer() for v in values)


def gap_of(a: float, b: float, whole: bool = False) -> str:
    """The gap between two figures as they are printed, to one decimal (R25: a gap said beside its two figures is their difference); between
    two figures printed whole (`whole`, margins filed in whole points), a whole number (LIVE7A-009: "a gap of 3.0 points")."""
    text = f1(float(f1(a)) - float(f1(b)))
    return text[:-2] if whole and text.endswith(".0") else text


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
    """Whether one group's figure may be ranked in a headline (R27): its sample is at least `floor` companies (HEADLINE_MIN, R31), it covers at least
    COVERAGE_MIN of the group's `of` companies, and the group is of one business model (theme_base.by_model's `model`: a layer whose companies'
    models are mostly unknown, "sparse", is not; no model read at all says nothing either way). A failing group is shown, never ranked.
    R40: nor a layer the split made and named only by how its companies earn ("by_how": "Makers of their own products"), a group of
    different businesses."""
    if (n or 0) < (HEADLINE_MIN if floor is None else floor):
        return False
    if of and n < of * COVERAGE_MIN:
        return False
    return not (isinstance(model, dict) and (model.get("sparse") or model.get("by_how")))


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
    theme_base.by_model's), a row of no family left out; [] when none has a family (gl50: no way of earning read ranks nothing) or the most
    common family is tied."""
    from collections import Counter
    fams = [family(r) or "" for r in rows]
    c = Counter(f for f in fams if f).most_common()
    if not c:
        # gl50 (R50): no row's way of earning read is no basis to rank on: nothing is set side by side (it was every row)
        return []
    if len(c) > 1 and c[0][1] == c[1][1]:
        return []
    return [r for r, f in zip(rows, fams) if f == c[0][0]]


INTENSITY_FACTOR = 3.0        # R30: two layers whose median capital for each unit of revenue differs more than threefold are not ranked
INTENSITY_WORD = "threefold"


SBC_FACTOR = 2.0          # gl52: stock-based pay (share of revenue) between two ranked layers, at most this many times apart


def sbc_apart(rows: list) -> tuple | None:
    """gl52 (R52): (the layer with the lowest stock-based pay over revenue, the one with the highest) when two or more of `rows` carry the figure
    (sbc_share, the layer's median company) and the highest is more than SBC_FACTOR times the lowest; else None."""
    xs = [r for r in rows if isinstance(r, dict) and isinstance(r.get("sbc_share"), (int, float)) and r["sbc_share"] > 0]
    if len(xs) < 2:
        return None
    lo, hi = min(xs, key=lambda r: r["sbc_share"]), max(xs, key=lambda r: r["sbc_share"])
    return (lo, hi) if hi["sbc_share"] > SBC_FACTOR * lo["sbc_share"] else None


def comparable_intensity(rows: list, intensity) -> bool:
    """Whether the rows a headline would rank are alike in asset intensity (R30): the highest median capital for each unit of revenue
    (`intensity(row)`, capital_per_revenue's) at most INTENSITY_FACTOR times the lowest. Rows with no figure say nothing either way; True when
    fewer than two have one."""
    xs = [x for x in (intensity(r) for r in rows) if x is not None and x > 0]
    return len(xs) < 2 or max(xs) <= min(xs) * INTENSITY_FACTOR


def listed_names(block: dict | None) -> list[str]:
    """R48: a layer's confirmed companies with figures by name, as the appendix's "Every company's figures" lists them under the layer."""
    return [r["name"] for r in (block or {}).get("companies") or [] if r.get("status") != "unverified" and has_figures(r)]


def intensity_test(groups: list) -> dict | None:
    """R48: the capital-intensity test of a comparison, reproducible: each group's median company's capital for each unit of revenue (book
    equity plus debt over the latest year's revenue, capital_per_revenue) and how many companies it is of, the highest over the lowest, and
    the threshold (INTENSITY_FACTOR). None when fewer than two groups have the figure (the test then says nothing either way)."""
    xs = [g for g in groups if g.get("intensity") is not None and g["intensity"] > 0]
    if len(xs) < 2:
        return None
    hi, lo = max(xs, key=lambda g: g["intensity"]), min(xs, key=lambda g: g["intensity"])
    ratio = hi["intensity"] / lo["intensity"]
    return {"values": [{"layer": g["layer"], "value": g["intensity"], "n": g.get("intensity_n")} for g in xs], "high": hi["layer"], "low": lo["layer"],
            "ratio": round(ratio, 2), "threshold": INTENSITY_FACTOR, "passed": ratio <= INTENSITY_FACTOR}


def model_words(model) -> str:
    """R48: a group's way of earning as the comparison basis says it: the model's words (theme_check.MODELS) and how many of its companies
    it is shown for; "" when none is read."""
    if not isinstance(model, dict) or not (model.get("id") or model.get("family")):
        return ""
    from .theme_check import MODELS
    what = MODELS[model["id"]][2] if model.get("id") in MODELS else model.get("family") or ""
    shown = f", shown for {model['known']} of {model['of']}" if model.get("known") is not None and model.get("of") and model["known"] < model["of"] else ""
    return what + (f" ({model['sub']})" if model.get("sub") else "") + shown


def comparison_basis(claim: str, metric: str, groups: list, made: bool = True, why: str = "", left: list | None = None,
                     high: str | None = None, low: str | None = None, floor: int | None = None) -> dict:
    """R48 (the outside review of the live R46 decks: "the 22% vs 9.5% EBITDA comparison spans different chemical business models; the
    comparability rationale is thin"): what a highest/lowest claim between groups rests on, so it can be reproduced: the metric, each group
    compared (its figure, how many companies it is of out of how many, those companies by name, its way of earning, its capital figure), the
    eligibility rules with their figures (headline floor and coverage, one way of earning, one period basis, the capital-intensity test with
    its threshold), whether the comparison is made, why not when it isn't, and each shown group left out with why.
    `groups`: [{"layer", "value", "n", "of", "model", "basis", "intensity", "intensity_n", "names"}]."""
    floor = HEADLINE_MIN if floor is None else floor
    fams = sorted({model_family_of(g.get("model")) for g in groups} - {""})
    subs = sorted({sub_of(g.get("model")) for g in groups} - {""})
    ways = sorted({model_words(g.get("model")).split(", shown for")[0] for g in groups} - {""})
    periods = sorted({g.get("basis") or "" for g in groups} - {""})
    it = intensity_test(groups)
    bizs = [business_words(g.get("model")) for g in groups]
    rules = [{"rule": "headline floor", "text": f"each layer with at least {floor} companies with the figure and at least "
                                                f"{COVERAGE_MIN * 100:.0f}% of its companies", "passed": all((g.get("n") or 0) >= floor and (not g.get("of") or g["n"] >= g["of"] * COVERAGE_MIN) for g in groups)},
             {"rule": "like-for-like model", "text": (f"one way of earning: {ways[0]}" if len(ways) == 1 else
                                                      f"ways of earning: {'; '.join(ways)}" if ways else "no way of earning read for these companies")
              + (f" (one kind of business: {fams[0]})" if len(fams) == 1 and len(ways) > 1 else ""),
              # gl50 (R50): no way of earning read fails the rule (it passed: nothing read was taken for one model)
              "passed": bool(fams) and len(fams) <= 1 and len(subs) <= 1},
             {"rule": "period basis", "text": "full years" if periods == ["full"] else ", ".join(periods) or "not stored", "passed": len(periods) <= 1 and "mixed" not in periods},
             # ex49 (R48): the business model apart from the way of earning: the map's own name for a layer may state one (custom synthesis,
             # contract manufacturing) its companies' way of earning doesn't (one_business)
             {"rule": "business model", "text": ("one business model: " + next(iter(set(bizs))) if len(set(bizs) - {""}) == 1 and "" not in bizs else
                                                 "none read apart from how the companies earn" if not any(bizs) else
                                                 "business models: " + "; ".join(f"{g['layer']}, {b or 'not read'}" for g, b in zip(groups, bizs))),
              "passed": len({business_of(g.get("model")) for g in groups} - {""}) <= 1}]
    # ex49 (R48): the capital-intensity check is a proxy for capital needs, its inputs checked (capital_inputs); passing it alone never
    # makes layers comparable: the way of earning and the business model decide that
    gaps = [(g["layer"], nm, miss) for g in groups for nm, miss in g.get("intensity_missing") or []]
    gap_text = ("; inputs missing: " + "; ".join(f"{nm} ({' and '.join(miss)})" for _, nm, miss in gaps[:8])
                + (f" and {len(gaps) - 8} more" if len(gaps) > 8 else "")) if gaps else ""
    if it:
        each = "; ".join(f"{x['layer']} {x['value']:.2f}" + (f" ({x['n']} companies)" if x.get("n") else "") for x in it["values"])
        rules.append({"rule": "capital intensity", "text": f"capital for each unit of revenue ({CAPITAL_PROXY}; the layer's median company, of the companies "
                                                           f"with both parts stored for the year): {each}; the highest is {it['ratio']:.1f} times the lowest, "
                                                           f"ranked only at {INTENSITY_FACTOR:g} times or less; never comparability on its own" + gap_text,
                      "passed": it["passed"], "test": it, "proxy": True, "missing": [[lay, nm, miss] for lay, nm, miss in gaps]})
    else:
        rules.append({"rule": "capital intensity", "text": f"fewer than two layers with a capital figure ({CAPITAL_PROXY}): the test says nothing either way"
                                                           + gap_text, "passed": True, "proxy": True, "missing": [[lay, nm, miss] for lay, nm, miss in gaps]})
    return {"claim": claim, "metric": metric, "made": made, "why": why, "high": high, "low": low,
            "groups": [{k: g.get(k) for k in ("layer", "value", "n", "of", "intensity", "intensity_n")} | {"names": list(g.get("names") or []),
                                                                                                         "business": business_words(g.get("model")),
                                                                                                         "listed": list(g.get("listed") or []),
                                                                                                         "model": model_words(g.get("model"))} for g in groups],
            "rules": rules, "left": [{"layer": x["layer"], "why": x["why"]} for x in left or []]}


def model_family_of(model) -> str:
    return (model or {}).get("family") or "" if isinstance(model, dict) else ""


def sub_of(model) -> str:
    """A layer's sub-basis within its family (R31, theme_check.sub_basis: a metals family's commodity), or ""."""
    return (model.get("sub") or "") if isinstance(model, dict) else ""


def one_sub(rows: list, model) -> list:
    """The rows of one family that may be set side by side in a headline (R31, the owner's review of the live R30 Metals deck: aluminium
    smelters ranked against ferro-alloy makers): where their family declares a sub-basis (`model(row)`'s "sub"), only those of the sub-basis
    most of them share; a "mixed" or "other" one left out; [] on a tie. Every row when none carries one."""
    subs = [sub_of(model(r)) for r in rows]
    if not any(subs):
        return list(rows)
    keep = [(r, x) for r, x in zip(rows, subs) if x and x not in ("mixed", "other")]
    c = Counter(x for _, x in keep).most_common()
    if not c or (len(c) > 1 and c[0][1] == c[1][1]):
        return []
    return [r for r, x in keep if x == c[0][0]]


def one_basis(rows: list, model) -> list:
    """one_family, then one_sub: the rows of one family and, where it declares one, one sub-basis (R29, R31); ex49: then one business model
    (one_business)."""
    return one_business(one_sub(one_family(rows, lambda r: model_family_of(model(r))), model), model)


def named_model(model) -> str:
    """ex49: the business model the map's own name for a layer states, of another family than how its companies earn (theme_base.by_model
    "named"), or ""."""
    return (model.get("named") or "") if isinstance(model, dict) else ""


def named_fit(model, v: dict) -> dict | None:
    """rv51 (R51, the outside review of the live Release 49 Consumer retail deck: two retail layers shown, not ranked, as "platforms and
    marketplaces" and "parts, component and ingredient makers", labels read from the map's earlier names for them): a layer's business model
    apart from how its companies earn ("named", theme_base.by_model) kept only where the layer's own records support it
    (theme_check.layer_business: its own name and description, and how its companies are read to earn), with where it is read ("named_from",
    "named_was"); dropped otherwise, so the layer is compared on how its companies earn. A record kept before this release is read the same
    way. Unchanged when the model names none."""
    if not isinstance(model, dict) or not model.get("named"):
        return model
    from .theme_check import layer_business
    got, where = layer_business(model["named"], v.get("layer") or "", v.get("was") or "", v.get("description") or "", model.get("family") or "")
    base = {k: x for k, x in model.items() if k not in ("named", "named_from", "named_was")}
    if not got:
        return base
    return {**base, "named": got, "named_from": where, **({"named_was": v.get("was")} if where == "map" else {})}


def business_of(model) -> str:
    """ex49 (R48, the outside review of the live R48 Chemicals deck: custom synthesis ranked against commodity intermediates): a layer's
    business model as the map's words and its companies support it: the family of the model its name states (named_model), else the family
    of how its companies earn; "" when neither is read."""
    from .theme_check import model_family
    return model_family(named_model(model)) or model_family_of(model)


def one_business(rows: list, model) -> list:
    """ex49: the rows that may be ranked against each other on their business model (business_of): those of the one most of them have; every
    row when none declares one apart from how it earns; [] on a tie. Separate from the way of earning (one_family) and the capital-intensity
    proxy, which alone never makes layers comparable."""
    if not any(named_model(model(r)) for r in rows):
        return list(rows)
    bs = [business_of(model(r)) for r in rows]
    c = Counter(b for b in bs if b).most_common()
    if not c or (len(c) > 1 and c[0][1] == c[1][1]):
        return []
    return [r for r, b in zip(rows, bs) if b == c[0][0]]


def business_words(model) -> str:
    """ex49: a layer's business model as the comparison basis says it, with where it is read: "contract manufacturing (the map's name for the
    layer)" or "makers of their own products (how its companies earn)"."""
    from .theme_check import FAMILIES, MODELS
    n = named_model(model)
    if n in MODELS:
        # rv51 (R51): where the model is read, from the layer's own records (named_fit): its own name, or the map's earlier name for it that
        # its description also states
        was = model.get("named_was") or ""
        if model.get("named_from") == "map" and was:
            return f"{lower_kept(MODELS[n][1])} (the map's name for the layer, “{was}”, and its description)"
        return f"{lower_kept(MODELS[n][1])} (stated by the layer's own name)"
    if not isinstance(model, dict) or not (model.get("id") or model.get("family")):
        return ""
    mid, f = model.get("id") or "", model.get("family") or ""
    name = MODELS[mid][1] if mid in MODELS else FAMILIES.get(f, (f,))[0]
    return f"{lower_kept(name)} (how its companies earn)"


def rank_pair(rows: list, value, count, floor: int | None = None, of=None, model=None, basis=None, intensity=None):
    """(highest, lowest) of `rows` by `value(row)` among those whose figure is of at least `floor` companies (`count(row)`) (R25: one floor for
    every comparison of layers) and, given `of`, `model` and `basis` (each a function of the row), passes headline_ok and shares one period
    basis (R27), and given `intensity`, are alike in asset intensity (R30); None when fewer than two qualify, or when the highest or the lowest is tied (no layer is named for a tie)."""
    have = comparable_rows(rows, value, count, floor, of, model, basis, intensity)
    if len(have) < 2 or value(have[-1]) == value(have[-2]) or value(have[0]) == value(have[1]):
        return None
    if value(have[-1]) - value(have[0]) < ROUNDING:          # d1: a gap under a point is no comparison
        return None
    return have[-1], have[0]


def comparable_rows(rows: list, value, count, floor: int | None = None, of=None, model=None, basis=None, intensity=None) -> list:
    """The rows a sentence may rank against each other, lowest `value(row)` first: the one rule of "one kind of business" behind every
    ranking (the chain's line, the findings, the questions and, lane m1, the "Layers side by side" headline, which ranked contractors
    against developers and equipment makers against generators on the live R32 Real estate and Utilities decks). Each has the figure for
    at least `floor` companies (HEADLINE_MIN) and COVERAGE_MIN of its own, and is of one business model (headline_ok); all are of one
    business-model family and, where it declares one, one sub-basis (one_basis); on one period basis; alike in asset intensity. [] when the
    period bases or the asset intensities differ."""
    have = sorted((r for r in rows if value(r) is not None and headline_ok(count(r) or 0, of(r) if of else None, model(r) if model else None, floor)),
                  key=value)
    if model:                       # R29: one business-model family only; R31: and one sub-basis (a commodity) where the family has one
        have = one_basis(have, model)
    if basis and not same_basis([basis(r) for r in have]):
        return []
    if intensity and not comparable_intensity(have, intensity):         # R30: alike in asset intensity
        return []
    if sbc_apart(have):                     # gl52: alike in stock-based pay, where the rows carry it
        return []
    return have


def rank_top(rows: list, value, count, floor: int | None = None, of=None, model=None, basis=None, intensity=None):
    """(the row with the highest `value(row)`, the rows it was ranked among) under comparable_rows' rule; None when fewer than two qualify
    or the highest is tied."""
    have = comparable_rows(rows, value, count, floor, of, model, basis, intensity)
    if len(have) < 2 or value(have[-1]) == value(have[-2]):
        return None
    return have[-1], have


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
    # R44: unless the year's stored income outside operations covers the profit above EBITDA, as the company row's check (R46: with the year's
    # other stored lines, bridge)
    clean = [r for r in keep if not any(one_off(year_of(r, lb)["opm"], year_of(r, lb)["profit"] / year_of(r, lb)["sales"] * 100
                                                if year_of(r, lb)["profit"] is not None else None)
                                        and not (bridge(year_of(r, lb)) or {}).get("covered") for lb in span)]
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
def theme_segment(segments, words: set) -> dict | None:
    """gl52: the one reported segment of a company that runs several businesses whose name says what the theme or its layer is about (its
    words, kind_stems), with its share of revenue; None when no one segment does or no shares are stored."""
    from .theme_base import kind_stems
    hits = [x for x in segments or [] if isinstance(x, dict) and x.get("name") and num(x.get("share_pct")) and 0 < num(x.get("share_pct")) <= 100
            and kind_stems(x["name"]) & words]
    return {"name": str(hits[0]["name"]), "pct": round(num(hits[0]["share_pct"]), 1)} if len(hits) == 1 else None


def size_section(rows: list[dict], wide=(), segs=None, words_of=None) -> dict:
    """The theme's size: its companies' market value together and the largest. gl52 (R52, the rotating review of Release 51: Adani
    Enterprises, its whole market value, 35.1% of Airlines and travel; L&T 29.8% of Renewable energy; Grasim 21.9% of Cement): a company that
    runs other businesses too (`wide`) counts the share of its market value of its segment that is the theme's (`segs(symbol)`: its reported
    segments; `words_of(symbol)`: the theme's and its layer's words), by that segment's share of revenue; with no such segment stored, its whole
    market value is counted and its row says so ("whole": True)."""
    caps = []
    for r in rows:
        if not r.get("cap"):
            continue
        c, note = r["cap"], {}
        if r["symbol"] in set(wide or ()):
            seg = theme_segment(segs(r["symbol"]) if segs else None, words_of(r["symbol"]) if words_of else set())
            if seg:
                c, note = r["cap"] * seg["pct"] / 100, {"segment": seg["name"], "segment_pct": seg["pct"], "full_cap": r["cap"]}
            else:
                note = {"whole": True}
        caps.append((c, r, note))
    caps.sort(key=lambda t: -t[0])
    total = sum(c for c, _, _ in caps)
    return {"companies": len(rows), "with_value": len(caps), "total_cap": total or None,
            "biggest": [{"symbol": r["symbol"], "name": r["name"], "cap": c, "share": round(c / total * 100, 1), **note} for c, r, note in caps[:5]] if total else [],
            "top3_share": round(sum(c for c, _, _ in caps[:3]) / total * 100, 1) if total and len(caps) >= 3 else None,
            **({"segment_counted": sum(1 for _, _, n in caps if n.get("segment")), "whole_counted": sum(1 for _, _, n in caps if n.get("whole"))}
               if any(n for _, _, n in caps) else {})}


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
    for s_, x in zip(have, parts):
        a, b = year(s_, y0), year(s_, y1)
        by_layer[x["layer"] or "Other"] = by_layer.get(x["layer"] or "Other", 0.0) + (b["sales"] * b["opm"] / r1 - a["sales"] * a["opm"] / r0)
    change = round(end - start, 1)
    # LIVE7A-014 (the live Automotive deck: layer parts −2.3, +0.5, +0.3, +0.1, +0.1, +0 printed under "the parts add up to the change" of −1.4):
    # each layer's part to one decimal, rounded so the printed parts add up to the printed change
    keys = list(by_layer)
    shown = dict(zip(keys, round_to_sum([by_layer[k] for k in keys], change)))
    return {"from": y0, "to": y1, "start": round(start, 1), "end": round(end, 1), "change": change, "n": len(have),
            "companies": sorted(parts, key=lambda x: -abs(x["part"]))[:6],
            "layers": sorted(({"layer": k, "part": shown[k]} for k in keys), key=lambda x: -abs(x["part"]))}


def round_to_sum(values: list[float], total: float, dp: int = 1) -> list[float]:
    """Each value to `dp` decimals, the ones nearest a rounding boundary moved so the rounded values add up to `total` (itself to `dp`
    decimals): the largest remainder rule."""
    import math
    k = 10 ** dp
    target = round(total * k)
    scaled = [v * k for v in values]
    base = [math.floor(x) for x in scaled]
    left = target - sum(base)
    order = sorted(range(len(values)), key=lambda i: -(scaled[i] - base[i]))
    if left >= 0:
        for i in order[:left] if left <= len(order) else order:
            base[i] += 1
    else:
        for i in list(reversed(order))[:-left]:
            base[i] -= 1
    return [round(b / k, dp) for b in base]


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


def _peer_values(r: dict, market: list[dict], key: str, ok, theme: set) -> tuple[list[dict], str]:
    """(a company's comparable peers that have `key`, the set's name); ([], "none") with fewer than PEER_MIN."""
    peers, basis = comparable_peers(r, market, theme)
    got = [m for m in peers if num(m.get(key)) is not None and ok(num(m.get(key)))]
    return (got, basis) if basis != "none" and len(got) >= PEER_MIN else ([], "none")


PEER_NAMES = 3                # peers named beside a peer median (d1), the most used first
PEER_KEEP = 120               # peer symbols kept behind a peer median, those the most companies are compared with first; "symbols_n" counts all
PEER_MOVE = 5.0               # a peer median this many % away from the stored run before it is said with both (peer_moved)
PEER_RUNS = 8                 # a theme's kept peer medians, one for each run that differs from the one before (theme_routes.sources)


def peers_section(rows: list[dict], market: list[dict], as_of: str | None = None) -> dict:
    """Each company against its comparable peers (comparable_peers: its own sector first, then similar market value, the same market and
    accounts): its P/E, its revenue growth over three years and its ROCE beside their medians, and the theme's median company of each (the
    owner, 7 Nov: "valuation premium vs same-size peers beside growth and ROCE"). `sets` counts the companies compared with each set, and
    "none" those with the figure but no comparable peer set (R27: left out, never set against the whole market). Facts: a comparison, never
    a view of what is cheap. R35 (GPT reviews of R31.5-R31.9: a peer median moved between two runs with nothing to trace it by): each
    median keeps the peers behind it ("symbols", the most used first, at most PEER_KEEP; "symbols_n" all of them) and the latest close its
    prices are of ("as_of": the peers' and the companies' own, `as_of` when the rows carry no day)."""
    theme = {r["symbol"] for r in rows}
    names = {m["symbol"]: m.get("name") or m["symbol"] for m in market if m.get("symbol")}
    ind_key = lambda x: re.sub(r"[^a-z0-9]+", " ", str(x or "").lower()).strip()      # noqa: E731
    out = {}
    for key, mkey, ok in (("pe", "pe", lambda x: 0 < x <= stock_pages.PE_MAX), ("sales_3y", "sales_cagr_3y", lambda x: True), ("roce", "roce", lambda x: True)):
        own, peer, prem, sets, used, days = [], [], [], {}, {}, []
        alike, uses = 0, 0
        for r in rows:
            v = num(r.get(key))
            if v is None or not ok(v):
                continue
            got, basis = _peer_values(r, market, mkey, ok, theme)
            sets[basis] = sets.get(basis, 0) + 1
            if not got:
                continue
            pm = median(num(m.get(mkey)) for m in got)
            mine = ind_key(r.get("map_industry") or r.get("industry"))
            for m in got:
                if m.get("symbol"):
                    used[m["symbol"]] = used.get(m["symbol"], 0) + 1
                if mine and m.get("industry"):          # judged only where both industries are known
                    uses += 1
                    alike += 1 if ind_key(m.get("industry")) == mine else 0
            days += [str(d)[:10] for d in [r.get("price_at")] + [m.get("price_at") for m in got] if d]
            own.append(v)
            peer.append(pm)
            if key == "pe" and pm > 0:
                prem.append((v / pm - 1) * 100)
        if own:
            # the P/E gap is the ratio of the two medians over the same companies, the two numbers a table shows (R17-010: the median of each
            # company's own gap, 8.2%, sat beside medians 3.4% apart)
            mo, mp = median(own), median(peer)
            out[key] = {"n": len(own), "theme": round(mo, 1), "peers": round(mp, 1), "sets": sets, "none": sets.get("none", 0),
                        "premium": round((round(mo, 1) / round(mp, 1) - 1) * 100, 1) if prem and round(mp, 1) > 0 else None,
                        "symbols": sorted(used, key=lambda s_: (-used[s_], s_))[:PEER_KEEP], "symbols_n": len(used),
                        "as_of": max(days, default=None) or as_of,
                        # d1 (the outside review of the live Release 41 Banks, Insurance and Cybersecurity decks: "50.4% below peers' 22.6x"
                        # with no peer named, the peers of the broad sector, not of the business): the peers most used, by name, and whether
                        # most of the peers are of the company's own official industry (like for like); a gap is said only then
                        "names": [names.get(s_, s_) for s_ in sorted(used, key=lambda s_: (-used[s_], s_))[:PEER_NAMES]],
                        "like": (alike * 2 >= uses) if uses else None}
        elif sets.get("none"):
            out[key] = {"n": 0, "theme": None, "peers": None, "sets": sets, "none": sets["none"], "premium": None}
    return out


def peer_moved(points: list[dict]) -> dict | None:
    """What a theme's peer median P/E was at the stored run before this one, when the two are more than PEER_MOVE % apart (R35: 19.2x one day
    and 18.4x the next, with nothing said): {"from", "on", "to", "at", "pct", "peers_from", "peers_to", "n_from", "n_to"}; None otherwise.
    `points`: the kept runs, oldest first, this run last ({"d": the close, "peers": the median, "k": how many peers, "n": how many of the
    theme's companies were compared})."""
    pts = [p for p in points or [] if isinstance(p, dict) and num(p.get("peers"))]
    if len(pts) < 2 or pts[-2]["peers"] <= 0:
        return None
    was, now = pts[-2], pts[-1]
    pct = round((now["peers"] / was["peers"] - 1) * 100, 1)
    if abs(pct) <= PEER_MOVE:
        return None
    return {"from": was["peers"], "on": was.get("d"), "to": now["peers"], "at": now.get("d"), "pct": pct, "peers_from": was.get("k"), "peers_to": now.get("k"),
            "n_from": was.get("n"), "n_to": now.get("n")}


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
            "ev_missing": sum(1 for r in rows if r.get("ev_ebitda") is None and not r.get("bank")), "losses": losses,
            "peers": peers_section(rows, market, max((str(r["price_at"])[:10] for r in rows if r.get("price_at")), default=None)),
            "n": len(rows)}                 # the population every count here is of (R22: 11 with a P/E and 6 loss-makers of 15)


def relative_ok(val: dict) -> bool:
    """Whether a theme's valuation may be relative (R29, the owner's review of the live R27 Telecom deck: 24 companies with a P/E, none with a
    comparable peer set): comparable peers cover at least half of the companies with a P/E. Otherwise the valuation is descriptive (the
    theme's own medians and spread, by layer and over time), never set against peers or the whole market."""
    pe_n = (val.get("pe") or {}).get("n") or 0
    pp = (val.get("peers") or {}).get("pe") or {}
    with_peers = pp.get("n") or 0
    # d1: and the peers are like for like (most of them of the companies' own official industries) and named; else no relative figure
    return bool(pe_n) and with_peers * 2 >= pe_n and pp.get("like") is not False


def layer_valuation(blocks: list[dict], counted: set) -> list[dict]:
    """Each layer's own median P/E, P/B and EV/EBITDA with their counts and ranges (R29: the descriptive valuation), over its confirmed
    companies with figures that are in its figures (never one whose model is left out, `model_out`); a layer with none of the three is left out."""
    out = []
    for b in blocks:
        cos = [c for c in b.get("companies") or [] if c.get("symbol") in counted and in_calc(c)]
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


QUARTER_SHARE = 1 / 3        # gl50: the share of the companies with a quarter that the median's quarter end needs


def quarter_section(rows: list[dict], filed: list[dict] | None = None) -> dict:
    """The latest reported quarter of each company against the same quarter a year before (revenue and net profit change), as the company page's
    "Latest YoY" gives it, with how many are up and down. One quarter per median (the owner, 7 Nov: June and September mixed in one median): the
    newest quarter at least a third of them and MIN_LAYER report is the median's (gl50), else the one most report; a company still on an earlier quarter is listed apart, and one whose
    newer results were filed (`filed`: the events' results filed) but aren't in its figures yet is marked with the filing's day. Facts only: it
    compares a company with its own year-ago quarter, not with anyone's estimate."""
    have = [r for r in rows if r.get("quarter") and (r["quarter"]["sales"] is not None or r["quarter"]["profit"] is not None)]
    ends = Counter(quarter_end(r["quarter"]["of"]) for r in have)
    ends.pop(None, None)
    # gl50 (R50, the rotating review: the live Software deck's median was of "Oct 2026", 2 companies whose fiscal quarter ends in October, and
    # 90 on the September quarter were "still on an earlier quarter"; Cybersecurity 6 of 15, Consumer retail 16 of 91): the newest quarter
    # end at least QUARTER_SHARE of the companies with one report, and MIN_LAYER; else the one most of them report
    usual = max((d for d, k in ends.items() if k >= MIN_LAYER and k >= QUARTER_SHARE * len(have)), default=None) or \
        (max(ends, key=lambda d: (ends[d], d)) if ends else None)
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


# ---------- gl50 (R50): a parent and its listed subsidiary in one theme ----------
# The rotating review of the live Cement deck: Grasim (whole company, consolidating UltraTech) and UltraTech, and Ambuja and ACC (consolidated
# with it), each added into revenue totals. The generic signal in stored data: the exchange's shareholding filing names a company's promoter
# holders; one that is another company of the theme holding more than half of it controls it, and so consolidates it.
CONTROL_PCT = 50.0
_ENTITY_END = re.compile(r"\b(?:limited|ltd|inc|incorporated|corp|corporation|co|company|plc|llc|pvt|private|the)\b\.?", re.I)


def entity_key(name) -> str:
    """A company's name for matching a holder to a company: lower case, legal words and punctuation left out ("Grasim Industries Limited" and
    "Grasim Industries Ltd" meet)."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", _ENTITY_END.sub(" ", str(name or "").lower().replace("&", " and "))).split())


def parents_of(symbols: list[str], names: dict, src) -> dict:
    """{subsidiary symbol: {"parent", "parent_name", "pct", "quarter"}} for each of `symbols` whose latest stored shareholding filing names
    another of `symbols` (by name, entity_key) among its promoter holders with more than CONTROL_PCT of its shares. {} where no filing is
    stored (the US: none is read), never a guess from names alone."""
    by_key = {entity_key(names.get(s) or s): s for s in symbols if entity_key(names.get(s) or s)}
    out = {}
    for sym in symbols:
        try:
            co = src.shareholding(sym)
        except Exception as e:
            print("theme data: holdings not read:", sym, type(e).__name__, str(e)[:100])
            co = None
        qs = sorted((co or {}).get("q") or {})
        if not qs:
            continue
        best = None
        for r in (co["q"].get(qs[-1]) or {}).get("rows") or []:
            try:
                name, _, group, _, pct = r[:5]
                pct = float(pct)
            except (TypeError, ValueError):
                continue
            p = by_key.get(entity_key(name))
            if group == "promoter" and p and p != sym and pct > CONTROL_PCT and (best is None or pct > best[1]):
                best = (p, pct)
        if best:
            out[sym] = {"parent": best[0], "parent_name": names.get(best[0]) or best[0], "pct": round(best[1], 1), "quarter": qs[-1]}
    return out


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
                    "severity": i.get("severity"), "subject": i.get("subject") or i.get("title") or "", "url": i.get("url"),
                    "text": str(i.get("text") or "")[:240]})        # m2: the filing's own words, for the context a dated update states
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
            label, text = a.get("label") or "", a.get("text") or ""
            if label and text.lower().startswith(label.lower()):           # LIVE7A-025: "Dividend: Dividend $0.15 a share" said once
                text = text[len(label):].strip(" :–-")
            actions.append({"symbol": a["symbol"], "name": names.get(a["symbol"]) or a["symbol"], "date": a.get("ex_date"), "kind": a.get("kind"),
                            "label": label, "text": text})
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
    # the posts keep the marks' floor (COMPARE_MIN), as blog_research._theme_gap does: R31's headline floor is the decks'
    have = [r for r in chain["rows"] if r["ebitda"] is not None and headline_ok(r["ebitda_n"], r["n"], r.get("model"), floor=COMPARE_MIN)
            and r["layer"] not in apart]
    have = one_family(have, lambda r: model_family_of(r.get("model")))       # gl50: of one kind of business, and never with none read
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


# ---------- q1: who was in each layer's calculations at the runs before (the GPT review of the live R34 Telecom deck: 6 of 9 operators in
# R33, 3 of 8 in R34, with nothing said) ----------
COHORT_RUNS = 6               # a theme's kept layer cohorts, one for each run whose cohorts differ from the one before (theme_routes.sources)
COHORT_SHARE = 1 / 3          # a layer whose count in its calculations falls by more than this share against the run before is said...
COHORT_FALL = 3               # ...or by this many companies or more


def cohort_point(blocks: list[dict], today: date) -> dict:
    """This run's layer cohorts, as kept: {"d": the day, "layers": {layer: [the symbols in its calculations]}, "names": {symbol: name}}."""
    layers, names = {}, {}
    for b in blocks:
        ins = sorted(c["symbol"] for c in b.get("companies") or [] if calc_of(c)["in"])
        layers[b["layer"]] = ins
        names.update({c["symbol"]: c.get("name") or c["symbol"] for c in b.get("companies") or [] if c["symbol"] in ins})
    return {"d": today.isoformat(), "layers": layers, "names": names}


def cohort_drops(points: list[dict], blocks: list[dict]) -> list[dict]:
    """Each layer whose count in its calculations fell by more than COHORT_SHARE, or by COHORT_FALL or more, against the run before (q1):
    {"layer", "from", "to", "on": that run's day, "left": [{"symbol", "name", "why"}]}, each company that left with its reason now (its own
    record's reason when the layer still lists it, the layer it moved to, or no longer in the theme). A layer is the run before's of the same
    name, else the one that held most of its companies then. `points`: the kept runs, oldest first, this run last."""
    pts = [p for p in points or [] if isinstance(p, dict) and isinstance(p.get("layers"), dict)]
    if len(pts) < 2:
        return []
    was, now = pts[-2], pts[-1]
    where = {c["symbol"]: (b["layer"], calc_of(c)) for b in blocks for c in b.get("companies") or []}
    out = []
    for layer, ins in now["layers"].items():
        before = was["layers"].get(layer)
        if before is None:
            listed = {c["symbol"] for b in blocks if b["layer"] == layer for c in b.get("companies") or []}
            best = max(was["layers"].items(), key=lambda kv: len(listed & set(kv[1])), default=(None, []))
            before = best[1] if best[0] is not None and len(listed & set(best[1])) * 2 >= max(1, len(best[1])) else None
        if not before:
            continue
        fell = len(before) - len(ins)
        if fell <= 0 or not (fell > COHORT_SHARE * len(before) or fell >= COHORT_FALL):
            continue
        left = []
        for s_ in sorted(set(before) - set(ins), key=lambda x: (was.get("names") or {}).get(x, x)):
            at = where.get(s_)
            why = ("no longer in the theme" if at is None else at[1]["why"] or "in the calculations" if at[0] == layer
                   else f"moved to {at[0]}" + (f" ({at[1]['why']})" if not at[1]["in"] and at[1]["why"] else ""))
            left.append({"symbol": s_, "name": (was.get("names") or {}).get(s_) or (now.get("names") or {}).get(s_) or s_, "why": why})
        out.append({"layer": layer, "from": len(before), "to": len(ins), "on": was.get("d"), "left": left})
    return out


# ---------- the sources, and the whole dive ----------
class Sources:
    """Where a dive reads its stored figures. Each is a callable, so a test passes its own:
    facts(symbol) -> a company's stored page facts or None; index_rows() -> the screens' index rows (the market, for comparison);
    shareholding(symbol) -> the stored shareholding quarters; insider_buys() -> {symbol: the latest purchase's day};
    results(frm, to, symbols), actions(frm, to, symbols), red_flags(symbols, frm, to) -> stored rows;
    card(symbol, row) -> the management report card checked against the reported years ({met, missed}) or None;
    history(key, point) -> the theme's kept points after adding `point` (a day's median P/E and the like), oldest first;
    peer_history(key, point) -> the theme's kept peer medians after adding this run's `point`, oldest first, this run last (R35, peer_moved);
    cohort_history(key, point) -> the theme's kept layer cohorts after adding this run's `point`, oldest first, this run last (q1, cohort_drops);
    segments(symbol) -> the business segments the company's documents report ([{name, share_pct}]) or None (is_diversified);
    corp_history(symbol) -> the company's stored corporate actions (every kind, each with "kind" and "ex_date"), never read from a source;
    metrics(symbol, family) -> the company's filed sector figures (sector_metrics: a stored piece, read now or queued) or None (R23);
    about(symbol) -> the company's whole stored description or None, never read from a source (R35: sub_members);
    passages(symbols, query) -> the matching passages of the companies' own documents in the filings index (m53: sector_ops), never read
    from a source."""

    def __init__(self, today: date, facts, index_rows=lambda: [], shareholding=lambda s: None, insider_buys=lambda: {},
                 results=lambda a, b, s: [], actions=lambda a, b, s: [], red_flags=lambda s, a, b: [], card=lambda s, r: None,
                 history=lambda k, p: [p], segments=lambda s: None, corp_history=lambda s: [], metrics=lambda s, fam: None, about=lambda s: None,
                 peer_history=lambda k, p: [p], cohort_history=lambda k, p: [p], passages=lambda syms, q: []):
        self.today, self.facts, self.index_rows, self.shareholding, self.insider_buys = today, facts, index_rows, shareholding, insider_buys
        self.results, self.actions, self.red_flags, self.card, self.history, self.segments = results, actions, red_flags, card, history, segments
        self.corp_history, self.metrics, self.about, self.peer_history = corp_history, metrics, about, peer_history
        self.cohort_history, self.passages = cohort_history, passages


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


# rv51 (R51, the outside review of the live Release 49 IT services deck: Black Box Ltd "own words describe other work", screened out on its
# first sentence, "AGC Networks Ltd. (AGC), incorporated in 1986 by Tata Telecom Pvt. Ltd. to manufacture telecommunication equipment", though
# its description goes on to an ICT solutions provider and integrator): another company's name is no word of the company's own work ("Tata
# Telecom Pvt. Ltd.", the parent that incorporated it), and a sentence of its history (incorporated, established ... to manufacture), with no
# verb of what it does now, is not its business
_NAMED_COMPANY = re.compile(r"\b(?:[A-Z][\w&'-]*\.?\s+){1,5}(?:Pvt\.?|Private|Ltd\.?|Limited|Inc\.?|Corp\.?|Corporation|LLC|L\.L\.C\.|plc|PLC)"
                            r"(?:\s+(?:Ltd\.?|Limited))?(?=\W|$)")
_HISTORY = re.compile(r"\b(?:incorporated|established|founded|set up|formed|promoted|originally|formerly|began|started|was born)\b", re.I)
_NOW_VERB = re.compile(r"(?<!\bto )\b(?:is|are|provides|offers|operates|delivers|serves|sells|makes|manufactures|produces|develops|designs|"
                       r"specialises|specializes|focuses|runs|supplies|builds|integrates|implements|caters|engages|works)\b", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(“\"])")


def business_sentence(text: str) -> str:
    """rv51: the first sentence of a company's description that says what it does now: another company's name taken out (_NAMED_COMPANY),
    a sentence that names no work (BUSINESS) or tells only its history (_HISTORY with no verb of what it does now) passed over. ""."""
    t = str(text or "")
    # a name that ends a sentence keeps its full stop ("held by Essar Telecom Ltd. Over the years ..."), else it is one word of the sentence
    t = _NAMED_COMPANY.sub(lambda m_: "another company" + ("." if m_.group(0).endswith(".") and re.match(r"\s+[A-Z]", t[m_.end():]) else ""), t)
    for s_ in _SENTENCE_END.split(t):
        if BUSINESS.search(s_) and not (_HISTORY.search(s_) and not _NOW_VERB.search(s_)):
            return " ".join(s_.split())
    return ""


def principal_business(c: dict, about: str | None = None, segments=None) -> tuple[str, str]:
    """rv51: a company's principal disclosed business, (where, text): its largest reported segment ("segment"), else the first sentence of
    its own description that says what it does now ("description", business_sentence over its whole stored description, else its line),
    else its official industry ("industry"); ("", "") with none."""
    segs = [x for x in segments or [] if isinstance(x, dict) and x.get("name")]
    if segs:
        top = max(segs, key=lambda x: x.get("share_pct") or 0)
        return "segment", str(top["name"])
    said = business_sentence(about or "") or business_sentence(c.get("what") or "")
    if said:
        return "description", said
    ind = str(c.get("industry") or "")
    return ("industry", ind) if ind else ("", "")


PRINCIPAL_WORDS = {"segment": "its largest reported segment", "description": "the first sentence of its description that says what it does now",
                   "industry": "its official industry"}


def principal_fits(c: dict, words: set[str], about: str | None = None, segments=None) -> str:
    """rv51: where a company's principal disclosed business (principal_business) is read when it fits the theme's definition (its words
    show the theme's work and name no other kind of work); "" when it doesn't."""
    where, text = principal_business(c, about, segments)
    return where if text and does_the_work(text, words) and not other_work(text, words) else ""


def membership(c: dict, words: set[str], about: str | None = None, segments=None, principal: bool = True) -> str:
    """How sure the theme is of a company (the owner, 7 Nov: a membership check for official-industry companies too, so an insurance software
    house filed under auto parts isn't in the auto figures): "core", a company of the theme's own industries or list whose own words (or a
    checked quote) show the work; "exposure", a company from another industry whose own words were checked to show the work; "unverified",
    the rest: listed, but left out of every median and total. rv51 (R51): a company of the theme's own industries whose principal disclosed
    business fits the theme (principal_fits: its largest segment, else the first sentence of its description that says what it does now,
    else its official industry; `about` its whole stored description, `segments` its reported segments, a callable or a list) is never
    screened out by its words: they place it in a layer or in "Other", in the theme (`principal` False: the check without it)."""
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
        if principal and principal_fits(c, words, about, segments() if callable(segments) else segments):
            return "core"
        return "unverified"
    return "exposure" if c.get("verified") else "unverified"


def theme_record(c: dict, status: str) -> dict:
    """c1 (R44, the outside review of the live Release 43 decks, ask 3: "keep theme membership separate from comparison eligibility, each with
    its reason"): a company's place in the theme, {"in", "status", "by", "why"}, decided apart from whether its figures are compared
    (calc_record, comparison_said). "in": confirmed in the theme (membership "core" or "exposure"); a company "unverified" is listed, never in
    a figure. "by": what put it in the theme: "industry" (filed under one of the theme's official industries), "list" (the theme's own list),
    "other_industry" (the theme's map named it from another industry) or "map". A company dropped from the theme is named on its coverage
    with its own reason (theme_base.without_off_industry)."""
    from .theme_base import plain_industry
    ind = plain_industry(c.get("industry")) if c.get("industry") else ""
    if c.get("base") is None and c.get("verified") is None:
        by, why = "map", "placed in the theme's map"
    elif c.get("base"):
        if c.get("basis") == "list":
            by, why = "list", "named in the theme's own list"
        else:
            by = "industry"
            why = f"filed under {ind}, an official industry of the theme" if ind else "filed under an official industry of the theme"
            if status == "unverified":
                why += ", but its own words describe other work"
    else:
        by = "other_industry"
        frm = f"from another industry ({ind})" if ind else "from another industry"
        if c.get("verified_by") == "words":
            why = f"the theme's map names it in one of its own layers, {frm}; its own words say what that layer's name says"
        elif status == "exposure":
            why = f"the theme's map names it, {frm}; its own words were checked to show the theme's work"
        else:
            why = f"the theme's map names it, {frm}; its own words are not confirmed to show the theme's work yet"
    return {"in": status != "unverified", "status": status, "by": by, "why": why}


def comparison_said(rec: dict, b: dict) -> str:
    """c1 (R44, ask 3): a company's comparison decision as one sentence, from its kept record (calc_record) and its layer: in its layer's
    figures or not and why, and whether those figures are compared with other layers' (the "Other" group never is, nor a half of a layer by
    market value alone, nor a group made by how its companies earn)."""
    if not rec.get("in"):
        # ex49 (R48): its precise reason, kind first (a different revenue model with both models; insufficient evidence with what is missing)
        if rec.get("kind") == "not confirmed in the theme" or rec.get("why") == "not confirmed":
            return "left out of every figure: not confirmed in the theme"
        kind = rec.get("kind") or WHY_KIND.get(rec.get("why"))
        if kind:
            return f"listed in its layer, left out of its figures: {kind}, {rec.get('detail') or KIND_SAID[kind]}"
        return "left out of its layer's figures"
    m = b.get("model") or {}
    if b.get("basis") == "rest":
        return "in the “Other” group's figures, which are never compared with the layers'"
    if b.get("scale"):
        return "in its layer's figures; the layer is half of a group split by market value, never ranked alone"
    if isinstance(m, dict) and m.get("by_how"):
        return "in its layer's figures; the layer is a group by how its companies earn, of different businesses, shown and never ranked"
    if not model_family_of(m):
        # gl50 (R50, the live Capital goods deck said "how it earns shown and of the layer's kind" of every company beside "no way of earning
        # read for these companies"): with no way of earning read, nothing is said of the layer's kind, and the layer is never ranked
        return "in its layer's figures: confirmed, with a figure; how its layer's companies earn is not read, so the layer is shown, not ranked"
    if rec.get("by_words"):             # ex49 (R48, G3): the map's pick, its own words say the layer's name and no other way of earning
        return ("in its layer's figures: confirmed, with a figure; the map placed it here and its own words say the layer's name and no other "
                "way of earning; only the AI's read gave it another")
    if rec.get("own_goods"):            # ex49 (R48): read as a retailer of them, its own words say it designs the goods it sells
        return ("in its layer's figures: confirmed, with a figure; read as a retailer, its own words say it designs the goods it sells, "
                "so it sells products of its own, as the layer's companies do")
    return "in its layer's figures: confirmed, how it earns shown and of the layer's kind, with a figure"


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


def layer_coverage(checked: dict) -> dict | None:
    """R44 (the outside review's ask 2: classification coverage): of the companies the map places (every company once, in its first layer),
    how many are in an informative layer, one the map names (an AI layer or an exchange industry), against the "Other" group (fit none of
    the map's layers, or not checked yet): {"informative", "placed", "share" (whole per cent), "other", "unread", "other_name"}; None when
    nothing is placed."""
    placed, rest, unread, name = set(), set(), set(), ""
    for v in checked.get("value_chain") or []:
        is_rest = bool(v.get("official")) and v.get("basis") == "rest"
        for c in v.get("companies") or []:
            t = c.get("ticker")
            if not t or t in placed:
                continue
            placed.add(t)
            if is_rest:
                rest.add(t)
                name = name or v.get("layer") or ""
                if c.get("unread"):
                    unread.add(t)
    if not placed:
        return None
    n = len(placed) - len(rest)
    return {"informative": n, "placed": len(placed), "share": int(Decimal(n * 100) / Decimal(len(placed)) + Decimal("0.5")),
            "other": len(rest), "unread": len(unread), "other_name": name}


def build(region: str, theme: str, checked: dict, src: Sources) -> dict:
    """The dive for a checked map (see theme_check.check_placements): the tables by layer, the whole chain in one table, the sub-themes'
    companies, and the sections for the theme as a whole. Every figure is from the stored facts; nothing here calls a source."""
    checked = by_industry(checked)
    from .theme_base import with_sub_only
    checked = with_sub_only(checked, theme)          # d1: a company named in a sub-theme only is in "Other", never in no layer
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

    def seg_list(sym):
        try:
            return src.segments(sym)
        except Exception as e:
            print("theme data: segments not read:", sym, type(e).__name__, str(e)[:100])
            return None
    # rv51 (R51): a company of the theme's industries is screened out by its words only when its principal disclosed business doesn't fit
    # (membership: its whole stored description and its segments read)
    every_status = {s: membership(c, words, src.about(s), lambda s=s: seg_list(s)) for s, c in placed.items()}
    facts = {s: src.facts(s) for s in placed}
    rows = {s: r for s, r in ((s, company_row(region, s, f)) for s, f in facts.items()) if r}
    for s, c in placed.items():
        if s in rows:
            rows[s]["name"] = shown_name(c.get("name"), rows[s]["name"]) or rows[s]["name"]
            rows[s]["status"] = every_status[s]
            rows[s]["theme"] = theme_record(c, rows[s]["status"])     # c1: in the theme, with its reason (apart from any comparison)
            if c.get("base") and rows[s]["status"] == "core" and membership(c, words, principal=False) == "unverified":
                where, said = principal_business(c, src.about(s), seg_list(s))
                rows[s]["theme"]["why"] += (f"; its own words name other work, but its principal business ({PRINCIPAL_WORDS[where]}"
                                            + (f", “{said}”" if where == "segment" else "") + ") fits the theme, so it stays in the theme")
            rows[s]["map_industry"] = c.get("industry") or ""          # the exchange's (or the SEC's) industry the map gives (R27: metric_registry)
            rows[s]["map_what"] = c.get("what") or ""                  # what the map says the company does (an insurer's type: metric_registry)
            if c.get("unread"):        # d1: in "Other" because nothing it says was read yet (theme_base.place_rest), not because it fits no layer
                rows[s]["unread"] = True

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
    # gl50: each listed subsidiary of another company of the theme, from the stored shareholding filings (parents_of)
    parents = parents_of(sorted(s for s, r in rows.items() if r.get("status") != "unverified"), names, src)
    for s, p in parents.items():
        rows[s]["parent"] = p

    blocks, histories = [], {}
    # R32: a split by market value one of whose halves shows no company is undone (theme_base.unsplit_unshown)
    from .theme_base import own_words as _own, unsplit_unshown, whole_words
    own_words = lambda t, n, sym=None: _own(whole_words(t, src.about(sym)) if sym and t else t, n)     # noqa: E731  (LIVE7A-004: no word cut)
    for v in unsplit_unshown(checked.get("value_chain") or [], {s for s, r in rows.items() if r.get("status") != "unverified"}):
        mine = [rows[c["ticker"]] for c in v.get("companies") or [] if c["ticker"] in rows]
        if v.get("sub_only") and not mine:          # d1: the "Other" group made for sub-theme-only companies none of which has figures
            continue
        what = {c["ticker"]: c.get("what") for c in v.get("companies") or []}
        ind = {c["ticker"]: c.get("industry") for c in v.get("companies") or []}          # the exchange's industry, a column of an AI layer (R20)
        from .theme_check import model_family
        for r in mine:                     # R30: an EBITDA margin checked against how the company earns
            validate_model(r, model_family(model_fields(v, r["symbol"]).get("model") or "") or ((v.get("model") or {}).get("family") or ""))
        stage_check(v, mine)               # gl50: a clinical-stage or pre-revenue layer's commercial companies, out of its figures
        b = layer_block(v.get("layer") or "", [{**r, "what": own_words(what.get(r["symbol"]), r.get("name") or "", r["symbol"]) or None, "company_wide": r["symbol"] in wide, "official_industry": ind.get(r["symbol"]) or "",
                                                **model_fields(v, r["symbol"]), **refit_of(v, r["symbol"])} for r in mine], wide)
        b["description"] = v.get("description") or ""
        b["policy"] = v.get("policy")
        b["official"], b["basis"] = bool(v.get("official")), v.get("basis")     # a layer that is one official industry's companies the AI didn't place (theme_base.py)
        b["by_industry"] = bool(v.get("by_industry"))
        if v.get("scale"):          # d1: a half of a layer split by market value (theme_base.by_model step 2), never ranked on its own
            b["scale"], b["sibling"] = v["scale"], v.get("sibling")
        b["model"] = named_fit(v.get("model"), v) or None   # what the layer's companies have in common: how they earn (theme_base.by_model, R25)
        if b["model"]:                                       # R28: counted over the companies the page shows, not every company the map placed
            from .theme_base import shown_model
            b["model"] = shown_model(b["model"], [r for r in b["companies"] if r.get("status") != "unverified"])
        blocks.append(b)
        ins = {r["symbol"] for r in b["companies"] if in_calc(r)}       # the layer's one record of who is in its calculations
        sure = [r for r in mine if r["symbol"] in ins]
        histories[b["layer"]] = layer_history([r for r in sure if r["symbol"] not in wide] or sure)
    for b in blocks:                        # c1: each company's comparison decision, said with its reason beside the in-theme one
        for r in b["companies"]:
            if isinstance(r.get("calc"), dict):
                r["comparison"] = comparison_said({**calc_of(r), **({k: True for k in ("own_goods", "by_words") if r.get(k)})}, b)
    chain = chain_table(blocks)
    counted = [r for b in blocks for r in b["companies"] if r.get("status") != "unverified"]
    pool = [r for r in counted if not r["company_wide"]] or counted
    allm = stat(r["ebitda"] for r in {r["symbol"]: r for r in pool}.values())
    for b in blocks:
        b["line"] = margin_line(b, allm["median"] if allm else None, several=sum(1 for x in blocks if x["stats"].get("ebitda")) > 1, whole=whole_points(pool))
        b["ebitda_whole"] = whole_points([r for r in b["companies"] if in_calc(r)] or b["companies"])        # LIVE7A-009: its median printed whole
        b["history"] = histories.get(b["layer"])
    subs = []
    for s in checked.get("sub_themes") or []:
        cos = []
        for c in sub_members(s, checked.get("value_chain") or [], src.about):
            r = rows.get(c["ticker"])
            if r:
                cos.append({"symbol": r["symbol"], "name": r["name"], "what": own_words(c.get("what"), r["name"] or "", r["symbol"]) or None, "cap": r["cap"], "sales_1y": r["sales_1y"], "ebitda": r["ebitda"], "ebitda_dp": r.get("ebitda_dp"),
                            "company_wide": r["symbol"] in wide, "year": r["year"], "bank": r.get("bank"), "net": r.get("net"), "one_off": r.get("one_off"), "roe": r.get("roe")})
        subs.append({"name": s.get("name") or "", "detail": s.get("detail") or "", "companies": cos})
    for r in rows.values():                 # a merger or demerger broke the company's series: no growth figure for it, none in the growth totals
        r["demerger"] = demerger_on(src, r["symbol"])
        if series_break(r) or r["demerger"]:
            r["series_break"] = True
            for k in ("sales_1y", "sales_3y", "sales_5y", "profit_1y", "profit_3y", "profit_5y"):
                r[k] = None
    listed = one_row_each(sorted(rows.values(), key=lambda r: -(r.get("cap") or 0)))     # R36: one company under two symbols, once
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
    pp = val["peers"].get("pe") or {}
    if pp.get("peers"):           # R35: this run's peer median beside the stored run before it, said when the two are apart (peer_moved)
        try:
            moved = peer_moved(src.peer_history(slug(theme), {"d": pp.get("as_of") or src.today.isoformat(), "peers": pp["peers"],
                                                              "k": pp.get("symbols_n"), "n": pp.get("n")}))
        except Exception as e:
            print("theme data: peer medians not kept:", type(e).__name__, str(e)[:100])
            moved = None
        if moved:
            pp["moved"] = moved
    market_med = {k: stat(m.get(k) for m in market) for k in ("opm", "net_margin", "roce", "sales_cagr_3y")} if market else {}
    as_of, older = price_day(members)
    own_set = {r["symbol"] for r in own}
    from .theme_base import kind_stems as _kind
    layer_name = {c["symbol"]: b["layer"] for b in blocks for c in b["companies"]}
    size_words = lambda s_: _kind(checked.get("sector") or theme) | _kind(layer_name.get(s_) or "")      # noqa: E731  (gl52: the theme's segment)
    out = {
        "region": region, "sector": checked.get("sector") or theme, "as_of": as_of, "as_of_older": older, "ebitda_whole": whole_points(own), "unit": next((r["unit"] for r in members if r.get("unit")), None),
        "basis": basis_text(members, region), "layers": blocks, "chain": chain, "subs": subs, "company_wide": sorted(wide & set(syms)),
        # "with figures" means the key figures exist (revenue or profit), not just a stored page (R20: a bank with dashes in every field
        # counted among "20 of 20 with figures")
        "members": sum(1 for r in members if has_figures(r)),
        "sections": {
            "size": size_section(members, wide, segs, size_words), "medians": {k: stat(in_median(r, k) for r in own) for k in ("ebitda", "net", "roce", "roe")},
            # gl50: totals that add companies together leave out a listed subsidiary whose parent is added too (consolidated_in)
            "growth": aggregate_growth([r for r in own if not r.get("series_break") and not consolidated_in(r, own)]),
            "margins": margin_history([r for r in own if not consolidated_in(r, own)]), "valuation": val,
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
    # gl50: the parent and listed subsidiary pairs, and whether the parent's stored figures are consolidated (its basis) or the whole company's
    out["parents"] = [{"symbol": s, "name": rows[s]["name"], "parent": p["parent"], "parent_name": rows[p["parent"]]["name"] if p["parent"] in rows else p["parent_name"],
                       "pct": p["pct"], "quarter": p["quarter"], "basis": (rows.get(p["parent"]) or {}).get("basis") or "",
                       "parent_wide": p["parent"] in wide, "same_layer": layer_of.get(s) == layer_of.get(p["parent"])}
                      for s, p in sorted(parents.items()) if s in layer_of and p["parent"] in layer_of]
    out["sections"]["margin_drivers"] = margin_drivers(out["sections"]["margins"], rows, layer_of)
    out["sections"]["quarter"] = quarter_section(members, out["sections"]["events"].get("results_filed"))
    # each company's revenue model family: its layer's (theme_base.by_model), unless the layer's model rests on too few of its companies
    model_of = {c["symbol"]: b["model"]["family"] for b in blocks for c in b["companies"]
                if (b.get("model") or {}).get("family") and not b["model"].get("sparse")}
    out["sections"]["sector"] = sector_metrics.section([r for r in own if r.get("status") != "unverified"], region, layer_of, pending, stat, model_of)
    # m53 (R53): each sector's own operating measures (airlines, hospitals, cement, power, payments) where the companies' own stored documents
    # state them, for the companies whose layer the sector's profile fits
    out["sections"]["ops"] = sector_ops.section([r for r in own if r.get("status") != "unverified"], region, layer_of, model_of, src.passages,
                                                {s: p["parent"] for s, p in parents.items()}, layer_of)
    out["metrics_pending"] = sorted(pending)
    out["metrics_families"] = pending_fam           # R29: each one's family, so a kept dive can queue a read the worker dropped again
    out["checks"] = data_checks(listed, blocks, out)
    try:                          # q1: a layer whose count in its calculations fell against the run before, with who left and why
        out["checks"]["cohort"] = cohort_drops(src.cohort_history(slug(theme), cohort_point(blocks, src.today)), blocks)
    except Exception as e:
        print("theme data: layer cohorts not kept:", type(e).__name__, str(e)[:100])
        out["checks"]["cohort"] = []
    out["notable"] = notable_items(blocks, chain, histories)
    return out


# ---------- headlines worth a line ----------
# a quote page, a derivatives table, a list of picks or a price-move roundup is not news about the business (the owner, 7 Nov: "Share Price -
# Live", "Option Chain", put counts, Diwali picks)
NOISE = re.compile(r"share price|stock price|price today|price live|\blive\b.*\bchart\b|option chain|\b(?:put|call) contracts?\b|open interest|"
                   r"stock picks?|stocks? to (?:buy|watch)|top (?:gainers|losers)|gainers (?:&|and) losers|technical (?:signals|view|outlook)|"
                   r"\bquote(?:,| and)|price,? news|multibagger|target price|\bbuy or sell\b|share price target|\bmuhurat\b|"
                   # LIVE6-018: quote and forecast pages ("PANW Stock Quote Price and Forecast | CNN") and evergreen click-bait ("If You Invested
                   # $1000 In CrowdStrike...") are not headlines
                   r"\bstock quotes?\b|\bquote price\b|\b(?:stock|price|share) (?:forecast|prediction)s?\b|\bprice and forecast\b|"
                   r"\bif you(?:'d| had| would have)? invested\b|\bhow much (?:you'd|you would) have\b|\bwould be worth\b|"
                   r"\bmake you (?:a )?(?:rich|millionaire)\b|\bmillionaire[- ]maker\b|\bshould you buy\b|\btime to buy\b|\b(?:is it|still) a buy\b|"
                   r"\bstocks? (?:you|i)(?:'d| would)? (?:should )?(?:buy|own)\b|\bbest stocks?\b|\bno-brainer\b|"
                   # LIVE7A-012: a fund's holding notice ("$AMD Stock Acquired by ... Advisors LLC"), a price-move note ("Shares Down 1.4% -
                   # Here's What Happened"), a "which is the better buy" comparison and a score page ("GF Score: 64/100") are not headlines
                   r"\bbetter buy\b|\bwhich\b.{0,80}\bbuy\b|\bhere'?s (?:what happened|why)\b|"
                   r"\b(?:shares?|stock)\s+(?:(?:is|are)\s+)?(?:up|down|higher|lower|gaps?\s+(?:up|down)|gapped\s+(?:up|down)|trading\s+(?:up|down))\s+[\d.]+%|"
                   r"\b(?:stock|shares|stake|position|holdings?)\s+(?:acquired|sold|purchased|bought|raised|lowered|trimmed|boosted|cut|increased|decreased|reduced)\s+by\b|"
                   r"\b(?:llc|advis[eo]rs?|management|capital|partners|wealth|investments?|asset|trust|fund)\b.{0,40}?\b(?:acquires|sells|buys|raises|lowers|trims|boosts|cuts|"
                   r"increases|decreases|reduces|takes)\s+(?:a\s+)?(?:its\s+)?(?:new\s+)?(?:\$[\d.,]+\w?\s+)?(?:stake|position|holdings?|shares)\s+in\b|"
                   r"\b(?:stake|position|holdings?|shares)\s+in\b.{0,80}\((?:nasdaq|nyse\w*|amex|otc\w*|nse|bse):|"
                   r"\bgf (?:value|score)\b|\bsays (?:over|under)valued\b|\b(?:stock|shares) rating\b|\bprice target\b", re.I)
HOME = {"IN": re.compile(r"\bindia|\bindian\b|\bnse\b|\bbse\b|\bsebi\b|\brbi\b|\bgst\b|₹|\brs\.? ?\d|\bcrore|\blakh", re.I),
        "US": re.compile(r"\bu\.?s\.?\b|\bamerica|\bunited states|\bsec\b|\bnyse\b|\bnasdaq\b|\bfed\b|\$", re.I)}


def headline_kept(item: dict, region: str) -> bool:
    """Whether a headline is about the business: not a quote page, a derivatives table, a list of picks or a price roundup; and a headline
    about the theme in general (no company of the theme in it) must be about the theme's own market (the owner, 7 Nov: Mexico's tax plan,
    Schaeffler's job cuts in Europe in an India theme). It needs a headline and a source (LIVE6-018). An exchange filing with a title is
    always kept."""
    text = str(item.get("headline") or "").strip()
    if item.get("kind") == "filing" or str(item.get("source") or "").lower() in ("exchange filing", "sec filing"):
        return bool(text)
    if not text or not str(item.get("source") or "").strip():          # LIVE6-018: a headline with no source isn't listed as one
        return False
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
        # R44: one list of every figure a check looked at, with its state (verified, not reconciled, invalid) and why; the lists below are
        # read from the same records, so every page counts the same companies
        "states": figure_states(rows),
        # a net margin not reconciled (above the EBITDA margin, or unusual, with nothing stored to give it): shown with †, out of the medians
        "one_off": [{"symbol": r["symbol"], "name": r["name"], "ebitda": r["ebitda"], "net": r["net"], "why": ((r.get("verify") or {}).get("net") or {}).get("why") or "",
                     # R46: the line-by-line record of why the stored lines don't explain it, and where the year's figures come from
                     **({"bridge": r["verify"]["net"]["bridge"]} if ((r.get("verify") or {}).get("net") or {}).get("bridge") else {}),
                     "source": r.get("source"), "lines": source_lines(r.get("filed"))}
                    for r in rows if r.get("one_off") and r.get("status") != "unverified"],
        "held": held_rows(rows),            # R30: figures a check held back (validate_row, validate_model)
        "verified": [x for x in figure_states(rows) if x["state"] == VERIFIED],
        "net_with": (meds.get("net_all") or {}).get("median"), "net_without": (meds.get("net") or {}).get("median"),
        "series": [{"symbol": r["symbol"], "name": r["name"], **({"demerger": r["demerger"]} if r.get("demerger") else {})} for r in rows if r.get("series_break") or series_break(r)],
        "unverified": [{"symbol": r["symbol"], "name": r["name"]} for r in rows if r.get("status") == "unverified"],
        "earlier_quarter": q.get("earlier") or [], "quarter": q.get("quarter"),
        "n": {k: (meds.get(k) or {}).get("n", 0) for k in ("ebitda", "net", "roce", "roe")},
        "lenders": sum(1 for r in rows if r.get("bank") and r.get("status") != "unverified"),
        # companies reporting in another currency (R22): converted at the stated rate, or left out of money totals when there is none
        "currency": [{"symbol": r["symbol"], "name": r["name"], "currency": r["currency"], "rate": (r.get("fx") or {}).get("rate"), "at": (r.get("fx") or {}).get("at")}
                     for r in rows if r.get("fx")],
        # R43.1: of the margins counted only (a company with no EBITDA margin, as most insurers, filed none in whole points: the live
        # Insurance deck said "3 of the 1 EBITDA margins are filed in whole points")
        "whole_points": sum(1 for r in rows if r.get("ebitda") is not None and r.get("ebitda_dp") == 0),
        "with_ebitda": sum(1 for r in rows if r.get("ebitda") is not None),
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
    # LIVE7A-005: a previous or year-ago figure that is another company's own latest figure (the live TMPV "Year ago 37,530 units", Tata
    # Motors CV's October), the same misread: held too
    latest = {}
    for r in rows:
        if r.get("value") is not None:
            latest.setdefault((r.get("unit"), r["value"]), set()).add(r["symbol"])
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
            elif v is not None and latest.get((r.get("unit"), v), set()) - {r["symbol"]}:
                held.append(f"the {'previous' if k == 'prev' else 'year-ago'} figure is another company's latest")
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


BIZ_STALE_MONTHS = {"month": 3, "quarter": 6}       # an operating figure for a period this many months back is old (deck.STALE_MONTHS)


def biz_old(r: dict, today: date) -> bool:
    """Whether an operating figure's period ended more than BIZ_STALE_MONTHS before `today` (LIVE7A-010: Ather's "Q4 FY25", Ola's "Mar 2025",
    SJVN's "Feb 2025" beside October 2026 rows)."""
    try:
        y, m = (int(x) for x in str(r.get("period")).split("-")[:2])
    except ValueError:
        return False
    return (today.year - y) * 12 + today.month - m > BIZ_STALE_MONTHS.get(r.get("span") or "month", 3)


def business_section(blocks: list[dict], subs: list[dict], names: dict, read, today: date | None = None) -> dict:
    """Operating figures by layer and sub-theme, plus how many of the theme's companies have one; figures that need checking are held
    (hold_suspect) across the whole theme, since two companies can share a misread filing. LIVE7A-010: a figure for an old period
    (biz_old) is left out, and a company's figure is listed once: under its layer, or under a sub-theme only when no layer lists it."""
    today = today or date.today()
    fresh = lambda rows: [r for r in rows if not biz_old(r, today)]      # noqa: E731
    every = {}
    for b in blocks:
        b["business"] = fresh(business_rows([c["symbol"] for c in b["companies"]], names, read))
        every.update({r["symbol"]: r for r in b["business"]})
    in_layers = set(every)
    for s in subs:
        s["business"] = fresh(business_rows([c["symbol"] for c in s["companies"] if c["symbol"] not in in_layers], names, read))
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

SUB_GENERIC = {"and", "of", "the", "for", "in", "with", "operators", "operator", "companies", "company", "makers", "maker", "providers", "provider",
               "services", "service", "network", "networks", "players", "firms", "suppliers", "supplier", "other", "related", "solutions",
               "carriers", "carrier"}
# R35 (GPT review of R31.9: Jio left out of "Mobile network operators"; its line says "networks, devices, applications"): a sub-theme's own
# word, said another way in a company's description. word -> (words that name the same business, a wider phrase that counts only when
# the description names no narrower business, those narrower businesses). Used only for the map layer that holds most of the sub-theme's
# own companies, so a handset distributor or a messaging platform elsewhere on the map never joins by "mobile".
_MOBILE = (r"mobile|mobility|wireless|cellular|\bgsm\b|pre-?paid|post-?paid|\b[2-5]g\b|\blte\b",
           r"telecom(?:munications?)?\s+(?:services?|operators?|service\s+providers?|compan(?:y|ies))|providers?\s+of\s+telecom(?:munications?)?\s+services",
           r"broadband|fixed[- ]?line|landline|wire-?line|\bwired\b|internet\s+service|leased\s+lines?|fib(?:re|er)|cable|towers?|equipment|"
           r"enterprise|satellite|handsets?")
SUB_ALSO = {"mobile": _MOBILE, "wireless": _MOBILE, "cellular": _MOBILE}
# a sentence that says the business ended names it no longer ("discontinued its GSM mobile services in 2017")
_ENDED = re.compile(r"discontinu|ceased|exited|shut\s+down|surrender|divest|sold\s+its|transferred\s+its|no\s+longer", re.I)


def _names_word(word: str, text: str, wide: bool) -> bool:
    """Whether a company's description names a sub-theme's word: the word itself, or (`wide`: the company sits in the sub-theme's main
    layer) another way of saying it (SUB_ALSO), in a sentence that doesn't say the business ended."""
    live = " ".join(x for x in re.split(r"(?<=[.;])\s+", text) if not _ENDED.search(x))
    if re.search(rf"\b{word}", live):
        return True
    if not wide or word not in SUB_ALSO:
        return False
    same, wider, narrower = SUB_ALSO[word]
    return bool(re.search(same, live)) or bool(re.search(wider, live) and not re.search(narrower, live))


def sub_members(sub: dict, layers: list, about_of=None) -> list:
    """A sub-theme's companies, completed from the map (R34, GPT review of R31.5: Bharti Airtel left out of "Mobile network operators" while
    in the "Mobile and broadband operators" layer): a company of a map layer that holds one of the sub-theme's own companies joins it when its
    own description names every word that sets the sub-theme apart (at most two: "mobile"); a name of more such words is left as the map has it.
    R35: the description is the company's line and, where kept, its whole stored description (`about_of(symbol)`, never read from a source
    here); in the layer that holds most of the sub-theme's own companies a word also counts when said another way (SUB_ALSO: wireless,
    cellular, "telecommunication services" with no narrower business named), so a broadband-only company stays out."""
    own = list(sub.get("companies") or [])
    have = {c.get("ticker") for c in own}
    words = [w for w in re.findall(r"[a-z]+", str(sub.get("name") or "").lower()) if w not in SUB_GENERIC and len(w) > 2]
    if not have or not 1 <= len(words) <= 2:
        return own
    first = set(have)
    shared = [(len(first & {c.get("ticker") for c in v.get("companies") or []}), v) for v in layers if not v.get("official")]
    most = max((n for n, _ in shared), default=0)
    main = next((v for n, v in shared if n and n == most), None)
    for n, v in shared:
        if not n:
            continue
        for c in v.get("companies") or []:
            if c.get("ticker") in have:
                continue
            more = ""
            if about_of is not None:
                try:
                    more = str(about_of(c.get("ticker")) or "")
                except Exception:
                    more = ""
            what = f"{c.get('what') or ''}. {more}".lower()
            if what.strip(" .") and all(_names_word(w, what, v is main) for w in words):
                own.append(c)
                have.add(c.get("ticker"))
    return own
