"""ETF prices against their NAV: the arithmetic and the words, reading the exchange's ETF list loosely, matching NAVs by
ISIN, the stored 30-day history, the job, the pages' answers and the alert. Every number is synthetic (fake_etf.py)."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: I001  (first: the app loads the newsletter job before the modules built on it)
from app import db, etf_nav as E, stock_alerts as sa
from tests import fake_etf as FE
from tests import world as W
from tests.fake_db import headers

DAY = date(2026, 10, 3)
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|amfi|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|cheap|expensive|overpriced|underpriced|overvalued|undervalued|wait)\b", re.I)


class Feed:
    def __init__(self, data=None, fail=False):
        self.data, self.fail, self.calls = data if data is not None else FE.answer(), fail, 0

    def etf_list(self):
        self.calls += 1
        if self.fail:
            raise ValueError("down")
        return self.data


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    monkeypatch.setattr(E, "navs", lambda: FE.navs(DAY))
    yield world
    world["close"]()
    E.forget()


# ---------- the arithmetic and the words ----------
def test_gap_maths():
    assert E.gap(105.20, 99.15) == 6.1
    assert E.gap(81.20, 82.0) == -0.98
    assert E.gap("1,000.00", "1000") == 0.0
    assert E.gap(100, None) is None and E.gap(None, 100) is None and E.gap(0, 100) is None and E.gap(-5, 100) is None
    assert E.gap(100, 40) is None                    # 150% away: a NAV for another unit, not a real gap
    assert E.gap(True, 100) is None and E.gap("-", 100) is None and E.gap(float("nan"), 100) is None


def test_words_are_neutral():
    assert E.words(4.2) == "trades 4.2% above its NAV"
    assert E.words(-0.35, "iNAV") == "trades 0.35% below its iNAV"
    assert E.words(0.0) == "trades at its NAV" and E.words(0.004) == "trades at its NAV"
    assert E.words(-12.345) == "trades 12.3% below its NAV"
    assert E.words(None) == ""
    for g in (-30, -1, -0.1, 0, 0.1, 1, 30):
        assert not ADVICE.search(E.words(g))


# ---------- the exchange's list ----------
def test_parse_exchange_list():
    got = E.parse_exchange(FE.answer())
    assert got["as_of"] == "2026-10-03T15:30+05:30"
    rows = got["rows"]
    assert set(rows) == {"SILVERBEES", "GOLDBEES", "NIFTYBEES", "BANKBEES", "LIQUIDBEES"}       # ODDETF has no price
    assert rows["SILVERBEES"] == {"name": "Nippon India Silver ETF", "isin": "INF204KC1402", "price": 105.2, "inav": 99.15,
                                  "underlying": "Nippon India Silver ETF"}
    assert rows["LIQUIDBEES"]["price"] == 1000.0


def test_parse_survives_odd_shapes():
    for junk in (None, [], {}, {"data": None}, {"data": "x"}, {"data": [None, 3, "x", {}]}, "text"):
        assert E.parse_exchange(junk)["rows"] == {}
    rows = E.parse_exchange([{"symbol": "abc etf;drop", "ltP": "10"}, {"symbol": "OK", "lastPrice": 12.5, "iNavValue": "12.4",
                                                                     "isin": "not-an-isin", "timestamp": "x"}])["rows"]
    assert list(rows) == ["OK"] and rows["OK"]["inav"] == 12.4 and rows["OK"]["isin"] == ""
    assert E.parse_exchange({"timestamp": "nonsense", "data": []})["as_of"] is None


# ---------- the table, the detail and the history ----------
def test_table_widest_gap_first(w):
    E.refresh(Feed())
    t = E.table()
    syms = [r["symbol"] for r in t["rows"]]
    assert syms[0] == "SILVERBEES" and syms[-1] == "LIQUIDBEES" and t["count"] == 5
    by = {r["symbol"]: r for r in t["rows"]}
    s = by["SILVERBEES"]
    assert (s["inav_gap"], s["nav"], s["nav_date"], s["basis"], s["fund"], s["fund_label"]) == (6.1, 98.4, "2026-10-03", "iNAV", "silver", "Silver ETF")
    assert s["nav_gap"] == E.gap(105.2, 98.4) and s["text"] == "SILVERBEES trades 6.1% above its indicative NAV"
    assert by["BANKBEES"]["nav"] is None and by["BANKBEES"]["inav_gap"] == -1.3        # no NAV in the file: the iNAV gap only
    assert by["GOLDBEES"]["fund"] == "gold" and by["LIQUIDBEES"]["fund"] == "debt" and by["NIFTYBEES"]["fund"] == "equity"
    assert by["LIQUIDBEES"]["text"] == "LIQUIDBEES trades at its indicative NAV"
    assert t["nav_as_of"] == "2026-10-03" and t["as_of"] == "2026-10-03T15:30+05:30"


def test_nav_only_when_no_inav(w):
    data = FE.answer()
    for it in data["data"]:
        it["nav"] = "-"
    E.refresh(Feed(data))
    by = {r["symbol"]: r for r in E.table()["rows"]}
    assert by["GOLDBEES"]["basis"] == "NAV" and by["GOLDBEES"]["gap"] == -0.98
    assert by["GOLDBEES"]["text"] == "GOLDBEES trades 0.98% below its last NAV"
    assert by["BANKBEES"]["gap"] is None and by["BANKBEES"]["text"] is None
    assert [r["symbol"] for r in E.table()["rows"]][-1] == "BANKBEES"           # no gap at all: last


def test_nav_matched_by_isin_only(w, monkeypatch):
    E.refresh(Feed())
    other = FE.navs(DAY)
    other["isin"] = {}                       # the file has the names but not these ISINs: nothing is guessed by name
    monkeypatch.setattr(E, "navs", lambda: other)
    E.forget()
    assert all(r["nav"] is None for r in E.table()["rows"])


def test_record_fill_and_history(w):
    E.refresh(Feed())
    live = E.load_live()
    assert E.record_close(DAY, live, FE.navs(DAY - timedelta(days=1))) == 5          # tonight's NAVs aren't out yet
    assert E.history("SILVERBEES") == [{"day": "2026-10-03", "close": 105.2, "nav": None, "gap": None}]
    assert E.fill_navs(FE.navs(DAY), DAY) == 4                                       # out now (BANKBEES has none)
    h = E.history("SILVERBEES")[0]
    assert (h["nav"], h["gap"]) == (98.4, E.gap(105.2, 98.4))
    assert E.fill_navs(FE.navs(DAY), DAY) == 0                                       # nothing left to fill
    assert E.fill_navs(FE.navs(DAY), DAY + timedelta(days=30)) == 0                  # too far back to look


def test_history_keeps_thirty_days(w):
    FE.seed_history(DAY, 34)
    E.refresh(Feed())
    E.record_close(DAY, E.load_live(), FE.navs(DAY))
    days = [k for k, _ in db.all_settings_with_prefix(E.DAY_KEY)]
    assert len(days) == E.KEEP_DAYS and max(days).endswith(DAY.isoformat())
    h = E.history("SILVERBEES")
    assert len(h) == 30 and h[-1]["day"] == DAY.isoformat()
    s = E.summary(h)
    assert s["days"] == 30 and s["low"] < s["avg"] < s["high"] and s["to"] == DAY.isoformat()
    assert E.summary([{"day": "x", "gap": None}]) is None


def test_detail_and_unknown(w):
    FE.seed_history(DAY, 30)
    E.refresh(Feed())
    d = E.detail("silverbees")
    assert d["row"]["symbol"] == "SILVERBEES" and len(d["history"]) == 30 and d["days"]["days"] == 30
    assert E.detail("RELIANCE") is None
    assert E.known("NIFTYBEES") and not E.known("RELIANCE")


def test_known_without_a_list(w):
    assert E.known("ANYTHING")               # nothing stored yet: nothing can be said, so nothing is refused


# ---------- the job ----------
def test_job_reads_in_hours_and_records_after_close(w, monkeypatch):
    feed = Feed()
    job = E.Job(lambda: feed)
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    ist = timezone(timedelta(hours=5, minutes=30))
    friday = datetime(2026, 10, 2, 11, 0, tzinfo=ist)
    monkeypatch.setattr(E, "navs", lambda: FE.navs(date(2026, 10, 2)))
    job.tick(friday.astimezone(timezone.utc))
    assert feed.calls == 1 and E.load_live()["rows"]
    job.tick((friday + timedelta(minutes=1)).astimezone(timezone.utc))
    assert feed.calls == 1                                 # read every few minutes, not every check
    n = job.tick(datetime(2026, 10, 2, 15, 50, tzinfo=ist).astimezone(timezone.utc))
    assert n == 5 and job.status["recorded"] == "2026-10-02" and db.get_setting("newsjob:etfnav-close") == "2026-10-02"
    assert E.history("SILVERBEES")[-1]["nav"] == 98.4
    calls = feed.calls
    job.tick(datetime(2026, 10, 2, 16, 0, tzinfo=ist).astimezone(timezone.utc))
    assert feed.calls == calls                             # recorded once a day; closed now, so no more reads


def test_job_survives_the_exchange_being_down(w, monkeypatch):
    feed = Feed(fail=True)
    job = E.Job(lambda: feed)
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: True)
    ist = timezone(timedelta(hours=5, minutes=30))
    assert job.tick(datetime(2026, 10, 2, 15, 50, tzinfo=ist).astimezone(timezone.utc)) == 0
    assert job.status["last_error"] and db.get_setting("newsjob:etfnav-close") is None      # tried again later


# ---------- the pages ----------
def test_routes(w):
    c = w["client"]
    r = c.get("/invest/etf-gaps", headers=headers("free-token"))
    assert r.status_code == 200
    body = r.json()
    assert body["rows"][0]["symbol"] == "SILVERBEES" and body["count"] == 5 and "alerts" in body
    text = json.dumps(body)
    assert not PROVIDERS.search(text) and not ADVICE.search(text)
    r = c.get("/invest/etf-gaps/SILVERBEES", headers=headers("free-token"))
    assert r.status_code == 200 and r.json()["row"]["gap"] == 6.1
    for bad in ("RELIANCE", "x" * 40, "A;B"):
        assert c.get(f"/invest/etf-gaps/{bad}", headers=headers("free-token")).status_code == 404
    assert c.get("/invest/etf-gaps").status_code == 401


# ---------- the alert ----------
def test_alert_clean_and_describe():
    a = sa.clean({"region": "IN", "symbol": "SILVERBEES", "kind": "etfgap", "op": "above", "value": 2})
    assert (a["op"], a["value"]) == ("above", 2.0)
    assert sa.describe(a) == "Trades 2% or more above its NAV"
    assert sa.describe({**a, "op": "either", "value": 1.5}) == "Trades 1.5% or more away from its NAV, either way"
    for bad in ({"op": "up"}, {"value": 0}, {"value": 80}, {"value": None}, {"region": "US"}):
        with pytest.raises(sa.AlertError):
            sa.clean({"region": "IN", "symbol": "SILVERBEES", "kind": "etfgap", "op": "above", "value": 2, **bad})


def test_alert_fires_on_the_gap():
    a = {**sa.clean({"region": "IN", "symbol": "SILVERBEES", "kind": "etfgap", "op": "above", "value": 5}), "state": {}}
    snap = {"price": 105.2, "today": "2026-10-02", "tz": "Asia/Kolkata"}
    gap = {"gap": 6.1, "basis": "iNAV", "text": "SILVERBEES trades 6.1% above its indicative NAV (price ₹105.20, iNAV ₹99.15)"}
    assert sa.evaluate(a, {**snap, "gap": gap})[0] == gap["text"]
    assert sa.evaluate(a, {**snap, "gap": {**gap, "gap": 4.9}})[0] is None
    assert sa.evaluate(a, {**snap, "gap": None})[0] is None
    below = {**a, "op": "below"}
    assert sa.evaluate(below, {**snap, "gap": {**gap, "gap": -5.5}})[0] and not sa.evaluate(below, {**snap, "gap": gap})[0]
    either = {**a, "op": "either"}
    assert sa.evaluate(either, {**snap, "gap": {**gap, "gap": -5.5}})[0] and sa.evaluate(either, {**snap, "gap": gap})[0]
    assert not ADVICE.search(gap["text"])


def test_gap_now(w):
    E.refresh(Feed())
    g = E.gap_now("SILVERBEES", 105.2)
    assert g["basis"] == "iNAV" and g["gap"] == 6.1 and "₹99.15" in g["text"] and not ADVICE.search(g["text"])
    assert E.gap_now("RELIANCE", 100) is None and E.gap_now("SILVERBEES", None) is None
    data = FE.answer()
    for it in data["data"]:
        it["nav"] = "-"
    E.refresh(Feed(data))
    g = E.gap_now("GOLDBEES", 81.2)
    assert g["basis"] == "NAV" and g["gap"] == -0.98 and "on 2026-10-03" in g["text"]


def test_checker_sends_the_gap_alert(w, monkeypatch):
    E.refresh(Feed())
    sa.create("u-basic", {"region": "IN", "symbol": "SILVERBEES", "kind": "etfgap", "op": "above", "value": 5}, 10)
    sa.create("u-free", {"region": "IN", "symbol": "SILVERBEES", "kind": "etfgap", "op": "above", "value": 5}, 10)
    sent = []
    chk = sa.Checker(lambda r, s: {x: {"price": 105.2, "change_pct": 0.1} for x in s}, lambda r, s: [], lambda p: 10,
                     send=lambda p, subject, text: sent.append((p["id"], text)) or ["push"], profile=lambda uid: {"id": uid},
                     gaps=E.gap_now, kind_ok=lambda p, k: p["id"] != "u-free")
    ist = timezone(timedelta(hours=5, minutes=30))
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: True)
    chk.tick(datetime(2026, 10, 2, 11, 0, tzinfo=ist).astimezone(timezone.utc))
    assert [u for u, _ in sent] == ["u-basic"] and "6.1% above its indicative NAV" in sent[0][1]


def test_create_alert_route(w, monkeypatch):
    E.refresh(Feed())
    monkeypatch.setattr(main, "alert_quotes", lambda r, s: {x: {"price": 105.2} for x in s})
    c = w["client"]
    body = {"region": "IN", "symbol": "SILVERBEES", "kind": "etfgap", "op": "above", "value": 3}
    r = c.post("/alerts", json=body, headers=headers("basic-token"))
    assert r.status_code == 200 and r.json()["alert"]["text"] == "Trades 3% or more above its NAV"
    r = c.post("/alerts", json={**body, "symbol": "RELIANCE"}, headers=headers("basic-token"))
    assert r.status_code == 400 and "ETF list" in r.json()["detail"]["message"]


def test_alert_on_a_non_etf_saved_before_the_list_never_fires(w, monkeypatch):
    """With no list read yet nothing can be refused, but once the list is known an alert on a symbol not on it is
    refused when saved or edited, and one saved earlier never fires."""
    monkeypatch.setattr(main, "alert_quotes", lambda r, s: {x: {"price": 105.2} for x in s})
    monkeypatch.setattr(E, "_first_read", lambda: None)
    c = w["client"]
    body = {"region": "IN", "symbol": "RELIANCE", "kind": "etfgap", "op": "either", "value": 0.1}
    r = c.post("/alerts", json=body, headers=headers("basic-token"))
    assert r.status_code == 200                        # no list stored: allowed for now
    aid = r.json()["alert"]["id"]
    E.refresh(Feed())                                  # the list is read, and RELIANCE isn't on it
    assert c.post("/alerts", json=body, headers=headers("basic-token")).status_code == 400
    assert c.put(f"/alerts/{aid}", json=body, headers=headers("basic-token")).status_code == 400
    sent = []
    chk = sa.Checker(lambda r, s: {x: {"price": 1e6, "change_pct": 50} for x in s}, lambda r, s: [], lambda p: 10,
                     send=lambda p, subject, text: sent.append(text) or ["push"], profile=lambda uid: {"id": uid},
                     gaps=E.gap_now)
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: True)
    ist = timezone(timedelta(hours=5, minutes=30))
    chk.tick(datetime(2026, 10, 2, 11, 0, tzinfo=ist).astimezone(timezone.utc))
    assert sent == []
