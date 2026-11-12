"""The earnings-call calendar (concalls.py): which exchange filings are about calls and meetings, what a notice says
(date, time, zone, a webcast or dial-in link), what is filed after a call (transcript, recording, presentation), the
store and the evening run, the page's answer and its plan gate, and the money calendar's hook."""
import json
import re
from datetime import date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import concalls as C, db, main, money_calendar, redflags as R, results
from app.intel import filings as F
from app.intel.net import SourceError

ADVICE = re.compile(r"\b(buy|sell|accumulate|avoid|cheap|expensive|bullish|bearish|target|should|recommend)\b", re.I)
NOTICE_TEXT = ("ACME LIMITED\nNovember 10, 2026\nSub: Earnings Conference Call - Q2 FY27\nWe hereby inform that an 'Earnings "
               "Conference Call' is scheduled on Monday, November 16, 2026 at 4:00 PM (IST) to discuss the unaudited financial results.\n"
               "Click here to pre-register.\nDial-in: +91 22 6280 1107\nwww.acme.example")
JOIN = "https://services.choruscall.in/DiamondPassRegistration/register?confirmationNumber=1&linkSecurityString=ab"
SUBJECT = "Analysts/Institutional Investor Meet/Con. Call Updates"


@pytest.fixture
def mem(monkeypatch):
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    C.forget()
    R.forget()
    yield store
    C.forget()


def raw(symbol, text, when="2026-11-10 18:00:00", desc=SUBJECT, url=None, seq=None):
    return {"symbol": symbol, "sm_name": f"{symbol.title()} Limited", "desc": desc, "attchmntText": text, "sort_date": when,
            "seq_id": seq or f"{symbol}-{when}-{text[:10]}", "attchmntFile": url or f"https://nsearchives.nseindia.com/corporate/{symbol}_{abs(hash(text)) % 10**6}.pdf"}


# ---------- which filings ----------
def test_kind_of_tells_notices_from_what_is_filed_after_a_call():
    assert C.kind_of(SUBJECT, "Acme Limited has informed the Exchange about Schedule of meet", None, "investor_meet") == "notice"
    assert C.kind_of(SUBJECT, "Acme Limited has informed the Exchange about Transcript", None, "concall") == "transcript"
    assert C.kind_of(SUBJECT, "Acme Limited has informed the Exchange about Link of Recording", None, "concall") == "recording"
    assert C.kind_of("Investor Presentation", "Acme Limited has informed the Exchange about Investor Presentation", None, "presentation") == "presentation"
    assert C.kind_of(SUBJECT, "Outcome of the conference call held on November 5, 2026", None, "concall") == "outcome"
    assert C.kind_of("Outcome of Board Meeting", "Acme has submitted the financial results", None, "results") is None
    assert C.kind_of("Shareholders meeting", "Transcript of the Annual General Meeting", None, "agm") is None       # a shareholders' meeting


def test_meet_rows_keep_the_market_lists_call_filings_with_a_stable_id():
    rows = C.meet_rows([raw("ACME", "Acme Limited has informed the Exchange about Schedule of meet"),
                        raw("ACME", "Acme Limited has submitted the financial results", desc="Outcome of Board Meeting"),
                        raw("bad sym!", "Schedule of meet"), "junk"])
    assert [(r["symbol"], r["kind"]) for r in rows] == [("ACME", "notice")]
    assert rows[0]["company"] == "Acme Limited" and rows[0]["url"].startswith("https://nsearchives")
    again = C.meet_rows([raw("ACME", "Acme Limited has informed the Exchange about Schedule of meet", seq="other")])
    assert again[0]["id"] == rows[0]["id"]


def test_the_exchange_feed_hands_over_the_calls_from_the_same_one_call_as_the_red_flags():
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.url.path)
        if req.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "nsit=abc; Path=/"})
        return httpx.Response(200, json=[raw("ABC", "Resignation of the Statutory Auditor", desc="Change in Auditors"),
                                         raw("DEF", "Def Limited has informed the Exchange about Schedule of meet")])
    feed = F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert [r["symbol"] for r in feed.market_flags(date(2026, 11, 10))] == ["ABC"]
    assert [r["symbol"] for r in feed.market_meets(date(2026, 11, 10))] == ["DEF"]
    assert calls.count("/api/corporate-announcements") == 1


# ---------- what a notice says ----------
def row(text="Schedule of meet", at="2026-11-10T18:00", kind="notice", symbol="ACME", url=None):
    return {"id": f"{symbol}|{at}|{abs(hash(text)) % 10**8}", "symbol": symbol, "company": f"{symbol.title()} Limited", "at": at, "kind": kind,
            "subject": SUBJECT, "text": text, "url": url or f"https://nsearchives.nseindia.com/corporate/{symbol}_{abs(hash(text + at)) % 10**6}.pdf"}


def test_a_call_notice_gives_the_day_time_and_zone():
    ev = C.notice_event(row(), NOTICE_TEXT)
    assert ev == {"type": "call", "dates": ["2026-11-16"], "time": "16:00", "tz": "IST", "rescheduled": False}
    assert C.notice_event(row(), "conference call on 13th November, 2026 at 15:00 hrs")["time"] == "15:00"
    assert C.notice_event(row(), "Earnings call on November 19,\n202 6 at 11:30 AM")["dates"] == ["2026-11-19"]      # a year split by the PDF


def test_the_exchanges_own_subject_does_not_make_a_meeting_a_call():
    text = ("Schedule of analysts/institutional investors meet\nDate Event Type\nNovember 16, 2026 India Forum In-Person Group Mumbai\n"
            "November 18, 2026 Asia Pacific Summit In-Person Group Singapore")
    ev = C.notice_event(row(text="Acme has informed the Exchange about Schedule of meet"), text)
    assert ev["type"] == "meet" and ev["dates"] == ["2026-11-16", "2026-11-18"]


def test_a_letters_own_date_is_not_the_event_but_a_same_day_meeting_after_on_is():
    assert C.notice_event(row(), "November 10, 2026\nSchedule of meet\nNo date follows.") is None
    ev = C.notice_event(row(), "November 10, 2026\nrepresentatives will be meeting investors on Monday, November 10, 2026 at 09:00 AM onwards")
    assert ev["dates"] == ["2026-11-10"] and ev["time"] == "09:00"


def test_links_only_from_the_filing_and_only_the_kinds_worth_showing():
    urls = C.links_in("Webcast: www.acme.example/investors\nAudio at https://acme.example/files/Q2_Concall_Audio.mp3\nmail investor@acme.example",
                      [JOIN, "mailto:cs@acme.example", "https://www.nseindia.com/x", "https://acme.example/"])
    kinds = C.typed_links("notice", urls)
    assert {"k": "join", "u": JOIN} in kinds and not any("mailto" in x["u"] or "nseindia" in x["u"] for x in kinds)
    assert all(x["u"] != "https://acme.example/" for x in kinds)                                  # a home page isn't a link to show
    rec = C.typed_links("recording", urls)
    assert {"k": "audio", "u": "https://acme.example/files/Q2_Concall_Audio.mp3"} in rec
    assert C.typed_links("transcript", ["https://acme.example/uploads/Q2-Earnings-Call-Transcript.pdf"])[0]["k"] == "transcript"


def test_held_on_reads_the_day_a_call_was_held():
    assert C.held_on(row(at="2026-11-11T20:00", kind="transcript"), "the transcript of the earnings call for the quarter, held on November 5, 2026.") == date(2026, 11, 5)
    assert C.held_on(row(at="2026-11-11T20:00", kind="recording"), "was held today i.e. on November 11, 2026") == date(2026, 11, 11)
    assert C.held_on(row(at="2026-11-11T20:00", kind="transcript"), "Transcript") is None


# ---------- the store ----------
def reader(texts: dict):
    def read(url):
        got = texts.get(url)
        if isinstance(got, Exception):
            raise got
        return got if got is not None else ("", [])
    return read


def test_a_notice_then_its_transcript_and_recording_make_one_call_with_its_links():
    n = row(at="2026-11-10T18:00")
    t = row("Acme Limited has informed the Exchange about Transcript", at="2026-11-20T19:00", kind="transcript")
    r = row("Acme Limited has informed the Exchange about Link of Recording", at="2026-11-16T21:00", kind="recording")
    d = row("Investor Presentation", at="2026-11-16T10:00", kind="presentation")
    doc = {"events": [], "pending": [], "seen": {}}
    got = C.process(doc, [n], reader({n["url"]: (NOTICE_TEXT, [JOIN])}), today=date(2026, 11, 10))
    assert got["events"] == 1 and got["reads"] == 1
    out = C.process(doc, [t, r, d], reader({t["url"]: ("held on November 16, 2026", []),
                                            r["url"]: ("audio recording: https://acme.example/a/Q2_Concall.mp3", [])}), today=date(2026, 11, 21))
    assert out["events"] == 1
    ev = doc["events"][0]
    assert (ev["date"], ev["time"], ev["tz"], ev["type"]) == ("2026-11-16", "16:00", "IST", "call")
    kinds = [x["k"] for x in ev["links"]]
    assert kinds[:2] == ["notice", "join"] and {"transcript", "audio", "presentation"} <= set(kinds)
    assert next(x for x in ev["links"] if x["k"] == "transcript")["u"] == t["url"]               # the transcript is the filing itself
    assert next(x for x in ev["links"] if x["k"] == "audio")["u"] == "https://acme.example/a/Q2_Concall.mp3"
    assert set(doc["seen"]) == {n["id"], t["id"], r["id"], d["id"]} and doc["pending"] == []


def test_a_transcript_with_no_notice_is_a_call_of_its_own_and_a_lone_presentation_is_not():
    t = row("Transcript", at="2026-11-11T20:00", kind="transcript", symbol="BETA")
    d = row("Investor Presentation", at="2026-11-11T20:00", kind="presentation", symbol="GAMA")
    doc = {"events": [], "pending": [], "seen": {}}
    C.process(doc, [t, d], reader({t["url"]: ("transcript of the call held on November 5, 2026", [])}), today=date(2026, 11, 12))
    assert [(e["symbol"], e["date"], e.get("from_followup")) for e in doc["events"]] == [("BETA", "2026-11-05", True)]


def test_a_rescheduled_call_replaces_the_earlier_one_and_a_repeat_notice_merges():
    a = row(at="2026-11-05T10:00")
    b = row("Rescheduled", at="2026-11-09T10:00")
    c = row("again", at="2026-11-09T11:00")
    doc = {"events": [], "pending": [], "seen": {}}
    C.process(doc, [a], reader({a["url"]: ("Earnings call on November 12, 2026 at 11:00 AM IST", [])}), today=date(2026, 11, 5))
    C.process(doc, [b, c], reader({b["url"]: ("The earnings call is rescheduled to November 18, 2026 at 3:00 PM IST", []),
                                   c["url"]: ("Earnings call on November 18, 2026 at 3:00 PM IST", [JOIN])}), today=date(2026, 11, 9))
    assert [(e["date"], e["time"]) for e in doc["events"]] == [("2026-11-18", "15:00")]
    assert len([x for x in doc["events"][0]["links"] if x["k"] == "notice"]) == 2


def test_reads_are_bounded_and_what_is_not_read_waits_then_goes_on_its_filing_link():
    rows = [row(f"n{i}", at=f"2026-11-10T1{i}:00") for i in range(5)]
    doc = {"events": [], "pending": [], "seen": {}}
    got = C.process(doc, rows, reader({}), limit=2, today=date(2026, 11, 10))
    assert got["reads"] == 2 and len(doc["pending"]) == 3                       # the rest wait for the next run
    busy = row("busy", at="2026-11-10T09:00")
    doc2 = {"events": [], "pending": [], "seen": {}}
    got = C.process(doc2, [busy, row("other", at="2026-11-10T08:00")], reader({busy["url"]: SourceError("x", "busy", busy=True)}), today=date(2026, 11, 10))
    assert got["busy"] and got["reads"] == 1 and len(doc2["pending"]) == 2      # the archive turned us away: nothing more this run
    old = row("old notice, never readable", at="2026-10-01T10:00")
    doc3 = {"events": [], "pending": [{**old, "tries": 0}], "seen": {}}
    C.process(doc3, [], reader({}), limit=0, today=date(2026, 11, 10))
    assert doc3["pending"] == [] and old["id"] in doc3["seen"]                   # past its days: given up


def test_the_evening_run_reads_the_days_lists_and_a_feed_without_them_is_left_alone(mem):
    n = row(at="2026-11-10T18:00")

    class Feed:
        def __init__(self):
            self.days = []

        def market_meets(self, day):
            self.days.append(day)
            return [n] if day == date(2026, 11, 10) else []
    feed = Feed()
    out = C.after_india(feed, date(2026, 11, 12), read=reader({n["url"]: (NOTICE_TEXT, [JOIN])}))
    assert out["events"] == 1 and feed.days[0] == date(2026, 11, 12) - timedelta(days=C.FIRST_DAYS) and feed.days[-1] == date(2026, 11, 12)
    stored = json.loads(mem[C.KEY])
    assert stored["through"] == "2026-11-12" and stored["events"][0]["date"] == "2026-11-16"
    feed.days.clear()
    C.after_india(feed, date(2026, 11, 13), read=reader({}))
    assert feed.days[0] == date(2026, 11, 10)                                    # two days back from the last day read
    assert C.after_india(object(), date(2026, 11, 13)) is None


def test_the_red_flag_run_hands_its_feed_to_the_calendar(mem, monkeypatch):
    seen = []
    monkeypatch.setattr(C, "after_india", lambda feed, today, **kw: seen.append((feed, today)))

    class Feed:
        def market_flags(self, day):
            return []
    feed = Feed()
    R.Runner(lambda: {"in": feed}, sleep=lambda s: None, pause=0).run("IN", date(2026, 11, 12))
    assert seen == [(feed, date(2026, 11, 12))]


# ---------- the page ----------
def seed(mem, today=date(2026, 11, 12)):
    events = [
        {"id": "ACME|2026-11-13|call", "symbol": "ACME", "name": "Acme Limited", "date": "2026-11-13", "type": "call", "time": "16:00", "tz": "IST",
         "filed": "2026-11-10T18:00", "links": [{"k": "notice", "u": "https://nsearchives.nseindia.com/corporate/a.pdf", "at": "2026-11-10T18:00"},
                                                 {"k": "join", "u": JOIN, "at": "2026-11-10T18:00"}]},
        {"id": "BETA|2026-11-24|meet", "symbol": "BETA", "name": "Beta Limited", "date": "2026-11-24", "until": "2026-11-26", "dates": ["2026-11-24", "2026-11-26"],
         "type": "meet", "filed": "2026-11-10T18:00", "links": [{"k": "notice", "u": "https://nsearchives.nseindia.com/corporate/b.pdf", "at": ""}]},
        {"id": "GAMA|2026-11-05|call", "symbol": "GAMA", "name": "Gama Limited", "date": "2026-11-05", "type": "call", "filed": "2026-11-01T10:00",
         "links": [{"k": "notice", "u": "https://nsearchives.nseindia.com/corporate/g.pdf", "at": ""},
                   {"k": "transcript", "u": "https://nsearchives.nseindia.com/corporate/t.pdf", "at": "2026-11-09T10:00"}]},
    ]
    mem[C.KEY] = json.dumps({"events": events, "pending": [], "seen": {}, "through": today.isoformat(), "at": "2026-11-12T21:30"})
    C.forget()


def test_view_lists_what_is_coming_soonest_first_and_what_was_held_with_its_transcript(mem):
    seed(mem)
    up = C.view("IN", today=date(2026, 11, 12))
    assert [r["symbol"] for r in up["rows"]] == ["ACME", "BETA"] and up["rows"][0]["links"][0]["kind"] == "join"
    assert up["rows"][0]["type_label"] == "Earnings call" and up["rows"][1]["until"] == "2026-11-26"
    past = C.view("IN", when="past", today=date(2026, 11, 12))
    assert [r["symbol"] for r in past["rows"]] == ["GAMA"] and {x["kind"] for x in past["rows"][0]["links"]} == {"notice", "transcript"}
    assert [r["symbol"] for r in C.view("IN", kind="meet", today=date(2026, 11, 12))["rows"]] == ["BETA"]
    assert [r["symbol"] for r in C.view("IN", scope="mine", mine={"BETA"}, today=date(2026, 11, 12))["rows"]] == ["BETA"]
    assert [r["symbol"] for r in C.view("IN", q="acme", today=date(2026, 11, 12))["rows"]] == ["ACME"]
    assert not ADVICE.search(json.dumps(up))


def test_without_the_full_calendar_only_this_weeks_calls_and_their_notice_and_join_links(mem):
    seed(mem)
    v = C.view("IN", today=date(2026, 11, 12), full=False)
    assert [r["symbol"] for r in v["rows"]] == ["ACME"] and v["to"] == "2026-11-15" and v["full"] is False      # to Sunday
    seed(mem)
    v = C.view("IN", when="past", today=date(2026, 11, 12), full=False)
    assert all(x["kind"] in ("notice", "join") for r in v["rows"] for x in r["links"])


def test_us_rows_are_the_results_calendars_sessions_and_the_filed_release(mem):
    mem[results.KEY + "US"] = json.dumps({"at": "x", "v": 2, "rows": [
        {"region": "US", "symbol": "ZZZ", "name": "Zed Corp", "date": "2026-11-13", "when": "after the close", "purpose": "Quarterly results"},
        {"region": "US", "symbol": "YYY", "name": "Why Inc", "date": "2026-11-10", "when": "before the open", "purpose": "Quarterly results",
         "out": {"at": "2026-11-10", "title": "Earnings release (8-K)", "url": "https://www.sec.gov/Archives/edgar/data/1/x.htm"}}]})
    up = C.view("US", today=date(2026, 11, 12))
    assert [(r["symbol"], r["session"], r["tz"], r["type"]) for r in up["rows"]] == [("ZZZ", "after the close", "ET", "results")]
    past = C.view("US", when="past", today=date(2026, 11, 12))
    assert past["rows"][0]["links"] == [{"kind": "release", "label": "Earnings release (8-K)", "url": "https://www.sec.gov/Archives/edgar/data/1/x.htm", "filed": "2026-11-10"}]


@pytest.fixture
def client(mem, monkeypatch):
    who = {"p": {"id": "u1", "plan": "basic", "_plan": "basic"}}
    main.app.dependency_overrides[main.current_profile] = lambda: who["p"]
    monkeypatch.setattr(results, "my_stocks", lambda uid, region=None: ["ACME"])
    c = TestClient(main.app)
    c.who = who
    yield c
    main.app.dependency_overrides.clear()


def test_the_route_gives_basic_the_full_calendar_and_free_this_week(client, mem):
    import time_machine
    with time_machine.travel(datetime(2026, 11, 12, 6, 0)):
        seed(mem)
        r = client.get("/research/earnings-calls?region=IN&scope=mine")
        assert r.status_code == 200 and [x["symbol"] for x in r.json()["rows"]] == ["ACME"] and r.json()["full"] is True
        assert client.get("/research/earnings-calls?when=past").json()["rows"][0]["symbol"] == "GAMA"
        client.who["p"] = {"id": "u1", "plan": "free", "_plan": "free"}
        r = client.get("/research/earnings-calls")
        assert r.status_code == 200 and r.json()["full"] is False and r.json()["plan_needed"] == "Basic"
        assert [x["symbol"] for x in r.json()["rows"]] == ["ACME"]
        for q in ("when=past", "scope=mine", "kind=call", "q=acme"):
            assert client.get(f"/research/earnings-calls?{q}").status_code == 402
        assert client.get("/research/earnings-calls?when=later").status_code == 400


def test_the_money_calendar_feed_carries_your_stocks_calls_on_basic(mem, monkeypatch):
    seed(mem)
    monkeypatch.setattr(money_calendar, "tracked", lambda uid: ({"ACME": {}}, [("IN", "BETA"), ("US", "ZZZ")]))
    monkeypatch.setattr(db, "cached_profile", lambda uid: {"id": uid, "plan": "basic", "_plan": "basic"})
    assert ("concalls", "calendar_dates", "holdings") in money_calendar.HOOKS
    import time_machine
    with time_machine.travel(datetime(2026, 11, 12, 6, 0)):
        got = C.calendar_dates("u1", 30)
        assert [(e["date"], e["title"]) for e in got] == [("2026-11-13", "ACME: earnings call at 16:00 IST"), ("2026-11-24", "BETA: analyst or investor meet")]
        assert JOIN in got[0]["detail"] and got[0]["url"] == "/research/IN/ACME"
        monkeypatch.setattr(db, "cached_profile", lambda uid: {"id": uid, "plan": "free", "_plan": "free"})
        assert C.calendar_dates("u1", 30) == []
