"""Release 89 site items (lane site89b): the US results calendar's duplicate rows, the Results page's "Usual move", the US heatmap and
sector rotation against India's, server paging for the corporate actions and earnings calls lists, and honest coverage counts."""
import json
from datetime import date

import pytest

from app import db, results as R
from app.intel import us_calendar
from tests import world


@pytest.fixture
def w(monkeypatch):
    world_ = world.build(monkeypatch)
    yield world_
    world_["close"]()


# ---------- 1. the US results calendar: one row per company per results ----------
class CompanyData:
    """The US company data's whole-market list (its fiscal quarters, no session for most)."""

    def __init__(self, rows):
        self.rows = rows

    def earnings_between(self, frm, to, ttl=3600):
        return [r for r in self.rows if frm.isoformat() <= r["date"] <= to.isoformat()]

    def earnings_calendar(self, sym):
        return []


class MarketCalendar:
    """The US market calendar, a day at a time (its quarter-end month, the session)."""

    def __init__(self, days: dict):
        self.days = days

    def earnings(self, d):
        return us_calendar.earnings_rows({"data": {"rows": self.days.get(d.isoformat(), [])}}, d)


TODAY_US = date(2026, 11, 25)                 # a Wednesday, as on the live site when the duplicates were seen


def live_like_sources():
    """The answers of 23-27 Nov 2026 as the live calendar had them: Burlington dated Mon 23 by the company data and Tue 24 (before the
    open) by the market calendar; Chagee and Nordic American on Thanksgiving by one and Fri 27 by the other; CrowdStrike on the calendar on
    two days for the same quarter; ABLT given two different fiscal quarters by the company data (two results, both kept)."""
    data = CompanyData([
        {"symbol": "BURL", "date": "2026-11-23", "quarter": 3, "year": 2027},
        {"symbol": "CHA", "date": "2026-11-26", "quarter": 3, "year": 2026},
        {"symbol": "NAT", "date": "2026-11-26", "hour": "bmo", "quarter": 3, "year": 2026},
        {"symbol": "ABLT", "date": "2026-11-23", "quarter": 3, "year": 2026},
        {"symbol": "ABLT", "date": "2026-12-01", "quarter": 1, "year": 2026},
        {"symbol": "DE", "date": "2026-11-25", "hour": "bmo", "quarter": 4, "year": 2026},
    ])
    cal = MarketCalendar({
        "2026-11-23": [{"symbol": "CRWD", "name": "CrowdStrike Holdings, Inc.", "time": "time-not-supplied", "fiscalQuarterEnding": "Oct/2026"}],
        "2026-11-24": [{"symbol": "BURL", "name": "Burlington Stores, Inc.", "time": "time-pre-market", "fiscalQuarterEnding": "Oct/2026"}],
        "2026-11-27": [{"symbol": "CHA", "name": "Chagee Holdings Limited", "time": "time-not-supplied", "fiscalQuarterEnding": "Sep/2026"},
                       {"symbol": "NAT", "name": "Nordic American Tankers Limited", "time": "time-not-supplied", "fiscalQuarterEnding": "Sep/2026"}],
        "2026-12-01": [{"symbol": "CRWD", "name": "CrowdStrike Holdings, Inc.", "time": "time-after-hours", "fiscalQuarterEnding": "Oct/2026"}],
    })
    return {"us": data, "cal": cal, "sec": None}


def test_the_us_calendar_lists_each_company_once_per_results(w):
    R.refresh("US", live_like_sources(), set(), TODAY_US)
    rows = R.load("US")["rows"]
    by: dict = {}
    for r in rows:
        by.setdefault(r["symbol"], []).append(r)
    assert [r["date"] for r in by["BURL"]] == ["2026-11-24"]                  # the calendar's day, with its session
    assert by["BURL"][0]["when"] == "before the open"
    assert [r["date"] for r in by["CHA"]] == ["2026-11-27"] and [r["date"] for r in by["NAT"]] == ["2026-11-27"]
    assert by["NAT"][0]["when"] == "before the open"                          # the company data's session carries over
    assert len(by["CRWD"]) == 1                                               # one quarter (Oct 2026) on two calendar days: one row
    assert sorted(r["date"] for r in by["ABLT"]) == ["2026-11-23", "2026-12-01"]   # two different quarters stay two rows
    assert len(by["DE"]) == 1
    # the page's answer, every company, day by day: nobody twice in the two weeks
    v = R.view("US", "u-pro", "all", today=TODAY_US, limit=50)
    shown = [r["symbol"] for wk in v["weeks"] for r in wk["rows"]]
    assert sorted(s for s in shown if s != "ABLT") == sorted(set(s for s in shown if s != "ABLT"))
    # the earnings calls list (US: the results calendar's rows) has each company once too
    from app import concalls
    calls = [r["symbol"] for r in concalls.us_rows(date(2026, 11, 23), date(2026, 12, 6)) if r["symbol"] != "ABLT"]
    assert sorted(calls) == sorted(set(calls)) and "CHA" in calls
    # the days gone by kept for the usual move: Burlington's results day once, on the calendar's day
    assert R.load_past("US")["rows"].get("BURL") is None or R.load_past("US")["rows"]["BURL"] == ["2026-11-24"]


def test_a_stored_us_calendar_with_both_dates_is_served_once(w):
    """The list stored before the fix (both rows) is served with one row per results at once, without waiting for the next refresh; what
    the dropped row learnt (the filing, who was told) stays on the kept one."""
    out = {"at": "2026-11-24", "title": "Earnings release (8-K)", "url": "https://www.sec.gov/x.htm", "numbers": []}
    stored = [R.row("US", "BURL", date(2026, 11, 23), "Quarterly results (fiscal Q3 2027)", src="company data", period="Q3 2027"),
              R.row("US", "BURL", date(2026, 11, 24), "Quarterly results (quarter ended Oct 2026)", when="before the open",
                    src="market calendar", period="Oct 2026")]
    stored[0].update(out=out, told=True)
    stored[1].update(out=out, told=False)
    db.set_setting(R.KEY + "US", json.dumps({"at": "2026-11-24T06:00", "v": R.CAL_VERSION, "rows": stored}))
    rows = R.load("US")["rows"]
    assert len(rows) == 1 and rows[0]["date"] == "2026-11-24" and rows[0]["when"] == "before the open"
    assert rows[0]["told"] is True                                            # already told under the other date: not told again
    # India's rows are left as they are
    db.set_setting(R.KEY + "IN", json.dumps({"at": "x", "v": R.CAL_VERSION, "rows": [
        R.row("IN", "TCS", date(2026, 11, 23), "Financial Results"), R.row("IN", "TCS", date(2026, 11, 26), "Financial Results")]}))
    assert len(R.load("IN")["rows"]) == 2


# ---------- 2. the Results page's "Usual move": earlier results days only, one per results, with its basis ----------
def _bars(days_closes: dict):
    return [{"t": f"{d}T00:00:00-05:00", "c": c} for d, c in sorted(days_closes.items())]


def test_a_usual_move_stands_on_earlier_results_days_once_each_and_says_so(w):
    """Live, 25 Nov: Burlington's row for its 24 Nov results said "Usual move ±0.4%", the move of those same results under the company
    data's date (23 Nov), and NVDA's "±3.3%" was its 17 Nov move alone: a US company kept only its latest results day. Now the row's own
    results are left out, a US company's earlier results days come from its earnings releases on the SEC's filing list, two dates of one
    results count once, and the answer carries the days it stands on."""
    out = {"at": "2026-11-24", "title": "Earnings release (8-K)", "url": "https://www.sec.gov/x.htm", "numbers": []}
    row = R.row("US", "BURL", date(2026, 11, 24), "Quarterly results (quarter ended Oct 2026)", when="before the open", src="market calendar", period="Oct 2026")
    row.update(out=out, told=True)
    R.save("US", [row])
    R.add_past("US", [{"symbol": "BURL", "date": "2026-11-23"}], TODAY_US)          # as the live store had it: this results' wrong date only
    closes = {"2026-11-20": 100, "2026-11-23": 99.6, "2026-11-24": 104, "2026-11-25": 104,
              "2026-08-26": 100, "2026-08-27": 100, "2026-08-28": 110,          # 27 Aug: +10%
              "2026-05-27": 100, "2026-05-28": 100, "2026-05-29": 96,           # 28 May: -4%
              "2026-03-04": 100, "2026-03-05": 100, "2026-03-06": 106}          # 5 Mar: +6%
    R.setup(history=lambda r, s, d: _bars(closes))
    # no filing list: its only kept day is this results' own, so there is no usual move (it was "±0.4%")
    got = R.moves_for("US", ["BURL"], TODAY_US)["BURL"]
    assert got is None or got["moves"] is None
    # the SEC's filing list: its earnings releases, one filed twice two days apart (an amended release) counting once
    R.setup(history=lambda r, s, d: _bars(closes), filed=lambda s: ["2026-11-24", "2026-08-27", "2026-05-28", "2026-05-26", "2026-03-05"])
    got = R.moves_for("US", ["BURL"], TODAY_US)["BURL"]["moves"]
    assert got["dates"] == ["2026-08-27", "2026-05-28", "2026-03-05"] and got["n"] == 3      # 24 Nov (its own) and 23 Nov left out
    assert got["last"] == [10.0, -4.0, 6.0] and got["avg"] == 6.7 and "close before the results day" in got["basis"]
    # the page's own row says the same
    v = R.view("US", "u-pro", "all", today=TODAY_US)
    burl = next(r for wk in v["weeks"] for r in wk["rows"] if r["symbol"] == "BURL")
    assert burl["moves"]["dates"] == got["dates"] and burl["mv_days"] == 3


def test_two_dates_of_one_indian_results_count_once():
    """SETCO's kept days on the live site: 24 Nov, 23 Oct, 31 Aug and 29 Aug (one results, its meeting moved), counted as four."""
    assert R.one_per_results(["2026-11-24", "2026-10-23", "2026-08-31", "2026-08-29", "2026-05-30"]) == ["2026-11-24", "2026-10-23", "2026-08-31", "2026-05-30"]
    store = {"rows": {"SETCO": {"moves": [["2026-11-24", -3.84], ["2026-10-23", -9.62], ["2026-08-31", -1.45], ["2026-08-29", -1.28], ["2026-05-30", 2.0]]}}}
    m = R._moves_of("IN", "SETCO", store, ("2026-11-24",))
    assert m["dates"] == ["2026-10-23", "2026-08-31", "2026-05-30"] and m["n"] == 3 and m["last"] == [-9.62, -1.45, 2.0]


def test_a_split_in_the_daily_prices_is_no_results_day_move():
    """Live: Vicarious Surgical's usual move read "±900.0%", a 1-for-10 reverse split in its daily prices across a results day."""
    assert R.reaction(_bars({"2026-08-10": 0.1, "2026-08-11": 0.1, "2026-08-12": 1.0}), date(2026, 8, 11)) is None
    assert R.reaction(_bars({"2026-08-10": 100, "2026-08-11": 100, "2026-08-12": 50}), date(2026, 8, 11)) is None     # a 2-for-1 split
    assert R.reaction(_bars({"2026-08-10": 100, "2026-08-11": 100, "2026-08-12": 160}), date(2026, 8, 11)) == 60.0    # a big move stays
    store = {"rows": {"RBOT": {"moves": [["2026-08-11", 900.0], ["2026-05-12", 4.0], ["2026-02-10", -6.0]]}}}
    assert R._moves_of("US", "RBOT", store) == {**R._moves_of("US", "RBOT", store), "avg": 5.0, "n": 2, "dates": ["2026-05-12", "2026-02-10"]}


# ---------- 4. the corporate actions and earnings calls lists come a page at a time ----------
def _div(i: int, ex: date):
    from app import corp_actions as C
    return C.row("IN", f"CO{i:03d}", {"kind": "dividend", "label": "Dividend", "text": "Dividend ₹1 a share", "amount": 1.0}, ex)


def test_the_corporate_actions_list_is_paged_on_the_server(w):
    """Live: the corporate actions page loaded every row of both lists in one answer (and the earnings calls page 400 at once); the page
    now reads a page of each list and the next as the reader scrolls."""
    from datetime import timedelta
    from app import corp_actions as C
    from tests.fake_db import headers
    today = C.local_today("IN")
    ahead = [_div(i, today + timedelta(days=1 + i % 9)) for i in range(130)]
    gone = [_div(500 + i, today - timedelta(days=1 + i % 5)) for i in range(70)]
    C.save("IN", ahead + gone)
    c, h = w["client"], headers("pro-token")
    first = c.get("/research/corp-actions?region=IN&scope=all", headers=h).json()
    assert len(first["ahead"]) == C.PAGE and len(first["recent"]) == C.PAGE
    assert first["ahead_total"] >= 130 and first["recent_total"] >= 70
    assert len(first["days"]) >= 14                                     # every ex-date for the day filter, not only those of the first page
    seen = [r["id"] for r in first["ahead"]]
    while len(seen) < first["ahead_total"]:
        nxt = c.get(f"/research/corp-actions?region=IN&scope=all&part=ahead&offset={len(seen)}", headers=h).json()
        assert nxt["recent"] == [] and nxt["ahead"], "each next page brings rows until the list is whole"
        seen += [r["id"] for r in nxt["ahead"]]
    assert len(seen) == len(set(seen)) == first["ahead_total"]          # every row once, in the list's own order
    whole = C.view("IN", "u-pro", "all", limit=10_000)
    assert seen == [r["id"] for r in whole["ahead"]]
    more = c.get(f"/research/corp-actions?region=IN&scope=all&part=recent&offset={C.PAGE}", headers=h).json()
    assert more["ahead"] == [] and len(more["recent"]) == first["recent_total"] - C.PAGE


def test_the_earnings_calls_list_is_paged_on_the_server(w):
    from datetime import timedelta
    from app import concalls
    from tests.fake_db import headers
    today = R.local_today("US")
    R.save("US", [R.row("US", f"C{i:03d}", today + timedelta(days=i % 10), "Quarterly results", src="market calendar") for i in range(130)])
    c, h = w["client"], headers("pro-token")
    first = c.get("/research/earnings-calls?region=US", headers=h).json()
    assert len(first["rows"]) == concalls.PAGE and first["matching"] == 130 and first["more"] == 130 - concalls.PAGE
    second = c.get(f"/research/earnings-calls?region=US&offset={concalls.PAGE}", headers=h).json()
    assert len(second["rows"]) == concalls.PAGE and second["offset"] == concalls.PAGE
    assert not {r["id"] for r in first["rows"]} & {r["id"] for r in second["rows"]}
