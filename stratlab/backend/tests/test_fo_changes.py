"""F&O contract changes: reading the exchange's contract file and circulars (from synthetic samples in
fixtures/fo_changes), the changes one copy shows and the ones between two copies, the dated list kept across runs,
sources that fail or are busy, the page's answer and badges, the alert on Basic and up, and the twice-a-day job."""
import json
import random
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app import db, main  # noqa: F401  (main first: it loads the modules in the order they need)
from app import fo_changes as F, fo_changes_routes as R
from app.intel.net import SourceError
from app.config import settings
from tests import fake_fo_changes as X
from tests import world as W
from tests.fake_db import headers

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|risky|danger|beware|should)\b", re.I)
OLD, NEW = "fo_mktlots_2026-09-25.csv", "fo_mktlots_2026-10-03.csv"
DAY1, DAY2 = date(2026, 9, 25), date(2026, 10, 3)
RULE = lambda sym, month: F.rule_expiry(month)  # noqa: E731


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    F._cache.clear()


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


class NSE:
    """A stand-in exchange client: the contract file and the circulars the test sets, either of which can be down
    or busy for a number of calls."""

    def __init__(self, lots: str, circulars):
        self.lots, self.circulars = lots, circulars
        self.down: dict[str, int] = {}      # "lots" / "circulars" -> calls left that fail
        self.busy = True
        self.calls = {"lots": 0, "circulars": 0}

    def _fail(self, part):
        self.calls[part] += 1
        if self.down.get(part, 0) > 0:
            self.down[part] -= 1
            raise SourceError("the exchange", f"The exchange's {part} isn't answering.", busy=self.busy)

    def _surv_text(self, url):
        assert url == F.LOT_URL
        self._fail("lots")
        return self.lots

    def _get(self, path, params, referer=None, circuit="main"):
        assert path == "/api/circulars" and circuit == "fochanges" and {"fromDate", "toDate"} <= set(params)
        self._fail("circulars")
        return self.circulars


class Feed:
    def __init__(self, lots=None, circulars=None):
        self.nse = NSE(lots if lots is not None else X.sample(OLD), circulars if circulars is not None else X.sample("circulars.json"))


# ---------- reading ----------
def test_months_and_dates_as_the_exchange_writes_them():
    assert [F.month_of(c) for c in ("OCT-26", "Oct-2026", "NOV 26", "dec26", "SYMBOL", "", "XYZ-26")] == [
        "2026-10", "2026-10", "2026-11", "2026-12", None, None, None]
    assert F.series_name("2026-07") == "Jul 2026"
    assert [F.iso_day(s) for s in ("October 01, 2026", "01-Oct-2026", "2026-10-01", "01/10/2026", "2026-10-01 18:00:00", "soon")] == [
        "2026-10-01"] * 5 + [None]


def test_expiry_rule_last_tuesday_from_september_2025_and_thursday_before():
    jun25 = F.rule_expiry("2025-06")
    assert jun25 == date(2025, 6, 26) and jun25.weekday() == 3
    for month in ("2025-09", "2026-01", "2026-07", "2026-10"):
        d = F.rule_expiry(month)
        last_tue = max(date(int(month[:4]), int(month[5:]), n) for n in range(22, 32)
                       if _valid(month, n) and date(int(month[:4]), int(month[5:]), n).weekday() == 1)
        assert d <= last_tue and (last_tue - d).days < 6 and d.strftime("%Y-%m") == month
    assert F.rule_expiry("2026-07") == date(2026, 7, 28)        # Exide and Nuvama's last expiry


def _valid(month, n):
    try:
        date(int(month[:4]), int(month[5:]), n)
        return True
    except ValueError:
        return False


def test_contract_file_rows_months_and_indices():
    got = F.read_lots(X.sample(NEW))
    assert got["months"] == ["2026-10", "2026-11", "2026-12"]
    rows = got["rows"]
    assert rows["NIFTY"] == {"name": "NIFTY 50", "index": True, "lots": {"2026-10": 75, "2026-11": 75, "2026-12": 65}}
    assert rows["INFY"]["lots"]["2026-10"] == 1200 and rows["INFY"]["index"] is False      # "1,200" in quotes
    assert rows["EXIDEIND"]["lots"] == {"2026-10": 1800, "2026-11": 1800}                  # blank December
    assert "SYMBOL" not in rows and set(rows) >= {"JIOFIN", "NUVAMA", "TATASTEEL", "BANKNIFTY", "FINNIFTY"}
    tabbed = X.sample(NEW).replace(",", "\t")
    assert F.read_lots(tabbed)["rows"]["NIFTY"]["lots"]["2026-12"] == 65


def test_a_file_that_isnt_the_contract_file_is_a_clear_error():
    for bad in ("", "\x00\x01PK binary", "<html><body>Access denied</body></html>", "UNDERLYING,SYMBOL,OCT-26\n",
                "SYMBOL,LOT\nNIFTY,75\n"):
        with pytest.raises(ValueError):
            F.read_lots(bad)


def test_fuzz_the_readers_never_raise_anything_but_value_error():
    rng = random.Random(3)
    base = X.sample(NEW)
    for _ in range(300):
        chars = list(base)
        for _ in range(rng.randint(1, 40)):
            chars[rng.randrange(len(chars))] = rng.choice(",\n\t\"x9-  \x00")
        try:
            F.read_lots("".join(chars))
        except ValueError:
            pass
    for junk in (None, 1, "x", [], {}, {"data": [1, "x", None, {"sub": 5}]}, [[{"sub": "Exclusion from F&O", "date": None}]]):
        assert isinstance(F.read_circulars(junk, {"NIFTY"}), list)


# ---------- the changes ----------
def test_one_copy_shows_exits_lot_revisions_and_their_dates():
    got = {e["id"]: e for e in F.derive(F.read_lots(X.sample(NEW)), RULE)}
    exide = got["exit:EXIDEIND:2026-11"]
    assert exide["expiry"] == F.rule_expiry("2026-11").isoformat() and exide["lot"] == 1800
    assert got["exit:NUVAMA:2026-10"]["expiry"] == F.rule_expiry("2026-10").isoformat()
    nifty = got["lot:NIFTY:2026-12:75>65"]
    assert nifty["segment"] == "index" and nifty["effective"] > F.rule_expiry("2026-11").isoformat()
    assert (date.fromisoformat(nifty["effective"]) - F.rule_expiry("2026-11")).days <= 4     # the next trading day
    assert "lot:RELIANCE:2026-12:500>250" in got
    assert not any(k.startswith(("exit:INFY", "lot:INFY", "exit:NIFTY")) for k in got)


def test_two_copies_show_entries_and_lots_changed_within_a_series():
    old, new = F.read_lots(X.sample(OLD)), F.read_lots(X.sample(NEW))
    got = {e["id"]: e for e in F.diff(old, new, "2026-10-03", RULE)}
    assert got["entry:JIOFIN:2026-10"]["lot"] == 2350 and got["entry:JIOFIN:2026-10"]["effective"] == "2026-10-03"
    assert got["lot:TATASTEEL:2026-10:5500>5800"]["within"] is True
    assert got["lot:RELIANCE:2026-12:500>250"]["was"] == 500
    dropped = F.diff(new, {"months": new["months"], "rows": {k: v for k, v in new["rows"].items() if k != "NUVAMA"}}, "2026-10-28", RULE)
    assert [(e["kind"], e["symbol"], e["series"]) for e in dropped] == [("exit", "NUVAMA", "2026-10")]


def test_circulars_are_sorted_by_kind_with_the_symbols_they_name():
    got = F.read_circulars(X.sample("circulars.json"), set(F.read_lots(X.sample(NEW))["rows"]))
    by = {c["no"]: c for c in got}
    assert set(by) == {"FAOP/71001", "FAOP/71002", "FAOP/71003", "FAOP/71004", "FAOP/71007"}     # index and listing ones left out
    assert (by["FAOP/71001"]["kind"], by["FAOP/71001"]["symbols"], by["FAOP/71001"]["symbol"]) == ("exit", ["EXIDEIND", "NUVAMA"], None)
    assert (by["FAOP/71002"]["kind"], by["FAOP/71002"]["symbol"]) == ("entry", "JIOFIN")
    assert by["FAOP/71003"]["kind"] == "lot" and by["FAOP/71004"]["kind"] == "expiry" and by["FAOP/71004"]["symbol"] == "NIFTY"
    assert by["FAOP/71007"]["kind"] == "circular" and by["FAOP/71001"]["date"] == "2026-10-01"


# ---------- the dated list ----------
def test_refresh_keeps_a_dated_list_and_reports_only_what_is_new(w):
    feed = Feed()
    first = F.refresh(feed, DAY1, sleep=lambda s: None)
    assert first["new"] == [] and first["added"] >= 5 and first["problems"] == []      # the first read is not news
    ids = {e["id"] for e in F.load_events()}
    assert {"exit:EXIDEIND:2026-11", "lot:NIFTY:2026-12:75>65"} <= ids and not any(i.startswith("entry:JIOFIN") for i in ids)
    feed.nse.lots = X.sample(NEW)
    second = F.refresh(feed, DAY2, sleep=lambda s: None)
    assert {e["id"] for e in second["new"]} == {"entry:JIOFIN:2026-10", "lot:RELIANCE:2026-12:500>250",
                                                "lot:TATASTEEL:2026-10:5500>5800", "lot:TATASTEEL:2026-11:5800>5500"}
    assert all(e["seen"] == "2026-10-03" for e in second["new"])
    assert F.refresh(feed, DAY2, sleep=lambda s: None)["new"] == []                     # nothing twice
    st = json.loads(db.get_setting(F.KEY))
    assert st["lots"]["as_of"] == "2026-10-03" and st["circulars"]["count"] == 5


def test_a_source_that_fails_keeps_its_last_copy_and_a_busy_one_is_retried(w):
    feed, waits = Feed(), []
    F.refresh(feed, DAY1, sleep=waits.append)
    feed.nse.down = {"lots": 1}                                  # busy once: retried after a pause, then read
    out = F.refresh(feed, DAY2, sleep=waits.append)
    assert out["problems"] == [] and waits == [F.RETRIES[0]] and feed.nse.calls["lots"] == 3
    feed.nse.down, feed.nse.busy = {"lots": 1}, False           # refused outright: not retried, the old copy stays
    out = F.refresh(feed, DAY2 + timedelta(days=1), sleep=waits.append)
    assert out["problems"] and out["problems"][0].startswith("contract file") and len(waits) == 1
    st = json.loads(db.get_setting(F.KEY))
    assert st["lots"]["as_of"] == "2026-10-03" and st["lots"]["rows"]["NIFTY"] and st["lots"]["error"]
    feed.nse.down, feed.nse.busy = {"circulars": 9}, True        # busy through every retry
    out = F.refresh(feed, DAY2 + timedelta(days=2), sleep=waits.append)
    assert any(p.startswith("circulars") for p in out["problems"]) and len(waits) == 3
    feed.nse.lots = "<html>blocked</html>"
    out = F.refresh(feed, DAY2 + timedelta(days=3), sleep=lambda s: None)
    assert any("contract file" in p for p in out["problems"])
    v = F.view(DAY2)
    assert {s["id"]: s["failed"] for s in v["sources"]} == {"lots": True, "circulars": True}


def test_the_view_in_words_with_badges_and_no_advice(w):
    F.refresh(Feed(lots=X.sample(NEW)), DAY2, sleep=lambda s: None)
    v = F.view(DAY2)
    rows = {e["id"]: e for e in v["events"]}
    exide = rows["exit:EXIDEIND:2026-11"]
    assert exide["date"] == exide["expiry"] and exide["upcoming"] and exide["series_label"] == "Nov 2026"
    assert exide["text"] == f"EXIDEIND leaves F&O. The Nov 2026 series, expiring {F._day(exide['expiry'])}, is the last one the contract file lists."
    assert rows["lot:NIFTY:2026-12:75>65"]["text"].startswith("NIFTY's lot size goes from 75 to 65 from the Dec 2026 series")
    circ = next(e for e in v["events"] if e["source"] == "circular" and e["kind"] == "exit")
    assert circ["text"] == "Exchange circular FAOP/71001: Exclusion of EXIDEIND and NUVAMA from F&O segment"
    assert [e["date"] for e in v["events"]] == sorted((e["date"] for e in v["events"]), reverse=True)
    exp = date.fromisoformat(exide["expiry"])
    assert v["badges"]["EXIDEIND"][0]["short"] == f"Leaves F&O after {exp.day} {exp:%b}"
    assert v["badges"]["NIFTY"][0]["short"].startswith("Lot 75→65 from ")
    assert "JIOFIN" not in v["badges"]               # read on the first run: in the file, but not seen arriving
    assert not PROVIDERS.search(json.dumps(v)) and not ADVICE.search(json.dumps(v["events"]))
    later = F.view(exp + timedelta(days=1))
    assert "EXIDEIND" not in later["badges"]                     # after its last expiry the badge goes
    assert not F.view(date(2027, 6, 1))["badges"].get("NIFTY")   # a month after it applied


# ---------- who it touches, and the alert ----------
def _watch(uid, *syms):
    db.set_setting(f"watchlist:{uid}", json.dumps({"items": [{"region": "IN", "symbol": s} for s in syms] + [{"region": "US", "symbol": "AAPL"}]}))


def test_session_symbols_and_tracked(w):
    assert F.session_symbol({"type": "OPTIONS", "underlying": "NIFTY", "symbol": "NIFTY options"}) == "NIFTY"
    assert F.session_symbol({"fno": True, "name": "RELIANCE", "symbol": "RELIANCE26OCTFUT"}) == "RELIANCE"
    assert F.session_symbol({"symbol": "INFY", "market": "IN"}) == "INFY"
    assert F.session_symbol({"symbol": "BTC-USD", "market": "CRYPTO"}) is None
    _watch("u-basic", "tatasteel")
    db.create_session({"id": "11111111-1111-1111-1111-111111111111", "user_id": "u-basic", "name": "n", "status": "running",
                       "instrument": {"type": "OPTIONS", "underlying": "NIFTY", "market": "IN"}, "started_at": "2026-10-01T04:00:00+00:00"})
    db.create_session({"id": "22222222-2222-2222-2222-222222222222", "user_id": "u-basic", "name": "s", "status": "stopped",
                       "instrument": {"symbol": "INFY", "market": "IN"}, "started_at": "2026-09-01T04:00:00+00:00"})
    assert F.tracked("u-basic") == {"TATASTEEL", "NIFTY"}
    assert F.tracked("u-basic", running_only=False) == {"TATASTEEL", "NIFTY", "INFY"}


def test_alert_goes_once_to_those_who_turned_it_on_with_the_plan(w):
    F.refresh(Feed(), DAY1, sleep=lambda s: None)
    _watch("u-basic", "RELIANCE", "JIOFIN")
    _watch("u-free", "RELIANCE")
    _watch("u-pro", "INFY")
    for uid in ("u-basic", "u-free", "u-pro"):
        F.set_alert(uid, True)
    _watch("u-admin", "RELIANCE")                                 # watching, but the alert is off
    feed = Feed(lots=X.sample(NEW))
    new = F.refresh(feed, DAY2, sleep=lambda s: None)["new"]
    got = []
    allowed = lambda p: p["id"] != "u-free"  # noqa: E731
    n = F.fire(new, allowed, lambda p, s, t: got.append((p["id"], s, t)) or ["push"])
    assert n == 1 and [g[0] for g in got] == ["u-basic"]
    subject, text = got[0][1], got[0][2]
    assert subject == "StratLab: F&O contract changes for JIOFIN, RELIANCE"
    assert "JIOFIN enters F&O from the Oct 2026 series, with a lot of 2,350." in text and "RELIANCE's lot size goes from 500 to 250" in text
    assert "Facts, not advice." in text and not PROVIDERS.search(text) and not ADVICE.search(text)
    assert F.fire(new, allowed, lambda p, s, t: got.append(p["id"]) or ["push"]) == 0 and len(got) == 1     # once
    F.set_alert("u-basic", False)
    assert F.alert_row("u-basic") == {"on": False, "sent": F.alert_row("u-basic")["sent"]} and F.alert_row("u-basic")["sent"]


def test_routes_view_alert_setting_and_admin_refresh(w, paid):
    c = w["client"]
    assert c.get("/trade/fo-changes").status_code == 401
    r = c.get("/trade/fo-changes", headers=headers("free-token"))
    assert r.status_code == 200 and r.json()["events"] == [] and r.json()["alerts"]["allowed"] is False
    assert c.post("/admin/fo-changes/refresh", headers=headers("pro-token")).status_code in (401, 403)
    r = c.post("/admin/fo-changes/refresh", headers=headers("admin-token"))
    assert r.status_code == 200 and r.json()["problems"] == [] and r.json()["added"] >= 5
    _watch("u-free", "EXIDEIND")
    v = c.get("/trade/fo-changes", headers=headers("free-token")).json()       # free to view
    assert any(e["symbol"] == "EXIDEIND" and e["kind"] == "exit" for e in v["events"]) and v["mine"] == ["EXIDEIND"]
    assert v["badges"]["EXIDEIND"][0]["short"].startswith("Leaves F&O after")
    assert {s["id"] for s in v["sources"]} == {"lots", "circulars"} and v["as_of"]
    assert not PROVIDERS.search(json.dumps(v))
    r = c.put("/trade/fo-changes/alerts", headers=headers("free-token"), json={"on": True})
    assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
    assert c.put("/trade/fo-changes/alerts", headers=headers("free-token"), json={"on": False}).status_code == 200    # off is always allowed
    r = c.put("/trade/fo-changes/alerts", headers=headers("basic-token"), json={"on": True})
    assert r.status_code == 200 and r.json()["on"] is True and r.json()["allowed"] is True
    assert c.get("/trade/fo-changes", headers=headers("basic-token")).json()["alerts"]["on"] is True
    for bad in ({}, {"on": "maybe"}, {"on": [1]}):
        assert c.put("/trade/fo-changes/alerts", headers=headers("basic-token"), json=bad).status_code == 422


def test_the_job_reads_twice_a_trading_day_and_sends_what_is_new(w):
    feed, sent = Feed(), []
    job = F.Job(lambda: feed, lambda new: sent.append(new) or 1)
    from app.data import calendar
    day = date.today()
    while not calendar.is_trading_day("IN", day):
        day -= timedelta(days=1)
    morning = datetime.combine(day, datetime.min.time()).replace(hour=8, minute=30, tzinfo=ZoneInfo("Asia/Kolkata"))
    job.tick(morning)
    assert db.get_setting("newsjob:fochanges-am") == day.isoformat() and F.load_state().get("lots")
    assert sent == []                                             # the first read sends nothing
    feed.nse.lots = X.sample(NEW).replace("JIOFIN", "NEWFNO")
    job.tick(morning.replace(hour=20))
    assert db.get_setting("newsjob:fochanges-pm") == day.isoformat()
    assert sent and any(e["symbol"] == "NEWFNO" for e in sent[0]) and job.status["added"] >= 1
    assert job.tick(morning.replace(hour=21)) == 0                # once per run


def test_listed_expiries_come_from_the_contract_list_when_there_is_one(w):
    ex = R.listed_expiries()
    from app import main
    rows = [r for r in main.options_data._rows.get("NFO", []) if r["type"] == "FUT"]
    if rows:
        r = rows[0]
        assert ex(r["name"].upper(), r["expiry"][:7]).isoformat() >= r["expiry"]
    assert ex("NOSUCH", "2026-07") == F.rule_expiry("2026-07")
