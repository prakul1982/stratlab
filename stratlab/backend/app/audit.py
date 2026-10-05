"""The data audit: every company in a set run through the deep dive's numbers, checks and documents on the live server,
with each number compared against its source and every gap written down. Run from the admin page; nothing here uses
AI, so a full run costs no AI allowance. The aim is that nothing StratLab shows needs checking anywhere else."""
import threading
import re
import time
from datetime import datetime, timedelta, timezone

from . import db, sector_members, universes
from .kite_service import not_company

KEY = "audit:last"
MAX_SYMBOLS = 600
PE_TOLERANCE = 0.25            # our P/E from market cap and trailing profit vs the page's stated P/E (minority
                               # shares and one-offs beyond this are explained on the page by a note)
TTM_TOLERANCE = 0.05           # trailing-year revenue vs the last four quarters added up
TTM_ROUNDING = 2               # ...but tiny companies' quarters are shown in whole crore, so 2 cr apart is rounding
PRICE_TOLERANCE = 0.03         # prices from different sources, allowing for a day's move
PRICE_TICK = 0.02              # ...but a cent or two apart on a penny stock is just its price step


# whole NSE indices, read from the exchange's own constituent lists when the audit starts
INDEX_SETS = {"nifty500": ("NIFTY 500", "NIFTY 500", 500), "niftynext50": ("NIFTY NEXT 50", "NIFTY Next 50", 50),
              "midcap150": ("NIFTY MIDCAP 150", "NIFTY Midcap 150", 150), "smallcap250": ("NIFTY SMALLCAP 250", "NIFTY Smallcap 250", 250)}


def sets(region: str = "IN") -> list[dict]:
    """The sets an audit can run on: the ready-made groups, every sector's main stocks, and (India) whole NSE indices."""
    if region == "US":
        out = [{"id": p["id"], "name": p["name"], "count": len(p["symbols"])} for p in universes.PRESETS["US"]]
        return out + [{"id": "sectors", "name": "Every sector's main US stocks", "count": len(all_sector_stocks("US"))}]
    out = [{"id": p["id"], "name": p["name"], "count": len(p["symbols"])} for p in universes.PRESETS["IN"]]
    every = all_sector_stocks()
    out.append({"id": "sectors", "name": "Every sector's main stocks", "count": len(every)})
    out += [{"id": k, "name": f"{name} (the exchange's list)", "count": n} for k, (_, name, n) in INDEX_SETS.items()]
    return out


def all_sector_stocks(region: str = "IN") -> list[str]:
    seen: list[str] = []
    for p in universes.PRESETS[region]:
        seen += [s for s in p["symbols"] if s not in seen]
    for syms in getattr(sector_members, region).values():
        seen += [s for s in syms if s not in seen]
    return seen


def symbols_for(set_id: str, custom: list[str] | None = None, members=None, region: str = "IN") -> list[str]:
    """`members(index)` gives an NSE index's stocks (the exchange feed), for the whole-index sets."""
    if set_id in INDEX_SETS and not custom and region == "IN":
        if members is None:
            raise ValueError("Index lists aren't available here.")
        return members(INDEX_SETS[set_id][0])[:MAX_SYMBOLS]
    if custom:
        return list(dict.fromkeys(s.strip().upper() for s in custom if s.strip()))[:MAX_SYMBOLS]
    if set_id == "sectors":
        return all_sector_stocks(region)[:MAX_SYMBOLS]
    for p in universes.PRESETS[region]:
        if p["id"] == set_id:
            return list(p["symbols"])
    raise ValueError("Unknown set")


# What a finding is: a number that disagrees with its source (mismatch), something a user would still have to look up
# elsewhere (gap), a source failing in a way that needs fixing (error), a true fact about the company that explains a
# blank, such as a recent listing or no earnings calls (fact), or a check that couldn't run because a source turned us
# away or was down (pending: it is checked again later, and isn't a finding about the company at all).
LEVELS = ("mismatch", "error", "gap", "fact", "pending")

# a source turning us away or not answering: the company wasn't checked, nothing is wrong with it
RETRY_LATER = re.compile(r"refused the request|isn't answering|is busy|having trouble|rate limiting|sent a page instead|"
                         r"sent something that isn't data|couldn't reach|server disconnected|unknown content-type|"
                         r"service unavailable|bad gateway|gateway time|timed? ?out|connection (?:reset|aborted)|"
                         r"not available from BSE right now", re.I)


def _issue(level: str, area: str, detail: str) -> dict:
    return {"level": level, "area": area, "detail": detail}


PLAIN_MAX = 1000                # a source's message is untrusted and can be a whole page: the regex below is
                               # quadratic on long runs, and only the first 120 to 200 characters are ever shown


def _plain(why) -> str:
    """A source's message without its "Try again later." (the audit says when it tries again)."""
    return re.sub(r"\s*Try again[^.]*\.?\s*$", "", str(why or "")[:PLAIN_MAX]).strip().rstrip(".")


def _later(area: str, why: str) -> dict:
    """A check to run again later: "Not checked yet: the exchange feed refused the request (403)."."""
    why = _plain(why) or "a source didn't answer"
    if why[1:2].islower():                    # "The exchange..." reads "the exchange...", "SEC EDGAR..." stays
        why = why[0].lower() + why[1:]
    return _issue("pending", area, f"Not checked yet: {why}. It is checked again later.")


def _off(a, b) -> float | None:
    """How far apart two numbers are, as a fraction of the second."""
    if a is None or b is None or not b:
        return None
    return abs(a - b) / abs(b)


def _last_ttm(table: dict | None, *prefixes: str):
    """The trailing-twelve-month value of a row, when the table has a TTM column."""
    if not table or not table.get("cols") or str(table["cols"][-1]).upper() != "TTM":
        return None
    for name, vals in (table.get("rows") or {}).items():
        if any(name.lower().startswith(p.lower()) for p in prefixes) and vals:
            return vals[-1] if len(vals) == len(table["cols"]) else None
    return None


FINANCIAL = {"lender", "insurer", "holding", "bdc"}
NO_REVENUE = "No revenue reported in any year: a company without sales yet"
NO_PLANT = "No capex: the filings show no plant, property or equipment, so there is nothing to spend capex on"


def short_history(n: int) -> str:
    return f"Only {n} year{'s' if n != 1 else ''} of annual results so far: listed, demerged or first reporting recently"


DVR = re.compile(r"\bDVR\b|differential voting", re.I)
NO_RESULTS_DVR = "Shares with differential voting rights (DVR): the company's results are shown under its ordinary shares"
NO_RESULTS_YET = "No annual results on the company page yet: listed recently"


def _margins(p: dict, years: list[dict]) -> list[dict]:
    """Years whose operating margin is above 100%, read against the page's own sales and costs: nil or negative sales
    (returns or reversals: a margin of nothing), costs that came out negative (written back), and a margin the sales
    and costs don't explain, which is worth a look. Filings without a costs line (US) can only say what they show."""
    odd = [y for y in years if y.get("opm") is not None and y["opm"] > 100]
    if not odd:
        return []
    pl = p.get("pl") or {}
    costs = next((dict(zip(pl.get("cols") or [], v)) for k, v in (pl.get("rows") or {}).items() if k.lower().startswith("expenses")), None)
    src = "The filings show" if p.get("region") == "US" else "The company page shows"
    if costs is None:              # no costs line (US filings): the page's own figure, shown as filed
        return [_issue("gap", "Numbers", f"{src} an operating margin above 100% in {', '.join(y['year'] for y in odd[:4])} (costs written back)")]
    nil = [y["year"] for y in odd if y.get("sales") is not None and y["sales"] <= 0]
    back = [y["year"] for y in odd if y["year"] not in nil and (costs.get(y["year"]) or 0) < 0]
    rest = [y["year"] for y in odd if y["year"] not in nil + back]
    out = []
    if nil:
        out.append(_issue("fact", "Numbers", f"Sales were nil or negative in {', '.join(nil[:4])} (returns or reversals), so the operating margin there is not a margin"))
    if back:
        out.append(_issue("fact", "Numbers", f"Costs were written back in {', '.join(back[:4])} (negative expenses), so the operating margin is above 100%"))
    if rest:
        out.append(_issue("gap", "Numbers", f"{src} an operating margin above 100% in {', '.join(rest[:4])} that its sales and costs don't explain"))
    return out


def check_numbers(p: dict, nums: dict, snap: dict, group: str | None = None, young: bool = False) -> list[dict]:
    """`young`: the shares have traded for under 30 days, so a page without annual results is a new listing's."""
    out = []
    years = nums.get("years") or []
    if not years:
        if DVR.search(p.get("name") or ""):
            out.append(_issue("fact", "Numbers", NO_RESULTS_DVR))
        elif young:
            out.append(_issue("fact", "Numbers", NO_RESULTS_YET))
        else:
            out.append(_issue("gap", "Numbers", "Only 0 years of annual results"))
    elif len(years) < 5:              # the source shows every year there is: fewer is a young company, not missing data
        out.append(_issue("fact", "Numbers", short_history(len(years))))
    no_sales = [y["year"] for y in years if y.get("sales") is None]
    missing = [y["year"] for y in years if y.get("sales") is None or y.get("profit") is None]
    first = next((i for i, y in enumerate(years) if y.get("sales") is not None), len(years))
    before = [y["year"] for y in years[:first]]                   # years before its first sales, with a profit (loss) filed
    # years whose annual report has no revenue line at all (US filings): no sales that year, not a figure we missed
    none_filed = set(nums.get("no_revenue") or [])
    stopped = [y["year"] for y in years[first:] if y["year"] in none_filed and y.get("profit") is not None]
    if years and len(no_sales) == len(years) and all(y.get("profit") is not None for y in years):
        out.append(_issue("fact", "Numbers", NO_REVENUE))         # a company with no sales yet (in development, a shell)
    elif missing and missing == before and all(y.get("profit") is not None for y in years[:first]):
        out.append(_issue("fact", "Numbers", f"No revenue before {years[first]['year']}: sales began then"))
    elif missing:
        if stopped:
            out.append(_issue("fact", "Numbers", f"No revenue in {', '.join(stopped[:4])}: the annual report shows no sales that year"))
        rest = [y for y in missing if y not in stopped and not (y in before and y in none_filed)]
        if rest:
            out.append(_issue("gap", "Numbers", f"Revenue or profit missing for {', '.join(rest[:4])}"))
    if not nums.get("bank") and group not in FINANCIAL:
        out += _margins(p, years)
        if len(years) >= 3 and all(y.get("capex") is None for y in years[-3:]):
            out.append(_issue("fact", "Capex", NO_PLANT) if p.get("region") == "US" and not _plant(p, 3)
                       else _issue("gap", "Capex", "No capex estimate for the last three years"))
    ttm = _last_ttm(p.get("pl"), "Net Profit")
    fx = _usd_rate(p)
    if snap.get("pe") and snap.get("market_cap_cr") and ttm and ttm > 0 and fx:
        ours = snap["market_cap_cr"] / (ttm * fx)
        off = _off(ours, snap["pe"])
        explained = any("P/E is based on" in n for n in nums.get("notes") or [])
        if off is not None and off > PE_TOLERANCE and not explained:
            out.append(_issue("mismatch", "Valuation", f"P/E {snap['pe']:.1f} on the company page, {ours:.1f} from market cap ÷ trailing profit"))
    ttm_sales = _last_ttm(p.get("pl"), "Sales", "Revenue")
    q = [x.get("sales") for x in (nums.get("quarters") or [])[-4:]]
    if ttm_sales and len(q) == 4 and all(v is not None for v in q):
        off = _off(sum(q), ttm_sales)
        if off is not None and off > TTM_TOLERANCE and abs(sum(q) - ttm_sales) > TTM_ROUNDING:
            if p.get("region") == "US":            # in the filings' own unit: "$1,204 m", "CAD 95 m"
                from .deepdive import money
                unit = p.get("unit") or nums.get("unit") or "$ million"
                out.append(_issue("mismatch", "Numbers", f"Trailing revenue {money(ttm_sales, unit)} vs last four quarters {money(sum(q), unit)}"))
            else:
                out.append(_issue("mismatch", "Numbers", f"Trailing revenue {ttm_sales:,.0f} cr vs last four quarters {sum(q):,.0f} cr"))
    return out


def _plant(p: dict, n: int) -> bool:
    """Whether the balance sheet shows any plant, property or equipment in the last `n` years."""
    vals = (((p.get("balance") or {}).get("rows") or {}).get("Fixed Assets") or [])[-n:]
    return any(v for v in vals)


def _usd_rate(p: dict) -> float | None:
    """Dollars to one unit of the company's reporting currency (US filings), so a market value in dollars can be set
    against its reported profit; 1 for everything reported in the market's own currency."""
    if p.get("currency") in (None, "USD", "INR"):
        return 1.0
    return (p.get("fx") or {}).get("rate")


NO_PRICES = {    # why there's no trend: the facts first, then a source to try again
    "new": ("fact", "Listed recently: fewer than 30 trading days of prices, so no trend or stage yet"),
    "untraded": ("fact", "Not trading now (suspended, or not on the exchange's trading list), so no daily prices"),
    "stale": ("fact", "No trades for over a month (suspended or illiquid), so no current trend or stage"),
}


def _near(ours: float, other: float) -> bool:
    off = _off(ours, other)
    return off is None or off <= PRICE_TOLERANCE or abs(ours - other) <= PRICE_TICK


def _in_range(ours: float, low, high) -> bool:
    """Within the session's traded range (with the usual tolerance): a close read a few minutes before or after the
    company page's quote, on a stock moving fast that day, is the same session's price, not a different one."""
    return bool(low and high and low * (1 - PRICE_TOLERANCE) <= ours <= high * (1 + PRICE_TOLERANCE))


def _quote(exchange) -> dict:
    """The exchange's quote as {"price", "prev_close", "low", "high", "at"}, from a dict like that, a (last price,
    previous close) pair or a bare last price."""
    if isinstance(exchange, dict):
        return exchange
    if isinstance(exchange, (list, tuple)):
        return {"price": exchange[0] if exchange else None, "prev_close": exchange[1] if len(exchange) > 1 else None}
    return {"price": exchange}


def _agrees(ours: float, day: str | None, q: dict) -> bool:
    """Our last daily close agrees with the exchange's quote: near its last price or its previous close (a thinly
    traded stock's close can be a day older than its last trade), or, when the quote's last trade was on the same
    day as our close, anywhere in that day's range: BSE's closing price is the average of the last half hour's
    trades, which on a thin stock can sit well away from the last one."""
    if any(_near(ours, x) for x in (q.get("price"), q.get("prev_close")) if x):
        return True
    lo, hi, at = q.get("low"), q.get("high"), str(q.get("at") or "")
    return bool(day and at[:10] == day[:10] and lo and hi and lo - PRICE_TICK <= ours <= hi + PRICE_TICK)


def check_prices(snap: dict, trend: dict | None, exchange, why: str | None = None, page_quote=None) -> list[dict]:
    """Our last daily close against the exchange's quote and the company page. `exchange` is the quote (see _quote
    and _agrees).
    `page_quote` is the company page's own (last price, previous close[, day high, day low]) when it has them (US):
    the page's price can be today's while our last daily close is yesterday's, so its previous close counts too, as
    the exchange's does, and a close anywhere in the page's day range is that session's price read at another minute.
    A page with only a price (India) can be a session behind ours: our previous close counts too.
    `why` says why there's no trend when there isn't one ("new", "untraded", "stale" or "error")."""
    out = []
    if not trend:
        if why == "error":
            out.append(_later("Prices", "daily prices couldn't be read"))
        else:
            level, text = NO_PRICES.get(why or "", ("gap", "No daily prices, so no trend or stage"))
            out.append(_issue(level, "Prices", text))
    ours = trend.get("price") if trend else None
    q = _quote(exchange)
    shown = q.get("price") or q.get("prev_close")
    if ours is not None and shown and not _agrees(ours, trend.get("t"), q):
        out.append(_issue("mismatch", "Prices", f"Last close {ours:,.2f} vs {shown:,.2f} on the exchange's live quote"))
    elif ours is not None and snap.get("price"):
        page = [x for x in (page_quote or ())[:2] if x] or [snap["price"]]
        hi, lo = (tuple(page_quote or ())[2:4] + (None, None))[:2]
        chg = trend.get("chg")
        before = ours / (1 + chg / 100) if page_quote is None and chg is not None and chg > -100 else None
        if not any(_near(x, on_page) for on_page in page for x in (ours, before) if x) and not _in_range(ours, lo, hi):
            prev = f" (previous close {page[1]:,.2f})" if len(page) > 1 else ""
            out.append(_issue("mismatch", "Prices", f"Last close {ours:,.2f} vs {page[0]:,.2f} on the company page{prev}"))
    return out


def _no_sales(rows: list[dict]) -> bool:
    return any(r.get("sales") is not None and r["sales"] <= 0 for r in rows)


def _why_na(label: str, years: list[dict], quarters: list[dict]) -> str | None:
    """Why a check couldn't be judged when it is a fact about the company, not a missing number: "history" (too few
    years or quarters of results to measure growth over, losses to grow from or turn into cash, no insider trades
    filed, too short a price history for a stage) or "sales" (no sales in a year the check compares: growth and a
    margin need sales). None: a number is missing."""
    if label.startswith(("Insider", "Promoter and insider")):        # "None": no trades filed is an answer
        return "history"
    if label.startswith("Price in Stage"):
        return "history"                          # the stage needs 170 trading days of prices: a young listing has none yet
    sold = [y for y in years if y.get("sales") is not None]          # the years the checklist measures over
    last3, last4 = years[-3:], years[-4:]
    if label.startswith(("Sales growth", "Operating margin holding up")):
        if len(years) < 4:
            return "history"
        # a year in the window whose annual report shows no revenue line at all (US filings): no sales that year
        if any(y.get("sales") is None and y.get("no_revenue") for y in last4):
            return "sales"
        return "sales" if len(sold) >= 4 and _no_sales(sold[-4:][:1] + sold[-1:]) else None
    if label.startswith("Profit growth"):
        return "history" if len(years) < 4 or any((y.get("profit") or 0) <= 0 for y in last4[:1] + last4[-1:]) else None
    if label.startswith("Latest quarter"):
        return "history" if len(quarters) < 5 else "sales" if _no_sales(quarters[-5:][:1] + quarters[-1:]) else None
    if label.startswith(("Profit turning into cash", "Free cash flow")):
        return "history" if len(years) < 3 or sum(y.get("profit") or 0 for y in last3) <= 0 else None
    return None


def check_view(view: dict, told: dict | None = None, price_why: str | None = None) -> list[dict]:
    """Classification, valuation, checklist and documents, from the same view a user sees. US companies are checked
    for their annual and quarterly reports; Indian ones for presentations and call transcripts. `told`: what an Indian
    company told the exchange in the period (deepdive.meetings: its meetings, its calls among them and its filings of
    any kind; None: unknown). `price_why`: why there are no daily prices, when there aren't ("new", "untraded"...)."""
    out = []
    cl = view.get("checklist") or {}
    ind = cl.get("industry") or {}
    if not ind.get("path"):
        label = ind.get("label") or "a general business"
        if price_why in ("new", "untraded"):      # the exchange classifies a company once it trades
            out.append(_issue("fact", "Industry", f"No industry classification yet (a new listing, or not trading); treated as {label}"))
        else:
            out.append(_issue("gap", "Industry", f"No industry classification; treated as {label}"))
    v = view.get("valuation") or {}
    if v.get("value") is None and "There's no" not in (v.get("why") or ""):      # a loss or negative net worth is said
        out.append(_issue("gap", "Valuation", f"No {v.get('short') or 'valuation'} figure"))
    nums = view.get("numbers") or {}
    none_filed = set(nums.get("no_revenue") or [])
    years = [{**y, "no_revenue": y.get("year") in none_filed} for y in nums.get("years") or []]
    quarters = nums.get("quarters") or []
    na = [c["label"] for c in cl.get("checks", []) if c.get("state") == "na"]
    why = {x: _why_na(x, years, quarters) for x in na}
    unexplained = [x for x in na if not why[x]]
    if len(unexplained) >= 3:
        out.append(_issue("gap", "Checklist", f"{len(unexplained)} checks couldn't be judged: {', '.join(unexplained[:5])}"))
    elif len(na) >= 3:
        unsold = [x for x in na if why[x] == "sales"]
        young = [x for x in na if why[x] == "history"]
        if unsold:
            out.append(_issue("fact", "Checklist", f"{len(unsold)} check{'s' if len(unsold) != 1 else ''} can't be judged "
                                                   f"without sales (none in a year compared): {', '.join(unsold)}"))
        if young:
            out.append(_issue("fact", "Checklist", f"{len(young)} checks need more history than the company has yet: {', '.join(young[:5])}"))
    if view.get("doc_note"):
        note = view["doc_note"]
        out.append(_later("Documents", note) if RETRY_LATER.search(note) else _issue("error", "Documents", note))
    elif view.get("region") == "US":
        docs = view.get("documents") or []
        kinds = [d["kind"] for d in docs]
        foreign = any(d.get("form") in ("20-F", "20-F/A", "40-F", "40-F/A") for d in docs)   # foreign companies file no 10-Qs
        if "annual_report" not in kinds and "quarterly_report" not in kinds:
            out.append(_issue("fact", "Documents", STOPPED_FILING))
        elif "annual_report" not in kinds:
            out.append(_issue("fact", "Documents", LATE_ANNUAL))
        elif "quarterly_report" not in kinds and not foreign:
            out.append(_issue("gap", "Documents", "No quarterly report (10-Q) filed in the last two years"))
    else:
        out += _india_documents([d["kind"] for d in view.get("documents") or []], told, price_why)
    return out


def _india_documents(kinds: list[str], told: dict | None, price_why: str | None) -> list[dict]:
    """An Indian company's presentations and transcripts against what it told the exchange. A deck isn't required
    for every meeting, so none filed is a fact; a transcript is required for every earnings call (not for a meeting
    with an investor), so calls without one found is a gap, ours to look into."""
    if told is not None and not told.get("filed"):
        if price_why in ("untraded", "stale"):
            return [_issue("fact", "Documents", NOTHING_FILED)]
        return [_issue("gap", "Documents", NO_FILINGS_READ)]
    meets, calls = (told or {}).get("meets"), (told or {}).get("calls")
    if "presentation" not in kinds and "transcript" not in kinds and meets == 0:
        return [_issue("fact", "Documents", NO_MEETS)]                   # many small companies hold no calls at all
    out = []
    if "presentation" not in kinds:
        out.append(_issue("gap", "Documents", "No investor presentation filed in the last two years") if meets is None else
                   _issue("fact", "Documents", f"Filed no investor presentation in the last two years, though {meets} of its "
                                               "filings are about calls or meetings with investors"))
    if "transcript" not in kinds:
        if calls is None:
            out.append(_issue("gap", "Documents", "No call transcript filed in the last two years"))
        elif calls == 0:
            out.append(_issue("fact", "Documents", NO_CALLS if meets else NO_CALLS_TOLD))
        else:
            out.append(_issue("gap", "Documents", f"No call transcript found, though {calls} of its filings in the last two "
                                                  "years are about earnings calls"))
    return out


STOPPED_FILING = "No annual or quarterly report filed in the last two years: the company has stopped filing with the SEC"
LATE_ANNUAL = ("No annual report (10-K, 20-F or 40-F) filed in the last two years, though it still files quarterly "
               "reports: its annual report is late")
NO_MEETS = ("Held no earnings calls or analyst meetings in the last two years (none told to the exchange), "
            "so there's no presentation or call transcript to read")
NO_CALLS = ("Held no earnings call in the last two years (only meetings with analysts or investors were told to the "
            "exchange), so there's no call transcript to read")
NO_CALLS_TOLD = ("Held no earnings call in the last two years (no calls or meetings with investors were told to the "
                 "exchange), so there's no call transcript to read")
NOTHING_FILED = ("Filed nothing with the exchange in the last two years (its shares aren't trading), so there's no "
                 "presentation or call transcript to read")
NO_FILINGS_READ = ("No filings came back from the exchange for the last two years, though a trading company files its "
                   "results every quarter: its documents couldn't be looked for")


def check_documents(docs: list[dict], read) -> list[dict]:
    """Whether the newest presentation and the newest transcript can be turned into text (the step that decides
    whether the AI read and the report card can work). `read(candidates, problems)` returns the readable pairs."""
    out = []
    for kind, label in (("presentation", "presentation"), ("transcript", "call transcript")):
        cands = [d for d in docs if d["kind"] == kind]
        if not cands:
            continue
        problems: list[str] = []
        try:
            got = read(cands, problems)
        except Exception as e:
            got, problems = [], [str(e)]
        if not got:
            out.append(_issue("gap", "Documents", f"No readable {label}: {'; '.join(problems[:2]) or 'nothing came back'}"))
    return out


# nothing for the app to show, and that's a fact about the security: funds, SPACs and shells file no annual results,
# foreign companies traded over the counter file nothing with the SEC, and some report in another currency
NOT_COVERED = ("has no annual results filed", "isn't a company that files with the SEC", "has nothing for that",
               "not US dollars", "can't be shown here", "no business numbers to show")
# SEC industry codes of securities with no operating business to check: blank-check companies (SPACs), and funds and
# trusts that hold investments or commodities
NOT_OPERATING = {"6770": "a blank-check company (SPAC) with no business of its own yet",
                 "6722": "an investment fund", "6726": "an investment fund or trust", "6221": "a commodity fund or trust"}
FUND_OR_TRUST = "an exchange-traded fund, or a real-estate or infrastructure trust"


def restate(issue: dict, us: bool = False) -> dict | None:
    """A stored finding read with today's rules, so a company checked under older rules isn't re-run just to drop a
    false alarm: None when today's rules wouldn't report it."""
    level, area, detail = issue.get("level"), issue.get("area"), str(issue.get("detail") or "")
    num = lambda x: float(x.replace(",", ""))   # noqa: E731
    if level == "mismatch" and detail.startswith("Operating margin above 100% in "):
        src = "The filings show" if us else "The company page shows"
        return _issue("gap", area, f"{src} an operating margin above 100% in {detail[31:]} (costs written back)")
    m = re.match(r"Trailing revenue \$?m?([\d,.]+)(?: cr)? vs last four quarters \$?m?([\d,.]+)(?: cr)?$", detail)
    if level == "mismatch" and m:
        a, b = num(m[1]), num(m[2])
        if abs(a - b) <= TTM_ROUNDING:
            return None
        if us:                                  # a US company's figures are in $ million, never crore
            from .deepdive import money
            return _issue(level, area, f"Trailing revenue {money(a, '$ million')} vs last four quarters {money(b, '$ million')}")
        return issue
    m = re.match(r"Last close ([\d,.]+) vs ([\d,.]+)", detail)
    if level == "mismatch" and area == "Prices" and m and abs(num(m[1]) - num(m[2])) <= PRICE_TICK:
        return None
    if level in ("error", "gap") and area == "Company page" and any(x in detail for x in NOT_COVERED):
        return _issue("fact", area, detail)
    if level == "error" and RETRY_LATER.search(detail):        # a source turned us away: not checked, not wrong
        return _later(area, detail.removeprefix("Exchange price unavailable: ")[:120])
    m = re.match(r"Only (\d+) years? of annual results$", detail)
    if level == "gap" and m and int(m[1]) > 0:
        return _issue("fact", area, short_history(int(m[1])))
    if level == "gap" and area == "Documents" and detail.startswith("No annual report (10-K"):
        return _issue("fact", area, LATE_ANNUAL)
    if area == "Company page" and detail.startswith(("SEC EDGAR has nothing for that", "The SEC has nothing for that")):
        return _issue("fact", area, OLD_NOTHING)      # checked before the reason was read: said plainly until re-checked
    return issue


def restate_row(row: dict, us: bool = False) -> list[dict]:
    """A stored company's findings with today's rules, including those that depend on each other: checks a short
    history explains are a fact, and no annual and no quarterly report together mean the company stopped filing."""
    issues = [x for x in (restate(i, us) for i in row.get("issues") or []) if x]
    details = [i["detail"] for i in issues]
    if any(d.startswith("Only ") and "so far" in d for d in details):
        issues = [_issue("fact", "Checklist", i["detail"].replace("couldn't be judged", "need more history than the company has yet"))
                  if i["area"] == "Checklist" and i["level"] == "gap" else i for i in issues]
    if us and any(d.startswith("No annual report") for d in details) and any(d.startswith("No quarterly report") for d in details):
        issues = [i for i in issues if not i["detail"].startswith(("No annual report", "No quarterly report"))]
        issues.append(_issue("fact", "Documents", STOPPED_FILING))
    return issues


# the old wording for a company with no figures filed as data, before the reason was read from its filings
OLD_NOTHING = "The SEC has no financial statements filed as data for this company, so its results can't be shown here."


class Skipped(Exception):
    pass


class Breaker:
    """Stops calling a source after it has failed `limit` times in a row (the same refusal on every company is one
    finding, not two hundred); later calls raise Skipped."""

    def __init__(self, fn, limit: int = 3):
        self.fn, self.limit, self.fails = fn, limit, 0

    def __call__(self, *a):
        if self.fails >= self.limit:
            raise Skipped()
        try:
            out = self.fn(*a)
        except Exception:
            self.fails += 1
            raise
        self.fails = 0
        return out


def audit_company(sym: str, base_fn, view_fn, exchange_price=None, read=None) -> dict:
    """One company, start to finish. Each source failing shows up as a row (an error, or a check to run again when the
    source only turned us away), never stops the run."""
    t0 = time.monotonic()
    issues: list[dict] = []
    name = sym
    try:
        base = base_fn(sym)
        p = base["p"]
        if p.get("region") == "US" and str(p.get("sic") or "") in NOT_OPERATING:
            what = NOT_OPERATING[str(p["sic"])]
            return {"symbol": sym, "name": p.get("name") or sym, "seconds": round(time.monotonic() - t0, 1),
                    "issues": [_issue("fact", "Company page", f"Not an operating company: {what}, so there are no business numbers to check")]}
        if p.get("region") != "US" and not_company(p.get("name")):      # an ETF or trust the broker's list names otherwise
            return {"symbol": sym, "name": p["name"], "seconds": round(time.monotonic() - t0, 1),
                    "issues": [_issue("fact", "Company page", f"Not an operating company: {FUND_OR_TRUST}, so there are no business numbers to check")]}
        view = view_fn(sym, base)
        name = view.get("name") or sym
        group = ((view.get("checklist") or {}).get("industry") or {}).get("group")
        issues += check_numbers(p, view["numbers"], view.get("snapshot") or {}, group, young=base.get("trend_why") == "new")
        ex = None
        if exchange_price:
            try:
                ex = exchange_price(sym)
            except Skipped:
                ex = None
            except Exception as e:
                why = _plain(e)[:120] or e.__class__.__name__
                issues.append(_later("Prices", f"the exchange's quote couldn't be read ({why})") if RETRY_LATER.search(why)
                              else _issue("error", "Prices", f"Exchange price unavailable: {why}"))
        q = base.get("quote") or {}
        issues += check_prices(view.get("snapshot") or {}, base.get("trend"), ex, base.get("trend_why"),
                               (q.get("price"), q.get("prev_close"), q.get("high"), q.get("low")) if q else None)
        issues += check_view(view, base.get("told"), base.get("trend_why"))
        if read and view.get("documents"):
            issues += check_documents(view["documents"], lambda c, pr: read(c, pr, p))
    except Exception as e:
        d = getattr(e, "detail", None)          # an HTTP error from a data source carries its message here
        msg = d.get("message") if isinstance(d, dict) else d if isinstance(d, str) else str(e)
        msg = (msg or e.__class__.__name__)[:200]
        if any(x in msg for x in NOT_COVERED):    # shells, SPACs, trusts and funds: nothing to show, not something broken
            issues.append(_issue("fact", "Company page", msg))
        elif RETRY_LATER.search(msg):             # the source was down or turned us away: check again later
            issues.append(_later("Company page", msg))
        else:
            issues.append(_issue("error", "Company page", msg))
    return {"symbol": sym, "name": name, "seconds": round(time.monotonic() - t0, 1), "issues": issues}


def summarise(rows: list[dict]) -> dict:
    by_area: dict[str, dict[str, int]] = {}
    for r in rows:
        for i in r["issues"]:
            a = by_area.setdefault(i["area"], {k: 0 for k in LEVELS})
            a[i["level"] if i["level"] in a else "gap"] += 1
    clean = sum(1 for r in rows if all(i["level"] == "fact" for i in r["issues"]))      # facts are nothing wrong
    secs = [r["seconds"] for r in rows]
    total = lambda k: sum(a[k] for a in by_area.values())     # noqa: E731
    return {"companies": len(rows), "clean": clean, "by_area": by_area,
            "mismatches": total("mismatch"), "gaps": total("gap"), "errors": total("error"), "facts": total("fact"),
            "pending": sum(1 for r in rows if any(i["level"] == "pending" for i in r["issues"])),
            "avg_seconds": round(sum(secs) / len(secs), 1) if secs else None,
            "slowest": sorted(({"symbol": r["symbol"], "seconds": r["seconds"]} for r in rows), key=lambda x: -x["seconds"])[:5]}


class Runner:
    """One audit at a time, in a background thread; progress is readable while it runs and the result is saved."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state: dict = {"running": False}
        self._stop = threading.Event()

    def cancel(self):
        """Stop after the company being checked now; what's done so far is kept and saved."""
        self._stop.set()

    def status(self) -> dict:
        with self.lock:
            if self.state.get("running") or self.state.get("rows") is not None:
                return self._public()
        try:
            import json
            saved = db.get_setting(KEY)
            return json.loads(saved) if saved else {"running": False}
        except Exception:
            return {"running": False}

    def _public(self) -> dict:
        s = dict(self.state)
        s["summary"] = summarise(s.get("rows") or [])
        return s

    def start(self, symbols: list[str], label: str, check, docs: bool, region: str = "IN") -> dict:
        with self.lock:
            if self.state.get("running"):
                raise RuntimeError("An audit is already running.")
            self.state = {"running": True, "label": label, "docs": docs, "region": region, "total": len(symbols), "done": 0, "rows": [],
                          "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None, "cancelled": False}
            self._stop.clear()
        threading.Thread(target=self._run, args=(symbols, check), daemon=True).start()
        return self.status()

    def _run(self, symbols: list[str], check):
        import json
        for sym in symbols:
            if self._stop.is_set():
                with self.lock:
                    self.state["cancelled"] = True
                break
            try:
                row = check(sym)
            except Exception as e:                # one company failing never stops the run, or leaves it "running"
                row = {"symbol": sym, "name": sym, "seconds": 0, "issues": [_issue("error", "Audit", str(e)[:200] or e.__class__.__name__)]}
            with self.lock:
                self.state["rows"].append(row)
                self.state["done"] += 1
        with self.lock:
            self.state["running"] = False
            self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
            result = self._public()
        try:
            db.set_setting(KEY, json.dumps(result))
        except Exception as e:
            print("could not save the audit:", e)


MARKET = "audit:market"        # settings keys: the switch and list state, the list itself, and results in shards
RETRY_HOURS = 1                # a check a source turned away is tried again no sooner than this
MAX_TRIES = 3                  # an error from an unreachable source is tried this many times in all; "not checked
                               # yet" (a source refusing us) is tried for as long as it takes, at the slow pace below
RETRY_BATCH = 20               # retries go in small batches: this many, then a pause of RETRY_GAP hours...
RETRY_GAP = 1
RETRY_GAP_MAX = 24             # ...doubled (up to a day) each time a whole batch is turned away again
TRANSIENT_AREAS = {"Company page", "Prices", "Audit"}      # errors from a source being unreachable, not from the data
BLOCKING_AREAS = {"Company page", "Audit"}                 # the whole check failed: slow down. Documents alone don't
NEW_DAYS = 30                  # listed (or first seen on the list) within this many days: checked
LIST_EVERY = 86400             # re-read the exchange's list of companies once a day
SHARDS = [*"ABCDEFGHIJKLMNOPQRSTUVWXYZ0", *(f"bse{d}" for d in "0123456789")]
COOL_MAX = 1800                # a source turning every company away: wait up to half an hour between checks


def _shard(sym: str, key: str = MARKET) -> str:
    if sym.startswith("BSE:"):                  # thousands of BSE-only companies: ten shards of their own
        return f"{key}:rows:bse{sym[-1]}"
    c = sym[:1].upper()
    return f"{key}:rows:{c if c.isalpha() else '0'}"


def _transient(row: dict) -> bool:
    """The check failed because a source couldn't be reached (busy, down, blocked), not because the data was wrong."""
    return any(i.get("level") == "pending" or (i.get("level") == "error" and i.get("area") in TRANSIENT_AREAS)
               for i in row.get("issues") or [])


def _blocked(row: dict) -> bool:
    """The whole check was turned away (the company page or the check itself), not just one part such as documents."""
    return any(i.get("level") in ("pending", "error") and i.get("area") in BLOCKING_AREAS for i in row.get("issues") or [])


def _retry_forever(row: dict) -> bool:
    """A source refused us (not checked yet): tried again for as long as it takes, at the batches' pace."""
    return any(i.get("level") == "pending" for i in row.get("issues") or [])


def india_tz():
    """India time: the monthly check runs on the 1st there."""
    from zoneinfo import ZoneInfo
    return ZoneInfo("Asia/Kolkata")


def next_month_start(now: datetime) -> str:
    """The 1st of the month after `now`, as "2026-11-01"."""
    y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return f"{y:04d}-{m:02d}-01"


def _fresh_retry() -> dict:
    return {"next": None, "gap": RETRY_GAP, "left": RETRY_BATCH, "tried": 0, "refused": 0}


class AuditNotLoaded(RuntimeError):
    """The stored audit couldn't be read; nothing is checked or saved until it can be."""


class MarketAudit:
    """Every listed company, checked in the background. The exchange's list is read once a day; a company that listed
    (or first showed up on the list) in the last NEW_DAYS days is checked once, a delisted company is dropped, and a
    check a source turned away is tried again in small hourly batches (slower while the source keeps refusing).
    A full check of every company runs on the 1st of each month (India time), or when started by hand; a reset
    clears every result and starts one from nothing. Each result is saved as it finishes, so a restart carries on
    where it stopped, and the month's run is marked in the database so a restart doesn't repeat it. Gives way while
    a hand-started audit runs, and waits while the price feed is offline (`ready_fn`): a company checked then would
    only come back "not checked yet"."""

    def __init__(self, list_fn, check_fn, busy_fn=lambda: False, pause: float = 3.0, key: str = MARKET, ready_fn=lambda: True):
        self.list_fn, self.check_fn, self.busy_fn, self.pause, self.key = list_fn, check_fn, busy_fn, pause, key
        self.ready_fn = ready_fn
        self.lock = threading.Lock()
        self.loaded = False
        self.state: dict = {"enabled": False, "list_at": None, "list_tried_at": None, "list_error": None}
        self.listing: dict[str, dict] = {}
        self.rows: dict[str, dict] = {}
        self.current: str | None = None
        self.secs: list[float] = []
        self.cool = 0.0                # extra seconds between checks while a source keeps turning us away

    # storage
    def _load(self):
        if self.loaded:
            return
        import json
        # read everything first and only then take it: a read that fails (the database busy right after a restart)
        # must not leave an empty audit that then saves over the stored results and starts again from nothing
        try:
            state = json.loads(db.get_setting(self.key) or "{}")
            listing = json.loads(db.get_setting(f"{self.key}:list") or "{}")
            rows: dict = {}
            for c in SHARDS:
                rows.update(json.loads(db.get_setting(f"{self.key}:rows:{c}") or "{}"))
        except Exception as e:
            print("could not load the market audit (will try again):", e)
            raise AuditNotLoaded(str(e)[:200]) from None
        us = self.key.endswith("-us")
        for row in rows.values():                   # older checks, read with today's rules
            row["issues"] = restate_row(row, us)
        self.state.update(state)
        self.listing, self.rows = listing, rows
        self.loaded = True

    def _save(self, *what: str):
        import json
        try:
            for w in what:
                if w == "state":
                    db.set_setting(self.key, json.dumps(self.state))
                elif w == "list":
                    db.set_setting(f"{self.key}:list", json.dumps(self.listing))
                else:                                   # a symbol: save its shard
                    key = _shard(w, self.key)
                    db.set_setting(key, json.dumps({s: r for s, r in self.rows.items() if _shard(s, self.key) == key}))
        except Exception as e:
            print("could not save the market audit:", e)

    # control
    def _begin_full(self, everything: bool = True, pending: bool = False):
        """Start a full check (the lock held)."""
        self.state.update(full_since=datetime.now(timezone.utc).isoformat(), full_done=None, full_all=everything,
                          full_pending=pending)
        self._save("state")

    def start_full(self, everything: bool = True, pending: bool = False):
        """Check listed companies once, then go back to new listings: every one of them again (results stay until
        each is replaced), with everything=False only those never checked, or with pending=True only those a source
        turned away last time (an exchange refusing the documents step), however many times they were tried."""
        with self.lock:
            self._load()
            self._begin_full(everything, pending)

    def reset(self):
        """Clear every stored result and start a full check from nothing, switched on. The list stays (the caller
        re-reads it); the monthly marker stays, so this doesn't move the next monthly check."""
        import json
        with self.lock:
            self._load()
            self.rows.clear()
            self.secs, self.cool = [], 0.0
            self.state.update(enabled=True, reset_at=datetime.now(timezone.utc).isoformat(), retry=_fresh_retry())
            self._begin_full(everything=True)
            for c in SHARDS:
                try:
                    db.set_setting(f"{self.key}:rows:{c}", json.dumps({}))
                except Exception as e:
                    print("could not clear the market audit:", e)

    def full_once(self):
        """The first time this runs: every company not checked yet, once, so the whole market starts out checked.
        Companies already checked keep their results and aren't repeated."""
        with self.lock:
            self._load()
            started = self.state.get("full_since") or self.state.get("full_done")
        if not started:
            self.start_full(everything=False)

    def set_monthly(self, on: bool):
        with self.lock:
            self._load()
            self.state["monthly"] = bool(on)
            self._save("state")

    def monthly(self, now: datetime | None = None) -> bool:
        """On the 1st of each month (India time), start a full check of every company, once: the month it ran is
        saved, so a restart that day doesn't start it again. The very first time it only marks this month, so a
        deploy mid-month doesn't start one straight away. True when it started one."""
        month = (now or datetime.now(india_tz())).strftime("%Y-%m")
        with self.lock:
            self._load()
            if not self.state.get("monthly", True):
                return False
            last = self.state.get("monthly_run")
            if last and last >= month:
                return False
            self.state["monthly_run"] = month
            if not last:
                self._save("state")
                return False
            self._begin_full(everything=True)
            return True

    def _full_left(self) -> list[str]:
        since = self.state.get("full_since")
        if not since:
            return []
        if self.state.get("full_pending"):
            return sorted(s for s in self.listing if _transient(self.rows.get(s) or {}) and (self.rows[s].get("at") or "") < since)
        if not self.state.get("full_all", True):
            return sorted(s for s in self.listing if not (self.rows.get(s) or {}).get("at"))
        return sorted(s for s in self.listing if ((self.rows.get(s) or {}).get("at") or "") < since)

    def set_enabled(self, on: bool):
        with self.lock:
            self._load()
            self.state["enabled"] = bool(on)
            self._save("state")

    def refresh_list(self, force: bool = False) -> bool:
        """Read the exchange's list when it is a day old (or now, when forced). Keeps the last good list on failure."""
        with self.lock:
            self._load()
            last = self.state.get("list_tried_at")
            if not force and last and time.time() - datetime.fromisoformat(last).timestamp() < LIST_EVERY:
                return False
            self.state["list_tried_at"] = datetime.now(timezone.utc).isoformat()
        try:
            got = self.list_fn()
        except Exception as e:
            with self.lock:
                self.state["list_error"] = str(e)[:200]
                self._save("state")
            return False
        today = datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            first = not self.listing         # the first read: nothing in it is new, it's just the start
            fresh = {c["symbol"]: {"name": c.get("name") or c["symbol"], "listed": c.get("listed"),
                                   "seen": (self.listing.get(c["symbol"]) or {}).get("seen") or (None if first or c.get("old") else today)}
                     for c in got}
            gone = [s for s in self.rows if s not in fresh]
            for s in gone:
                self.rows.pop(s)
            self.listing = fresh
            self.state.update(list_at=self.state["list_tried_at"], list_error=None)
            self._save("state", "list", *{_shard(s, self.key): s for s in gone}.values())
        return True

    def _is_new(self, sym: str, today) -> bool:
        info = self.listing.get(sym) or {}
        d = info.get("listed") or info.get("seen")
        try:
            return d is not None and (today - datetime.fromisoformat(d).date()).days <= NEW_DAYS
        except ValueError:
            return False

    def _retry(self) -> dict:
        r = self.state.get("retry")
        if not isinstance(r, dict):
            r = self.state["retry"] = _fresh_retry()
        return r

    def waiting(self, now: datetime | None = None) -> list[str]:
        """Companies a source turned away that are due another try, oldest first: at least RETRY_HOURS since the
        last, and (an error rather than a refusal) fewer than MAX_TRIES tries so far."""
        cut = ((now or datetime.now(timezone.utc)) - timedelta(hours=RETRY_HOURS)).isoformat()
        out = []
        for sym in self.listing:
            row = self.rows.get(sym) or {}
            at = row.get("at")
            if at and at < cut and _transient(row) and (_retry_forever(row) or (row.get("tries") or 1) < MAX_TRIES):
                out.append((at, sym))
        return [s for _, s in sorted(out)]

    def _retries_now(self, now: datetime) -> list[str]:
        """The retries allowed right now: the rest of this batch, or none while the batches are resting."""
        r = self._retry()
        if r.get("next") and now.isoformat() < r["next"]:
            return []
        return self.waiting(now)[:max(0, int(r.get("left") or 0))]

    def queue(self) -> list[str]:
        """Companies due a check, in order: new listings not yet checked (newest first), this batch of checks to
        retry, then (during a full check) every company not yet checked since it started."""
        now = datetime.now(timezone.utc)
        today = now.date()
        new = []
        for sym, info in self.listing.items():
            if not (self.rows.get(sym) or {}).get("at") and self._is_new(sym, today):
                new.append((info.get("listed") or info.get("seen") or "", sym))
        first = [s for _, s in sorted(new, reverse=True)] + self._retries_now(now)
        taken = set(first)
        return first + [s for s in self._full_left() if s not in taken]

    def _store(self, sym: str, row: dict, retried: bool = False):
        """Save one finished check (the lock held). A retry counts against its batch; when the batch is through, the
        retries rest an hour, or twice as long as last time when the whole batch was turned away again."""
        row["at"] = datetime.now(timezone.utc).isoformat()
        info = self.listing.get(sym) or {}
        if info.get("name") and row.get("name") in (None, "", sym, sym.split(":")[-1]):
            row["name"] = info["name"]          # the check failed before the company's name was read
        prev = self.rows.get(sym) or {}
        row["tries"] = (prev.get("tries") or 1) + 1 if _transient(prev) and _transient(row) else 1
        # the whole check turned away: slow down (doubling, up to half an hour) until the source answers again. One
        # part refused (documents from an exchange that turns this server away) waits for the hourly retries instead
        self.cool = min(COOL_MAX, max(60.0, self.cool * 2)) if _blocked(row) else 0.0
        if sym in self.listing:
            self.rows[sym] = row
            self.secs = (self.secs + [row.get("seconds") or 0])[-50:]
            self._save(sym)
        if not retried:
            return
        r = self._retry()
        r["left"] = int(r.get("left") or RETRY_BATCH) - 1
        r["tried"] = int(r.get("tried") or 0) + 1
        r["refused"] = int(r.get("refused") or 0) + (1 if _transient(row) else 0)
        if r["left"] <= 0 or not self.waiting():
            gap = r.get("gap") or RETRY_GAP
            gap = min(RETRY_GAP_MAX, gap * 2) if r["refused"] >= r["tried"] else RETRY_GAP
            nxt = datetime.now(timezone.utc) + timedelta(hours=gap)
            self.state["retry"] = {**_fresh_retry(), "gap": gap, "next": nxt.isoformat(),
                                   "last": {"tried": r["tried"], "refused": r["refused"]}}
        self._save("state")

    # work
    def step(self) -> str | None:
        """Check one due company; returns its symbol, or None when there's nothing to do right now."""
        try:
            self.monthly()
        except Exception as e:
            print("market audit: couldn't start the monthly check:", e)
        with self.lock:
            self._load()
            if not self.state.get("enabled"):
                return None
        if self.busy_fn() or not self.ready_fn():
            return None
        self.refresh_list()
        with self.lock:
            now = datetime.now(timezone.utc)
            due = self.queue()
            retries = set(self._retries_now(now))
            if self.state.get("full_since") and not self._full_left():     # the full check is through
                self.state.update(full_since=None, full_done=now.isoformat())
                self._save("state")
            if not due:
                return None
            sym = self.current = due[0]
        try:
            row = self.check_fn(sym)
        except Exception as e:                # stored as a finding and retried at the batches' pace: never the same
            row = {"symbol": sym, "name": sym, "seconds": 0,      # company every minute, holding up the rest
                   "issues": [_issue("error", "Audit", _plain(e)[:200] or e.__class__.__name__)]}
        finally:
            with self.lock:
                self.current = None
        with self.lock:
            self._store(sym, row, retried=sym in retries)
        return sym

    def recheck(self, sym: str) -> dict:
        """Check one listed company again now (the panel's "Re-check" link); the new result replaces the old."""
        with self.lock:
            self._load()
            if sym not in self.listing:
                raise KeyError(sym)
        try:
            row = self.check_fn(sym)
        except Exception as e:                # one company failing is a finding, never a broken page
            row = {"symbol": sym, "name": sym, "seconds": 0, "issues": [_issue("error", "Audit", str(e)[:200] or e.__class__.__name__)]}
        with self.lock:
            self._store(sym, row)
            return self.rows.get(sym) or row

    def loop(self):
        while True:                           # until the stored audit can be read (the database may be busy at boot)
            try:
                self.full_once()
                break
            except Exception as e:
                print("market audit: couldn't start the first full check:", e)
                time.sleep(60)
        while True:
            try:
                did = self.step()
            except Exception as e:
                print("market audit step failed:", e)
                did = None
            time.sleep(self.pause + self.cool if did else 60)

    def checked_since(self, since_iso: str) -> list[dict]:
        """Every company checked since a time, with or without problems."""
        with self.lock:
            self._load()
            return [r for r in self.rows.values() if (r.get("at") or "") >= since_iso]

    def status(self) -> dict:
        """Everything the panel shows. `paused` says why nothing is being checked: "off" (switched off), "busy" (an
        audit started by hand is running), "offline" (the price feed is offline until the next data login), "cooling"
        (a source is turning every company away, so it waits between checks), or None (running). The rate is
        companies checked in the last hour; the time left follows from it."""
        busy = bool(self.busy_fn())
        offline = not self.ready_fn()
        with self.lock:
            try:
                self._load()
            except AuditNotLoaded as e:
                return {"loading": True, "error": f"The stored results couldn't be read yet ({e}); trying again.",
                        "enabled": self.state.get("enabled"), "paused": "loading"}
            now = datetime.now(timezone.utc)
            due = self.queue()
            today = now.date()
            rows = list(self.rows.values())
            new = sorted(({"symbol": s, "name": i.get("name"), "listed": i.get("listed"),
                           "checked": bool((self.rows.get(s) or {}).get("at"))}
                          for s, i in self.listing.items() if self._is_new(s, today)), key=lambda x: x["listed"] or "", reverse=True)
            avg = (sum(self.secs) / len(self.secs) + self.pause) if self.secs else None
            hour_ago = (now - timedelta(hours=1)).isoformat()
            rate = sum(1 for r in rows if (r.get("at") or "") >= hour_ago)
            left = len(self._full_left())
            eta = round(len(due) / rate, 1) if rate else round(len(due) * avg / 3600, 1) if avg else None
            enabled = bool(self.state.get("enabled"))
            r = self._retry()
            waiting = sum(1 for x in rows if _transient(x))
            on = bool(self.state.get("monthly", True))
            return {**{k: self.state.get(k) for k in ("enabled", "list_at", "list_tried_at", "list_error", "reset_at")},
                    "paused": "off" if not enabled else "busy" if busy else "offline" if offline else "cooling" if self.cool else None,
                    "cool_minutes": round(self.cool / 60) if self.cool else 0,
                    "full": {"running": bool(self.state.get("full_since")), "since": self.state.get("full_since"),
                             "done_at": self.state.get("full_done"), "left": left,
                             "checked": len(self.listing) - left if self.state.get("full_since") else None,
                             "everything": bool(self.state.get("full_all", True)), "pending_only": bool(self.state.get("full_pending"))},
                    "monthly": {"on": on, "last": self.state.get("monthly_run"),
                                "next": next_month_start(datetime.now(india_tz())) if on else None},
                    "retry": {"waiting": waiting, "due": len(self.waiting(now)), "next": r.get("next"),
                              "gap_hours": r.get("gap") or RETRY_GAP, "batch": RETRY_BATCH, "last": r.get("last")},
                    "pending": waiting,
                    "listed": len(self.listing), "checked": len(self.rows), "due": len(due), "current": self.current,
                    "rate_per_hour": rate, "eta_hours": eta, "new_listings": new[:30],
                    "summary": summarise(rows), "rows": [x for x in rows if x.get("issues")]}
