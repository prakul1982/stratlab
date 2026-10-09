"""Round 6 visitor review of the live site: market values that can't be right (an ADR counted in ordinary shares, a
shell's stray trade, an ETN filed under its bank), prices a close or more behind and an Indian last trade called the
close, "same sector" lists that weren't what they said, library verdicts that claimed checks that weren't run, the
weekly email's paying count, email links on the API's own host, and the odd values on company pages."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import alerts, db, email_kit, email_previews, library, library_seed, main, money_advance_tax, screens, stock_pages, weekly
from app.config import settings
from app.engine import verdict
from tests import world

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def us(**kw) -> dict:
    """A US page's facts; market value in $ million."""
    base = {"region": "US", "symbol": "ACME", "name": "Acme Inc", "exchange": "Listed in the US", "industry": ["Manufacturing", "Widgets"],
            "currency": "USD", "unit": "$ million", "market_cap_unit": "$ million", "price": 50.0, "price_at": "2026-10-07",
            "high52": 60.0, "low52": 40.0, "market_cap": 50_000.0, "pe": 20.0, "div_yield": 1.0, "net_margin": 10.0, "opm": 20.0,
            "years": [{"year": "Dec 2025", "sales": 20_000.0, "profit": 2_000.0, "opm": 20.0, "debt": 100.0}], "growth": {},
            "filings": [], "built_at": "2026-10-08T05:00:00+00:00", "v": stock_pages.FACTS_VERSION, "sales_usd": 20_000.0}
    return {**base, **kw}


# ---------- R6V-001: market values checked before they are shown or ranked ----------
def test_a_bradesco_like_adr_has_no_45_trillion_market_cap():
    # $4.34 a share, 10.6 trillion "shares" from the filing: $45.9T, P/E 9,710, on revenue of about $55B
    bbd = us(symbol="BBD", price=4.34, market_cap=45_900_000.0, pe=9710.2, unit="BRL million", sales_usd=55_000.0,
             years=[{"year": "Dec 2025", "sales": 298_187.0, "profit": 23_673.0}])
    assert stock_pages.cap_problem(bbd)
    assert stock_pages.shown_cap(bbd) is None and stock_pages.shown_pe(bbd) is None and stock_pages.cap_text(bbd) == "–"
    page = stock_pages.render(bbd, "US", "BBD", None)
    assert "<span>Market cap</span><b>n/a</b>" in page and "<span>P/E</span><b>n/a</b>" in page and "data-cap-check" in page
    assert "45.90T" not in page and "9,710" not in page


def test_values_out_of_line_with_revenue_or_with_no_revenue_are_left_out():
    bsac = us(symbol="BSAC", price=31.64, market_cap=5_960_000.0, pe=5836.1, unit="CLP million", sales_usd=4_000.0)
    tv = us(symbol="TV", price=2.23, market_cap=703_500.0, pe=None, unit="MXN million", cap_unverified=True)
    aktx = us(symbol="AKTX", price=8.62, market_cap=1_340_000.0, pe=None, sales_usd=0.0, years=[])
    brrn = us(symbol="BRRN", price=2100.0, market_cap=945_000.0, pe=None, sales_usd=0.0, years=[])
    for f in (bsac, tv, aktx, brrn):
        assert stock_pages.cap_problem(f), f["symbol"]
    # a page stored before revenue was kept, reporting in another currency, with a P/E in the thousands
    old = us(symbol="BSAC", market_cap=5_960_000.0, pe=5836.1, unit="CLP million", years=[])
    old.pop("sales_usd")
    assert stock_pages.cap_problem(old)


def test_real_large_companies_keep_their_market_value():
    for f in (us(symbol="AAPL", market_cap=4_000_000.0, sales_usd=416_000.0, pe=35.0),
              us(symbol="TSM", market_cap=1_500_000.0, sales_usd=120_000.0, unit="TWD million", pe=25.0),
              us(symbol="PLTR", market_cap=450_000.0, sales_usd=4_500.0, pe=600.0),         # 100x sales, P/E 600
              us(symbol="BIO", market_cap=5_000.0, sales_usd=0.0, pe=None)):              # a $5B company before revenue
        assert stock_pages.cap_problem(f) is None, f["symbol"]
        assert stock_pages.shown_cap(f) == f["market_cap"]
    india = {"region": "IN", "currency": "INR", "market_cap": 250_000.0, "pe": 1500.0}        # a big Indian company, tiny profit
    assert stock_pages.shown_cap(india) == 250_000.0 and stock_pages.shown_pe(india) is None   # P/E above 1,000: n/a


def test_negative_and_huge_pe_are_na():
    assert stock_pages.shown_pe(us(pe=-12.0)) is None and stock_pages.shown_pe(us(pe=1000.5)) is None
    assert stock_pages.shown_pe(us(pe=999.0)) == 999.0


def test_an_etn_filed_under_its_bank_is_not_a_company(w):
    gldi = us(symbol="GLDI", name="CREDIT SUISSE AG", market_cap=611_600.0, div_yield=27.47, not_company="an exchange-traded product (an ETF or ETN)")
    page = stock_pages.render(gldi, "US", "GLDI", None)
    assert "GLDI is an exchange-traded product" in page and "noindex" in page and "611" not in page
    assert screens.row("US", "GLDI", gldi) is None


def test_the_largest_lists_rank_only_checked_values(w):
    rows = [{"symbol": "BBD", "name": "Bank Bradesco", "market_cap": 45_900_000.0, "cap_checked": True},     # stale index row
            {"symbol": "NVDA", "name": "NVIDIA", "market_cap": 4_900_000.0, "cap_checked": True},
            {"symbol": "AAPL", "name": "Apple", "market_cap": 4_000_000.0, "cap_checked": True},
            {"symbol": "TV", "name": "Grupo Televisa", "market_cap": 703_500.0}]                             # built before the checks
    db.set_setting(screens.INDEX_KEY + "US", json.dumps({"at": "2026-10-08", "rows": rows}))
    screens._mem.clear()
    for s in ("BBD", "NVDA", "AAPL", "TV"):
        stock_pages.companies("US").setdefault(s, {"name": s, "sym": s, "bse": None})
    big, ranked = stock_pages.largest("US")
    assert ranked and [s for s, _ in big][:2] == ["NVDA", "AAPL"] and "BBD" not in dict(big) and "TV" not in dict(big)
    page = stock_pages.index_page(None)
    assert "US: the largest companies" in page and "passed StratLab" in page


def test_the_index_row_carries_the_checked_value():
    bad = us(symbol="BBD", market_cap=45_900_000.0, pe=9710.2, sales_usd=55_000.0)
    r = screens.row("US", "BBD", bad)
    assert r["market_cap"] is None and r["pe"] is None and r["cap_checked"] is True
    good = screens.row("US", "AAPL", us(market_cap=4_000_000.0, sales_usd=416_000.0))
    assert good["market_cap"] == 4_000_000.0


def test_bradescos_thousandfold_share_count_is_checked_against_an_earlier_years_eps():
    """Its filings tag 10.6 trillion shares (a thousand times too many) and no EPS for the last two years: the count the
    latest year with both profit and EPS implies is used (tests/fixtures/sec_live/bbd.json.gz: trimmed SEC data)."""
    import gzip
    from app.intel import sec
    with gzip.open(ROOT / "backend" / "tests" / "fixtures" / "sec_live" / "bbd.json.gz", "rt") as fh:
        d = json.load(fh)
    p = sec.build(d["facts"], d["subs"], symbol="BBD")
    assert 10e9 < p["shares"] < 12e9
    r = sec.ratios(sec.with_ads({**p, "fx": {"rate": 0.18}}, 1), 4.34)
    assert 40_000 < r["Market Cap"] < 60_000 and 5 < r["Stock P/E"] < 20           # about $49B, not $45.9T


COVER_HEAD = ("ANNUAL REPORT PURSUANT TO SECTION 12(b) OR (g) OF THE SECURITIES EXCHANGE ACT OF 1934 OR ANNUAL REPORT PURSUANT TO "
              "SECTION 13 OR 15(d) For the fiscal year ended December 31, 2025 Commission file number: 001-00000 " + "x " * 200)


def test_the_depositary_ratio_is_read_as_the_cover_writes_it():
    from app.intel.sec import ads_ratio
    # Ecopetrol writes "Depository": its ADSs of 20 shares were counted as single shares ($696 billion)
    ec = COVER_HEAD + ("Securities registered or to be registered pursuant to Section 12(b) of the Act. Title of each class Trading "
                       "Symbol(s) American Depository Shares (as evidenced by American Depository Receipts), each representing 20 "
                       "common shares par value COP 609 per share EC New York Stock Exchange. Table of contents")
    assert ads_ratio(ec) == {"ratio": 20.0, "ads": True}
    # Banco Santander-Chile: a "Table of contents" page link sits above the list of registered securities
    bsac = COVER_HEAD + ("Table of contents Securities registered or to be registered pursuant to Section 12(b) of the Act: Title of "
                         "each class American Depositary Shares (“ADS”), each representing the right to receive 400 Shares of "
                         "Common Stock without par value BSAC New York Stock Exchange. " + "y " * 300 + "TABLE OF CONTENTS Item 1")
    assert ads_ratio(bsac) == {"ratio": 400.0, "ads": True}
    plain = COVER_HEAD + "Securities registered pursuant to Section 12(b) of the Act: Ordinary Shares AZN New York Stock Exchange. Table of contents"
    assert ads_ratio(plain) == {"ratio": None, "ads": False}


def test_a_us_page_build_stores_what_the_value_is_checked_against():
    p = {"currency": "MXN", "fx": {"rate": 0.054}, "share_note": "The US-listed shares are American depositary shares (ADSs), and how many ...",
         "pl": {"cols": ["Dec 2024"], "rows": {"Sales": [62_260.0]}}, "cashflow": {"cols": ["Dec 2024"], "rows": {"Dividends paid": [-1_000.0]}}}
    got = main.us_cap_checks(p, "TV")
    assert got == {"sales_usd": round(62_260.0 * 0.054, 2), "cap_unverified": True, "divs_paid": True}
    assert main.us_cap_checks({"currency": "USD", "pl": {"cols": [], "rows": {}}}, "AKTX") == {"sales_usd": 0.0}
    # a foreign company's annual report that couldn't be read this time: its value isn't taken on trust
    assert main.us_cap_checks({"currency": "EUR", "fx": {"rate": 1.1}, "ads_unread": True}, "ASML")["cap_unverified"] is True


def test_an_unread_annual_report_is_said_not_taken_as_no_depositary_shares(monkeypatch):
    from app.intel.sec import SEC
    s = SEC()
    monkeypatch.setattr(s.limit, "take", lambda *a, **k: False)               # the filing source's ration is spent
    subs = {"cik": 1444406, "filings": {"recent": {"form": ["20-F"], "accessionNumber": ["0001-26-000001"], "primaryDocument": ["ec.htm"]}}}
    got = s.ads(subs)
    assert got["unread"] is True and got["ads"] is None and got["ratio"] is None


# ---------- R6V-002: no stale or intraday price called a close; every page follows each close ----------
def test_a_price_older_than_the_last_close_is_called_last_price(monkeypatch):
    now = datetime(2026, 10, 8, 23, 0, tzinfo=timezone.utc)       # 8 Oct's US close settled; India's too
    monkeypatch.setattr(stock_pages, "last_close", lambda region, n=None: (datetime(2026, 10, 8).date(), now))
    f = us(price_at="2026-10-06")
    assert stock_pages.behind(f) and stock_pages.price_label(f) == "Last price, 6 Oct 2026"
    page = stock_pages.render(f, "US", "ACME", None)
    assert "<span>Last price, 6 Oct 2026</span>" in page and "<span>Last close" not in page and "data-behind" in page and "6 Oct 2026 close" not in page
    current = us(price_at="2026-10-08")
    assert not stock_pages.behind(current) and stock_pages.price_label(current) == "Last close, 8 Oct 2026"


def test_india_takes_the_days_close_only_hours_after_the_bell():
    assert stock_pages.settle("IN") >= 3 * 3600 and stock_pages.settle("US") == stock_pages.SETTLE
    bars = [{"t": f"2026-10-0{d}T00:00:00+05:30", "o": 1, "h": 2, "l": 1, "c": float(d)} for d in (6, 7, 8)]
    at = lambda h, m: datetime(2026, 10, 8, h, m, tzinfo=IST)           # noqa: E731
    assert stock_pages.price_facts(bars, "IN", at(16, 20))["price_at"] == "2026-10-07"     # INFY's 1,001.85 "close"
    assert stock_pages.price_facts(bars, "IN", at(18, 31))["price_at"] == "2026-10-08"


def test_a_page_is_read_from_prices_fetched_after_the_close_settled(w, monkeypatch):
    seen = {}

    class Prov:
        def history(self, inst, tf, days, ttl=None):
            seen.update(tf=tf, ttl=ttl)
            return [{"t": "2026-10-07T00:00:00-04:00", "o": 1, "h": 1, "l": 1, "c": 1}]
    monkeypatch.setattr(main.universes, "resolve", lambda reg, region, members: (["US:ACME"], []))
    monkeypatch.setattr(main.markets, "resolve", lambda iid: (Prov(), {"token": "ACME"}))
    settled = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(stock_pages, "last_close", lambda region, n=None: (settled.date(), settled - timedelta(seconds=stock_pages.settle(region))))
    main.stock_page_bars("US", {"sym": "ACME", "bse": None})
    assert seen["tf"] == "1d" and 7000 <= seen["ttl"] <= 7300           # a cached copy only if it was read after the settle


def test_the_price_job_moves_stale_pages_to_the_new_close(w, monkeypatch):
    now = datetime.now(timezone.utc)
    day = now.date()
    iso = lambda back: (day - timedelta(days=back)).isoformat()          # noqa: E731
    monkeypatch.setattr(stock_pages, "last_close", lambda region, n=None: (day, now - timedelta(hours=3)))
    built = now.timestamp() - 5 * 3600                                    # the full build: before the latest close settled
    old = {"ts": built, "facts": us(symbol="NVDA", price=100.0, price_at=iso(2), market_cap=4_000_000.0, pe=50.0, div_yield=1.0, sales_usd=200_000.0)}
    small = {"ts": built, "facts": us(symbol="SMOL", price=10.0, price_at=iso(2), market_cap=100.0, sales_usd=50.0)}
    fresh_one = {"ts": built, "facts": us(symbol="AAPL", price_at=iso(0))}
    for s, v in (("NVDA", old), ("SMOL", small), ("AAPL", fresh_one), ("BROKE", {"ts": built, "facts": us(symbol="BROKE", price_at=iso(7))})):
        db.set_setting(f"stocks:page:US:{s}", json.dumps(v))
    order = []

    def bars_of(region, sym):
        order.append(sym)
        if sym == "BROKE":
            raise RuntimeError("no prices")
        return [{"t": iso(1) + "T00:00:00-04:00", "o": 1, "h": 112, "l": 95, "c": 105.0},
                {"t": iso(0) + "T00:00:00-04:00", "o": 1, "h": 125, "l": 100, "c": 110.0}]
    pages = stock_pages.Pages(lambda r, c: None)
    got = pages.refresh_prices("US", bars_of, lambda b: {"stage": 2, "stage_days": 3, "st_up": True, "st_days": 1}, gap=0, now=now)
    assert got == {"refreshed": 2, "left": 0, "failed": 1}
    assert order[0] == "NVDA" and "AAPL" not in order                  # the largest first; a current page isn't read again
    stored = json.loads(db.get_setting("stocks:page:US:NVDA"))
    f = stored["facts"]
    assert f["price"] == 110.0 and f["price_at"] == iso(0) and f["high52"] == 125
    assert f["market_cap"] == 4_400_000.0 and f["pe"] == 55.0 and f["div_yield"] == round(1.0 / 1.1, 2) and f["stage"] == 2
    assert stored["price_ts"] > 0 and stored["ts"] == built             # the reported numbers wait for the next full build
    assert stock_pages.fresh(stored, "US", now=now.timestamp())         # no rebuild needed for the price alone
    # every page read at this close: the next runs don't read storage or prices again until the next close
    calls = len(order)
    assert pages.refresh_prices("US", bars_of, gap=0, now=now) == {"refreshed": 0, "left": 0, "failed": 0} and len(order) == calls


def test_with_new_close_leaves_a_page_alone_without_a_newer_close():
    f = us(price_at="2026-10-08")
    assert stock_pages.with_new_close(f, [{"t": "2026-10-08T00:00:00-04:00", "o": 1, "h": 1, "l": 1, "c": 99.0}]) is f
    assert stock_pages.with_new_close(f, []) is f


def test_a_us_page_built_before_the_checks_is_rebuilt_when_opened():
    settled = stock_pages.last_close("US")[1].timestamp() + stock_pages.settle("US")
    old = {"ts": settled + 60, "facts": {**us(), "v": 1}}
    assert not stock_pages.fresh(old, "US", now=settled + 120)
    assert stock_pages.fresh({"ts": settled + 60, "facts": us()}, "US", now=settled + 120)


# ---------- R6V-003: related companies by checked size, in the real industry, with a true caption ----------
def test_same_industry_is_ranked_by_checked_value_and_says_which_industry(w):
    rows = [{"symbol": s, "name": n, "sector": "Manufacturing", "industry": ind, "market_cap": cap, "cap_checked": True}
            for s, n, ind, cap in (("DELL", "Dell", "Electronic Computers", 90_000), ("SMCI", "Super Micro", "Electronic Computers", 25_000),
                                   ("NVDA", "NVIDIA", "Semiconductors", 4_900_000), ("AKTX", "Akari", "Pharmaceuticals", None),
                                   ("HPQ", "HP Inc", "Electronic Computers", 30_000))]
    db.set_setting(screens.INDEX_KEY + "US", json.dumps({"at": "2026-10-08", "rows": rows}))
    screens._mem.clear()
    for r in rows:
        stock_pages.companies("US").setdefault(r["symbol"], {"name": r["name"], "sym": r["symbol"], "bse": None})
    secs = stock_pages.peer_sections("US", "AAPL", ["Manufacturing", "Electronic Computers"])
    assert secs[0]["title"] == "Same industry" and [s for s, _ in secs[0]["rows"]] == ["DELL", "HPQ", "SMCI"]
    assert "(Electronic Computers), by market value" in secs[0]["caption"]
    # fewer than four in the industry: the wider sector follows, under its own caption, never mixed into the first list
    assert secs[1]["title"] == "Same sector" and [s for s, _ in secs[1]["rows"]] == ["NVDA"] and "wider sector (Manufacturing)" in secs[1]["caption"]
    assert all(s != "AKTX" for sec in secs for s, _ in sec["rows"])        # no checked value, not ranked


# ---------- R6V-011, R6V-014, R6V-015: odd values, the range's name, search counts ----------
def test_tiny_numbers_never_read_minus_zero_and_tiny_values_read_under_a_million():
    assert stock_pages._fmt(-0.04, 0) == "-0.04" and stock_pages._fmt(-0.0001, 2) == "-0.0001" and stock_pages._fmt(0.0, 0) == "0"
    assert stock_pages._fmt(-0.00001, 2) == "0.00"
    assert stock_pages._fmt(-0.0, 1) == "0.0"
    assert stock_pages.cap_text(us(market_cap=0.3, sales_usd=0.1)) == "<$1M"


def test_a_page_with_no_price_says_so_instead_of_a_bare_as_of(w):
    page = stock_pages.render(us(price=None, price_at=None, high52=None, low52=None), "US", "LLPS", None)
    assert "No recent share price is available" in page and "Prices are closing prices" not in page


def test_a_zero_yield_beside_dividends_paid_is_na():
    assert stock_pages.shown_yield(us(div_yield=0.0, divs_paid=True)) is None
    assert stock_pages.shown_yield(us(div_yield=0.0)) == 0.0 and stock_pages.shown_yield(us(div_yield=3.4)) == 3.4


def test_the_year_range_says_it_is_intraday():
    labels = dict(stock_pages._stats(us()))
    assert "1-year range (intraday)" in labels and "1-year range" not in labels


def test_a_capped_search_says_first_n(w, monkeypatch):
    monkeypatch.setattr(stock_pages, "search", lambda r, q, n=30: [(f"A{i}", f"A{i}") for i in range(n)])
    page = stock_pages.index_page("US", "a")
    assert "the first 30 matches" in page and "30 matches" not in page.replace("the first 30 matches", "")
    monkeypatch.setattr(stock_pages, "search", lambda r, q, n=30: [("AAPL", "Apple")])
    assert "1 match for" in stock_pages.index_page("US", "apple")


# ---------- R6V-005: verdicts say what the checks showed, and the card and the page agree ----------
SEED = {"id": "seed-supertrend-us", "name": "Supertrend flip · 20 US large caps", "group": {"id": "us_mega", "name": "20 US large caps"},
        "verdict": {"verdict": "edge", "headline": "Likely a real edge.", "passed": 3, "total": 3,
                    "summary": "It made money after costs, kept working on unseen data, and doesn't depend on one exact setting."},
        "stats": {"ret": 55.83, "buy_hold": 172.93, "mdd": -13.7, "trades": 250, "unseen": 19.05}}


def test_a_stored_seed_is_restated_from_its_own_checks():
    v = library.restated(SEED)
    assert [c["status"] for c in v["checks"]] == ["pass", "skip", "pass", "pass"]           # nearby: never run on a group
    assert v["label"] == "Passed all 3 checks run"
    # round 7 (R6V-005 leftover): a strategy behind buy and hold leads with the shortfall, then the checks it passed
    assert v["fact_headline"] == "117.1 points behind buy and hold after costs; passed all 3 checks run."
    assert "doesn't depend on one exact" not in v["fact_summary"] and "nearby-settings check wasn't run" in v["fact_summary"]
    assert v["fact_summary"].startswith("It returned +55.8% after costs; buying and holding over the same period returned +172.9%, 117.1 points more.")
    assert not re.search(r"\b(buy now|should|recommend)\b", v["fact_summary"], re.I)


def test_two_of_four_and_a_failed_seed_say_exactly_that():
    two = {**SEED, "verdict": {**SEED["verdict"], "passed": 2, "total": 3}, "stats": {**SEED["stats"], "unseen": 4.0, "trades": 138}}
    assert library.label(two) == "Passed 2 of the 3 checks run"
    assert [c["status"] for c in library.restated(two)["checks"]] == ["pass", "skip", "warn", "pass"]
    luck = {**SEED, "verdict": {**SEED["verdict"], "verdict": "luck", "passed": 1, "total": 3}, "stats": {**SEED["stats"], "unseen": -2.2}}
    assert library.label(luck) == "Lost money on the unseen years"


def test_the_public_library_gives_the_card_and_the_page_the_same_words(w):
    e = {**SEED, "official": True, "owner": library.OFFICIAL_OWNER, "strategy": {"entry": [], "exit": []}, "tf": "1d", "market": "US"}
    library.save(e)
    c = w["client"]
    card = next(x for x in c.get("/public/library").json()["entries"] if x["id"] == SEED["id"])
    page = c.get(f"/public/library/{SEED['id']}").json()
    assert card["verdict"]["label"] == page["verdict"]["label"] == "Passed all 3 checks run"
    assert page["verdict"]["fact_headline"].startswith("117.1 points behind buy and hold") and len(page["verdict"]["checks"]) == 4


def test_a_new_verdict_never_claims_the_nearby_check_when_it_wasnt_run():
    checks = [{"id": "unseen", "status": "pass"}, {"id": "nearby", "status": "skip"}, {"id": "shuffle", "status": "pass"}, {"id": "sample", "status": "pass"}]

    class S:
        entry = []
    got = verdict.decide(checks, 100, 20.0, S(), 1825, 3650, 80.0)
    assert got["verdict"] == "edge" and "doesn't depend on one exact" not in got["summary"] and "wasn't run" in got["summary"]
    checks[1]["status"] = "pass"
    assert "settings near yours made money too" in verdict.decide(checks, 100, 20.0, S(), 1825, 3650, 80.0)["summary"]


# ---------- R6V-012: each library strategy's page has its own tags before any script runs ----------
def test_the_sites_list_of_library_pages_matches_the_seeds():
    src = (ROOT / "frontend" / "src" / "content" / "seo.ts").read_text()
    listed = re.findall(r'\["(seed-[a-z0-9-]+)", "([^"]+)"\]', src)
    want = [(library_seed.entry_id(slug, pid), f"{s['name']} · {library_seed.preset_of(m, pid)['name']}")
            for slug, s in library_seed.STRATEGIES.items() for m, pid in s["groups"]]
    assert listed == want


# ---------- R6V-010: the weekly email counts paying apart from given, and says why an admin gets it ----------
def test_the_weekly_email_separates_paying_from_given_and_matches_admin_errors():
    facts = {"stats": {"users": 10, "new": 4, "paid": {"pro": 6}, "paying": {}, "given": {"pro": 6}, "experiments": 0, "ai": 0},
             "checks": [], "audits": {}, "errors": 22, "errors_since_restart": 0, "errors_before_restart": 23, "admin_url": None}
    _, text = weekly.summary(datetime(2026, 10, 5, 9, 0, tzinfo=IST), facts)
    assert "- Paying: none" in text and "- Given by the owner, not paying: Pro 6" in text and "Paid: Pro 6" not in text
    # R9P-004: the words and numbers of Admin → System ("0 since the last restart, 23 kept from before it"), not a second wording
    assert "- 22 errors this week (0 since the last restart, 23 kept from before it)" in text


def test_admin_emails_say_why_an_admin_gets_them(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_message", lambda *a, **k: sent.append((a, k)))
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "email_confirmed", lambda p: True)
    for _, job in alerts.jobs_for({"alert_email": "a@x.com"}, "S", "T", "/admin", alerts.ADMIN_WHY, "Admin alert"):
        job()
    (args, kw), = sent
    assert args[4] == "Admin alert" and kw["why"] == alerts.ADMIN_WHY and "turned on notifications" not in kw["why"]


# ---------- R6V-016: email links on the site's own domain, unsubscribe without sign-in, one time zone ----------
def test_email_links_use_the_public_site_which_forwards_them_to_the_api(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://stratlab.studio")
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://stratlab-production-ca25.up.railway.app")
    for url in (alerts.confirm_url("u-1", "a@x.com"), alerts.unsubscribe_url("u-1", "market_in")):
        assert url.startswith("https://stratlab.studio/") and "railway" not in url
    vercel = json.loads((ROOT / "frontend" / "vercel.json").read_text())
    fwd = {r["source"]: r["destination"] for r in vercel["rewrites"]}
    assert fwd["/unsubscribe"].endswith(".railway.app/unsubscribe") and fwd["/email/confirm"].endswith(".railway.app/email/confirm")
    _, html, text = email_previews.describe("confirm", True)["subject"], None, email_previews.describe("confirm", True)["text"]
    assert "railway" not in text and "https://stratlab.studio/email/confirm?t=" in text


def test_a_preview_unsubscribe_link_is_the_signed_out_page_not_settings(w):
    d = email_previews.describe("market_in", True)
    link = re.search(r"Unsubscribe from India briefs: (\S+)", d["text"]).group(1)
    assert "/unsubscribe?t=" + email_kit.PREVIEW_TOKEN in link and "settings" not in link
    r = w["client"].get("/unsubscribe", params={"t": email_kit.PREVIEW_TOKEN})
    assert r.status_code == 200 and "nothing was changed" in r.text and "sign-in" in r.text


def test_preview_times_are_india_time_and_the_tax_reminder_is_dated_when_sent():
    assert screens._when("2026-10-08T18:29:00+00:00") == "8 Oct 2026, 23:59 IST"
    d = {"date": "2026-12-15", "label": "15 Dec 2026", "n": 2, "pct": 0.75}
    _, html, text = money_advance_tax.reminder_email(d, 7)
    assert "Tue 8 Dec" in text and "Advance tax · Tue 15 Dec" not in text           # the header: the day it goes out
