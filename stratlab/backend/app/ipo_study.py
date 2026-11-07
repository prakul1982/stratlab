"""The IPO study: how India's IPOs of the last two years have done, from the stored IPO history (ipo_history.py) and daily closes.

Per issue: the listing-day change (open and close against the issue price), the change to the latest close, the NIFTY 50's and the
NIFTY Smallcap 250's change over the same days, the retail subscription and the share of retail demand that could be filled (and the
retail allotment odds where the exchange gave the applications). Aggregates by listing year, issue size, sector and retail
subscription, for the main board and SME issues separately; the share of issues below their issue price now; the money raised, fresh
issue against offer for sale.

    python -m app.ipo_study --out DIR [--rows rows.json] [--today YYYY-MM-DD] [--no-prices] [--drafts] [--charts]

writes DIR/ipo-study.json and DIR/ipo-study.md (and with --drafts the three drafts, with --charts their PNG charts when matplotlib is
installed, else the chart specs as JSON). Every figure in the drafts is taken from the JSON, and each draft ends with the JSON path of
every number it uses. Facts and arithmetic only: no view on any issue."""
import argparse
import json
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SITE = "https://stratlab.studio"
BENCH = (("nifty50", "NIFTY 50", "^NSEI"), ("smallcap250", "NIFTY Smallcap 250", "NIFTYSMLCAP250.NS"))
SIZE_BUCKETS = (("Under ₹100 cr", 0, 100), ("₹100 to 500 cr", 100, 500), ("₹500 to 1,000 cr", 500, 1000), ("₹1,000 to 5,000 cr", 1000, 5000),
                ("Over ₹5,000 cr", 5000, float("inf")))
SME_SIZE_BUCKETS = (("Under ₹25 cr", 0, 25), ("₹25 to 50 cr", 25, 50), ("₹50 to 100 cr", 50, 100), ("Over ₹100 cr", 100, float("inf")))
RETAIL_BUCKETS = (("Retail under 5 times", 0, 5), ("Retail 5 to 50 times", 5, 50), ("Retail over 50 times", 50, float("inf")))
SEGMENTS = (("mainboard", "Main board"), ("sme", "SME"))
TOP_SECTORS = 8
LISTED_GAP_DAYS = 5               # a first candle more than this many days after the listing day is not the listing day's


def _pct(a: float, b: float) -> float:
    return round((a / b - 1) * 100, 2)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def before(closes: dict[str, float], day: str) -> str | None:
    """The last day in `closes` before `day`."""
    got = [d for d in closes if d < day]
    return max(got) if got else None


def on_or_before(closes: dict[str, float], day: str) -> str | None:
    got = [d for d in closes if d <= day]
    return max(got) if got else None


def retail_row(sub: dict | None) -> dict | None:
    """The retail (individual investors') line of an issue's final bids."""
    for r in (sub or {}).get("rows") or []:
        label = str(r.get("label") or "")
        if re.match(r"(retail|individual)", label, re.IGNORECASE) and not re.search(r"non.?institutional", label, re.IGNORECASE):
            return r
    return None


def money(row: dict, issue: float | None) -> dict:
    """The issue's size in ₹ crore and its two parts (fresh issue and offer for sale), at the issue price where given in shares."""
    from . import ipo as I
    sz = I.sizes({**row, "market": "IN", "price": issue or row.get("price")})
    fresh = row.get("fresh_cr") or (round(row["fresh"] * issue / 1e7, 2) if row.get("fresh") and issue else None)
    ofs = row.get("ofs_cr") or (round(row["ofs"] * issue / 1e7, 2) if row.get("ofs") and issue else None)
    total = sz.get("amount")
    if (fresh or ofs) and not total:
        total = round((fresh or 0) + (ofs or 0), 2)
    # one part known: the other is nil when the issue's own terms (read from its page) don't mention it
    text = str(row.get("issue_text") or "")
    if text and fresh is not None and ofs is None and not re.search(r"offer for sale|\bofs\b", text, re.IGNORECASE):
        ofs = 0.0
    if text and ofs is not None and fresh is None and not re.search(r"fresh", text, re.IGNORECASE):
        fresh = 0.0
    return {"size_cr": total, "fresh_cr": fresh, "ofs_cr": ofs}


RATIOS = (2.0, 3.0, 4.0, 5.0, 10.0, 1.5, 20.0, 25.0, 50.0)


def split_factor(exchange_close, adjusted_close) -> float:
    """What a split or bonus since the listing day turned one listing-day share into: the exchange's listing-day close against the same
    day's close as read today, snapped to a usual ratio (2, 3, 5, 10, 1.5 for a 1:2 bonus...). 1 when the two agree within 25%."""
    if not _num(exchange_close) or not _num(adjusted_close) or not adjusted_close or not exchange_close:
        return 1.0
    r = exchange_close / adjusted_close
    if 0.8 <= r <= 1.25:
        return 1.0
    near = min(RATIOS, key=lambda x: abs(x / r - 1))
    return near if abs(near / r - 1) < 0.08 else round(r, 3)


def issue_figures(row: dict, closes: dict[str, float], bench: dict[str, dict[str, float]], today: date, opens: dict[str, float] | None = None) -> dict:
    """One issue's figures (see the module's note). `closes` {day: close} of the stock (and `opens` {day: open}), `bench` {key: {day: close}}
    of the indices."""
    perf, bp = row.get("perf") or {}, row.get("bse_perf") or {}
    issue = row.get("price") or perf.get("issue_price") or bp.get("issue_price")
    listing = str(row.get("listing") or "")[:10]
    out = {"id": row["id"], "name": row.get("name"), "symbol": row.get("symbol"), "segment": row.get("segment"), "listing": listing,
           "year": listing[:4], "issue_price": issue, "sector": row.get("industry") or None, "listing_open_pct": None,
           "listing_close_pct": None, "last_close": None, "last_day": None, "return_pct": None, "below_issue": None}
    if issue:
        days = sorted(d for d in closes if d >= listing and d <= today.isoformat())
        first = days[0] if days and (date.fromisoformat(days[0]) - date.fromisoformat(listing)).days <= LISTED_GAP_DAYS else None
        # daily prices read today are adjusted for later splits and bonuses, the issue price is not: the exchange's own listing-day
        # close (BSE's table) against the first day's adjusted close gives the factor (Waterways Leisure Tourism: ₹667.35 against
        # ₹66.81 after its 10-for-1 split, so not -89% but the price times ten)
        cand = closes[first] if first else perf.get("day_close")
        factor = split_factor(bp.get("day_close"), cand)
        out["split_factor"] = factor if factor != 1 else None
        if _num(bp.get("day_close")):
            out["listing_close_pct"] = _pct(bp["day_close"], issue)
        elif first:
            out["listing_close_pct"] = _pct(closes[first], issue)
        elif _num(perf.get("day_change_pct")):
            out["listing_close_pct"] = perf["day_change_pct"]
        if first and _num((opens or {}).get(first)):
            out["listing_open_pct"] = _pct(opens[first] * factor, issue)
        elif _num(perf.get("listing_price")):
            out["listing_open_pct"] = _pct(perf["listing_price"] * factor, issue)
        elif _num(perf.get("listing_change_pct")) and factor == 1:
            out["listing_open_pct"] = perf["listing_change_pct"]
        if days:
            out["last_day"], out["last_close"] = days[-1], round(closes[days[-1]] * factor, 2)
        elif _num(perf.get("latest")):
            out["last_day"], out["last_close"] = perf.get("latest_date"), round(perf["latest"] * factor, 2)
        elif _num(bp.get("latest")):
            out["last_close"] = bp["latest"]
        if out["last_close"]:
            out["return_pct"] = _pct(out["last_close"], issue)
            out["below_issue"] = out["last_close"] < issue
        # a price far below the issue price with no exchange close to check it against may be a split: named nowhere until checked
        out["check_split"] = bool(factor == 1 and not _num(bp.get("day_close")) and out["last_close"] and out["last_close"] / issue < 0.3)
    # the index over the same days: from its close before the listing day to its close on the stock's latest day
    for key, _label, _sym in BENCH:
        idx, ret = bench.get(key) or {}, None
        if out["return_pct"] is not None and out["last_day"] and idx:
            a, b = before(idx, listing), on_or_before(idx, out["last_day"])
            if a and b and b > a:
                ret = _pct(idx[b], idx[a])
        out[f"{key}_pct"] = ret
        out[f"vs_{key}_pct"] = round(out["return_pct"] - ret, 2) if ret is not None else None
    rr = retail_row(row.get("sub"))
    out["retail_times"] = rr["times"] if rr and _num(rr.get("times")) and rr["times"] > 0 else None
    out["total_times"] = (row.get("sub") or {}).get("times") if _num((row.get("sub") or {}).get("times")) else None
    out["retail_fill_pct"] = round(min(100.0, rr["offered"] / rr["bid"] * 100), 2) if rr and rr.get("offered") and rr.get("bid") else None
    apps, lot = (rr or {}).get("apps"), row.get("lot")
    out["retail_odds_pct"] = round(min(100.0, rr["offered"] / lot / apps * 100), 2) if rr and apps and lot and rr.get("offered") else None
    out.update(money(row, issue))
    return out


MIN_BASE = 10                   # a median or a share of fewer issues than this is not given (the SME listing day had 2 of 203)


def _median(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 2) if len(xs) >= MIN_BASE else None


def _share(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole >= MIN_BASE else None


def stats(items: list[dict]) -> dict:
    lc = [i["listing_close_pct"] for i in items if _num(i.get("listing_close_pct"))]
    lo = [i["listing_open_pct"] for i in items if _num(i.get("listing_open_pct"))]
    # one rule for every figure after the listing day: an issue whose latest price may still carry an unadjusted split (check_split) is
    # left out of the median, the share below issue, the index comparisons and the range alike, and counted (review: 18 SME issues were out
    # of the range but in the median, -0.2% against +6.3%)
    split_out = [i for i in items if i.get("check_split")]
    now = [i for i in items if _num(i.get("return_pct")) and not i.get("check_split")]
    vs_items = {k: [i for i in items if _num(i.get(f"vs_{k}_pct")) and not i.get("check_split")] for k, _l, _s in BENCH}
    vs = {k: [i[f"vs_{k}_pct"] for i in v] for k, v in vs_items.items()}
    sized = [i for i in items if _num(i.get("size_cr"))]
    split = [i for i in sized if _num(i.get("fresh_cr")) and _num(i.get("ofs_cr"))]
    out = {"issues": len(items), "with_listing_close": len(lc), "median_listing_open_pct": _median(lo), "median_listing_close_pct": _median(lc),
           "mean_listing_close_pct": round(statistics.fmean(lc), 2) if len(lc) >= MIN_BASE else None, "with_listing_open": len(lo),
           "closed_above_issue_pct": _share(sum(1 for x in lc if x > 0), len(lc)),
           "with_return": len(now), "median_return_pct": _median([i["return_pct"] for i in now]),
           "below_issue_now": sum(1 for i in now if i["below_issue"]), "below_issue_now_pct": _share(sum(1 for i in now if i["below_issue"]), len(now)),
           "raised_cr": round(sum(i["size_cr"] for i in sized), 2) if sized else None, "with_size": len(sized),
           "fresh_cr": round(sum(i["fresh_cr"] for i in split), 2) if split else None, "ofs_cr": round(sum(i["ofs_cr"] for i in split), 2) if split else None,
           "with_split": len(split), "split_left_out": len(split_out)}
    money_ = (out["fresh_cr"] or 0) + (out["ofs_cr"] or 0)          # a share of rupees, given when enough issues have both parts
    out["fresh_share_pct"] = round((out["fresh_cr"] or 0) / money_ * 100, 1) if len(split) >= MIN_BASE and money_ else None
    for k, _l, _s in BENCH:
        out[f"with_vs_{k}"] = len(vs[k])
        days = sorted(i["listing"] for i in vs_items[k] if i.get("listing"))      # the listing dates the comparison covers
        out[f"vs_{k}_from"], out[f"vs_{k}_to"] = (days[0], days[-1]) if days else (None, None)
        out[f"median_vs_{k}_pct"] = _median(vs[k])
        out[f"beat_{k}_pct"] = _share(sum(1 for x in vs[k] if x > 0), len(vs[k]))
    rt = [i["retail_times"] for i in items if _num(i.get("retail_times"))]
    out["with_retail_times"], out["median_retail_times"] = len(rt), _median(rt)
    fill = [i["retail_fill_pct"] for i in items if _num(i.get("retail_fill_pct"))]
    out["with_retail_fill"], out["median_retail_fill_pct"] = len(fill), _median(fill)
    odds = [i["retail_odds_pct"] for i in items if _num(i.get("retail_odds_pct"))]
    out["with_retail_odds"], out["median_retail_odds_pct"] = len(odds), _median(odds)
    return out


def bucket(v, buckets) -> str | None:
    if not _num(v):
        return None
    return next((label for label, lo, hi in buckets if lo <= v < hi), None)


def groups(items: list[dict], key, order: list[str] | None = None) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for i in items:
        k = key(i)
        if k is not None:
            by.setdefault(k, []).append(i)
    labels = [x for x in order if x in by] if order else sorted(by)
    return [{"label": k, **stats(by[k])} for k in labels]


def sector_groups(items: list[dict]) -> list[dict]:
    named = [i for i in items if i.get("sector")]
    counts: dict[str, int] = {}
    for i in named:
        counts[i["sector"]] = counts.get(i["sector"], 0) + 1
    top = [s for s, _n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:TOP_SECTORS]]
    out = groups(named, lambda i: i["sector"] if i["sector"] in top else "Other sectors", top + ["Other sectors"])
    return out


def segment_block(items: list[dict], seg: str) -> dict:
    sizes = SIZE_BUCKETS if seg == "mainboard" else SME_SIZE_BUCKETS
    ranked = sorted((i for i in items if _num(i.get("return_pct")) and not i.get("check_split")), key=lambda i: i["return_pct"])
    pick = lambda i: {k: i[k] for k in ("id", "name", "listing", "issue_price", "last_close", "last_day", "return_pct")}
    return {"all": stats(items), "best": pick(ranked[-1]) if ranked else None, "worst": pick(ranked[0]) if ranked else None, "by_year": groups(items, lambda i: i["year"] or None),
            "by_size": groups(items, lambda i: bucket(i.get("size_cr"), sizes), [b[0] for b in sizes]),
            "by_sector": sector_groups(items),
            "by_retail": groups(items, lambda i: bucket(i.get("retail_times"), RETAIL_BUCKETS), [b[0] for b in RETAIL_BUCKETS])}


def study(rows: list[dict], closes_of, bench: dict[str, dict[str, float]], today: date, window: tuple[str, str] | None = None) -> dict:
    """The whole study. `closes_of(row)` → {day: close} of the issue's stock, or ({day: close}, {day: open}); {} when unknown."""
    items = []
    for r in rows:
        if r.get("market", "IN") != "IN" or not r.get("listing") or r.get("issue_status") or r.get("social"):
            continue
        try:
            got = closes_of(r) or {}
        except Exception:
            got = {}
        closes, opens = got if isinstance(got, tuple) else (got, None)
        items.append(issue_figures(r, closes, bench, today, opens))
    items.sort(key=lambda i: (i["listing"], i["id"]), reverse=True)
    days = [i["listing"] for i in items]
    closed = sorted(i["last_day"] for i in items if i.get("last_day"))
    # "as of" is the latest close the figures use, not the day the study ran (a Sunday run said "the close of" a Sunday)
    out = {"as_of": closed[-1] if closed else today.isoformat(), "run_on": today.isoformat(), "window": {"from": window[0] if window else (min(days) if days else None),
                                                 "to": window[1] if window else (max(days) if days else None)},
           "benchmarks": {k: label for k, label, _s in BENCH},
           "coverage": {"issues": len(items), **{seg: sum(1 for i in items if i["segment"] == seg) for seg, _l in SEGMENTS},
                        "segment_not_recorded": sum(1 for i in items if i["segment"] not in ("mainboard", "sme")),
                        "with_issue_price": sum(1 for i in items if i["issue_price"]), "with_listing_close": sum(1 for i in items if _num(i["listing_close_pct"])),
                        "with_return": sum(1 for i in items if _num(i["return_pct"])), "with_retail_times": sum(1 for i in items if _num(i["retail_times"])),
                        "with_size": sum(1 for i in items if _num(i["size_cr"])), "with_sector": sum(1 for i in items if i["sector"]),
                        "with_retail_odds": sum(1 for i in items if _num(i["retail_odds_pct"]))},
           "definitions": {
               "listing_open_pct": "The first session's opening price against the issue price.",
               "listing_close_pct": "The first session's close against the issue price.",
               "return_pct": "The latest close against the issue price, with a split or bonus since the listing day counted back in (from the exchange's own listing-day close).",
               "vs_index_pct": "The issue's return minus the index's change from its close before the listing day to its close on the issue's latest day.",
               "retail_times": "Retail (individual) bids as a multiple of the shares kept for retail, from the exchange's final bids.",
               "retail_fill_pct": "The shares kept for retail as a share of the shares retail bid for: at most this much of retail demand could be met.",
               "retail_odds_pct": "Lots kept for retail against retail applications, where the exchange gave the applications.",
               "size_cr": "The issue's size in ₹ crore: as stated, else the shares at the issue price."},
           "segments": {seg: segment_block([i for i in items if i["segment"] == seg], seg) for seg, _l in SEGMENTS},
           "issues": items}
    return out


# ---------- markdown ----------
def fmt_pct(v, signed: bool = True) -> str:
    if not _num(v):
        return "–"
    return f"{v:+.1f}%" if signed else f"{v:.1f}%"


def fmt_cr(v) -> str:
    return f"₹{v:,.0f} cr" if _num(v) else "–"


def fmt_x(v) -> str:
    return f"{v:,.1f}x" if _num(v) else "–"


COLS = (("Issues", lambda s: str(s["issues"])), ("Median listing-day close", lambda s: fmt_pct(s["median_listing_close_pct"])),
        ("Closed above issue on day 1", lambda s: fmt_pct(s["closed_above_issue_pct"], False)),
        ("Median return to date", lambda s: fmt_pct(s["median_return_pct"])), ("Below issue now", lambda s: fmt_pct(s["below_issue_now_pct"], False)),
        ("Median vs NIFTY 50", lambda s: fmt_pct(s["median_vs_nifty50_pct"])), ("Median vs Smallcap 250", lambda s: fmt_pct(s["median_vs_smallcap250_pct"])),
        ("Raised", lambda s: fmt_cr(s["raised_cr"])))


def table(head: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(head))) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def group_table(title: str, rows: list[dict]) -> str:
    if not rows:
        return ""
    return f"**{title}**\n\n" + table([title.split(" by ")[-1].capitalize()] + [c for c, _f in COLS], [[r["label"]] + [f(r) for _c, f in COLS] for r in rows])


def markdown(res: dict) -> str:
    cov = res["coverage"]
    out = [f"# India IPOs, {res['window']['from']} to {res['window']['to']}", "",
           f"As of {res['as_of']}. {cov['issues']} listed issues: {cov['mainboard']} main board, {cov['sme']} SME"
           + (f", {cov['segment_not_recorded']} with the segment not recorded" if cov["segment_not_recorded"] else "") + ".", "",
           table(["Coverage", "Issues"], [[k.replace("_", " ").capitalize(), str(v)] for k, v in cov.items()]), ""]
    for seg, label in SEGMENTS:
        b = res["segments"][seg]
        if not b["all"]["issues"]:
            continue
        a = b["all"]
        out += [f"## {label}", "", table(["Measure", "Value"], [
            ["Issues", str(a["issues"])], ["Median listing-day open", fmt_pct(a["median_listing_open_pct"])],
            ["Median listing-day close", fmt_pct(a["median_listing_close_pct"])], ["Closed above issue on day 1", fmt_pct(a["closed_above_issue_pct"], False)],
            ["Median return to date", fmt_pct(a["median_return_pct"])], ["Below issue price now", f"{a['below_issue_now']} of {a['with_return']} ({fmt_pct(a['below_issue_now_pct'], False)})"],
            ["Median vs NIFTY 50", fmt_pct(a["median_vs_nifty50_pct"])], ["Beat NIFTY 50", fmt_pct(a["beat_nifty50_pct"], False)],
            ["Median vs NIFTY Smallcap 250", fmt_pct(a["median_vs_smallcap250_pct"])], ["Median retail subscription", fmt_x(a["median_retail_times"])],
            ["Median share of retail demand that could be filled", fmt_pct(a["median_retail_fill_pct"], False)],
            ["Money raised", fmt_cr(a["raised_cr"])], ["Fresh issue / offer for sale (issues with both known)", f"{fmt_cr(a['fresh_cr'])} / {fmt_cr(a['ofs_cr'])}"]]), ""]
        for key, title in (("by_year", f"{label} by year"), ("by_size", f"{label} by size"), ("by_retail", f"{label} by retail subscription"),
                           ("by_sector", f"{label} by sector")):
            t = group_table(title, b[key])
            if t:
                out += [t, ""]
    out += ["## Definitions", ""] + [f"- **{k}**: {v}" for k, v in res["definitions"].items()]
    return "\n".join(out).rstrip() + "\n"


# ---------- drafts ----------
class Figures:
    """Reads numbers from the study's JSON by path and remembers each path used, for the draft's list of sources."""

    def __init__(self, res: dict):
        self.res, self.used = res, []

    def __call__(self, path: str):
        v = self.res
        for part in path.split("."):
            v = v[int(part)] if isinstance(v, list) else v.get(part) if isinstance(v, dict) else None
            if v is None:
                break
        if path not in self.used:
            self.used.append(path)
        return v

    def sources(self) -> str:
        return "\n".join(["", "---", "Figures used (paths in ipo-study.json):", ""] + [f"- `{p}`: {self(p)}" for p in self.used])


TERMS = {"listing_open_pct": "Listing-day open", "listing_close_pct": "Listing-day close", "return_pct": "Return to date",
         "vs_index_pct": "Against the index", "retail_times": "Retail subscription", "retail_fill_pct": "Share of retail demand that could be filled",
         "retail_odds_pct": "Retail allotment odds", "size_cr": "Issue size"}


def _group(res: dict, seg: str, key: str, label: str) -> int | None:
    rows = res["segments"][seg][key]
    return next((i for i, r in enumerate(rows) if r["label"] == label), None)


def drafts(res: dict, site: str = SITE) -> dict[str, str]:
    """The research note, the X article and the LinkedIn post, from the study's figures only (marked DRAFT)."""
    ipos = f"{site}/invest/ipos"
    win = f"{res['window']['from']} to {res['window']['to']}"
    banner = ("> DRAFT for review. The title's claim (India first by number of IPOs) is not from these figures: cite the global count it "
              "comes from, or drop it. Figures in brackets are the number of issues each figure is worked out on; a figure from fewer than "
              f"{MIN_BASE} issues is not given.\n")
    horizon = (f"Return to date runs from each issue's listing day to the close of {res['as_of']}, so the holding periods differ, from days to "
               "two years: it is not a same-length comparison between issues.")

    def nb(v, n, signed: bool = True) -> str:
        """A figure with the number of issues it is worked out on."""
        return f"{fmt_pct(v, signed)} ({n})"

    def vs_sample(f: Figures, p: str, k: str = "nifty50") -> str:
        """Which issues an index comparison covers: their number and listing dates (the index's closes are stored for recent listings)."""
        return f"the {f(p + f'.with_vs_{k}')} issues listed {f(p + f'.vs_{k}_from')} to {f(p + f'.vs_{k}_to')} with the index's closes stored"

    def split_note(f: Figures, p: str, label: str) -> str:
        n = f(p + ".split_left_out") or 0
        return (f" {n} {label} issues whose latest price may still carry an unadjusted share split are left out of every figure after the "
                "listing day.") if n else ""

    def sector_note(seg: str) -> str:
        days = sorted(i["listing"] for i in res["issues"] if i.get("segment") == seg and i.get("sector") and i.get("listing"))
        return f"Sector is stored for {len(days)} issues, listed {days[0]} to {days[-1]}." if days else ""

    def seg_lines(f: Figures, seg: str, label: str) -> list[str]:
        p = f"segments.{seg}.all"
        lc, rt, vs = f(p + '.with_listing_close'), f(p + '.with_return'), f(p + '.with_vs_nifty50')
        return [f"| {label} | {f(p + '.issues')} | {nb(f(p + '.median_listing_close_pct'), lc)} | {nb(f(p + '.closed_above_issue_pct'), lc, False)} | "
                f"{nb(f(p + '.median_return_pct'), rt)} | {nb(f(p + '.below_issue_now_pct'), rt, False)} | {nb(f(p + '.median_vs_nifty50_pct'), vs)} | "
                f"{fmt_cr(f(p + '.raised_cr'))} ({f(p + '.with_size')} of {f(p + '.issues')} sized) |"]

    def retail_rows(f: Figures, seg: str) -> list[str]:
        out = []
        for label, _lo, _hi in RETAIL_BUCKETS:
            i = _group(res, seg, "by_retail", label)
            if i is None:
                continue
            p = f"segments.{seg}.by_retail.{i}"
            out.append(f"| {label} | {f(p + '.issues')} | {fmt_pct(f(p + '.median_listing_close_pct'))} | {fmt_pct(f(p + '.median_return_pct'))} | "
                       f"{fmt_pct(f(p + '.below_issue_now_pct'), False)} | {fmt_pct(f(p + '.median_vs_nifty50_pct'))} |")
        return out

    # ---- research note
    f = Figures(res)
    mb, sme = "segments.mainboard.all", "segments.sme.all"
    note = [banner, "# India is the world's #1 IPO market. Is retail winning?", "",
            f"StratLab tracks every Indian IPO from the exchanges' own pages: the bids by investor type, the listing day, and how each "
            f"stock has done since against the index. This note counts the issues that listed from {win}: {f('coverage.issues')} in all, "
            f"{f('coverage.mainboard')} on the main board and {f('coverage.sme')} on the SME platforms. Every issue is on "
            f"[StratLab's IPOs page]({ipos}).", "",
            "## The headline figures", "",
            "| Segment | Issues | Median listing-day close | Closed above issue on day 1 | Median return to date | Below issue now | Median vs NIFTY 50 | Raised |",
            "|---|---:|---:|---:|---:|---:|---:|---:|", *seg_lines(f, "mainboard", "Main board"), *seg_lines(f, "sme", "SME"), "",
            f"In brackets: the issues each figure is worked out on. A dash: fewer than {MIN_BASE} issues have it. Raised: the issues whose size is "
            "stored, out of all. " + horizon, "",
            f"On the main board, the median issue closed its first day {fmt_pct(f(mb + '.median_listing_close_pct'))} against its issue price, "
            f"and {fmt_pct(f(mb + '.closed_above_issue_pct'), False)} closed above it (the {f(mb + '.with_listing_close')} issues with a first-day close stored). To the latest close, the median return is "
            f"{fmt_pct(f(mb + '.median_return_pct'))}, and {f(mb + '.below_issue_now')} of {f(mb + '.with_return')} issues "
            f"({fmt_pct(f(mb + '.below_issue_now_pct'), False)}) trade below the price people paid.", "",
            "## The listing day is not the whole story", "",
            f"Measured over the same days ({vs_sample(f, mb)}), the median main-board issue did {fmt_pct(f(mb + '.median_vs_nifty50_pct'))} against the NIFTY 50 and "
            f"{fmt_pct(f(mb + '.median_vs_smallcap250_pct'))} against the NIFTY Smallcap 250 (the {f(mb + '.with_vs_smallcap250')} issues with that index's "
            f"closes over their days); {fmt_pct(f(mb + '.beat_nifty50_pct'), False)} of {f(mb + '.with_vs_nifty50')} did better than the NIFTY 50. For SME issues the median against the NIFTY 50 is {fmt_pct(f(sme + '.median_vs_nifty50_pct'))}, "
            f"and {f(sme + '.below_issue_now')} of {f(sme + '.with_return')} SME issues trade below their issue price." + split_note(f, sme, "SME"), "",
            f"The spread between issues is wide. On the main board, {f('segments.mainboard.best.name')} (listed {f('segments.mainboard.best.listing')}) is "
            f"{fmt_pct(f('segments.mainboard.best.return_pct'))} from its issue price; {f('segments.mainboard.worst.name')} (listed "
            f"{f('segments.mainboard.worst.listing')}) is {fmt_pct(f('segments.mainboard.worst.return_pct'))}. Among SME issues the range is "
            f"{fmt_pct(f('segments.sme.worst.return_pct'))} to {fmt_pct(f('segments.sme.best.return_pct'))}.", "",
            "## Does a heavily bid retail book mean a good result?", "",
            "Retail subscription is the retail bids as a multiple of the shares kept for retail, from the exchange's final figures.", "",
            "| Main board | Issues | Median listing-day close | Median return to date | Below issue now | Median vs NIFTY 50 |",
            "|---|---:|---:|---:|---:|---:|", *retail_rows(f, "mainboard"), "",
            f"Across the {f(mb + '.with_retail_times')} main-board issues with final bids stored, the median retail book was "
            f"{fmt_x(f(mb + '.median_retail_times'))} subscribed. At that demand, at most "
            f"{fmt_pct(f(mb + '.median_retail_fill_pct'), False)} of what retail asked for could be filled: in a heavily bid issue most "
            "applicants get nothing, so the listing-day gain reaches few of them.", "",
            "## Where the money went", "",
            f"The {f(mb + '.with_size')} main-board issues with a known size raised {fmt_cr(f(mb + '.raised_cr'))}. Of the "
            f"{f(mb + '.with_split')} where both parts are known, {fmt_cr(f(mb + '.fresh_cr'))} was fresh money for the company and {fmt_cr(f(mb + '.ofs_cr'))} was an "
            f"offer for sale by existing holders ({fmt_pct(f(mb + '.fresh_share_pct'), False)} fresh).", ""]
    yr = res["segments"]["mainboard"]["by_year"]
    if yr:
        note += ["## By year (main board)", "", "| Year | Issues | Median listing-day close | Median return to date | Below issue now |", "|---|---:|---:|---:|---:|"]
        for i, _r in enumerate(yr):
            p = f"segments.mainboard.by_year.{i}"
            note.append(f"| {f(p + '.label')} | {f(p + '.issues')} | {fmt_pct(f(p + '.median_listing_close_pct'))} | {fmt_pct(f(p + '.median_return_pct'))} | "
                        f"{fmt_pct(f(p + '.below_issue_now_pct'), False)} |")
        note.append("")
    sz = res["segments"]["mainboard"]["by_size"]
    if sz:
        note += ["## By issue size (main board)", "", "| Size | Issues | Median listing-day close | Median return to date | Below issue now |", "|---|---:|---:|---:|---:|"]
        for i, _r in enumerate(sz):
            p = f"segments.mainboard.by_size.{i}"
            note.append(f"| {f(p + '.label')} | {f(p + '.issues')} | {fmt_pct(f(p + '.median_listing_close_pct'))} | {fmt_pct(f(p + '.median_return_pct'))} | "
                        f"{fmt_pct(f(p + '.below_issue_now_pct'), False)} |")
        note.append("")
    sec = res["segments"]["mainboard"]["by_sector"]
    if sec:
        note += ["## By sector (main board)", "", sector_note("mainboard"), "",
                 "| Sector | Issues | Median listing-day close | Median return to date | Below issue now | Median vs NIFTY 50 |",
                 "|---|---:|---:|---:|---:|---:|"]
        for i, _r in enumerate(sec):
            p = f"segments.mainboard.by_sector.{i}"
            note.append(f"| {f(p + '.label')} | {f(p + '.issues')} | {fmt_pct(f(p + '.median_listing_close_pct'))} | {fmt_pct(f(p + '.median_return_pct'))} | "
                        f"{fmt_pct(f(p + '.below_issue_now_pct'), False)} | {fmt_pct(f(p + '.median_vs_nifty50_pct'))} |")
        note.append("")
    sr = retail_rows(f, "sme")
    if sr:
        note += ["## SME issues by retail subscription", "", "| SME | Issues | Median listing-day close | Median return to date | Below issue now | Median vs NIFTY 50 |",
                 "|---|---:|---:|---:|---:|---:|", *sr, ""]
    note += ["## What StratLab tracks", "",
             f"Each issue on [StratLab's IPOs page]({ipos}) shows its dates, price band and size (fresh issue and offer for sale), the bids by "
             "investor type through the bidding days, the listing-day open and close against the issue price, and the trading since. "
             "The offer document's facts and red flags are read from the document itself.", "",
             "## How the figures are worked out", ""] + [f"- **{TERMS.get(k, k)}**: {v}" for k, v in res["definitions"].items()] + [
             f"- Data: the exchanges' public-issue pages and daily closes, as of {f('as_of')}.", f.sources()]
    note_md = "\n".join(note) + "\n"

    # ---- X article
    f = Figures(res)
    x = [banner, "# India's IPO boom: what happened after the listing day", "",
         f"India lists more IPOs than any other market. StratLab tracked {f('coverage.issues')} that listed from {win}. Here is what the "
         "exchanges' own figures show.", "",
         "## 1. " + ("Day one was mostly up" if (f(mb + '.closed_above_issue_pct') or 0) > 50 else "Day one was mixed"), "",
         f"The median main-board issue closed its first day {fmt_pct(f(mb + '.median_listing_close_pct'))} against its issue price; "
         f"{fmt_pct(f(mb + '.closed_above_issue_pct'), False)} closed above it ({f(mb + '.with_listing_close')} issues with a first-day close stored)."
         + (f" SME issues: median {nb(f(sme + '.median_listing_close_pct'), f(sme + '.with_listing_close'))}." if _num(f(sme + '.median_listing_close_pct')) else ""), "",
         "## 2. " + ("Then the gains narrowed" if _num(f(mb + '.median_return_pct')) and _num(f(mb + '.median_listing_close_pct')) and f(mb + '.median_return_pct') < f(mb + '.median_listing_close_pct') else "After the listing day"), "",
         f"To the latest close, the median main-board issue is {fmt_pct(f(mb + '.median_return_pct'))} from its issue price, and "
         f"{fmt_pct(f(mb + '.below_issue_now_pct'), False)} trade below it. Against the NIFTY 50 over the same days ({vs_sample(f, mb)}): "
         f"{fmt_pct(f(mb + '.median_vs_nifty50_pct'))} (median), and {fmt_pct(f(mb + '.beat_nifty50_pct'), False)} did better than the index. "
         f"The range is wide: {f('segments.mainboard.best.name')} is {fmt_pct(f('segments.mainboard.best.return_pct'))} from its issue price, "
         f"{f('segments.mainboard.worst.name')} {fmt_pct(f('segments.mainboard.worst.return_pct'))}. " + horizon, "",
         "[Chart 1: median listing-day close and median return to date, by retail subscription, main board]", "",
         "## 3. A heavily bid retail book means few get shares", "",
         f"The median retail book was {fmt_x(f(mb + '.median_retail_times'))} subscribed, so at most {fmt_pct(f(mb + '.median_retail_fill_pct'), False)} "
         f"of retail demand could be met (median over the {f(mb + '.with_retail_times')} issues with final bids stored). In a heavily bid issue, "
         "most retail applicants get no shares at all, so the listing-day change is not what most of them had.", "",
         "## 4. " + ("Most of the money went to selling holders" if (f(mb + '.fresh_share_pct') or 0) < 50 else "Most of the money was fresh capital"), "",
         f"Of the main-board money where the split is known, {fmt_pct(f(mb + '.fresh_share_pct'), False)} was fresh capital for the company; the rest "
         "was existing holders selling.", "",
         "## 5. SME issues are a different market", "",
         f"{f('coverage.sme')} SME issues listed in the same period. To the latest close their median is {fmt_pct(f(sme + '.median_return_pct'))} "
         f"from the issue price, {f(sme + '.below_issue_now')} of the {f(sme + '.with_return')} with a latest close ({fmt_pct(f(sme + '.below_issue_now_pct'), False)}) "
         f"trade below it, and against the NIFTY 50 the median is {nb(f(sme + '.median_vs_nifty50_pct'), f(sme + '.with_vs_nifty50'))}." + split_note(f, sme, "SME"), "",
         "[Chart 2: share of issues below their issue price now, main board and SME]", "",
         "## 6. See every issue", "",
         f"Bids by investor type, listing day and performance since listing are tracked on [StratLab's IPOs page]({ipos}).", f.sources()]
    x_md = "\n".join(x) + "\n"

    # ---- LinkedIn
    f = Figures(res)
    li = [banner, "India is the world's #1 IPO market. Is retail winning?", "",
          f"I counted {f('coverage.issues')} Indian IPOs that listed from {win}, using the exchanges' own figures, on StratLab.", "",
          f"- Main board: the median issue closed day one {fmt_pct(f(mb + '.median_listing_close_pct'))} against its issue price ({f(mb + '.with_listing_close')} issues with a first-day close).",
          f"- To date, the median is {fmt_pct(f(mb + '.median_return_pct'))}, and {fmt_pct(f(mb + '.below_issue_now_pct'), False)} trade below the issue price.",
          f"- Against the NIFTY 50 over the same days, the median issue is {fmt_pct(f(mb + '.median_vs_nifty50_pct'))} ({vs_sample(f, mb)}).",
          f"- The median retail book was {fmt_x(f(mb + '.median_retail_times'))} subscribed: at most {fmt_pct(f(mb + '.median_retail_fill_pct'), False)} of retail demand could be filled ({f(mb + '.with_retail_times')} of {f(mb + '.issues')} issues with final bids stored).",
          f"- {fmt_pct(f(mb + '.fresh_share_pct'), False)} of the money (where the split is known) was fresh capital; the rest went to selling holders.", "",
          "The listing-day figures and the figures to date are different measures. " + horizon, "",
          f"Every issue, with bids by investor type and performance since listing: {ipos}", f.sources()]
    li_md = "\n".join(li) + "\n"
    return {"research-note.md": note_md, "x-article.md": x_md, "linkedin-post.md": li_md}


def chart_specs(res: dict) -> list[dict]:
    """The X article's two charts as specs (rendered by `render_charts` when matplotlib is installed)."""
    rb = res["segments"]["mainboard"]["by_retail"]
    mb = res["segments"]["mainboard"]["all"]
    note = (f"Return to date: each issue from its listing day to {res['as_of']}, so holding periods differ. In brackets: issues in the group. "
            f"Retail subscription is stored for {mb['with_retail_times']} of {mb['issues']} main-board issues.")
    return [{"file": "chart-1-retail-subscription.png", "type": "grouped_bar", "note": note,
             "title": f"Main board IPOs: listing day vs to date, by retail subscription (as of {res['as_of']})",
             "categories": [f"{r['label']} ({r['issues']})" for r in rb],
             "series": [{"name": "Median listing-day close", "values": [r["median_listing_close_pct"] for r in rb], "source": "segments.mainboard.by_retail.*.median_listing_close_pct"},
                        {"name": "Median return to date", "values": [r["median_return_pct"] for r in rb], "source": "segments.mainboard.by_retail.*.median_return_pct"}],
             "y_label": "% against the issue price"},
            {"file": "chart-2-below-issue.png", "type": "bar", "title": f"Share of IPOs below their issue price (as of {res['as_of']})",
             "note": "In brackets: issues with a latest close. The issues listed on different days, so each has been held for a different time.",
             "categories": [f"{label} ({res['segments'][seg]['all']['with_return']})" for seg, label in SEGMENTS],
             "series": [{"name": "Below issue price now", "values": [res["segments"][seg]["all"]["below_issue_now_pct"] for seg, _l in SEGMENTS],
                         "source": "segments.<segment>.all.below_issue_now_pct"}], "y_label": "% of issues"}]


def render_charts(specs: list[dict], out: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        (out / "chart-specs.json").write_text(json.dumps(specs, indent=1, ensure_ascii=False))
        return ["chart-specs.json"]
    done = []
    for s in specs:
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
        n = len(s["series"])
        width = 0.8 / n
        for k, ser in enumerate(s["series"]):
            xs = [i + (k - (n - 1) / 2) * width for i in range(len(s["categories"]))]
            vals = [v if _num(v) else 0 for v in ser["values"]]
            bars = ax.bar(xs, vals, width, label=ser["name"], color=("#3b6fd8", "#e0884a")[k % 2])
            for b_, v in zip(bars, ser["values"]):
                ax.annotate("–" if not _num(v) else f"{v:.1f}%", (b_.get_x() + b_.get_width() / 2, b_.get_height()), ha="center",
                            va="bottom" if (v or 0) >= 0 else "top", fontsize=8)
        ax.set_xticks(range(len(s["categories"])), s["categories"])
        ax.axhline(0, color="#888", linewidth=0.8)
        ax.set_ylabel(s["y_label"])
        ax.set_title(s["title"], fontsize=11)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        if n > 1:
            ax.legend(frameon=False, fontsize=8)
        if s.get("note"):
            fig.text(0.01, 0.045, s["note"], fontsize=6.5, color="#444", wrap=True)
        fig.text(0.01, 0.01, "Source: exchanges' public-issue pages and daily closes. StratLab, stratlab.studio/invest/ipos", fontsize=7, color="#666")
        fig.tight_layout(rect=(0, 0.09 if s.get("note") else 0.03, 1, 1))
        fig.savefig(out / s["file"])
        plt.close(fig)
        done.append(s["file"])
    return done


# ---------- running it ----------
def closes_from(bars: list[dict]) -> dict[str, float]:
    return {b["t"][:10]: b["c"] for b in bars if _num(b.get("c"))}


def yahoo_bars(yahoo, symbol: str, days: int) -> list[dict]:
    try:
        return yahoo.chart(symbol, "1d", days)["candles"]
    except Exception:
        return []


def yahoo_closes(yahoo, symbol: str, days: int) -> dict[str, float]:
    return closes_from(yahoo_bars(yahoo, symbol, days))


def run(rows: list[dict], out: Path, today: date, yahoo=None, with_drafts: bool = False, with_charts: bool = False,
        window: tuple[str, str] | None = None) -> dict:
    from . import ipo as I
    out.mkdir(parents=True, exist_ok=True)
    days = 800
    bench = {k: yahoo_closes(yahoo, sym, days) for k, _l, sym in BENCH} if yahoo else {}

    def closes_of(r):
        sym = I.yahoo_symbol({**r, "market": "IN"})
        bars = yahoo_bars(yahoo, sym, days) if yahoo and sym else []
        return closes_from(bars), {b["t"][:10]: b["o"] for b in bars if _num(b.get("o"))}
    res = study(rows, closes_of, bench, today, window)
    (out / "ipo-study.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    (out / "ipo-study.md").write_text(markdown(res))
    if with_drafts:
        for name, text in drafts(res).items():
            (out / name).write_text(text)
    if with_charts:
        render_charts(chart_specs(res), out)
    return res


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="The IPO study: India's IPOs of the last two years, from the stored history.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", help="a JSON file of IPO rows (else the stored history and the live list's listed issues)")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today in India)")
    ap.add_argument("--no-prices", action="store_true", help="no daily closes: only the stored listing-day and latest figures")
    ap.add_argument("--drafts", action="store_true")
    ap.add_argument("--charts", action="store_true")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()
    if a.rows:
        got = json.loads(Path(a.rows).read_text())
        rows = got.get("rows", got) if isinstance(got, dict) else got
    else:
        from . import ipo as I
        from . import ipo_history as H
        have = {r["id"]: r for r in H.load()["rows"]}
        for r in I.load("IN")["rows"]:
            if r["id"] not in have and H.keeps(r, today) and I.stage_of(r) == "listed":
                have[r["id"]] = r
        rows = list(have.values())
    yahoo = None
    if not a.no_prices:
        from .intel.yahoo import Yahoo
        yahoo = Yahoo()
    from .ipo_history import cutoff
    res = run(rows, Path(a.out), today, yahoo, a.drafts, a.charts, (cutoff(today).isoformat(), today.isoformat()) if not a.rows else None)
    print(json.dumps(res["coverage"]))


if __name__ == "__main__":
    main()
