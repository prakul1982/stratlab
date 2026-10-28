"""A harsh public-site audit of the company pages (DK-018 to DK-033): recent filings that name nothing and link nowhere, a
profit line that disagrees with the P/E, a "how these figures are worked out" box that looks empty, EBITDA margin on an
insurer, SEC suffixes and absurd margins, one company under two addresses, HEAD answered 405, and a 52-week low cut
down to the rupee."""
import json
import re

import pytest

from app import db, main, screens, stock_pages
from tests import world
from tests.tiles import stat


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def facts(**kw) -> dict:
    base = {"region": "IN", "symbol": "ACME", "name": "Acme Ltd", "exchange": "NSE", "industry": ["Industrials"],
            "currency": "INR", "unit": "₹ crore", "price": 100.0, "price_at": "2026-10-07", "price_basis": "close", "high52": 120.0,
            "low52": 80.0, "market_cap": 770345.0, "pe": 14.3, "roe": 12.0, "opm": 28.0, "net_margin": 19.4, "debt_equity": 0.1,
            "div_yield": 1.1, "years": [{"year": f"Mar 202{i}", "sales": 100.0 + i, "profit": 20.0, "opm": 26.0 + i % 2, "debt": 1.0}
                                        for i in range(2, 7)],
            "growth": {}, "filings": [], "built_at": "2026-10-08T05:00:00+00:00"}
    return {**base, **kw}




# ---------- DK-018: each filing named, linked, and the paperwork left out ----------
EXCHANGE = "https://nsearchives.nseindia.com/corporate/"
RIL = [
    {"at": "2026-10-14", "title": "Other update: Copy of Newspaper Publication", "text": "Reliance has informed the Exchange regarding Copy of Newspaper Publication", "url": EXCHANGE + "a.pdf"},
    {"at": "2026-10-14", "title": "Credit rating: Credit Rating", "url": EXCHANGE + "b.pdf",
     "text": "Reliance Industries Limited has informed the Exchange regarding Credit Rating - CRISIL reaffirms AAA/Stable. Assigned on 10th Oct."},
    {"at": "2026-10-13", "title": "Other update: Updates", "url": EXCHANGE + "c.pdf",
     "text": "Reliance Industries Limited has informed the Exchange about Press Release on Jio Platforms results"},
    {"at": "2026-10-12", "title": "Other update: General Updates", "text": "", "url": EXCHANGE + "d.pdf"},
    {"at": "2026-10-11", "title": "Financial results: Outcome of Board Meeting", "text": "x", "url": EXCHANGE + "e.pdf"},
    {"at": "2026-10-10", "title": "Other update: Trading Window", "text": "", "url": EXCHANGE + "f.pdf"},
]


def test_a_filing_is_named_by_what_it_is_and_the_paperwork_is_dropped():
    got = stock_pages.listed_filings(RIL)
    assert [x["name"] for x in got] == ["Credit rating: CRISIL reaffirms AAA/Stable", "Press Release on Jio Platforms results",
                                        "Financial results: Outcome of Board Meeting"]
    assert [x["url"] for x in got] == [EXCHANGE + "b.pdf", EXCHANGE + "c.pdf", EXCHANGE + "e.pdf"]
    # a US filing is already named, and links to the SEC's document
    sec = stock_pages.listed_filings([{"at": "2026-08-01", "title": "Annual report (10-K)", "url": "https://www.sec.gov/Archives/x.htm"}])
    assert sec == [{"at": "2026-08-01", "title": "Annual report (10-K)", "name": "Annual report (10-K)", "url": "https://www.sec.gov/Archives/x.htm"}]
    # an address that is not https is never linked
    assert "url" not in stock_pages.listed_filings([{"at": "2026-08-01", "title": "Board meeting: Outcome", "url": "javascript:alert(1)"}])[0]


def test_the_recent_filings_list_links_each_filing_and_shows_no_bare_other_update():
    built = stock_pages.facts("IN", "ACME", {"name": "Acme"}, {"years": []}, {}, None, None, RIL, "NSE")
    assert len(built["filings"]) == 3
    page = stock_pages.render(facts(filings=built["filings"]), "IN", "ACME", "Acme Ltd")
    assert f'<a href="{EXCHANGE}b.pdf" rel="noopener nofollow">Credit rating: CRISIL reaffirms AAA/Stable</a>' in page
    assert "Newspaper" not in page and "Other update" not in page and "Trading Window" not in page
    # a page stored before filings were named is worked out from its titles when drawn, and drops what says nothing
    old = stock_pages.render(facts(filings=[{"at": "2026-10-14", "title": "Other update: Updates"},
                                            {"at": "2026-10-13", "title": "Board meeting: Outcome of Board Meeting"}]), "IN", "ACME", None)
    block = re.search(r"<h2>Recent filings</h2>.*?</ul>", old, re.S).group(0)
    assert "Other update" not in old and block.count("<li>") == 1 and "Board meeting: Outcome of Board Meeting" in block
    only_noise = stock_pages.render(facts(filings=[{"at": "2026-10-14", "title": "Other update: Copy of Newspaper Publication"}]), "IN", "ACME", None)
    assert "Recent filings" not in only_noise


# ---------- DK-021: the profit line and the P/E agree ----------
RELIANCE = dict(price=1350.0, market_cap=1_840_000.0, pe=24.62, profit_ttm=88167.0,       # 1,840,000 / 24.62 = 74,736
                years=[{"year": "Mar 2026", "sales": 1_000_000.0, "profit": 80000.0, "opm": 17.0, "debt": 300000.0}])


def test_a_p_e_on_the_shareholders_profit_sits_beside_that_profit_and_the_one_with_minorities():
    f = facts(**RELIANCE)
    assert stock_pages.owners_profit(f) == pytest.approx(74736, abs=1)
    page = stock_pages.render(f, "IN", "RELIANCE", None)
    assert stat(page, "Profit to shareholders, last 12 months (₹ crore)") == "74,736"
    assert stat(page, "Net profit incl. minority interests, last 12 months (₹ crore)") == "88,167"
    assert stat(page, "Net profit, last 12 months (₹ crore)") is None
    note = re.search(r'<p class="note" data-pe-basis>(.*?)</p>', page).group(1)
    assert "74,736 crore" in note and "88,167 crore" in note and "gives 20.9" in note
    # where they agree there is one line, as before
    agree = stock_pages.render(facts(**{**RELIANCE, "market_cap": 1_000_000.0, "pe": 20.0, "profit_ttm": 50000.0}), "IN", "ACME", None)
    assert stat(agree, "Net profit, last 12 months (₹ crore)") == "50,000" and "Profit to shareholders" not in agree


# ---------- DK-022: the "how these figures are worked out" box shows it opens ----------
def test_the_how_box_has_a_marker_and_says_show_or_hide():
    css = re.search(r"<style>(.*?)</style>", stock_pages.render(facts(), "IN", "ACME", None), re.S).group(1)
    assert "details.how summary::before" in css and "details.how[open] summary::before" in css
    assert 'content:"Show"' in css and 'content:"Hide"' in css and "details.how summary::-webkit-details-marker{display:none}" in css
    assert "list-style:none" in css.split("details.how summary{")[1].split("}")[0]


# ---------- DK-023: an insurer is treated as a bank ----------
def test_an_insurer_has_no_ebitda_margin_or_debt_to_equity():
    p = {"name": "Life Insurance Corporation of India", "industry_path": ["Financial Services", "Insurance", "Life Insurance"]}
    built = stock_pages.facts("IN", "LICI", p, {"years": [{"year": "Mar 2026", "sales": 900000.0, "profit": 48000.0, "opm": 5.0, "debt": 0}]},
                              {"debt_equity": 0.0, "opm": 5.0}, None, None, [], "NSE")
    assert built["bank"] is True
    page = stock_pages.render({**facts(), **built}, "IN", "LICI", None)
    assert "<span>EBITDA margin" not in page and "<span>Debt to equity" not in page and "Borrowings" not in page and "<td>EBITDA margin" not in page
    assert "<span>EBITDA margin" in stock_pages.render(facts(), "IN", "ACME", None)
    plain = stock_pages.facts("IN", "ACME", {"name": "Acme Ltd", "industry_path": ["Industrials", "Machinery"]}, {"years": []}, {}, None, None, [], "NSE")
    assert plain["bank"] is False


# ---------- DK-024: names, industries, margins and small numbers ----------
def test_sec_suffixes_and_titles_are_tidied():
    assert stock_pages.strip_registration("Rivian Automotive, Inc. / DE") == "Rivian Automotive, Inc."
    assert stock_pages.proper_name("RIVIAN AUTOMOTIVE, INC. /DE/") == "Rivian Automotive, Inc."
    assert stock_pages.proper_name("COSTCO WHOLESALE CORP /NEW") == "Costco Wholesale Corp"
    assert stock_pages.strip_registration("Procter & Gamble Co") == "Procter & Gamble Co"
    built = stock_pages.facts("US", "RIVN", {"name": "Rivian Automotive, Inc. / DE"}, {"years": []}, {}, None, None, [], "Listed in the US")
    assert built["name"] == "Rivian Automotive, Inc."
    page = stock_pages.render(facts(region="US", name="Rivian Automotive, Inc. / DE", currency="USD", unit="$ million"), "US", "RIVN", None)
    assert "/ DE" not in page and "Rivian Automotive, Inc. (RIVN)" in page
    assert stock_pages.plain_industry("Motor Vehicles & Passenger Car Bodies") == "Motor vehicles and passenger car bodies"
    assert stock_pages.plain_industry("Computer Peripheral Equipment, Nec") == "Computer peripheral equipment"
    assert stock_pages.plain_industry("Radio & Tv Broadcasting & Communications Equipment") == "Radio and TV broadcasting and communications equipment"
    assert stock_pages.shown_industry(["Manufacturing", "Motor Vehicles & Passenger Car Bodies"], plain=True) == ["Manufacturing", "Motor vehicles and passenger car bodies"]
    us = stock_pages.render(facts(region="US", currency="USD", unit="$ million", industry=["Manufacturing", "Motor Vehicles & Passenger Car Bodies"]),
                            "US", "RIVN", None)
    assert "Manufacturing · Motor vehicles and passenger car bodies" in us and "Passenger Car Bodies" not in us
    assert "Information Technology" in stock_pages.render(facts(industry=["Information Technology"]), "IN", "ACME", None)     # India's are left as listed


def test_every_page_names_the_year_its_key_figures_are_on_and_absurd_margins_are_not_meaningful():
    msft = facts(region="US", currency="USD", unit="$ million", years=[{"year": "Jun 2026", "sales": 300.0, "profit": 100.0, "opm": 45.0, "debt": 1.0}])
    page = stock_pages.render(msft, "US", "MSFT", None)
    for label in ("Return on equity", "EBITDA margin", "Net margin"):
        assert stat(page, f"{label} (year to Jun 2026)") is not None, label
    rivian = facts(region="US", currency="USD", unit="$ million", opm=-7314.5, net_margin=-9100.0,
                   years=[{"year": "Dec 2025", "sales": 0.05, "profit": -4000.0, "opm": -7314.5, "debt": 1.0}])
    page = stock_pages.render(rivian, "US", "RIVN", None)
    assert stat(page, "EBITDA margin (year to Dec 2025)") == "n/m" and stat(page, "Net margin (year to Dec 2025)") == "n/m"
    assert "7,314" not in re.sub(r"<style>.*?</style>", "", page, flags=re.S) and "<td>n/m</td>" in page and "n/m: not meaningful" in page
    assert stock_pages._pct(-999.0) == "-999.0%" and stock_pages._pct(1000.1) == "n/m"


def test_small_amounts_share_one_precision():
    tiny = facts(unit="₹ crore", profit_ttm=0.43, years=[{"year": f"Mar 202{i}", "sales": s, "profit": 0.43, "opm": 5.0, "debt": 0.2}
                                                          for i, s in zip(range(2, 7), (2.04, 2.1, 2.2, 2.4, 2.9))])
    page = stock_pages.render(tiny, "IN", "TINY", None)
    assert "<td>2.04</td>" in page and "<td>2.90</td>" in page and "<td>0.43</td>" in page and "<td>0.20</td>" in page
    assert stat(page, "Net profit, last 12 months (₹ crore)") == "0.43"
    big = stock_pages.render(facts(), "IN", "ACME", None)
    assert "<td>102</td>" in big and "102.00" not in big
    assert stock_pages.small_digits(2, 3, 99.9) == 2 and stock_pages.small_digits(2, 100) == 0 and stock_pages.small_digits(None) == 0


# ---------- DK-025: one company, one page ----------
def put_lists():
    db.set_setting("audit:bse-only", json.dumps({
        "511712": {"ts": "RELICTEC", "token": 1, "name": "RELIC TECHNOLOGIES"},         # BSE trades it under NSE's own symbol
        "543000": {"ts": "KRISHNA", "token": 2, "name": "KRISHNA DEFENCE AND ALLIED"},      # the same company, under another symbol, BSE's name cut short
        "543210": {"ts": "TINYCO", "token": 3, "name": "TINY CO"},                            # BSE only
        "500999": {"ts": "RELIGARE", "token": 4, "name": "SOME OTHER COMPANY"}}))            # a symbol shared by an unrelated company
    rows = {"RELICTEC": {"name": "Relic Technologies Limited"}, "KRISHNADEF": {"name": "Krishna Defence and Allied Products Limited"},
            "RELIGARE": {"name": "Religare Enterprises Limited"}, "RELIANCE": {"name": "Reliance Industries Limited"},
            "RELAXO": {"name": "Relaxo Footwears Limited"}, "RELIABLE": {"name": "Reliable Data Services Limited"},
            "BSE:511712": {"name": "RELIC TECHNOLOGIES"}, "BSE:543000": {"name": "KRISHNA DEFENCE AND ALLIED"},
            "BSE:543210": {"name": "TINY CO"}, "BSE:500999": {"name": "SOME OTHER COMPANY"}}
    db.set_setting("audit:market:list", json.dumps(rows))
    stock_pages._companies.clear()


def test_a_company_on_both_exchanges_has_one_page_and_the_bse_address_goes_to_it(w):
    put_lists()
    cos = stock_pages.companies("IN")
    assert "511712" not in cos and "543000" not in cos and "KRISHNA" not in cos and "KRISHNADEF" in cos and "RELICTEC" in cos
    assert cos.twins["511712"] == "RELICTEC" and cos.twins["543000"] == "KRISHNADEF" and cos.twins["KRISHNA"] == "KRISHNADEF"
    assert stock_pages.nse_twins()["511712"] == "RELICTEC"
    assert "500999" in cos and "500999" not in cos.twins          # RELIGARE's symbol, but not its name: another company, kept
    assert cos["500999"]["name"] == "Some Other Company" and cos["TINYCO"]["name"] == "Tiny Co"      # BSE writes capitals
    assert stock_pages.find("IN", "511712")[0] == "RELICTEC" and stock_pages.find("IN", "krishna")[0] == "KRISHNADEF"
    c = w["client"]
    r = c.get("/stocks/in/511712", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/stocks/in/RELICTEC"
    sitemap = c.get("/sitemaps/stocks-in-1.xml").text
    assert "/stocks/in/511712" not in sitemap and "/stocks/in/543000" not in sitemap and "/stocks/in/KRISHNA<" not in sitemap


def test_names_cut_short_match_only_when_they_are_clearly_the_same_company():
    assert stock_pages.same_company("RELIC TECHNOLOGIES", "Relic Technologies Limited")
    assert stock_pages.same_company("KRISHNA DEFENCE AND ALLIED", "Krishna Defence and Allied Industries Limited")
    assert not stock_pages.same_company("SUN PHARMA", "Sun Pharmaceutical Industries Limited")        # too short to be a cut-off form
    assert not stock_pages.same_company("TATA", "Tata Steel Limited")
    assert stock_pages.same_company("RELIC TECH", "Relic Technologies Limited", same_symbol=True)       # the shared symbol and first word
    assert not stock_pages.same_company("OTHER THING", "Relic Technologies Limited", same_symbol=True)
    out = {"AAA": {"name": "Alpha Beta Gamma Holdings Limited", "bse": None}, "AAB": {"name": "Alpha Beta Gamma Hospitality Limited", "bse": None},
           "543": {"name": "ALPHA BETA GAMMA H", "bse": "543"}}
    assert stock_pages.twin_pages(out, {"543": "ZZZ"}) == {}          # two NSE companies it could be: no guess
    del out["AAB"]
    assert stock_pages.twin_pages(out, {"543": "ZZZ"}) == {"543": "AAA"}


def test_search_puts_the_exact_symbol_then_the_larger_names_first(w):
    put_lists()
    rows = [{"symbol": s, "name": n, "market_cap": cap, "price": 1350.0 if cap > 1e6 else 100.0} for s, n, cap in (
        ("RELIANCE", "Reliance Industries Limited", 1_800_000.0), ("RELAXO", "Relaxo Footwears Limited", 9_000.0),
        ("RELIGARE", "Religare Enterprises Limited", 8_000.0), ("RELIABLE", "Reliable Data Services Limited", 100.0))]
    db.set_setting(screens.INDEX_KEY + "IN", json.dumps({"at": "2026-10-08", "rows": rows}))
    screens._mem.clear()
    got = [s for s, _ in stock_pages.search("IN", "reli")]
    assert got[:3] == ["RELIANCE", "RELIGARE", "RELIABLE"] and got[3] == "RELICTEC" and "RELAXO" not in got      # larger first, then the rest
    assert [s for s, _ in stock_pages.search("IN", "RELAXO")][0] == "RELAXO"                # the exact symbol, whatever its size
    assert stock_pages.search("IN", "511712")[0][0] == "RELICTEC" and len(stock_pages.search("IN", "relic technologies")) == 1
    first = stock_pages.search("IN", "footwears")                                            # a word inside the name
    assert [s for s, _ in first] == ["RELAXO"]


# ---------- DK-033: HEAD answers as GET does, with no body ----------
def test_head_on_public_pages_has_the_headers_of_get_and_no_body(w):
    c = w["client"]
    for url in ("/stocks/in/RELIANCE", "/stocks/us/AAPL", "/stocks", "/stocks/in", "/stocks/in/NOPE", "/sitemap.xml", "/robots.txt",
                "/sitemaps/stocks-in-1.xml"):
        g, h = c.get(url, follow_redirects=False), c.head(url, follow_redirects=False)
        assert h.status_code == g.status_code, url
        assert h.content == b"", url
        for name in ("content-type", "cache-control", "content-encoding", "vary", "location"):
            assert h.headers.get(name) == g.headers.get(name), (url, name)
        assert int(h.headers["content-length"]) > 0 or g.status_code == 301, url
    assert c.head("/stocks/IN/reliance", follow_redirects=False).headers["location"] == "/stocks/in/RELIANCE"


# ---------- DK-028: a 52-week range in whole rupees takes the exchange's figures ----------
def test_a_range_cut_down_to_the_rupee_takes_the_exchange_paisa():
    report = {"day": "2026-10-08", "rows": {"TCS": [4_592.25, "2026-01-05", 1_976.80, "2026-09-29"]}}
    tcs = facts(symbol="TCS", high52=4592.0, low52=1976.0, range_whole=True, v=stock_pages.FACTS_VERSION)
    got = stock_pages.with_week52_report(tcs, report, "TCS")
    assert got["low52"] == 1976.80 and got["high52"] == 4592.25
    # a page stored before it was marked, with both figures whole, is told the same way
    assert stock_pages.with_week52_report({k: v for k, v in tcs.items() if k != "range_whole"}, report, "TCS")["low52"] == 1976.80
    # a range from candles (not whole) is left alone when the exchange's is within a rupee above it
    candles = facts(symbol="TCS", high52=4592.25, low52=1976.3, v=stock_pages.FACTS_VERSION)
    assert stock_pages.with_week52_report(candles, report, "TCS")["low52"] == 1976.3
    # ...and a whole figure further than a rupee from the exchange's is another basis
    far = facts(symbol="TCS", high52=4592.0, low52=1900.0, range_whole=True)
    assert stock_pages.with_week52_report(far, report, "TCS")["low52"] == 1900.0
    # the build marks a range that came from the fundamentals source
    built = stock_pages.facts("IN", "TCS", {"name": "TCS"}, {"years": []}, {"high52": 4592.0, "low52": 1976.0}, None, {"price": 2000.0}, [], "NSE")
    assert built["range_whole"] is True and built["low52"] == 1976.0
    with_candles = stock_pages.facts("IN", "TCS", {"name": "TCS"}, {"years": []}, {"high52": 4592.0, "low52": 1976.0}, None,
                                     {"price": 2000.0, "high52": 4592.25, "low52": 1976.8}, [], "NSE")
    assert "range_whole" not in with_candles
