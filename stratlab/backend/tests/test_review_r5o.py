"""Round 5, the owner's review: database reconnects (R5O-002) and the other fixes in this round that are pure backend."""
import socket
import threading

import httpx
import pytest

from app import db


# ---------- R5O-002: the database connection drops ----------
class Flaky(httpx.BaseTransport):
    """Fails the first `fail` requests with `exc`, then answers 200."""

    def __init__(self, exc, fail=1):
        self.exc, self.fail, self.calls = exc, fail, []

    def handle_request(self, request):
        self.calls.append(request.method)
        if len(self.calls) <= self.fail:
            raise self.exc("Server disconnected without sending a response.", request=request)
        return httpx.Response(200, json=[{"id": 1}])


def test_a_read_is_tried_once_more_when_the_connection_drops():
    inner = Flaky(httpx.RemoteProtocolError)
    with httpx.Client(transport=db.RetryReads(inner)) as c:
        r = c.get("https://db.example/rest/v1/profiles")
    assert r.json() == [{"id": 1}] and inner.calls == ["GET", "GET"]


def test_a_read_fails_after_one_retry_not_forever():
    inner = Flaky(httpx.RemoteProtocolError, fail=5)
    with httpx.Client(transport=db.RetryReads(inner)) as c, pytest.raises(httpx.RemoteProtocolError):
        c.get("https://db.example/rest/v1/profiles")
    assert inner.calls == ["GET", "GET"]


def test_a_write_is_not_sent_twice_when_it_may_have_landed():
    inner = Flaky(httpx.RemoteProtocolError)
    with httpx.Client(transport=db.RetryReads(inner)) as c, pytest.raises(httpx.RemoteProtocolError):
        c.post("https://db.example/rest/v1/usage_events", json={"kind": "x"})
    assert inner.calls == ["POST"]


def test_a_write_that_never_left_is_sent_again():
    inner = Flaky(httpx.ConnectError)
    with httpx.Client(transport=db.RetryReads(inner)) as c:
        r = c.post("https://db.example/rest/v1/usage_events", json={"kind": "x"})
    assert r.status_code == 200 and inner.calls == ["POST", "POST"]


def test_the_database_client_uses_a_pool_of_http1_connections(monkeypatch):
    """HTTP/2 shared by every thread raised KeyError: 819 (a stream number) in count_usage and "Server disconnected"
    for every request in flight; the client is HTTP/1.1 with the retrying transport."""
    monkeypatch.setattr(db, "_client", None)
    monkeypatch.setattr(db.settings, "SUPABASE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(db.settings, "SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
    c = db.sb()
    try:
        session = c.postgrest.session
        assert isinstance(session._transport, db.RetryReads)
        pool = session._transport.inner._pool
        assert pool._http2 is False and pool._http1 is True
    finally:
        monkeypatch.setattr(db, "_client", None)


def _server(replies):
    """A one-thread HTTP server on localhost: the first connection is closed without an answer, the rest answer."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(8)
    seen = []

    def run():
        while True:
            try:
                conn, _ = s.accept()
            except OSError:
                return
            with conn:
                data = conn.recv(65536)
                if not data:
                    continue
                seen.append(data.split(b"\r\n", 1)[0].decode())
                if len(seen) <= replies.get("drop", 0):
                    continue            # close without a word: "Server disconnected without sending a response"
                body = b'[{"id": 7}]'
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Range: 0-0/3\r\n"
                             b"Connection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    threading.Thread(target=run, daemon=True).start()
    return s, seen


def test_a_real_count_survives_a_dropped_connection(monkeypatch):
    srv, seen = _server({"drop": 1})
    try:
        monkeypatch.setattr(db, "_client", None)
        monkeypatch.setattr(db, "RETRY_PAUSE", 0.0)
        monkeypatch.setattr(db.settings, "SUPABASE_URL", f"http://127.0.0.1:{srv.getsockname()[1]}")
        monkeypatch.setattr(db.settings, "SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
        assert db.count_usage("u1", "backtest", "2026-10-01T00:00:00+00:00") == 3
        assert len(seen) == 2 and all(x.startswith("GET /rest/v1/usage_events") for x in seen)
    finally:
        srv.close()
        monkeypatch.setattr(db, "_client", None)


def test_admin_sessions_lists_an_options_session_with_its_market():
    """'OptionSession' object has no attribute 'market' (25 Sep): the session carries its market now."""
    from app.options.session import OptionSession
    src = OptionSession.__init__.__code__.co_names
    assert "market" in src


# ---------- R5O-008: the theme map's tickers ----------
LISTED_IN = [{"symbol": "BHARTIARTL", "name": "BHARTI AIRTEL"}, {"symbol": "BHEL", "name": "BHARAT HEAVY ELECTRICALS"},
             {"symbol": "BEL", "name": "BHARAT ELECTRONICS"}, {"symbol": "MAZDOCK", "name": "MAZAGON DOCK SHIPBUILDERS"},
             {"symbol": "HAL", "name": "HINDUSTAN AERONAUTICS"}, {"symbol": "TATAELXSI", "name": "TATA ELXSI"},
             {"symbol": "MODEFENCE", "name": "MOTILAL OSWAL NIFTY INDIA DEFENCE ETF"},
             {"symbol": "SOLARINDS", "name": "SOLAR INDUSTRIES (I) LTD"}]


def fake_lookup(q, region):
    """A stand-in for the market's list: the exact symbol, else names with the first two words typed."""
    from app.intel.grounding import _words, _same_word
    exact = [r for r in LISTED_IN if r["symbol"] == q.upper()]
    if exact:
        return exact
    want = _words(q)
    return [r for r in LISTED_IN if want and all(any(_same_word(w, x) for x in _words(r["name"])) for w in want[:2])]


def test_names_agree():
    from app.intel.grounding import names_agree
    assert names_agree("Bharat Heavy Electricals Ltd", "BHARAT HEAVY ELECTRICALS")
    assert names_agree("Solar Industries India", "SOLAR INDUSTRIES (I) LTD")
    assert names_agree("Tata Consultancy Services", "TATA CONSULTANCY SERV LT")
    assert names_agree("Vertiv", "Vertiv Holdings Co")
    assert not names_agree("Bharat Heavy Electricals Ltd", "BHARTI AIRTEL")
    assert not names_agree("Bharat Heavy Electricals", "BHARAT ELECTRONICS")
    assert not names_agree("Tata Advanced Systems", "TATA ELXSI")
    assert not names_agree("Hindustan Aeronautics", "HINDUSTAN UNILEVER")


def test_theme_tickers_are_checked_against_the_list():
    from app.intel.grounding import ground_sector
    ai = {"screen": [{"name": "Bharat Heavy Electricals Ltd", "ticker": "BHARTIARTL", "layer": "OEM"},
                     {"name": "Mazagon Dock Shipbuilders", "ticker": "MDSL", "layer": "Shipyards"},
                     {"name": "Tata Advanced Systems", "ticker": "TATASYS", "layer": "Private OEM"},
                     {"name": "Hindustan Aeronautics", "ticker": "HAL", "layer": "Aircraft"}],
          "clusters": [{"name": "State-owned OEMs", "companies": [
              {"name": "Bharat Heavy Electricals Ltd", "ticker": "BHARTIARTL"}, {"name": "Tata Advanced Systems", "ticker": "TATASYS"},
              {"name": "Antrix", "ticker": ""}, {"name": "Bharat Electronics", "ticker": "BEL"}]}],
          "value_chain": [{"layer": "Ships", "companies": [{"name": "Mazagon Dock", "ticker": "MDSL"}]}],
          "etfs": [{"ticker": "NIFTYDEF", "name": "Nifty India Defence ETF"}, {"ticker": "INDDEF", "name": "India Defence Fund"},
                   {"ticker": "MODEFENCE", "name": "Motilal Oswal Nifty India Defence ETF"}]}
    out = ground_sector(ai, "IN", fake_lookup)
    assert [(s["ticker"], s["name"]) for s in out["screen"]] == [
        ("BHEL", "Bharat Heavy Electricals Ltd"), ("MAZDOCK", "Mazagon Dock Shipbuilders"), ("HAL", "Hindustan Aeronautics")]
    cos = out["clusters"][0]["companies"]
    assert [(c["name"], c["ticker"], c["listed"]) for c in cos] == [
        ("Bharat Heavy Electricals Ltd", "BHEL", True), ("Tata Advanced Systems", "", False), ("Antrix", "", False),
        ("Bharat Electronics", "BEL", True)]
    assert out["value_chain"][0]["companies"][0]["ticker"] == "MAZDOCK"
    assert out["etfs"] == [{"ticker": "MODEFENCE", "name": "MOTILAL OSWAL NIFTY INDIA DEFENCE ETF"}]


def test_a_theme_map_is_grounded_before_it_is_cached():
    """The route runs the check on what the AI wrote, so a cached map never carries an unchecked ticker."""
    from app.intel import routes
    src = open(routes.__file__).read()
    assert "grounding.ground_sector(A.sector(theme, r, _ai), r, hub.search)" in src


def test_when_the_list_is_down_nothing_passes_as_checked():
    from app.intel.grounding import ground_sector

    def down(q, region):
        raise RuntimeError("list down")
    out = ground_sector({"screen": [{"name": "Hindustan Aeronautics", "ticker": "HAL"}], "etfs": [{"ticker": "X", "name": "Y"}]},
                        "IN", down)
    assert out["screen"] == [] and out["etfs"] == []


# ---------- R5O-018: the market read, checked against the index numbers ----------
NIFTY_8_OCT = [{"name": "NIFTY 50", "price": 22231.80, "change_pct": -1.64, "high52": 26400.0, "low52": 22182.55,
                "from_high_pct": -15.79},
               {"name": "SENSEX", "price": 71593.24, "change_pct": -1.44, "high52": 85900.0, "low52": 71000.0, "from_high_pct": -16.7}]
HEADLINES = [{"headline": "Sensex, Nifty fall 1.6% as IT and banking shares slide; RBI raises repo rate to 5.5%"}]


def test_the_market_read_keeps_only_what_the_numbers_and_headlines_support():
    from app.intel.grounding import ground_pulse
    ai = {"tone": ("The NIFTY 50 fell 1.64% to 22,231.80 and the SENSEX lost 1.44%. Selling pushed the indices well below their "
                   "52-week lows, erasing roughly ₹7 lakh crore of market value. Hawkish Fed minutes weighed on sentiment. "
                   "Money rotated into utilities. The RBI raised the repo rate to 5.5%. Markets could rebound next week."),
          "hot": [{"name": "Infosys", "ticker": "INFY", "why": "IT shares slid."}, {"name": "Reliance", "ticker": "RELIANCE", "why": "Jio."}],
          "flows": [{"title": "FII selling", "detail": "Foreign investors sold.", "direction": "OUTFLOW"}],
          "themes": []}
    out = ground_pulse(ai, NIFTY_8_OCT, HEADLINES)
    assert out["tone"] == "The NIFTY 50 fell 1.64% to 22,231.80 and the SENSEX lost 1.44%. The RBI raised the repo rate to 5.5%."
    assert out["hot"] == [] and out["flows"] == []        # no headline names them
    for gone in ("52-week lows", "lakh crore", "Fed", "utilities", "rebound"):
        assert gone not in out["tone"]


def test_a_52_week_claim_must_match_the_levels():
    from app.intel.grounding import range_claims_ok
    assert not range_claims_ok("The indices fell well below their 52-week lows.", NIFTY_8_OCT)
    assert range_claims_ok("The NIFTY 50 closed near its 52-week low.", NIFTY_8_OCT)          # 0.2% above it
    assert not range_claims_ok("The market hit record highs.", NIFTY_8_OCT)
    below = [{**NIFTY_8_OCT[0], "price": 22100.0}]
    assert range_claims_ok("The NIFTY 50 broke below its 52-week low.", below)


def test_when_nothing_survives_the_read_is_the_numbers_alone():
    from app.intel.grounding import ground_pulse
    out = ground_pulse({"tone": "Stocks rallied to record highs on hopes of a Fed cut."}, NIFTY_8_OCT, HEADLINES)
    assert out["tone"].startswith("NIFTY 50 at 22,231.80, −1.64% on the day, 0.2% above its 52-week low and 15.8% below its high.")


def test_the_pulse_gives_the_ai_the_52_week_position_and_checks_its_reply(monkeypatch):
    import json as _json
    from app.intel import ai as A
    seen = {}

    def fake(system, text, **k):
        seen["facts"] = text
        return _json.dumps({"tone": "Indices sank below their 52-week lows. The NIFTY 50 fell 1.64%.", "hot": [], "flows": [], "themes": []})
    monkeypatch.setattr(A, "complete", fake)
    out = A.pulse("IN", "", NIFTY_8_OCT, HEADLINES, (None, None))
    assert out["tone"] == "The NIFTY 50 fell 1.64%." and '"from_low_pct": 0.22' in seen["facts"]


# ---------- R5O-027: the company read, checked against the company's numbers ----------
def test_the_company_read_states_facts_only():
    from datetime import date
    from app.intel.grounding import ground_company
    facts = {"symbol": "AAPL", "price": 336.67, "metrics": {"P/E": 37.98, "200-day average": 290.2}, "range_52w": [190.0, 340.0]}
    read = {"summary": "Apple sells iPhones, Macs and services. Its P/E is 37.98, lower than the typical range of 20-30 for the company.",
            "valuation_note": "The share price is 16% above its 200-day average, indicating limited upside.",
            "bull": ["Services keep growing.", "The stock looks cheap at 37.98 times earnings."], "bear": ["Rivals may pressure margins."],
            "position": "", "watch": ["Q4 FY2025 earnings release"],
            "ideas": [{"title": "Fade overbought", "text": "Sell AAPL short when 14-day RSI exceeds 70, cover when it drops below 50, 3% stop loss", "why": "x"},
                      {"title": "Trend", "text": "Buy AAPL when the 20-day EMA crosses above the 50-day EMA, sell when it crosses back below", "why": "y"}]}
    out = ground_company(read, facts, "US", date(2026, 10, 8))
    assert out["summary"] == "Apple sells iPhones, Macs and services."
    assert out["valuation_note"] == ""                     # "limited upside" is a forecast; 16% isn't in the facts either
    assert out["bull"] == ["Services keep growing."] and out["bear"] == []
    texts = [i["text"] for i in out["ideas"]]
    assert texts[0] == "Enter short when 14-day RSI exceeds 70, cover when it drops below 50, 3% stop loss"
    assert texts[1] == "Enter long when the 20-day EMA crosses above the 50-day EMA, exit when it crosses back below"
    assert not any("AAPL" in t or t.lower().startswith(("sell", "buy")) for t in texts)


def test_indian_fiscal_quarter_labels_follow_the_calendar():
    from datetime import date
    from app.intel.grounding import fiscal_quarter, fix_fiscal_labels, ground_company
    assert fiscal_quarter(date(2026, 10, 8), "IN") == (2, 2027)
    assert fiscal_quarter(date(2027, 2, 1), "IN") == (3, 2027)
    assert fiscal_quarter(date(2026, 5, 1), "IN") == (4, 2026)
    assert fix_fiscal_labels("Q2 FY2026 earnings release", date(2026, 10, 8), "IN") == "Q2 FY2027 earnings release"
    assert fix_fiscal_labels("Q1 FY27 results", date(2026, 10, 8), "IN") == "Q1 FY2027 results"
    out = ground_company({"summary": "Revenue grew in Q3 FY26.", "watch": ["Q2 FY2026 earnings release"]}, {"symbol": "TCS"}, "IN", date(2026, 10, 8))
    assert out["watch"] == ["Q2 FY2027 earnings release"] and out["summary"] == "Revenue grew in Q3 FY26."   # the past stays


def test_company_profiles_lose_scrape_residue():
    from app.intel.screener import clean_profile
    raw = ("Tata Consultancy Services is an IT services, consulting and business solutions company.[1] "
           "[1] Revenue Breakup Q3FY26 [1] BFSI : 31.9% Manufacturing : 8.4%")
    assert clean_profile(raw) == "Tata Consultancy Services is an IT services, consulting and business solutions company."


# ---------- R5O-023: the scan page ----------
def test_a_live_scan_says_last_price_not_closed_at():
    import numpy as np
    from app import scan_presets
    from tests.test_scan_presets import bars
    closes = list(np.concatenate([np.linspace(150, 100, 260), [100.0] * 5]))
    b = bars(closes + [min(closes[-253:]) * 1.03])
    live = scan_presets.evaluate(b, only=["near_low52"], live=True)["matches"]["near_low52"]["detail"]
    stored = scan_presets.evaluate(b, only=["near_low52"])["matches"]["near_low52"]["detail"]
    assert live.startswith("Last price ") and stored.startswith("Closed at ")


def test_a_skipped_stock_is_named_by_its_symbol_and_counted():
    from app import scan

    class Prov:
        def instrument(self, token):
            return {"symbol": "SIMPLXREA", "name": "Simplex Realty"} if token == "195818241" else None

    class Reg:
        def provider(self, market):
            return Prov()

        def resolve(self, iid):
            return Prov(), {"id": iid}
    import app.universes as U
    orig_resolve, orig_bars = U.resolve, scan._bars
    try:
        U.resolve = lambda reg, market, members: (["IN:195818241"], [])
        scan._bars = lambda reg, iid: [{"t": "2026-10-08", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}] * 3
        out = scan.run_preset(Reg(), "IN", [{"symbol": "SIMPLXREA"}], "near_low52")
    finally:
        U.resolve, scan._bars = orig_resolve, orig_bars
    assert out["problems"] == ["SIMPLXREA: not enough daily prices yet"] and out["checked"] == 0 and out["asked"] == 1


# ---------- R5O-020: no provider names; a US company's own news and peers ----------
def test_us_peers_start_with_companies_of_its_size_in_its_sector():
    from app.intel.company import us_peers
    got = us_peers("AAPL", ["DELL", "SNDK", "WDC", "HPE", "NTAP", "SMCI", "HPQ", "NOTREAL"])
    assert got[:3] == ["MSFT", "NVDA", "AVGO"] and "NOTREAL" not in got and len(got) == 8


def test_a_providers_news_page_is_not_shown_as_the_publisher():
    from app.branding import public_research
    out = public_research({"news": [{"headline": "Apple unveils", "source": "Yahoo"}, {"headline": "x", "source": "Reuters"}]})
    assert [n["source"] for n in out["news"]] == [None, "Reuters"]


def test_us_company_news_is_about_the_company():
    from app.intel.news import mentions
    assert mentions("Apple Inc", "AAPL", "Apple's iPhone 18 sales rise in China")
    assert not mentions("Apple Inc", "AAPL", "Dow futures slip ahead of jobs data")
    assert not mentions("Apple Inc", "AAPL", "OneKey launches a new hardware wallet")
    src = open(__import__("app.intel.company", fromlist=["x"]).__file__).read()
    assert 'mentions(p["name"], sym, n["headline"])' in src


# ---------- R5O-031: the owner's Zerodha holdings, on the data login's token ----------
from tests.test_connect import ADMIN, FakeKite, kite, kite_login, on   # noqa: E402,F401  (fixtures)


def _data_login(monkeypatch, user="AB1234"):
    from app.kite_service import today_ist
    monkeypatch.setattr(db.settings, "KITE_USER_ID", user)
    db.set_setting("kite_access_token", "DATA-TOKEN-TODAY")
    db.set_setting("kite_token_day", today_ist())


def test_the_owners_holdings_follow_the_data_login_without_a_daily_login(w, kite, monkeypatch):
    from app.connect import jobs, kite_user, state, vault
    c = w["client"]
    kite_login(c)                                       # connected yesterday, as Zerodha user AB1234
    state.update("u-admin", "kite", day="2020-01-01", refreshed_at="2020-01-01T09:00:00+00:00")
    assert c.post("/connect/kite/refresh", headers=ADMIN).status_code == 409        # no data login today: log in again
    _data_login(monkeypatch)
    v = c.get("/connect", headers=ADMIN).json()["kite"]
    assert v["live"] and not v["expired"]
    from datetime import datetime
    from app.kite_service import IST
    assert jobs.kite_user.run_daily(datetime.now(IST).replace(hour=10, minute=0)) == 1
    box = state.section("u-admin", "kite")
    assert vault.unseal(box["token"]) == "DATA-TOKEN-TODAY" and box["status"] == "ok"
    assert kite_user.run_daily(datetime.now(IST).replace(hour=11)) == 0          # once a day


def test_another_zerodha_account_still_logs_in_itself(w, kite, monkeypatch):
    from app.connect import state
    c = w["client"]
    kite_login(c)
    state.update("u-admin", "kite", day="2020-01-01")
    _data_login(monkeypatch, user="ZZ9999")             # the data login is a different Zerodha account
    assert c.post("/connect/kite/refresh", headers=ADMIN).status_code == 409


def test_the_owner_connecting_shares_the_data_login_instead_of_cancelling_it(w, kite, monkeypatch):
    from app.connect import state
    _data_login(monkeypatch)
    r = w["client"].get("/connect/kite/login", headers=ADMIN).json()
    assert r["shared"] is True and r["url"] == "https://site.example/settings?kite=ok#accounts"
    assert not [x for x in FakeKite.log if x[0] == "session"]                        # no second Zerodha login
    assert state.section("u-admin", "kite")["status"] == "ok"


# ---------- R5O-025: slow pages ----------
def test_a_daily_candles_time_is_its_day_not_midnight():
    from app.main import candle_day
    assert candle_day("2026-10-08T00:00:00+05:30") == "2026-10-08"
    assert candle_day("2026-10-08") == "2026-10-08"
    assert candle_day("2026-10-08T15:29:00+05:30") == "2026-10-08T15:29:00+05:30"
    assert candle_day(None) is None


def test_a_sector_of_business_updates_is_read_in_one_database_call(monkeypatch):
    from app import biz_updates as B
    reads, batches = [], []
    monkeypatch.setattr(B._cache, "get", lambda k: None)
    monkeypatch.setattr(B._cache, "set", lambda *a, **k: None)
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: batches.append(list(keys)))
    monkeypatch.setattr(db, "get_setting", lambda k: reads.append(k) or None)
    sector = next(iter(B.SECTORS))
    B.sector_view(sector)
    assert len(batches) == 1 and len(batches[0]) == len(B.SECTORS[sector]["symbols"])


def test_holders_page_opens_on_the_kept_count_and_builds_the_index_behind(monkeypatch):
    from app import shareholders as S
    store = {S.COVERAGE_KEY: '{"companies": 1840, "latest_quarter": "2026-06-30"}'}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(S._cache, "get", lambda k: None)
    built = []
    monkeypatch.setattr(S, "_build_behind", lambda: built.append(1))
    monkeypatch.setattr(S, "_index", lambda: (_ for _ in ()).throw(AssertionError("no full read on opening")))
    assert S.coverage() == {"companies": 1840, "latest_quarter": "2026-06-30", "queued": 0} and built == [1]


def test_a_fresh_recording_answers_while_the_live_chain_is_read(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import positioning as P
    now = datetime.now(timezone.utc)
    rec = {"expiry": "2026-10-13", "expiries": ["2026-10-13"], "spot": 22200, "chain": [], "source": "recorded",
           "taken_at": (now - timedelta(minutes=2)).isoformat()}
    monkeypatch.setattr(P, "recorded_last", lambda name, day: [rec])
    monkeypatch.setattr(P, "recorded_chain", lambda name, choice, day: rec)
    assert P._fresh_recording("NIFTY", "current") is rec
    old = {**rec, "taken_at": (now - timedelta(minutes=30)).isoformat()}
    monkeypatch.setattr(P, "recorded_chain", lambda name, choice, day: old)
    assert P._fresh_recording("NIFTY", "current") is None


def test_the_deep_dive_reads_its_sources_side_by_side():
    from app import main
    src = open(main.__file__).read()
    assert '_deep_pool.submit(filings_feed.announcements, sym' in src and '_deep_pool.submit(price_status, sym)' in src


# ---------- R5O-016: a job's last run survives a restart ----------
def test_a_jobs_last_run_is_shown_after_a_restart(monkeypatch):
    from app import job_status
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(job_status, "_written", {})

    class Job:
        status = {"last_run": "2026-10-08T03:00:00+00:00", "last_error": None, "problems": []}
    job_status.keep("positioning", Job())
    after_restart = {"last_run": None, "last_error": None, "problems": []}
    got = job_status.kept("positioning", after_restart)
    assert got["last_run"] == "2026-10-08T03:00:00+00:00" and got["before_restart"] is True
    assert job_status.kept("never-ran", after_restart) == after_restart


def test_the_news_jobs_keep_their_status_when_they_mark_a_run():
    from app import main  # noqa: F401  (the jobs import each other through the app, as when it starts)
    from app import etf_nav, fo_changes, market_events, positioning, surveillance, vix
    keys_ = {m.Job.status_key for m in (etf_nav, fo_changes, market_events, positioning, surveillance, vix)}
    assert keys_ == {"etf", "fo", "events", "positioning", "surveillance", "vix"}
    src = open(__import__("app.admin_jobs", fromlist=["x"]).__file__).read()
    for k in keys_ | {"corp", "results", "closing-auction"}:
        assert f'"{k}")' in src, k


# ---------- R5O-014: the library's cards beside buy and hold ----------
def test_library_entries_carry_their_return_beside_buy_and_hold():
    from app import library
    e = {"stats": {"ret": 55.8, "buy_hold": 172.9, "trades": 40}, "verdict": {"verdict": "edge", "checks": []}}
    assert library.public(e)["vs_hold"] == {"ret": 55.8, "hold": 172.9, "gap": -117.1}
    assert library.public({**e, "stats": {**e["stats"], "trades": 0}})["vs_hold"] is None       # never traded: nothing to compare
    assert library.public({**e, "stats": {"ret": 5.0, "buy_hold": None, "trades": 20}})["vs_hold"] is None


# ---------- R5O-010: notebook defaults ----------
@pytest.fixture
def w(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_the_questions_about_an_idea_stay_with_the_notebook(w):
    c, h = w["client"], w["headers"]("pro-token")
    gaps = {"mentioned": ["sl"], "notes": [], "instName": None, "usedAI": True, "fallback": ""}
    strat = {"name": "EMA", "entry": [{"l": {"t": "ema", "p": 20}, "op": "xa", "r": {"t": "ema", "p": 50}}], "risk": {"sl": 2, "tgt": 0}}
    nb = c.post("/notebooks", headers=h, json={"name": "EMA", "strategy": strat, "gaps": gaps}).json()
    assert c.get(f"/notebooks/{nb['id']}", headers=h).json()["gaps"]["mentioned"] == ["sl"]
    # an answer is kept: the person leaves and comes back to the same place
    r = c.put(f"/notebooks/{nb['id']}", headers=h, json={"gaps": {**gaps, "answered": {"exit": "Sell when EMA 20 drops below EMA 50"}}})
    assert r.status_code == 200
    back = c.get(f"/notebooks/{nb['id']}", headers=h).json()
    assert back["gaps"]["answered"] == {"exit": "Sell when EMA 20 drops below EMA 50"}
    assert back["strategy"]["risk"]["tgt"] == 0          # no target was asked for, none is stored
    # an unrelated save keeps them; "Close" clears them
    c.put(f"/notebooks/{nb['id']}", headers=h, json={"notes": "x"})
    assert c.get(f"/notebooks/{nb['id']}", headers=h).json()["gaps"]["mentioned"] == ["sl"]
    c.put(f"/notebooks/{nb['id']}", headers=h, json={"clearGaps": True})
    assert not c.get(f"/notebooks/{nb['id']}", headers=h).json().get("gaps")


def test_gaps_are_bounded(w):
    c, h = w["client"], w["headers"]("pro-token")
    nb = c.post("/notebooks", headers=h, json={"name": "X"}).json()
    r = c.put(f"/notebooks/{nb['id']}", headers=h, json={"gaps": {"mentioned": ["x" * 50]}})
    assert r.status_code == 422


def test_the_ai_builders_internal_notes_are_not_shown():
    from app.ai_writer import user_note
    assert not user_note("No timeframe specified, left as null.")
    assert not user_note("Timeframe not specified; defaulted to daily.")
    assert not user_note("No stop loss was given.")
    assert not user_note("The user did not mention an exit.")
    assert user_note("Option legs can't be tested here, so the straddle part was left out.")
    assert user_note("Advanced indicators need the Basic plan, so MACD was left out.")
    assert user_note("The volume filter you mentioned isn't available, so it was skipped.")


def test_write_strategy_drops_internal_notes(monkeypatch):
    import json as _json
    from app import ai_writer
    reply = {"entry": [{"l": {"t": "ema", "p": 20}, "op": "xa", "r": {"t": "ema", "p": 50}}], "exit": [], "tf": None,
             "risk": {"sl": 2}, "mentioned": ["sl"],
             "notes": ["No timeframe specified, left as null.", "Short selling on delivery isn't possible, so only longs are tested."]}
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: _json.dumps(reply))
    out = ai_writer.write_strategy("Buy when EMA 20 crosses above EMA 50, stop loss 2%", False)
    assert out["notes"] == ["Short selling on delivery isn't possible, so only longs are tested."]
    assert "tgt" not in out.get("risk", {})
    assert "Never invent exits, stops or targets" in ai_writer.SYSTEM
