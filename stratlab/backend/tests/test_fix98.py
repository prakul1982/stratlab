"""Lane fix98: four production faults of 26-27 Nov 2026. Each test fails on origin/main a8816c5 and passes after, except those marked
as guards."""
from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
import httpx
import pytest

from app.intel import filings as F
from app.intel import nse_archive as A
from app.intel.net import SourceError

EQUITY_CSV = ("SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
              + "".join(f"CO{i},Company {i} Limited,EQ,01-Jan-2010,10,1,INE{i:09d},10\n" for i in range(150)))


# ---------- 1. the exchange's archive: every host in turn ----------
def test_the_list_of_companies_is_read_from_the_next_archive_host_when_one_refuses():
    """Fails on main: production's address got 403 on nsearchives.nseindia.com for EQUITY_L.csv every hour from 26 Nov 19:51 UTC
    ("stock list IN failed: The exchange's list of companies was refused (403)") while the .in host and archives.nseindia.com served
    the same file. The .in host is asked first (as R93), then .com, then archives.nseindia.com."""
    asked = []

    def handler(r):
        asked.append(r.url.host)
        return httpx.Response(200, text=EQUITY_CSV) if r.url.host == "archives.nseindia.com" else httpx.Response(403)
    feed = F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    got = feed.all_equities()
    assert len(got) == 150 and got[0]["symbol"] == "CO0"
    assert asked == ["nsearchives.nseindia.in", "nsearchives.nseindia.com", "archives.nseindia.com"]
    # the .in host answering: asked once, nothing else
    asked.clear()
    feed = F.NSEFilings(transport=httpx.MockTransport(lambda r: (asked.append(r.url.host), httpx.Response(200, text=EQUITY_CSV))[1]))
    assert len(feed.all_equities()) == 150 and asked == ["nsearchives.nseindia.in"]


def test_the_list_of_companies_fails_only_when_every_host_refuses():
    asked = []
    feed = F.NSEFilings(transport=httpx.MockTransport(lambda r: (asked.append(r.url.host), httpx.Response(403))[1]))
    with pytest.raises(SourceError, match=r"list of companies was refused \(403\)"):
        feed.all_equities()
    assert asked == list(A.MIRRORS)
    # a host that can't be reached moves on too; the last refusal is what is said
    calls = []

    def flaky(r):
        calls.append(r.url.host)
        if r.url.host == "nsearchives.nseindia.in":
            raise httpx.ConnectError("down")
        return httpx.Response(403)
    with pytest.raises(SourceError, match=r"\(403\)"):
        F.NSEFilings(transport=httpx.MockTransport(flaky)).all_equities()
    assert calls == list(A.MIRRORS)


def test_a_missing_file_is_the_archives_answer_and_is_not_asked_three_times():
    """Guard: only a refusal (401/403) or no connection moves on; a 404 (not published) or a 5xx is the archive's answer."""
    for code in (404, 500, 200):
        asked = []
        http = httpx.Client(transport=httpx.MockTransport(lambda r: (asked.append(r.url.host), httpx.Response(code))[1]))
        assert A.get(http, F.SEC_LIST).status_code == code and asked == ["nsearchives.nseindia.in"]


def test_every_archive_address_in_the_app_goes_through_the_one_rule():
    """The rule is the host, not a list of addresses: each archive file the app reads (price bands, F&O ban, index files, lot sizes,
    ETF list, bhavcopies, participant files) is asked on each host in turn, and the allow-lists of documents take every host."""
    from app import docs, ipo, ipo_docs, positioning, shareholders
    assert A.mirrors("https://archives.nseindia.com/content/fo/fo_mktlots.csv") == [
        "https://nsearchives.nseindia.in/content/fo/fo_mktlots.csv", "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv",
        "https://archives.nseindia.com/content/fo/fo_mktlots.csv"]
    assert A.mirrors("https://www.nseindia.com/api/x") == ["https://www.nseindia.com/api/x"]
    # no address names the older host as a second address of its own any more: the rule asks it
    assert all("//archives." not in u for u in (*F.sec_list_urls(), *positioning.FILE_URLS))
    for host in A.HOSTS:
        assert host in docs.ALLOWED_HOSTS and host in ipo_docs.HOSTS and host in shareholders.XBRL_HOSTS
        assert f"https://{host}/" in ipo.LINK_HOSTS and F._archive_url(f"https://{host}/x.xml")
    # the per-stock desks' and positioning's files (positioning.Feed) read through the same rule
    asked = []

    def handler(r):
        asked.append(r.url.host)
        if r.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(200, text="a,b\n1,2\n") if r.url.host == "archives.nseindia.com" else httpx.Response(403)
    f = positioning.Feed(F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None), sleep=lambda s: None)
    assert f.raw("https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261126_F_0000.csv.zip") == b"a,b\n1,2\n"
    assert asked[-3:] == list(A.MIRRORS)


def test_a_filed_document_refused_on_one_host_is_read_from_the_next():
    """A filing's PDF linked on the .com host and refused there is read from the archive's other hosts."""
    from app import docs
    asked = []

    def handler(r):
        asked.append(str(r.url))
        return httpx.Response(200, content=b"%PDF-1.4 x") if r.url.host == "archives.nseindia.com" else httpx.Response(403)
    d = docs.Docs(transport=httpx.MockTransport(handler), check_host=lambda h: True)
    url = "https://nsearchives.nseindia.com/corporate/X_1.pdf"
    assert d._download(url, (), 1000) == b"%PDF-1.4 x"
    assert asked == [url, "https://nsearchives.nseindia.in/corporate/X_1.pdf", "https://archives.nseindia.com/corporate/X_1.pdf"]
    with pytest.raises(SourceError, match=r"\(403\)"):
        docs.Docs(transport=httpx.MockTransport(lambda r: httpx.Response(403)), check_host=lambda h: True)._download(url, (), 1000)


# ---------- 2. the price refresh doesn't try Indian pages while the broker's login has ended ----------
from tests.test_review_r7v import mem, us  # noqa: E402,F401  (the in-memory settings table and a page's facts)


def test_the_price_refresh_asks_for_no_page_while_the_broker_login_has_ended(mem, capsys):  # noqa: F811
    """Fails on main: "stock pages: price refresh failed: IN 544937 Indian market data is offline: the broker login has ended." was
    logged every minute from IST midnight to the 08:00 login, one page tried (and failed) a pass, a pass a minute. Now, while the login
    isn't valid, no page is asked for and nothing is logged; the pages wait (for the usual pass, not one a minute) and are read once the
    login is back."""
    import json
    from datetime import datetime, timezone
    from app import stock_pages
    from app.kite_service import KiteNotReady
    now = datetime(2026, 10, 9, 0, 30, tzinfo=timezone.utc)
    built = now.timestamp() - 30 * 3600
    for i, sym in enumerate(("AAA", "BBB", "CCC")):
        mem[f"stocks:page:US:{sym}"] = json.dumps({"ts": built, "facts": us(symbol=sym, price_at="2026-10-07", market_cap=1_000.0 * (3 - i))})
    asked, login = [], {"ok": False}

    def bars(region, sym):
        asked.append(sym)
        if not login["ok"]:
            raise KiteNotReady("Indian market data is offline: the broker login has ended.")
        return [{"t": "2026-10-08T00:00:00-04:00", "o": 1, "h": 1, "l": 1, "c": 1.0}]
    pages = stock_pages.Pages(lambda r, c: None)
    got = pages.refresh_prices("US", bars, gap=0, now=now, ready=lambda: login["ok"])
    assert asked == [] and "price refresh failed" not in capsys.readouterr().out
    assert got["source_down"] and got["left"] == 3 and got["failed"] == 0 and "US" not in pages.prices_done
    assert not main.price_pass_failed(got) and not main.refresh_backlog({"IN": got}) and main.refresh_wait({"IN": got}) == main.PRICE_REFRESH_EVERY
    login["ok"] = True                                              # the morning login: read at the next pass
    got = pages.refresh_prices("US", bars, gap=0, now=now, ready=lambda: login["ok"])
    assert got["refreshed"] == 3 and asked == ["AAA", "BBB", "CCC"]
    # the job hands India's pass the broker's own check
    import inspect
    assert '"ready": kite.ready' in inspect.getsource(main.stock_price_refresh_once)


# ---------- 4. members no longer listed leave every figure of a theme ----------
from app.intel import theme_base as TB  # noqa: E402
from app.intel import theme_data as TD  # noqa: E402
from app.intel import theme_listed as TL  # noqa: E402
from tests.test_theme1 import TODAY, facts as page_facts  # noqa: E402


def _drillers(listed, extra=()):
    """A US theme of eight drillers, with the SEC list `listed` gives: EP7 taken private (off the list, its last price 1 Sep), EP6 off the
    list but trading (its price today), OLDT renamed (its name the registrant the SEC lists as NEWT)."""
    cos = [(f"EP{i}", f"Driller {i} Inc", 50000 - i * 1000) for i in range(8)] + [("OLDT", "Newco Corp", 30000)]
    rows = [{"symbol": s, "name": n, "industry": "Crude Petroleum and Natural Gas", "market_cap": c} for s, n, c in cos]
    ai = {"sector": "Oil and gas", "summary": "", "core": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 0,
          "value_chain": [{"layer": "Exploration and production", "description": "Drill for crude oil and natural gas.",
                           "companies": [{"ticker": s, "name": n, "what": "explores for and produces crude oil and natural gas", "verified": True}
                                         for s, n, _ in cos]}]}
    m = TB.with_base(ai, {**ai, "placements": {"checked": True, "pending": 0}}, rows, [])
    f = {}
    for i, (s, n, cap) in enumerate(cos + [("NEWT", "Newco Corp", 31000)]):
        f[s] = {**page_facts(s, n, [500, 600, 700, 800 + i * 20], [20.0, 21.0, 22.0, 18.0 + i], [50, 60, 70, 80 + i], cap=cap, pe=12.0,
                             industry=("Crude Petroleum and Natural Gas",)), "region": "US", "unit": "$ million", "annual_form": "10-K",
                "annual_filed": "2026-02-01"}
    f["EP7"]["price_at"] = "2026-09-01"                   # its last trade, before it was taken private
    f["OLDT"] = {"region": "US", "symbol": "OLDT", "name": "Newco Corp", "price": 9.0, "price_at": "2026-09-02"}     # the old ticker's page: no figures
    return TD.build("US", "Oil and gas", m, TD.Sources(TODAY, facts=f.get, listed=listed))


def _sec_list(*off):
    tickers = {f"T{i}": {"cik": 10_000 + i, "name": f"Other Co {i}"} for i in range(1200)}
    tickers.update({f"EP{i}": {"cik": i + 1, "name": f"Driller {i} Inc"} for i in range(8) if f"EP{i}" not in off})
    tickers.update({"NEWT": {"cik": 99, "name": "NEWCO CORP"}, "NEWT-WT": {"cik": 99, "name": "NEWCO CORP"}})
    return TL.from_sec(tickers, TODAY.isoformat())


def test_a_member_no_longer_on_its_markets_list_is_listed_so_and_in_no_figure():
    """Fails on main: Qorvo, taken private and gone from the SEC's company_tickers.json, stayed in Semiconductors' layer medians, and EA, TMHC,
    TPH and SPR were read for every dive ("sector metrics: not read: US EA ... isn't a company that files with the SEC"). A member its market's
    current list doesn't name is listed once as no longer listed (too_small, kind "delisted") and is in no table, median, total or ranking."""
    lst = _sec_list("EP6", "EP7")
    dive = _drillers(lambda: lst)
    lay = next(b for b in dive["layers"] if b["layer"] == "Exploration and production")
    shown = {c["symbol"] for c in lay["companies"]}
    assert "EP7" not in shown and all(TD.in_calc(c) for c in lay["companies"])
    gone = [x for x in dive["too_small"] if x.get("kind") == "delisted"]
    assert [x["symbol"] for x in gone] == ["EP7"] and gone[0]["why"].startswith("no longer listed: the SEC's list of companies")
    assert "1 Sep 2026" in gone[0]["why"] and "in no figure of the theme" in gone[0]["why"]
    assert "EP6" in shown                                      # off the list but trading today: no proof it left, kept
    assert lay["stats"]["ebitda"]["n"] == len([c for c in lay["companies"] if TD.in_calc(c)])
    assert dive["with_figures"] == len(shown)                  # the companies with figures: not the one no longer listed
    # renamed, not gone: OLDT is the registrant the SEC lists as NEWT, read by NEWT's page (its figures), never removed
    old = next(c for c in lay["companies"] if c["symbol"] == "OLDT")
    assert old["now_ticker"] == "NEWT" and old["revenue"] and TD.in_calc(old)
    assert "OLDT" not in {x["symbol"] for x in dive["too_small"]}
    # the deck says them on a page of the appendix of their own and in its method notes, never among the too small
    from app import deck
    assert deck.NOT_LISTED_TITLE.endswith(": no longer listed")


def test_missing_data_never_removes_a_member():
    """Guard: no list (it can't be read, or the kept one is days old), or a broken one: nobody is removed; the same dive as before."""
    for listed in (lambda: None, lambda: TL.from_sec({"EP1": {"cik": 1, "name": "x"}}, TODAY.isoformat())):
        dive = _drillers(listed)
        lay = next(b for b in dive["layers"] if b["layer"] == "Exploration and production")
        assert "EP7" in {c["symbol"] for c in lay["companies"]} and not [x for x in dive["too_small"] if x.get("kind") == "delisted"]
    # India: the company pages' kept list, older than LIST_FRESH_DAYS, is no current list; a fresh one is, BSE-only trading symbols with it
    from datetime import date
    kept = {"at": "2026-10-01T03:00:00+00:00", "rows": {**{f"S{i}": "x" for i in range(150)}, "BSE:500001": "Aruna"}}
    assert TL.from_kept(kept, {"500001": {"ts": "ARUNAHTEL"}}, date(2026, 10, 9)) is None
    got = TL.from_kept(kept, {"500001": {"ts": "ARUNAHTEL"}}, date(2026, 10, 3))
    assert {"S1", "ARUNAHTEL", "500001"} <= got["symbols"]
    assert TL.gone("IN", "ARUNAHTEL", None, got) is None and TL.gone("IN", "GONECO", "2026-08-31", got)
    assert TL.gone("IN", "SMEONLY", "2026-09-05", got) is None          # an SME board company the list does not carry, trading this month: kept
    # a list that can't be read is asked again at the next dive, never kept as "none"
    TL.forget()
    calls = []
    r = TL.reader("US", TODAY, sec_tickers=lambda: calls.append(1) or (_ for _ in ()).throw(RuntimeError("down")))
    assert r() is None and r() is None and len(calls) == 2
    TL.forget()


def test_paramount_skydance_is_a_current_filer_under_skyd():
    """PSKY (Paramount Skydance) isn't on the SEC's list of 27 Nov: the SEC lists its registrant, Skydance Corp (CIK 2041610), as SKYD (and
    SKYD-WT, its warrants). It is renamed, never no longer listed: its name is the one registrant's."""
    tickers = {f"T{i}": {"cik": 10_000 + i, "name": f"Other Co {i}"} for i in range(1200)}
    tickers.update({"SKYD": {"cik": 2041610, "name": "Skydance Corp"}, "SKYD-WT": {"cik": 2041610, "name": "Skydance Corp"}})
    lst = TL.from_sec(tickers, "2026-11-27")
    assert TL.renamed("US", "PSKY", ["Skydance Corp"], lst) == "SKYD"
    assert TL.renamed("US", "PSKY", ["Paramount Skydance Corporation"], lst) is None        # no registrant of that name: not guessed
    assert TL.renamed("US", "PSKY", ["Skydance Corp"], lst, taken={"SKYD"}) is None        # another member's ticker: not taken twice
    assert TL.gone("US", "BRK.B", None, TL.from_sec({**tickers, "BRK-B": {"cik": 1, "name": "Berkshire"}}, "2026-11-27")) is None


# ---------- 1b. the official closes (the daily cash bhavcopy): the same rule, and a refused day asked again ----------
def test_the_official_closes_file_is_read_from_the_next_host_and_a_refused_day_is_asked_again(mem, monkeypatch):  # noqa: F811
    """Fails on main: "official closes: <date> The exchange's file was refused (403)" for many dates from ~05:56 UTC 27 Nov, the cash
    bhavcopy refused on nsearchives.nseindia.com while the .in host and archives.nseindia.com served it (checked 27 Nov for 26 Nov's
    bhavcopy, index closes and 52-week file: 200 on all three). Read through the archive rule, the .in host first; a day every host refuses
    is no "failed" day: nothing is kept for it and it is asked again after official_close.RETRY."""
    import time as _t
    from datetime import date
    from app import exchange_days as X, official_close as OC, positioning
    from tests.fake_stock_desks import cash_csv
    d = date(2026, 11, 26)
    zipped = __import__("io").BytesIO()
    with __import__("zipfile").ZipFile(zipped, "w") as z:
        z.writestr("BhavCopy.csv", cash_csv(d))
    state = {"open": ("nsearchives.nseindia.in",)}
    asked = []

    def handler(r):
        if r.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        asked.append(r.url.host)
        return httpx.Response(200, content=zipped.getvalue()) if r.url.host in state["open"] else httpx.Response(403)
    feed = positioning.Feed(F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None), sleep=lambda s: None)
    files = X.Files(feed, sleep=lambda s: None, pace=0)
    X.clear_cache()
    assert X.cash_closes(files, d) and asked == ["nsearchives.nseindia.in"]
    # every host refusing: the read fails (said once), nothing kept, the day asked again once RETRY has passed
    X.clear_cache()
    state["open"], asked[:] = (), []
    OC._asked.clear()
    monkeypatch.setitem(OC._src, "files", lambda: files)
    assert OC._read_closes(d.isoformat(), lambda: files) is None
    assert set(asked) == set(A.MIRRORS) and OC._asked[("asked", d.isoformat())] <= _t.time() + OC.RETRY
    assert X._cache.get(("cash", d.isoformat())) is None              # no "not published" kept for a refusal
    state["open"] = ("archives.nseindia.com",)
    OC._asked.clear()                                                  # RETRY later
    got = OC._read_closes(d.isoformat(), lambda: files)
    assert got and len(got) > 3
    OC._asked.clear(), X.clear_cache()


def test_the_deck_lists_a_member_no_longer_listed_once_on_its_own_appendix_page():
    """The deck: a member no longer listed on a page of its own in the appendix, with why, in no layer table, and named in the method notes
    as no longer listed, never among the too small or too stale."""
    from app import deck
    from app.intel import theme_routes as TR
    from tests.test_r18_deck import NOW
    dive = _drillers(lambda: _sec_list("EP7"))
    m = {"sector": "Oil and gas", "value_chain": [], "placements": {"checked": True}}
    slides = deck.with_held(deck.theme_plan(TR.deck_view("US", m, dive), now=NOW)[0])
    gone = [s for s in slides if s.title.startswith(deck.NOT_LISTED_TITLE)]
    assert len(gone) == 1 and not [s for s in slides if s.title.startswith(deck.DUST_TITLE)]
    rows = [r for b in gone[0].blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict)]
    assert len(rows) == 1 and rows[0][0].startswith("Driller 7") and rows[0][2].startswith("no longer listed: the SEC's list")
    others = [r for s in slides if not s.title.startswith((deck.NOT_LISTED_TITLE, deck.METHOD_TITLE)) for b in s.blocks if b["kind"] == "table"
              for r in b["rows"] if not isinstance(r, dict) and any("Driller 7" in str(x) for x in r)]
    assert not others
    text = " ".join(str(p) for s in slides if s.title.startswith(deck.METHOD_TITLE) for b in s.blocks for p in (b.get("paras") or []))
    text += " ".join(str(x) for s in slides if s.title.startswith(deck.METHOD_TITLE) for b in s.blocks for r in (b.get("rows") or [])
                     if not isinstance(r, dict) for x in r)
    assert "1 company no longer listed" in text or "no longer listed (not on the market's current list" in text


def test_the_lists_rule_reads_the_secs_names_and_leaves_what_no_list_carries():
    """The SEC's state suffix is no part of a name (Texas Capital, TCBI, is the registrant the SEC lists as TXCP, "TEXAS CAPITAL BANCSHARES
    INC/TX"); a trust in India (the equity list is of companies) and an unsponsored ADR in the US (its company files nothing with the SEC)
    are never taken for no longer listed by a list that never carries them."""
    tickers = {f"T{i}": {"cik": 10_000 + i, "name": f"Other Co {i}"} for i in range(1200)}
    tickers.update({"TXCP": {"cik": 1077428, "name": "TEXAS CAPITAL BANCSHARES INC/TX"}, "TXCP-PB": {"cik": 1077428, "name": "TEXAS CAPITAL BANCSHARES INC/TX"}})
    lst = TL.from_sec(tickers, "2026-11-27")
    assert TL.renamed("US", "TCBI", ["Texas Capital Bancshares Inc"], lst) == "TXCP"
    assert TL.gone("US", "ADYEY", None, lst, names=["Adyen Nv-Unspon ADR"]) is None
    assert TL.gone("US", "EA", None, lst, names=["Electronic Arts Inc."])
    inl = {"day": "2026-11-27", "symbols": {"TCS"}, "names": {}}
    assert TL.gone("IN", "DIGIFIBRE", None, inl, names=["Digital Fibre Infrastructure Trust"]) is None
    assert TL.gone("IN", "EMBASSY-RR", None, inl, names=["Embassy Office Parks REIT"]) is None
    assert TL.gone("IN", "NOVARTIND", "2026-10-20", inl, names=["Novartis India Ltd"]) and not TL.gone("IN", "NOVARTIND", "2026-11-03", inl)
