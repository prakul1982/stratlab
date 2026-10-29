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
from datetime import date, datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

from . import blog, db, email_kit as kit

IST = ZoneInfo("Asia/Kolkata")
STATE_KEY = "blog:research:state"
MONTH_KEY = "blog:research:month"
GEN = 3                             # the version of what the builders write; bump it with a change to a post's words or tables and every post is written again at the next check after the deploy (LIVE2-029)
GEN_KEY = "blog:research:gen"       # {"gen", "ok", "tries", "at"} of the last run made for a version
SIP_AMOUNT = 10000
SIP_HORIZONS = (3, 5)
IPO_ROWS_SHOWN = 50
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
    risk, mrisk = library_seed.RISK, library_seed.MARKET_RISK
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
    for label, lo, hi in (("Under 10 times", 0, 10), ("10 to 50 times", 10, 50), ("Over 50 times", 50, 1e12)):
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
        {"t": "p", "text": f"How Indian IPOs did on their first day of trading in {year}, for the issues in StratLab's IPO tracker. The change on listing day is the "
                         "first session's close (or opening price) compared with the issue price."},
        {"t": "h2", "text": "What the data shows"},
        {"t": "stats", "items": [
            {"v": str(len(facts)), "l": "issue listed" if len(facts) == 1 else "issues listed", "s": f"{short(first)} to {short(last)}"},
            {"v": f"{len(up)} of {len(have)}", "l": "closed above the issue price", "s": "on listing day"},
            {"v": p1(median(closes)), "l": "median close against the issue price", "s": f"lowest {p1(min(closes))}, highest {p1(max(closes))}"},
            *([{"v": p1(median(opens)), "l": "median open against the issue price", "s": f"{len(opens)} {'issue' if len(opens) == 1 else 'issues'}"}] if opens else [])]},
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
                   {"t": "table", "caption": "Listing-day close against the issue price, by subscription",
                    "head": ["Subscribed", "Issues", "Median change", "Closed above issue price"], "rows": buckets,
                    "align": "lrrr"}]
    blocks += [{"t": "h2", "text": "Every issue counted"},
               {"t": "p", "text": f"Newest listing first{f'; the latest {IPO_ROWS_SHOWN} of {len(have)} are shown, and every figure above counts all {len(have)}' if len(have) > IPO_ROWS_SHOWN else ''}."},
               {"t": "table", "caption": f"IPO listing day in India, {year}: Open and Close are the first day's price against the issue price",
                "head": ["Issue", "Listed", "Issue price", "Open", "Close", "Subscribed"], "rows": table, "align": "lrrrrr", "widths": [38, 13, 12, 11, 11, 15]},
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
def theme_post(dive: dict, theme: str, region: str, now: datetime | None = None) -> dict | None:
    """A DRAFT research post from a theme's deep dive (intel/theme_data.build) when the data shows something worth saying: one layer's
    EBITDA margin far from the others', or a layer whose margin moved a lot over three years. None when it shows nothing notable. The post is
    never published here: it is stored hidden, for the owner to read in Admin and publish by hand. Every figure is the dive's; the words only
    say what the table says."""
    from .intel import theme_data
    notable = dive.get("notable") or []
    rows = [r for r in (dive.get("chain") or {}).get("rows") or [] if r.get("ebitda") is not None]
    if not notable or len(rows) < 2:
        return None
    now = now or datetime.now(timezone.utc)
    day = blog.now_iso(now)[:10]
    unit = dive.get("unit") or ("₹ crore" if region == "IN" else "$ million")
    title = f"{dive.get('sector') or theme}: where the margin sits along the chain"
    lines = []
    for n in notable:
        if n["kind"] == "gap":
            lines.append(f"The median EBITDA margin is {theme_data.pts(n['high_value'])} in {n['high']} and {theme_data.pts(n['low_value'])} in {n['low']}, "
                         f"a gap of {theme_data.f1(n['gap'])} points.")
        elif n["kind"] == "move":
            lines.append(f"{n['layer']}: the EBITDA margin of its {n['n']} companies together went from {theme_data.pts(n['from'])} in {n['from_year']} to "
                         f"{theme_data.pts(n['to'])} in {n['to_year']}, a move of {theme_data.f1(abs(n['move']))} points {'up' if n['move'] > 0 else 'down'}.")
    table = [[r["layer"], str(r["n"]), p1_plain(r["revenue"], unit), pts_or_dash(r["ebitda"]), pts_or_dash(r["net"]), pts_or_dash(r["roce"])] for r in dive["chain"]["rows"]]
    blocks = [
        {"t": "p", "text": f"{dive.get('members')} listed companies placed in {len(dive['layers'])} layers of the {dive.get('sector') or theme} value chain, each one only where its "
                           "own description shows it does that layer's work. The table gives each layer's median margins from the companies' latest full-year figures."},
        {"t": "h2", "text": "What the figures show"},
        {"t": "ul", "items": lines},
        {"t": "h2", "text": "The whole chain in one table"},
        {"t": "table", "caption": f"Median figures by layer (revenue in {unit}, combined)", "head": ["Layer", "Companies", "Revenue", "EBITDA margin", "Net margin", "ROCE"],
         "rows": table, "align": "lrrrrr"},
        {"t": "details", "title": "How these figures were worked out", "items": [
            dive.get("basis") or "", "A company that runs other businesses too is marked, and its company-wide figures are left out of its layer's median.",
            "Medians are of the companies with a figure; a layer's count says how many. Facts and arithmetic only: nothing here says what to do with a share."]},
    ]
    from .intel import theme_data as td
    return {"slug": f"theme-{td.slug(theme)}-margins-{region.lower()}", "kind": "research", "market": region if region in ("IN", "US") else None, "title": title,
            "summary": (lines[0] if lines else title)[:380], "blocks": blocks, "published_at": blog.now_iso(now), "indexable": True, "published": False, "day": day}


def p1_plain(v, unit: str) -> str:
    return "–" if v is None else f"{v:,.0f}"


def pts_or_dash(v) -> str:
    return "–" if v is None else p1(v)


def draft_theme_post(dive: dict, theme: str, region: str, now: datetime | None = None) -> dict:
    """Store the theme's draft post (hidden) when its data is notable: {"result": "new" | "updated" | "same" | "nothing notable" | "left out", "slug"}."""
    post = theme_post(dive, theme, region, now)
    if not post:
        return {"result": "nothing notable", "slug": None}
    bad = advice_words(post)
    if bad:
        return {"result": "left out", "slug": None, "problem": f"it has the word {bad!r}"}
    return {"result": blog.upsert_research(post, now), "slug": post["slug"]}


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
