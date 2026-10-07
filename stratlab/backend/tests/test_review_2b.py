"""Round 2B review fixes: dates stamped by the data, one shared price reading, library evidence and reasons, and pages
that open without failing requests."""
from datetime import datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401,I001  (first: the app wires the modules)
from app import holdings, library
from tests import world as W
from tests.fake_db import headers
from tests.fake_kite import IST, session_clock


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


# ---------- R2B-001: a stamp is the time of the latest trade, never the moment of asking ----------
def test_prices_are_stamped_with_the_latest_trade_not_now():
    now = datetime(2026, 10, 7, 22, 0, tzinfo=timezone.utc)                       # 03:30 IST on 8 Oct
    quotes = [{"at": "2026-10-07T15:29:58"}, {"at": "2026-10-07T15:30:00+05:30"}, {"price": 1}, {"at": "junk"}]
    got = holdings.latest_trade(quotes, now)
    assert got.astimezone(IST).isoformat() == "2026-10-07T15:30:00+05:30"          # a stamp without a zone is India's
    assert holdings.latest_trade([{"at": "2026-10-09T09:00:00+05:30"}], now) == now      # never later than the moment it was read
    assert holdings.latest_trade([{"price": 1}], now) is None


def test_the_fake_broker_stands_still_out_of_hours():
    night = datetime(2026, 10, 8, 3, 31, tzinfo=IST)                               # Thursday, before the open
    assert session_clock(night) == datetime(2026, 10, 7, 15, 30, tzinfo=IST)
    assert session_clock(datetime(2026, 10, 10, 12, 0, tzinfo=IST)) == datetime(2026, 10, 9, 15, 30, tzinfo=IST)    # a Saturday: Friday's close
    assert session_clock(datetime(2026, 10, 5, 8, 0, tzinfo=IST)) == datetime(2026, 10, 2, 15, 30, tzinfo=IST)      # Monday morning: Friday's close
    mid = datetime(2026, 10, 7, 11, 5, tzinfo=IST)
    assert session_clock(mid) == mid


def test_quotes_carry_the_zone_of_the_trade(w):
    q = main.kite.quote(["RELIANCE"])["RELIANCE"]
    assert q["at"].endswith("+05:30")


# ---------- R2B-002: one reading of the prices for every page ----------
def test_pages_opened_seconds_apart_share_one_reading(w, monkeypatch):
    calls = []
    real = main.kite.quote
    monkeypatch.setattr(main.kite, "quote", lambda syms: (calls.append(1), real(syms))[1])
    main._PRICED.clear()
    p = {"id": "u-share", "_plan": "pro"}
    holdings.save("u-share", [{"symbol": "RELIANCE", "qty": 10, "avg": 1000.0}], "manual")
    a, b = main.holdings_view(p), main.holdings_view(p)
    assert len(calls) == 1 and a["totals"] == b["totals"] and a["prices_at"] == b["prices_at"]
    main._PRICED.clear()
    main.holdings_view(p)
    assert len(calls) == 2                                                         # after the window, a fresh reading
    holdings.delete("u-share")


# ---------- R2B-004 / R2B-005: the library ----------
def test_a_strategy_that_never_traded_sorts_below_the_rest_and_says_so():
    idle = {"name": "idle", "verdict": {"verdict": "edge"}, "stats": {"unseen": None, "ret": 0, "trades": 0}, "published_at": "2026-10-09", "copies": 9}
    busy = {"name": "busy", "verdict": {"verdict": "no_edge"}, "stats": {"unseen": -2, "ret": -5, "trades": 40}, "published_at": "2026-10-01", "copies": 0}
    for sort in ("best", "new", "copied"):
        assert [r["name"] for r in library.search([idle, busy], sort=sort)] == ["busy", "idle"]
    assert library.ran(idle) is False and library.ran(busy) is True
    assert library.public(idle)["ran"] is False


def test_each_card_has_one_line_reason_from_the_verdicts_own_checks():
    checks = [{"id": "unseen", "status": "pass"}, {"id": "nearby", "status": "fail"}, {"id": "shuffle", "status": "skip"}, {"id": "sample", "status": "pass"}]
    e = {"verdict": {"verdict": "luck", "passed": 2, "total": 3, "checks": checks}, "stats": {"trades": 40, "ret": 12}}
    assert library.reason(e) == "Passed: unseen years, enough trades. Failed: nearby settings. Not run: bad-luck fall."
    assert library.reason({"verdict": {"verdict": "not_enough"}, "stats": {"trades": 3}}) == "Only 3 trades in this period, too few to tell skill from luck."
    assert library.reason({"verdict": {"verdict": "not_enough"}, "stats": {"trades": 0}}) == "No trades in this period, so nothing was tested."
    assert library.reason({"verdict": {"verdict": "no_edge"}, "stats": {"trades": 30, "ret": -4}}).startswith("Lost money after costs")
    assert library.reason({"verdict": {"verdict": "edge"}, "stats": {"trades": 30}}) is None                  # an older entry with no checks
    assert library._unseen({"verdict": {"checks": [{"id": "unseen", "status": "pass", "data": {"unseen_ret": 0}}]}}) is None


# ---------- R2B-011: no failing requests for "no data" ----------
def test_a_company_with_no_shareholding_filing_is_an_empty_200(w):
    r = w["client"].get("/research/holders/RELIANCE", headers=headers("free-token"))
    assert r.status_code == 200 and r.json()["available"] is False and r.json()["holders"] == []


def test_an_unusable_ai_read_is_a_200_that_says_so(w, monkeypatch):
    from app.intel import ai as A
    monkeypatch.setattr(A, "complete", lambda system, text, **kw: "not json at all")
    r = w["client"].get("/research/company/IN/RELIANCE/ai", headers=headers("pro-token"))
    assert r.status_code == 200 and r.json()["unavailable"] is True and r.json()["code"] == "ai_failed"


def test_the_company_pages_price_stamp_is_the_quotes_trade_time(w):
    r = w["client"].get("/research/company/IN/RELIANCE", headers=headers("pro-token")).json()
    assert datetime.fromisoformat(r["as_of"]) <= datetime.now(timezone.utc) + timedelta(seconds=1)
    assert datetime.fromisoformat(r["as_of"]) == datetime.fromisoformat(r["quote"]["at"]).replace(second=0, microsecond=0)
