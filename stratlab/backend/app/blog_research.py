"""The blog's research posts (BLOG-1), written from StratLab's own data and never from a number typed in by hand:

  (a) Classic strategies across ten markets, after costs: the strategy library's published samples.
  (b) IPO listing day in India, this year so far: the IPO tracker's listed issues.
  (c) SIP vs lump sum on the NIFTY 50: the SIP test engine on the index's own history.

Each builder is a function of plain data (library entries, tracker rows, index closes), so what a post says can be checked
against what it was given; `generate` reads the app's sources and stores the posts. It runs when an admin presses the button
and once a month from the newsletter job's clock (no job of its own), and each post is one row that is updated in place.
Every post says where its data comes from (by kind, never by vendor), the period, the method and the limits, and keeps to
facts: no advice wording, no ranking of what to pick, no promise."""
import json
import re
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from . import blog, db, email_kit as kit

IST = ZoneInfo("Asia/Kolkata")
STATE_KEY = "blog:research:state"
MONTH_KEY = "blog:research:month"
GEN = 9                             # 9: a theme post's counts of companies and layers as its public page and card say them (e81, LIVE17A-005); 8: a theme post follows its deck: medians on 3 companies or more with their counts, the chain's own comparison, each company's own words, the theme page and deck linked (blog2); 7: a theme post says the day of the theme's read it was worked out from (LIVE7A-017); 6: theme posts with no layers, a headline for a name or a same-day twin are hidden (LIVE6-003); the version of what the builders write; bump it with a change to a post's words or tables and every post is written again at the next check after the deploy (LIVE2-029)
GEN_KEY = "blog:research:gen"       # {"gen", "ok", "tries", "at"} of the last run made for a version
SIP_AMOUNT = 10000
SIP_HORIZONS = (3, 5)
IPO_ROWS_SHOWN = 1000               # every issue counted is listed (LIVE4-019 partial: "the latest 50 of 85"); a phone pages them
IPO_PHONE_PAGE = 20
RESEARCH_DAY = 3                    # the monthly run waits for the third (the data of the month's first days is in by then)
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
MARKETS = ["IN", "US", "UK", "EU", "JP", "CRYPTO", "FX", "MCX", "CDS", "CMDTY"]
_lock = threading.Lock()


def p1(x) -> str:
    """+4.2% or −3.1% (one decimal, a real minus; a move that rounds to zero has no sign)."""
    return kit.pct(x, 1)


def n1(x) -> str:
    return f"{float(x):,.1f}"


# ---------- (a) the strategy library's samples ----------
def classic_strategies(entries: list[dict], now: datetime | None = None) -> dict | None:
    """The post on StratLab's own published strategy samples (library entries made by library_seed, as library.public_entries
    gives them): each strategy's return after costs beside the passive return over the same period, the four checks, and
    the method. None when there are fewer than ten samples (nothing worth a post)."""
    from . import library, library_seed
    from .data.markets import BY_ID
    rows = [e for e in entries if isinstance(e.get("seed"), dict) and e.get("market") in blog_markets() and isinstance(e.get("stats"), dict)]
    if len(rows) < 10:
        return None
    by_market: dict[str, list[dict]] = {m: [] for m in MARKETS}
    for e in rows:
        by_market[e["market"]].append(e)
    live = [m for m in MARKETS if by_market[m]]
    ran = [e for e in rows if library.ran(e)]
    versus = [(e, library.versus_hold(e)) for e in rows]
    ahead = sum(1 for _, h in versus if h and h["gap"] > 0)
    behind = sum(1 for _, h in versus if h and h["gap"] < 0)
    lost = sum(1 for e in ran if isinstance(e["stats"].get("ret"), (int, float)) and e["stats"]["ret"] < 0)
    froms = sorted(str((e.get("range") or {}).get("from") or "")[:10] for e in rows if (e.get("range") or {}).get("from"))
    tos = sorted(str((e.get("range") or {}).get("to") or "")[:10] for e in rows if (e.get("range") or {}).get("to"))
    kinds: dict[str, int] = {}
    for e in rows:
        v = (e.get("verdict") or {}).get("verdict")
        kinds[v] = kinds.get(v, 0) + 1
    names = {s: re.sub(r"^ST S2: ", "", spec["name"]) for s, spec in library_seed.STRATEGIES.items()}      # (LIVE2-006: the scan's shorthand is not a name in a table)
    n_strats = len({e["seed"].get("slug") for e in rows})
    checks: dict[str, dict[str, int]] = {}
    for e in rows:
        for c in library.checks_of(e):
            checks.setdefault(c["id"], {}).setdefault(c["status"], 0)
            checks[c["id"]][c["status"]] += 1
    # the table's names are short; each check is described in full under "How these tests were run"
    check_names = {"unseen": "Unseen data", "nearby": "Nearby settings", "shuffle": "Bad-luck drawdown", "sample": "Enough trades"}
    word = {"pass": "passed", "warn": "warning", "fail": "failed", "skip": "not run", "not_passed": "not passed"}
    # the four checks as one small table: a row each, a column for each outcome that happened (PUB-2: four sentences of counts)
    outcomes = [st for st in ("pass", "warn", "fail", "skip", "not_passed") if any(st in checks.get(cid, {}) for cid in check_names)]
    check_rows = [[check_names[cid]] + [str(checks[cid].get(st, 0)) for st in outcomes] for cid in ("unseen", "nearby", "shuffle", "sample") if checks.get(cid)]
    first, last = (froms[0], tos[-1]) if froms and tos else ("", "")
    other_n = len(rows) - ahead - behind
    side = {id(e): h for e, h in versus}
    market_rows = []
    for m in live:
        hs = [side[id(e)] for e in by_market[m]]
        up = sum(1 for h in hs if h and h["gap"] > 0)
        down = sum(1 for h in hs if h and h["gap"] < 0)
        market_rows.append({"label": (BY_ID.get(m) or {}).get("name") or m, "values": [up, down, len(hs) - up - down]})
    kind_words = [(k, label) for k, label in (("edge", "passed their checks"), ("mixed", "with mixed check results"), ("not_enough", "with too few trades"),
                                              ("luck", "that failed a robustness check"), ("no_edge", "that lost money after costs")) if kinds.get(k)]
    blocks: list[dict] = [
        {"t": "p", "text": f"{len(rows)} tests of {n_strats} well-known rule sets on a standard group of instruments in each of {len(live)} markets, run on "
                           "StratLab's own backtester with each market's costs applied. Every test is published in the strategy library with its rules, "
                           "its result and its verdict; this post puts the results side by side. In the tables, After costs is the rule set's return with the "
                           "market's costs applied, and Passive is the return of owning the same instruments for the whole period."},
        {"t": "h2", "text": "What the tests show"},
        {"t": "stats", "items": [
            {"v": f"{ahead} of {len(rows)}", "l": "tests ahead of the passive return", "s": "after costs"},
            {"v": f"{behind} of {len(rows)}", "l": "tests behind it", "s": f"{other_n} could not be compared" if other_n else "after costs"},
            {"v": f"{lost} of {len(ran)}", "l": "tests that traded lost money", "s": "after costs"},
            {"v": f"{kinds.get('edge', 0)} of {len(rows)}", "l": "passed their checks", "s": "the verdict of the four checks"}]},
        {"t": "bars", "caption": "Tests in each market: return after costs against the passive return", "series": ["Ahead", "Behind", "Not compared"], "rows": market_rows},
        ]
    # VR6-006: said by the tiles and the bars above; the sentences stay in the page, folded (see the IPO post)
    words = [
            f"Against the passive return, after costs: ahead in {ahead} of {len(rows)} tests, behind in {behind}" + (f", and {other_n} could not be compared (no trades or no figure)." if other_n else "."),
            f"{lost} of the {len(ran)} tests that traded lost money after costs.",
            "Verdicts as the tests' checks gave them: " + ", ".join(f"{kinds[k]} {label}" for k, label in kind_words) + ".",
            (f"Periods: tests run between {short(first)} and {short(last)}; each table gives its own." if first and last else "Each table gives its own period."),
    ]
    if check_rows:
        k = len(outcomes)
        blocks += [{"t": "h2", "text": "The four checks"},
                   {"t": "table", "caption": "Tests by the outcome of each check", "head": ["Check"] + [word[st].capitalize() for st in outcomes],
                    "rows": check_rows, "align": "l" + "r" * k}]
    for m in live:
        group = sorted(by_market[m], key=lambda e: (names.get(e["seed"].get("slug"), e["name"]), e["id"]))
        mname = (BY_ID.get(m) or {}).get("name") or m
        groups = sorted({(e.get("group") or {}).get("name") or "" for e in group} - {""})
        table, spans = [], []
        for e in group:
            h = library.versus_hold(e)
            st = e["stats"]
            table.append([{"a": names.get(e["seed"].get("slug"), e["name"]), "href": f"/library/{e['id']}"},
                          p1(st["ret"]) if library.ran(e) and isinstance(st.get("ret"), (int, float)) else "no trades",
                          p1(st["buy_hold"]) if isinstance(st.get("buy_hold"), (int, float)) else "–",
                          (f"{blog.MINUS if h['gap'] <= -0.05 else '+' if h['gap'] >= 0.05 else ''}{abs(h['gap']):.1f} pts") if h else "–",
                          f"{st['trades']:,}" if isinstance(st.get("trades"), int) else "–",
                          library.label(e)])
            spans.append(f"{short((e.get('range') or {}).get('from'))} to {short((e.get('range') or {}).get('to'))}")
        # one period said once: every row repeated the same "11 Mar 2025 to 28 Oct 2026", which also pushed the table off a phone's
        # screen (VR4-006). The caption gives the usual period; a test that ran over another one says so in small type under its name,
        # not in a column of its own that is empty for all the others (PUB-2)
        usual = max(set(spans), key=spans.count) if spans else ""
        for row, x in zip(table, spans):
            if x != usual:
                row[0] = [row[0], {"s": f"Tested {x}"}]
        # VR7-002: one fold for each market (open on a desktop; a phone shows the ten markets as ten lines and opens one at a time:
        # the ten tables were 10,000px of cards on a phone). Every figure stays in the page.
        blocks += [{"t": "fold", "title": mname, "note": f"{len(group)} tests", "blocks": [
                   {"t": "p", "text": f"Group: {', '.join(groups)}." if groups else f"{mname} group."},
                   {"t": "table", "caption": f"{mname}, tested {usual}", "align": "lrrrrl", "widths": [34, 12, 9, 11, 8, 26],
                    "head": ["Rule set", "After costs", "Passive", "Difference", "Trades", "Checks"], "rows": table}]}]
    risk = library_seed.RISK
    blocks += [
        {"t": "details", "title": "The headline figures in words", "items": words, "words": True},
        {"t": "details", "title": "How these tests were run", "items": [
            "Data: daily candles from each market's public price data (exchange data for shares and futures, public price feeds for coins and "
            "currency pairs); the intraday rule set uses 15-minute candles. Each test covers about five years of daily candles, or what the market has.",
            "Each rule set runs on every instrument of its group as one pot of capital. Starting capital is "
            f"{risk['capital']:,} in the market's own money (more for Japan, Indian commodities and Indian currency futures, whose contracts cost more); a "
            f"position risks {risk['riskPct']:g}% of capital and takes at most {risk['maxAlloc']:g}% of it, with a stop (an exit when the price falls a set distance) where the rule set has one.",
            f"Costs: each market's own charges are applied to every order (in India brokerage, STT, exchange and SEBI fees, stamp duty and GST; in the US "
            f"the SEC and FINRA fees; stamp duty in the UK; trading fees on coins; spreads on currency pairs and commodity futures), plus "
            f"{risk['slippage']:g}% slippage on every fill. Brokerage is a flat amount per order in the market's currency: "
            f"{library_seed.risk_of({'body': {}}, 'IN')['brokerage']:g} in India, none in the markets where trading is free.",
            "The four checks: unseen data (the period is split 70/30 and the last part is traded with fresh capital), nearby settings (indicator lengths "
            "nudged up and down; not run on a group of instruments), bad-luck drawdown (the order of the trades reshuffled 1,000 times) and enough "
            "trades (under 15 is too few to tell skill from luck, 30 or more is a fair sample).",
            "The rule sets, with their exact rules, are in the strategy library: " + ", ".join(names[s] for s in sorted({e["seed"]["slug"] for e in rows} & set(names))) + "."]},
        {"t": "details", "title": "Limits", "items": [
            "These are results on past prices. They say nothing about what a rule set will do next, and a check passed in the past is not a promise.",
            "The groups are each list's members on the day the test ran, so earlier years leave out companies that were dropped from a list before "
            "then, which can flatter older results.",
            "The passive return is the price return of the same instruments over the same dates. Dividends are not added in every market.",
            "One period per test: a different start date can change a result a lot, and a strategy that trades rarely is judged on few trades.",
            "Prices are the data sources' own and can differ from an exchange's final figures; coins, currency pairs and futures have no single official close."]},
        {"t": "p", "text": [{"a": "Open the strategy library", "href": "/library"}, " to read each rule set and its checks, or ",
                            {"a": "test your own idea on past prices", "href": "/new"}, "."]}]
    return {"slug": "classic-strategies-ten-markets-after-costs", "kind": "research", "market": None,
            "title": f"Classic strategies across {NUMBER_WORDS.get(len(live), len(live))} markets, after costs",
            "summary": f"{len(rows)} tests of {n_strats} classic rule sets on {len(live)} markets with costs applied: return against the passive return, "
                       f"the robustness checks, the costs used and the limits. Own backtests, {short(first)} to {short(last)}.",
            "blocks": blocks, "published_at": blog.now_iso(now)}


def blog_markets() -> set[str]:
    return set(MARKETS)


def short(day) -> str:
    return blog.short_day(day) if day else "–"


# ---------- (b) IPO listing day ----------
def ipo_facts(rows: list[dict], now: datetime | None = None) -> list[dict]:
    """The listed Indian issues of this year as plain facts, from the IPO tracker's rows: name, symbol, segment, listing day,
    issue price, the opening and closing change on the first day against the issue price (None where the tracker has none)
    and the subscription in times. A row of an issue that did not go ahead, a social stock exchange raise or one not yet
    listed is left out."""
    from . import ipo
    now = now or datetime.now(timezone.utc)
    year = str(now.astimezone(IST).year)
    out = []
    for r in rows:
        if r.get("market") != "IN" or ipo.stage_of(r, now) != "listed" or not str(r.get("listing") or "").startswith(year):
            continue
        perf = ipo.official_perf(r, r.get("perf"), now) or {}
        sub = (r.get("sub") or {}).get("times")
        # (a row no list named, kept from BSE's table of listed issues, has no segment: it is not called a main board issue, RC4-003)
        out.append({"name": r.get("name") or r.get("symbol") or "", "symbol": r.get("symbol"), "segment": r.get("segment") or None,
                    "listing": str(r["listing"])[:10], "issue_price": r.get("price") or perf.get("issue_price"),
                    "open_pct": perf.get("listing_change_pct"), "close_pct": perf.get("day_change_pct"),
                    "sub_times": sub if isinstance(sub, (int, float)) and sub > 0 else None})
    return sorted(out, key=lambda x: (x["listing"], x["name"]), reverse=True)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


SUB_BUCKETS = (("Under 10 times", 0, 10), ("10 to 50 times", 10, 50), ("Over 50 times", 50, 1e12))


def ipo_listing_day(facts: list[dict], now: datetime | None = None) -> dict | None:
    """The IPO post from `ipo_facts`: how many issues listed, how many have a listing-day close to count, how the close and
    the open compared with the issue price, by segment and by subscription, and every issue with its figures. None when no
    issue has data."""
    now = now or datetime.now(timezone.utc)
    year = now.astimezone(IST).year
    have = [f for f in facts if _num(f.get("close_pct"))]
    if not have:
        return None
    lack = len(facts) - len(have)
    up = [f for f in have if round(f["close_pct"], 2) > 0]
    down = [f for f in have if round(f["close_pct"], 2) < 0]
    flat = len(have) - len(up) - len(down)
    opens = [f["open_pct"] for f in have if _num(f.get("open_pct"))]
    closes = [f["close_pct"] for f in have]
    days = sorted(f["listing"] for f in facts)
    first, last = days[0], days[-1]
    seg = []
    for key, label in (("mainboard", "Main board"), ("sme", "SME"), (None, "Segment not recorded")):
        part = [f for f in have if f["segment"] == key]
        if part:
            seg.append([label, str(len(part)), str(sum(1 for f in part if round(f["close_pct"], 2) > 0)),
                        str(sum(1 for f in part if round(f["close_pct"], 2) < 0)), p1(median(f["close_pct"] for f in part))])
    buckets = []
    for label, lo, hi in SUB_BUCKETS:
        part = [f for f in have if _num(f.get("sub_times")) and lo <= f["sub_times"] < hi]
        buckets.append([label, str(len(part)), p1(median(f["close_pct"] for f in part)) if part else "–",
                        str(sum(1 for f in part if round(f["close_pct"], 2) > 0)) if part else "–"])
    nosub = sum(1 for f in have if not _num(f.get("sub_times")))
    table = []
    for f in have[:IPO_ROWS_SHOWN]:
        href = blog.company_path("IN", f["symbol"]) if f.get("symbol") else None
        table.append([{"a": f["name"], "href": href} if href else f["name"], short(f["listing"]), f"₹{f['issue_price']:,.2f}" if _num(f.get("issue_price")) else "–",
                      p1(f["open_pct"]) if _num(f.get("open_pct")) else "–", p1(f["close_pct"]),
                      f"{f['sub_times']:,.1f} times" if _num(f.get("sub_times")) else "–"])
    blocks: list[dict] = [
        {"t": "p", "text": f"How Indian IPOs did on their first day of trading, for the issues in StratLab's IPO tracker that listed from {short(first)} to {short(last)}. "
                         "The change on listing day is the first session's close (or opening price) compared with the issue price."},
        {"t": "h2", "text": "What the data shows"},
        {"t": "stats", "items": [
            # LIVE4-019: each tile says which issues it counts (all listed, those with a listing-day close, those with an opening price)
            {"v": str(len(facts)), "l": "issue listed" if len(facts) == 1 else "issues listed", "s": f"all in the tracker, {short(first)} to {short(last)}"},
            {"v": f"{len(up)} of {len(have)}", "l": "closed above the issue price", "s": f"of the {len(have)} with a listing-day close"},
            {"v": p1(median(closes)), "l": "median listing-day close", "s": f"of the same {len(have)}, against the issue price"},
            *([{"v": p1(median(opens)), "l": "median listing-day open", "s": f"of the {len(opens)} with an opening price"}] if opens else [])]},
        ]
    # VR6-006: the tiles say the headline figures; the same four sentences were printed under them (a wall of text saying each number twice).
    # They stay in the page, folded, for a reader who wants them in words and for a crawler
    words = [
            f"{len(facts)} {'issue' if len(facts) == 1 else 'issues'} listed between {short(first)} and {short(last)}; {len(have)} "
            f"{'has' if len(have) == 1 else 'have'} a listing-day close in the tracker and {'is' if len(have) == 1 else 'are'} counted below. "
            f"{lack} {'lacks' if lack == 1 else 'lack'} it (the exchange's price tables have no trading figures for {'it' if lack == 1 else 'them'}) and {'is' if lack == 1 else 'are'} left out of every figure, "
            f"so the medians describe the {len(have)} counted, not all {len(facts)}.",
            f"On listing day {len(up)} closed above the issue price, {len(down)} below it and {flat} at it.",
            f"The middle issue (median) closed {p1(median(closes))} from its issue price; the lowest was {p1(min(closes))} and the highest {p1(max(closes))}.",
            (f"Opening price against the issue price: median {p1(median(opens))} across the {len(opens)} issues with an opening price." if opens
             else "No issue has an opening price in the tracker."),
    ]
    if len(seg) > 1:                                        # one row would only repeat the sentence above it (LIVE2-008)
        blocks += [{"t": "h2", "text": "By segment"},
                   {"t": "table", "caption": "Listing-day close against the issue price, by segment",
                    "head": ["Segment", "Issues counted", "Closed above issue price", "Closed below", "Median change"], "rows": seg,
                    "align": "lrrrr"}]
    if any(b[1] != "0" for b in buckets):
        blocks += [{"t": "h2", "text": "By subscription"},
                   {"t": "p", "text": "Subscription is the number of times the shares offered were applied for, over the whole bidding period. "
                                      "Small groups say little: read the count in the second column before the median." + (f" {nosub} counted {'issue has' if nosub == 1 else 'issues have'} no subscription figure and {'is' if nosub == 1 else 'are'} not in this table." if nosub else "")},
                   {"t": "hbar", "caption": "Median listing-day close against the issue price, by subscription",
                    "rows": [{"label": f"{b[0]} ({b[1]} {'issue' if b[1] == '1' else 'issues'})", "value": median(f["close_pct"] for f in have if _num(f.get("sub_times")) and lo <= f["sub_times"] < hi) if b[1] != "0" else None,
                              "text": b[2] if b[1] != "0" else "none"} for b, (_, lo, hi) in zip(buckets, SUB_BUCKETS)]},
                   {"t": "table", "caption": "Listing-day close against the issue price, by subscription",
                    "head": ["Subscribed", "Issues", "Median change", "Closed above issue price"], "rows": buckets,
                    "align": "lrrr"}]
    # LIVE2-005: the issue-by-issue list is a fold (as each market of the classic post is): open, its 50 rows were most of the
    # post's 11,555 px on a phone, every row a card; the figures above stay in view
    shown = min(IPO_ROWS_SHOWN, len(have))
    blocks += [{"t": "fold", "title": "Every issue counted", "note": f"{shown} of {len(have)} issues" if len(have) > shown else f"{len(have)} issues", "blocks": [
                   {"t": "p", "text": f"Newest listing first{f'; the latest {IPO_ROWS_SHOWN} of {len(have)} are shown, and every figure above counts all {len(have)}' if len(have) > IPO_ROWS_SHOWN else ''}."},
                   {"t": "table", "caption": f"IPO listing day in India, {year}: Open and Close are the first day's price against the issue price",
                    "head": ["Issue", "Listed", "Issue price", "Open", "Close", "Subscribed"], "rows": table, "align": "lrrrrr", "widths": [38, 13, 12, 11, 11, 15],
                    "page": IPO_PHONE_PAGE}]},
               {"t": "details", "title": "The headline figures in words", "items": words, "words": True},
               {"t": "details", "title": "How this was worked out", "items": [
                   "Data: the exchanges' public-issue pages (issue price, dates, bids received) and the exchanges' daily prices after listing. The tracker is "
                   "read every morning and evening.",
                   "Listing-day close against the issue price is (close ÷ issue price − 1) × 100 on the issue's first trading day. The opening price is the first "
                   "session's opening price. The final subscription is the total times subscribed.",
                   "Counted: issues the tracker shows as listed in " + str(year) + " that have a first-day close. An issue without one is counted in the number "
                   "listed and nowhere else."]},
               {"t": "details", "title": "Limits", "items": [
                   "The tracker keeps an issue for a limited time after its listing, so this post covers the issues it holds, not every issue of the year. "
                   f"The first listing it holds is {short(first)}.",
                   "One day is a short window: what an issue did on later days is not in these figures.",
                   "Main board and SME issues differ in size and trading rules" + ("; the segment table keeps them apart" if len(seg) > 1 else "; this post's issues are all in one segment") + (
                       ", and an issue whose segment the tracker did not record has a line of its own." if any(f["segment"] is None for f in have) else "."),
                   "Only official numbers are used: no grey market premium, which is not an official figure.",
                   "This is a record of what happened, not a view on any issue and not a pointer to the next one."]},
               {"t": "p", "text": [{"a": "See the IPO tracker", "href": "/invest/ipos"}, " for open and upcoming issues, or ", {"a": "read about any listed company", "href": "/stocks"}, "."]}]
    return {"slug": f"ipo-listing-day-india-{year}-so-far", "kind": "research", "market": "IN", "title": f"IPO listing day in India since {short(first)}",
            "summary": f"{len(have)} Indian IPOs that listed between {short(first)} and {short(last)}: first-day close and open against the issue price, by segment and "
                       f"subscription." + (f" {lack} {'issue lacks' if lack == 1 else 'issues lack'} price data and {'is' if lack == 1 else 'are'} not counted." if lack else ""),
            "blocks": blocks, "published_at": blog.now_iso(now)}


# ---------- (c) SIP vs lump sum ----------
def sip_vs_lump(closes: dict[str, float], now: datetime | None = None, amount: int = SIP_AMOUNT) -> dict | None:
    """The SIP-or-lump-sum post from an index's daily closes {day: close}: the SIP test engine's own simulation of a monthly
    SIP and of the same money put in on the SIP's first day, with the charges of buying units of an index fund, over the
    latest window and, for each horizon, from every start month the history allows. None with under four years of history."""
    from . import sip_test as S
    days = sorted(closes)
    if len(days) < 400:
        return None
    first_day, last_day = days[0], days[-1]
    # (the first close is the first session on or after the day the history was asked from, up to a week later: 10 years less 4 days
    # of closes are ten years, not nine, RC4-004)
    years = min(10, int(((date.fromisoformat(last_day) - date.fromisoformat(first_day)).days + 10) // 365.25))
    if years < 4:
        return None
    # units are a hundredth of the index, so a month's instalment buys whole units (the index itself is worth more than an instalment)
    units = {d: closes[d] / 100.0 for d in days}
    leg = {"symbol": "NIFTY 50", "weight": 1.0, "closes": units, "days": days, "high": {}, "kind": "in_etf"}
    plan = {"mode": "amount", "amount": amount, "qty": 1, "freq": "monthly", "dom": 1, "weekday": 0, "step_up": 0.0, "rule": "plain",
            "dip": 0.1, "extra": 0.5, "brokerage": 0.0, "lookback": 252}
    start = S._add_years(last_day, -years)
    start = next((d for d in days if d >= start), first_day)
    head = S.simulate([leg], plan, start, last_day)
    if not head:
        return None
    lump = S._once([leg], {**plan, "amount": head["invested"]}, head["start"], last_day)
    if not lump:
        return None
    rows = []
    for h in SIP_HORIZONS:
        starts = [m for m in S._months(first_day, last_day) if m >= first_day and S._add_years(m, h) <= last_day]
        res = []
        for s in starts:
            e = S._add_years(s, h)
            a = S.simulate([leg], plan, s, e, keep=False)
            if not a or a.get("xirr") is None:
                continue
            b = S._once([leg], {**plan, "amount": a["invested"]}, a["start"], e)
            if b and b.get("xirr") is not None:
                res.append((a, b))
        if len(res) >= 2:
            sx, lx = sorted(a["xirr"] for a, _ in res), sorted(b["xirr"] for _, b in res)
            ahead = sum(1 for a, b in res if a["value"] > b["value"])
            rows.append({"years": h, "windows": len(res), "sip_ahead": ahead, "lump_ahead": sum(1 for a, b in res if b["value"] > a["value"]),
                         "sip_median": median(sx), "lump_median": median(lx), "sip_low": sx[0], "lump_low": lx[0],
                         "from": res[0][0]["start"], "to": res[-1][0]["end"]})
    if not rows:
        return None
    inr = lambda v: kit.inr(v, 0)       # noqa: E731
    x = lambda v: p1(v * 100) if v is not None else "–"       # noqa: E731
    now = now or datetime.now(timezone.utc)
    table = [["Money put in", inr(head["invested"]), inr(lump["invested"])],
             ["Value at the end", inr(head["value"]), inr(lump["value"])],
             ["Gain", inr(head["gain"]), inr(lump["gain"])],
             ["Annual return (XIRR)", x(head["xirr"]), x(lump["xirr"])],
             ["Deepest fall of the index's price (the same for both)", p1(head["deepest_fall_pct"]), p1(lump["deepest_fall_pct"])],
             ["Charges paid", inr(head["charges"]), inr(lump["charges"])]]
    spread = [[f"{r['years']} years", str(r["windows"]), str(r["sip_ahead"]), str(r["lump_ahead"]), x(r["sip_median"]), x(r["lump_median"]),
               x(r["sip_low"]), x(r["lump_low"])] for r in rows]
    blocks: list[dict] = [
        {"t": "p", "text": f"A monthly SIP of {inr(amount)} on the NIFTY 50 against putting the same total in as a lump sum on the SIP's first day, on the index's own "
                          f"price history from {short(first_day)} to {short(last_day)}, with the charges of purchasing units."},
        {"t": "h2", "text": f"The latest {years} years: {short(head['start'])} to {short(head['end'])}"},
        {"t": "p", "text": f"The SIP bought on the first trading day of each of {head['instalments']} months. The lump sum is the SIP's whole total, "
                           f"{inr(head['invested'])}, put in on {short(head['start'])}."},
        {"t": "stats", "items": [
            {"v": inr(head["value"]), "l": "Monthly SIP: value at the end", "s": f"{inr(head['invested'])} put in"},
            {"v": inr(lump["value"]), "l": "Lump sum: value at the end", "s": f"{inr(lump['invested'])} put in"},
            {"v": x(head["xirr"]), "l": "Monthly SIP: annual return", "s": "XIRR"},
            {"v": x(lump["xirr"]), "l": "Lump sum: annual return", "s": "XIRR"}]},
        {"t": "hbar", "caption": f"Money put in and value at the end, {short(head['start'])} to {short(head['end'])}",
         "rows": [{"label": "Money put in (each)", "value": head["invested"], "text": inr(head["invested"])},
                  {"label": "Monthly SIP: value at the end", "value": head["value"], "text": inr(head["value"])},
                  {"label": "Lump sum: value at the end", "value": lump["value"], "text": inr(lump["value"])}]},
        {"t": "table", "caption": f"SIP and lump sum on the NIFTY 50, {short(head['start'])} to {short(head['end'])}", "head": ["", "Monthly SIP", "Lump sum"], "rows": table,
         "align": "lrr"},
        {"t": "h2", "text": "From every start month"},
        {"t": "p", "text": "The same comparison for every start month the history allows: the SIP runs for the horizon, and the lump sum is that SIP's total put in on its "
                           "first day. 'Ahead' counts the windows in which one ended with the higher value. Windows that start a month apart overlap almost "
                           "entirely, so they are not independent results."},
        {"t": "bars", "caption": "Start months in which each ended with the higher value", "series": ["SIP ahead", "Lump sum ahead", "Level"],
         "rows": [{"label": f"{r['years']} years", "values": [r["sip_ahead"], r["lump_ahead"], r["windows"] - r["sip_ahead"] - r["lump_ahead"]]} for r in rows]},
        {"t": "table", "caption": "SIP against lump sum across start months. Ahead counts windows; median and lowest are annual returns (XIRR)",
         "head": ["Horizon", "Windows", "SIP ahead", "Lump ahead", "SIP median", "Lump median", "SIP lowest", "Lump lowest"], "rows": spread,
         "align": "lrrrrrrr", "widths": [12, 12, 12, 13, 13, 13, 12, 13]},
        {"t": "p", "text": " ".join(f"Over {r['years']}-year horizons the lump sum ended ahead in {r['lump_ahead']} of {r['windows']} windows and the SIP in {r['sip_ahead']}."
                                    for r in rows)},
        {"t": "details", "title": "How the comparison was run", "items": [
            "Data: the NIFTY 50's daily closes from exchange data, as the app holds them. The index is a price index, so dividends are not included.",
            f"Each instalment of {inr(amount)} is invested at that day's close in whole units, each worth a hundredth of the index level; what a whole unit "
            "can't use waits for the next instalment. The lump sum is invested the same way on its day.",
            "Charges are those of purchasing exchange-traded fund units in India: no STT on units, exchange and SEBI fees with GST, and stamp duty on the purchase. "
            "Brokerage is set to zero, since it differs by broker. No sale is made, so no charges on a sale and no tax are counted.",
            "The annual return is the XIRR of the dated payments in and the value at the end. The deepest fall is the largest drop of the units' price from a high "
            "(the pot's value with the instalments taken out), so it is the same number for the SIP and the lump sum: both own the same units through the same "
            "prices. What differs is how much money was in the pot when the fall came, which the SIP's instalments built up over the years.",
            "Charges are a share of each purchase (no flat fee, brokerage set to zero), so the same total put in costs the same whether it goes in at once or in "
            "instalments."]},
        {"t": "details", "title": "Limits", "items": [
            "The index can't be bought as such: this models units that follow it exactly, with no fund expense ratio and no tracking difference.",
            f"The history is {years} years at most and one market; a different period or market can give another answer. The windows overlap, so the counts above are "
            "not a probability of anything.",
            "A lump sum is invested for longer than the SIP's average rupee, so its result depends on whether prices rose over the period; the tables record what "
            "happened in this history, not what happens next.",
            "Nothing here is a suggestion to start, change or stop a SIP."]},
        {"t": "p", "text": [{"a": "Test a SIP on any Indian stock or ETF", "href": "/invest"}, " with the same engine, or read the ", {"a": "company pages", "href": "/stocks"}, "."]}]
    return {"slug": "sip-vs-lump-sum-nifty-50", "kind": "research", "market": "IN", "title": "SIP vs lump sum on the NIFTY 50: what the history shows",
            "summary": f"A monthly {inr(amount)} SIP against the same money as a lump sum on day one, on NIFTY 50 history from {short(first_day)} to {short(last_day)}, "
                       f"with charges. Results for the latest {years} years and for every start month over {' and '.join(str(h) for h in SIP_HORIZONS)}-year horizons.",
            "blocks": blocks, "published_at": blog.now_iso(now)}


# ---------- reading the app's sources ----------
def library_entries() -> list[dict]:
    from . import library
    return library.public_entries()


def ipo_rows() -> list[dict]:
    from . import ipo
    return ipo.load("IN")["rows"]


def index_closes(days: int = 3650) -> dict[str, float]:
    """The NIFTY 50's daily closes {day: close} from the app's market data."""
    from . import main, sip_test
    bars = main.research_hub.yahoo.chart("^NSEI", "1d", days, ttl=300)["candles"]
    return sip_test.closes_from(bars)[0]


def source_posts() -> tuple:
    """(name, builder(now)) of each research post, every builder reading the app's own source."""
    return (("classic strategies", lambda now: classic_strategies(library_entries(), now)),
            ("IPO listing day", lambda now: ipo_listing_day(ipo_facts(ipo_rows(), now), now)),
            ("SIP vs lump sum", lambda now: sip_vs_lump(index_closes(), now)))


POSTS = source_posts()


def generate(now: datetime | None = None, builders=None) -> dict:
    """Write the research posts from the app's data now: one after another, a failure in one leaves the others. Returns
    {"at", "made": [{"post", "slug", "result"}], "problems": [...]} (the result is "new", "updated" or "same", or "nothing to
    say" when the data has too little). The run is recorded for Admin."""
    from . import memguard
    now = now or datetime.now(timezone.utc)
    out = {"at": blog.now_iso(now), "made": [], "problems": []}
    if not _lock.acquire(blocking=False):
        return {**out, "problems": ["A run is already going."]}
    try:
        with memguard.heavy("blog-research", force_release=True):
            for name, build in (builders or POSTS):
                try:
                    post = build(now)
                    if not post:
                        out["made"].append({"post": name, "slug": None, "result": "nothing to say"})
                        continue
                    bad = advice_words(post)
                    if bad:
                        out["problems"].append(f"{name}: left out, it has the word {bad!r}")
                        continue
                    out["made"].append({"post": name, "slug": post["slug"], "result": blog.upsert_research(post, now)})
                except Exception as e:
                    out["problems"].append(f"{name}: {type(e).__name__}: {str(e)[:160]}")
                    print("blog research:", name, type(e).__name__, str(e)[:160])
            if builders is None:                    # the committed theme posts first (blog2), then every theme post again from its kept figures (R11)
                made, problems = seed_theme_posts(now)
                out["made"] += made
                out["problems"] += problems
                made, problems = rewrite_theme_posts(now)
                out["made"] += made
                out["problems"] += problems
    finally:
        _lock.release()
    try:
        db.set_setting(STATE_KEY, json.dumps(out))
    except Exception as e:
        print("blog research: couldn't keep the run:", str(e)[:120])
    return out


def advice_words(post: dict) -> str | None:
    """The first word in a post that turns a fact into advice or a forecast (the newsletters' list, plus 'should'), or None."""
    import re
    from .newsletter import write
    text = f"{post.get('title')} {post.get('summary')} {blog.plain_text(post.get('blocks') or [])}"
    m = write._BANNED.search(text) or re.search(r"\bshould\b|\bbest stock|\bguarantee", text, re.I)
    return m.group(0) if m else None


def last_run() -> dict:
    return db.json_value(db.get_setting(STATE_KEY), {})


def due(now: datetime) -> str | None:
    """The month ("2026-11") whose research run is due now, or None: from the third day of a month, once for each month
    (the month is marked when a run starts, so a failed run is asked for again from Admin, not every few minutes)."""
    local = now.astimezone(IST)
    month = f"{local.year}-{local.month:02d}"
    if local.day < RESEARCH_DAY or db.get_setting(MONTH_KEY) == month:
        return None
    return month


def run_monthly(now: datetime | None = None) -> dict | None:
    """The monthly run, if one is due: marks the month, then generates."""
    now = now or datetime.now(timezone.utc)
    month = due(now)
    if not month:
        return None
    db.set_setting(MONTH_KEY, month)
    return generate(now)


# ---------- (d) a theme's margin by layer (THEME-1) ----------
THEME_PREFIX = "theme-"
LIST_GROUP = "Named in the theme's list"         # theme_base.with_base's group of the theme's own list that no layer took
_MOVE = re.compile(r"^(?P<layer>.+?): the EBITDA margin of its (?P<n>\d+) companies together went from (?P<a>[−\-]?[\d.]+)% in (?P<fy>.+?) to "
                   r"(?P<b>[−\-]?[\d.]+)% in (?P<ty>.+?), a move of")


def theme_stamp() -> list:
    """The versions a theme post's figures were worked out under: the membership rules (which company sits in which layer), the dive's
    own sentences and the sector figures' rules, the parts of a stored dive's key that say how its figures were made (theme_routes.dive_key).
    Kept in the post's figures (src "stamp"): a post whose stamp is not today's was worked out under older rules (lane upd1)."""
    from .intel import sector_metrics, theme_base, theme_data
    return [theme_base.RULES, theme_data.DIVE_TEXT, sector_metrics.VERSION]


def stale_figures(src: dict | None) -> bool:
    """Whether a theme post's kept figures were worked out under older rules than today's (a post kept before the stamp was, too)."""
    return isinstance(src, dict) and src.get("stamp") != theme_stamp()


THEME_SRC_V = 2                         # 2: the deck's own counts, coverage and comparison kept with each layer (blog2); 1: before
# the figures a layer's row keeps, each with how many companies it is the median of (the deck's columns: theme deck "The value chain by layer")
ROW_FIGS = ("ebitda", "net", "roce", "roe", "nii_assets", "gnpa", "pb")
QUOTE_MAX = 180                         # a company's own words beside its name, cut on a word


def _row_shown(dive: dict) -> tuple[list[dict], list[dict]]:
    """(the layers the deck's value chain shows, the companies of the theme's industries no layer takes) as the theme's deck picks them
    (deck.py, "The value chain by layer"): a layer with at least one confirmed company; an official industry's leftover group is a list in the
    deck's appendix, not a row, when the map has two layers of its own or more."""
    layers = dive.get("layers") or []
    shown = [x for x in layers if any(c.get("status") != "unverified" for c in x.get("companies") or [])]
    own = [x for x in shown if not x.get("official")]
    unplaced = [x for x in shown if x.get("official") and not x.get("by_industry") and x.get("basis") != "rest"] if len(own) >= 2 else []
    return [x for x in shown if x not in unplaced], unplaced


def _period(cos: list[dict]) -> dict | None:
    """The year most of a theme's companies' latest full year ends in, with how many: {"year": "Mar 2026", "n": 95, "of": 102}."""
    from collections import Counter
    years = Counter(str(c.get("year")) for c in cos if c.get("year"))
    if not years:
        return None
    year, n = years.most_common(1)[0]
    return {"year": year, "n": n, "of": sum(years.values())}


_NEWSY = re.compile(r"^\w+\s?-\s|\b(?:collaborat\w*|announc\w*|partners? with|signs?|signed|bags?|wins?|won|order worth|press release)\b", re.I)
_BROKEN = re.compile(r"^[^.]{0,40}:\s|\d…?$|\s-\s.*\s-\s")      # "Market Leadership: - 3rd ... - 5% ... and 5", "Business Segments Q2 FY27: a) ..."
_HEADING = re.compile(r"\s(?:[A-Z][\w&]*\s){1,3}[\w ]{0,20}:\s")
_FIRST = re.compile(r"^(.+?[.!?])(?:\s|$)")


def _layer_words(b: dict) -> str:
    """The first sentence of a layer's description (the map's, written by AI): what its companies do, without the lines on what sets their
    margin."""
    from .share import public_words
    text = public_words(b.get("description"), 400)
    m = _FIRST.match(text)
    first = (m.group(1) if m else text).strip()
    from .newsletter import write
    return first if 20 <= len(first) <= 300 and not first.endswith("…") and not write.banned(first) else ""


def _company(c: dict) -> dict:
    """A company as a theme post keeps it: its name and symbol, its own words about its work (the advice filter applied), its place in its
    layer's figures and what its membership rests on."""
    from .newsletter import write
    from .share import public_words
    what = public_words(c.get("what"), QUOTE_MAX) if c.get("what") else ""
    head = _HEADING.search(what)                    # "... banking services Key Ratios Q3 FY26: CRAR: 17.19% ...": the words before a heading
    if head and head.start() >= 30:
        what = what[:head.start()].rstrip(" ,;")
    if len(what) < 30 or _NEWSY.search(what) or _BROKEN.search(what) or what.count("(") != what.count(")"):
        what = ""                                   # a news line, a heading or a line cut mid-figure is no description of its work
    calc = c.get("calc") or {}
    return {"symbol": c.get("symbol"), "name": c.get("name") or c.get("symbol"), "what": "" if write.banned(what) else what,
            "evidence": c.get("evidence") or (c.get("theme") or {}).get("evidence"), "unverified": c.get("status") == "unverified",
            "out": "" if calc.get("in", True) else str(calc.get("why") or "")[:80], "year": c.get("year")}


def theme_source(dive: dict, theme: str, region: str) -> dict:
    """The figures a theme post is written from, kept in the post's row (body.src) so a later version of the words is written again from
    them, with no AI read and no map that may have expired. blog2 (R59 posts): what the theme's deck shows, by the deck's own rules: the
    value chain's rows (each layer's companies in its calculations "of" those it lists, each median with how many companies it is of), the
    chain's own comparison (its line, the layers it ranks and those it shows without ranking), the theme's counts (in the theme, core members
    with figures, adjacent participants), the years the figures are of, each layer's companies with their own words, and the basis."""
    from .deck import is_lender_set, population
    from .intel import theme_data as td
    layers, unplaced = _row_shown(dive)
    by = {x.get("layer"): x for x in layers}
    chain = dive.get("chain") or {}
    rows = []
    for r in chain.get("rows") or []:
        blk = by.get(r.get("layer"))
        if not blk or not r.get("n"):
            continue
        rows.append({"layer": r["layer"], "n": r["n"], "listed": r.get("listed") or len(blk.get("companies") or []), "revenue": r.get("revenue"),
                     **{k: r.get(k) for k in ROW_FIGS}, **{f"{k}_n": r.get(f"{k}_n") or 0 for k in ROW_FIGS},
                     "official": bool(r.get("official") or blk.get("official")), "basis": blk.get("basis"), "adjacent": bool(r.get("adjacent") or blk.get("adjacent")),
                     "scale": r.get("scale"), "words": _layer_words(blk),
                     "companies": [_company(c) for c in blk.get("companies") or [] if c.get("symbol")][:120]})
    adj = {x.get("symbol") for x in dive.get("adjacent") or [] if x.get("symbol")}
    seen: set = set()
    cos = [c for x in layers for c in x.get("companies") or [] if c.get("status") != "unverified" and not (c.get("revenue") is None and c.get("profit") is None)
           and c.get("symbol") not in adj and not c.get("adjacent") and not (c.get("symbol") in seen or seen.add(c.get("symbol")))]      # deck.population's core
    lender = is_lender_set([c for x in layers for c in x.get("companies") or []])
    checks = dive.get("checks") or {}
    p = dive.get("placements") or {}
    pop = population(dive)
    listed = len({c.get("symbol") for x in layers for c in x.get("companies") or [] if c.get("symbol")})
    figs = dive.get("figures") or {}
    # e81 (LIVE17A-005: the Semiconductors post "104 listed US companies ... 9 layers" beside its page's "102 companies in 10 layers"): the
    # theme's count as its public page and its /themes card say it (public_themes.counts, from the stored read and this dive)
    page_counts = None
    try:
        from . import public_themes
        from .intel import theme_library
        nm = theme_library.normalise(theme, region) or theme
        ent = next((x for x in public_themes.entries(region) if x["name"] == nm), None)
        pl = public_themes.payload(ent) if ent else None
        page_counts = public_themes.counts(pl, dive) if pl else None
    except Exception:
        page_counts = None
    return {"v": THEME_SRC_V, "theme": theme, "region": region, "sector": dive.get("sector") or theme, "unit": dive.get("unit"),
            "basis": dive.get("basis") or "", "rows": rows, "notable": [n for n in dive.get("notable") or [] if n.get("kind") == "move"],
            "members": dive.get("members") if dive.get("members") is not None else pop["core"], "adjacent_n": pop["adjacent"],
            "total": (page_counts or {}).get("all") or p.get("total") or listed, "listed": listed,
            **({"page_counts": {k: page_counts[k] for k in ("listed", "layers", "all")}} if page_counts else {}), "window": {"shown": figs.get("shown"), "of": figs.get("of")} if figs.get("of") else None,
            "unplaced": sum(1 for x in unplaced for c in x.get("companies") or [] if c.get("status") != "unverified"),
            "chain": {k: chain.get(k) for k in ("line", "highest", "lowest", "measure", "compared", "unranked")},
            "lender": lender, "whole": td.mostly_whole(checks.get("whole_points"), checks.get("with_ebitda")),
            "period": _period(cos), "as_of": dive.get("as_of"), "page": theme_page_path(theme, region),
            "stamp": theme_stamp(), "read_on": datetime.now(timezone.utc).date().isoformat(),
            # r64e (LIVE11A-020: "read of the theme on 17 Nov 2026" for a map made 7 Nov): the day the theme's map was made, said beside
            **({"map_on": datetime.fromtimestamp(float(dive["map_at"]), timezone.utc).date().isoformat()}
               if isinstance(dive.get("map_at"), (int, float)) and dive["map_at"] > 0 else {})}


def _page_counts(theme: str, region: str) -> dict | None:
    """e81: the theme's count as its public page's dive keeps it (public_themes.stored_counts), or None."""
    try:
        from . import public_themes
        from .intel import theme_library
        nm = theme_library.normalise(theme, region) or theme
        ent = next((x for x in public_themes.entries(region) if x["name"] == nm), None)
        pl = public_themes.payload(ent) if ent else None
        return public_themes.stored_counts(region, nm, pl) if pl else None
    except Exception:
        return None


def theme_page_path(theme: str, region: str) -> str:
    """The theme's public page (/themes/in/it-service): the library keeps a theme under its normalised name (theme_library.normalise)."""
    from . import public_themes
    from .intel import theme_library
    try:
        name = theme_library.normalise(theme, region) or theme
    except Exception:
        name = theme
    return public_themes.page_path(region, name)        # the page's own address (LIVE9A-029) when the theme is stored


def app_theme_path(theme: str, region: str) -> str:
    """The theme in the app, where its deck is made (a sign-in; decks on Basic and Pro)."""
    from urllib.parse import quote
    return f"/research/themes?q={quote(str(theme or ''))}&region={region}"


def figures_moved(old: dict | None, new: dict) -> bool:
    """Whether a theme post's kept figures differ from the theme's live read (LIVE7A-017: the public Cybersecurity post said 14 companies in 5
    layers, "Identity and access has one company", while its theme page had 16 and two in identity): another set of layers, companies or
    layer figures, how many companies a figure is of, or the chain's comparison; a post kept before the deck's counts were (blog2) takes them.
    The day of the read alone is no difference."""
    if not isinstance(old, dict):
        return False
    if (old.get("v") or 1) != (new.get("v") or 1):
        return True
    shape = lambda src: [(r.get("layer"), r.get("n"), r.get("listed"), r.get("revenue"), tuple((r.get(k), r.get(f"{k}_n")) for k in ROW_FIGS),      # noqa: E731
                          sorted(c.get("symbol") or "" for c in r.get("companies") or [])) for r in src.get("rows") or []]
    return (shape(old) != shape(new) or old.get("members") != new.get("members") or old.get("total") != new.get("total")
            or (old.get("chain") or {}) != (new.get("chain") or {}))


def _num_cell(v) -> float | None:
    """A figure of a stored table cell ("21,632", "+13.5%", "−9.1%", "–") as a number, or None."""
    t = str(v or "").replace(",", "").replace("%", "").replace("+", "").replace("−", "-").strip()
    try:
        return float(t)
    except ValueError:
        return None


def theme_source_from_blocks(post: dict) -> dict | None:
    """The figures of a theme post written before its figures were kept (GEN 3 and before), read back from its own table and sentences, so
    the post already live is written again in the new form. None when its table can't be read."""
    blocks = (post.get("body") or {}).get("blocks") or post.get("blocks") or []
    table = next((x for x in blocks if x.get("t") == "table" and (x.get("head") or [""])[0] == "Layer"), None)
    if not table:
        return None
    m = re.match(r"^theme-(.+)-margins-([a-z]{2})$", str(post.get("slug") or ""))
    region = (post.get("market") or (m.group(2).upper() if m else "IN"))
    rows = []
    for r in table.get("rows") or []:
        cells = [c if isinstance(c, str) else blog.plain_text([{"t": "p", "text": c}]) for c in r]
        if len(cells) < 6:
            continue
        n = int(_num_cell(cells[1]) or 0)
        e = _num_cell(cells[3])
        rows.append({"layer": cells[0], "n": n, "revenue": _num_cell(cells[2]), "ebitda": e, "net": _num_cell(cells[4]), "roce": _num_cell(cells[5]),
                     "ebitda_n": n if e is not None else 0, "official": cells[0] == LIST_GROUP, "basis": "list" if cells[0] == LIST_GROUP else None, "companies": []})
    if len(rows) < 2:
        return None
    first = next((x for x in blocks if x.get("t") == "p"), {})
    members = re.match(r"^(\d+) listed companies", str(first.get("text") or ""))
    moves = []
    for x in blocks:
        for item in x.get("items") or [] if x.get("t") == "ul" else []:
            mv = _MOVE.match(item if isinstance(item, str) else "")
            if mv:
                fa, fb = float(mv["a"].replace("−", "-")), float(mv["b"].replace("−", "-"))
                moves.append({"kind": "move", "layer": mv["layer"], "n": int(mv["n"]), "from": fa, "to": fb, "from_year": mv["fy"], "to_year": mv["ty"],
                              "move": round(fb - fa, 1)})
    how = next((x for x in blocks if x.get("t") == "details"), {})
    basis = next((i for i in how.get("items") or [] if isinstance(i, str) and i.startswith("Each company's")), "")
    cap = str(table.get("caption") or "")
    unit = re.search(r"revenue in (.+?),", cap)
    return {"v": 1, "theme": (m.group(1).replace("-", " ") if m else ""), "region": region, "sector": str(post.get("title") or "").split(":")[0].strip(),
            "members": int(members.group(1)) if members else sum(r["n"] for r in rows), "unit": unit.group(1) if unit else None,
            "basis": basis.replace("latest full latest fiscal year", "latest full fiscal year"), "rows": rows, "notable": moves}


def _lower_first(s: str) -> str:
    """"Cybersecurity" in a sentence is "cybersecurity"; "AI data centers" keeps its capitals."""
    return s[:1].lower() + s[1:] if len(s) > 1 and s[1:2].islower() else s


def _day(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)[:10]).strftime("%-d %b %Y")
    except ValueError:
        return ""


def theme_measure(src: dict) -> str:
    """The figure a theme post compares its layers on: the one its chain compared them on, else return on equity for a theme of lenders
    (deck: lenders' measures) and EBITDA margin for any other."""
    chain = src.get("chain") or {}
    if chain.get("highest") and chain.get("measure"):
        return chain["measure"]
    return "roe" if src.get("lender") else "ebitda"


def half_up_pc(v, whole: bool = False) -> str:
    """LIVE10A-019: a margin in the post's table and chart rounded as its sentences are (theme_data.f1: a half up), so 18.25 is 18.3% in
    both (the text said "Semiconductor equipment 18.3%" over a chart and table of 18.2%); a figure that rounds to zero has no sign."""
    from .intel.theme_data import f1
    if v is None:
        return "–"
    text = f1(abs(float(v)))
    neg = float(v) < 0 and float(text) != 0
    out = f"{'−' if neg else ''}{text}%"
    return out.replace(".0%", "%") if whole else out


def _cells(src: dict):
    """(format of each figure, the value chain table's (head, rows)) as the theme's deck writes them (deck.py "The value chain by layer"):
    each median with its base, none under 3 companies; a layer's companies "of" those it lists; revenue its companies added together."""
    from .deck import _medn, _times, _whole_rows, adjacent_label, companies_cell, drop_empty
    from .deepdive import money
    whole, unit = bool(src.get("whole")), src.get("unit") or ("₹ crore" if (src.get("region") or "IN") == "IN" else "$ million")
    fmt = {"ebitda": lambda x: half_up_pc(x, whole), "pb": _times}
    lend = src.get("lender") or theme_measure(src) == "roe"
    cols = [("n", "Companies"), ("revenue", "Revenue"), ("ebitda", "EBITDA margin"), ("net", "Net margin"), ("roce", "ROCE")]
    if lend:
        cols += [("roe", "ROE"), ("nii_assets", "NII / assets"), ("gnpa", "Gross NPA"), ("pb", "P/B")]

    def cell(r, k):
        if k == "n":
            return companies_cell(r["n"], r.get("listed"))
        if k == "revenue":
            return "–" if r.get("revenue") is None else money(r["revenue"], unit)
        return _medn(None, r["n"], fmt.get(k, half_up_pc), n=r.get(f"{k}_n"), value=r.get(k))
    v2 = (src.get("v") or 1) >= 2
    rows = [[adjacent_label(r["layer"], r.get("adjacent"))] + [cell(r, k) for k, _ in cols] for r in src.get("rows") or [] if r.get("n") and (v2 or not r.get("official"))]
    head, rows, _, _ = drop_empty(["Layer"] + [h for _, h in cols], rows, [1] * (len(cols) + 1))
    return fmt, head, _whole_rows(rows)          # each column at one precision, as every slide is (deck.whole_deck)


def theme_post_from(src: dict, now: datetime | None = None) -> dict:
    """The theme post from its kept figures (theme_source), by the theme deck's own rules (blog2, the owner, 16 Nov: "keep posting blog of the
    9+ decks"): what it covers with the day of the read and the years its figures are of; the headline counts as tiles; what the figures
    show in the chain's own words (the layers it ranks, those it shows without ranking and why); each layer's median by the deck's floor as a
    chart; every layer's figures in the deck's table, each median with the companies it is of; who is in each layer, each company with its
    own words; links to the theme's page and its deck; the method."""
    from .deck import adjacent_label, bar_marks, compare_note, decimal_units, whole_figures, ADJACENT_NOTE, COMPANIES_NOTE
    from .intel import theme_data as td
    now = now or datetime.now(timezone.utc)
    region = src.get("region") or "IN"
    sector = src.get("sector") or src.get("theme") or "Theme"
    v2 = (src.get("v") or 1) >= 2
    rows = [r for r in src.get("rows") or [] if r.get("n") and (v2 or not r.get("official"))]      # a kept post of before: its layers only
    chain = src.get("chain") or {}
    key = theme_measure(src)
    what = "return on equity" if key == "roe" else "EBITDA margin"
    fmt, head, table = _cells(src)
    shown = [r for r in rows if r.get(key) is not None and (r.get(f"{key}_n") or 0) >= td.MIN_BASE]
    keep = decimal_units(*[fmt.get(key, half_up_pc)(r[key]) for r in shown])          # the post's medians at one precision, as a deck's chart is
    f = lambda v: whole_figures(fmt.get(key, half_up_pc)(v), keep)          # noqa: E731
    total = src.get("total") or src.get("members") or len({c["symbol"] for r in rows for c in r.get("companies") or []})
    members = src.get("members") if src.get("members") is not None else total
    where = {"IN": "Indian", "US": "US"}.get(region, "")
    named = _lower_first(sector) + ("" if sector.lower().endswith("theme") else " theme")
    # e81 (LIVE17A-005): the theme's layers as its page counts them; the layers with figures said apart when fewer. A post kept before its
    # source held them reads them where its page's are kept (public_themes.stored_counts)
    pc = src.get("page_counts") or _page_counts(src.get("theme") or sector, region)
    if pc and pc.get("all"):
        total = int(pc["all"])
    n_layers = int((pc or {}).get("layers") or len(rows))
    intro = (f"{total:,} listed {where + ' ' if where else ''}compan{'y is' if total == 1 else 'ies are'} in the {named}; StratLab's map sorts them into "
             f"{n_layers} {'layer' if n_layers == 1 else 'layers'} of its value chain by what each company's own description says it does. "
             f"The figures below are of its {members:,} core member{'' if members == 1 else 's'} with figures"
             + (f", in the {len(rows)} {'layer' if len(rows) == 1 else 'layers'} that have them" if len(rows) < n_layers else ""))
    if src.get("adjacent_n"):
        intro += f"; {src['adjacent_n']:,} adjacent participant{' is' if src['adjacent_n'] == 1 else 's are'} shown apart, in no theme figure"
    intro += "."
    per = src.get("period") or {}
    if per.get("year"):
        intro += (f" Each company's figures are from its latest full-year accounts: the year to {per['year']} for {per['n']:,} of the {per['of']:,}."
                  if per.get("n") != per.get("of") else f" Each company's figures are from its latest full-year accounts, the year to {per['year']}.")
    else:
        intro += " Every figure is from the companies' latest full-year accounts."
    if src.get("read_on"):           # LIVE7A-017: the day of the read, so a post is never taken for the theme's page of another day
        day = _day(src["read_on"])
        if day:
            made = _day(src["map_on"]) if src.get("map_on") else ""
            intro += ((f" Worked out on {day} from StratLab's map of the theme made {made}" if made and made != day else
                       f" Worked out from StratLab's read of the theme on {day}")
                      + (f", prices as of {_day(src['as_of'])}" if src.get("as_of") and _day(src["as_of"]) else "")
                      + "; its companies and figures change as the theme is read again.")
    by = {r["layer"]: r for r in rows}
    hi, lo = by.get(chain.get("highest") or ""), by.get(chain.get("lowest") or "")
    lines = []
    if chain.get("line"):
        lines.append(whole_figures(chain["line"]))  # the deck's own sentence on its value chain, word for word, as its slides print it
    if not chain.get("highest"):
        if shown and not chain.get("line"):
            lines.append(f"Median {what} by layer, each on {td.MIN_BASE} companies or more: "
                         + "; ".join(f"{adjacent_label(r['layer'], r.get('adjacent'))} {f(r[key])}" for r in shown) + ".")
        if v2:
            lines.append(compare_note(chain, key))
    names = {r["layer"] for r in rows}
    for n in src.get("notable") or []:
        if n.get("kind") == "move" and n.get("layer") in names:
            # LIVE4-018: this is the layer's companies added together, not its median company (the chart's and the table's): said first, so
            # "−6.2%" here beside "−9.1%" in the chart reads as two different measures, not a contradiction
            lines.append(f"{n['layer']}: combined EBITDA margin (its {n['n']} companies' figures added together, not the median in the chart) "
                         f"{'up' if n['move'] > 0 else 'down'} {td.f1(abs(n['move']))} points, from {td.pts(n['from'])} in {n['from_year']} to {td.pts(n['to'])} in {n['to_year']}.")
    if src.get("unplaced"):
        k = src["unplaced"]
        lines.append(f"{k:,} more {'company' if k == 1 else 'companies'} of the theme's industries {'is' if k == 1 else 'are'} in no layer of the map; "
                     f"{'it counts' if k == 1 else 'they count'} in the theme's counts, not in any layer's row.")
    tiles = [{"v": f"{total:,}", "l": "companies", "s": "in the theme"}, {"v": f"{members:,}", "l": "with figures", "s": "core members, every figure is of these"},
             {"v": str(len(rows)), "l": "layers", "s": "of its value chain"}]
    if hi and lo:
        tiles = tiles[:2] + [{"v": f(hi[key]), "l": f"highest median {'ROE' if key == 'roe' else 'margin'}", "s": hi["layer"]},
                  {"v": f(lo[key]), "l": f"lowest median {'ROE' if key == 'roe' else 'margin'}", "s": lo["layer"]}]
    notes = [f"Each bar is a layer's median company, latest full year, with the companies it is of in its label; a layer is drawn on a median of "
             f"{td.MIN_BASE} companies or more, and every layer is in the table below."]
    if any(r.get("adjacent") for r in rows):
        notes.append(ADJACENT_NOTE)
    blocks: list[dict] = [{"t": "p", "text": intro}, {"t": "stats", "items": tiles}, {"t": "h2", "text": "What the figures show"},
                          {"t": "ul", "items": lines or [f"{len(rows)} layers; the table below has every figure."]}]
    if len(shown) >= 2:
        labels = bar_marks(chain, shown, key)[0] if v2 else [r["layer"] for r in shown]
        blocks += [{"t": "h2", "text": f"Median {what} by layer"},
                   {"t": "hbar", "caption": f"Median {what} of each layer's companies, latest full year",
                    "rows": [{"label": lab, "value": r[key], "text": f(r[key])} for lab, r in zip(labels, shown)],
                    "note": " ".join(notes)}]
    caption = "Revenue: each layer's companies added together; margins and returns: its median company, with the companies it is of where fewer than the layer's"
    blocks += [{"t": "h2", "text": "Every layer in figures"},
               {"t": "table", "caption": caption, "head": head, "rows": table, "align": "l" + "r" * (len(head) - 1), "names": True}]
    foot = [f"A median is shown for {td.MIN_BASE} companies or more; “– (2)” is a figure two companies have, “(3 of 5)” a median of 3 of the layer's 5."]
    if v2 and any((r.get("listed") or 0) > r["n"] for r in rows):
        foot.append(COMPANIES_NOTE.replace(" (who and why: the layer's page)", " (who and why: the layer's list below)"))
    blocks.append({"t": "note", "text": " ".join(foot)})
    who = [r for r in rows if r.get("companies")]
    if who:
        blocks.append({"t": "h2", "text": "Who is in each layer, in its own words"})
        win = src.get("window") or {}
        blocks.append({"t": "p", "text": (f"Figures are worked out for {win['shown']:,} of the theme's {win['of']:,} companies: every one the map names, then the "
                                          "largest of the rest. Those companies by layer, each with its own description of its work:")
                       if win.get("shown") and win.get("of") and win["shown"] < win["of"] else "Every company by layer, each with its own description of its work:"})
        for r in who:
            items = []
            for c in r["companies"]:
                h = blog.company_path(region, c["symbol"]) if c.get("symbol") else None
                name = {"a": c["name"], "href": h} if h else c["name"]
                if c.get("unverified"):
                    tail = ": membership not checked yet; listed, in no figure"
                elif c.get("what"):
                    tail = f": “{c['what']}”"
                elif c.get("evidence") in ("industry_code_supported", "list_supported"):
                    tail = ": " + ("in the theme on its official industry" if c["evidence"] == "industry_code_supported" else "in the theme on the theme's own list")
                else:
                    tail = ""
                if c.get("out") and not c.get("unverified"):
                    tail += f" (not in the layer's figures: {c['out']})"
                items.append([name, tail] if tail else [name])
            label = adjacent_label(r["layer"], r.get("adjacent"))
            inner = ([{"t": "p", "text": f"The map's description (written by AI): {r['words']}"}] if r.get("words") else []) + [{"t": "ul", "items": items}]
            blocks.append({"t": "fold", "title": label[:80], "note": f"{len(r['companies'])} {'company' if len(r['companies']) == 1 else 'companies'}",
                           "blocks": inner})
    page, app = src.get("page") or theme_page_path(src.get("theme") or sector, region), app_theme_path(src.get("theme") or sector, region)
    blocks += [
        {"t": "h2", "text": "The theme and its deck"},
        {"t": "p", "text": ["Every company in the theme by layer, with what each one's place rests on: the ", {"a": f"{sector} theme page", "href": page},
                            ". The full theme, with every company's figures, the tailwinds and risks with their sources and the slide deck these figures "
                            "are from, is ", {"a": "the theme in StratLab", "href": app}, " (a sign-in; decks on Basic and Pro, a sample deck on ",
                            {"a": "the plans page", "href": "/plans"}, ")."]},
        {"t": "details", "title": "How these figures were worked out", "items": [x for x in [
            src.get("basis") or "",
            "A layer's margins and returns are its median company's (the middle one), so one very large or very small company doesn't set it; "
            "its revenue is its companies' added together. A company that runs other businesses too is left out of its layer's median, since its "
            "figures are the whole company's.",
            "A change over three years adds the same companies' figures together in each year (their operating profit over their revenue), so it "
            "can differ from the median in the table." if any(n.get("kind") == "move" for n in src.get("notable") or []) else "",
            "Facts and arithmetic only: nothing here says what to do with a share."] if x]},
        {"t": "p", "text": ["Read about any listed company on its ", {"a": "company page", "href": "/stocks"}, "."]},
    ]
    title = f"{sector}: where the {'return on equity' if key == 'roe' else 'margin'} sits along the chain"
    summary = (td.finding_first(lines[0]) if lines and chain.get("line") else intro)      # r66e (LIVE12A-009): the finding first
    return {"slug": f"{THEME_PREFIX}{td.slug(src.get('theme') or sector)}-margins-{region.lower()}", "kind": "research",
            "market": region if region in ("IN", "US") else None, "title": title, "summary": summary[:380], "blocks": blocks,
            "published_at": blog.now_iso(now), "indexable": True, "published": False, "day": blog.now_iso(now)[:10], "src": src}


# a news headline is not a theme (LIVE6-003: "Auto names among top movers" was made a theme post): the words of a market report, a
# question or an exclamation, a figure with a percent, or more words than a theme's name has
_HEADLINE = re.compile(r"\b(?:among|amid|after|top (?:movers|gainers|losers)|gainers|losers|surges?|surged|rall(?:y|ies|ied)|jumps?|jumped|"
                       r"slumps?|slumped|plunges?|plunged|soars?|soared|tumbles?|tumbled|falls?|fell|rises?|rose|gains|gained|hits?|record high|"
                       r"why|says?|said|today|yesterday|this week)\b|[?!%\"“”:]", re.I)
THEME_WORDS = 6
THEME_MIN_LAYERS = 2                 # layers with a margin a theme post needs: its chart and its sentences are about them


def headline_like(name: str) -> bool:
    # blog2: a name's own description in brackets is no headline ("Utilities (Indian power, gas and water-linked infrastructure)")
    n = re.sub(r"\s*\([^()]*\)\s*$", "", str(name or "").strip())
    return bool(n) and (len(n.split()) > THEME_WORDS or bool(_HEADLINE.search(n)))


def theme_problem(src: dict) -> str | None:
    """Why a theme post can't stand (LIVE6-003: two posts said "sorted into 0 layers" over an empty "Margin by layer" chart), or None:
    fewer than THEME_MIN_LAYERS layers with a median of the figure it compares on (theme_measure) of the deck's floor of companies
    (theme_data.MIN_BASE, blog2: the decks show no median of fewer), or a headline for the theme's name."""
    from .intel import theme_data as td
    key, v2 = theme_measure(src), (src.get("v") or 1) >= 2
    layers = [r for r in src.get("rows") or [] if (v2 or not r.get("official")) and r.get(key) is not None
              and (r.get(f"{key}_n") if r.get(f"{key}_n") is not None else r.get("n") or 0) >= td.MIN_BASE]
    if len(layers) < THEME_MIN_LAYERS:
        return f"{len(layers)} {'layer' if len(layers) == 1 else 'layers'} with a margin"
    if headline_like(src.get("theme") or "") or headline_like(src.get("sector") or ""):
        return "its name is a headline, not a theme"
    return None


def _theme_twin(a: dict, b: dict) -> bool:
    """Two theme posts' figures of one theme: the same market and the same sector, or most of the same companies (four in five)."""
    if (a.get("region") or "IN") != (b.get("region") or "IN"):
        return False
    if str(a.get("sector") or "").strip().lower() and str(a.get("sector") or "").strip().lower() == str(b.get("sector") or "").strip().lower():
        return True
    ca = {c["symbol"] for r in a.get("rows") or [] for c in r.get("companies") or [] if c.get("symbol")}
    cb = {c["symbol"] for r in b.get("rows") or [] for c in r.get("companies") or [] if c.get("symbol")}
    return bool(ca and cb) and len(ca & cb) >= 0.8 * len(ca | cb)


def same_day_twin(post: dict, rows: list[dict] | None = None) -> str | None:
    """The slug of another theme post stored the same day for the same theme (one post per theme per day, LIVE6-003: a third automotive
    post the same day), or None."""
    day = str(post.get("day") or post.get("published_at") or "")[:10]
    try:
        rows = rows if rows is not None else blog.admin_rows(500)
    except Exception:
        return None
    for r in rows:
        slug = str(r.get("slug") or "")
        if not slug.startswith(THEME_PREFIX) or slug == post.get("slug") or str(r.get("published_at") or "")[:10] != day:
            continue
        other = (blog.get(slug) or {}).get("body") or {}
        if isinstance(other.get("src"), dict) and _theme_twin(post.get("src") or {}, other["src"]):
            return slug
    return None


def theme_post(dive: dict, theme: str, region: str, now: datetime | None = None, notable_only: bool = True, carry: bool = True) -> dict | None:
    """A DRAFT research post from a theme's deep dive (intel/theme_data.build) when the data shows something worth saying: one layer's
    EBITDA margin far from the others', or a layer whose margin moved a lot over three years. None when it shows nothing notable. The post is
    never published here: it is stored hidden, for the owner to read in Admin and publish by hand. Every figure is the dive's; the words only
    say what the table says. `notable_only=False` (the owner's button, and a theme read with no post yet: R15) makes it from any theme
    whose chain has two layers with a margin. `carry`: a stored post on this theme with figures from older rules takes these (carry_to_stored;
    the owner's button stores the post itself)."""
    notable = dive.get("notable") or []
    if notable_only and not notable:
        return None
    src = theme_source(dive, theme, region)
    if carry:
        carry_to_stored(theme_slug(src), src, now)
    if theme_problem(src):
        return None
    post = theme_post_from(src, now)
    return None if same_day_twin(post) else post


def theme_slug(src: dict) -> str:
    """A theme post's address from its figures (theme_post_from's)."""
    from .intel import theme_data as td
    return f"{THEME_PREFIX}{td.slug(src.get('theme') or src.get('sector') or 'Theme')}-margins-{(src.get('region') or 'IN').lower()}"


def _stored_src(old: dict | None) -> dict | None:
    if not old:
        return None
    src = (old.get("body") or {}).get("src") or old.get("src")
    return src if isinstance(src, dict) else theme_source_from_blocks(old)


def carry_to_stored(slug: str, src: dict, now: datetime | None = None) -> str | None:
    """A theme post already stored under this address whose figures were worked out under older rules (stale_figures) takes the figures of
    the dive just built (lane upd1: a stored post's figures were never worked out again, only re-worded from its old figures, so a post kept
    its old layers, e.g. a chip maker in an equipment layer, after the rules that placed it there were fixed). Its address, first date and
    whether it is published stay (blog.upsert_research); one the new figures can't stand up (theme_problem) is hidden, as
    rewrite_theme_posts hides one. Returns what was done, or None when nothing was."""
    try:
        old = blog.get(slug)
    except Exception as e:
        print("blog research: theme post not read:", slug, type(e).__name__, str(e)[:100])
        return None
    # LIVE7A-017: also when the live read's layers, companies or figures differ from the post's (a theme read again under the same rules)
    if not old or not (stale_figures(_stored_src(old)) or figures_moved(_stored_src(old), src)):
        return None
    try:
        if theme_problem(src):
            if old.get("published"):
                blog.set_published(slug, False, now)
            return "hidden"
        post = {**theme_post_from(src, now), "slug": slug, "published": bool(old.get("published"))}
        if advice_words(post):
            return None
        return blog.upsert_research(post, now)
    except Exception as e:
        print("blog research: theme post not brought up to date:", slug, type(e).__name__, str(e)[:100])
        return None


def draft_theme_post(dive: dict, theme: str, region: str, now: datetime | None = None, notable_only: bool = True) -> dict:
    """Store the theme's draft post (hidden) when its data is notable (or, with notable_only=False, has two layers with a margin):
    {"result": "new" | "updated" | "same" | "nothing notable" | "too few figures" | "left out", "slug"}."""
    post = theme_post(dive, theme, region, now, notable_only, carry=False)
    if not post:
        return {"result": "nothing notable" if notable_only else "too few figures", "slug": None}
    bad = advice_words(post)
    if bad:
        return {"result": "left out", "slug": None, "problem": f"it has the word {bad!r}"}
    return {"result": blog.upsert_research(post, now), "slug": post["slug"]}


def rewrite_theme_posts(now: datetime | None = None) -> tuple[list[dict], list[str]]:
    """Every stored theme post written again in the builders' current form (run with the research posts after a deploy that bumped GEN):
    from the figures kept in its row, or, for a post written before they were kept, from its own table and sentences. Its address, its first
    date and whether it is published stay (blog.upsert_research)."""
    made, problems = [], []
    rows = blog.admin_rows(500)
    kept: list[tuple[str, dict]] = []               # (day, figures) of the theme posts kept so far, oldest first
    for row in sorted(rows, key=lambda r: str(r.get("published_at") or "")):
        slug = str(row.get("slug") or "")
        if row.get("kind") != "research" or not slug.startswith(THEME_PREFIX):
            continue
        try:
            old = blog.get(slug) or {}
            src = (old.get("body") or {}).get("src") or theme_source_from_blocks(old)
            if not src:
                problems.append(f"{slug}: its figures couldn't be read")
                continue
            # LIVE6-003: a post with no layers to chart, a headline for a name, or a later twin of a theme posted the same day is hidden
            # (kept in the store, answering "not found"), never written again
            day = str(row.get("published_at") or "")[:10]
            why = theme_problem(src) or ("a second post on this theme the same day" if any(d == day and _theme_twin(src, o) for d, o in kept) else None)
            if why:
                if row.get("published"):
                    blog.set_published(slug, False, now)
                made.append({"post": "theme", "slug": slug, "result": "hidden"})
                problems.append(f"{slug}: hidden, {why}")
                continue
            kept.append((day, src))
            post = theme_post_from(src, now)
            post["slug"] = slug                     # the address it has, whatever the theme's words now make
            bad = advice_words(post)
            if bad:
                problems.append(f"{slug}: left out, it has the word {bad!r}")
                continue
            made.append({"post": "theme", "slug": slug, "result": blog.upsert_research(post, now)})
        except Exception as e:
            problems.append(f"{slug}: {type(e).__name__}: {str(e)[:160]}")
            print("blog research: theme post", slug, type(e).__name__, str(e)[:160])
    return made, problems


# ---------- theme posts that ship with a release (blog2) ----------
# The owner, 16 Nov: "keep posting blog of the 9+ decks". A theme post is published by committing its figures, read from the theme's live
# dive at the time, to blog_themes/<slug>.json (scripts/theme_post.py drafts and checks one); the release stores and publishes it at the
# first check after the deploy (seed_theme_posts). Nothing is written to the live site by hand, and the post then follows the theme's later
# reads like any theme post (carry_to_stored, refresh_theme_posts_if_due).
SEED_DIR = Path(__file__).with_name("blog_themes")
SEED_KEY = "blog:theme:seeded"          # {slug: read_on} of the committed theme posts already stored and published


def committed_theme_sources() -> list[dict]:
    """The committed theme posts' figures (blog_themes/*.json), each a theme_source of the theme's live read; a file that can't be read is
    left out and said."""
    out = []
    for p in sorted(SEED_DIR.glob("*.json")):
        try:
            src = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print("blog research: committed theme post not read:", p.name, type(e).__name__)
            continue
        if isinstance(src, dict) and src.get("rows"):
            out.append(src)
    return out


def seed_mark() -> tuple:
    """What the committed theme posts are, for the newsletter clock's "nothing new since the last look" (newsletter/job.blog_versions)."""
    return tuple((theme_slug(s), str(s.get("read_on") or "")) for s in committed_theme_sources())


def seed_theme_posts(now: datetime | None = None) -> tuple[list[dict], list[str]]:
    """Each committed theme post stored and published, once for each committed read (SEED_KEY), so a post hidden in Admin afterwards stays
    hidden: written from its committed figures, unless the store already holds this post from a later read in the same form (its figures
    kept); a post drafted hidden before is dated the day it goes up (blog.publish_now). A post its own checks fail is left out and said."""
    now = now or datetime.now(timezone.utc)
    made, problems = [], []
    try:
        done = db.json_value(db.get_setting(SEED_KEY), {}) or {}
    except Exception as e:
        return made, [f"committed theme posts: not read: {type(e).__name__}"]
    changed = False
    for src in committed_theme_sources():
        slug = theme_slug(src)
        if done.get(slug) == src.get("read_on"):
            continue
        try:
            old = blog.get(slug)
            kept = _stored_src(old)
            later = (isinstance(kept, dict) and (kept.get("v") or 1) >= THEME_SRC_V and kept.get("stamp") == src.get("stamp")
                     and str(kept.get("read_on") or "") > str(src.get("read_on") or ""))
            use = kept if later else src
            bad = theme_post_problems(use)
            if bad:
                problems.append(f"{slug}: not published, {bad[0]}")
                continue
            post = {**theme_post_from(use, now), "slug": slug, "published": True}
            res = blog.upsert_research(post, now)
            if old and not old.get("published"):
                blog.publish_now(slug, now)
                res = "published" if res == "same" else f"{res}, published"
            made.append({"post": "theme (committed)", "slug": slug, "result": res})
            done[slug] = src.get("read_on")
            changed = True
        except Exception as e:
            problems.append(f"{slug}: {type(e).__name__}: {str(e)[:160]}")
            print("blog research: committed theme post", slug, type(e).__name__, str(e)[:160])
    if changed:
        db.set_setting(SEED_KEY, json.dumps(done))
    return made, problems


_NUM = re.compile(r"(?<![\w.])[−\-+]?\d[\d,]*(?:\.\d+)?")


def _td_f1(v: float) -> str:
    from .intel.theme_data import f1
    try:
        return f1(v)
    except Exception:
        return ""


def _numbers_of(v, out: set) -> None:
    """Every number in a theme post's figures, as the texts it can be printed as (whole, one and two decimals, with and without its sign)."""
    if isinstance(v, bool) or v is None:
        return
    if isinstance(v, (int, float)):
        for x in (v, abs(v), v / 1000, abs(v) / 1000, v / 100000, abs(v) / 100000):
            for dp in (0, 1, 2):
                out.add(f"{x:.{dp}f}")
        out.add(_td_f1(abs(v)))           # LIVE10A-019: the half-up rounding the post's sentences and tables print (18.25 → 18.3)
        return
    if isinstance(v, dict):
        for x in v.values():
            _numbers_of(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _numbers_of(x, out)
    elif isinstance(v, str):
        for t in _NUM.findall(v):
            t = t.replace("−", "-").replace(",", "").lstrip("+-")
            out.update({t, t[:-2] if t.endswith(".0") else t})


def figures_not_in_source(src: dict, post: dict) -> list[str]:
    """blog2: every number a theme post prints (its words, tiles, charts and tables) that its kept figures (src) don't hold, once each: none
    for a post written from its figures. The deck's own fixed numbers (the floors of a median and a ranking) and the post's dates count as
    held. Company names and quoted words are left out (their digits are names, not figures)."""
    from .intel import theme_data as td
    held: set = set()
    _numbers_of({k: v for k, v in src.items() if k != "rows"}, held)
    for r in src.get("rows") or []:
        _numbers_of({k: v for k, v in r.items() if k != "companies"}, held)
        _numbers_of(r.get("layer"), held)
        _numbers_of(len(r.get("companies") or []), held)
    _numbers_of([td.MIN_BASE, td.HEADLINE_MIN, 3, 2, 1, 0], held)
    _numbers_of([post.get("published_at"), post.get("day")], held)
    texts: list[str] = [post.get("title") or "", post.get("summary") or ""]
    for b in post.get("blocks") or []:
        t = b.get("t")
        if t in ("p", "note", "h2", "h3") and isinstance(b.get("text"), str):
            texts.append(b["text"])
        elif t == "ul":
            texts += [i for i in b.get("items") or [] if isinstance(i, str)]
        elif t == "stats":
            texts += [f"{i.get('v')} {i.get('l')} {i.get('s')}" for i in b.get("items") or []]
        elif t == "hbar":
            texts += [f"{x.get('label')} {x.get('text')}" for x in b.get("rows") or []] + [b.get("caption") or ""]
        elif t == "table":
            texts += [" ".join(c for c in row if isinstance(c, str)) for row in b.get("rows") or []]
    out = []
    for text in texts:
        for tok in _NUM.findall(text):
            n = tok.replace("−", "-").replace(",", "").lstrip("+-")
            if n not in held and n.rstrip("0").rstrip(".") not in held and tok not in out:
                out.append(tok)
    return out


def theme_post_problems(src: dict, post: dict | None = None) -> list[str]:
    """What keeps a theme post off the site (scripts/theme_post.py and seed_theme_posts): too few layers to compare or a headline for a name
    (theme_problem), a word of advice, a data provider named, or a number its kept figures don't hold."""
    from .branding import public_text
    post = post or theme_post_from(src)
    out = []
    why = theme_problem(src)
    if why:
        out.append(why)
    bad = advice_words(post)
    if bad:
        out.append(f"it has the word {bad!r}")
    text = f"{post.get('title')} {post.get('summary')} {blog.plain_text(post.get('blocks') or [])}"
    if public_text(text) != text:
        out.append("it names a data provider")
    stray = figures_not_in_source(src, post)
    if stray:
        out.append("figures its source doesn't hold: " + ", ".join(stray[:8]))
    return out


THEME_REFRESH_RUN = 5                   # stale theme posts worked out again in one run (each a theme dive from stored pieces: no AI)
THEME_STAMP_KEY = "blog:theme:stamp"    # the theme_stamp() the stored theme posts were last brought up to date for


def library_dive(region: str, theme: str) -> dict | None:
    """A theme's dive from the theme library's read kept under today's rules (no AI asked, nothing read from a page), or None when the
    library holds no such read: the dive the theme's page would show, built from the stored company pieces."""
    from .intel import theme_library, theme_routes
    hit = theme_library.stored(region, theme)
    if hit is None:
        return None
    m = {**hit["payload"], "_library": hit["name"]}
    dive = theme_routes.dive_of(region, theme, theme_routes.with_descriptions(region, theme_routes.checked(region, theme, m)))
    return {**dive, "map_at": m.get("generated_at")} if isinstance(dive, dict) else dive      # r64e (LIVE11A-020): the map's day


def refresh_stale_theme_posts(now: datetime | None = None, limit: int = THEME_REFRESH_RUN, dive_for=None) -> dict:
    """The stored theme posts whose figures were worked out under older rules (stale_figures), worked out again from the theme's dive under
    today's rules (lane upd1: a rules or dive fix reached a theme post only when someone happened to open that theme). At most `limit` a
    run; a theme the library holds no current read of waits for its next read (carry_to_stored). {"made", "waiting", "problems"}."""
    from . import memguard
    now = now or datetime.now(timezone.utc)
    dive_for = dive_for or library_dive
    out: dict = {"made": [], "waiting": [], "problems": []}
    try:
        rows = blog.admin_rows(500)
    except Exception as e:
        out["problems"].append(f"posts not read: {type(e).__name__}")
        return out
    done = 0
    for row in rows:
        slug = str(row.get("slug") or "")
        if row.get("kind") != "research" or not slug.startswith(THEME_PREFIX):
            continue
        try:
            src = _stored_src(blog.get(slug))
            if not src or not stale_figures(src):
                continue
            if done >= limit:
                out["waiting"].append(slug)
                continue
            done += 1
            with memguard.heavy("blog-theme-refresh", force_release=True):
                dive = dive_for(src.get("region") or "IN", src.get("theme") or src.get("sector") or "")
            if not dive:
                out["waiting"].append(slug)
                continue
            res = carry_to_stored(slug, theme_source(dive, src.get("theme") or src.get("sector") or "", src.get("region") or "IN"), now)
            out["made"].append({"post": "theme", "slug": slug, "result": res or "same"})
        except Exception as e:
            out["problems"].append(f"{slug}: {type(e).__name__}: {str(e)[:160]}")
            print("blog research: stale theme post", slug, type(e).__name__, str(e)[:160])
    return out


def theme_posts_due() -> bool:
    """Whether the theme posts were last brought up to date for other rules than today's (theme_stamp)."""
    return db.json_value(db.get_setting(THEME_STAMP_KEY), []) != theme_stamp()


def refresh_theme_posts_if_due(now: datetime | None = None) -> dict | None:
    """After a deploy that changed the theme rules, the dive's sentences or the sector figures' rules: the stale theme posts worked out
    again (refresh_stale_theme_posts), and the stamp marked once none is left that a run can do (the rest wait for their theme's next
    read). None when nothing was due."""
    if not theme_posts_due():
        return None
    out = refresh_stale_theme_posts(now)
    if (not out["problems"] and not out["waiting"]) or not out["made"]:
        db.set_setting(THEME_STAMP_KEY, json.dumps(theme_stamp()))
    return out


def stale(now: datetime) -> bool:
    """Whether the posts were last written by an older version of the builders (or a run for this version failed and is due again:
    at most three tries, an hour apart)."""
    st = db.json_value(db.get_setting(GEN_KEY), {})
    if st.get("gen") != GEN:
        return True
    if st.get("ok") or int(st.get("tries") or 0) >= 3:
        return False
    try:
        return (now - datetime.fromisoformat(st["at"])).total_seconds() >= 3600
    except (KeyError, ValueError):
        return True


def run_if_stale(now: datetime | None = None) -> dict | None:
    """Write the research posts again when the builders changed since they were last written (a deploy), so a fix is on the live
    posts at the next check and not at the next month's run. Marked before it starts (a crash mid-run doesn't loop)."""
    now = now or datetime.now(timezone.utc)
    if not stale(now):
        return None
    st = db.json_value(db.get_setting(GEN_KEY), {})
    tries = int(st.get("tries") or 0) + 1 if st.get("gen") == GEN else 1
    db.set_setting(GEN_KEY, json.dumps({"gen": GEN, "ok": False, "tries": tries, "at": now.isoformat(timespec="seconds")}))
    out = generate(now)
    ok = not out["problems"]
    db.set_setting(GEN_KEY, json.dumps({"gen": GEN, "ok": ok, "tries": tries, "at": now.isoformat(timespec="seconds")}))
    return out
