"""A deep audit of the scan and market-view pages (DE-001 to DE-036): Indian scans down all weekend, two layouts for one
scan, raw SEC names, an EMA called an average, a silent alert; a blank Stage and an impossible range in the screener;
a theme map with wrong facts and unlisted companies; "well below 52-week highs" at 2.8% below; rotation's "4 weeks ago"
reading 3; an empty US results calendar in earnings season and an Indian one cut at the 400th row; no US ex-dates
ahead, a trust's distribution twice, a spin-off as a split; red flags that couldn't be read, a rating revision never
flagged, duplicate resignations and a news verification read as a rights issue.

The exchange's, the SEC's and the US market calendar's own files are in tests/fixtures/de1 (trimmed copies of the real
answers of 21-30 Oct 2026)."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from app import breadth, corp_actions as CA, db, main, redflags, results as R, rotation, scan, scan_presets, screens, stock_pages
from app.intel import ai as A, company, filings, grounding, sec, us_calendar
from app.intel.net import SourceError
from tests import world

FIX = Path(__file__).parent / "fixtures" / "de1"


def fixture(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def bars_from(closes, start=datetime(2025, 1, 1, tzinfo=timezone.utc)):
    return [{"t": (start + timedelta(days=i)).date().isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000}
            for i, c in enumerate(closes)]


# ---------- DE-025: the US results calendar, from the market calendar and the SEC's earnings releases ----------
def test_the_secs_filing_search_gives_the_days_earnings_releases():
    got = sec.earnings_hits(fixture("efts_8k_2026-10-21.json"))
    by = {x["symbol"]: x for x in got}
    assert set(by) == {"TSLA", "IBM", "PNFP"}                         # only 8-Ks with item 2.02, no amendment, no other item
    assert by["TSLA"]["at"] == "2026-10-21" and by["TSLA"]["url"] == \
        "https://www.sec.gov/Archives/edgar/data/1318605/000162828026066738/tsla-20261021.htm"
    assert by["PNFP"]["symbol"] == "PNFP"                             # the common stock's ticker, not a preferred series


def test_the_market_calendar_gives_each_days_companies_with_their_session():
    rows = us_calendar.earnings_rows(fixture("calendar_earnings_2026-10-28.json"), date(2026, 10, 28))
    by = {r["symbol"]: r for r in rows}
    assert by["MSFT"] == {"symbol": "MSFT", "name": "Microsoft Corporation", "date": "2026-10-28", "hour": "amc", "period": "Sep/2026"}
    assert by["GEV"]["hour"] == "bmo" and "GOOGL" in by
    assert us_calendar.earnings_rows(fixture("calendar_earnings_2026-10-24.json"), date(2026, 10, 24)) == []    # a Saturday: none


class EmptyFeed:
    """The company data's whole-market list as it answered on 24 Oct: nothing for three weeks of earnings season."""
    def __init__(self): self.asked = []
    def earnings_between(self, frm, to, ttl=3600): return []
    def earnings_calendar(self, sym):
        self.asked.append(sym)
        return []


class Cal:
    def __init__(self, days: dict, down=()):
        self.days, self.down = days, set(down)
    def earnings(self, d):
        if d.isoformat() in self.down:
            raise SourceError("calendar", "busy", busy=True)
        return us_calendar.earnings_rows(self.days.get(d.isoformat(), {}), d)


class Search:
    def __init__(self, days: dict): self.days = days
    def earnings_filed(self, d): return sec.earnings_hits(self.days[d.isoformat()]) if d.isoformat() in self.days else []


def test_an_empty_answer_for_the_whole_market_is_not_stored_as_no_results(w):
    out = R.refresh("US", {"us": EmptyFeed()}, set(), date(2026, 10, 24))
    assert out["rows"] is None and "came back empty" in out["problems"][0]
    assert R.load("US")["at"] is None                                 # the empty answer isn't stored as "no company reports"


def test_a_us_list_stored_by_an_older_reader_is_read_again_by_the_job_at_once(w):
    """RC1-005: the list stored empty before the market calendar was the source stayed empty until the next 06:00 slot."""
    srcs = {"us": EmptyFeed(), "cal": Cal({"2026-10-28": fixture("calendar_earnings_2026-10-28.json")}), "sec": None, "in": None}
    db.set_setting(R.KEY + "US", json.dumps({"at": "2026-10-23T06:00", "rows": []}))             # as the first reader left it: no version
    assert R.load("US")["v"] == 1
    job = R.Job(lambda: srcs, send=lambda *a, **k: None, can_alert=lambda p: False)
    job.tick(datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc))            # a Saturday morning in New York, before the 06:00 slot's day mark is looked at
    got = R.load("US")
    assert got["v"] == R.CAL_VERSION and any(r["symbol"] == "MSFT" for r in got["rows"])


def test_the_us_calendar_has_this_week_and_next_from_the_calendar_and_the_secs_releases(w):
    today = date(2026, 10, 24)
    srcs = {"us": EmptyFeed(), "cal": Cal({"2026-10-28": fixture("calendar_earnings_2026-10-28.json")}),
            "sec": Search({"2026-10-21": fixture("efts_8k_2026-10-21.json")})}
    out = R.refresh("US", srcs, {"AAPL"}, today)
    assert out["rows"] and not srcs["us"].asked                       # the calendar answered: nobody is asked one by one
    rows = {(r["symbol"], r["date"]): r for r in R.load("US")["rows"]}
    msft = rows[("MSFT", "2026-10-28")]
    assert msft["when"] == "after the close" and msft["purpose"] == "Quarterly results (quarter ended Sep 2026)" and msft["name"] == "Microsoft"
    tsla = rows[("TSLA", "2026-10-21")]                               # reported: its earnings release is on its row
    assert tsla["out"]["title"] == "Earnings release (8-K)" and tsla["out"]["url"].startswith("https://www.sec.gov/Archives/")
    assert rows[("IBM", "2026-10-21")]["name"] == "IBM"                 # the SEC's capitals, as the company pages name it
    v = R.view("US", "u-pro", "all", today=today)
    assert sum(len(wk["rows"]) for wk in v["weeks"]) >= 14
    assert [d["date"] for d in v["weeks"][1]["days"]] == ["2026-10-28"]


def test_a_release_filed_for_a_dated_row_lands_on_it_and_tells_its_people(w):
    rows = [R.row("US", "TSLA", date(2026, 10, 21), "Quarterly results", when="after the close")]
    filed = sec.earnings_hits(fixture("efts_8k_2026-10-21.json"))
    out = R.with_filings(rows, filed, date(2026, 10, 22))
    tsla = next(r for r in out if r["symbol"] == "TSLA")
    assert tsla["when"] == "after the close" and tsla["out"]["at"] == "2026-10-21" and tsla["told"] is False
    assert len([r for r in out if r["symbol"] == "TSLA"]) == 1        # one row, not a second one for the filing
    old = R.with_filings([], filed, date(2026, 11, 20))
    assert all("told" not in r for r in old)                          # a release from weeks ago is listed, nobody is told


def test_a_calendar_day_that_didnt_answer_keeps_the_dates_it_had(w):
    today = date(2026, 10, 24)
    full = Cal({"2026-10-28": fixture("calendar_earnings_2026-10-28.json")})
    R.refresh("US", {"us": EmptyFeed(), "cal": full}, set(), today)
    R.refresh("US", {"us": EmptyFeed(), "cal": Cal({"2026-10-27": {"data": {"rows": [{"symbol": "KO", "time": "time-pre-market"}]}}},
                                                   down={"2026-10-28"})}, set(), today)
    days = {(r["symbol"], r["date"]) for r in R.load("US")["rows"]}
    assert ("MSFT", "2026-10-28") in days and ("KO", "2026-10-27") in days


def test_the_results_job_reads_the_us_calendar_and_the_secs_search():
    src = Path(main.__file__).read_text()
    assert '"cal": us_market_calendar, "sec": sec_feed' in src


# ---------- DE-026, DE-027: India's list by day, every day said, a bare intimation named for what it is ----------
def test_every_day_is_listed_with_its_count_and_a_long_day_opens_in_full(w, monkeypatch):
    today = date(2026, 10, 24)
    meetings = [{"bm_symbol": f"CO{i:03d}", "bm_date": "31-Oct-2026", "bm_purpose": "Financial Results", "bm_desc": "results"} for i in range(66)]
    meetings += [{"bm_symbol": f"TU{i:03d}", "bm_date": "27-Oct-2026", "bm_purpose": "Financial Results", "bm_desc": "results"} for i in range(5)]

    class Feed:
        def board_meetings(self, f, t): return meetings
    R.refresh("IN", {"in": Feed()}, set(), today)
    v = R.view("IN", "u-pro", "all", today=today, limit=40)
    nxt = v["weeks"][1]
    assert nxt["days"] == [{"date": "2026-10-27", "count": 5, "shown": 5}, {"date": "2026-10-31", "count": 66, "shown": 40}]
    assert v["more"] == 26 and len(nxt["rows"]) == 45                 # Saturday is there, with its first 40 and its count
    full = R.view("IN", "u-pro", "all", today=today, limit=40, day="2026-10-31")
    assert full["weeks"][1]["days"][1] == {"date": "2026-10-31", "count": 66, "shown": 66} and full["more"] == 0


def test_a_bare_board_meeting_intimation_is_named_for_the_results_it_is_for():
    raw = fixture("nse_board_meetings.json")
    ntpc_alone = [r for r in raw if r["bm_symbol"] == "NTPC" and r["bm_purpose"] == "Board Meeting Intimation"]
    assert R.india_rows(ntpc_alone)[0]["purpose"] == "Financial Results/Dividend"
    rows = {r["symbol"]: r for r in R.india_rows(raw)}
    assert set(rows) == {"NTPC", "ADVENZYMES", "ATULAUTO"}            # one each, the fund raise isn't a results meeting
    assert rows["NTPC"]["purpose"] == "Financial Results/Dividend" and rows["NTPC"]["url"].endswith("INTIMTIONOFBOD.pdf")


# ---------- DE-028, DE-029, DE-030, DE-031: corporate actions ----------
def test_declared_us_dividends_come_from_the_market_calendar():
    rows = us_calendar.dividend_rows(fixture("calendar_dividends_2026-10-30.json"))
    lnt = next(r for r in rows if r["symbol"] == "LNT")
    assert lnt == {"symbol": "LNT", "name": "Alliant Energy Corporation Common Stock", "ex_date": "2026-10-30", "record_date": "2026-10-30",
                   "pay_date": "2026-11-16", "declared": "2026-10-15", "amount": 0.535}
    got = CA.calendar_dividends(rows, {"LNT", "CASY"})
    assert [r["symbol"] for r in got] == ["CASY", "LNT"] or [r["symbol"] for r in got] == ["LNT", "CASY"]
    row = next(r for r in got if r["symbol"] == "LNT")
    assert row["id"] == "LNT|dividend|2026-10-30|dividend" and row["name"] == "Alliant Energy Corporation" and row["pay_date"] == "2026-11-16"
    assert row["src"] == "market calendar" and row["text"] == "Dividend $0.535 a share"


def test_the_us_calendar_lists_dividends_ahead(w, monkeypatch):
    today = date(2026, 10, 26)
    monkeypatch.setattr(CA, "us_universe", lambda tracked=(): ["LNT", "CASY", "AGNC"])

    class DivCal:
        def dividends(self, d):
            return us_calendar.dividend_rows(fixture("calendar_dividends_2026-10-30.json")) if d.isoformat() == "2026-10-30" else []
    out = CA.refresh("US", {"us": None, "cal": DivCal()}, set(), today)
    assert out["rows"] >= 3
    v = CA.view("US", "u-pro", "all", today=today)
    assert v["ahead_known"] and {r["symbol"] for r in v["ahead"]} == {"LNT", "CASY", "AGNC"}
    # the daily read of the price histories keeps the declared dividends still ahead
    CA.refresh_universe({"us": None}, symbols=[], today=today, pace=0)
    assert {r["symbol"] for r in CA.load("US")["rows"] if r["ex_date"] >= today.isoformat()} == {"LNT", "CASY", "AGNC"}


ANANTAM = ("Distribution - Rs 2.75 Per Unit Consist Of Re 0.60821 Per Unit As Interest/ Re 0.34940 Per Unit As Dividend/ "
           "Rs 1.78940 Per Unit As Capital Repayment/Re 0.00299 Per Unit As Other Income")


def test_a_trusts_distribution_is_one_action_with_its_parts():
    got = CA.parse_purpose(ANANTAM)
    assert len(got) == 1 and got[0]["kind"] == "dividend" and got[0]["label"] == "Distribution" and got[0]["amount"] == 2.75
    assert [p["label"] for p in got[0]["parts"]] == ["interest", "dividend", "capital repayment", "other income"]
    assert got[0]["text"] == "Distribution ₹2.75 a unit: ₹0.6082 interest, ₹0.3494 dividend, ₹1.7894 capital repayment, ₹0.003 other income"
    rows = CA.india_rows([{"symbol": "ANANTAM", "comp": "Anantam Highways Trust", "exDate": "27-Oct-2026", "recDate": "27-Oct-2026",
                           "subject": ANANTAM, "faceVal": "100"}])
    assert len(rows) == 1 and rows[0]["parts"][1] == {"label": "dividend", "amount": 0.3494}
    assert CA.parse_purpose("Interim Dividend - Rs 9 Per Share")[0]["text"] == "Interim dividend ₹9 a share"


def test_a_price_history_adjustment_that_is_no_split_ratio_isnt_a_split():
    got = CA.us_rows("CTVA", {"splits": [{"date": "2026-10-01", "numerator": 6665, "denominator": 1000}],
                              "dividends": []})
    assert got[0]["kind"] == "demerger" and got[0]["label"] == "Price adjustment" and not CA.adjusts(got[0])
    assert "6.665 for 1" in got[0]["text"]
    split = CA.us_rows("NVDA", {"splits": [{"date": "2024-06-10", "numerator": 10, "denominator": 1}]})[0]
    assert split["kind"] == "split" and CA.adjusts(split) and CA.split_ratio(3, 2) and CA.split_ratio(1, 20)


def test_a_stored_split_row_that_is_no_split_ratio_is_a_price_adjustment_when_read_back(w):
    """RC1 DE-030: the calendar and the history kept CTVA's row as a split before the reader knew better."""
    old = CA.row("US", "CTVA", {"kind": "split", "sub": "6665:1000", "label": "Split", "text": "Split 6665-for-1000", "short": "split 6665-for-1000",
                                "factor": 6.665}, date(2026, 10, 1), src="price history")
    nvda = CA.row("US", "NVDA", {"kind": "split", "sub": "10:1", "label": "Split", "text": "Split 10-for-1", "short": "split 10-for-1", "factor": 10.0},
                  date(2024, 6, 10), src="price history")
    CA.save("US", [old, nvda])
    CA.hist_save("US", "CTVA", [old])
    for rows in (CA.load("US")["rows"], CA.hist_load("US", "CTVA")["rows"]):
        ctva = next(r for r in rows if r["symbol"] == "CTVA")
        assert ctva["kind"] == "demerger" and ctva["label"] == "Price adjustment" and not CA.adjusts(ctva)
    assert next(r for r in CA.load("US")["rows"] if r["symbol"] == "NVDA")["kind"] == "split"


def test_the_us_page_says_why_nothing_is_ahead(w, monkeypatch):
    today = date(2026, 10, 26)
    monkeypatch.setattr(CA, "us_universe", lambda tracked=(): ["LNT"])

    class Down:
        def dividends(self, d):
            raise CA.SourceError("calendar", "down")

    class Empty:
        def dividends(self, d):
            return []
    # the calendar never read: said to be unread, not "none declared"
    CA.refresh("US", {"us": None, "cal": Down()}, set(), today)
    v = CA.view("US", "u-pro", "all", today=today)
    assert not v["ahead_known"] and v["ahead"] == [] and "couldn't be read" in v["ahead_note"]
    # read, and none of the companies covered has one: said so
    CA.refresh("US", {"us": None, "cal": Empty()}, {"LNT"}, today)
    v = CA.view("US", "u-pro", "all", today=today)
    assert v["ahead_known"] and "No dividend is declared" in v["ahead_note"]
    assert CA.view("IN", "u-pro", "all", today=today)["ahead_note"] == "Nothing announced with an ex-date ahead."


def test_a_themes_central_point_is_a_phrase_never_a_sentence_run_into_the_page_lead():
    """RC1-009: "Everything converges on Domestic self-reliance in defence hardware… is the central." """
    from app.intel import ai
    assert ai.core_phrase("Domestic self-reliance in defence hardware... is the central.") == "Domestic self-reliance in defence hardware"
    assert ai.core_phrase("Domestic self-reliance in defence hardware… is the central pillar of the theme.") == "Domestic self-reliance in defence hardware"
    assert ai.core_phrase("Indigenous production of defence platforms.") == "Indigenous production of defence platforms"
    assert ai.core_phrase("Defence.") == "" and ai.core_phrase("") == ""
    assert ai.theme_served({"core": "Domestic orders… is the central."})["core"] == "Domestic orders"


# ---------- DE-032 to DE-036: red flags ----------
def test_a_companys_red_flags_come_from_the_stored_read_when_its_own_list_doesnt_answer(monkeypatch):
    monkeypatch.setattr(redflags, "state", lambda region: {"through": "2026-10-23"})
    flags_ = [{"id": "1", "symbol": "NTPC", "company": "NTPC", "at": "2026-10-20T10:00", "category": "pledge", "label": "Promoter pledge or encumbrance",
               "severity": "red", "subject": "Disclosure of pledge", "url": "https://nsearchives.nseindia.com/a.pdf", "text": "creation of pledge"},
              {"id": "2", "symbol": "TCS", "company": "TCS", "at": "2026-10-20T10:00", "category": "qip", "label": "QIP (fund raise)",
               "severity": "red", "subject": "QIP", "url": None, "text": "qualified institutions placement approved"}]
    monkeypatch.setattr(redflags.flags, "between", lambda region, frm, to: flags_)
    got = redflags.stored_rows(["NTPC", "HEXT"], today=date(2026, 10, 24))
    assert got["NTPC"]["stored"] and got["NTPC"]["summary"]["red"] == 1 and got["NTPC"]["summary"]["total"] is None
    assert got["NTPC"]["flags"][0]["subject"] == "Disclosure of pledge"
    assert got["HEXT"]["summary"]["red"] == 0 and got["HEXT"]["flags"] == []          # read, nothing flagged


def test_the_watchlist_view_shows_a_slow_company_from_the_stored_read():
    src = Path(main.__file__).read_text()
    assert "redflags.stored_rows(unread)" in src


def test_a_company_still_being_read_is_said_so_the_page_asks_again():
    import threading
    gate = threading.Event()

    class Slow:
        def announcements(self, sym, days=365):
            if sym == "NTPC":
                gate.wait(3)
            return []
    out = filings.overview(Slow(), ["NTPC", "TCS"], wait=0.3)
    gate.set()
    assert out["reading"] == ["NTPC"] and [r["symbol"] for r in out["rows"]] == ["TCS"]


@pytest.mark.parametrize("desc,text,cid,sev", [
    ("Credit Rating- Revision", "Kirloskar Electric Company Limited has informed the Exchange about Credit Rating- Revision received from Crisil ratings Limited.",
     "rating_revised", "amber"),
    ("Credit Rating- Revision", "ICRA has reaffirmed the rating at AA", "rating", "info"),
    ("Credit Rating", "CRISIL has downgraded the long-term rating to BBB", "rating_down", "red"),
    ("News Verification", "The Exchange has sought clarification from Grasim Industries Limited with respect to recent news item captioned "
     "Bombay HC Quashes Rs 329 Crore Tax Claim Against Grasim Over Vodafone Idea Rights Issue.", "news_clarification", "info"),
    ("Monitoring Agency Report", "monitoring agency report for the quarter on the proceeds of the preferential issue and QIP", "other", "info"),
    ("Resignation of Director/KMP/SMP", "Bajaj Housing Finance Limited has informed the Exchange about Resignation of Director/KMP/SMP",
     "resign_unnamed", "amber"),
    ("Resignation", "Bajaj Housing Finance Limited has informed the Exchange regarding Resignation of Gaurav Kalani - Chief Financial Officer",
     "kmp_resign", "amber"),
])
def test_rating_revisions_news_verifications_and_resignations(desc, text, cid, sev):
    assert filings.classify(desc, text) == (cid, sev)


def test_the_bare_resignation_form_beside_the_letter_is_one_resignation():
    letter = {"id": "106826590", "symbol": "BAJAJHFL", "at": "2026-10-23T17:03", "category": "kmp_resign", "severity": "amber",
              "subject": "Resignation", "text": "Resignation of Gaurav Kalani - Chief Financial Officer"}
    form = {"id": "106826616", "symbol": "BAJAJHFL", "at": "2026-10-23T17:09", "category": "resign_unnamed", "severity": "amber",
            "subject": "Resignation of Director/KMP/SMP", "text": "about Resignation of Director/KMP/SMP"}
    got = filings.one_per_filing([letter, form])
    assert len(got) == 1 and got[0]["id"] == "106826590" and got[0]["copies"] == 2
    alone = filings.one_per_filing([{**form, "symbol": "XCHANGING"}])
    assert len(alone) == 1 and alone[0]["category"] == "resign_unnamed"
    assert {"id": "resign_unnamed", "label": "Resignation filed (who isn't stated)", "severity": "amber"} in redflags.types("IN")


def test_the_us_tab_is_your_stocks_like_indias():
    src = Path(redflags.__file__).with_name("redflags_routes.py").read_text()
    assert "results.my_stocks(profile[\"id\"], region)" in src


# ---------- DE-001, DE-002, DE-003, DE-005, DE-006, DE-008: the trend scan ----------
class FakeChart:
    def __init__(self, series): self.series, self.asked = series, []
    def chart(self, symbol, tf="1d", days=365, **k):
        self.asked.append(symbol)
        return {"candles": self.series[symbol]}


def test_indian_scans_run_on_the_last_close_while_the_broker_is_offline(monkeypatch):
    up = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 185, 12)) + list(np.linspace(185, 198, 4))
    yahoo = FakeChart({"TCS.NS": bars_from(up), "500325.BO": bars_from(list(np.linspace(200, 90, 320)))})
    scan._cache.clear()
    monkeypatch.setattr(scan, "session_day", lambda market, now=None: None)
    reg = scan.LastCloseIndia(yahoo)
    out = scan.run(reg, "IN", [{"symbol": "TCS"}, {"symbol": "500325"}])
    assert [r["symbol"] for r in out["rows"]] == ["TCS", "500325"] and out["rows"][0]["signal"] == "fresh"
    assert yahoo.asked == ["TCS.NS", "500325.BO"] or set(yahoo.asked) == {"TCS.NS", "500325.BO"}
    assert out["rows"][0]["id"] == "IN:close:TCS"                    # never mixed up with a broker token's candles
    pre = scan.run_preset(reg, "IN", [{"symbol": "TCS"}], "high52")
    assert pre["checked"] == 1


def test_the_scan_route_reads_the_last_close_when_indian_data_is_offline():
    src = Path(main.__file__).read_text()
    assert "registry, offline = scan.LastCloseIndia(research_hub.yahoo), True" in src and 'out["last_close"] = offline' in src


def test_the_offline_message_names_the_day(monkeypatch):
    nxt = datetime.now(main.IST).replace(hour=8, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(main, "next_auto_login", lambda: nxt.isoformat())
    got = main.offline_when("Market data for this market is offline right now.")
    assert f"on {nxt:%a} {nxt.day} {nxt:%b} at 08:00 IST" in got and "today" not in got


def test_a_500_stock_groups_stage_2_scan_has_the_small_groups_layout():
    up = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 185, 12)) + list(np.linspace(185, 198, 4))
    got = scan_presets.evaluate(bars_from(up), only=["st_s2"])
    m = got["matches"]["st_s2"]
    small = scan.analyse(bars_from(up))
    assert m["st_days"] == small["st_days"] and m["stage_days"] == small["stage_days"]
    doc = scan_presets.build({"AAA": got})
    assert doc["rows"][0]["m"]["st_s2"][3]["st_days"] == m["st_days"]
    view = {"rows": [{"symbol": "AAA", "price": 198.0, "chg": 1.0, "as_of": got["as_of"], "st_days": 3, "stage_days": 200},
                     {"symbol": "BBB", "price": 50.0, "chg": 0.5, "as_of": got["as_of"], "st_days": 40, "stage_days": 90}],
            "checked": 501, "matches": 2, "as_of": got["as_of"], "updated_at": None}
    out = main.stored_st_s2("US", view)
    assert out["kind"] == "st_s2" and out["checked"] == 501 and out["counts"] == {"fresh": 1, "st_s2": 1, "stage2": None}
    assert [r["signal"] for r in out["rows"]] == ["fresh", "st_s2"] and out["rows"][0]["stage"] == 2
    older = main.stored_st_s2("US", {**view, "rows": [{"symbol": "AAA", "price": 1.0, "chg": 0.0, "as_of": "2026-10-23"}]})
    assert older["counts"]["fresh"] is None                           # stored before the days were kept: no split claimed


def test_us_names_are_clean(monkeypatch):
    monkeypatch.setattr(stock_pages, "companies", lambda region: {"MSFT": {"name": "MICROSOFT CORP"}, "COST": {"name": "COSTCO WHOLESALE CORP /NEW"},
                                                                   "LLY": {"name": "ELI LILLY & Co"}})
    assert scan.company_name("US", {"symbol": "MSFT"}, "US:MSFT") == "Microsoft Corp"
    assert scan.company_name("US", {"symbol": "COST"}, "US:COST") == "Costco Wholesale Corp"
    assert scan.company_name("US", {"symbol": "LLY"}, "US:LLY") == "Eli Lilly & Co"


def test_the_pullback_rule_says_ema():
    assert "20-day exponential average (EMA)" in scan_presets.BY_ID["pullback"]["text"]


def test_the_scan_alert_answer_says_where_it_goes():
    src = Path(main.__file__).read_text()
    assert 'return {"alerts": req.on, "channels": stock_alerts.channels(profile)}' in src


# ---------- DE-009, DE-010: the screener ----------
def test_a_condition_says_how_many_companies_it_leaves_out_for_want_of_a_figure():
    rows = [{"symbol": "TCS", "name": "TCS", "sector": "IT", "stage": None, "pe": 17.7},
            {"symbol": "INFY", "name": "Infosys", "sector": "IT", "stage": None, "pe": None},
            {"symbol": "WIPRO", "name": "Wipro", "sector": "IT", "stage": 1, "pe": 18.0}]
    f = screens.clean("IN", {"stage": [1], "ranges": {"pe": {"min": 10}}})
    # TCS meets the P/E condition and has no Stage; INFY has neither figure, so the Stage condition alone isn't what drops it
    assert screens.no_value("IN", rows, f) == {"stage": 1}
    assert screens.no_value("IN", rows, screens.clean("IN", {"ranges": {"pe": {"min": 10}}})) == {"pe": 1}
    with pytest.raises(screens.ScreenError):
        screens.clean("IN", {"ranges": {"pe": {"min": 50, "max": 10}}})


def test_a_price_read_without_a_stage_keeps_the_pages_stage():
    f = {"price": 2500.0, "price_at": "2026-10-22", "stage": 1, "stage_days": 6}
    new = stock_pages.with_new_close(f, bars_from([2500.0] * 40, start=datetime(2026, 9, 14, tzinfo=timezone.utc)),
                                     analyse=lambda bars: {"stage": None, "stage_days": None, "st_up": True, "st_days": 3})
    assert new["stage"] == 1 and new["stage_days"] == 6


def test_a_candle_without_a_price_does_not_blank_the_stage_and_old_pages_are_rebuilt():
    bars = [{"t": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": 100 + i * 0.1, "h": 101 + i * 0.1, "l": 99 + i * 0.1, "c": 100 + i * 0.1, "v": 1}
            for i in range(240)]
    bars[200] = {**bars[200], "c": float("nan"), "o": None}
    got = scan.analyse(bars)
    assert got is not None and got["stage"] in (1, 2, 3, 4)
    # the pages stored with a blank Stage (RC1: TCS, INFY) are from before the version that rebuilds them
    assert stock_pages.FACTS_VERSION >= 9
    assert not stock_pages.fresh({"ts": 9e12, "facts": {"v": 8, "stage": None}}, "IN", now=9e12)


# ---------- DE-013, DE-014, DE-015: themes ----------
LISTED = [{"symbol": "LT", "name": "LARSEN & TOUBRO LTD."}, {"symbol": "LTM", "name": "LTIMindtree Ltd"},
          {"symbol": "HAL", "name": "Hindustan Aeronautics Ltd"}, {"symbol": "BEL", "name": "Bharat Electronics Ltd"}]


def lookup(q, region):
    q = q.upper()
    return [r for r in LISTED if r["symbol"] == q or q.split()[0] in r["name"].upper()]


def test_a_theme_map_lists_only_listed_companies_under_their_listed_names():
    ai = {"sector": "India defence", "screen": [{"name": "Hindustan Aeronautics", "ticker": "HAL", "layer": "Aircraft", "one_line": "x"}],
          "clusters": [{"name": "Systems", "companies": [{"name": "Larsen & Toubro Defence", "ticker": "LT"}, {"name": "Larsen & Toubro", "ticker": "LT"},
                                                          {"name": "Larsen & Toubro Infotech", "ticker": ""}, {"name": "Agni Corp", "ticker": "AGNI"}]}],
          "value_chain": [], "etfs": []}
    out = grounding.ground_sector(ai, "IN", lookup)
    assert [(c["ticker"], c["name"]) for c in out["clusters"][0]["companies"]] == [("LT", "Larsen & Toubro Ltd.")]
    assert out["screen"][0]["name"] == "Hindustan Aeronautics Ltd"
    kept = grounding.listed_only({"clusters": [{"name": "x", "companies": [{"name": "LTI (not listed)", "ticker": "", "listed": False}]}], "value_chain": []})
    assert kept["clusters"] == []


def test_the_exchanges_own_list_of_the_themes_industries_is_beside_the_map():
    out = {"sector": "India defence", "screen": [{"ticker": "HAL"}, {"ticker": "BEL"}], "clusters": [], "value_chain": []}
    rows = [{"symbol": s, "name": n, "industry": i} for s, n, i in (
        ("HAL", "Hindustan Aeronautics Ltd", "Aerospace & Defense"), ("BEL", "Bharat Electronics Ltd", "Aerospace & Defense"),
        ("BDL", "Bharat Dynamics Ltd", "Aerospace & Defense"), ("DATAPATTNS", "Data Patterns (India) Ltd", "Aerospace & Defense"),
        ("TCS", "Tata Consultancy Services Ltd", "Computers - Software & Consulting"))]
    got = grounding.exchange_list(out, rows)
    assert got["industries"] == ["Aerospace & Defense"] and got["total"] == 4
    assert [(c["ticker"], c["named"]) for c in got["companies"]] == [("BDL", False), ("BEL", True), ("DATAPATTNS", False), ("HAL", True)]


def test_theme_text_states_no_unverifiable_figure():
    t = "Spending rose to Rs 5.5 lakh crore (+12%). Programmes like the light combat aircraft are under way, with strategic offset mandates,."
    assert A.theme_text(t, 900) == "Programmes like the light combat aircraft are under way, with strategic offset mandates."
    kept = A.theme_served({"summary": "The budget is ₹5.5 lakh crore (AI estimate). Shipyards build frigates.", "tailwinds": ["A 12% rise (AI estimate)."],
                           "risks": [], "sub_themes": [], "value_chain": [], "screen": []})
    assert kept["summary"] == "Shipyards build frigates." and kept["tailwinds"] == []


def test_letters_that_spell_nothing_are_asked_about_before_an_ai_read():
    vocab = grounding.vocabulary([{"name": "Hindustan Aeronautics Ltd", "industry": "Aerospace & Defense"}])
    assert not grounding.looks_like_theme("asdkjh qwe zzz", vocab)
    for q in ("India defence", "AI data centers", "grid electrification", "quantum computing", "GLP-1 drugs", "railways capex"):
        assert grounding.looks_like_theme(q, vocab), q


def test_the_theme_route_checks_the_words_and_serves_todays_checks():
    src = Path(grounding.__file__).with_name("routes.py").read_text()
    assert "grounding.looks_like_theme(theme, grounding.vocabulary(rows))" in src
    assert "grounding.listed_only(A.theme_served(got))" in src and '"exchange": grounding.exchange_list(got, rows)' in src


# ---------- DE-016, DE-017: the market pulse ----------
US = [{"name": "S&P 500", "price": 7623.68, "high52": 7843.0, "low52": 6000.0}, {"name": "Nasdaq", "price": 25955.34, "high52": 27500.0, "low52": 20000.0},
      {"name": "Dow Jones", "price": 52215.16, "high52": 53800.0, "low52": 44000.0}]


def test_well_below_the_highs_is_said_only_when_it_is():
    assert not grounding.range_claims_ok("All three indices closed well below their 52-week highs.", US)
    far = [{**i, "high52": i["price"] * 1.2} for i in US]
    assert grounding.range_claims_ok("All three indices closed well below their 52-week highs.", far)
    assert not grounding.range_claims_ok("The S&P 500 sits well below its 52-week high.", US)


def test_near_repeat_headlines_fold_and_a_cut_word_goes():
    items = [{"headline": "Sensex falls 600 points: Why is stock market down today?", "at": "2026-10-23T10:00"},
             {"headline": "Sensex down 500 points today: Why is stock market falling today?", "at": "2026-10-22T10:00"},
             {"headline": "Surging oil prices drag Indian shares to weekly losses", "at": "2026-10-23T09:00"}]
    got = company.grouped(items)
    assert [g["headline"] for g in got] == ["Sensex falls 600 points: Why is stock market down today?", "Surging oil prices drag Indian shares to weekly losses"]
    assert got[0]["similar"] == 1
    assert company.whole_words("Key factors behind Rs 3 lak") == "Key factors behind Rs 3…"
    assert company.whole_words("Sensex falls 600 points") == "Sensex falls 600 points"


# ---------- DE-018: "4 weeks ago" is four weeks ago ----------
def test_a_kept_copy_of_the_old_shape_is_worked_out_again(monkeypatch):
    from tests.fake_db import FakeSupabase
    monkeypatch.setattr(db, "_client", FakeSupabase())
    ran = []

    class Prov:
        def ready(self): return True
    monkeypatch.setattr(main.markets, "provider", lambda r: Prov())
    monkeypatch.setattr(main.stock_pages, "last_close", lambda r, now=None: (date(2026, 10, 22), None))
    monkeypatch.setattr(main.rotation, "run", lambda m, region, s, mem, interval, tail: ran.append((region, interval)) or
                        {"rows": [1], "skipped": [], "as_of": "2026-10-22", "v": rotation.VERSION})
    for r in ("IN", "US"):
        for iv in ("weekly", "daily"):
            db.set_setting(f"rotation:last:{r}:sectors:{iv}:5", json.dumps({"rows": [1], "as_of": "2026-10-22", "v": rotation.VERSION}))
    db.set_setting("rotation:last:IN:sectors:weekly:5", json.dumps({"rows": [1], "as_of": "2026-10-22"}))     # kept before DE-018
    assert main.rotation_after_close(datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)) == ["IN weekly"]


def test_the_weeks_ago_column_reads_the_point_that_many_weeks_back():
    days = [datetime(2025, 1, 3) + timedelta(days=7 * i) for i in range(80)]
    bench = [{"t": d.date().isoformat(), "c": 100.0 + i * 0.1} for i, d in enumerate(days)]
    mem = [{"t": d.date().isoformat(), "c": 100.0 + i * 0.1 + (5 if i % 9 < 4 else -5)} for i, d in enumerate(days)]
    m, b = rotation.closes(mem, "weekly"), rotation.closes(bench, "weekly")

    class Reg:
        def provider(self, m): return None
    load = lambda iid, n: mem if iid == "US:XLK" else bench               # noqa: E731
    out = rotation.compute(Reg(), "US", [("US:XLK", "XLK")], "weekly", 4, load, bench=("US:SPY", "SPY"))
    row = out["rows"][0]
    pts = rotation.path(m, b, 5)
    assert len(row["points"]) == 5 and row["points"] == pts                 # four weekly steps behind the dot
    assert row["moved"] == rotation.quadrant(pts[0]["x"], pts[0]["y"]) and out["v"] == rotation.VERSION


# ---------- DE-024: the sector table adds up ----------
def test_a_sector_too_small_for_the_table_is_named(monkeypatch):
    days = [f"2026-10-{d:02d}" for d in range(1, 24)]
    monkeypatch.setattr(breadth, "load_sectors", lambda g: {"days": days, "sectors": {
        "Diversified": {"a": [2] * 23, "n": [4] * 23}, "Energy": {"a": [10] * 23, "n": [20] * 23}}})
    t = breadth.sector_table("nifty500")
    assert [r["sector"] for r in t["rows"]] == ["Energy"] and t["small"] == [{"sector": "Diversified", "stocks": 4}] and t["min_stocks"] == 5
