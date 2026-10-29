"""Review 5c, the backend side of the Invest and Research screen fixes: an Indian company page whose price came from the
fallback source keeps that price's trade time (a stale price was dated "now"), a price with no time at all has no "as of"
and says its trading day is unknown, and the watchlist at a glance says how many companies it left out."""
import json
from datetime import datetime, timedelta, timezone

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app.intel import company as company_mod
from app.intel import routes
from app.intel.company import Research

YESTERDAY_CLOSE = "2026-10-08T15:29:59+05:30"


def _fallback_company(monkeypatch, got: dict) -> dict:
    """An Indian company page with the broker offline: the price from the fallback source (`y`) or the fundamentals page."""
    hub = Research.__new__(Research)
    monkeypatch.setattr(hub, "_kite", lambda: False, raising=False)
    monkeypatch.setattr(hub, "_run", lambda tasks: (got, []), raising=False)
    monkeypatch.setattr(company_mod, "_stored_dividends_in", lambda sym: [])
    return hub._company_in("TITAN", lean=True)


# ---------- a stale fallback price keeps its time ----------
def test_the_fallback_quote_keeps_the_time_of_its_last_trade(monkeypatch):
    y = {"price": 3410.5, "change": -12.0, "change_pct": -0.35, "high": 3440.0, "low": 3401.0, "prev_close": 3422.5,
         "volume": 1000, "at": YESTERDAY_CLOSE, "name": "Titan Company"}
    c = _fallback_company(monkeypatch, {"y": y})
    assert c["quote"]["at"] == YESTERDAY_CLOSE
    # the page's "as of" is that trade's time, and its day is the trading day it is of, not today
    assert routes.prices_as_of(c) == "2026-10-08T15:29+05:30"
    assert routes.quote_day("IN", c) == "2026-10-08"


def test_a_price_from_the_fundamentals_page_has_no_time_and_no_fresh_as_of(monkeypatch):
    scr = {"name": "Titan Company Ltd", "ratios": {"Current Price": 3410.5}, "fetched_at": "2026-10-08T06:00:00+00:00"}
    monkeypatch.setattr(company_mod, "scr_summary", lambda s, listed_on=None: {"price": 3410.5})
    c = _fallback_company(monkeypatch, {"scr": scr})
    assert c["quote"] == {"price": 3410.5, "at": None}
    assert routes.prices_as_of(c) is None                     # never "now"
    assert routes.quote_day("IN", c) is None                  # the page says the time is unknown


def test_prices_as_of_is_the_trade_time_and_never_after_now():
    assert routes.prices_as_of({"quote": {"price": 1, "at": YESTERDAY_CLOSE}}) == "2026-10-08T15:29+05:30"
    assert routes.prices_as_of({"quote": {"price": 1, "at": "2026-10-09T20:00:00Z"}}) == "2026-10-09T20:00+00:00"
    later = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    assert routes.prices_as_of({"quote": {"price": 1, "at": later}}) <= datetime.now(timezone.utc).isoformat(timespec="minutes")
    assert routes.prices_as_of({"quote": {"price": 1}}) is None
    assert routes.prices_as_of({"quote": None}) is None
    assert routes.prices_as_of({"quote": {"price": 1, "at": "not a time"}}) is None


def test_the_company_answer_says_the_prices_day(monkeypatch):
    page = {"region": "IN", "symbol": "TITAN", "name": "Titan", "quote": {"price": 3410.5, "at": YESTERDAY_CLOSE}}

    class Hub:
        def company(self, r, s, lean=False):
            return dict(page)
    monkeypatch.setattr(routes, "hub", Hub())
    monkeypatch.setattr(routes, "page_figures", lambda r, c: c)
    monkeypatch.setattr(routes, "market_open", lambda r, now=None: True)
    out = json.loads(routes.company("IN", "TITAN", lean=True, profile={"id": "u"}).body)
    assert out["quote_day"] == "2026-10-08" and out["as_of"] == "2026-10-08T15:29+05:30" and out["market_open"] is True
    page["quote"] = {"price": 3410.5, "at": None}
    out = json.loads(routes.company("IN", "TITAN", lean=True, profile={"id": "u"}).body)
    assert out["quote_day"] is None and out["as_of"] is None


# ---------- the watchlist at a glance says how many it checked of how many ----------
def test_the_watchlist_at_a_glance_returns_the_total(monkeypatch):
    syms = [f"S{i:02d}" for i in range(27)]
    monkeypatch.setattr(main, "need", lambda *a, **k: None)
    monkeypatch.setattr(main.filings, "watchlist_symbols", lambda uid, region: list(syms))
    monkeypatch.setattr(main, "_quiet", lambda *a, **k: {})

    def no_rotation(*a, **k):
        raise RuntimeError("not needed here")
    monkeypatch.setattr(main.rotation, "run", no_rotation)

    class Pool:
        def map(self, fn, items):
            return [{"symbol": s} for s in items]
    monkeypatch.setattr(main, "_investor_pool", Pool())
    out = json.loads(main.investor_home(region="IN", profile={"id": "u"}).body)
    assert len(out["rows"]) == main.investor.MAX == 20
    assert out["total"] == 27
    monkeypatch.setattr(main.filings, "watchlist_symbols", lambda uid, region: [])
    assert json.loads(main.investor_home(region="US", profile={"id": "u"}).body)["total"] == 0


# ---------- the watchlist's quotes: the server's cap stays, the page asks in batches ----------
def test_the_quotes_call_answers_at_most_24_symbols_a_request(monkeypatch):
    asked = []

    class Hub:
        def quotes(self, r, syms):
            asked.append(list(syms))
            return {s: {"price": 1.0} for s in syms}
    monkeypatch.setattr(routes, "hub", Hub())
    out = json.loads(routes.quotes(region="US", symbols=",".join(f"T{i}" for i in range(30)), profile={"id": "u"}).body)
    assert len(asked[0]) == 24 and len(out) == 24              # the page sends 24 at a time (lib/investUi QUOTE_BATCH)
