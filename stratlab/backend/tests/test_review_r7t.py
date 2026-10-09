"""Round 7 time review of the live site during India's open (9 Oct 2026), the server's side: each test is built on the
example the reviewer saw. Every clock is a fixed instant with its zone, never the time the tests run."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import breadth, breadth_live, db, positioning as P, stock_alerts as SA, vix
from app.intel import company as C, news as N, routes as research_routes
from app.newsletter import job as news_job, write
from app.options.engine import next_entry, next_entry_note
from tests import fake_positioning as FP

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc
OPEN = datetime(2026, 10, 9, 9, 39, tzinfo=IST)          # 9 Oct 2026, India open: the review's own moment
PRE_OPEN = datetime(2026, 10, 9, 9, 13, tzinfo=IST)
EARLY = datetime(2026, 10, 9, 7, 30, tzinfo=IST)


def items(c: dict) -> dict:
    return {i["label"]: i for g in c.get("metrics") or [] for i in g["items"]}


# ---------- R7T-001: BRK-B's range, EPS and P/E were Class A's beside a Class B price ----------
BRK_LISTING = {"symbol": "BRK-B", "currency": "USD", "exchange": "NYSE", "price": 511.05, "high52": 537.74, "low52": 464.01}
BRK_METRICS = {"52WeekLow": 698000.0, "52WeekHigh": 806102.8, "epsTTM": 59668.8094, "peTTM": 8.6}


def brk_page() -> dict:
    return {"region": "US", "symbol": "BRK-B", "quote": {"price": 511.05, "high": 513.1499, "low": 505.27},
            "range52": {"low": 698000.0, "high": 806102.8}, "market_cap": 983733560143.465,
            "metrics": [{"title": "Valuation", "items": [{"label": "P/E", "value": 0.01, "unit": "x"},
                                                         {"label": "Fwd P/E", "value": 23.07, "unit": "x"}]},
                        {"title": "Per share and returns", "items": [{"label": "EPS TTM", "value": 59668.8094, "unit": "money"}]}],
            "earnings": [{"period": "2026-06-30", "actual": 9038.3, "estimate": 7594.57, "surprise_pct": 19.01}],
            "next_earnings": {"date": "2026-11-02", "eps_estimate": 8887.52}}


def test_brk_b_takes_its_own_listings_range_not_class_as():
    one = C.us_listing({"exchange": "NEW YORK STOCK EXCHANGE, INC.", "currency": "USD", "marketCapitalization": 983733.56},
                       BRK_LISTING, BRK_METRICS)
    assert one["range52"] == {"low": 464.01, "high": 537.74}
    # a range that can't be the share's is never shown under its price
    assert C.with_today_range(brk_page())["range52"] == {"low": None, "high": None}
    assert C.plausible_range(511.05, 464.01, 537.74) and not C.plausible_range(511.05, 698000.0, 806102.8)


def test_brk_bs_class_a_eps_and_pe_are_left_out_without_a_public_figure(monkeypatch):
    monkeypatch.setattr(research_routes, "public_facts", lambda r, s: None)
    out = research_routes.per_share_checked(research_routes.with_public_eps("US", brk_page()))
    got = items(out)
    assert "P/E" not in got and "EPS TTM" not in got and got["Fwd P/E"]["value"] == 23.07
    assert out["earnings"] == [] and out["next_earnings"] == {"date": "2026-11-02", "eps_estimate": None}


def test_brk_bs_pe_and_value_are_its_public_pages_in_class_b_terms(monkeypatch):
    # the public page after R7V-001: every class in Class B shares (~2.14bn), P/E the value over the four quarters' profit
    f = {"region": "US", "symbol": "BRK-B", "price": 511.05, "price_at": "2026-10-08", "market_cap": 1_094_000.0, "pe": 12.76,
         "eps": 40.05, "pe_basis": "ttm", "pe_end": "2026-06-30", "sales_usd": 372_000.0, "unit": "$ million"}
    monkeypatch.setattr(research_routes, "public_facts", lambda r, s: f)
    c = {**brk_page(), "quote": {"price": 520.0, "high": 521.0, "low": 509.0}}
    out = research_routes.per_share_checked(research_routes.with_public_eps("US", c))
    got = items(out)
    assert got["EPS TTM"]["value"] == 40.05 and got["P/E"]["value"] == round(520.0 / 40.05, 2)
    assert out["market_cap"] == pytest.approx(1_094_000.0 * 1e6 * 520.0 / 511.05)
    # a public page whose P/E is n/a (as BRK-B's was on 9 Oct): n/a here too, and Class A's EPS goes with it
    monkeypatch.setattr(research_routes, "public_facts", lambda r, s: {**f, "pe": None, "eps": None})
    got = items(research_routes.with_public_eps("US", brk_page()))
    assert "P/E" not in got and "EPS TTM" not in got


# ---------- R7T-007: the year's range takes in today's high and low ----------
def test_the_52_week_low_takes_in_todays_low():
    c = {"quote": {"price": 1162.10, "low": 1160.20, "high": 1181.0}, "range52": {"low": 1160.80, "high": 1550.0}}
    assert C.with_today_range(c)["range52"] == {"low": 1160.20, "high": 1550.0}
    up = {"quote": {"price": 1600.0, "low": 1570.0, "high": 1612.5}, "range52": {"low": 1160.80, "high": 1550.0}}
    assert C.with_today_range(up)["range52"] == {"low": 1160.80, "high": 1612.5}


# ---------- R7T-008: Eni's market value and P/E on the public page's definition ----------
def test_enis_value_and_pe_are_the_public_pages(monkeypatch):
    f = {"region": "US", "symbol": "E", "price": 55.62, "price_at": "2026-10-08", "market_cap": 87_500.0, "pe": 29.9,
         "eps": 1.86, "pe_basis": "year", "pe_end": "2025-12-31", "sales_usd": 96_000.0, "unit": "EUR million"}
    monkeypatch.setattr(research_routes, "public_facts", lambda r, s: f)
    # the app's page before: the fundamentals' own P/E (another earnings definition) and its own market value
    c = {"region": "US", "symbol": "E", "quote": {"price": 55.62}, "market_cap": 79_572_642_336.37,
         "metrics": [{"title": "Valuation", "items": [{"label": "P/E", "value": 13.4171, "unit": "x"}]},
                     {"title": "Per share and returns", "items": [{"label": "Beta", "value": -0.3, "unit": "x"}]}]}
    out = research_routes.with_public_eps("US", c)
    pe = items(out)["P/E"]
    assert out["market_cap"] == pytest.approx(87_500.0 * 1e6) and pe["value"] == round(55.62 / 1.86, 2)
    assert "year to Dec 2025" in pe["note"] and "EPS TTM" not in items(out)      # per-share money stays off an ADR's page
    # a public value that fails its checks is n/a in the app too, not the other definition's
    monkeypatch.setattr(research_routes, "public_facts", lambda r, s: {**f, "cap_unverified": True})
    assert research_routes.with_public_eps("US", c)["market_cap"] is None


# ---------- R7T-002: the chain's counts are contracts ----------
def nifty_chain(ce_23000: int) -> list[list]:
    rows = FP.chain(23000.0, 0.12, "2026-10-13", datetime(2026, 10, 9, 9, 41, tzinfo=IST))
    for r in rows:
        if r[0] == 23000:
            r[4] = ce_23000
    return rows


def test_chain_open_interest_is_in_lots_as_the_exchange_counts_it(monkeypatch):
    got = {"expiry": "2026-10-13", "expiries": ["2026-10-13"], "spot": 22950.0, "chain": nifty_chain(14_086_345),
           "taken_at": "2026-10-09T09:41:00+05:30", "source": "live", "at_close": False, "lot": 65}
    before = {"chain": nifty_chain(13_000_000), "lot": 65, "taken_at": "2026-10-08T09:55:00+00:00"}
    monkeypatch.setattr(P, "live_chains", lambda od, names, choice: {n: got for n in names})
    monkeypatch.setattr(P, "recorded_before", lambda n, e, d: before)
    monkeypatch.setattr(P, "chain_coverage", lambda n: {"days": 0, "first": None, "last": None})
    v = P.chain_view(None, "NIFTY", "current", now=OPEN)
    row = next(r for r in v["rows"] if r["strike"] == 23000)
    # the exchange's 216,713 lots at 09:41, not 1.4 crore shares called contracts
    assert v["unit"] == "lots" and v["lot"] == 65 and row["call_oi"] == 216_713
    assert row["call_chg"] == 216_713 - 200_000 and v["top"]["call"] == {"strike": 23000, "oi": 216_713}
    raw = next(r for r in got["chain"] if r[0] == 23000)
    assert row["call_vol"] == round(raw[9] / 65) and row["put_oi"] == round(raw[8] / 65)          # volume too
    # ratios don't change with the unit
    assert v["pcr"]["oi"] == P.pcr(P.near(got["chain"], 22950.0))["oi"]


def test_without_a_lot_the_chain_says_shares():
    assert P.in_lots(14_086_345, None) == 14_086_345 and P.in_lots(14_086_345, 65) == 216_713


# ---------- R7T-005: a chain at the close is the close's recording; one IV and one PCR ----------
def close_recording() -> dict:
    at = datetime(2026, 10, 8, 15, 25, tzinfo=IST)
    return {"taken_at": at.astimezone(UTC).isoformat(), "exchange": "NFO", "name": "NIFTY", "expiry": "2026-10-13",
            "spot": 22231.80, "lot": 65, "chain": FP.chain(22231.80, 0.135, "2026-10-13", at, seed=8)}


def test_a_chain_at_the_close_uses_the_spot_recorded_with_it(monkeypatch):
    rec = close_recording()
    monkeypatch.setattr(P, "recorded_last", lambda name, day: [rec] if day == date(2026, 10, 8) else [])
    live = {"expiry": "2026-10-13", "expiries": ["2026-10-13"], "spot": 22314.95, "chain": FP.chain(22314.95, 0.14, "2026-10-13", PRE_OPEN),
            "taken_at": "2026-10-08T15:30:00+05:30", "source": "live", "at_close": True, "lot": 65}
    got = P.at_the_close("NIFTY", live, {"ltp": 22314.95, "close": 22231.80})
    assert got["spot"] == 22231.80 and got["chain"] is rec["chain"] and got["at_close"]
    # no recording of that close: the index's own close, not the pre-open level
    monkeypatch.setattr(P, "recorded_last", lambda name, day: [])
    monkeypatch.setattr(P, "ist_now", lambda: PRE_OPEN)
    assert P.at_the_close("NIFTY", live, {"ltp": 22314.95, "close": 22231.80})["spot"] == 22231.80


def test_the_vix_card_the_chain_panel_the_pcr_table_and_the_history_agree(monkeypatch):
    rec = close_recording()
    monkeypatch.setattr(P, "recorded_last", lambda name, day: [rec] if day == date(2026, 10, 8) else [])
    live = {"expiry": "2026-10-13", "expiries": ["2026-10-13"], "spot": 22314.95, "chain": rec["chain"],
            "taken_at": "2026-10-08T15:30:00+05:30", "source": "live", "at_close": True, "lot": 65}
    closed = P.at_the_close("NIFTY", live, None)
    monkeypatch.setattr(P, "live_chains", lambda od, names, choice: {n: closed for n in names})
    monkeypatch.setattr(P, "recorded_before", lambda n, e, d: None)
    monkeypatch.setattr(P, "chain_coverage", lambda n: {"days": 1, "first": "2026-10-08", "last": "2026-10-08"})
    monkeypatch.setattr(P, "chain_series", lambda n, since=None: [])
    day = P.summarise_day("NIFTY", date(2026, 10, 8))["x"]["2026-10-13"]           # what the history keeps for 8 Oct
    panel = P.chain_view(None, "NIFTY", "current", now=PRE_OPEN)
    table = P.pcr_table(None, now=PRE_OPEN, names=("NIFTY",))[0]
    card = vix.nifty_iv(None, PRE_OPEN)["today"]
    assert panel["spot"] == day["spot"] == 22231.80
    assert panel["atm_iv"] == day["atm_iv"] == card["iv"]
    assert panel["pcr"]["oi"] == day["pcr_near"] == table["pcr_oi"]


# ---------- R7T-003: SENSEX from the broker, a previous session never "today", no mood on stale levels ----------
class StubKite:
    def __init__(self, quotes: dict, candles: list | None = None):
        self.quotes, self.candles, self.ttls = quotes, candles or [], []

    def ready(self):
        return True

    def index_quotes(self, keys):
        return {k: self.quotes[k] for k in keys if k in self.quotes}

    def index_token(self, key):
        return 265 if key == "BSE:SENSEX" else None

    def by_symbol(self, sym, ex="NSE"):
        return {"token": 256265} if (ex, sym) == ("NSE", "NIFTY 50") else None

    def equity(self, sym):
        return {"token": 738561, "symbol": sym} if sym == "RELIANCE" else None

    def history(self, token, tf, days, ttl=None, **kw):
        self.ttls.append(ttl)
        return list(self.candles)

    def quote(self, syms):
        return {s: self.quotes.get(s) for s in syms}


class StubYahoo:
    def __init__(self, metas: dict):
        self.metas = metas

    def meta(self, sym):
        return dict(self.metas[sym])


def frozen_yahoo() -> StubYahoo:
    """The other source on 9 Oct: SENSEX still at the 8 Oct close and change."""
    eight = "2026-10-08T15:30:00+05:30"
    return StubYahoo({"^NSEI": {"price": 22430.1, "change_pct": 0.9, "high52": 26277.0, "at": "2026-10-09T09:38:00+05:30"},
                      "^BSESN": {"price": 71593.24, "change_pct": -1.44, "high52": 85978.0, "at": eight},
                      "^NSEBANK": {"price": 55010.0, "change_pct": 0.7, "high52": 57600.0, "at": "2026-10-09T09:38:00+05:30"}})


def test_an_index_still_at_yesterdays_level_after_the_open_is_stale_never_today():
    eight = {"price": 71593.24, "change_pct": -1.44, "at": "2026-10-08T15:30:00+05:30"}
    after = C.index_level("SENSEX", eight, "IN", OPEN)
    assert after["stale"] and not after["live"] and after["day"] == "2026-10-08"
    before = C.index_level("SENSEX", eight, "IN", EARLY)            # before the open: 8 Oct's close, not stale
    assert not before["stale"] and not before["live"]
    now = C.index_level("SENSEX", {"price": 72115.0, "change_pct": 0.73, "at": "2026-10-09T09:39:00+05:30"}, "IN", OPEN)
    assert now["live"] and not now["stale"]


def test_sensex_is_read_from_the_broker_like_nifty():
    k = StubKite({"NSE:NIFTY 50": {"price": 22431.0, "change_pct": 0.9, "at": "2026-10-09T09:39:00+05:30"},
                  "BSE:SENSEX": {"price": 72115.0, "change_pct": 0.73, "high": 72200.0, "low": 71700.0, "at": "2026-10-09T09:39:00+05:30"},
                  "NSE:NIFTY BANK": {"price": 55020.0, "change_pct": 0.72, "at": "2026-10-09T09:39:00+05:30"}})
    hub = C.Research(k, finnhub=SimpleNamespace(ready=lambda: False), yahoo=frozen_yahoo())
    got = {i["name"]: i for i in hub.indices("IN", now=OPEN)}
    assert got["SENSEX"]["price"] == 72115.0 and got["SENSEX"]["change_pct"] == 0.73 and got["SENSEX"]["live"]
    assert got["SENSEX"]["high52"] == 85978.0 and not any(i["stale"] for i in got.values())
    # the broker offline: the other source's level, marked as the previous session's
    k.quotes = {}
    got = {i["name"]: i for i in hub.indices("IN", now=OPEN)}
    assert got["SENSEX"]["price"] == 71593.24 and got["SENSEX"]["stale"]


def test_no_mood_is_written_while_an_index_is_stale(monkeypatch):
    stale = [{"name": "NIFTY 50", "price": 22430.1, "change_pct": 0.9, "day": "2026-10-09", "live": True, "stale": False},
             {"name": "SENSEX", "price": 71593.24, "change_pct": -1.44, "day": "2026-10-08", "live": False, "stale": True}]
    calls = []
    monkeypatch.setattr(research_routes, "hub", SimpleNamespace(indices=lambda r: stale, headlines=lambda r, f: calls.append(1) or []))
    monkeypatch.setattr(research_routes.A, "pulse", lambda *a, **k: pytest.fail("no mood on a previous session's level"))
    body = json.loads(research_routes.pulse_ai("IN", "", False, {"id": "u1", "_plan": "pro"}).body)
    assert body["unavailable"] and body["code"] == "stale" and "SENSEX hasn't updated" in body["message"]


def test_a_mood_from_before_the_open_is_written_again_after_it():
    before = [{"name": "SENSEX", "day": "2026-10-08", "change_pct": -1.44}, {"name": "NIFTY 50", "day": "2026-10-08", "change_pct": -1.6}]
    after = [{"name": "SENSEX", "day": "2026-10-09", "change_pct": 0.6}, {"name": "NIFTY 50", "day": "2026-10-09", "change_pct": 0.43}]
    assert research_routes.mood_key(before, False) != research_routes.mood_key(after, True)
    # within the session the same read serves while the moves stay within the same half percent
    later = [{**i, "change_pct": i["change_pct"] + 0.04} for i in after]
    assert research_routes.mood_key(after, True) == research_routes.mood_key(later, True)


def test_the_sensex_chart_has_todays_candle(monkeypatch):
    monkeypatch.setattr(C, "market_open", lambda region, now=None: True)
    monkeypatch.setattr(C, "market_today", lambda region, now=None: "2026-10-09")
    eight = [{"t": "2026-10-08T00:00:00+05:30", "o": 72600.0, "h": 72700.0, "l": 71500.0, "c": 71593.24, "v": 0.0}]
    k = StubKite({"BSE:SENSEX": {"price": 72115.0, "open": 71780.0, "high": 72200.0, "low": 71700.0, "at": "2026-10-09T09:39:00+05:30"}}, eight)
    hub = C.Research(k, finnhub=SimpleNamespace(ready=lambda: False), yahoo=frozen_yahoo())
    got = hub.chart("IN", "^BSESN", "1m", "1d")
    assert got["source"] == "Kite" and len(got["candles"]) == 2
    assert got["candles"][-1] == {"t": "2026-10-09T00:00:00+05:30", "o": 71780.0, "h": 72200.0, "l": 71700.0, "c": 72115.0, "v": 0.0}
    assert k.ttls == [60]                                         # read within the minute while the session trades


# ---------- R7T-006: a company's 1Y daily chart re-read within the minute in market hours ----------
def test_the_daily_chart_is_never_a_copy_from_before_the_open(monkeypatch):
    today = [{"t": "2026-10-09T00:00:00+05:30", "o": 1178.0, "h": 1181.0, "l": 1160.2, "c": 1165.0, "v": 1.0}]
    k = StubKite({}, today)
    hub = C.Research(k, finnhub=SimpleNamespace(ready=lambda: False), yahoo=frozen_yahoo())
    monkeypatch.setattr(C, "market_open", lambda region, now=None: True)
    monkeypatch.setattr(C, "market_today", lambda region, now=None: "2026-10-09")
    hub.chart("IN", "RELIANCE", "1y", "1d")
    monkeypatch.setattr(C, "market_open", lambda region, now=None: False)
    hub.chart("IN", "RELIANCE", "1y", "1d")
    assert k.ttls == [60, None]                                   # out of hours the usual copy serves


# ---------- R7T-004: the pre-open price is never the last close ----------
def test_a_price_before_0915_is_the_pre_open_price():
    q = {"quote": {"price": 1179.0, "change": 1.0, "at": "2026-10-09T09:09:49+05:30"}}
    assert research_routes.price_phase("IN", q, PRE_OPEN) == "pre_open"
    assert research_routes.price_phase("IN", q, OPEN) is None                       # trading: the live price
    yesterday = {"quote": {"price": 1178.0, "at": "2026-10-08T15:29:59+05:30"}}
    assert research_routes.price_phase("IN", yesterday, PRE_OPEN) is None           # before the auction: the close
    assert research_routes.price_phase("US", q, PRE_OPEN) is None


# ---------- R7T-009: the email is the stored issue, and no advice-worded headline ----------
def test_the_email_is_written_from_the_stored_issue_the_page_shows(monkeypatch):
    issue = {"id": "market.US.2026-10-08", "kind": "market", "region": "US", "day": "2026-10-08", "weekly": False,
             "subject": "US Market Brief · Thu 8 Oct", "title": "US Market Brief", "label": "Market brief · United States",
             "summary": "U.S. equity indices were mixed on Tuesday.", "sections": [], "indices": [], "at": "2026-10-09T02:04+05:30"}
    issue["html"], issue["text"] = write.render(issue)
    issue["summary"] = "U.S. equity indices were mixed on Thursday."       # the stored issue, repaired after it was built
    html, text = news_job.email_of(issue)
    assert "Thursday" in html and "Thursday" in text and "Tuesday" not in html + text
    sent = []
    monkeypatch.setattr(news_job, "address", lambda p: "owner@example.com")
    monkeypatch.setattr(news_job, "confirmed", lambda p: True)
    monkeypatch.setattr(news_job.alerts, "email_ready", lambda: True)
    monkeypatch.setattr(news_job.kit, "finish", lambda h, t, uid, what: (h, t, None))
    monkeypatch.setattr(news_job.alerts, "send_email", lambda to, subject, text, html=None, headers=None: sent.append((text, html)))
    assert news_job.deliver_why({"id": "u1"}, issue, "market_us", teaser_too=False) == "sent"
    assert "Thursday" in sent[0][0] and "Thursday" in sent[0][1] and "Tuesday" not in sent[0][0]
    assert main.news_view(issue)["html"].count("Thursday") >= 1


@pytest.mark.parametrize("title", [
    "We’re adding to our position in a hard-hit stock before important catalysts arrive",
    "We’re buying the dip in a stock that just reported",
    "We're trimming a winner after its big run",
])
def test_advice_worded_headlines_are_dropped_whatever_the_apostrophe(title):
    assert not N.plain_headline(title)
    assert N.plain_headline("Mastercard rises 0.8% as payments stocks gain")


# ---------- R7T-010: the Invest home's breadth card is live while the market trades ----------
def test_the_home_cards_breadth_has_the_live_point(monkeypatch):
    pts = [["09:15", 179, 63, 8, 100, 250, 120, 250, 140, 250, 23000.0], ["09:30", 136, 108, 6, 98, 250, 118, 250, 139, 250, 23010.0]]
    live = {"state": "live", "day": "2026-10-09", "fields": list(breadth_live.FIELDS), "points": pts, "as_of": "09:30", "latest": {"adv": 136},
            "message": None, "every_minutes": 15}
    monkeypatch.setattr(breadth, "view", lambda g, r, full, brief: {"group": {"id": g}, "today": None})
    monkeypatch.setattr(breadth_live, "view", lambda g, ready=True: live)
    out = json.loads(main.market_breadth("smallcap250", "1y", True, {"id": "u1", "_plan": "free"}).body)
    assert out["live"]["state"] == "live" and out["live"]["points"] == [pts[-1]] and out["live"]["latest"]["adv"] == 136


# ---------- R7T-012: options sessions count as running ----------
def test_admin_counts_options_sessions_as_running():
    sessions = [SimpleNamespace(polled=True, kind="options"), SimpleNamespace(polled=False), SimpleNamespace(polled=True)]
    assert main.session_counts(sessions) == {"india_sessions": 1, "options_sessions": 1}


# ---------- R7T-013: the next entry after a stop-out ----------
def test_after_a_stop_out_the_session_says_when_it_may_enter_again():
    t = SimpleNamespace(entry="09:30", lastEntry="14:45", cooldown=120)
    assert next_entry("2026-10-09T11:41:00+05:30", t) == "11:41"
    assert next_entry_note("2026-10-09T11:41:00+05:30", t) == "Next entry from 11:41: entries are 120 minutes apart."
    assert next_entry("2026-10-09T15:00:00+05:30", t) is None and "next market day" in next_entry_note("2026-10-09T15:00:00+05:30", t)
    assert next_entry(None, t) is None


# ---------- R7T-014: the alert's level and price have the same places ----------
def test_an_alerts_price_has_the_levels_places():
    a = {"kind": "price", "op": "above", "value": 258.90, "region": "IN", "symbol": "ITC", "state": {"side": "below"}}
    text, _ = SA.evaluate(a, {"price": 259.0, "today": "2026-10-09", "tz": "Asia/Kolkata"})
    assert text == "ITC crossed above ₹258.90 (now ₹259.00)"
    assert SA.money(3000.0, "IN", 3012.0) == "₹3,000" and SA.money(259.0, "IN") == "₹259"


def test_tests_here_never_read_the_clock():
    # every instant above is fixed and zoned; a guard that this file keeps to it
    src = open(__file__, encoding="utf-8").read()
    assert "datetime.now(" not in src.replace('"datetime.now("', "") and "date.today(" not in src.replace('"date.today("', "")
    assert timedelta(minutes=120) == timedelta(hours=2)
