"""The data audit: every company in a set run through the deep dive's numbers, checks and documents on the live server,
with each number compared against its source and every gap written down. Run from the admin page; nothing here uses
AI, so a full run costs no AI allowance. The aim is that nothing StratLab shows needs checking anywhere else."""
import threading
import re
import time
from datetime import datetime, timedelta, timezone

from . import db, sector_members, universes

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
                         r"service unavailable|bad gateway|gateway time|timed? ?out|connection (?:reset|aborted)", re.I)


def _issue(level: str, area: str, detail: str) -> dict:
    return {"level": level, "area": area, "detail": detail}


def _later(area: str, why: str) -> dict:
    """A check to run again later: "Not checked yet: the exchange feed refused the request (403)."."""
    why = re.sub(r"\s*Try again[^.]*\.?\s*$", "", str(why or "")).strip().rstrip(".") or "a source didn't answer"
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


FINANCIAL = {"lender", "insurer", "holding"}
NO_REVENUE = "No revenue reported in any year: a company without sales yet"


def short_history(n: int) -> str:
    return f"Only {n} year{'s' if n != 1 else ''} of annual results so far: listed, demerged or first reporting recently"


def check_numbers(p: dict, nums: dict, snap: dict, group: str | None = None) -> list[dict]:
    out = []
    years = nums.get("years") or []
    if not years:
        out.append(_issue("gap", "Numbers", "Only 0 years of annual results"))
    elif len(years) < 5:              # the source shows every year there is: fewer is a young company, not missing data
        out.append(_issue("fact", "Numbers", short_history(len(years))))
    no_sales = [y["year"] for y in years if y.get("sales") is None]
    missing = [y["year"] for y in years if y.get("sales") is None or y.get("profit") is None]
    first = next((i for i, y in enumerate(years) if y.get("sales") is not None), len(years))
    before = [y["year"] for y in years[:first]]                   # years before its first sales, with a profit (loss) filed
    if years and len(no_sales) == len(years) and all(y.get("profit") is not None for y in years):
        out.append(_issue("fact", "Numbers", NO_REVENUE))         # a company with no sales yet (in development, a shell)
    elif missing and missing == before and all(y.get("profit") is not None for y in years[:first]):
        out.append(_issue("fact", "Numbers", f"No revenue before {years[first]['year']}: sales began then"))
    elif missing:
        out.append(_issue("gap", "Numbers", f"Revenue or profit missing for {', '.join(missing[:4])}"))
    if not nums.get("bank") and group not in FINANCIAL:
        # a margin above 100% means costs came out negative (provisions written back): the margin is the company
        # page's own figure, shown as filed, so it is worth a look but isn't our reading going wrong
        odd = [y["year"] for y in years if y.get("opm") is not None and y["opm"] > 100]
        if odd:
            src = "The filings show" if p.get("region") == "US" else "The company page shows"
            out.append(_issue("gap", "Numbers", f"{src} an operating margin above 100% in {', '.join(odd[:4])} (costs written back)"))
        if len(years) >= 3 and all(y.get("capex") is None for y in years[-3:]):
            out.append(_issue("gap", "Capex", "No capex estimate for the last three years"))
    ttm = _last_ttm(p.get("pl"), "Net Profit")
    if snap.get("pe") and snap.get("market_cap_cr") and ttm and ttm > 0:
        ours = snap["market_cap_cr"] / ttm
        off = _off(ours, snap["pe"])
        explained = any("P/E is based on" in n for n in nums.get("notes") or [])
        if off is not None and off > PE_TOLERANCE and not explained:
            out.append(_issue("mismatch", "Valuation", f"P/E {snap['pe']:.1f} on the company page, {ours:.1f} from market cap ÷ trailing profit"))
    ttm_sales = _last_ttm(p.get("pl"), "Sales", "Revenue")
    q = [x.get("sales") for x in (nums.get("quarters") or [])[-4:]]
    if ttm_sales and len(q) == 4 and all(v is not None for v in q):
        off = _off(sum(q), ttm_sales)
        if off is not None and off > TTM_TOLERANCE and abs(sum(q) - ttm_sales) > TTM_ROUNDING:
            unit = ("$m", "") if p.get("region") == "US" else ("", " cr")
            out.append(_issue("mismatch", "Numbers", f"Trailing revenue {unit[0]}{ttm_sales:,.0f}{unit[1]} vs last four quarters {unit[0]}{sum(q):,.0f}{unit[1]}"))
    return out


NO_PRICES = {    # why there's no trend: the facts first, then a source to try again
    "new": ("fact", "Listed recently: fewer than 30 trading days of prices, so no trend or stage yet"),
    "untraded": ("fact", "Not trading now (suspended, or not on the exchange's trading list), so no daily prices"),
    "stale": ("fact", "No trades for over a month (suspended or illiquid), so no current trend or stage"),
}


def _near(ours: float, other: float) -> bool:
    off = _off(ours, other)
    return off is None or off <= PRICE_TOLERANCE or abs(ours - other) <= PRICE_TICK


def check_prices(snap: dict, trend: dict | None, exchange, why: str | None = None) -> list[dict]:
    """Our last daily close against the exchange's quote and the company page. `exchange` is the quote's last price,
    or (last price, previous close): a thinly traded stock's close can be a day older than its last trade, or BSE's
    closing price (an average of the last half hour) rather than the last trade, so either agreeing is a match.
    `why` says why there's no trend when there isn't one ("new", "untraded", "stale" or "error")."""
    out = []
    if not trend:
        if why == "error":
            out.append(_later("Prices", "daily prices couldn't be read"))
        else:
            level, text = NO_PRICES.get(why or "", ("gap", "No daily prices, so no trend or stage"))
            out.append(_issue(level, "Prices", text))
    ours = trend.get("price") if trend else None
    quote = [x for x in (exchange if isinstance(exchange, (list, tuple)) else [exchange]) if x]
    if ours is not None and quote and not any(_near(ours, q) for q in quote):
        out.append(_issue("mismatch", "Prices", f"Last close {ours:,.2f} vs {quote[0]:,.2f} on the exchange's live quote"))
    elif ours is not None and snap.get("price") and not _near(ours, snap["price"]):
        out.append(_issue("mismatch", "Prices", f"Last close {ours:,.2f} vs {snap['price']:,.2f} on the company page"))
    return out


HISTORY_CHECKS = ("Sales growth", "Profit growth", "Latest quarter", "Operating margin holding up", "Profit turning into cash",
                  "Free cash flow")


def _explained(label: str, years: list[dict], quarters: list[dict]) -> bool:
    """A check that couldn't be judged because of a fact about the company, not a missing number: too few years or
    quarters of results to measure growth over, losses to grow from or turn into cash, no insider trades filed, or
    too short a price history for a stage."""
    if label.startswith(("Insider", "Promoter and insider")):        # "None": no trades filed is an answer
        return True
    if label.startswith("Price in Stage"):
        return True                               # the stage needs 170 trading days of prices: a young listing has none yet
    last3, last4 = years[-3:], years[-4:]
    if label.startswith(("Sales growth", "Operating margin holding up")):
        return len(years) < 4
    if label.startswith("Profit growth"):
        return len(years) < 4 or any((y.get("profit") or 0) <= 0 for y in last4[:1] + last4[-1:])
    if label.startswith("Latest quarter"):
        return len(quarters) < 5
    if label.startswith(("Profit turning into cash", "Free cash flow")):
        return len(years) < 3 or sum(y.get("profit") or 0 for y in last3) <= 0
    return False


def check_view(view: dict, meets: int | None = None) -> list[dict]:
    """Classification, valuation, checklist and documents, from the same view a user sees. US companies are checked
    for their annual and quarterly reports; Indian ones for presentations and call transcripts. `meets`: how many
    analyst or investor meetings and calls the company told the exchange about in the period (None: unknown)."""
    out = []
    cl = view.get("checklist") or {}
    ind = cl.get("industry") or {}
    if not ind.get("path"):
        out.append(_issue("gap", "Industry", f"No industry classification; treated as {ind.get('label') or 'a general business'}"))
    v = view.get("valuation") or {}
    if v.get("value") is None and "There's no" not in (v.get("why") or ""):      # a loss or negative net worth is said
        out.append(_issue("gap", "Valuation", f"No {v.get('short') or 'valuation'} figure"))
    nums = view.get("numbers") or {}
    years, quarters = nums.get("years") or [], nums.get("quarters") or []
    na = [c["label"] for c in cl.get("checks", []) if c.get("state") == "na"]
    unexplained = [x for x in na if not _explained(x, years, quarters)]
    if len(unexplained) >= 3:
        out.append(_issue("gap", "Checklist", f"{len(unexplained)} checks couldn't be judged: {', '.join(unexplained[:5])}"))
    elif len(na) >= 3:
        out.append(_issue("fact", "Checklist", f"{len(na)} checks need more history than the company has yet: {', '.join(na[:5])}"))
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
            out.append(_issue("gap", "Documents", "No annual report (10-K, 20-F or 40-F) filed in the last two years"))
        elif "quarterly_report" not in kinds and not foreign:
            out.append(_issue("gap", "Documents", "No quarterly report (10-Q) filed in the last two years"))
    else:
        kinds = [d["kind"] for d in view.get("documents") or []]
        if "presentation" not in kinds and "transcript" not in kinds and meets == 0:
            out.append(_issue("fact", "Documents", NO_MEETS))         # many small companies hold no calls at all
        else:
            if "presentation" not in kinds:
                out.append(_issue("gap", "Documents", "No investor presentation filed in the last two years"))
            if "transcript" not in kinds:
                out.append(_issue("gap", "Documents", "No call transcript filed in the last two years"))
    return out


STOPPED_FILING = "No annual or quarterly report filed in the last two years: the company has stopped filing with the SEC"
NO_MEETS = ("Held no earnings calls or analyst meetings in the last two years (none told to the exchange), "
            "so there's no presentation or call transcript to read")


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
               "not US dollars")
# SEC industry codes of securities with no operating business to check: blank-check companies (SPACs), and funds and
# trusts that hold investments or commodities
NOT_OPERATING = {"6770": "a blank-check company (SPAC) with no business of its own yet",
                 "6722": "an investment fund", "6726": "an investment fund or trust", "6221": "a commodity fund or trust"}


def restate(issue: dict, us: bool = False) -> dict | None:
    """A stored finding read with today's rules, so a company checked under older rules isn't re-run just to drop a
    false alarm: None when today's rules wouldn't report it."""
    level, area, detail = issue.get("level"), issue.get("area"), str(issue.get("detail") or "")
    num = lambda x: float(x.replace(",", ""))   # noqa: E731
    if level == "mismatch" and detail.startswith("Operating margin above 100% in "):
        src = "The filings show" if us else "The company page shows"
        return _issue("gap", area, f"{src} an operating margin above 100% in {detail[31:]} (costs written back)")
    m = re.match(r"Trailing revenue \$?m?([\d,.]+)(?: cr)? vs last four quarters \$?m?([\d,.]+)", detail)
    if level == "mismatch" and m:
        a, b = num(m[1]), num(m[2])
        if abs(a - b) <= TTM_ROUNDING:
            return None
        return _issue(level, area, f"Trailing revenue $m{a:,.0f} vs last four quarters $m{b:,.0f}") if us else issue
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
    if level == "gap" and area == "Documents" and detail.startswith("No annual report (10-K)"):
        return _issue(level, area, "No annual report (10-K, 20-F or 40-F) filed in the last two years")
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
        view = view_fn(sym, base)
        name = view.get("name") or sym
        group = ((view.get("checklist") or {}).get("industry") or {}).get("group")
        issues += check_numbers(p, view["numbers"], view.get("snapshot") or {}, group)
        ex = None
        if exchange_price:
            try:
                ex = exchange_price(sym)
            except Skipped:
                ex = None
            except Exception as e:
                why = str(e)[:120] or e.__class__.__name__
                issues.append(_later("Prices", f"the exchange's quote couldn't be read ({why})") if RETRY_LATER.search(why)
                              else _issue("error", "Prices", f"Exchange price unavailable: {why}"))
        issues += check_prices(view.get("snapshot") or {}, base.get("trend"), ex, base.get("trend_why"))
        issues += check_view(view, base.get("meets"))
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
RETRY_HOURS = 6                # a check that failed because a source was down is tried again after this long
MAX_TRIES = 3                  # ...this many times in all, then it is left as it is
TRANSIENT_AREAS = {"Company page", "Prices", "Audit"}      # errors from a source being unreachable, not from the data
NEW_DAYS = 30                  # listed (or first seen on the list) within this many days: checked
LIST_EVERY = 86400             # re-read the exchange's list of companies once a day


def _shard(sym: str, key: str = MARKET) -> str:
    if sym.startswith("BSE:"):                  # thousands of BSE-only companies: ten shards of their own
        return f"{key}:rows:bse{sym[-1]}"
    c = sym[:1].upper()
    return f"{key}:rows:{c if c.isalpha() else '0'}"


def _transient(row: dict) -> bool:
    """The check failed because a source couldn't be reached (busy, down, blocked), not because the data was wrong."""
    return any(i.get("level") == "pending" or (i.get("level") == "error" and i.get("area") in TRANSIENT_AREAS)
               for i in row.get("issues") or [])


COOL_MAX = 1800                # a source turning every company away: wait up to half an hour between checks


class MarketAudit:
    """New listings, checked in the background as they appear. The exchange's list is read once a day; a company that
    listed (or first showed up on the list) in the last NEW_DAYS days is checked once, a delisted company is dropped,
    and a check that failed only because a source was down is tried again. The thousands of companies already listed
    are not re-run: going through a whole market takes more than a day and its storage. Each result is saved as it
    finishes, so a restart carries on where it stopped. Gives way while a hand-started audit runs."""

    def __init__(self, list_fn, check_fn, busy_fn=lambda: False, pause: float = 3.0, key: str = MARKET):
        self.list_fn, self.check_fn, self.busy_fn, self.pause, self.key = list_fn, check_fn, busy_fn, pause, key
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
        try:
            self.state.update(json.loads(db.get_setting(self.key) or "{}"))
            self.listing = json.loads(db.get_setting(f"{self.key}:list") or "{}")
            for c in [*"ABCDEFGHIJKLMNOPQRSTUVWXYZ0", *(f"bse{d}" for d in "0123456789")]:
                self.rows.update(json.loads(db.get_setting(f"{self.key}:rows:{c}") or "{}"))
            us = self.key.endswith("-us")
            for row in self.rows.values():          # older checks, read with today's rules
                row["issues"] = restate_row(row, us)
        except Exception as e:
            print("could not load the market audit:", e)
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
    def start_full(self, everything: bool = True, pending: bool = False):
        """Check listed companies once, then go back to new listings: every one of them again (results stay until
        each is replaced), with everything=False only those never checked, or with pending=True only those a source
        turned away last time (an exchange refusing the documents step), however many times they were tried."""
        with self.lock:
            self._load()
            self.state.update(full_since=datetime.now(timezone.utc).isoformat(), full_done=None, full_all=everything,
                              full_pending=pending)
            self._save("state")

    def full_once(self):
        """The first time this runs: every company not checked yet, once, so the whole market starts out checked.
        Companies already checked keep their results and aren't repeated."""
        with self.lock:
            self._load()
            started = self.state.get("full_since") or self.state.get("full_done")
        if not started:
            self.start_full(everything=False)

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

    def queue(self) -> list[str]:
        """Companies due a check, in order: new listings not yet checked (newest first), failed checks to retry, then
        (during a full check) every company not yet checked since it started."""
        now = datetime.now(timezone.utc)
        today = now.date()
        retry_cut = (now - timedelta(hours=RETRY_HOURS)).isoformat()
        new, retry = [], []
        for sym, info in self.listing.items():
            row = self.rows.get(sym) or {}
            at = row.get("at")
            if not at:
                if self._is_new(sym, today):
                    new.append((info.get("listed") or info.get("seen") or "", sym))
            elif _transient(row) and (row.get("tries") or 1) < MAX_TRIES and at < retry_cut:
                retry.append((at, sym))           # a source was down or busy: try again later
        first = [s for _, s in sorted(new, reverse=True)] + [s for _, s in sorted(retry)]
        taken = set(first)
        return first + [s for s in self._full_left() if s not in taken]

    # work
    def step(self) -> str | None:
        """Check one due company; returns its symbol, or None when there's nothing to do right now."""
        with self.lock:
            self._load()
            if not self.state.get("enabled"):
                return None
        if self.busy_fn():
            return None
        self.refresh_list()
        with self.lock:
            due = self.queue()
            if self.state.get("full_since") and not self._full_left():     # the full check is through
                self.state.update(full_since=None, full_done=datetime.now(timezone.utc).isoformat())
                self._save("state")
            if not due:
                return None
            sym = self.current = due[0]
        try:
            row = self.check_fn(sym)
        finally:
            with self.lock:
                self.current = None
        row["at"] = datetime.now(timezone.utc).isoformat()
        with self.lock:
            info = self.listing.get(sym) or {}
            if info.get("name") and row.get("name") in (None, "", sym, sym.split(":")[-1]):
                row["name"] = info["name"]          # the check failed before the company's name was read
            prev = self.rows.get(sym) or {}
            row["tries"] = (prev.get("tries") or 1) + 1 if _transient(prev) and _transient(row) else 1
            # a source turning us away: slow down (doubling, up to half an hour) until it answers again
            self.cool = min(COOL_MAX, max(60.0, self.cool * 2)) if _transient(row) else 0.0
            if sym in self.listing:
                self.rows[sym] = row
                self.secs = (self.secs + [row.get("seconds") or 0])[-50:]
                self._save(sym)
        return sym

    def loop(self):
        try:
            self.full_once()
        except Exception as e:
            print("market audit: couldn't start the first full check:", e)
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
        with self.lock:
            self._load()
            due = self.queue()
            today = datetime.now(timezone.utc).date()
            rows = list(self.rows.values())
            new = sorted(({"symbol": s, "name": i.get("name"), "listed": i.get("listed"),
                           "checked": bool((self.rows.get(s) or {}).get("at"))}
                          for s, i in self.listing.items() if self._is_new(s, today)), key=lambda x: x["listed"] or "", reverse=True)
            avg = (sum(self.secs) / len(self.secs) + self.pause) if self.secs else None
            left = len(self._full_left())
            return {**{k: self.state.get(k) for k in ("enabled", "list_at", "list_tried_at", "list_error")},
                    "full": {"running": bool(self.state.get("full_since")), "since": self.state.get("full_since"),
                             "done_at": self.state.get("full_done"), "left": left,
                             "checked": len(self.listing) - left if self.state.get("full_since") else None,
                             "everything": bool(self.state.get("full_all", True)), "pending_only": bool(self.state.get("full_pending"))},
                    "pending": sum(1 for r in rows if _transient(r)),
                    "listed": len(self.listing), "checked": len(self.rows), "due": len(due), "current": self.current,
                    "eta_hours": round(len(due) * avg / 3600, 1) if avg else None, "new_listings": new[:30],
                    "summary": summarise(rows), "rows": [r for r in rows if r.get("issues")]}
