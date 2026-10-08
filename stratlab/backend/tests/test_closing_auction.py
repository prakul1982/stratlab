"""The closing auction desk: reading the exchange's CAS data (the real idle answer and the in-auction shape), the
arithmetic, the phase, the job's window and the stored day, the 60-day history and its plan gate, the pages' answers,
and paper option positions at the indicative settlement."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import main  # noqa: I001  (first: the app loads the newsletter job before the modules built on it)
from app import closing_auction as CA, db
from app.data import sessions as S
from tests import fake_cas as FC
from tests import world as W
from tests.fake_db import headers
from tests.test_journal import payments_live

IST = timezone(timedelta(hours=5, minutes=30))
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|cheap|expensive|squeeze|will close)\b", re.I)


def ist(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=IST)


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    CA.forget()


# ---------- reading ----------
def test_reads_the_real_idle_answer():
    s = CA.parse_stocks(FC.idle_stocks())
    assert s["rows"] == {} and s["eligible"][:3] == ["360ONE", "ABB", "ABCAPITAL"] and len(s["eligible"]) == 12
    i = CA.parse_indices(FC.idle_indices())
    assert i["NIFTY 50"] == {"value": 22431.65, "prev_close": 22421.95, "indicative": None, "status": "CLOSE"}


def test_reads_the_real_answer_after_the_auction():
    s = CA.parse_stocks(FC.closed_stocks())
    assert s["as_of"] == "2026-10-05T15:29:43+05:30" and s["status"] == "Closed"
    r = s["rows"]["HDFCBANK"]
    assert (r["ref"], r["final"], r["final_qty"], r["lower"], r["upper"]) == (705.45, 704.8, 1204879, 684.3, 726.6)
    assert (r["buy_qty"], r["sell_qty"]) == (3041126, 3028799)
    v = CA.stock_view("HDFCBANK", r, "closed")
    assert v["final_out"] and v["gap"] == -0.09 and v["price"] == 704.8
    i = CA.parse_indices(FC.closed_indices())
    assert i["NIFTY 50"]["value"] == 22555.75 and i["NIFTY 50"]["indicative"] is None


def test_reads_the_auction_loosely():
    s = CA.parse_stocks(FC.auction_stocks())
    assert sorted(s["rows"]) == ["INFY", "RELIANCE", "TCS"]          # no price at all, and a bad symbol, are left out
    r = s["rows"]["RELIANCE"]
    assert (r["ref"], r["iep"], r["ieq"], r["final"], r["imb"]) == (1400.0, 1407.0, 250000, None, 1200)
    assert CA.parse_stocks(None)["rows"] == {} and CA.parse_indices({"x": 1}) == {}
    assert CA.num("1,234.50") == 1234.5 and CA.num("-") is None and CA.num(True) is None


def test_gap_and_words():
    assert CA.gap(1407, 1400) == 0.5 and CA.gap(2964, 3000) == -1.2 and CA.gap(1500, 1500) == 0.0
    assert CA.gap(None, 1) is None and CA.gap(1, 0) is None and CA.gap(200, 100) is None     # beyond any band: broken
    assert CA.words(0.5) == "0.50% above the reference price" and CA.words(-1.2) == "1.20% below the reference price"
    assert CA.words(0.0) == "at the reference price" and CA.words(None) == ""


def test_stock_view_uses_the_final_price_once_out():
    live = CA.parse_stocks(FC.auction_stocks())["rows"]["TCS"]
    v = CA.stock_view("TCS", live, "entry")
    assert v["price"] == 2964.0 and not v["final_out"] and v["text"] == "TCS: IEP 1.20% below the reference price"
    done = CA.parse_stocks(FC.auction_stocks(final=True))["rows"]["TCS"]
    v = CA.stock_view("TCS", done, "closed")
    assert v["final_out"] and v["final_qty"] == 91000 and v["text"].startswith("TCS: final price")


def test_a_price_is_called_final_only_once_the_auction_is_over(w):
    """A closing price read as final while continuous trading goes on was called "final" on the page (R4-010): the indicative
    equilibrium price stays indicative until the auction has finished; an earlier day's read is that day's finished auction."""
    done = CA.parse_stocks(FC.auction_stocks(final=True))["rows"]["TCS"]
    for phase in ("preopen", "before", "transition", "entry", "matching"):
        v = CA.stock_view("TCS", done, phase)
        assert not v["final_out"] and v["final"] is None and v["price"] == done["iep"] and "IEP" in v["text"], phase
    assert CA.stock_view("TCS", done, "closed")["final_out"]
    me = {"id": "u-pro", "_plan": "pro"}
    CA.refresh(FC.Feed(final=True), now=ist(2026, 10, 5, 15, 40).astimezone(timezone.utc))      # the read the day's auction left
    for at, final in ((ist(2026, 10, 5, 15, 31), False), (ist(2026, 10, 5, 15, 36), True),       # the same day: through matching, then over
                      (ist(2026, 10, 6, 10, 4), True)):                                          # the next morning: that day's finished auction
        v = CA.view(me, at)
        assert v["stocks"] and all(r["final_out"] is final for r in v["stocks"]), at
        assert v["fresh"] is (at.date() == date(2026, 10, 5)) and v["day"] == "2026-10-05"


@pytest.mark.parametrize("hm,phase", [("15:14:59", "before"), ("15:15", "transition"), ("15:19:59", "transition"), ("15:20", "entry"),
                                      ("15:29:59", "entry"), ("15:30", "matching"), ("15:34:59", "matching"), ("15:35", "closed")])
def test_phase_boundaries(hm, phase):
    h, m, *s = map(int, hm.split(":"))
    assert S.phase(ist(2026, 10, 5, h, m, s[0] if s else 0)) == phase
    assert S.phase(ist(2026, 7, 31, 15, 20)) == "none"            # before the auction began


# ---------- the job ----------
def test_job_reads_in_the_window_and_stores_the_day(w, monkeypatch):
    feed = FC.Feed()
    job = CA.Job(lambda: feed)
    assert job.tick(datetime(2026, 10, 5, 9, 43, tzinfo=timezone.utc)) is None            # 15:13 IST: not yet
    assert job.tick(datetime(2026, 10, 5, 9, 44, tzinfo=timezone.utc)) == "read" and feed.calls == 1
    assert job.tick(datetime(2026, 10, 5, 9, 44, 10, tzinfo=timezone.utc)) is None and feed.calls == 1   # every 30 s
    live = CA.load_live()
    assert live["day"] == "2026-10-05" and live["start"]["NIFTY 50"] == 25000.0
    assert job.tick(datetime(2026, 10, 4, 9, 50, tzinfo=timezone.utc)) is None            # a Sunday
    feed.final = True
    job._next = 0
    assert job.tick(datetime(2026, 10, 5, 10, 6, tzinfo=timezone.utc)) == "read"          # 15:36
    assert job.tick(datetime(2026, 10, 5, 10, 11, tzinfo=timezone.utc)) == "recorded"     # 15:41
    got = json.loads(db.get_setting(CA.DAY_KEY + "2026-10-05"))
    assert got["stocks"]["RELIANCE"] == [1400.0, 1407.0, 260000] and got["indices"]["NIFTY 50"] == [25000.0, 25075.0]
    assert job.tick(datetime(2026, 10, 5, 10, 20, tzinfo=timezone.utc)) is None           # once
    h = CA.history()
    assert h["days"][0]["day"] == "2026-10-05" and h["days"][0]["widest"] == {"symbol": "TCS", "gap": -1.2}
    assert h["days"][0]["indices"][0]["gap"] == 0.3


def test_job_survives_a_dead_feed(w):
    job = CA.Job(lambda: FC.Feed(fail=True))
    assert job.tick(datetime(2026, 10, 5, 9, 50, tzinfo=timezone.utc)) is None and "down" in job.status["last_error"]


def test_history_keeps_sixty_days(w):
    live = {"day": None, "stocks": {"A": dict(zip(CA.FIELDS, [100, 97, 103, 101, 1, 101, 5, 0, 0, 1, 1, 1, 1]))}, "indices": {}, "start": {}}
    d = date(2026, 1, 1)
    for i in range(CA.KEEP_DAYS + 3):
        day = (d + timedelta(days=i)).isoformat()
        CA.record_day(day, {**live, "day": day})
    assert len(CA.history()["days"]) == CA.KEEP_DAYS
    assert CA.record_day("2026-12-01", live) == 0                 # a read from another day doesn't count


# ---------- the pages ----------
def test_routes_and_gate(w, monkeypatch):
    c = w["client"]
    CA.refresh(main.filings_feed)                                  # the world's exchange: the auction just ended
    FC.seed(date.today())
    r = c.get("/trade/closing-auction", headers=headers("free-token"))
    assert r.status_code == 200
    v = r.json()
    assert v["stocks"][0]["symbol"] == "TCS" and v["eligible"] == 3 and v["indices"][0]["name"] == "NIFTY 50"
    assert v["timetable"]["derivatives_close"] in ("15:40", "15:30") and "settle" in v["expiry"]["settlement"]
    text = json.dumps(v)
    assert not PROVIDERS.search(json.dumps({k: x for k, x in v.items() if k != "sources"})) and not ADVICE.search(v["note"])
    assert c.get("/trade/closing-auction").status_code == 401
    payments_live(monkeypatch)
    assert c.get("/trade/closing-auction/history", headers=headers("free-token")).status_code == 402
    r = c.get("/trade/closing-auction/history", headers=headers("basic-token"))
    assert r.status_code == 200 and len(r.json()["days"]) == 8
    r = c.get("/trade/closing-auction/history?symbol=reliance", headers=headers("basic-token"))
    # the stored days are at the demo world's closes (fake_prices): the latest one's final price is RELIANCE's close
    # that day, 0.1% above its reference price
    st = r.json()["days"][0]["stock"]
    assert st["ref"] == pytest.approx(st["final"] / 1.001, abs=0.01)
    assert c.get("/trade/closing-auction/history?symbol=A;B", headers=headers("basic-token")).status_code == 422
    assert c.get(f"/trade/closing-auction/history?symbol={'X' * 40}", headers=headers("basic-token")).status_code == 422
    assert "TCS" in text


def test_positions_at_the_indicative_settlement(monkeypatch):
    leg = lambda opt, side, k, entry: {"open": True, "strike": k, "opt": opt, "side": side, "qty": 75, "entry": entry, "sym": f"NIFTY{k}{opt}"}
    eng = SimpleNamespace(pos={"expiry": "2026-10-06", "closed_pnl": 0.0,
                               "legs": [leg("CE", "sell", 25000, 100.0), leg("PE", "sell", 25000, 90.0)]})
    sess = SimpleNamespace(id="s1", name="Straddle", kind="options", engine=eng,
                           strategy=SimpleNamespace(exchange="NFO", underlying="NIFTY"))
    monkeypatch.setattr(main.manager, "user_running", lambda uid: [sess])
    idx = CA.parse_indices(FC.auction_indices())
    [p] = CA.positions_at_settlement({"id": "u"}, idx, {}, date(2026, 10, 6))
    assert p["settle_on"] == 25075.0 and [l["value"] for l in p["legs"]] == [75.0, 0.0]
    assert p["open_pnl"] == (100 - 75) * 75 + 90 * 75
    assert CA.positions_at_settlement({"id": "u"}, idx, {}, date(2026, 10, 7)) == []      # not expiring that day
