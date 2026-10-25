"""IPOs: the rows built from the saved real files (tests/fixtures/ipo, fetched 25 Oct 2026: NSE, BSE, SEBI, the public IPO calendar and
EDGAR), their stages and dates, a source that fails, the listing performance, the scheduled job (slots, the bids through the day,
the documents and their summaries), the alerts and their dedupe, and the routes with their plan gates."""
import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine

from app import db, main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import ipo as I, ipo_docs as D
from app.intel import ipo_sources as S
from app.intel.net import SourceError
from tests import fake_ipo as F
from tests import world as W
from tests.fake_db import headers

UTC, IST, NY = ZoneInfo("UTC"), ZoneInfo("Asia/Kolkata"), ZoneInfo("America/New_York")
TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 5, 0, tzinfo=UTC)               # a Sunday, 10:30 IST
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|nasdaq\.com|api\.nasdaq|edgar|efts", re.I)       # (an exchange's or regulator's own address is a link, not a name)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|apply|subscribe|attractive|cheap|expensive|undervalued|grey market|gmp|should)\b", re.I)


def at(y, mo, d, h=10, mi=30, tz=IST):
    return datetime(y, mo, d, h, mi, tzinfo=tz).astimezone(UTC)


class FakeYahoo:
    """Daily candles per symbol; `calls` counts the reads."""

    def __init__(self, bars: dict[str, list]):
        self.bars, self.calls = bars, []

    def chart(self, symbol, tf="1d", days=365, **kw):
        self.calls.append(symbol)
        if symbol not in self.bars:
            raise SourceError("prices", "No prices found.")
        return {"meta": {}, "candles": self.bars[symbol]}


def bar(day, o, c):
    return {"t": f"{day}T00:00:00+05:30", "o": o, "h": max(o, c), "l": min(o, c), "c": c, "v": 1000.0}


@pytest.fixture
def w(monkeypatch):
    with time_machine.travel(NOW, tick=False):
        world = W.build(monkeypatch)
        feed, cal, sebi, edgar = F.Feed(), F.Calendar(), F.Sebi(), F.Edgar()
        yahoo = FakeYahoo({"BONFIG.NS": [bar("2026-10-23", 640.0, 612.0), bar("2026-10-26", 615.0, 650.0)],
                           "IAM": [bar("2026-10-15", 19.5, 21.0), bar("2026-10-23", 21.0, 18.4)]})
        monkeypatch.setitem(I._wire, "feed", lambda: feed)
        monkeypatch.setitem(I._wire, "calendar", lambda: cal)
        monkeypatch.setitem(I._wire, "sebi", lambda: sebi)
        monkeypatch.setitem(I._wire, "edgar", lambda: edgar)
        monkeypatch.setitem(I._wire, "yahoo", lambda: yahoo)
        monkeypatch.setitem(I._wire, "ai", lambda: (None, None))
        world.update(feed=feed, cal=cal, sebi=sebi, edgar=edgar, yahoo=yahoo)
        I.forget()
        I._live.clear()
        yield world
        world["close"]()
        I.forget()


def read_all(w, now=NOW, perf=True):
    job = I.Job(sleep=lambda s: None)
    job.read("IN", now, perf=perf)
    job.read("US", now, perf=perf)
    return job


def by_id(market):
    return {r["id"]: r for r in I.load(market)["rows"]}


# ---------- stages and dates ----------
def test_stage_follows_the_dates_and_the_close_time_in_india():
    row = {"market": "IN", "open": "2026-10-26", "close": "2026-10-28", "listing": None}
    st = lambda *a: I.stage_of(row, at(*a))                      # noqa: E731
    assert st(2026, 10, 25) == "upcoming" and st(2026, 10, 26, 9, 0) == "open" and st(2026, 10, 28, 16, 59) == "open"
    assert st(2026, 10, 28, 17, 0) == "closed" and st(2026, 10, 30) == "closed"                # bidding ends at five on the last day
    assert I.stage_of({**row, "listing": "2026-10-30"}, at(2026, 10, 30, 8, 0)) == "listed"
    assert I.stage_of({**row, "listing": "2026-11-02"}, at(2026, 10, 30, 8, 0)) == "closed"
    assert I.stage_of({"market": "IN", "open": None, "close": None}, NOW) == "filed"


def test_us_stage():
    assert I.stage_of({"market": "US", "priced": "2026-10-15"}, NOW) == "listed"
    assert I.stage_of({"market": "US", "priced": "2026-10-26"}, NOW) == "closed"
    assert I.stage_of({"market": "US", "expected": "2026-10-28"}, NOW) == "upcoming"
    assert I.stage_of({"market": "US", "filed": "2026-10-21"}, NOW) == "filed"


def test_allotment_and_listing_are_sebis_timetable_until_the_exchange_publishes_them(w):
    row = {"market": "IN", "open": "2026-10-26", "close": "2026-10-28"}
    t = I.timeline(row, NOW)
    assert t == {"allotment": "2026-10-29", "allotment_expected": True, "listing": "2026-11-02", "listing_expected": True}       # T+1 and T+3 working days: 31 Oct is a Saturday
    t = I.timeline({**row, "listing": "2026-11-03"}, NOW)
    assert t["listing"] == "2026-11-03" and not t["listing_expected"]                   # the exchange's own date wins
    old = I.timeline({"market": "IN", "open": "2026-09-17", "close": "2026-09-21"}, NOW)
    assert old["allotment"] is None and old["listing"] is None                          # a date that has passed unpublished is not asserted
    assert I.timeline({"market": "US"}, NOW) == {"allotment": None, "allotment_expected": False, "listing": None, "listing_expected": False}


def test_size_and_minimum_investment_are_arithmetic_on_the_issue_terms():
    base = {"market": "IN", "lot": 91, "high": 162.0, "low": 153.0, "size_shares": 17000000}
    p = I.public({**base, "id": "x", "name": "x", "open": "2026-10-28", "close": "2026-10-30"}, NOW)
    assert p["min_amount"] == 14742.0 and p["min_basis"] == "lot at the top of the price band"
    assert (p["size"], p["size_basis"]) == (275.4, "shares at the top of the price band")
    p = I.public({**base, "id": "x", "name": "x", "price": 150.0, "fresh_cr": 100.0, "ofs_cr": 25.5, "open": "2026-10-28", "close": "2026-10-30"}, NOW)
    assert p["min_amount"] == 13650.0 and p["min_basis"] == "lot at the issue price" and (p["size"], p["size_basis"]) == (125.5, "stated")


# ---------- reading the sources ----------
def test_india_rows_from_the_exchanges_and_sebi(w):
    rows, problems = I.refresh_india(w["feed"], w["sebi"], TODAY, NOW, sleep=lambda s: None)
    assert problems == []
    ids = {r["id"]: r for r in rows}
    stage = {r["id"]: I.stage_of(r, NOW) for r in rows}
    assert {k for k, v in stage.items() if v == "upcoming"} == {"in-mksons", "in-sfctech", "in-blspoly", "in-edelalts", "in-bse-4907"}
    assert [k for k, v in stage.items() if v == "open"] == ["in-bse-4902"]                    # an SME issue only BSE lists
    core = ids["in-bse-4902"]
    assert (core["segment"], core["exchanges"], core["open"], core["close"], core["high"]) == ("sme", ["BSE"], "2026-10-23", "2026-10-27", 93.0)
    eaaa = ids["in-edelalts"]
    assert eaaa["exchanges"] == ["BSE", "NSE"] and eaaa["bse_code"] == "4901"                  # the same company on both lists is one row
    assert sum(1 for k in ids if k.startswith("in-bse-") and ids[k]["name"].lower().startswith("eaaa")) == 0
    bon = ids["in-bonfig"]
    assert (bon["lot"], bon["ofs"], bon["listing"], bon["price"], bon["isin"], bon["sub"]["times"]) == (25, 43239042, "2026-10-23", 586.0, "INE28SO01013", 46.06)
    assert stage["in-bonfig"] == "listed" and bon["segment"] == "mainboard"
    mk = ids["in-mksons"]
    assert (mk["lot"], mk["fresh"], mk["ofs"]) == (91, 13600000, 3400000) and "sub" not in mk
    # SEBI's red herring document is attached by company name; a draft with no dates stays a "filed" row
    assert {d["kind"]: d["source"] for d in ids["in-sfctech"]["docs"]} == {"RHP": "sebi"}
    filed = [r for r in rows if I.stage_of(r, NOW) == "filed"]
    assert len(filed) >= 15 and all(r["docs"][0]["kind"] == "DRHP" and r["docs"][0]["url"].startswith("https://www.sebi.gov.in/") for r in filed)
    assert any(r["name"] == "Hunger Pangs Limited" for r in filed)


def test_a_source_that_fails_leaves_the_rest(w):
    feed = F.Feed(down={"upcoming"})
    rows, problems = I.refresh_india(feed, w["sebi"], TODAY, NOW, sleep=lambda s: None)
    assert problems and "upcoming" in problems[0]
    stage = {r["id"]: I.stage_of(r, NOW) for r in rows}
    assert "in-bonfig" in stage and stage["in-bse-4907"] == "upcoming"                       # BSE still lists the issues NSE's list would have
    rows2, problems2 = I.refresh_india(F.Feed(down={"upcoming", "current", "past", "bse"}), F.Sebi(down={"sebi"}), TODAY, NOW, sleep=lambda s: None)
    assert len(problems2) >= 5 and rows2 == []                                               # nothing read at all: what was stored stands (nothing yet)


def test_nothing_read_keeps_what_was_stored_and_a_fact_not_given_this_time_is_kept(w):
    job = I.Job(sleep=lambda s: None)
    job.read("IN", NOW)
    before = by_id("IN")
    assert before["in-bonfig"]["lot"] == 25
    w["feed"].nse.down = {"upcoming", "current", "past", "detail"}
    w["feed"].bse.down = {"bse"}
    w["sebi"].down = {"sebi"}
    job.read("IN", NOW + timedelta(hours=12))
    after = by_id("IN")
    assert after.keys() == before.keys() and after["in-bonfig"]["lot"] == 25 and job.status["problems"]
    w["feed"].nse.down = {"detail"}                                                           # the lists answer, the issue pages don't
    job.read("IN", NOW + timedelta(hours=13))
    assert by_id("IN")["in-bonfig"]["sub"]["times"] == 46.06                                  # kept from the earlier read


def test_us_rows_from_the_calendar_and_the_sec(w):
    rows, problems = I.refresh_us(w["cal"], w["edgar"], TODAY, NOW)
    assert problems == [] and w["cal"].months == ["2026-08", "2026-09", "2026-10", "2026-11"]
    ids = {r["id"]: r for r in rows}
    stage = {r["id"]: I.stage_of(r, NOW) for r in rows}
    assert sum(1 for v in stage.values() if v == "listed") == 20 and sum(1 for v in stage.values() if v == "filed") == 55
    iam = ids["us-1273626-119431"]
    assert (iam["name"], iam["symbol"], iam["priced"], iam["price"], iam["shares"], iam["cik"]) == ("Iambic Therapeutics, Inc.", "IAM", "2026-10-15", 16.0, 9375000, "1997038")
    assert [d["kind"] for d in iam["docs"]] == ["424B4", "S-1/A", "S-1"] and iam["docs"][0]["link"].endswith("-index.htm")
    assert not any("kepuni" in r["name"].lower() for r in rows)                                # a withdrawn offering is dropped
    assert w["edgar"].names and len(w["edgar"].names) <= 10                                    # a few lookups a pass


def test_us_calendar_down_keeps_stored_rows_and_edgar_down_loses_nothing(w):
    job = I.Job(sleep=lambda s: None)
    job.read("US", NOW)
    n = len(I.load("US")["rows"])
    w["cal"].down = {"calendar"}
    job.read("US", NOW + timedelta(hours=12))
    assert len(I.load("US")["rows"]) == n and job.status["problems"]
    w["cal"].down = set()
    w["edgar"].down = {"edgar"}
    job.read("US", NOW + timedelta(days=3))
    assert len(I.load("US")["rows"]) == n and by_id("US")["us-1273626-119431"]["docs"]         # its documents stay


# ---------- how a listed issue has traded ----------
def test_listing_performance_against_the_issue_price(w):
    read_all(w)
    bon = by_id("IN")["in-bonfig"]
    p = I.performance(bon, w["yahoo"], TODAY)
    assert (p["issue_price"], p["listing_price"], p["day_close"], p["latest"], p["listed"]) == (586.0, 640.0, 612.0, 650.0, "2026-10-23")
    assert (p["listing_change_pct"], p["day_change_pct"], p["change_pct"]) == (9.22, 4.44, 10.92) and p["basis"] == "prices"
    assert bon["perf"]["change_pct"] == 10.92 and bon["perf"]["at"]
    iam = by_id("US")["us-1273626-119431"]["perf"]
    assert (iam["listing_price"], iam["listing_change_pct"], iam["latest"], iam["change_pct"]) == (19.5, 21.88, 18.4, 15.0)


def test_when_the_prices_cannot_be_read_the_exchange_table_stands_in(w):
    read_all(w)
    aye = {"market": "IN", "symbol": None, "bse_code": "544699", "listing": "2026-02-16", "price": 129.0,
           "bse_perf": {"issue_price": 129.0, "day_close": 128.9, "latest": 134.55}}
    p = I.performance(aye, w["yahoo"], TODAY)
    assert p["basis"] == "exchange" and p["listing_price"] is None
    sym = {**aye, "symbol": "NOSUCH"}
    p = I.performance(sym, w["yahoo"], TODAY)
    assert p["basis"] == "exchange" and p["listing_price"] is None and (p["day_change_pct"], p["change_pct"]) == (-0.08, 4.3)
    assert I.performance({"market": "IN", "symbol": "NOSUCH", "listing": "2026-10-23", "price": 100.0}, w["yahoo"], TODAY) is None


# ---------- the job ----------
def test_slots_run_once_a_day_and_survive_a_restart(w):
    job = I.Job(sleep=lambda s: None)
    day = at(2026, 10, 26, 7, 45)
    assert job.tick(day)[:1] == ["in-am"] and I.run_marker("in-am") == "2026-10-26"
    assert "in-am" not in I.Job(sleep=lambda s: None).tick(day + timedelta(minutes=5))      # a new process, the same day
    assert by_id("IN") and w["feed"].nse.calls.count("upcoming") == 1
    assert I.state()["IN"]["read"] and job.status["last_run"] and job.status["read"] == "IN"


def test_the_bids_are_read_every_quarter_hour_while_an_issue_is_open(w):
    """Bonfiglioli was open 15 to 19 Oct: put it back into bidding and read its page through the day."""
    row = {"id": "in-bonfig", "market": "IN", "segment": "mainboard", "name": "Bonfiglioli Transmissions Limited", "symbol": "BONFIG", "series": "EQ",
           "open": "2026-10-15", "close": "2026-10-19", "exchanges": ["NSE"], "currency": "INR", "nkey": "bonfiglioli"}
    I.save("IN", [row], {})
    job = I.Job(sleep=lambda s: None)
    for name, _ in I.Job.SLOTS:                                        # the day's slots are done: only the bids are read
        db.set_setting("ipo:ran:" + name, "2026-10-16")
    morning = at(2026, 10, 16, 10, 30)
    assert job.live_due(morning) is True
    assert job.tick(morning) == ["live"]
    got = by_id("IN")["in-bonfig"]
    assert got["sub"]["times"] == 46.06 and got["lot"] == 25 and got["sub_read"]
    assert job.live_due(morning + timedelta(minutes=5)) is False                            # not again within the quarter hour
    job._live_at -= I.LIVE_EVERY + 1
    assert job.live_due(morning + timedelta(minutes=16)) is True
    assert job.live_due(at(2026, 10, 16, 18, 30)) is False and job.live_due(at(2026, 10, 18, 10, 30)) is False        # after hours, and a Sunday


def test_final_bids_are_read_after_the_exchange_completes_them(w):
    row = {"id": "in-bonfig", "market": "IN", "segment": "mainboard", "name": "Bonfiglioli Transmissions Limited", "symbol": "BONFIG", "series": "EQ",
           "open": "2026-10-15", "close": "2026-10-19", "exchanges": ["NSE"], "currency": "INR", "nkey": "bonfiglioli"}
    I.save("IN", [row], {})
    job = I.Job(sleep=lambda s: None)
    assert job.read_open(at(2026, 10, 19, 19, 25), final=True) == 1
    assert by_id("IN")["in-bonfig"]["sub"]["as_of"] == "2026-10-19 19:00"


def test_first_start_reads_both_markets_at_once(w):
    job = I.Job(sleep=lambda s: None)
    assert job.tick(at(2026, 10, 25, 6, 0)) == [] and I.load("IN")["rows"] and I.load("US")["rows"]            # before any slot is due
    assert by_id("IN")["in-bonfig"]["perf"]["change_pct"] == 10.92                           # and how listed issues have traded


# ---------- the offer document: facts and the summary ----------
@pytest.fixture
def docs(w, monkeypatch):
    """Downloads answer with a placeholder PDF (or the saved US prospectus start); the PDF reader gives each issue's saved pages."""
    import gzip
    html = gzip.open(F.DIR / "iambic_424b4_head.htm.gz").read()
    fetched = []

    def download(url, limit=0, head=None, transport=None):
        fetched.append(url)
        return html if "sec.gov" in url else b"%PDF-1.4 placeholder"

    monkeypatch.setattr(D, "download", download)
    monkeypatch.setattr(D, "pdf_pages", lambda data, max_pages=0: F.pages_of("bonfig_rhp"))
    w["fetched"] = fetched
    return w


def quote_ai(monkeypatch, calls=None):
    """An AI that answers from the passages it is given."""
    def fake(system, text, **kw):
        if calls is not None:
            calls.append(text)
        if "Cover" in text and "Collaboration revenue" in text:                 # the US prospectus
            q = "Our approach to drug discovery, which integrates AI with automated experimentation, is novel and unproven"
            return json.dumps({"business": {"text": "An AI-enabled drug discovery company.", "quote": q}, "financials": [], "objects": [], "promoters": [],
                               "risks": [{"text": "The company has a limited operating history and has made large losses.",
                                          "quote": "We have a limited operating history and have incurred significant losses and negative cash flows"}]})
        return json.dumps({"business": {"text": "Makes gearboxes and drives.", "quote": "OUR PROMOTERS: SONIA BONFIGLIOLI, LUCIANO BONFIGLIOLI, LUISA LUSARDI, BON-FI S.R.L., AND BONFIGLIOLI S.P.A."},
                           "promoters": [{"text": "The promoters are Sonia Bonfiglioli, Luciano Bonfiglioli, Luisa Lusardi, Bon-Fi S.r.l. and Bonfiglioli S.p.A.",
                                          "quote": "OUR PROMOTERS: SONIA BONFIGLIOLI, LUCIANO BONFIGLIOLI, LUISA LUSARDI, BON-FI S.R.L., AND BONFIGLIOLI S.P.A."}],
                           "financials": [], "objects": [], "risks": []})
    monkeypatch.setattr(D, "complete", fake)


def test_the_job_reads_documents_nearest_their_dates_first_then_summarises(docs, monkeypatch):
    read_all(docs)
    calls = []
    quote_ai(monkeypatch, calls)
    job = I.Job(sleep=lambda s: None)
    n = job.read_docs(NOW, limit=3)
    assert n >= 3 and docs["fetched"] and not job.status["problems"]
    # the issues open or about to open are read before the listed ones and the filings with no dates
    first = [r for r in I.load("IN")["rows"] if I.facts_of(I.doc_to_read(r))]
    assert any(r["id"] in ("in-mksons", "in-sfctech", "in-blspoly") for r in first)
    bon = by_id("IN")["in-bonfig"]
    d = I.doc_to_read(bon)
    assert d["source"] == "nse" and d["url"].endswith("RHP_BONFIG.zip")                          # the exchange's copy is read, SEBI's page is only linked
    I.read_doc(bon, d)
    f = I.facts_of(d)
    assert f["promoters"][0] == "Sonia Bonfiglioli" and f["financials"]["page"] == 72 and f["objects"]["page"] == 111 and f["pages_read"] == 150 and "excerpt" in f
    assert len(calls) == 2                                                                       # at most two summaries a pass, written from the documents' own passages
    made = [json.loads(v) for _, v in db.all_settings_with_prefix(D.SUM_KEY)]
    assert len(made) == 2 and all(m["items"]["promoters"][0]["text"].startswith("The promoters are") for m in made)
    job.read_docs(NOW + timedelta(minutes=5), limit=3)
    assert len(calls) == 4 and len(list(db.all_settings_with_prefix(D.SUM_KEY))) == 4         # the next pass writes the next two, none twice


def test_a_failing_document_is_tried_three_times_then_left_for_a_day(docs, monkeypatch):
    read_all(docs)
    monkeypatch.setattr(D, "download", lambda *a, **k: (_ for _ in ()).throw(SourceError("the document's site", "The document couldn't be downloaded (503).", busy=True)))
    job = I.Job(sleep=lambda s: None)
    for _ in range(5):
        job.read_docs(NOW, limit=1)
    assert job.status["problems"] and "503" in job.status["problems"][0]
    tries = [json.loads(v) for k, v in db.all_settings_with_prefix("ipo:try:")]
    assert tries and max(t["n"] for t in tries) == 3


# ---------- alerts ----------
def set_prefs(uid, **kw):
    p = I.prefs(uid)
    p.update(kw)
    I.save_prefs(uid, p)


def test_events_of_a_day(w):
    read_all(w)
    rows = I.load("IN")["rows"]
    ev = I.events_on(rows, "IN", date(2026, 10, 27), at(2026, 10, 27, 8, 0))
    kinds = {(e["row"]["id"], e["kind"]) for e in ev}
    assert ("in-sfctech", "open") in kinds and ("in-blspoly", "open") in kinds and ("in-bse-4902", "close") in kinds
    sfc = next(e for e in ev if e["row"]["id"] == "in-sfctech" and e["kind"] == "open")
    assert sfc["text"] == "SFC Environmental Technologies Limited opens for bidding today (price band ₹313 to ₹330)."
    mk = I.events_on(rows, "IN", date(2026, 11, 4), at(2026, 11, 4, 8, 0))
    assert any(e["row"]["id"] == "in-mksons" and e["kind"] == "listing" and "SEBI's timetable" in e["text"] for e in mk)
    assert all(not ADVICE.search(e["text"]) for e in ev + mk)
    us = I.events_on(I.load("US")["rows"], "US", date(2026, 10, 15), at(2026, 10, 15, 9, 0, NY))
    assert any("Iambic" in e["text"] and "starts trading today after pricing at $16.00" in e["text"] for e in us)


def test_alerts_go_to_basic_users_who_turned_them_on_once(w):
    read_all(w)
    sent = []
    send = lambda p, subject, text: (sent.append((p["id"], subject, text)) or ["push"])         # noqa: E731
    day, now = date(2026, 10, 27), at(2026, 10, 27, 8, 0)
    set_prefs("u-basic", on=True, events=["open", "close"], markets=["IN"], sme=False)
    set_prefs("u-free", on=True)                                                                 # on, but the plan has no IPO alerts
    set_prefs("u-pro", on=False)
    assert I.send_alerts("IN", day, now, send=send) == 1
    uid, subject, text = sent[0]
    assert uid == "u-basic" and subject.startswith("StratLab IPOs: ") and "SFC Environmental Technologies Limited opens for bidding today" in text
    assert "Core4" not in text                                                                    # SME issues are left out unless asked for
    assert not ADVICE.search(text) and not PROVIDERS.search(text) and "Facts, not advice." in text
    assert I.send_alerts("IN", day, now, send=send) == 0                                          # the same events are never sent twice
    set_prefs("u-basic", sme=True)
    assert I.send_alerts("IN", day, now, send=send) == 1 and "Core4" in sent[1][2] and "SFC" not in sent[1][2]


def test_an_alert_that_could_not_be_sent_is_tried_again(w):
    read_all(w)
    set_prefs("u-basic", on=True, events=["open"], markets=["IN"])
    day, now = date(2026, 10, 27), at(2026, 10, 27, 8, 0)
    assert I.send_alerts("IN", day, now, send=lambda p, s, t: []) == 0                          # nowhere to reach
    assert I.send_alerts("IN", day, now, send=lambda p, s, t: (_ for _ in ()).throw(RuntimeError("x"))) == 0
    assert I.prefs("u-basic")["sent"] == []
    assert I.send_alerts("IN", day, now, send=lambda p, s, t: ["email"]) == 1


def test_the_alert_slots_send_through_the_users_channels(w, monkeypatch):
    read_all(w)
    got = []
    monkeypatch.setattr(I.alerts_mod, "jobs_for", lambda profile, subject, text, url, **kw: [("push", lambda: got.append((profile["id"], url, kw.get("label"))) or 1)])
    set_prefs("u-basic", on=True, events=["open"], markets=["IN"])
    job = I.Job(sleep=lambda s: None)
    I.save_state({"IN": {"tried": at(2026, 10, 27, 7, 50).isoformat()}, "US": {"tried": at(2026, 10, 27, 7, 50).isoformat()}})
    ran = job.tick(at(2026, 10, 27, 8, 5))
    assert "in-alert" in ran and got == [("u-basic", "/invest/ipos", "IPO alert")] and job.status["sent"] == 1


# ---------- the routes ----------
def test_the_list_is_free_and_has_every_stage(w):
    read_all(w)
    c = w["client"]
    r = c.get("/invest/ipos?market=IN", headers=headers("free-token"))
    assert r.status_code == 200
    d = r.json()
    assert d["counts"]["upcoming"] == 5 and d["counts"]["open"] == 1 and d["counts"]["listed"] == 54 and d["counts"]["filed"] >= 15
    up = d["tabs"]["upcoming"]
    assert [x["id"] for x in up][:2] == ["in-edelalts", "in-sfctech"] or up[0]["open"] <= up[-1]["open"]                  # soonest first
    mk = next(x for x in up if x["id"] == "in-mksons")
    assert (mk["low"], mk["high"], mk["lot"], mk["min_amount"], mk["size"], mk["stage"]) == (153.0, 162.0, 91, 14742.0, 275.4, "upcoming")
    assert mk["allotment"] == "2026-11-02" and mk["allotment_expected"] and mk["listing"] == "2026-11-04" and mk["listing_expected"]
    listed = d["tabs"]["listed"]
    assert listed[0]["listing"] >= listed[-1]["listing"]                                                                 # newest first
    bon = next(x for x in listed if x["id"] == "in-bonfig")
    assert bon["sub_times"] == 46.06 and bon["perf"]["change_pct"] == 10.92 and bon["price"] == 586.0
    assert d["prefs"]["allowed"] is False and d["prefs"]["plan"] == "Basic" and "GMP" not in json.dumps(d)
    assert "grey" not in json.dumps(d).lower()
    us = c.get("/invest/ipos?market=US", headers=headers("free-token")).json()
    assert us["counts"]["listed"] == 20 and us["tabs"]["listed"][0]["priced"] >= us["tabs"]["listed"][-1]["priced"] and "no public bidding window" in us["note"]
    assert c.get("/invest/ipos?market=UK", headers=headers("free-token")).status_code == 404
    assert c.get("/invest/ipos").status_code in (401, 403)


def test_an_issue_page_shows_its_facts_to_everyone_and_the_summary_to_basic(docs, monkeypatch):
    read_all(docs)
    quote_ai(monkeypatch)
    c = docs["client"]
    bon = by_id("IN")["in-bonfig"]
    I.read_doc(bon, I.doc_to_read(bon))
    r = c.get("/invest/ipos/in-bonfig", headers=headers("free-token"))
    assert r.status_code == 200
    d = r.json()
    ipo = d["ipo"]
    assert (ipo["name"], ipo["stage"], ipo["lot"], ipo["listing"], ipo["price"], ipo["isin"], ipo["company_link"]) == \
        ("Bonfiglioli Transmissions Limited", "listed", 25, "2026-10-23", 586.0, "INE28SO01013", "/research/IN/BONFIG")
    assert ipo["min_amount"] == 14650.0 and ipo["ofs"] == 43239042
    assert d["facts"]["state"] == "ready" and d["facts"]["promoters"][0] == "Sonia Bonfiglioli" and d["facts"]["financials"]["rows"][0]["values"] == [2013.53, 1854.18, 1687.33]
    assert d["facts"]["objects"]["text"].startswith("The objects of the Offer are to")
    assert "excerpt" not in json.dumps(d)                                                       # the passages the AI reads stay on the server
    assert d["subscription"]["times"] == 46.06 and d["perf"]["listing_price"] == 640.0
    assert d["summary"] == {"allowed": False, "plan": "Basic", "state": "locked", "kind": "RHP"}
    assert d["documents"] == [{"kind": "RHP", "label": "Red herring prospectus (RHP)", "source": "NSE, ZIP", "date": None, "read": True,
                               "url": "https://nsearchives.nseindia.com/content/ipo/RHP_BONFIG.zip"}]
    assert all(x["url"].startswith(("https://www.sebi.gov.in/", "https://nsearchives.nseindia.com/", "https://www.sec.gov/")) for x in d["documents"])
    # a free account is turned away from asking for the summary; Basic gets it written once
    r = c.post("/invest/ipos/in-bonfig/summary", headers=headers("free-token"))
    assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
    b = c.get("/invest/ipos/in-bonfig", headers=headers("basic-token")).json()
    assert b["summary"]["state"] == "pending"
    r = c.post("/invest/ipos/in-bonfig/summary", headers=headers("basic-token"))
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["state"] == "ready" and s["items"]["promoters"][0]["text"].startswith("The promoters are") and s["items"]["promoters"][0]["quote"].startswith("OUR PROMOTERS")
    assert c.get("/invest/ipos/in-bonfig", headers=headers("free-token")).json()["summary"]["state"] == "locked"      # still locked for Free
    n = len(docs["fetched"])
    c.post("/invest/ipos/in-bonfig/summary", headers=headers("pro-token"))
    assert len(docs["fetched"]) == n                                                           # written once for everyone: no second download or AI call
    text = json.dumps(r.json())
    assert not ADVICE.search(text.replace("OUR PROMOTERS", "")) and not PROVIDERS.search(text)


def test_a_us_issue_page_and_its_summary(docs, monkeypatch):
    read_all(docs)
    quote_ai(monkeypatch)
    c = docs["client"]
    r = c.post("/invest/ipos/us-1273626-119431/summary", headers=headers("basic-token"))
    assert r.status_code == 200, r.text
    d = c.get("/invest/ipos/us-1273626-119431", headers=headers("basic-token")).json()
    assert d["ipo"]["company_link"] == "/research/US/IAM" and d["ipo"]["price"] == 16.0 and d["ipo"]["industry"].startswith("Biological")
    assert d["facts"]["us"]["company_shares"] == 9375000 and d["facts"]["us"]["proceeds"].startswith("We estimate")
    assert d["summary"]["items"]["risks"][0]["text"].startswith("The company has a limited operating history")
    assert d["perf"]["listing_price"] == 19.5 and d["perf"]["change_pct"] == 15.0
    assert [x["label"] for x in d["documents"]][0] == "Final prospectus (424B4)" and d["documents"][0]["url"].endswith("-index.htm")


def test_the_summary_is_unavailable_when_the_ai_is(docs, monkeypatch):
    read_all(docs)
    from app.ai_providers import AIBusy
    monkeypatch.setattr(D, "complete", lambda *a, **k: (_ for _ in ()).throw(AIBusy("Every AI provider is busy.")))
    c = docs["client"]
    r = c.post("/invest/ipos/in-bonfig/summary", headers=headers("basic-token"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_unavailable"
    assert I.summary_of(I.doc_to_read(by_id("IN")["in-bonfig"])) is None                    # nothing was kept: it is tried again
    assert c.post("/invest/ipos/nope/summary", headers=headers("basic-token")).status_code == 404
    assert c.get("/invest/ipos/NOT_AN_ID!", headers=headers("basic-token")).status_code == 404


def test_the_open_issues_bids_are_refreshed_when_the_page_is_opened_during_bidding(w, monkeypatch):
    row = {"id": "in-bonfig", "market": "IN", "segment": "mainboard", "name": "Bonfiglioli Transmissions Limited", "symbol": "BONFIG", "series": "EQ",
           "open": "2026-10-15", "close": "2026-10-19", "exchanges": ["NSE"], "currency": "INR", "nkey": "bonfiglioli"}
    I.save("IN", [row], {})
    with time_machine.travel(at(2026, 10, 16, 11, 0), tick=False):
        d = w["client"].get("/invest/ipos/in-bonfig", headers=headers("free-token")).json()
        assert d["ipo"]["stage"] == "open" and d["subscription"]["times"] == 46.06 and d["subscription"]["live"] is True
        calls = w["feed"].nse.calls.count("detail:BONFIG")
        w["client"].get("/invest/ipos/in-bonfig", headers=headers("free-token"))
        assert w["feed"].nse.calls.count("detail:BONFIG") == calls == 1                       # not read again within five minutes
    I._live.clear()
    with time_machine.travel(at(2026, 10, 16, 20, 0), tick=False):
        w["client"].get("/invest/ipos/in-bonfig", headers=headers("free-token"))
        assert w["feed"].nse.calls.count("detail:BONFIG") == 1                               # and not after hours


def test_alert_settings_and_their_plan_gate(w):
    c = w["client"]
    body = {"on": True, "events": ["open", "listing"], "markets": ["IN", "US"], "sme": True}
    r = c.put("/invest/ipos/alerts", headers=headers("free-token"), json=body)
    assert r.status_code == 402 and "IPO alerts are on the Basic plan" in r.json()["detail"]["message"]
    assert c.put("/invest/ipos/alerts", headers=headers("free-token"), json={**body, "on": False}).status_code == 200            # off is always allowed
    r = c.put("/invest/ipos/alerts", headers=headers("basic-token"), json=body)
    assert r.status_code == 200 and r.json()["on"] is True and r.json()["events"] == ["open", "listing"] and r.json()["sme"] is True
    assert c.get("/invest/ipos/alerts", headers=headers("basic-token")).json()["markets"] == ["IN", "US"]
    assert c.put("/invest/ipos/alerts", headers=headers("basic-token"), json={**body, "events": ["nope"]}).status_code == 400
    assert c.put("/invest/ipos/alerts", headers=headers("basic-token"), json={**body, "markets": []}).status_code == 400
    assert c.put("/invest/ipos/alerts", headers=headers("basic-token"), json={**body, "events": ["open", "open", "close"]}).json()["events"] == ["open", "close"]


def test_a_downgraded_account_stops_receiving_alerts_and_the_admin_refresh_is_for_admins(w):
    read_all(w)
    set_prefs("u-free", on=True, events=["open"], markets=["IN"])
    assert I.send_alerts("IN", date(2026, 10, 27), at(2026, 10, 27, 8, 0), send=lambda *a: ["push"]) == 0
    c = w["client"]
    assert c.post("/admin/ipos/refresh", headers=headers("basic-token")).status_code in (401, 403)
    assert c.post("/admin/ipos/refresh", headers=headers("admin-token")).json()["started"] is True


def test_nothing_shown_names_a_data_vendor_or_gives_advice(docs, monkeypatch):
    read_all(docs)
    quote_ai(monkeypatch)
    c = docs["client"]
    c.post("/invest/ipos/in-bonfig/summary", headers=headers("basic-token"))
    for url in ("/invest/ipos?market=IN", "/invest/ipos?market=US", "/invest/ipos/in-bonfig", "/invest/ipos/us-1273626-119431", "/invest/ipos/alerts"):
        text = re.sub(r"https://[^\"\s]+", "", json.dumps(c.get(url, headers=headers("basic-token")).json()))
        assert not PROVIDERS.search(text), (url, PROVIDERS.search(text).group())
        assert not re.search(r"yahoo|finnhub|screener|kite|zerodha|nasdaq data|edgar", text, re.I), url
        scrubbed = re.sub(r"OUR PROMOTERS[^\"]*|Facts, not advice\.", "", text)
        assert not ADVICE.search(scrubbed), (url, ADVICE.search(scrubbed).group())


def test_the_job_is_listed_for_admins(w):
    from app import admin_jobs
    row = next(r for r in admin_jobs.rows() if r["id"] == "ipo")
    assert row["name"] == "IPOs" and "7:40 AM" in row["schedule"] and row["run"][0]["path"] == "/admin/ipos/refresh"


def test_the_stored_rows_and_documents_live_in_the_market_data_store():
    from app import market_store
    for key in (I.ROWS_KEY + "IN", I.STATE_KEY, D.SUM_KEY + "abc", D.FACTS_KEY + "abc"):
        assert key.startswith(market_store.MARKET_PREFIXES), key
    assert not I.USER_KEY.startswith(market_store.MARKET_PREFIXES)                           # a person's settings are not market data


def test_alert_settings_are_part_of_a_persons_data(w):
    from app import user_data
    set_prefs("u-basic", on=True)
    assert any(k == "ipo.USER_KEY" for k in user_data.ALERT_KEYS)
    assert db.get_setting(I.USER_KEY + "u-basic")
    assert user_data._alerts("u-basic") >= 1                                                  # deleting an account deletes them
    assert not db.get_setting(I.USER_KEY + "u-basic")


# ---------- issues that did not go ahead, Social Stock Exchange raises, and a size with a part in shares (MEM1 B) ----------
def test_the_exchanges_note_on_an_issue_is_read_off_its_name():
    assert S.classify("Zenith Foods Limited-Issue Withdrawn") == ("Zenith Foods Limited", "withdrawn", False)
    assert S.classify("Acme Ltd - Issue postponed") == ("Acme Ltd", "postponed", False)
    assert S.classify("Acme Ltd (Issue Cancelled)") == ("Acme Ltd", "cancelled", False)
    assert S.classify("Rays of Belief Limited- For Profit Social Enterprise (FPSE)") == ("Rays of Belief Limited", None, True)
    assert S.classify("Plain Company Limited") == ("Plain Company Limited", None, False)
    assert S.classify("Social Stock Exchange Ltd")[2] is False                    # only a note at the end of the name counts
    rows = S.bse_issues({"Table": [{"Scrip_cd": 9001, "Scrip_Name": "Zenith Foods Limited-Issue Withdrawn", "IR_flag": "IPO", "Status": "F",
                                    "eXCHANGE_PLATFORM": "MainBoard", "Start_Dt": "2026-11-02T00:00:00", "End_Dt": "2026-11-04T00:00:00",
                                    "Price_Band": "100.00 - 110.00"}]})
    assert rows[0]["name"] == "Zenith Foods Limited" and rows[0]["issue_status"] == "withdrawn" and "social" not in rows[0]
    plain = S.bse_issues({"Table": [{**{"Scrip_cd": 9002, "Scrip_Name": "Other Limited", "IR_flag": "IPO", "eXCHANGE_PLATFORM": "SME"}}]})
    assert "issue_status" not in plain[0]


def _row(**kw):
    return {"id": "in-x", "market": "IN", "name": "X Ltd", "symbol": "X", "segment": "mainboard", "currency": "INR", "open": "2026-10-20", "close": "2026-10-22",
            "low": 100.0, "high": 110.0, **kw}


def test_a_withdrawn_or_social_issue_is_in_no_stage_and_has_no_dates_or_alerts():
    for extra, stage in (({"issue_status": "withdrawn"}, "withdrawn"), ({"issue_status": "postponed"}, "withdrawn"), ({"social": True}, "social")):
        r = _row(**extra)
        assert I.stage_of(r, NOW) == stage
        pub = I.public(r, NOW)
        assert pub["stage"] == stage and not pub["allotment_expected"] and not pub["listing_expected"]
        assert I.events_on([r], "IN", date(2026, 10, 22), NOW) == []                       # no "closes today" message for it
    assert I.stage_of(_row(), NOW) == "closed"


def test_the_list_keeps_withdrawn_postponed_and_social_issues_out_of_the_closed_tab(w, monkeypatch):
    read_all(w)
    rows = I.load("IN")["rows"]
    keep = [dict(r) for r in rows]
    bon = next(r for r in keep if r["id"] == "in-bonfig")
    mk = next(r for r in keep if r["id"] == "in-mksons")
    bon["issue_status"], mk["issue_status"] = "withdrawn", "postponed"
    shares = next(r for r in keep if r["id"] == "in-ravita")
    shares["social"] = True
    I.save("IN", keep, I.load("IN")["checked"], as_of=I.load("IN")["as_of"])
    d = w["client"].get("/invest/ipos?market=IN", headers=headers("free-token")).json()
    ids = lambda tab: {x["id"] for x in d["tabs"][tab]}      # noqa: E731
    assert {"in-bonfig", "in-mksons"} <= ids("withdrawn") and "in-ravita" in ids("social")
    for tab in ("upcoming", "open", "closed", "listed"):
        assert not ({"in-bonfig", "in-mksons", "in-ravita"} & ids(tab))
    assert d["counts"]["withdrawn"] == len(d["tabs"]["withdrawn"]) >= 2 and d["counts"]["social"] >= 1
    assert {x["id"]: x["issue_status"] for x in d["tabs"]["withdrawn"]}["in-mksons"] == "postponed"
    one = w["client"].get("/invest/ipos/in-bonfig", headers=headers("free-token")).json()["ipo"]
    assert one["stage"] == "withdrawn" and one["issue_status"] == "withdrawn"


def test_a_note_the_exchange_stops_giving_is_dropped_at_the_next_read():
    nse = {"past": [], "current": [], "upcoming": [{"symbol": "ZENITH", "name": "Zenith Foods Limited", "series": "EQ", "segment": "mainboard", "open": "2026-11-02",
                                                   "close": "2026-11-04", "low": 100.0, "high": 110.0, "size_shares": None, "issue_status": "postponed"}]}
    first = I.merge_india([], nse, [], [], [], [], TODAY)
    assert first[0]["issue_status"] == "postponed"
    nse["upcoming"][0].pop("issue_status")                              # announced again, without the note
    again = I.merge_india(first, nse, [], [], [], [], TODAY)
    assert not again[0]["issue_status"] and I.stage_of(again[0], NOW) == "upcoming"


def test_a_part_in_rupees_and_a_part_in_shares_is_not_the_size():
    r = _row(fresh_cr=500.0, ofs=1_00_00_000, high=None, low=None)
    got = I.public(r, NOW)
    assert got["size"] is None and got["size_parts"] == {"fresh_cr": 500.0, "ofs": 10000000}        # no band yet: both parts, no total
    banded = I.public(_row(fresh_cr=500.0, ofs=1_00_00_000, low=95.0, high=100.0), NOW)
    assert banded["size"] == 600.0 and banded["size_basis"] == "at the top of the price band"       # 500 + 1 crore shares x 100
    assert banded["size_parts"] == {"fresh_cr": 500.0, "ofs": 10000000}
    priced = I.public(_row(fresh_cr=500.0, ofs=1_00_00_000, low=95.0, high=100.0, price=98.0), NOW)
    assert priced["size"] == 598.0 and priced["size_basis"] == "at the issue price"
    flip = I.public(_row(ofs_cr=200.0, fresh=50_00_000, low=95.0, high=100.0), NOW)
    assert flip["size"] == 250.0 and flip["size_parts"] == {"ofs_cr": 200.0, "fresh": 5000000}
    # the other cases keep their words
    assert I.public(_row(fresh_cr=500.0, ofs_cr=100.0), NOW)["size"] == 600.0
    assert I.public(_row(fresh_cr=500.0), NOW)["size"] == 500.0 and "size_parts" not in I.public(_row(fresh_cr=500.0), NOW)
    assert I.public(_row(size_shares=1_00_00_000), NOW)["size_basis"] == "shares at the top of the price band"
