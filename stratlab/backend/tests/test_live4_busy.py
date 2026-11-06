"""LIVE4-004: a busy source is never "no such company". 21 company pages at once answered "Couldn't find ITC" (a 502) for a valid stock
and cut other pages down to the name in capitals with no market value; a busy source now says busy, and the company's last stored
figures stand in meanwhile."""
import pytest

from app import main
from app.intel import company as C
from app.intel.net import SourceError


@pytest.fixture
def w(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


class KiteBusy(Exception):
    """The broker's turn not reached in time (the real one is kite_service.KiteBusy, not a SourceError)."""


def _busy_sources(monkeypatch):
    hub = main.research_hub
    def scr(*a, **k):
        raise SourceError("Screener.in", "Screener.in is busy (our rate limit). Try again in a minute.", busy=True)
    def quote(*a, **k):
        raise KiteBusy("no broker turn in 4 s")
    monkeypatch.setattr(hub, "_fundamentals", scr)
    monkeypatch.setattr(hub, "_page_quote", quote)


def test_a_listed_company_with_every_source_busy_is_busy_not_not_found(w, monkeypatch):
    _busy_sources(monkeypatch)
    monkeypatch.setattr(C.Research, "kept_facts", None)
    r = w["client"].get("/research/company/IN/ITC", headers=w["headers"]("pro-token"))
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["message"] == C.BUSY_TEXT and "Couldn't find" not in r.text


def test_a_busy_fundamentals_source_shows_the_last_stored_figures(w, monkeypatch):
    _busy_sources(monkeypatch)
    kept = {"name": "ITC Limited", "market_cap": 512345.0, "pe": 25.5, "roe": 28.1, "div_yield": 3.4, "price": 410.0, "price_at": "2026-10-27",
            "built_at": "2026-10-27T18:00:00+00:00"}
    monkeypatch.setattr(C.Research, "kept_facts", staticmethod(lambda r, s: kept if (r, s) == ("IN", "ITC") else None))
    r = w["client"].get("/research/company/IN/ITC", headers=w["headers"]("pro-token"))
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["name"] == "ITC Limited" and c["market_cap"] == pytest.approx(512345.0 * 1e7) and c["figures_kept"] == kept["built_at"]
    val = {i["label"]: i["value"] for g in c["metrics"] if g["title"] == "Valuation" for i in g["items"]}
    assert val["P/E"] == pytest.approx(25.5) and c["quote"]["price"] == 410.0


def test_an_unknown_company_is_still_not_found(w):
    r = w["client"].get("/research/company/IN/ZZZZNOTREAL", headers=w["headers"]("pro-token"))
    assert r.status_code == 404 and "Couldn't find ZZZZNOTREAL" in r.json()["detail"]["message"]


def test_busy_errors_are_told_from_missing_ones():
    assert C.busy_error(SourceError("x", "busy", busy=True)) and C.busy_error(KiteBusy()) and C.busy_error(TimeoutError())
    assert not C.busy_error(SourceError("x", "has nothing for that")) and not C.busy_error(ValueError("parse"))
    assert C.kept_summary(None) == {} and C.kept_summary({"market_cap": 5.0, "pe": None, "debt": 2.0}) == {"market_cap_cr": 5.0, "debt_cr": 2.0}


def test_a_us_page_with_its_listing_source_busy_is_busy_not_no_such_company(monkeypatch):
    hub = main.research_hub
    def meta(sym):
        raise SourceError("Yahoo Finance", "busy", busy=True)
    monkeypatch.setattr(hub.yahoo, "meta", meta)
    with pytest.raises(SourceError) as e:
        hub._us_listing("NVDA")
    assert e.value.busy and not isinstance(e.value, C.NotFound)


# ---------- LIVE4-022: a slow first read never holds a request until the host gives up on it ----------
def test_a_first_read_slower_than_the_wait_answers_pending_and_is_kept_when_it_lands():
    import threading
    import time
    from app import swr
    swr.clear()
    gate, calls = threading.Event(), []

    def slow():
        calls.append(1)
        gate.wait(5)
        return ["filed"]
    t0 = time.monotonic()
    with pytest.raises(swr.Pending):
        swr.get(("biz", "SLOWCO"), slow, wait=0.2)
    assert time.monotonic() - t0 < 1.0
    with pytest.raises(swr.Pending):
        swr.get(("biz", "SLOWCO"), slow, wait=0.1)          # asked again meanwhile: the same read, not a second one
    gate.set()
    time.sleep(0.2)
    assert swr.get(("biz", "SLOWCO"), slow, wait=0.1) == ["filed"] and len(calls) == 1
    with pytest.raises(RuntimeError):                      # a read that fails in time raises its error, as without a wait
        swr.get(("biz", "BADCO"), lambda: (_ for _ in ()).throw(RuntimeError("down")), wait=1.0)
    swr.clear()


def test_the_business_updates_route_says_pending_while_the_first_read_goes_on(w, monkeypatch):
    import threading
    from app import biz_updates, swr
    swr.clear()
    gate = threading.Event()
    monkeypatch.setattr(biz_updates, "FIRST_READ_WAIT", 0.1)
    monkeypatch.setattr(biz_updates, "feed_items", lambda feed, sym: gate.wait(5) and [])
    r = w["client"].get("/research/business-updates/HDFCBANK", headers=w["headers"]("pro-token"))
    assert r.status_code == 200 and r.json()["pending"] is True
    gate.set()
    import time
    time.sleep(0.2)
    r = w["client"].get("/research/business-updates/HDFCBANK", headers=w["headers"]("pro-token"))
    assert r.status_code == 200 and not r.json().get("pending")
    swr.clear()
