"""Corporate actions: reading the exchange's purpose text (fakes for the exchange's list, BSE's list, company notices
and the US price history), the bonus and split adjustment maths, dividend income for holdings, the rolling stored
calendar, the announcement and ex-date messages with their run markers, the My Stocks section and the API."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import corp_actions as C, db, holdings
from app.intel.net import SourceError
from app.newsletter import content, write
from tests import world as W
from tests.fake_db import headers

TODAY = date(2026, 10, 5)              # a Monday
IN_EVENING = datetime(2026, 10, 5, 12, 15, tzinfo=timezone.utc)     # 17:45 IST


# ---------- fakes for the feeds ----------
class FakeIndia:
    """The exchange: a market-wide corporate-actions list, each company's history, notices, and BSE-only companies."""

    def __init__(self, actions=None, history=None, bse=None, notices=None, down=False):
        self.actions, self.hist, self.bse, self.notices, self.down = actions or [], history or {}, bse or {}, notices or {}, down
        self.asked: list[str] = []

    def corporate_actions(self, frm=None, to=None, symbol=None):
        if self.down:
            raise SourceError("the exchange", "busy", busy=True)
        return self.actions

    def actions_of(self, symbol):
        self.asked.append(symbol)
        if symbol in self.bse:
            return "bse", self.bse[symbol]
        if self.down:
            raise SourceError("the exchange", "busy", busy=True)
        return "nse", self.hist.get(symbol, [])

    def announcements(self, symbol, days=365):
        return self.notices.get(symbol, [])

    def code_of(self, symbol):
        return "543210" if symbol in self.bse else None


class FakeUS:
    def __init__(self, events=None):
        self.ev = events or {}

    def events(self, symbol, days=1100):
        if symbol not in self.ev:
            raise SourceError("prices", "no history")
        return self.ev[symbol]


def nse(sym, subject, ex, rec=None, fv="1"):
    f = lambda d: d.strftime("%d-%b-%Y") if d else "-"
    return {"symbol": sym, "comp": f"{sym} Limited", "subject": subject, "exDate": f(ex), "recDate": f(rec or ex), "faceVal": fv}


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    content._cache.clear()
    write._cache.clear()
    yield world
    world["close"]()


def watch(uid, *items):
    db.set_setting(f"watchlist:{uid}", json.dumps({"items": [{"region": r, "symbol": s} for r, s in items]}))


# ---------- reading what the exchange wrote ----------
@pytest.mark.parametrize("text,want", [
    ("Interim Dividend - Rs 9 Per Share", [("dividend", "Interim dividend", 9.0, None, None)]),
    ("Final Dividend - Rs - 11.0000", [("dividend", "Final dividend", 11.0, None, None)]),
    ("Interim Dividend - Rs. - 5.5000", [("dividend", "Interim dividend", 5.5, None, None)]),
    ("Dividend - Re 0.50 Per Share", [("dividend", "Dividend", 0.5, None, None)]),
    ("Annual General Meeting/Dividend - Rs 8 Per Share", [("dividend", "Dividend", 8.0, None, None)]),
    ("Dividend - Rs 2.50 Per Share And Special Dividend Rs 1 Per Share",
     [("dividend", "Dividend", 2.5, None, None), ("dividend", "Special dividend", 1.0, None, None)]),
    ("Distribution - Rs 2.5 Per Unit", [("dividend", "Distribution", 2.5, None, None)]),
    ("Bonus 1:1", [("bonus", "Bonus 1:1", None, [1, 1], 2.0)]),
    ("Bonus 3:2", [("bonus", "Bonus 3:2", None, [3, 2], 2.5)]),
    ("Bonus issue 1:2 And Dividend - Rs 5 Per Share", [("bonus", "Bonus 1:2", None, [1, 2], 1.5), ("dividend", "Dividend", 5.0, None, None)]),
    ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share", [("split", "Split", None, None, 10.0)]),
    ("Stock  Split From Rs.10/- to Rs.2/-", [("split", "Split", None, None, 5.0)]),
    ("Consolidation of shares from Rs 1 to Rs 10", [("split", "Consolidation", None, None, 0.1)]),
    ("Rights 1:5 @ Premium Rs 100/-", [("rights", "Rights 1:5", None, [1, 5], None)]),
    ("Buy Back", [("buyback", "Buyback", None, None, None)]),
    ("Demerger", [("demerger", "Demerger", None, None, None)]),
    ("Annual General Meeting", []), ("Interest Payment", []), ("Redemption of NCDs", []), ("", []), (None, []),
])
def test_purpose_text_is_read_into_actions(text, want):
    got = [(a["kind"], a["label"], a["amount"], a["ratio"], a["factor"]) for a in C.parse_purpose(text)]
    assert got == want


def test_percent_dividends_use_the_face_value_and_the_wording_is_plain():
    a = C.parse_purpose("Dividend - 50%", face_value=10)[0]
    assert a["amount"] == 5.0 and a["text"] == "Dividend ₹5 a share"
    assert C.parse_purpose("Rights 1:5 @ Premium Rs 100/-")[0]["text"] == "Rights issue 1:5 (1 new share offered for every 5 held), at a premium of ₹100"
    assert C.parse_purpose("Bonus 1:1")[0]["text"] == "Bonus 1:1 (1 new share for every 1 held)"
    assert C.money(5.5) == "₹5.50" and C.money(11.0) == "₹11" and C.money(0.2625, "$") == "$0.2625"


def test_exchange_rows_skip_meetings_and_junk_and_keep_dates():
    rows = C.india_rows([nse("TCS", "Bonus 1:1", TODAY), nse("HDFCBANK", "Annual General Meeting", TODAY),
                         {"symbol": "X", "subject": "Bonus 1:1", "exDate": "-"}, {"symbol": "../x", "subject": "Bonus 1:1", "exDate": "05-Oct-2026"},
                         "junk", None, nse("ABC", "Dividend - Rs 2 Per Share", None, TODAY + timedelta(days=1))])
    assert [(r["symbol"], r["kind"], r["ex_date"]) for r in rows] == [("TCS", "bonus", "2026-10-05"), ("ABC", "dividend", "2026-10-06")]
    assert rows[1]["record_date"] == "2026-10-06" and rows[0]["name"] == "TCS Limited"
    again = C.india_rows([nse("TCS", "Bonus 1:1", TODAY)])
    assert again[0]["id"] == rows[0]["id"]                          # the same action read twice is the same row


def test_bse_and_us_rows():
    b = C.bse_rows([{"Purpose": "Interim Dividend - Rs. - 0.5000", "Ex_date": "12 Oct 2026", "RD_Date": "12 Oct 2026", "long_name": "Tiny Co Ltd"},
                    {"Purpose": "Bonus issue 1:1", "Ex_date": ""}, 5], "TINYCO")
    assert [(r["symbol"], r["amount"], r["ex_date"]) for r in b] == [("TINYCO", 0.5, "2026-10-12")]
    u = C.us_rows("AAPL", {"dividends": [{"date": "2026-08-11", "amount": 0.26}, {"date": "bad", "amount": 1}, {"date": "2026-05-11", "amount": -1}],
                           "splits": [{"date": "2020-08-31", "numerator": 4, "denominator": 1}, {"date": "2021-01-01", "numerator": 1, "denominator": 10},
                                      {"date": "2022-01-01", "numerator": 0, "denominator": 1}]})
    assert [(r["kind"], r["text"], r.get("factor")) for r in u] == [("dividend", "Dividend $0.26 a share", None), ("split", "Split 4-for-1", 4.0),
                                                                      ("split", "Reverse split 1-for-10", 0.1)]
    assert all(r["currency"] == "USD" and r["record_date"] is None for r in u)


def test_notices_are_read_when_the_list_is_down():
    items = [{"subject": "Record Date", "text": "The Board recommended an interim dividend of Rs 7 per share. Record date: 16-10-2026.",
              "at": "2026-10-01T18:00", "url": "https://nsearchives.nseindia.com/r.pdf"},
             {"subject": "Record Date", "text": "Interim dividend of Rs 3 per share. Record date: 16-10-2026.", "at": "2026-06-01T18:00"},   # an old notice
             {"subject": "Outcome", "text": "Dividend of Rs 9 per share approved", "at": "2026-10-01T18:00"}]      # no record date
    rows = C.from_announcements("ABC", items, TODAY)
    assert [(r["amount"], r["ex_date"], r["record_date"], r["src"]) for r in rows] == [(7.0, "2026-10-16", "2026-10-16", "announcement")]


# ---------- the adjustment maths ----------
BONUS = {"id": "TCS|bonus|2026-10-05|1:1", "kind": "bonus", "ratio": [1, 1], "factor": 2.0, "ex_date": "2026-10-05", "short": "1:1 bonus", "label": "Bonus 1:1", "text": "Bonus 1:1"}


@pytest.mark.parametrize("qty,avg,a,want", [
    (12, 3520.0, BONUS, (24, 1760.0)),
    (15, 300.0, {"kind": "bonus", "ratio": [1, 2], "factor": 1.5}, (22, 200.0)),       # 7.5 new shares: 7 allotted, the half paid in cash
    (7, 99.0, {"kind": "bonus", "ratio": [3, 2], "factor": 2.5}, (17, 39.6)),
    (10, 1500.0, {"kind": "split", "factor": 5.0}, (50, 300.0)),
    (10, 1500.0, {"kind": "split", "factor": 2.5}, (25, 600.0)),
    (25, 10.0, {"kind": "split", "factor": 0.1}, (2, 100.0)),                           # a consolidation: 2.5 becomes 2
    (12.5, 100.0, {"kind": "split", "factor": 2.0}, (25.0, 50.0)),                       # a fractional holding scales exactly
    (12, None, BONUS, (24, None)),                                                       # no average price: none after
])
def test_bonus_and_split_adjustments(qty, avg, a, want):
    assert C.adjusted(qty, avg, a) == want


def test_cost_is_kept_by_a_whole_number_split():
    q, avg = C.adjusted(40, 2410.35, {"kind": "split", "factor": 10.0})
    assert q * avg == pytest.approx(40 * 2410.35)


def test_apply_dismiss_and_undo():
    item = {"symbol": "TCS", "qty": 12, "avg": 3520.0, "since": "2026-10-01"}
    assert [a["id"] for a in C.pending(item, [BONUS], "2026-10-01", TODAY)] == [BONUS["id"]]
    assert C.pending(item, [BONUS], "2026-10-06", TODAY) == []                       # saved after the ex-date: already in the file
    assert C.pending(item, [BONUS], "2026-10-01", TODAY - timedelta(days=1)) == []  # not ex yet
    done = C.apply(item, BONUS)
    assert (done["qty"], done["avg"], done["applied"]) == (24, 1760.0, [BONUS["id"]])
    assert C.pending(done, [BONUS], "2026-10-01", TODAY) == []
    back = C.undo(done)
    assert (back["qty"], back["avg"], back["applied"], back["adjusted"]) == (12, 3520.0, [], [])
    assert C.undo(back) == back
    gone = C.dismiss(item, BONUS)
    assert gone["qty"] == 12 and C.pending(gone, [BONUS], "2026-10-01", TODAY) == []


def _div(sym, ex, amount, label="Dividend"):
    return {"id": f"{sym}|dividend|{ex}|{label}", "kind": "dividend", "label": label, "amount": amount, "ex_date": ex, "record_date": ex}


def test_dividend_income_counts_the_shares_held_on_each_ex_date():
    t = TODAY.isoformat
    acts = {"TCS": [_div("TCS", "2026-06-27", 30.0), _div("TCS", "2025-03-01", 66.0), BONUS, _div("TCS", "2026-10-08", 11.0, "Interim dividend")],
            "RELIANCE": [_div("RELIANCE", "2026-10-10", 5.5)]}
    items = [{"symbol": "TCS", "qty": 12, "avg": 3520.0, "since": "2026-10-01"}, {"symbol": "RELIANCE", "qty": 50, "avg": 2400.0}]
    v = C.holdings_view(items, acts, TODAY, "2026-09-01T10:00:00+00:00")
    assert [(x["symbol"], x["qty"], x["total"]) for x in v["ahead"]] == [("TCS", 24, 264.0), ("RELIANCE", 50, 275.0)]   # after the bonus: 24 shares
    assert [(x["symbol"], x["qty"], x["total"]) for x in v["received"]] == [("TCS", 12, 360.0)]       # the 2025 one is over a year ago
    assert (v["ahead_total"], v["received_total"]) == (539.0, 360.0)
    n = v["notices"][0]
    assert (n["symbol"], n["to_qty"], n["to_avg"]) == ("TCS", 24, 1760.0)
    assert n["text"] == "TCS had a 1:1 bonus on Mon 5 Oct: your quantity is now 24, average price ₹1,760."
    applied = [C.apply(items[0], BONUS), items[1]]
    v2 = C.holdings_view(applied, acts, TODAY, None)
    assert v2["notices"] == [] and v2["undo"][0]["symbol"] == "TCS"
    assert [(x["qty"], x["total"]) for x in v2["ahead"] if x["symbol"] == "TCS"] == [(24, 264.0)]
    assert v2["received"][0]["qty"] == 12                             # worked back to before the bonus
    assert t() == "2026-10-05"


def test_dividends_are_also_summed_by_financial_year_like_the_tax_tools():
    acts = {"TCS": [_div("TCS", "2026-06-27", 30.0), _div("TCS", "2026-02-01", 20.0), _div("TCS", "2025-03-01", 66.0)]}
    items = [{"symbol": "TCS", "qty": 10, "avg": 3520.0, "since": "2024-01-01"}]
    v = C.holdings_view(items, acts, TODAY, None)
    assert v["by_fy"] == [{"fy": 2026, "label": "FY 2026-27", "total": 300.0, "count": 1},
                          {"fy": 2025, "label": "FY 2025-26", "total": 200.0, "count": 1}]      # the March 2025 one is FY 2024-25: not listed
    assert v["received_total"] == 500.0                                                          # the rolling twelve months holds both


def test_a_consolidation_to_nothing_is_not_offered():
    item = {"symbol": "X", "qty": 3, "avg": 10.0, "since": "2026-09-01"}
    a = {"id": "X|split|2026-10-01|1-10", "kind": "split", "factor": 0.1, "ex_date": "2026-10-01", "short": "consolidation", "label": "Consolidation", "text": "c"}
    assert C.holdings_view([item], {"X": [a]}, TODAY, None)["notices"] == []


def test_holdings_remember_when_each_quantity_was_saved():
    before = [{"symbol": "TCS", "qty": 12, "since": "2026-09-01", "applied": ["x"]}, {"symbol": "INFY", "qty": 5, "since": "2026-09-01"}]
    got = {i["symbol"]: i for i in holdings.stamp([{"symbol": "TCS", "qty": 12}, {"symbol": "INFY", "qty": 6}, {"symbol": "ITC", "qty": 1}], before, "2026-10-05")}
    assert got["TCS"]["since"] == "2026-09-01" and got["TCS"]["applied"] == ["x"]
    assert got["INFY"]["since"] == "2026-10-05" and got["ITC"]["since"] == "2026-10-05"


# ---------- the stored, rolling calendar ----------
def test_merge_keeps_the_past_drops_withdrawn_and_marks_new_actions():
    a = C.india_rows([nse("AAA", "Dividend - Rs 2 Per Share", TODAY + timedelta(days=3))])[0]
    old_past = C.india_rows([nse("BBB", "Bonus 1:1", TODAY - timedelta(days=10))])[0]
    gone = C.india_rows([nse("CCC", "Buy Back", TODAY + timedelta(days=5))])[0]
    ancient = C.india_rows([nse("DDD", "Bonus 1:1", TODAY - timedelta(days=60))])[0]
    new = C.india_rows([nse("EEE", "Bonus 2:1", TODAY + timedelta(days=9)), nse("FFF", "Dividend - Rs 1 Per Share", TODAY - timedelta(days=2))])
    got = {r["symbol"]: r for r in C.merge([a, old_past, gone, ancient], [a] + new, TODAY - timedelta(days=7), TODAY)}
    assert set(got) == {"AAA", "BBB", "EEE", "FFF"}
    assert got["EEE"].get("fresh") and not got["AAA"].get("fresh") and not got["FFF"].get("fresh")    # FFF went ex already
    assert not any(r.get("fresh") for r in C.merge([], new, TODAY - timedelta(days=7), TODAY, first=True))


def test_refresh_reads_the_list_bse_only_companies_and_us_histories(w):
    india = FakeIndia([nse("TCS", "Bonus 1:1", TODAY), nse("RELIANCE", "Dividend - Rs 5.50 Per Share", TODAY + timedelta(days=5))],
                      bse={"TINYCO": [{"Purpose": "Interim Dividend - Rs. - 0.5000", "Ex_date": (TODAY + timedelta(days=7)).strftime("%d %b %Y")}]})
    out = C.refresh("IN", {"in": india}, {"TCS", "TINYCO"}, TODAY)
    assert out["rows"] == 3 and india.asked == ["TINYCO"]
    assert {r["symbol"] for r in C.load("IN")["rows"]} == {"TCS", "RELIANCE", "TINYCO"}
    us = FakeUS({"AAPL": {"dividends": [{"date": (TODAY - timedelta(days=3)).isoformat(), "amount": 0.26}], "splits": []}})
    out = C.refresh("US", {"us": us}, {"AAPL", "NOPE"}, TODAY)
    assert out["rows"] == 1 and out["problems"]
    assert C.hist_load("US", "AAPL")["rows"][0]["amount"] == 0.26


def test_when_the_list_is_down_notices_are_read_and_the_calendar_survives(w):
    C.refresh("IN", {"in": FakeIndia([nse("TCS", "Bonus 1:1", TODAY + timedelta(days=2))])}, set(), TODAY)
    notice = {"subject": "Record date", "text": "Final dividend of Rs 4 per share. Record date 20-10-2026", "at": "2026-10-02T10:00"}
    out = C.refresh("IN", {"in": FakeIndia(down=True, notices={"INFY": [notice]})}, {"INFY"}, TODAY)
    assert out["problems"] and {r["symbol"] for r in C.load("IN")["rows"]} == {"TCS", "INFY"}
    before = C.load("IN")
    assert C.refresh("IN", {"in": FakeIndia(down=True)}, set(), TODAY)["rows"] is None
    assert C.load("IN") == before


def test_history_is_stored_and_kept_when_the_feed_fails(w):
    india = FakeIndia(history={"TCS": [nse("TCS", "Final Dividend - Rs - 30.0000", TODAY - timedelta(days=100)),
                                       nse("TCS", "Special Dividend - Rs 66 Per Share", TODAY - timedelta(days=2000))]})
    rows = C.history("IN", "TCS", {"in": india}, TODAY)
    assert [r["amount"] for r in rows] == [30.0]                       # older than three years: left out
    assert C.history("IN", "TCS", {"in": FakeIndia(down=True)}, TODAY) == rows          # fresh: not asked again
    db.set_setting(C.HIST + "IN:TCS", json.dumps({"at": "2020-01-01T00:00+00:00", "rows": rows}))
    assert C.history("IN", "TCS", {"in": FakeIndia(down=True)}, TODAY) == rows          # stale, but the feed is down
    c = C.company("IN", "TCS", None, TODAY, fetch=False)
    assert c["past"][0]["amount"] == 30.0 and c["dividends_12m"] == {"amount": 30.0, "count": 1, "currency": "₹"}


# ---------- the messages ----------
def job_with(india=None, us=None):
    sent = []
    job = C.Job(lambda: {"in": india or FakeIndia(), "us": us or FakeUS()},
                send=lambda p, subject, text, url: sent.append((p["id"], subject, text, url)), can_alert=lambda p: C.alerts_on(p["id"]))
    return job, sent


def test_new_actions_are_announced_once_to_the_people_tracking_them(w):
    watch("u-pro", ("IN", "TCS"))
    watch("u-free", ("IN", "INFY"))
    C.refresh("IN", {"in": FakeIndia([nse("INFY", "Dividend - Rs 2 Per Share", TODAY + timedelta(days=9))])}, set(), TODAY)   # the first build
    india = FakeIndia([nse("INFY", "Dividend - Rs 2 Per Share", TODAY + timedelta(days=9)), nse("TCS", "Bonus 1:1", TODAY + timedelta(days=9))])
    job, sent = job_with(india)
    job.tick(datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc))          # 07:30 IST: the morning refresh
    assert [(uid, subject) for uid, subject, _, _ in sent] == [("u-pro", "StratLab: corporate action announced")]
    assert "TCS: Bonus 1:1" in sent[0][2] and not write.banned(sent[0][2]) and "INFY" not in sent[0][2]
    job.tick(datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc))        # the evening refresh: nothing new
    assert len([s for s in sent if "announced" in s[1]]) == 1


def test_the_evening_before_an_ex_date_and_friday_for_monday(w):
    watch("u-pro", ("IN", "TCS"), ("IN", "RELIANCE"))
    C.refresh("IN", {"in": FakeIndia([nse("TCS", "Interim Dividend - Rs 11 Per Share", TODAY + timedelta(days=1)),
                                      nse("RELIANCE", "Dividend - Rs 5.50 Per Share", TODAY + timedelta(days=7))])}, set(), TODAY)
    job, sent = job_with()
    job.tick(IN_EVENING)
    assert [(uid, subject) for uid, subject, _, _ in sent] == [("u-pro", "StratLab: ex-date tomorrow")]
    assert "TCS: Interim dividend ₹11 a share, ex-date tomorrow" in sent[0][2] and "RELIANCE" not in sent[0][2]
    again, sent2 = job_with()                                          # a restart: the run marker is in the database
    again.tick(IN_EVENING + timedelta(minutes=10))
    assert sent2 == []
    friday = TODAY + timedelta(days=4)
    job.tick(datetime.combine(friday, datetime.min.time(), timezone.utc) + timedelta(hours=12, minutes=15))
    assert sent[-1][1] == "StratLab: ex-dates coming up" and "RELIANCE" in sent[-1][2]


def test_people_who_turned_the_messages_off_dont_get_them(w):
    watch("u-pro", ("IN", "TCS"))
    C.set_alerts("u-pro", False)
    C.refresh("IN", {"in": FakeIndia([nse("TCS", "Bonus 1:1", TODAY + timedelta(days=1))])}, set(), TODAY)
    job, sent = job_with()
    job.tick(IN_EVENING)
    assert sent == []


def test_my_stocks_newsletter_has_a_corporate_actions_section(w):
    watch("u-pro", ("IN", "TCS"))
    C.refresh("IN", {"in": FakeIndia([nse("TCS", "Interim Dividend - Rs 11 Per Share", TODAY + timedelta(days=2)),
                                      nse("INFY", "Bonus 1:1", TODAY + timedelta(days=2))])}, set(), TODAY)
    acts = content.actions_week("u-pro", TODAY, False)
    assert [(r["symbol"], r["ex_date"]) for r in acts] == [("TCS", "2026-10-07")]
    f = {"kind": "my_stocks", "weekly": False, "day": TODAY.isoformat(), "since": TODAY.isoformat(), "stocks": [], "results": [], "actions": acts}
    sec = next(s for s in write.sections(f) if s["title"] == "Corporate actions")
    assert "TCS: Interim dividend ₹11 a share, ex-date Wed 7 Oct" in json.dumps(sec, ensure_ascii=False)
    assert "ex-date" in write.template(f) and "ex-dates this week for 1" in write.subject(f)


# ---------- the API ----------
def test_calendar_company_and_holdings_api(w):
    c, h = w["client"], headers("pro-token")
    got = c.get("/research/corp-actions?region=IN&scope=all", headers=h).json()
    syms = {r["symbol"] for r in got["ahead"]}
    assert {"TCS", "RELIANCE", "INFY"} <= syms and "HDFCBANK" not in syms
    assert any(r["symbol"] == "ITC" and r["kind"] == "buyback" for r in got["recent"])
    assert c.get("/research/corp-actions?region=IN&scope=all&kind=bonus", headers=h).json()["ahead"][0]["kind"] == "bonus"
    assert c.get("/research/corp-actions?region=IN&scope=mine", headers=h).json()["ahead"] == []
    one = c.get("/research/corp-actions/IN/TCS", headers=h).json()
    assert [r["kind"] for r in one["ahead"]][:2] == ["bonus", "dividend"] and one["dividends_12m"]["amount"] == 40.0
    us = c.get("/research/corp-actions/US/AAPL", headers=h).json()
    assert us["past"][0]["text"] == "Dividend $0.26 a share" and us["ahead_known"] is False
    for body in (got, one, us):
        assert not any(n in json.dumps(body).lower() for n in ("yahoo", "finnhub", "kite", "zerodha", "screener"))
    assert c.put("/research/corp-actions/alerts", headers=h, json={"on": False}).json() == {"alerts": False}
    assert c.get("/research/corp-actions?region=IN", headers=h).json()["alerts"] is False

    assert c.put("/holdings", headers=h, json={"items": [{"symbol": "TCS", "qty": 12, "avg": 3520}, {"symbol": "RELIANCE", "qty": 50, "avg": 2400}]}).status_code == 200
    v = c.get("/holdings/corp-actions", headers=h).json()
    tcs = next(n for n in v["notices"] if n["symbol"] == "TCS")
    assert (tcs["to_qty"], tcs["to_avg"]) == (24, 1760.0) and "1:1 bonus" in tcs["text"]
    assert any(x["symbol"] == "TCS" and x["qty"] == 24 and x["total"] == 264.0 for x in v["ahead"])
    assert c.post("/holdings/corp-actions", headers=h, json={"symbol": "TCS", "id": "TCS|bonus|nope", "action": "apply"}).status_code == 409
    assert c.post("/holdings/corp-actions", headers=h, json={"symbol": "NOPE", "id": tcs["id"]}).status_code == 404
    r = c.post("/holdings/corp-actions", headers=h, json={"symbol": "TCS", "id": tcs["id"], "action": "apply"}).json()
    row = next(x for x in r["holdings"]["rows"] if x["symbol"] == "TCS")
    assert (row["qty"], row["avg"]) == (24, 1760.0) and not any(n["symbol"] == "TCS" for n in r["actions"]["notices"])
    assert c.put("/holdings", headers=h, json={"items": [{"symbol": "TCS", "qty": 24, "avg": 1760}, {"symbol": "RELIANCE", "qty": 50, "avg": 2400}]}).status_code == 200
    assert not any(n["symbol"] == "TCS" for n in c.get("/holdings/corp-actions", headers=h).json()["notices"])   # a re-save keeps it applied
    r = c.post("/holdings/corp-actions", headers=h, json={"symbol": "TCS", "action": "undo"}).json()
    assert next(x for x in r["holdings"]["rows"] if x["symbol"] == "TCS")["qty"] == 12
    assert any(n["symbol"] == "TCS" for n in r["actions"]["notices"])
    assert c.post("/holdings/corp-actions", headers=h, json={"symbol": "TCS", "action": "undo"}).status_code == 409
    r = c.post("/holdings/corp-actions", headers=h, json={"symbol": "TCS", "id": tcs["id"], "action": "dismiss"}).json()
    assert next(x for x in r["holdings"]["rows"] if x["symbol"] == "TCS")["qty"] == 12 and not r["actions"]["notices"]


def test_routes_need_sign_in_and_reject_bad_input(w):
    c = w["client"]
    assert c.get("/research/corp-actions").status_code == 401
    assert c.get("/research/corp-actions?region=XX", headers=headers("pro-token")).status_code == 400
    assert c.get("/research/corp-actions/IN/..%2F..", headers=headers("pro-token")).status_code in (400, 404)
    assert c.post("/admin/corp-actions/refresh", headers=headers("pro-token")).status_code == 403
    assert c.post("/admin/corp-actions/refresh", headers=headers("admin-token")).json()["IN"]["rows"] >= 3


def test_made_up_tickers_on_the_company_route_store_nothing(w):
    """Security: anyone signed in can name any ticker. A company with no actions found is remembered in memory only,
    so looping through made-up tickers can't fill the database; a real one's history is stored as before."""
    c, h = w["client"], headers("pro-token")
    for i in range(5):
        assert c.get(f"/research/corp-actions/IN/ZZFAKE{i}", headers=h).json()["past"] == []
    assert not [k for k, _ in db.all_settings_with_prefix(C.HIST) if "ZZFAKE" in k]
    assert c.get("/research/corp-actions/IN/TCS", headers=h).status_code == 200
    assert C.hist_load("IN", "TCS")["at"]
    feed = FakeIndia()
    assert C.company("IN", "NEWCO", {"in": feed}, TODAY)["past"] == [] and feed.asked == ["NEWCO"]
    C.company("IN", "NEWCO", {"in": feed}, TODAY)
    assert feed.asked == ["NEWCO"]                     # remembered for a while: not asked again
    assert C.history("IN", "HELD", {"in": feed}, TODAY) == [] and C.hist_load("IN", "HELD")["at"]   # holdings still store
