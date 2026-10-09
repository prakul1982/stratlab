"""Round 8B review of the live site at India's close (9 Oct 2026): daily candles that kept the pre-auction price (and
the My Stocks email that repeated it), the paper overview's worst day and deepest fall read from a capped minute curve,
AI reads whose words disagree with their numbers, a Pulse mood that counted sectors it never saw, a PCR column that
repeated another, the chain "at the close" read a minute early, the email's preheader and style, "today's numbers"
of yesterday, 52-week highs from history that missed a bonus, advice-flavoured headlines and the Newsletters row."""
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import db, official_close, risk
from app.kite_service import KiteService

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def mem(monkeypatch):
    """The settings table in memory."""
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, *a: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    official_close.forget()
    yield store
    official_close.forget()


def _ist(d: str, hm: str) -> datetime:
    h, m = hm.split(":")
    return datetime.fromisoformat(d).replace(hour=int(h), minute=int(m), tzinfo=IST)


def _bars(n: int = 260, last_day: str = "2026-10-09", last_close: float = 2171.5, prev_close: float = 2077.0):
    """n daily candles ending on `last_day`, the day before closing at `prev_close`."""
    end = date.fromisoformat(last_day)
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    out = []
    for i, d in enumerate(days):
        c = 1900 + i * 0.6
        if d == end:
            c = last_close
        elif i == len(days) - 2:
            c = prev_close
        out.append({"t": f"{d.isoformat()}T00:00:00+05:30", "o": c, "h": c + 5, "l": c - 5, "c": c, "v": 1000.0})
    return out


# ---------- R8B-001: the day's candle takes the exchange's official close ----------
def _quotes(price=2156.0, at="2026-10-09T15:31:07+05:30"):
    return {"TCS": {"price": price, "at": at}, "RELIANCE": {"price": 1170.3, "at": "2026-10-09T15:59:58+05:30"}}


def test_a_days_candle_takes_the_official_close_once_the_auction_has_matched(mem):
    official_close.save("2026-10-08", {"TCS": 2076.0})                       # the bhavcopy of the day before
    official_close.setup(None, lambda syms: {}, force=True, all_quotes_fn=lambda: _quotes())
    bars = _bars()
    out = official_close.history_close(bars, "TCS", "cas", "NSE", now=_ist("2026-10-09", "16:19"))
    assert out[-1]["c"] == 2156.0 and out[-1]["official"] is True              # not the pre-auction 2,171.50
    assert out[-2]["c"] == 2076.0                                              # the day before from the bhavcopy
    assert round((out[-1]["c"] / out[-2]["c"] - 1) * 100, 2) == 3.85           # the email's move: +3.85%, not +4.60%
    assert out[-1]["h"] >= 2156.0 and out[-1]["l"] <= 2156.0
    assert bars[-1]["c"] == 2171.5 and "official" not in bars[-1]              # the broker's cached copy is left alone


def test_no_official_close_before_the_auction_matches_or_from_a_pre_auction_trade(mem):
    official_close.setup(None, lambda syms: {}, force=True, all_quotes_fn=lambda: _quotes())
    bars = _bars()
    # 15:25: the auction is still running, so the quote is the last continuous trade
    assert official_close.history_close(bars, "TCS", "cas", "NSE", now=_ist("2026-10-09", "15:25")) == bars
    assert official_close.day_close("TCS", "2026-10-09", "cas", "NSE", now=_ist("2026-10-09", "15:34")) is None
    # after the auction, a quote whose last trade is from before 15:15 isn't the auction's price
    official_close.forget()
    official_close.setup(None, lambda syms: {}, force=True, all_quotes_fn=lambda: _quotes(2171.5, "2026-10-09T15:14:58+05:30"))
    assert official_close.day_close("TCS", "2026-10-09", "cas", "NSE", now=_ist("2026-10-09", "16:00")) is None
    # a quote of another day is never a close of this one
    official_close.forget()
    official_close.setup(None, lambda syms: {}, force=True, all_quotes_fn=lambda: _quotes(2076.0, "2026-10-08T15:59:00+05:30"))
    assert official_close.day_close("TCS", "2026-10-09", "cas", "NSE", now=_ist("2026-10-09", "16:00")) is None


def test_the_bhavcopy_overwrites_the_quote_close_when_it_arrives(mem):
    official_close.setup(None, lambda syms: {}, force=True, all_quotes_fn=lambda: _quotes(2156.5))
    bars = _bars()
    assert official_close.history_close(bars, "TCS", now=_ist("2026-10-09", "16:30"))[-1]["c"] == 2156.5
    official_close.save("2026-10-09", {"TCS": 2156.0})
    assert official_close.history_close(bars, "TCS", now=_ist("2026-10-09", "18:40"))[-1]["c"] == 2156.0
    # a "-BE" series stock is named without its suffix in the exchange's file
    assert official_close.base_symbol("ABC-BE") == "ABC" and official_close.base_symbol("BAJAJ-AUTO") == "BAJAJ-AUTO"


def test_the_quote_price_before_the_auction_is_never_a_public_pages_close(mem):
    official_close.setup(None, lambda syms: {"TCS": {"price": 2171.5, "at": "2026-10-09T15:14:58+05:30"}}, force=True)
    assert official_close.quote_close("TCS", "2026-10-09", now=_ist("2026-10-09", "15:20")) is None
    assert official_close.quote_close("TCS", "2026-10-09", now=_ist("2026-10-09", "16:20")) == 2171.5


def _kite(monkeypatch, bars):
    ks = KiteService()
    ks.access_token, ks.token_day = "t", datetime.now(IST).date().isoformat()
    inst = {"token": 2953217, "symbol": "TCS", "exchange": "NSE", "type": "EQ", "fno": False}
    ks._by_token = {2953217: inst}
    monkeypatch.setattr(ks, "derivative_names", lambda: {"TCS"})
    calls = []

    class Inner:
        def historical_data(self, token, frm, to, interval, continuous=False):
            calls.append(token)
            return [{"date": datetime.fromisoformat(b["t"]), "open": b["o"], "high": b["h"], "low": b["l"],
                     "close": b["c"], "volume": b["v"]} for b in bars]
    ks.kite = Inner()
    ks._throttle = lambda: None
    return ks, calls


def test_every_daily_candle_read_from_the_broker_gets_the_official_close(monkeypatch, mem):
    """The charts, scans, briefs, My Stocks, alerts and backtests all read daily candles through KiteService.history."""
    bars = _bars()
    ks, _ = _kite(monkeypatch, bars)
    seen = []
    ks.day_close = lambda b, sym, kind, ex: (seen.append((sym, kind, ex)) or [*b[:-1], {**b[-1], "c": 2156.0}])
    out = ks.history(2953217, "1d", 30)
    assert out[-1]["c"] == 2156.0 and seen == [("TCS", "cas", "NSE")]
    assert ks.history(2953217, "1h", 30)[-1]["c"] == 2171.5                    # intraday candles as they are
    # the app's own broker is wired to the official close
    assert main.kite.__dict__.get("day_close") is official_close.history_close


def test_a_daily_candle_read_before_the_auction_is_read_again_after_it(monkeypatch, mem):
    ks, calls = _kite(monkeypatch, _bars())
    out_ts = time.time() - 5
    monkeypatch.setattr(KiteService, "_close_out", staticmethod(lambda now: out_ts))
    ks._cache[(2953217, "1d", 30, False)] = (out_ts - 60, _bars(last_close=2160.0))   # read at 15:3x
    assert ks.history(2953217, "1d", 30)[-1]["c"] == 2171.5 and calls == [2953217]
    assert ks.history(2953217, "1d", 30)[-1]["c"] == 2171.5 and calls == [2953217]   # the fresh copy is reused


def test_the_brief_and_my_stocks_wait_for_indias_official_close():
    from app.newsletter import content
    day = date(2026, 10, 9)
    assert not content.closed("IN", day, _ist("2026-10-09", "15:31"))         # was "closed" at 15:30, mid-auction
    assert not content.closed("IN", day, _ist("2026-10-09", "15:36"))
    assert content.closed("IN", day, _ist("2026-10-09", "15:41"))
    from app.newsletter import job
    j = job.Job()
    assert j.due("market-IN", _ist("2026-10-09", "15:39").astimezone(timezone.utc), "Asia/Kolkata", "15:00", region="IN") is None


def test_my_stocks_reports_the_official_close_and_its_move(monkeypatch, mem):
    from app.newsletter import content
    official_close.save("2026-10-08", {"TCS": 2076.0})
    official_close.setup(None, lambda syms: {}, force=True, all_quotes_fn=lambda: _quotes())
    bars = official_close.history_close(_bars(), "TCS", now=_ist("2026-10-09", "16:19"))
    monkeypatch.setattr(content, "_symbol_data", lambda r, s, d: {"bars": bars, "filings": [], "news": []})
    monkeypatch.setattr(content, "surveillance_lines", lambda s, since: None)
    monkeypatch.setattr(content.deals, "recent_for", lambda s, since: [])
    row = content.stock_row("IN", "TCS", date(2026, 10, 9), False, "2026-10-08T16:19")
    assert row["price"] == 2156.0 and row["change_pct"] == 3.85


# ---------- R8B-002: the paper overview's worst day and deepest fall ----------
def _trade(t: str, pnl: float) -> dict:
    return {"opened": t, "closed": t, "pnl": pnl}


def test_worst_day_and_deepest_fall_come_from_the_whole_history_not_the_capped_curve():
    """The reviewer's options session: 5 Oct −1,01,891; 6 and 7 Oct; 8 Oct +1,548 (−2,11,285 in all by its close);
    9 Oct a stop loss at 09:41 (−59,209) then +1,01,817 at the 15:15 square-off. The minute curve keeps 800 points
    and begins at 8 Oct 13:49."""
    trades = [_trade("2026-10-05T10:02:00+05:30", -61891.0), _trade("2026-10-05T14:40:00+05:30", -40000.0),
              _trade("2026-10-06T11:00:00+05:30", -60000.0), _trade("2026-10-07T12:00:00+05:30", -50942.0),
              _trade("2026-10-08T11:30:00+05:30", 1548.0),
              _trade("2026-10-09T09:41:00+05:30", -59209.0), _trade("2026-10-09T15:15:00+05:30", 101817.0)]
    cap = 5000000.0
    realised = sum(t["pnl"] for t in trades)
    assert realised == -168677.0
    curve = [{"t": "2026-10-08T13:49:00+05:30", "eq": cap - 211285.0}, {"t": "2026-10-08T15:15:00+05:30", "eq": cap - 211285.0},
             {"t": "2026-10-09T09:41:00+05:30", "eq": cap - 270494.0}, {"t": "2026-10-09T15:15:00+05:30", "eq": cap - 168677.0}]
    snap = {"id": "610500be", "name": "Iron fly", "kind": "options", "instrument": {"currency": "INR", "market": "IN"},
            "started_at": "2026-10-05T09:20:00+05:30", "equity_curve": curve, "trades": trades,
            "account": {"capital": cap, "equity": cap + realised, "realised": realised, "trades": len(trades)}}
    inr = risk.summary([snap], today="2026-10-09")["currencies"][0]
    assert inr["worst_day"] == {"date": "2026-10-05", "pnl": -101891.0}
    assert inr["deepest_fall"] == {"pnl": -270494.0, "pct": -5.41, "date": "2026-10-09"}
    assert inr["max_drawdown_pct"] == -5.41
    assert inr["today"] == 42608.0                                             # 1,01,817 − 59,209 (the page rounds each)
    assert [p["t"] for p in inr["curve"]][0] == "2026-10-05"                  # the chart spans the whole run
    # the day closes a session keeps (with open positions at their marks) win for the days they have
    snap2 = {**snap, "day_equity": {"2026-10-05": cap - 90000.0}}
    assert risk.summary([snap2], today="2026-10-09")["currencies"][0]["worst_day"] == {"date": "2026-10-05", "pnl": -90000.0}


def test_a_session_keeps_each_days_close_beyond_its_capped_curve():
    days = risk.note_days({}, [{"t": "2026-10-05T15:15", "eq": 100.0}, {"t": "2026-10-05T15:20", "eq": 90.0}])
    days = risk.note_days(days, [{"t": "2026-10-06T10:00", "eq": 95.0}])     # 5 Oct has left the curve
    assert days == {"2026-10-05": 90.0, "2026-10-06": 95.0}
    assert risk.closed_list([{"exit_t": "2026-10-05T15:15", "pnl": 10}, {"closed": "2026-10-06T10:00", "pnl": -2.5}, {"pnl": 1}]) == [
        ["2026-10-05T15:15", 10.0], ["2026-10-06T10:00", -2.5]]


def test_a_truncated_trade_list_never_reads_its_start_as_one_days_move():
    """A snapshot that lists only its latest trades: the ones it no longer lists start the running total."""
    trades = [_trade("2026-10-08T11:30:00+05:30", 1548.0), _trade("2026-10-09T09:41:00+05:30", -59209.0)]
    snap = {"id": "s", "name": "s", "kind": "options", "instrument": {"currency": "INR"}, "trades": trades,
            "account": {"capital": 5000000.0, "equity": 5000000.0 - 270494.0, "realised": -270494.0}}
    inr = risk.summary([snap], today="2026-10-09")["currencies"][0]
    assert inr["worst_day"] == {"date": "2026-10-09", "pnl": -59209.0}


# ---------- R8B-003: an AI read's direction words agree with its numbers ----------
AAPL_READ = {"summary": "Apple Inc. designs consumer electronics.", "bull": ["Revenue grew 14.2% YoY", "Return on equity is 137.2%"],
             "bear": ["Revenue fell from FY22 (394.3 B) to FY23 (383.3 B)",
                      "Net profit declined from FY24 (93.7 B) to FY25 (112.0 B) after a dip in FY23‑FY24",
                      "Operating margin slipped from 31.5% in FY24 to 30.1% in FY25"],
             "watch": ["Mon, 2 Nov next earnings results date"], "ideas": []}


def test_a_direction_word_its_numbers_contradict_is_dropped():
    from app.intel import grounding as G
    out = G.polish_company(AAPL_READ, "US", today=date(2026, 10, 9))
    assert not any("declined from FY24" in b for b in out["bear"])          # 93.7 B to 112.0 B is a rise
    assert not any("FY22" in b for b in out["bear"])                       # a fall two years before FY25: not a current risk
    assert "Operating margin slipped from 31.5% in FY24 to 30.1% in FY25" in out["bear"]   # a fall that is one, and current
    assert out["bull"] == ["Revenue grew 14.2% YoY", "Return on equity is 137.2%"]
    assert G.moves_agree("Net profit rose from FY24 (93.7 B) to FY25 (112.0 B).")
    assert not G.moves_agree("Net profit rose from ₹1,200 crore to ₹1,050 crore.")
    assert G.moves_agree("Net loss rose from -5.2 B to -7.1 B.")             # a loss that grows is left alone
    assert G.moves_agree("Sales fell 4% in the year.")                     # no from-to amounts: nothing to check


def test_dates_in_a_read_are_the_apps_whatever_hyphen_the_model_wrote():
    from app.intel import grounding as G
    s = "The most immediate focus is the upcoming Q2 FY2027 results due on 2026‑10‑17."
    out = G.polish_company({"summary": s, "bull": [], "bear": [], "watch": [], "ideas": []}, "IN", lender=True, today=date(2026, 10, 9))
    assert out["summary"].endswith("due on Sat, 17 Oct.")
    assert G.dates_in("on 2026–10–17") == ["2026-10-17"]


# ---------- R8B-004: the market mood counts sectors only from StratLab's own data ----------
def test_the_mood_never_says_all_sectors_rose_when_one_fell(monkeypatch):
    from app.intel import ai as A
    seen = {}

    def fake(system, text, **k):
        seen["facts"], seen["system"] = text, system
        return ('{"tone": "The NIFTY 50 closed at 22,520.45, up 1.3%. It rose as all sectoral indices turned green.", '
                '"hot": [], "flows": [], "themes": []}')
    monkeypatch.setattr(A, "complete", fake)
    idx = [{"name": "NIFTY 50", "price": 22520.45, "change_pct": 1.3, "high52": 26373.2, "low52": 21743.65}]
    sectors = {"up": 15, "down": 1, "unchanged": 0, "of": 16, "rows": []}
    out = A.pulse("IN", "", idx, [], (None, None), closed=True, sectors=sectors)
    assert "all sectoral" not in out["tone"] and "22,520.45" in out["tone"]
    assert '"sectors": {"up": 15, "down": 1, "unchanged": 0, "of": 16}' in seen["facts"]
    assert "sectors\" counts" in seen["system"]
    # with no count of StratLab's own, no count is kept; with one that bears it out, it is
    assert "all sectoral" not in A.pulse("IN", "", idx, [], (None, None), closed=True)["tone"]
    every = {"up": 16, "down": 0, "unchanged": 0, "of": 16}
    assert "all sectoral indices turned green" in A.pulse("IN", "", idx, [], (None, None), closed=True, sectors=every)["tone"]


def test_sector_counts_are_checked():
    from app.intel import grounding as G
    sec = {"up": 15, "down": 1, "unchanged": 0, "of": 16}
    assert G.sector_claims_ok("Fifteen of 16 sectors rose.", sec)
    assert not G.sector_claims_ok("All 16 sectors rose.", sec)
    assert not G.sector_claims_ok("Gains were spread across the board.", sec)
    assert G.sector_claims_ok("All sectors except oil and gas gained.", sec)
    assert not G.sector_claims_ok("Fifteen of 16 sectors rose.", None)
    assert G.sector_claims_ok("The NIFTY 50 rose 1.3%.", None)


def test_the_sector_count_comes_from_the_sector_indices_quotes(monkeypatch):
    from app.intel import company as C
    hub = C.Research.__new__(C.Research)

    class Kite:
        def index_quotes(self, keys):
            return {k: {"change_pct": -0.09 if "OIL" in k else 1.1} for k in keys}
    hub.kite = Kite()
    monkeypatch.setattr(hub, "_kite", lambda: True, raising=False)
    got = hub.sector_moves("IN")
    assert got["down"] == 1 and got["up"] == got["of"] - 1 and got["of"] >= 12
    assert any(r["name"] == "NIFTY OIL AND GAS" and r["change_pct"] == -0.09 for r in got["rows"])


# ---------- R8B-006: the chain "at the close" is read after F&O stops trading ----------
def test_the_closing_chain_is_read_after_the_derivatives_close():
    from app.options import recorder as R

    class Data:
        def ready(self):
            return True

        def pick_expiry(self, ex, name, choice):
            return "2026-10-13"

        def chain(self, ex, name, choice, around=10):
            return {"expiry": "2026-10-13" if choice == "current" else "2026-10-20", "spot": 22520.45, "lot": 65,
                    "rows": [{"strike": 22500.0, "ce": {"oi": 152284}, "pe": {"oi": 202941}}]}
    saved = []
    rec = R.Recorder(Data(), saved.append, [("NFO", "NIFTY")])
    assert R.in_hours(_ist("2026-10-09", "15:39")) and not R.close_window(_ist("2026-10-09", "15:40"))
    assert rec.run_once(_ist("2026-10-09", "15:41")) == 2                    # the closing read, after 15:40
    assert saved[0]["taken_at"].startswith("2026-10-09T15:41")
    assert rec.run_once(_ist("2026-10-09", "15:46")) == 0                    # once a day
    assert rec.run_once(_ist("2026-10-09", "16:30")) == 0
    assert not R.close_window(_ist("2026-10-10", "15:41"))                   # a Saturday


# ---------- R8B-007: the brief's preheader, one structure every day, "52-week high" ----------
def test_the_inbox_preview_line_never_ends_mid_sentence():
    from app import email_kit as kit
    long = ("On October 9, 2026, the NIFTY 50 closed at 22,520.45, up 1.30%, while the SENSEX ended at 72,472.33, up 1.23%, "
            "and NIFTY BANK at 55,256.65, up 1.36%. Nifty IT moved from Weakening to Leading.")
    line = kit.short_line(long)
    assert len(line) <= 140 and not line.endswith(" at") and line.endswith((".", "…"))
    assert kit.short_line("NIFTY 50 +1.30%; SENSEX +1.23% today. One sector moved.") == "NIFTY 50 +1.30%; SENSEX +1.23% today. One sector moved."
    html, _ = kit.render("T", [], kit.Footer(why="w"), summary=long)
    assert "and NIFTY BANK at</div>" not in html


def test_every_brief_opens_with_the_facts_line_and_the_ai_words_go_under_it(monkeypatch, mem):
    from app.newsletter import job, write
    ai = "On Friday the NIFTY 50 closed at 22,520.45, up 1.30%, led by IT."
    monkeypatch.setattr(write, "ai_summary", lambda f: ai)
    write._cache.clear()
    facts = {"kind": "market", "region": "IN", "day": "2026-10-09", "weekly": False, "since": "2026-10-08",
             "indices": [{"name": "NIFTY 50", "price": 22520.45, "change_pct": 1.3, "from_high_pct": -14.6},
                         {"name": "SENSEX", "price": 72472.33, "change_pct": 1.23}],
             "rotation": [{"sector": "Nifty IT", "from": "Weakening", "to": "Leading"}]}
    issue = job.make_issue(facts, "IN")
    assert issue["summary"].startswith("NIFTY 50 +1.30%; SENSEX +1.23% today.") and issue["ai_summary"] == ai and issue["ai"]
    html, text = write.render(issue)
    assert text.index("NIFTY 50 +1.30%; SENSEX +1.23% today.") < text.index(ai)
    assert ">NIFTY 50 +1.30%; SENSEX +1.23% today. 1 sector moved to another quadrant on the rotation chart.</div>" in html
    assert "14.6% below its 52-week high" in html and "below its high" not in html
    # a day whose AI words didn't pass has the same first line and nothing under it
    monkeypatch.setattr(write, "ai_summary", lambda f: None)
    write._cache.clear()
    plain = job.make_issue({**facts, "day": "2026-10-08"}, "IN")
    assert plain["summary"].startswith("NIFTY 50 +1.30%; SENSEX +1.23% today.") and not plain.get("ai_summary")


def test_stored_briefs_get_the_facts_line_first(mem):
    from app.newsletter import job
    issue = {"id": "market.IN.2026-10-09", "kind": "market", "region": "IN", "day": "2026-10-09", "weekly": False,
             "subject": "Market Brief India, Fri 9 Oct: NIFTY 50 +1.30%", "title": "NIFTY 50 up 1.30%", "ai": True,
             "summary": "On October 9, 2026, the NIFTY 50 closed at 22,520.45.", "indices": [{"name": "NIFTY 50", "price": 22520.45, "change_pct": 1.3}],
             "sections": [], "at": "2026-10-09T16:19+05:30"}
    job.save(issue)
    assert job.repair_facts_line("IN", days=3650) == 1
    got = job.load("market.IN.2026-10-09")
    assert got["summary"] == "NIFTY 50 +1.30% today." and got["ai_summary"].startswith("On October 9, 2026")
    assert job.repair_facts_line("IN", days=3650) == 0


def test_the_newsletters_row_says_the_skipped_count_even_when_none(monkeypatch, mem):
    from app import admin_jobs
    st = {"last_run": "2026-10-09T10:48:45+00:00", "sent": 2, "last_error": None, "regions": {
        "IN": {"issue": "market.IN.2026-10-09", "day": "2026-10-09", "readers": 1, "sent": 1, "other_edition": 0, "skipped": {}},
        "stocks": {"day": "2026-10-09", "readers": 2, "sent": 1, "other_edition": 0, "skipped": {"email address not confirmed": 1}}}}
    monkeypatch.setattr(main.newsletter_job, "status", st)
    row = next(r for r in admin_jobs.rows() if r["id"] == "newsletters")
    assert "India, 2026-10-09: sent to 1 of 1 reader; skipped 0" in row["log"]
    assert "My stocks, 2026-10-09: sent to 1 of 2 readers; skipped 1: 1 email address not confirmed" in row["log"]


# ---------- R8B-008: "Latest: 8 Oct · 9 Oct due about 18:30 IST" ----------
def test_numbers_of_yesterday_on_the_evening_of_today_say_when_todays_are_due():
    from app import stock_pages
    assert stock_pages.day_due("IN", "2026-10-08", _ist("2026-10-09", "19:05")) == {"day": "2026-10-09", "due": "18:30 IST"}
    assert stock_pages.day_due("IN", "2026-10-09", _ist("2026-10-09", "19:05")) is None       # in already
    assert stock_pages.day_due("IN", "2026-10-08", _ist("2026-10-09", "14:00")) is None       # the session is still on
    assert stock_pages.day_due("IN", "2026-10-09", _ist("2026-10-10", "11:00")) is None       # a Saturday
    assert stock_pages.day_due("IN", None, _ist("2026-10-09", "19:05")) is None


# ---------- R8B-009: the exchange's own 52-week high and low ----------
W52 = ('"Disclaimer - The Data provided in the adjusted 52 week high and adjusted 52 week low columns are adjusted for corporate '
       'actions (bonus, splits & rights)."\n"Effective for 09-Oct-2026"\n'
       '"SYMBOL","SERIES","Adjusted 52_Week_High","52_Week_High_Date","Adjusted 52_Week_Low","52_Week_Low_DT"\n'
       '"INFY","EQ","1728.00","03-FEB-2026","980.40","29-SEP-2026"\n'
       '"ITC","EQ","426.40","31-OCT-2025","244.10","25-SEP-2026"\n'
       '"ITC","BL","999.00","31-OCT-2025","1.00","25-SEP-2026"\n')


def test_the_exchanges_52_week_report_is_read():
    from app import exchange_days as E
    assert E.week52_rows(W52) == {"INFY": [1728.0, "2026-02-03", 980.4, "2026-09-29"], "ITC": [426.4, "2025-10-31", 244.1, "2026-09-25"]}
    with pytest.raises(ValueError):
        E.week52_rows("SYMBOL,CLOSE\nINFY,1000\n")


def test_the_candle_of_the_exchanges_52_week_high_day_takes_its_high(mem):
    """INFY's candle of 3 Feb 2026 (open 1,690.60, high 1,691.40) and ITC's of 31 Oct 2025 (high 406.55) are below the
    exchange's day highs of 1,728.00 and 426.40: the 52-week high on every page was off."""
    from app import exchange_days as E, stock_pages
    official_close.save_ranges("2026-10-09", E.week52_rows(W52))
    infy = [{"t": "2026-02-02T00:00:00+05:30", "o": 1626.8, "h": 1626.8, "l": 1583.7, "c": 1594.9, "v": 1.0},
            {"t": "2026-02-03T00:00:00+05:30", "o": 1690.6, "h": 1691.4, "l": 1618.0, "c": 1620.9, "v": 1.0},
            {"t": "2026-09-29T00:00:00+05:30", "o": 990.0, "h": 995.0, "l": 981.0, "c": 985.0, "v": 1.0},
            {"t": "2026-10-08T00:00:00+05:30", "o": 990.0, "h": 1001.0, "l": 985.0, "c": 997.0, "v": 1.0}]
    out = official_close.history_close(infy, "INFY", "cas", "NSE", now=_ist("2026-10-09", "11:00"))
    assert out[1]["h"] == 1728.0 and out[1]["o"] == 1690.6 and out[2]["l"] == 980.4 and infy[1]["h"] == 1691.4
    assert stock_pages.price_facts(out)["high52"] == 1728.0 and stock_pages.price_facts(out)["low52"] == 980.4
    itc = [{"t": "2025-10-31T00:00:00+05:30", "o": 400.95, "h": 406.55, "l": 398.75, "c": 400.8, "v": 1.0}]
    assert official_close.history_close(itc, "ITC", now=_ist("2026-10-09", "11:00"))[0]["h"] == 426.4
    # a figure on another basis (far beyond the candle) is left alone; a BSE-only stock isn't in the exchange's report
    far = [{"t": "2026-02-03T00:00:00+05:30", "o": 800.0, "h": 845.7, "l": 800.0, "c": 810.0, "v": 1.0}]
    assert official_close.history_close(far, "INFY", now=_ist("2026-10-09", "11:00"))[0]["h"] == 845.7
    assert official_close.history_close(itc, "ITC", exchange="BSE", now=_ist("2026-10-09", "11:00"))[0]["h"] == 406.55


def test_the_52_week_report_is_read_in_the_evening_with_the_closes(mem):
    from app import exchange_days as E
    asked = []

    class Files:
        def text(self, url, want=".csv"):
            asked.append(url)
            return W52 if "52_wk" in url else None
    official_close.setup(lambda: Files(), None, force=True)
    assert official_close.fetch_ranges("2026-10-09", _ist("2026-10-09", "17:00")) is None and asked == []
    got = official_close.fetch_ranges("2026-10-09", _ist("2026-10-09", "18:40"))
    assert got["day"] == "2026-10-09" and got["rows"]["INFY"][0] == 1728.0
    assert asked == [E.WEEK52.format(dmy="09102026")]


# ---------- R8B-012: more advice-worded headlines left out ----------
ADVICE = ["What should RIL investors do?", "Reliance shares: What should investors do now?",
          "What Could Drive Reliance Industries Stock Higher by 15%", "Owning Reliance may be a cheaper way to buy Jio Platforms",
          "TCS Q2 preview: Check Goldman Sachs, Morgan Stanley Target Prices",
          "Sensex jumps 879 points, Nifty above 22,500: What Investors Should Know", "Infosys: price targets raised after results"]
FACTUAL = ["Sensex jumps 879 points as IT stocks rally; Nifty ends at 22,520", "TCS Q2 results: net profit rises 6% to Rs 12,000 crore",
           "Reliance Jio adds 3 million subscribers in September", "What drove the Nifty 1.3% higher on Friday",
           "Infosys sets record date for its buyback", "Investors pull Rs 12,944 crore from Indian shares"]


def test_advice_worded_headlines_are_left_out_and_factual_ones_kept():
    from app.intel.news import plain_headline
    for t in ADVICE:
        assert not plain_headline(t), t
    for t in FACTUAL:
        assert plain_headline(t), t


def test_the_brief_and_my_stocks_leave_them_out(monkeypatch, mem):
    from app.newsletter import content, job
    assert not content.headline_ok("IN", "Sensex jumps 879 points, Nifty above 22,500: What Investors Should Know")
    monkeypatch.setattr(content, "_symbol_data", lambda r, s, d: {"bars": _bars(), "filings": [], "news": [
        {"headline": "What should RIL investors do?", "at": "2026-10-09T08:00:00+00:00"},
        {"headline": "Reliance Jio adds 3 million subscribers in September", "at": "2026-10-09T08:00:00+00:00"}]})
    monkeypatch.setattr(content, "surveillance_lines", lambda s, since: None)
    monkeypatch.setattr(content.deals, "recent_for", lambda s, since: [])
    row = content.stock_row("IN", "RELIANCE", date(2026, 10, 9), False, "2026-10-08T16:19")
    assert [n["headline"] for n in row["headlines"]] == ["Reliance Jio adds 3 million subscribers in September"]
    # a stored brief that carried one has it taken out
    job.save({"id": "market.IN.2026-10-09", "kind": "market", "region": "IN", "day": "2026-10-09", "weekly": False, "ai": False,
              "subject": "Market Brief India, Fri 9 Oct: NIFTY 50 +1.30%", "title": "NIFTY 50 up 1.30%", "summary": "NIFTY 50 +1.30% today.",
              "indices": [], "at": "2026-10-09T16:19+05:30", "sections": [{"title": "Headlines", "items": [
                  {"text": "Sensex jumps 879 points, Nifty above 22,500: What Investors Should Know"},
                  {"text": "Sensex jumps 879 points as IT stocks rally; Nifty ends at 22,520"}]}]})
    assert job.repair_facts_line("IN", days=3650) == 1
    items = job.load("market.IN.2026-10-09")["sections"][0]["items"]
    assert [i["text"] for i in items] == ["Sensex jumps 879 points as IT stocks rally; Nifty ends at 22,520"]
