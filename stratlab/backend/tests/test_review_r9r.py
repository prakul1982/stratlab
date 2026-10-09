"""Round 9 review of the broker, reliability and the US session (live site, 9 Oct 2026): the trade journal and the tax report
totalling the same 11 trades to opposite signs, an ex-date card saying "from today", the NAV label on an empty funds page,
the fund-cost check quoted two ways, a currency-futures check that passed a session behind, a raw dict in the Positioning
log, US breadth called "today's" during the US session, the Invest home's US tab, dropped connections on database and
upstream reads, and the slow first load of /mine.

Nothing here depends on the time of day or on a background job having run: every clock is passed in."""
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import auth, db, http_retry, journal as J, journal_routes, money_calendar, platform_check as pc, positioning as P
from app import stock_pages, tax_lots
from tests import world

PRO = world.headers("pro-token")
ADMIN = world.headers("admin-token")
ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT.parent / "frontend"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    J._paired.clear()
    journal_routes._synced.clear()
    yield built
    J._paired.clear()
    journal_routes._synced.clear()
    built["close"]()


# ---------- R9R-001: the journal and the tax report total the same sale lines to the same rupee ----------
def _pnl(pid: str, bd: str, sd: str, qty: float, bp: float, sp: float, charges: float, sym: str = "JMFINANCIL") -> list[dict]:
    """A tax P&L line as the tax report keeps it: the purchase (no charges) and the sale (the file's charges), tid ending :b and :s."""
    base = {"symbol": sym, "sym": sym, "isin": "", "name": sym, "exchange": "NSE", "src": "pnl"}
    return [{**base, "d": bd, "t": "", "side": "B", "qty": qty, "price": bp, "charges": 0.0, "tid": f"pnl:{pid}:b"},
            {**base, "d": sd, "t": "", "side": "S", "qty": qty, "price": sp, "charges": charges, "tid": f"pnl:{pid}:s"}]


# three lots of one company sold on 18 Jun at one price, with the charges the file listed on each sale (synthetic numbers)
TAX_TRADES = (_pnl("1", "2026-05-04", "2026-06-18", 100, 100.00, 142.98, 40.00)
              + _pnl("2", "2026-05-06", "2026-06-18", 80, 102.50, 142.98, 37.50)
              + _pnl("3", "2026-05-07", "2026-06-18", 60, 99.00, 142.98, 71.91)
              + _pnl("4", "2026-04-01", "2026-06-02", 10, 500.00, 480.00, 0.0, sym="ITC"))


def _tax_gain(trades) -> float:
    got = tax_lots.compute(trades, today="2026-10-09")
    return sum(r["gain"] for r in got["realised"]) + sum(i["pnl"] for i in got["intraday"])


def test_journal_lines_from_the_tax_report_carry_the_charges_the_file_listed():
    lines = J.from_tax(TAX_TRADES)["lines"]
    assert [x["charges"] for x in lines] == [40.0, 37.5, 71.91, 0.0]
    # the sale values are the file's own: the exit price is what the file says, not the price less charges
    assert lines[0]["sv"] == pytest.approx(100 * 142.98) and lines[0]["bv"] == pytest.approx(100 * 100.00)


def test_the_journal_and_the_tax_report_agree_on_the_same_sale_lines():
    trades = J.line_trades(J.from_tax(TAX_TRADES)["lines"], J.clean_settings({}))
    journal_net = sum(t["net"] for t in trades)
    assert journal_net == pytest.approx(_tax_gain(TAX_TRADES), abs=0.01)
    # and it is not the modelled figure: the same lines with no charges listed are charged at the published rates
    legacy = [{**x, "charges": None} for x in J.from_tax(TAX_TRADES)["lines"]]
    modelled = sum(t["net"] for t in J.line_trades(legacy, J.clean_settings({})))
    assert abs(modelled - journal_net) > 1
    assert all(t["charges_from"] == "file" for t in trades)
    # gross is the same either way
    assert sum(t["gross"] for t in trades) == pytest.approx(100 * 42.98 + 80 * 40.48 + 60 * 43.98 + 10 * -20.0)


def test_a_tax_line_with_no_charges_figure_at_all_is_still_modelled():
    bare = [{k: v for k, v in t.items() if k != "charges"} for t in TAX_TRADES]
    assert all(x["charges"] is None for x in J.from_tax(bare)["lines"])


def test_a_partly_matched_line_takes_its_share_of_the_charges():
    b, s = _pnl("9", "2026-05-04", "2026-06-18", 100, 100.0, 110.0, 30.0)
    assert J.tax_line_charges(b, {**s, "qty": 100}) == 30.0
    assert J.tax_line_charges(b, {**s, "qty": 200}) == 15.0         # a sale line of 200 shares matched to a purchase of 100: half its charges


def test_the_journal_page_shows_the_tax_reports_total_and_fixes_lines_saved_before(w):
    c = w["client"]
    tax_lots.save("u-pro", TAX_TRADES, [])
    # the journal as an earlier version saved it: the same lines with no charges of their own
    old = J.load("u-pro")
    J.add(old, {"fills": [], "lines": [{**x, "charges": None} for x in J.from_tax(TAX_TRADES)["lines"]]})
    old["files"] = [{"name": "From the tax report", "broker": "", "trades": 4, "at": "2026-10-04T14:35"}]
    J.save("u-pro", old)
    r = c.get("/trade/journal", headers=PRO)
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["net"] == pytest.approx(round(_tax_gain(TAX_TRADES), 2), abs=0.01)
    assert s["charges"] == pytest.approx(149.41, abs=0.01)
    assert all(x["charges"] is not None for x in J.load("u-pro")["lines"])             # kept, so it is looked up once
    # the Trade home's line says the same
    assert c.get("/trade/journal/brief", headers=PRO).json()["net"] == s["net"]


def test_lines_from_a_file_uploaded_to_the_journal_keep_their_own_charges(w):
    tax_lots.save("u-pro", TAX_TRADES, [])
    j = J.load("u-pro")
    J.add(j, {"fills": [], "lines": [{**x, "charges": None} for x in J.from_tax(TAX_TRADES)["lines"]]})
    j["files"] = [{"name": "tradebook.csv", "broker": "Zerodha", "trades": 4, "at": "2026-10-04T14:35"}]      # not the tax report's
    J.save("u-pro", j)
    assert journal_routes.sync_tax_charges("u-pro", J.load("u-pro"))["lines"][0]["charges"] is None


# ---------- R9R-002: an ex-date card names the day ----------
def test_the_ex_date_card_says_the_date_not_today():
    action = {"id": "a1", "symbol": "TCS", "kind": "dividend", "amount": 12.0, "ex_date": "2026-10-14", "record_date": "2026-10-14",
              "text": "Interim dividend ₹12 a share", "short": "Interim dividend ₹12", "label": "Dividend"}
    ev = money_calendar._action_events(action, {"qty": 10}, date(2026, 10, 9), date(2026, 12, 31))
    ex = next(e for e in ev if e["kind"] == "ex_dividend")
    assert "Shares bought on or after 14 Oct don't get it." in ex["detail"] and "from today" not in ex["detail"]
    later = money_calendar._action_events({**action, "ex_date": "2026-11-02", "record_date": "2026-11-02"}, None, date(2026, 10, 9), date(2026, 12, 31))
    assert "on or after 2 Nov" in later[0]["detail"]


def test_no_page_or_email_says_shares_bought_from_today():
    for path in list((ROOT / "app").rglob("*.py")) + list((FRONT / "src").rglob("*.ts*")):
        assert "bought from today" not in path.read_text(encoding="utf-8"), path


# ---------- R9R-003: the funds page's NAV date is the file's, and only when funds are held ----------
def test_the_mutual_funds_view_carries_the_nav_files_date_not_the_time_it_was_read(w, monkeypatch):
    from app import money_mf
    daily = {"schemes": {"1": {"code": "1", "isin": "", "isin2": "", "name": "A", "nav": 10.0, "date": "2026-10-08", "category": "", "amc": ""},
                         "2": {"code": "2", "isin": "", "isin2": "", "name": "B", "nav": 11.0, "date": "2026-10-07", "category": "", "amc": ""}},
             "isin": {}, "read_at": datetime(2026, 10, 9, 10, 39, tzinfo=timezone.utc).timestamp()}
    monkeypatch.setattr(money_mf.navs, "daily", lambda: daily)
    v = money_mf.view("u-nobody-has-funds", "pro")
    assert v["nav_date"] == "2026-10-08" and "nav_read_at" not in v
    assert v["total"]["held"] == 0 and v["total"]["nav_dates"] is None
    monkeypatch.setattr(money_mf.navs, "daily", lambda: {"schemes": {}, "isin": {}, "read_at": None})
    assert money_mf.view("u-nobody-has-funds", "pro")["nav_date"] is None


# ---------- R9R-004: the fund-cost line is the job's last result, in plain days ----------
def test_ages_are_written_in_the_singular_too():
    from app import money_mf_ter as ter
    assert [ter.age_words(d) for d in (0.2, 1.0, 1.4, 2.0, 30.0)] == ["today", "1 day ago", "1 day ago", "2 days ago", "30 days ago"]
    from app import research
    assert research.period_name(1) == "1 day" and research.period_name(10) == "10 days"


def _ter_status(stored: int, schemes: int, months: int, ago_days: float) -> dict:
    return {"stored": stored, "schemes": schemes, "months": months, "month": "2026-10", "last_ok": time.time() - ago_days * 86400,
            "error": None, "running": False}


def test_the_platform_check_reads_the_ter_job_s_last_result(w, monkeypatch):
    from app import main, money_mf_ter as ter
    monkeypatch.setattr(ter, "status", lambda: _ter_status(2631, 2182, 8, 1.0))
    monkeypatch.setattr(ter, "CHECK_SCHEMES", 3)
    kept = {"at": "2026-10-09T12:00:00+00:00", "auto": False, "counts": {"pass": 1, "warn": 0, "fail": 0},
            "checks": [{"name": "Fund costs (TER)", "area": "Money", "state": "pass", "seconds": 0.1,
                        "detail": "2178 schemes read for 2026-10, 1 days ago; 2557 stored over 7 months."}]}
    db.set_setting(main.PLATFORM_LAST, json.dumps(kept))
    got = w["client"].get("/admin/platform/last", headers=ADMIN).json()["last"]
    line = next(c for c in got["checks"] if c["name"] == "Fund costs (TER)")
    assert "2182 schemes" in line["detail"] and "2631 stored over 8 months" in line["detail"] and "1 day ago" in line["detail"]
    assert "1 days" not in line["detail"] and line["seconds"] == 0.1
    # the Data and jobs row quotes the very same figures
    jobs = {j["id"]: j for j in w["client"].get("/admin/jobs", headers=ADMIN).json()["jobs"]}
    assert "2182 schemes for 2026-10" in " ".join(jobs["ter"]["log"]) and "2631 schemes stored over 8 months" in " ".join(jobs["ter"]["log"])
    assert got["counts"] == {"pass": 1, "warn": 0, "fail": 0}


def test_reading_the_ter_line_starts_no_read(monkeypatch):
    from app import money_mf_ter as ter
    started = []
    monkeypatch.setattr(ter, "start", lambda force=False: started.append(1))
    monkeypatch.setattr(ter, "status", lambda: _ter_status(900, 700, 3, 2.0))
    assert ter.check(start_read=False)["state"] in ("pass", "warn") and not started
    ter.check()
    assert started == [1]


# ---------- R9R-005: a market whose session has closed must have that session's candle ----------
IST = ZoneInfo("Asia/Kolkata")


class _Prov:
    def __init__(self, last: str):
        self.last = last

    def ready(self):
        return True

    def defaults(self):
        return [{"symbol": "USDINR"}]

    def history(self, inst, tf, days):
        return [{"t": f"{self.last}T00:00:00+05:30", "o": 96.0, "h": 96.5, "l": 95.9, "c": 96.14}]


class _Reg:
    def __init__(self, last):
        self.p = _Prov(last)

    def provider(self, market):
        return self.p


def test_the_last_completed_session_waits_for_the_close_and_the_feed():
    fri_noon = datetime(2026, 10, 9, 12, 0, tzinfo=IST)
    assert pc.last_completed_session("CDS", fri_noon) == date(2026, 10, 8)
    assert pc.last_completed_session("CDS", datetime(2026, 10, 9, 17, 20, tzinfo=IST)) == date(2026, 10, 8)    # closed 20 minutes ago
    assert pc.last_completed_session("CDS", datetime(2026, 10, 9, 18, 15, tzinfo=IST)) == date(2026, 10, 9)
    assert pc.last_completed_session("IN", datetime(2026, 10, 9, 16, 30, tzinfo=IST)) == date(2026, 10, 9)
    assert pc.last_completed_session("CDS", datetime(2026, 10, 10, 12, 0, tzinfo=IST)) == date(2026, 10, 9)    # Saturday: Friday's
    assert pc.last_completed_session("CRYPTO", datetime(2026, 10, 9, 18, 15, tzinfo=IST)) == date(2026, 10, 8)  # never closes


def test_a_currency_candle_a_session_behind_after_the_close_is_a_warning_not_a_pass():
    after = datetime(2026, 10, 9, 18, 15, tzinfo=IST)
    got = pc.check_market(_Reg("2026-10-08"), "CDS", now=after)
    assert got["state"] == "warn" and "2026-10-08" in got["detail"] and "2026-10-09 session closed at 17:00 IST" in got["detail"]
    assert pc.check_market(_Reg("2026-10-09"), "CDS", now=after)["state"] == "pass"
    # before the close the day before's candle is the newest there should be
    assert pc.check_market(_Reg("2026-10-08"), "CDS", now=datetime(2026, 10, 9, 14, 0, tzinfo=IST))["state"] == "pass"


def test_a_candle_older_than_the_session_before_today_still_fails():
    got = pc.check_market(_Reg("2026-10-07"), "CDS", now=datetime(2026, 10, 9, 18, 15, tzinfo=IST), today=date(2026, 10, 9))
    assert got["state"] == "fail"


def test_a_futures_daily_candle_read_before_its_close_is_read_again_after_it(monkeypatch):
    """The daily candles were kept six hours, and re-read only after the stock market's close (15:47): a currency future read at
    16:50 (the daily check) was served at 18:15 with the day before as its newest (R9R-005)."""
    import time as _t
    from app.kite_service import KiteService
    ks = KiteService()
    ks.access_token, ks.token_day = "t", datetime.now(IST).date().isoformat()
    calls = []

    class Inner:
        def historical_data(self, token, frm, to, interval, continuous=False):
            calls.append(token)
            return [{"date": datetime(2026, 10, 9, tzinfo=IST), "open": 96.0, "high": 96.5, "low": 95.9, "close": 96.7, "volume": 1}]
    ks.kite, ks._throttle = Inner(), lambda: None
    now = _t.time()
    monkeypatch.setattr(KiteService, "_close_out", staticmethod(lambda n: now + 3600))              # the stock market's: not yet
    monkeypatch.setattr(KiteService, "_close_out_at", staticmethod(lambda n, hhmm: now - 60))       # the segment's own: a minute ago
    stale = [{"t": "2026-10-08T00:00:00+05:30", "o": 96.0, "h": 96.5, "l": 95.9, "c": 96.14, "v": 1}]
    ks._cache[(777, "1d", 30, False)] = (now - 600, stale)                                         # read ten minutes ago, before its close
    ks._cache[(778, "1d", 30, False)] = (now - 600, stale)
    ks.set_session_close(777, "17:00")
    assert ks.history(777, "1d", 30, continuous=False)[-1]["c"] == 96.7 and calls == [777]         # its segment closed since: read again
    assert ks.history(778, "1d", 30, continuous=False)[-1]["c"] == 96.14 and calls == [777]        # a token without a close of its own: as before


def test_currency_and_commodity_providers_tell_the_broker_when_their_segment_closes():
    from app.data.cds import CDSProvider
    from app.data.mcx import MCXProvider

    class Kite:
        def __init__(self):
            self.marks = []

        def set_session_close(self, token, hhmm):
            self.marks.append((token, hhmm))

        def history(self, token, tf, days, continuous=None, ttl=None):
            return [{"t": "2026-10-09T00:00:00+05:30", "o": 1, "h": 1, "l": 1, "c": 1, "v": 0}]
    for cls, close in ((CDSProvider, "17:00"), (MCXProvider, "23:30")):
        k = Kite()
        cls(k).history({"token": 55}, "1d", 30)
        assert k.marks == [(55, close)]
        cls(k).history({"token": 56}, "1h", 30)
        assert k.marks == [(55, close)]                                                         # intraday candles: nothing to mark


# ---------- R9R-006: the Positioning log is a sentence, and amber until the files arrive ----------
def test_a_positioning_run_is_written_in_words():
    assert P.run_sentence({"participants": "missing", "cash": "ok", "chains": 5}) == (
        "Participant files not out yet; FII/DII numbers in; 5 option chains summarised.", True)
    assert P.run_sentence({"participants": "ok", "cash": "ok", "chains": 1}) == (
        "Participant files in; FII/DII numbers in; 1 option chain summarised.", False)
    text, waiting = P.run_sentence({"participants": "the exchange is having trouble (503).", "cash": "missing", "chains": 0})
    assert "couldn't be read (the exchange is having trouble (503).)" in text and "FII/DII numbers not out yet" in text and waiting
    assert "{" not in text and P.run_sentence(None) == ("", False)


def test_the_jobs_table_shows_positioning_as_check_while_a_file_is_missing(w):
    from app import main
    main.positioning_job.status.update(last_run="2026-10-09T18:45:00+05:30", last_result={"participants": "missing", "cash": "ok", "chains": 5},
                                       last_error=None)
    try:
        row = next(j for j in w["client"].get("/admin/jobs", headers=ADMIN).json()["jobs"] if j["id"] == "positioning")
        assert row["state"] == "warn" and row["log"][0] == "Participant files not out yet; FII/DII numbers in; 5 option chains summarised."
        main.positioning_job.status.update(last_result={"participants": "ok", "cash": "ok", "chains": 5})
        row = next(j for j in w["client"].get("/admin/jobs", headers=ADMIN).json()["jobs"] if j["id"] == "positioning")
        assert row["state"] == "ok" and "{" not in row["log"][0]
    finally:
        main.positioning_job.status.update(last_run=None, last_result=None)


# ---------- R9R-007: a group with no live view says so while its session trades ----------
UTC = timezone.utc


def test_during_the_us_session_the_stored_day_is_called_the_latest_close():
    open_ = datetime(2026, 10, 9, 13, 33, tzinfo=UTC)            # 09:33 in New York, Friday
    got = stock_pages.day_due("US", "2026-10-08", open_, due="5:45 PM ET", during=True)
    assert got == {"day": "2026-10-09", "due": "5:45 PM ET", "during": True}
    assert stock_pages.day_due("US", "2026-10-08", datetime(2026, 10, 9, 12, 0, tzinfo=UTC), during=True) is None         # not open yet
    assert stock_pages.day_due("US", "2026-10-09", open_, during=True) is None                                              # today's is in
    assert stock_pages.day_due("US", "2026-10-08", datetime(2026, 10, 10, 15, 0, tzinfo=UTC), during=True) is None          # Saturday
    after = stock_pages.day_due("US", "2026-10-08", datetime(2026, 10, 9, 21, 30, tzinfo=UTC), due="5:45 PM ET", during=True)
    assert after == {"day": "2026-10-09", "due": "5:45 PM ET"}                                                              # after the close
    # India has a live view: without `during` its session is not announced as pending
    assert stock_pages.day_due("IN", "2026-10-08", datetime(2026, 10, 9, 5, 0, tzinfo=UTC)) is None


def test_the_us_count_is_due_at_the_time_the_job_runs():
    from app import breadth
    assert breadth.due_label("US") == "5:45 PM ET" and breadth.RUN_AT["US"][1] == "17:45" and breadth.due_label("IN") is None


def test_the_breadth_page_says_so_in_the_user_interface_text():
    src = (FRONT / "src" / "lib" / "format.ts").read_text(encoding="utf-8")
    assert "Latest close" in src and "today's count comes after" in src


# ---------- R9R-009: a dropped connection on a read is tried once more, on every long-lived client ----------
class Flaky(httpx.BaseTransport):
    """Fails the first `fail` requests with `exc`, then answers 200 with a small JSON list."""

    def __init__(self, exc, fail=1):
        self.exc, self.fail, self.calls = exc, fail, []

    def handle_request(self, request):
        self.calls.append(request.method)
        if len(self.calls) <= self.fail:
            raise self.exc("Server disconnected without sending a response.", request=request)
        return httpx.Response(200, json=[{"id": 1}])


@pytest.fixture
def no_pause(monkeypatch):
    monkeypatch.setattr(http_retry, "RETRY_PAUSE", 0.0)
    monkeypatch.setattr(db, "RETRY_PAUSE", 0.0)


@pytest.mark.parametrize("exc", [httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError])
def test_every_kind_of_dropped_connection_is_tried_once_more_on_a_read(no_pause, exc):
    inner = Flaky(exc)
    with httpx.Client(transport=http_retry.RetryReads(inner)) as c:
        assert c.get("https://api.example/x").json() == [{"id": 1}]
    assert inner.calls == ["GET", "GET"]
    inner = Flaky(exc, fail=4)
    with httpx.Client(transport=http_retry.RetryReads(inner)) as c, pytest.raises(exc):
        c.get("https://api.example/x")
    assert inner.calls == ["GET", "GET"]                                              # once, not for ever


def test_a_write_is_never_sent_twice_when_it_may_have_landed(no_pause):
    inner = Flaky(httpx.RemoteProtocolError)
    with httpx.Client(transport=http_retry.RetryReads(inner)) as c, pytest.raises(httpx.RemoteProtocolError):
        c.post("https://api.example/x", json={})
    assert inner.calls == ["POST"]


def test_the_retry_closes_the_idle_connections_so_it_opens_a_new_one(no_pause):
    """A connection the server closed means the others that sat as long probably are closed too."""
    class Conn:
        def __init__(self, idle):
            self.idle, self.closed = idle, False

        def is_idle(self):
            return self.idle

        def close(self):
            self.closed = True

    class Pool:
        connections = [Conn(True), Conn(False), Conn(True)]

    inner = Flaky(httpx.RemoteProtocolError)
    inner._pool = Pool()
    with httpx.Client(transport=http_retry.RetryReads(inner)) as c:
        c.get("https://api.example/x")
    assert [x.closed for x in Pool.connections] == [True, False, True]               # the one in use is left alone


def _clients():
    from app import market_events, rules_watch
    from app.data.coinbase import CoinbaseProvider
    from app.docs import Docs
    from app.intel.filings import BSEFilings, NSEFilings
    from app.intel.net import Source
    return {"database": db._http, "source": lambda: Source("https://api.example").http, "nse": lambda: NSEFilings().http,
            "bse": lambda: BSEFilings().http, "calendar": lambda: market_events.Web().http, "docs": lambda: Docs().http,
            "crypto": lambda: CoinbaseProvider()._http, "rules": lambda: rules_watch.Fetcher()._client()}


@pytest.mark.parametrize("name", ["database", "source", "nse", "bse", "calendar", "docs", "crypto", "rules"])
def test_every_long_lived_client_retries_a_dropped_read(no_pause, name):
    client = _clients()[name]()
    try:
        transport = client._transport
        assert isinstance(transport, http_retry.RetryReads), name
        flaky = Flaky(httpx.RemoteProtocolError)
        transport.inner = flaky
        r = client.get("https://api.example/x") if name != "source" else client.get("/x")
        assert r.status_code == 200 and flaky.calls == ["GET", "GET"]
    finally:
        client.close()


def test_a_source_read_survives_a_dropped_connection(no_pause):
    from app.intel.net import Source
    src = Source("https://api.example")
    src.http._transport.inner = Flaky(httpx.RemoteProtocolError)
    assert src.fetch("/prices", ttl=0) == [{"id": 1}]


def test_keep_alive_is_shorter_than_any_idle_timeout_we_know_of():
    """The pool closes an idle connection after KEEPALIVE_EXPIRY seconds; servers and proxies close theirs after a minute at
    least. (The `limits` once written on the database client, with a 30 s expiry, were ignored: a client given a
    transport uses the transport's.)"""
    client = db._http()
    try:
        pool = client._transport.inner._pool
        assert pool._keepalive_expiry == http_retry.KEEPALIVE_EXPIRY and 0 < pool._keepalive_expiry <= 10
        assert pool._http2 is False and pool._http1 is True
    finally:
        client.close()


def test_our_own_server_waits_longer_than_a_proxy_before_closing_an_idle_connection():
    """uvicorn closes an idle connection after --timeout-keep-alive seconds; a proxy in front reuses connections it thinks are
    open, so ours must outlast the proxy's idle timeout (60 s is the common one)."""
    for name in ("Procfile", "railway.json"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "--workers 1" in text
        assert int(text.split("--timeout-keep-alive")[1].split()[0].strip('",')) > 60, name


# ---------- R9R-010: a page's dozen calls ask the sign-in service and the profile table once ----------
def test_concurrent_calls_with_one_token_check_it_once(w, monkeypatch):
    auth._cache.clear()
    auth._rejected.clear()
    db.forget_profile("u-pro")
    sb = db.sb()
    real_get_user, asked = sb.auth.get_user, []

    def counting(token):
        asked.append(token)
        time.sleep(0.05)
        return real_get_user(token)
    monkeypatch.setattr(sb.auth, "get_user", counting)
    real_get_profile, reads = db.get_profile, []

    def counting_profile(uid, email=None):
        reads.append(uid)
        time.sleep(0.05)
        return real_get_profile(uid, email)
    monkeypatch.setattr(db, "get_profile", counting_profile)
    out, errors = [], []

    def call():
        try:
            out.append(auth.current_profile(authorization="Bearer pro-token")["id"])
        except Exception as e:                                                         # pragma: no cover
            errors.append(e)
    threads = [threading.Thread(target=call) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and out == ["u-pro"] * 12
    assert len(asked) == 1 and len(reads) == 1


def test_a_refused_token_is_checked_once_for_all_the_calls_waiting_on_it(w, monkeypatch):
    from fastapi import HTTPException
    auth._cache.clear()
    auth._rejected.clear()
    asked = []

    def refuse(token):
        asked.append(token)
        time.sleep(0.05)
        raise ValueError("bad jwt")
    monkeypatch.setattr(db.sb().auth, "get_user", refuse)
    codes = []

    def call():
        try:
            auth.current_profile(authorization="Bearer made-up")
        except HTTPException as e:
            codes.append(e.status_code)
    threads = [threading.Thread(target=call) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes == [401] * 8 and len(asked) == 1


def test_calls_waiting_on_an_unreachable_sign_in_service_do_not_each_wait_out_its_timeout(w, monkeypatch):
    from fastapi import HTTPException
    auth._cache.clear()
    auth._rejected.clear()
    asked = []

    def down(token):
        asked.append(token)
        time.sleep(0.05)
        raise httpx.ConnectError("no route")
    real = db.sb().auth.get_user
    monkeypatch.setattr(db.sb().auth, "get_user", down)
    codes = []

    def call():
        try:
            auth.current_profile(authorization="Bearer pro-token")
        except HTTPException as e:
            codes.append((e.status_code, e.detail["code"]))
    threads = [threading.Thread(target=call) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes == [(503, "auth_unavailable")] * 6 and len(asked) == 1
    # the note dies with the calls that shared it: the next call asks again, and is let in once the service is back
    monkeypatch.setattr(db.sb().auth, "get_user", real)
    assert auth.current_profile(authorization="Bearer pro-token")["id"] == "u-pro"


def test_no_route_that_runs_on_the_event_loop_does_blocking_work_there():
    """An `async def` route runs on the one event loop: a database call or a sleep in its body holds every other request
    meanwhile. They hand such work to a thread (run_in_threadpool) or are plain `def` routes, which FastAPI runs in one."""
    import ast
    blocking = {("time", "sleep"), ("db", "get_setting"), ("db", "set_setting"), ("db", "get_profile"), ("billing", "handle_webhook"),
                ("state", "update"), ("state", "section")}
    bad = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) \
                        and (node.func.value.id, node.func.attr) in blocking:
                    bad.append(f"{path.name}:{node.lineno} {node.func.value.id}.{node.func.attr}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "view" and path.name == "routes.py":
                    bad.append(f"{path.name}:{node.lineno} view()")
    assert not bad, bad
