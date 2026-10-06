"""Red-flag filings across every company (India: the exchange's list for the whole market; US: Form 8-K items) and US
holders above 5% (Schedule 13D and 13G): the rows read, the monthly store, the daily runs and job, the paged and
filtered list, the endpoints and facts-only wording."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, main, redflags as R, universes, us_holders as U
from app.intel import filings as F
from app.intel.net import SourceError
from app.intel.sec import SEC

FIX = Path(__file__).parent / "fixtures" / "us_holders"
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|best|cheap|expensive|bullish|bearish|target|should|recommend)\b", re.I)
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)
TODAY = date(2026, 10, 6)


@pytest.fixture
def mem(monkeypatch):
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    R.forget()
    yield store
    R.forget()


def nse(symbol, desc, when, text="", name=None, seq=None):
    return {"symbol": symbol, "sm_name": name or f"{symbol.title()} Limited", "desc": desc, "attchmntText": text, "sort_date": when,
            "seq_id": seq or f"{symbol}-{when}", "attchmntFile": "https://nsearchives.nseindia.com/c/x.pdf"}


def flag(symbol="ABC", at="2026-10-01T10:00", cat="auditor_resign", sev="red", region="IN", n=1):
    return {"id": f"{symbol}|{at}|{cat}|{n}", "symbol": symbol, "company": f"{symbol} Ltd", "at": at, "category": cat,
            "label": F.LABEL.get(cat, cat), "severity": sev, "subject": "x", "url": None}


# ---------- reading the exchange's whole-market list ----------
def test_flagged_rows_keep_red_and_amber_with_symbol_and_company():
    rows = F.flagged_rows([
        nse("ABC", "Change in Auditors", "2026-10-01 18:10:05", "Resignation of the Statutory Auditor"),
        nse("DEF", "Change in Directorate", "2026-10-02 10:00:00", "Resignation of Mr X as Independent Director", name="Def Industries Limited"),
        nse("GHI", "Outcome of Board Meeting", "2026-10-02 11:00:00", "Financial Results for the quarter"),       # routine: left out
        nse("ABC", "Change in Auditors", "2026-10-01 18:10:05", "Resignation of the Statutory Auditor", seq="dup"),  # the same filing again
        nse("bad symbol!", "Change in Auditors", "2026-10-01 18:10:05", "Resignation of the Statutory Auditor"),
        {"symbol": "JKL", "desc": "Qualified Institutions Placement", "sort_date": ""},                         # no date
        "junk",
    ])
    assert [r["symbol"] for r in rows] == ["ABC", "DEF"]
    a, d = rows
    assert a["category"] == "auditor_resign" and a["severity"] == "red" and a["company"] == "Abc Limited" and a["url"].startswith("https://")
    assert d["severity"] == "amber" and d["company"] == "Def Industries Limited"
    again = F.flagged_rows([nse("ABC", "Change in Auditors", "2026-10-01 18:10:05", "Resignation of the Statutory Auditor", seq="other")])
    assert again[0]["id"] == a["id"]                                          # the id depends on the filing, not on the feed's own number


def test_the_exchange_feed_reads_one_day_for_the_whole_market_and_keeps_the_answer():
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.url.path, dict(req.url.params)))
        if req.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "nsit=abc; Path=/"})
        return httpx.Response(200, json=[nse("ABC", "Change in Auditors", "2026-10-01 18:10:05", "Resignation of the Statutory Auditor")])
    feed = F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    out = feed.market_flags(date(2026, 10, 1))
    assert out[0]["symbol"] == "ABC"
    api = [c for c in calls if c[0] == "/api/corporate-announcements"]
    assert api[0][1] == {"index": "equities", "from_date": "01-10-2026", "to_date": "01-10-2026"} and "symbol" not in api[0][1]
    assert feed.market_flags(date(2026, 10, 1)) == out and len([c for c in calls if c[0] == "/api/corporate-announcements"]) == 1


def test_a_page_instead_of_the_list_is_an_error():
    def handler(req):
        return httpx.Response(200, text="<html></html>", headers={"set-cookie": "a=b"}) if req.url.path == "/" else httpx.Response(200, json={"oops": 1})
    with pytest.raises(SourceError):
        F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None).market_flags(date(2026, 10, 1))


# ---------- the monthly store ----------
def test_months_merge_by_id_and_read_a_date_range(mem):
    m = R.Months("redflags:")
    assert m.add("IN", [flag("A", "2026-09-30T10:00"), flag("B", "2026-10-02T10:00")]) == 2
    assert m.add("IN", [flag("A", "2026-09-30T10:00"), flag("C", "2026-10-03T10:00")]) == 1        # A is already there
    assert {k.split(":")[-1] for k in mem if k.startswith("redflags:IN:")} == {"2026-09", "2026-10"}
    got = m.between("IN", date(2026, 9, 30), date(2026, 10, 2))
    assert sorted(i["symbol"] for i in got) == ["A", "B"]
    assert m.between("IN", date(2026, 1, 1), date(2026, 1, 31)) == [] and m.between("US", date(2026, 9, 1), date(2026, 10, 31)) == []
    changed = {**flag("A", "2026-09-30T10:00"), "subject": "new"}
    m.add("IN", [changed])
    assert m.between("IN", date(2026, 9, 30), date(2026, 9, 30))[0]["subject"] == "x"                   # kept as stored
    m.add("IN", [changed], replace=True)
    assert m.between("IN", date(2026, 9, 30), date(2026, 9, 30))[0]["subject"] == "new"
    mem["redflags:IN:2026-08"] = "{not json"
    assert m.between("IN", date(2026, 8, 1), date(2026, 8, 31)) == []                                   # a damaged month reads as empty


# ---------- the India run ----------
class FakeNSE:
    def __init__(self, by_day=None, fail=(), busy=False):
        self.by_day, self.fail, self.busy, self.days = by_day or {}, set(fail), busy, []

    def market_flags(self, day):
        self.days.append(day)
        if day in self.fail:
            raise SourceError("the exchange", "down", busy=self.busy)
        return self.by_day.get(day, [])


def test_first_india_run_reads_back_45_days_and_the_next_overlaps_two(mem):
    feed = FakeNSE({date(2026, 10, 5): [flag("ABC", "2026-10-05T18:00")], date(2026, 9, 1): [flag("OLD", "2026-09-01T18:00")]})
    runner = R.Runner(lambda: {"in": feed}, sleep=lambda s: None, pause=0)
    out = runner.run("IN", TODAY)
    assert out["ok"] and out["through"] == "2026-10-06" and out["new"] == 2
    assert 0 <= (feed.days[0] - (TODAY - timedelta(days=45))).days <= 2 and feed.days[-1] == TODAY       # from 45 days back (the next weekday)
    assert all(d.weekday() < 5 or d == TODAY for d in feed.days)                          # weekdays only (and today)
    assert R.state("IN")["through"] == "2026-10-06" and R.state("IN")["days_read"] == len(feed.days)
    feed.days.clear()
    out = runner.run("IN", TODAY + timedelta(days=2))
    assert feed.days[0] == date(2026, 10, 5) and out["ok"]                                  # read again from two days back (Sunday is skipped)
    assert out["new"] == 0


def test_an_india_run_that_stops_midway_keeps_the_days_it_read(mem):
    feed = FakeNSE(fail={date(2026, 10, 2)}, busy=True)
    out = R.Runner(lambda: {"in": feed}, sleep=lambda s: None, pause=0).run("IN", TODAY)
    assert out["ok"] and out["through"] == "2026-10-01" and out["error"]                  # read to the day before the one that failed
    assert R.state("IN")["through"] == "2026-10-01"


def test_an_india_run_where_nothing_can_be_read_fails_and_says_why(mem):
    feed = FakeNSE(fail={TODAY - timedelta(days=i) for i in range(60)}, busy=True)
    runner = R.Runner(lambda: {"in": feed}, sleep=lambda s: None, pause=0)
    with pytest.raises(RuntimeError) as e:
        runner.run("IN", TODAY)
    assert "couldn't be read" in str(e.value) and R.state("IN")["failed_at"] and not R.state("IN").get("through")


def test_runs_go_one_at_a_time(mem):
    runner = R.Runner(lambda: {"in": FakeNSE()}, sleep=lambda s: None, pause=0)
    assert runner.lock.acquire()
    assert runner.run("IN", TODAY)["ok"] is False
    runner.lock.release()


# ---------- the US 8-K items ----------
def subs(cik=320193, rows=()):
    """A company's filing list: rows are (form, filed, accession, document, items)."""
    cols = list(zip(*rows)) or [[]] * 5
    return {"cik": str(cik), "name": "X", "filings": {"recent": dict(zip(("form", "filingDate", "accessionNumber", "primaryDocument", "items"), map(list, cols)))}}


EIGHT_K = [
    ("8-K", "2026-10-01", "0000320193-26-000100", "a8-k.htm", "4.01,9.01"),
    ("8-K", "2026-09-28", "0000320193-26-000099", "b8-k.htm", "5.02"),
    ("8-K", "2026-09-20", "0000320193-26-000098", "c8-k.htm", "2.02,9.01"),            # an earnings release: no flag
    ("8-K/A", "2026-09-15", "0000320193-26-000097", "d8-k.htm", "1.03,3.01,4.02"),
    ("10-Q", "2026-09-10", "0000320193-26-000096", "q.htm", ""),
    ("8-K", "2026-05-01", "0000320193-26-000010", "old.htm", "4.01"),                  # before the window
]


def test_us_items_matches_the_five_items_one_row_each():
    got = R.us_items(subs(rows=EIGHT_K), "AAPL", "Apple Inc.", date(2026, 7, 1))
    by = {(i["at"], i["category"]) for i in got}
    assert by == {("2026-10-01", "8k_4_01"), ("2026-09-28", "8k_5_02"), ("2026-09-15", "8k_1_03"), ("2026-09-15", "8k_3_01"), ("2026-09-15", "8k_4_02")}
    one = next(i for i in got if i["category"] == "8k_4_01")
    assert one["severity"] == "red" and one["symbol"] == "AAPL" and one["company"] == "Apple Inc." and one["label"].startswith("Change of auditor")
    assert one["url"] == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000100/a8-k.htm" and "Item 4.01" in one["subject"]
    assert next(i for i in got if i["category"] == "8k_5_02")["severity"] == "amber"
    assert len({i["id"] for i in got}) == len(got) and R.us_items({}, "X", None, date(2026, 7, 1)) == []
    assert R.us_items(subs(rows=EIGHT_K), "AAPL", None, date(2026, 10, 1))[0]["at"] == "2026-10-01"      # a shorter window


class FakeSEC:
    def __init__(self, by_cik, docs=None, fail=(), busy_docs=False):
        self.by_cik, self.docs, self.fail, self.busy_docs, self.reads, self.fresh = by_cik, docs or {}, set(fail), busy_docs, [], []

    def submissions(self, cik, fresh=False):
        self.fresh.append(fresh)
        if cik in self.fail:
            raise SourceError("The SEC", "down", busy=True)
        return self.by_cik[cik]

    def document(self, url):
        self.reads.append(url)
        if self.busy_docs:
            raise SourceError("The SEC", "busy", busy=True)
        return self.docs[url]


G13 = [("SCHEDULE 13G/A", "2026-09-30", "0000102909-26-000630", "xslSCHEDULE_13G_X02/primary_doc.xml", ""),
       ("SC 13D", "2026-08-10", "0001193125-26-000001", "d1.htm", ""),
       ("SC 13G", "2024-01-01", "0001193125-24-000001", "old.htm", "")]                 # older than the window


@pytest.fixture
def three(monkeypatch):
    monkeypatch.setattr(universes, "sp500_ciks", lambda: {"AAA": 1, "BBB": 2, "CCC": 3})
    monkeypatch.setattr(universes, "sp500_names", lambda: {"AAA": "Aaa Inc.", "BBB": "Bbb Corp.", "CCC": "Ccc Co."})


def us_sec(**kw):
    docs = {"https://www.sec.gov/Archives/edgar/data/1/000010290926000630/xslSCHEDULE_13G_X02/primary_doc.xml": (FIX / "schedule_13g_2026.txt").read_text(),
            "https://www.sec.gov/Archives/edgar/data/1/000119312526000001/d1.htm": (FIX / "sc_13g_a_2024.txt").read_text()}
    return FakeSEC({1: subs(1, EIGHT_K + G13), 2: subs(2, [("8-K", "2026-10-02", "0000000002-26-000001", "x.htm", "3.01")]),
                    3: subs(3, [("10-K", "2026-09-01", "0000000003-26-000001", "k.htm", "")])}, docs, **kw)


def test_us_run_stores_flags_and_holders_and_reads_covers_once(mem, three):
    sec = us_sec()
    runner = R.Runner(lambda: {"sec": sec}, sleep=lambda s: None, pause=0)
    out = runner.run("US", TODAY)
    assert out["ok"] and out["companies"] == 3 and out["covers_read"] == 2 and all(sec.fresh)
    page = R.listing("US", today=TODAY)
    assert page["total"] == 6 and {i["symbol"] for i in page["items"]} == {"AAA", "BBB"}
    assert page["items"][0]["symbol"] == "BBB" and page["items"][0]["category"] == "8k_3_01" and page["items"][0]["company"] == "Bbb Corp."
    h = R.holders_listing(today=TODAY)
    assert h["total"] == 2 and h["unread"] == 0
    new, old = h["items"][0], h["items"][1]
    assert new["form"] == "SCHEDULE 13G/A" and new["kind"] == "13G" and new["amendment"] and new["holder"] == "Vanguard Capital Management" and new["pct"] == 7.48
    assert old["kind"] == "13D" and old["holder"] == "Warren E. Buffett" and old["pct"] == 5.8 and old["label"] == "Schedule 13D (active stake)"
    n = len(sec.reads)
    out = runner.run("US", TODAY + timedelta(days=1))
    assert out["covers_read"] == 0 and len(sec.reads) == n                                # a cover is read once, not every day
    assert R.state("US")["through"] == "2026-10-07" and R.state("US")["holders"] == 2


def test_us_run_with_the_sec_down_fails_and_a_flaky_one_keeps_the_rest(mem, three):
    runner = R.Runner(lambda: {"sec": us_sec(fail={1, 2, 3})}, sleep=lambda s: None, pause=0)
    with pytest.raises(RuntimeError):
        runner.run("US", TODAY)
    out = R.Runner(lambda: {"sec": us_sec(fail={2})}, sleep=lambda s: None, pause=0).run("US", TODAY)
    assert out["ok"] and out["companies"] == 2 and out["error"].startswith("BBB")


def test_a_busy_sec_stops_cover_reads_and_leaves_them_for_the_next_run(mem, three):
    runner = R.Runner(lambda: {"sec": us_sec(busy_docs=True)}, sleep=lambda s: None, pause=0)
    out = runner.run("US", TODAY)
    assert out["ok"] and out["covers_read"] == 0 and R.holders_listing(today=TODAY)["unread"] == 2
    ok_sec = us_sec()
    assert R.Runner(lambda: {"sec": ok_sec}, sleep=lambda s: None, pause=0).read_covers(TODAY) == 2
    assert R.holders_listing(today=TODAY)["unread"] == 0


def test_a_cover_that_cant_be_read_is_not_asked_for_again():
    items = [{"id": "a", "at": "2026-09-01", "url": "u1", "read": False}, {"id": "b", "at": "2026-09-02", "url": "u2", "read": False}]
    done, failed = U.read_pending(items, lambda url: (_ for _ in ()).throw(ValueError("odd")), 5)
    assert failed == 2 and len(done) == 2 and all(i["read"] and i["holder"] is None for i in items)
    assert U.read_pending(items, lambda url: "", 5) == ([], 0)
    more = [{"id": str(n), "at": f"2026-09-{n:02d}", "url": "u", "read": False} for n in range(1, 8)]
    done, _ = U.read_pending(more, lambda url: "", 3)
    assert [i["at"] for i in done] == ["2026-09-07", "2026-09-06", "2026-09-05"]            # newest first, at most the limit


# ---------- reading a 13D/13G cover ----------
def test_read_cover_on_both_real_layouts():
    new = U.read_cover((FIX / "schedule_13g_2026.txt").read_text())
    assert new == {"holder": "Vanguard Capital Management", "pct": 7.48, "shares": 1099168953.0, "others": 0}
    old = U.read_cover((FIX / "sc_13g_a_2024.txt").read_text())
    assert old["holder"] == "Warren E. Buffett" and old["pct"] == 5.8 and old["shares"] == 905560000.0 and old["others"] >= 1


@pytest.mark.parametrize("text,holder,pct", [
    ("1. NAMES OF REPORTING PERSONS I.R.S. IDENTIFICATION NOS. OF ABOVE PERSONS (ENTITIES ONLY) The Vanguard Group 23-1945930 2. CHECK THE APPROPRIATE BOX IF A MEMBER OF A GROUP "
     "11. PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (9) 8.9% 12. TYPE OF REPORTING PERSON", "The Vanguard Group", 8.9),
    ("Names of Reporting Persons BlackRock, Inc. 2 Check the appropriate box ... Percent of class represented by amount in row (9) 6.2 %", "BlackRock, Inc.", 6.2),
    ("nothing useful here", None, None),
    ("Names of Reporting Persons 12345 2 Check the appropriate box Percent of class represented by amount in row 9 150%", None, None),
])
def test_read_cover_variants(text, holder, pct):
    got = U.read_cover(text)
    assert got["holder"] == holder and got["pct"] == pct


def test_items_from_subs_keeps_13d_and_13g_in_the_window():
    got = U.items_from_subs(subs(1, G13), "AAA", "Aaa Inc.", TODAY)
    assert [(i["form"], i["kind"], i["amendment"]) for i in got] == [("SCHEDULE 13G/A", "13G", True), ("SC 13D", "13D", False)]
    assert got[0]["url"] == "https://www.sec.gov/Archives/edgar/data/1/000010290926000630/xslSCHEDULE_13G_X02/primary_doc.xml" and got[0]["read"] is False
    assert U.items_from_subs(subs(1, G13), "AAA", None, TODAY, days=30)[0]["form"] == "SCHEDULE 13G/A" and len(U.items_from_subs(subs(1, G13), "AAA", None, TODAY, days=30)) == 1


# ---------- the list the page shows ----------
@pytest.fixture
def stocked(mem):
    items = [flag("AAA", f"2026-10-0{d}T10:00", "auditor_resign", "red", n=d) for d in range(1, 6)] \
          + [flag("BBB", "2026-09-20T10:00", "default", "red"), flag("CCC", "2026-09-10T10:00", "kmp_resign", "amber"),
             flag("DDD", "2026-06-01T10:00", "qip", "red"), flag("EEE", "2026-10-06T09:00", "pledge", "red")]
    R.flags.add("IN", items)
    mem[R.STATE_KEY + "IN"] = json.dumps({"through": "2026-10-06", "at": "2026-10-06T16:00:00+00:00"})
    return items


def test_listing_is_newest_first_paged_with_counts_by_type(stocked):
    p = R.listing("IN", today=TODAY, size=4)
    assert p["total"] == 8 and p["pages"] == 2 and p["page"] == 1 and p["from"] == "2026-07-08" and p["to"] == "2026-10-06"   # 90 days back: DDD is too old
    assert [i["symbol"] for i in p["items"]] == ["EEE", "AAA", "AAA", "AAA"] and p["items"][0]["at"] > p["items"][1]["at"]
    p2 = R.listing("IN", today=TODAY, size=4, page=2)
    assert [i["symbol"] for i in p2["items"]] == ["AAA", "AAA", "BBB", "CCC"] and p2["page"] == 2
    assert R.listing("IN", today=TODAY, size=4, page=99)["page"] == 2 and R.listing("IN", today=TODAY, page=-3)["page"] == 1
    counts = {t["id"]: t["count"] for t in p["types"]}
    assert counts["auditor_resign"] == 5 and counts["default"] == 1 and counts["kmp_resign"] == 1 and counts["pledge"] == 1 and counts["qip"] == 0
    assert p["as_of"] == "2026-10-06" and p["updated_at"] and p["companies"] == 4
    assert all(t["severity"] in ("red", "amber") for t in p["types"])


def test_listing_filters_by_type_dates_search_and_companies(stocked):
    only = R.listing("IN", flag="default,kmp_resign", today=TODAY)
    assert [i["symbol"] for i in only["items"]] == ["BBB", "CCC"] and only["total"] == 2
    assert {t["id"]: t["count"] for t in only["types"]}["auditor_resign"] == 5                  # counts ignore the type filter
    assert [i["symbol"] for i in R.listing("IN", frm="2026-09-15", to="2026-09-30", today=TODAY)["items"]] == ["BBB"]
    assert R.listing("IN", frm="2026-06-01", to="2026-06-30", today=TODAY)["items"][0]["symbol"] == "DDD"
    assert [i["symbol"] for i in R.listing("IN", q="ccc", today=TODAY)["items"]] == ["CCC"]
    assert [i["symbol"] for i in R.listing("IN", q="DDD LTD", frm="2026-01-01", today=TODAY)["items"]] == ["DDD"]        # the company name is searched too
    assert [i["symbol"] for i in R.listing("IN", symbols={"BBB", "EEE"}, today=TODAY)["items"]] == ["EEE", "BBB"]
    assert R.listing("IN", symbols=set(), today=TODAY)["total"] == 0
    odd = R.listing("IN", frm="garbage", to="2099-01-01", today=TODAY)
    assert odd["to"] == "2026-10-06" and odd["total"] == 8                                      # a bad date falls back; the future is cut off
    assert R.listing("IN", frm="2026-10-05", to="2026-09-01", today=TODAY)["from"] == "2026-09-01"       # a reversed range is made sensible
    assert R.listing("IN", flag="nope", today=TODAY)["total"] == 0 and R.listing("US", today=TODAY)["total"] == 0


def test_listing_types_for_each_region():
    india = {t["id"] for t in R.types("IN")}
    assert {"auditor_resign", "default", "qip", "pledge", "kmp_resign"} <= india and "results" not in india
    us = R.types("US")
    assert [t["id"] for t in us] == ["8k_1_03", "8k_3_01", "8k_4_01", "8k_4_02", "8k_5_02"] and not any("(Item" in t["label"] for t in us)


def test_holders_listing_filters_by_company_and_form(mem):
    rows = [{"id": f"{s}|{i}", "symbol": s, "company": s, "at": f"2026-09-{i:02d}", "form": "SC 13G", "kind": k, "amendment": False, "label": "x",
             "url": "u", "holder": None, "pct": None, "shares": None, "read": i % 2 == 0}
            for s in ("AAA", "BBB") for i, k in ((1, "13D"), (2, "13G"), (3, "13G"))]
    R.holds.add("US", rows)
    assert R.holders_listing(today=TODAY)["total"] == 6 and R.holders_listing("aaa", today=TODAY)["total"] == 3
    assert R.holders_listing("AAA", "13D", today=TODAY)["total"] == 1 and R.holders_listing(form="13G", today=TODAY)["total"] == 4
    page = R.holders_listing(size=2, page=2, today=TODAY)
    assert page["pages"] == 3 and len(page["items"]) == 2 and page["unread"] == 4
    assert R.holders_listing("A.B", today=TODAY)["symbol"] == "A-B"


# ---------- the daily job ----------
class Recorder:
    def __init__(self, fail=False):
        self.runs, self.fail = [], fail

    def run(self, region):
        self.runs.append(region)
        if self.fail:
            raise RuntimeError("down")
        _set = R._set_state
        _set(region, through="2026-10-06", at="2026-10-06T16:00:00+00:00")
        return {"ok": True}


def test_the_job_fills_an_empty_region_then_runs_once_a_day_after_its_time(mem, monkeypatch):
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda market, d: True)
    rec = Recorder()
    job = R.Job(rec)
    before = datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc)                  # 10:30 IST: before India's 21:00; 01:00 New York
    assert job.tick(before) == 2 and sorted(rec.runs) == ["IN", "US"]           # nothing stored yet: read at the first chance
    assert job.tick(before + timedelta(minutes=5)) == 0
    evening = datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc)                # 21:30 IST
    assert job.tick(evening) == 1 and rec.runs[-1] == "IN"
    assert job.tick(evening + timedelta(minutes=10)) == 0 and rec.runs.count("IN") == 2
    late = datetime(2026, 10, 6, 23, 45, tzinfo=timezone.utc)                  # 19:45 New York
    assert job.tick(late) == 1 and rec.runs[-1] == "US"
    again = R.Job(Recorder())
    assert again.tick(late + timedelta(minutes=5)) == 0                         # a restart does not repeat the day


def test_a_failed_run_is_tried_again_half_an_hour_later(mem, monkeypatch):
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda market, d: True)
    rec = Recorder(fail=True)
    job = R.Job(rec)
    assert job.tick(datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc)) == 0 and sorted(rec.runs) == ["IN", "US"]
    assert "down" in job.status["last_error"]
    job.tick(datetime(2026, 10, 6, 5, 1, tzinfo=timezone.utc))
    assert len(rec.runs) == 2                                                  # held back for 30 minutes
    assert job.retry["redflags-IN"] > 0


# ---------- the endpoints ----------
@pytest.fixture
def client(mem, monkeypatch):
    who = {"p": {"id": "u1", "plan": "pro", "_plan": "pro"}}
    main.app.dependency_overrides[main.current_profile] = lambda: who["p"]
    c = TestClient(main.app)
    c.who, c.mem = who, mem
    yield c
    main.app.dependency_overrides.clear()


def _today_flags():
    now = datetime.now(timezone.utc).date()
    day = lambda n: (now - timedelta(days=n)).isoformat()
    R.flags.add("IN", [flag("AAA", day(1) + "T10:00", "auditor_resign", "red"), flag("BBB", day(2) + "T10:00", "default", "red"),
                       flag("CCC", day(3) + "T10:00", "kmp_resign", "amber")])
    R.flags.add("US", [{**flag("AAPL", day(1) + "T00:00", "8k_4_01", "red"), "label": "Change of auditor (Item 4.01)"}])
    R.holds.add("US", [{"id": "AAPL|1", "symbol": "AAPL", "company": "Apple Inc.", "at": day(2), "form": "SCHEDULE 13G", "kind": "13G", "amendment": False,
                        "label": "Schedule 13G (passive stake)", "url": "https://www.sec.gov/Archives/x", "holder": "Vanguard", "pct": 7.5,
                        "shares": 1.0, "read": True}])


def test_red_flags_endpoint_lists_pages_and_filters(client):
    _today_flags()
    r = client.get("/research/redflags?region=IN")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3 and [i["symbol"] for i in body["items"]] == ["AAA", "BBB", "CCC"] and body["scope"] == "all" and body["region"] == "IN"
    assert body["covers"] and body["note"] and {t["id"] for t in body["types"]} >= {"auditor_resign", "default"}
    assert client.get("/research/redflags?region=IN&flag=default").json()["total"] == 1
    assert client.get("/research/redflags?region=IN&size=2&page=2").json()["items"][0]["symbol"] == "CCC"
    assert client.get("/research/redflags?region=IN&q=bbb").json()["total"] == 1
    us = client.get("/research/redflags?region=US").json()
    assert us["total"] == 1 and us["items"][0]["category"] == "8k_4_01" and "SEC" in us["note"]
    assert client.get("/research/redflags?region=XX").json()["region"] == "IN"
    for text in (json.dumps(body), json.dumps(us)):
        assert not ADVICE.search(text) and not PROVIDERS.search(text)


def test_red_flags_for_the_watchlist_only(client):
    _today_flags()
    client.mem["watchlist:u1"] = json.dumps({"items": [{"region": "IN", "symbol": "BBB"}, {"region": "US", "symbol": "AAPL"}, {"region": "IN", "symbol": "ZZZ"}]})
    mine = client.get("/research/redflags?region=IN&scope=mine").json()
    assert mine["scope"] == "mine" and [i["symbol"] for i in mine["items"]] == ["BBB"] and mine["watchlist"] == 2
    assert [i["symbol"] for i in client.get("/research/redflags?region=US&scope=mine").json()["items"]] == ["AAPL"]


def test_red_flags_across_companies_are_a_paid_feature_once_payments_are_live(client, monkeypatch):
    from app.config import settings
    for k, v in (("RAZORPAY_KEY_ID", "rzp_test_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "plan_b"), ("RAZORPAY_PLAN_PRO", "plan_p")):
        monkeypatch.setattr(settings, k, v)
    client.who["p"] = {"id": "u1", "plan": "free", "_plan": "free"}
    assert client.get("/research/redflags?region=IN").status_code == 402
    _today_flags()
    assert client.get("/research/holders-us").status_code == 402                              # every company's: Basic and up
    one = client.get("/research/holders-us?symbol=AAPL")
    assert one.status_code == 200 and one.json()["total"] == 1                                # one company's: for everyone


def test_us_holders_endpoint(client):
    _today_flags()
    body = client.get("/research/holders-us").json()
    assert body["total"] == 1 and body["items"][0]["holder"] == "Vanguard" and body["items"][0]["pct"] == 7.5 and "Not advice" in body["note"]
    assert client.get("/research/holders-us?symbol=aapl&form=13D").json()["total"] == 0
    assert client.get("/research/holders-us?symbol=aapl&form=13G").json()["total"] == 1
    assert not ADVICE.search(json.dumps(body)) and not PROVIDERS.search(json.dumps(body))


def test_admin_can_start_a_read_and_sees_the_job(client, monkeypatch):
    called = []
    monkeypatch.setattr(main.redflags_runner, "run", lambda region: called.append(region) or {"ok": True})
    from app import admin
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "admin", "role": "admin"}
    try:
        r = client.post("/admin/redflags/run?region=US")
        assert r.status_code == 200 and r.json()["started"] and r.json()["region"] == "US"
        import time
        for _ in range(50):
            if called:
                break
            time.sleep(0.05)
        assert called == ["US"]
        assert client.post("/admin/redflags/run?region=XX").status_code == 400
        rows = client.get("/admin/jobs").json()
        job = next(j for j in (rows["jobs"] if isinstance(rows, dict) else rows) if j["id"] == "redflags")
        assert job["name"] == "Red flags across companies" and {x["label"] for x in job["run"]} == {"Run India", "Run US"}
    finally:
        main.app.dependency_overrides.pop(admin.admin_profile, None)
