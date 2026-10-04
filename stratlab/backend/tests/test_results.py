"""The results calendar: reading the feeds (fakes for the exchange's board meetings, company notices, the US results
feed and the SEC), the rolling stored calendar, the morning and results-are-out messages with their run markers, the
My Stocks newsletter section and the API."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import db, results as R
from app.intel.net import SourceError
from app.newsletter import content, write
from tests import world as W
from tests.fake_db import headers
from tests.fake_intel import us_calendar

TODAY = date(2026, 10, 5)              # a Monday
IN_MORNING = datetime(2026, 10, 5, 2, 45, tzinfo=timezone.utc)      # 08:15 IST


# ---------- fakes for the feeds ----------
class FakeIndia:
    """The exchange: a board-meeting list, each company's notices, and which companies are BSE-only."""

    def __init__(self, meetings=None, notices=None, bse=(), down=False):
        self.meetings, self.notices, self.bse, self.down = meetings or [], notices or {}, set(bse), down
        self.asked: list[str] = []

    def board_meetings(self, frm, to):
        if self.down:
            raise SourceError("the exchange", "busy", busy=True)
        return self.meetings

    def announcements(self, symbol, days=365):
        self.asked.append(symbol)
        return self.notices.get(symbol, [])

    def code_of(self, symbol):
        return "543210" if symbol in self.bse else None


class FakeUS:
    def __init__(self, rows=None, down=False):
        self.rows, self.down = rows or [], down

    def earnings_between(self, frm, to, ttl=3600):
        if self.down:
            raise SourceError("Finnhub", "down")
        return [r for r in self.rows if frm.isoformat() <= r.get("date", "") <= to.isoformat()]

    def earnings_calendar(self, sym):
        return [r for r in self.rows if r.get("symbol") == sym]


class FakeSEC:
    def __init__(self, filed: dict):
        self.filed = filed            # symbol -> [(form, date, items)]

    def cik(self, symbol):
        if symbol not in self.filed:
            raise SourceError("SEC EDGAR", "not a filer")
        return 1000 + len(symbol)

    def submissions(self, cik, fresh=False):
        sym = next(s for s in self.filed if 1000 + len(s) == cik)
        rows = self.filed[sym]
        return {"cik": cik, "filings": {"recent": {"form": [r[0] for r in rows], "filingDate": [r[1] for r in rows],
                                                   "accessionNumber": [f"0001-26-{i:06d}" for i in range(len(rows))],
                                                   "primaryDocument": ["d8k.htm"] * len(rows), "items": [r[2] for r in rows]}}}


def notice(subject, text, at, url="https://nsearchives.nseindia.com/n.pdf", category="board"):
    return {"subject": subject, "text": text, "at": at, "url": url, "category": category, "severity": "info"}


def meeting(sym, day, purpose="Financial Results"):
    return {"bm_symbol": sym, "sm_name": f"{sym} Ltd", "bm_date": day.strftime("%d-%b-%Y"), "bm_purpose": purpose,
            "bm_desc": f"To consider: {purpose.lower()}", "attachment": "https://nsearchives.nseindia.com/x.pdf"}


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    content._cache.clear()
    write._cache.clear()
    yield world
    world["close"]()


def watch(uid, *items):
    db.set_setting(f"watchlist:{uid}", json.dumps({"items": [{"region": r, "symbol": s} for r, s in items]}))


# ---------- reading the feeds ----------
def test_exchange_rows_keep_only_results_meetings():
    rows = R.india_rows([meeting("RELIANCE", TODAY), meeting("INFY", TODAY, "Dividend"), {"bm_symbol": "X", "bm_date": "junk"}, "junk"])
    assert [(r["symbol"], r["date"], r["region"]) for r in rows] == [("RELIANCE", "2026-10-05", "IN")]
    assert rows[0]["name"] == "RELIANCE Ltd" and rows[0]["url"].startswith("https://")


@pytest.mark.parametrize("text,day", [
    ("Board meeting to be held on Thursday, 15th October, 2026 to consider financial results", date(2026, 10, 15)),
    ("meeting of the Board of Directors is scheduled on October 15, 2026 inter alia to approve the results", date(2026, 10, 15)),
    ("Board Meeting on 15-10-2026 to consider the unaudited financial results", date(2026, 10, 15)),
    ("Board meeting on 15-Oct-2026 for financial results", date(2026, 10, 15)),
])
def test_dates_read_from_company_notices(text, day):
    items = [notice("Board Meeting Intimation", text, "2026-10-01T18:10")]
    assert [r["date"] for r in R.from_announcements("ABC", items, TODAY)] == [day.isoformat()]


def test_notices_that_arent_upcoming_results_meetings_are_ignored():
    items = [notice("Outcome of Board Meeting", "The board approved the financial results on 01-10-2026", "2026-10-01T18:10"),
             notice("Board Meeting Intimation", "Board meeting on 20-10-2026 to consider a fund raise", "2026-10-01T18:10"),
             notice("Board Meeting Intimation", "Board meeting on 20-10-2025 for financial results", "2026-10-01T18:10"),   # before it was filed
             notice("Board Meeting Intimation", "Board meeting on 20-10-2026 for financial results", "2026-06-01T18:10")]   # an old notice
    assert R.from_announcements("ABC", items, TODAY) == []


def test_us_rows_carry_reported_numbers_but_never_estimates():
    rows = {r["symbol"]: r for r in R.us_rows(us_calendar(TODAY))}
    assert set(rows) == {"AAPL", "NVDA", "MSFT"}
    assert rows["AAPL"]["when"] == "after the close" and rows["AAPL"]["purpose"] == "Quarterly results (Q4 2026)"
    assert rows["MSFT"]["reported"] == [{"label": "EPS", "value": "$3.21"}, {"label": "Revenue", "value": "$69.40 billion"}]
    assert "estimate" not in json.dumps(rows).lower()


# ---------- the stored, rolling calendar ----------
def test_merge_moves_a_rescheduled_meeting_and_keeps_what_was_learnt():
    old = [R.row("IN", "AAA", TODAY + timedelta(days=3), "Financial Results"),
           {**R.row("IN", "BBB", TODAY - timedelta(days=1), "Financial Results"), "out": {"url": "https://x/y.pdf"}},
           R.row("IN", "CCC", TODAY - timedelta(days=6), "Financial Results"),          # before the fetched window: kept
           R.row("IN", "DDD", TODAY - timedelta(days=20), "Financial Results")]         # older than a week: dropped
    new = [R.row("IN", "AAA", TODAY + timedelta(days=5), "Financial Results"), R.row("IN", "BBB", TODAY - timedelta(days=1), "Financial Results"),
           R.row("IN", "EEE", TODAY + timedelta(days=2), "Board meeting", src="announcement"),
           R.row("IN", "EEE", TODAY + timedelta(days=4), "Financial Results")]
    got = {(r["symbol"], r["date"]): r for r in R.merge(old, new, TODAY - timedelta(days=3), TODAY)}
    assert ("AAA", (TODAY + timedelta(days=5)).isoformat()) in got and ("AAA", (TODAY + timedelta(days=3)).isoformat()) not in got
    assert got[("BBB", (TODAY - timedelta(days=1)).isoformat())]["out"] == {"url": "https://x/y.pdf"}
    assert ("CCC", (TODAY - timedelta(days=6)).isoformat()) in got and not any(k[0] == "DDD" for k in got)
    assert [k for k in got if k[0] == "EEE"] == [("EEE", (TODAY + timedelta(days=4)).isoformat())]      # the exchange's list wins


def test_refresh_stores_both_regions_and_reads_bse_only_companies_from_notices(w):
    india = FakeIndia([meeting("RELIANCE", TODAY + timedelta(days=2))],
                      {"SMALLCO": [notice("Board Meeting Intimation", "Board meeting on 09-10-2026 to consider financial results", "2026-10-02T10:00")]},
                      bse={"SMALLCO"})
    out = R.refresh("IN", {"in": india}, {"RELIANCE", "SMALLCO"}, TODAY)
    assert out["rows"] == 2 and india.asked == ["SMALLCO"]          # NSE companies come from the one market-wide call
    assert {r["symbol"]: r["src"] for r in R.load("IN")["rows"]} == {"RELIANCE": "exchange", "SMALLCO": "announcement"}
    R.refresh("US", {"us": FakeUS(us_calendar(TODAY))}, set(), TODAY)
    assert {r["symbol"] for r in R.load("US")["rows"]} == {"AAPL", "NVDA", "MSFT"}
    assert R.lookup("US", "aapl", TODAY)["next"]["date"] == "2026-10-06"
    assert R.lookup("US", "MSFT", TODAY)["last"]["date"] == "2026-10-03" and R.lookup("US", "MSFT", TODAY)["next"] is None


def test_when_the_exchange_list_is_down_tracked_companies_are_read_one_by_one(w):
    R.refresh("IN", {"in": FakeIndia([meeting("TCS", TODAY + timedelta(days=4))])}, set(), TODAY)
    india = FakeIndia(down=True, notices={"RELIANCE": [notice("Board Meeting Intimation", "Board meeting on 08-10-2026 to consider financial results", "2026-10-02T10:00")]})
    out = R.refresh("IN", {"in": india}, {"RELIANCE"}, TODAY)
    assert out["problems"] and india.asked == ["RELIANCE"]
    assert {r["symbol"] for r in R.load("IN")["rows"]} == {"RELIANCE", "TCS"}      # TCS's date wasn't asked again, so it stays
    before = R.load("IN")
    assert R.refresh("IN", {"in": FakeIndia(down=True)}, set(), TODAY)["rows"] is None
    assert R.load("IN") == before                                   # every source failed: the calendar is left alone


# ---------- the messages ----------
def job_with(india=None, us=None, sec=None):
    sent = []
    job = R.Job(lambda: {"in": india or FakeIndia(), "us": us or FakeUS(), "sec": sec},
                send=lambda p, subject, text, url: sent.append((p["id"], subject, text, url)), can_alert=lambda p: R.alerts_on(p["id"]))
    return job, sent


def test_results_morning_message_goes_once_to_people_tracking_the_stock(w):
    watch("u-pro", ("IN", "RELIANCE"), ("IN", "TCS"))
    watch("u-free", ("IN", "INFY"))
    india = FakeIndia([meeting("RELIANCE", TODAY), meeting("TCS", TODAY), meeting("INFY", TODAY + timedelta(days=1))])
    job, sent = job_with(india)
    assert job.tick(datetime(2026, 10, 5, 1, 0, tzinfo=timezone.utc)) == 0          # 06:30 IST: too early for anything
    job.tick(IN_MORNING)
    assert [(uid, subject) for uid, subject, _, _ in sent] == [("u-pro", "StratLab: results today")]
    text = sent[0][2]
    assert "RELIANCE" in text and "TCS" in text and "INFY" not in text and not write.banned(text)
    job.tick(IN_MORNING + timedelta(minutes=5))
    again, sent2 = job_with(india)                                   # a restart: the run marker is in the database
    again.tick(IN_MORNING + timedelta(minutes=10))
    assert len(sent) == 1 and sent2 == []


def test_people_who_turned_results_messages_off_dont_get_them(w):
    watch("u-pro", ("IN", "RELIANCE"))
    R.set_alerts("u-pro", False)
    job, sent = job_with(FakeIndia([meeting("RELIANCE", TODAY)]))
    job.tick(IN_MORNING)
    assert sent == []


def test_default_alert_check_needs_a_phone_or_telegram(w, monkeypatch):
    from app import alerts
    seen = []
    monkeypatch.setattr(alerts, "jobs_for", lambda p, s, t, url="": seen.append(p) or ([("telegram", None)] if p.get("telegram_chat_id") else []))
    assert R.can_alert({"id": "u-pro", "telegram_chat_id": "1", "email": "a@b.c"})
    assert not R.can_alert({"id": "u-pro", "email": "a@b.c"})
    assert all(p["email"] is None and p["alert_email"] is None for p in seen)      # never by email: the newsletter covers that


def test_india_results_out_message_has_the_filing_and_stated_numbers(w):
    watch("u-pro", ("IN", "RELIANCE"))
    filed = notice("Outcome of Board Meeting - Financial Results",
                   "Financial results for the quarter ended September 30, 2026. Revenue from operations of Rs 2,35,481 crore; "
                   "net profit of Rs 18,540 crore.", "2026-10-05T16:40", url="https://nsearchives.nseindia.com/res.pdf", category="results")
    early = notice("Board Meeting Intimation", "Board meeting on 05-10-2026 to consider financial results", "2026-09-28T10:00")
    india = FakeIndia([meeting("RELIANCE", TODAY)], {"RELIANCE": [filed, early]})
    job, sent = job_with(india)
    R.refresh("IN", {"in": india}, set(), TODAY)
    job.tick(datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc))           # 15:30 IST: morning, then the hourly check
    outs = [s for s in sent if "results are out" in s[1]]
    assert len(outs) == 1
    _, subject, text, url = outs[0]
    assert subject == "StratLab: RELIANCE results are out" and url == "/research/IN/RELIANCE"
    assert "https://nsearchives.nseindia.com/res.pdf" in text and "Revenue from operations ₹2,35,481 crore" in text
    assert "Net profit ₹18,540 crore" in text and not write.banned(text)
    row = R.lookup("IN", "RELIANCE", TODAY)["next"]
    assert row["out"]["url"] == "https://nsearchives.nseindia.com/res.pdf"
    job.tick(datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc))           # the next hour: already sent, not again
    assert len([s for s in sent if "results are out" in s[1]]) == 1


def test_no_filing_yet_means_no_message(w):
    watch("u-pro", ("IN", "RELIANCE"))
    india = FakeIndia([meeting("RELIANCE", TODAY)], {"RELIANCE": [notice("Board Meeting Intimation", "Board meeting on 05-10-2026 to consider financial results", "2026-09-28T10:00")]})
    R.refresh("IN", {"in": india}, set(), TODAY)
    assert R.check_out("IN", {"in": india}, {"RELIANCE"}, TODAY) == []


def test_us_results_out_from_the_8k_and_the_reported_numbers(w):
    watch("u-pro", ("US", "MSFT"))
    us = FakeUS(us_calendar(TODAY))
    sec = FakeSEC({"MSFT": [("8-K", "2026-10-03", "2.02,9.01"), ("10-Q", "2026-07-30", ""), ("8-K", "2026-09-01", "5.02")]})
    R.refresh("US", {"us": us}, set(), TODAY)
    found = R.check_out("US", {"us": us, "sec": sec}, {"MSFT"}, TODAY)
    assert len(found) == 1
    o = found[0]["out"]
    assert o["title"] == "Earnings release (8-K)" and o["url"].startswith("https://www.sec.gov/Archives/") and o["at"] == "2026-10-03"
    assert o["numbers"][0] == {"label": "EPS", "value": "$3.21"}
    text = R.out_text(found[0])
    assert "MSFT results are out" in text and "$69.40 billion" in text and "Finnhub" not in text and not write.banned(text)
    assert R.check_out("US", {"us": us, "sec": sec}, {"MSFT"}, TODAY) == []          # found once


# ---------- the newsletter ----------
def test_my_stocks_newsletter_has_a_results_this_week_section(w):
    watch("u-pro", ("IN", "RELIANCE"), ("US", "MSFT"))
    R.refresh("IN", {"in": FakeIndia([meeting("RELIANCE", TODAY + timedelta(days=1))])}, set(), TODAY)
    R.refresh("US", {"us": FakeUS(us_calendar(TODAY))}, set(), TODAY)
    R.check_out("US", {"us": FakeUS(us_calendar(TODAY)), "sec": FakeSEC({"MSFT": [("8-K", "2026-10-03", "2.02")]})}, {"MSFT"}, TODAY)
    due = content.results_week("u-pro", TODAY, False, "2026-10-02")
    assert [(r["symbol"], bool(r["out"])) for r in due] == [("MSFT", True), ("RELIANCE", False)]
    f = {"kind": "my_stocks", "uid": "u-pro", "day": TODAY.isoformat(), "weekly": False, "since": "2026-10-02",
         "stocks": [], "unchanged": [], "results": due, "paper": []}
    secs = {s["title"]: s for s in write.sections(f)}
    items = secs["Results this week"]["items"]
    assert items[0]["text"].startswith("MSFT: results filed Sat 03 Oct") and items[0]["lines"][0]["text"] == "EPS: $3.21 (as stated in the filing)"
    assert items[1]["text"] == "RELIANCE: Financial Results on Tue 06 Oct"
    assert write.subject(f) == "My Stocks, Mon 05 Oct: results this week for 2 of your stocks"
    assert "results date this week" in write.template(f) and not write.banned(write.template(f))


def test_results_tomorrow_count_as_news_for_my_stocks(w, monkeypatch):
    watch("u-pro", ("IN", "RELIANCE"))
    monkeypatch.setattr(content, "stock_row", lambda *a, **k: None)          # no price news at all
    R.refresh("IN", {"in": FakeIndia([meeting("RELIANCE", TODAY + timedelta(days=5))])}, set(), TODAY)
    assert not content.stock_facts("u-pro", TODAY)["changed"]                # later in the week: listed, not news by itself
    R.refresh("IN", {"in": FakeIndia([meeting("RELIANCE", TODAY + timedelta(days=1))])}, set(), TODAY)
    f = content.stock_facts("u-pro", TODAY)
    assert f["changed"] and f["results"][0]["symbol"] == "RELIANCE"


# ---------- the API ----------
def test_results_page_api_mine_and_all(w):
    c = w["client"]
    c.get("/me", headers=headers("pro-token"))
    watch("u-pro", ("IN", "RELIANCE"))
    r = c.get("/research/results", params={"region": "IN"}, headers=headers("pro-token"))
    assert r.status_code == 200, r.text
    body = r.json()                                         # built on first visit from the (fake) exchange list
    rows = [x for wk in body["weeks"] for x in wk["rows"]]
    assert [x["symbol"] for x in rows] == ["RELIANCE"] and rows[0]["mine"] and body["alerts"] and body["updated_at"]
    assert [wk["label"] for wk in body["weeks"]] == ["This week", "Next week"]
    every = c.get("/research/results", params={"region": "IN", "scope": "all"}, headers=headers("pro-token")).json()
    assert {x["symbol"] for wk in every["weeks"] for x in wk["rows"]} >= {"RELIANCE"}
    assert "INFY" not in json.dumps(every)                  # a dividend meeting isn't a results date
    us = c.get("/research/results", params={"region": "US", "scope": "all", "q": "aap"}, headers=headers("pro-token"))
    assert us.status_code == 200 and "finnhub" not in us.text.lower()
    assert {x["symbol"] for wk in us.json()["weeks"] for x in wk["rows"]} <= {"AAPL"}
    one = c.get("/research/results/IN/RELIANCE", headers=headers("pro-token")).json()
    assert one["next"]["symbol"] == "RELIANCE"
    assert c.get("/research/results/XX/RELIANCE", headers=headers("pro-token")).status_code == 400
    assert c.put("/research/results/alerts", json={"on": False}, headers=headers("pro-token")).json() == {"alerts": False}
    assert c.get("/research/results", headers=headers("pro-token")).json()["alerts"] is False
    assert c.get("/research/results").status_code == 401


def test_admin_refresh(w):
    c = w["client"]
    r = c.post("/admin/results/refresh", headers=headers("admin-token"))
    assert r.status_code == 200, r.text
    assert r.json()["IN"]["rows"] >= 2 and r.json()["US"]["rows"] >= 3
    assert c.post("/admin/results/refresh", headers=headers("pro-token")).status_code == 403
