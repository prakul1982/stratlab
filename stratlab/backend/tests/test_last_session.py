"""R41A: one source of truth for an Indian stock's or index's latest completed session outside market hours.

The bug, seen live on Saturday 17 Oct 2026 at 00:01 IST right after a server restart: the broker's daily history ended on
Thursday 15 Oct, the candles were kept for six hours as if current, and the quote (Friday 16 Oct's close) was paired with
Thursday's change: "Last close 2,465.00 +45.1 (+1.96%) on 15 Oct", the Brief's +4.89%, the index strip on 15 Oct while
the pulse had 16 Oct. Every test runs on a fake clock (time_machine) and a broker fake whose history lags."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import time_machine

from app import last_session
from app.intel import company as C
from tests import fake_kite

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc
SAT_0001_IST = datetime(2026, 10, 16, 18, 31, tzinfo=UTC)       # Saturday 17 Oct 2026, 00:01 IST
FRI_1000_IST = datetime(2026, 10, 16, 4, 30, tzinfo=UTC)        # Friday 16 Oct, 10:00 IST, market open

# closes by day (Mon 12 to Fri 16 Oct 2026): TCS's Thursday move is +45.0 (+1.95%), Friday's +115.0 (+4.89%)
CLOSES = {
    "TCS": {"2026-10-12": 2290.0, "2026-10-13": 2301.0, "2026-10-14": 2305.0, "2026-10-15": 2350.0, "2026-10-16": 2465.0},
    "NIFTY 50": {"2026-10-12": 22800.0, "2026-10-13": 22850.0, "2026-10-14": 22900.0, "2026-10-15": 22997.0, "2026-10-16": 23146.0},
    "SENSEX": {"2026-10-12": 74000.0, "2026-10-13": 74100.0, "2026-10-14": 74200.0, "2026-10-15": 74316.0, "2026-10-16": 74729.0},
}
PREV_OF_FRIDAY = {"TCS": 2350.0, "NIFTY 50": 22997.0, "SENSEX": 74316.0}


class Broker(fake_kite.FakeKiteConnect):
    """The broker's API with daily candles of fixed closes, and a history that may end before the quote's session."""

    def __init__(self, through="2026-10-16"):
        super().__init__()
        self.through = through              # the newest day the history service answers with
        self.history_calls = 0
        self.quote_fails = False

    def historical_data(self, token, frm, to, interval, continuous=False, oi=False):
        self._hit()
        self.history_calls += 1
        name = self.by_token[int(token)]["tradingsymbol"]
        if interval != "day" or name not in CLOSES:
            return []
        out = []
        for day, c in CLOSES[name].items():
            if day > self.through:
                continue
            out.append({"date": datetime.fromisoformat(day).replace(tzinfo=IST), "open": c - 5, "high": c + 8, "low": c - 9,
                        "close": c, "volume": 1000})
        return out

    def quote(self, keys):
        self._hit()
        if self.quote_fails:
            raise RuntimeError("quote service down")
        out = {}
        for k in keys:
            r = self.by_key.get(k)
            name = r["tradingsymbol"] if r else None
            if name not in CLOSES:
                continue
            last = CLOSES[name]["2026-10-16"]
            # after the close the broker's previous close has rolled over to the session's own close (R34-001)
            out[k] = {"instrument_token": r["instrument_token"], "last_price": last, "volume": 5000,
                      "last_trade_time": datetime(2026, 10, 16, 15, 59, 58), "timestamp": datetime(2026, 10, 16, 15, 59, 58),
                      "ohlc": {"open": last - 11, "high": last + 14, "low": last - 17, "close": last}}
        return out


def service(through="2026-10-16"):
    """A freshly started server's broker service: nothing cached, as after a restart."""
    k = fake_kite.online()
    k.kite = Broker(through)
    return k


def hub(kite):
    return C.Research(kite)


def token(kite, name, exchange="NSE"):
    return kite.by_symbol(name, exchange)["token"]


def closes(bars):
    return [(str(b["t"])[:10], b["c"]) for b in bars]


# ---------- the daily candle cache after a restart ----------
@time_machine.travel(SAT_0001_IST, tick=False)
def test_candles_that_end_a_session_early_get_the_quotes_close_after_a_restart():
    k = service(through="2026-10-15")                   # the broker's history is still on Thursday's candle
    bars = k.history(token(k, "TCS"), "1d", 370)
    assert closes(bars)[-2:] == [("2026-10-15", 2350.0), ("2026-10-16", 2465.0)]


@time_machine.travel(SAT_0001_IST, tick=False)
def test_a_restarted_server_gives_friday_close_and_fridays_change_not_thursdays():
    k = service(through="2026-10-15")
    q = hub(k).quotes("IN", ["TCS"])["TCS"]
    assert q["price"] == 2465.0 and q["change_day"] == "2026-10-16"
    assert q["prev_close"] == 2350.0 and q["change"] == 115.0 and q["change_pct"] == 4.89
    assert q["change_pct"] != 1.95 and q["change_day"] != "2026-10-15"


@time_machine.travel(SAT_0001_IST, tick=False)
def test_the_change_and_the_percent_are_of_the_same_two_closes():
    for through in ("2026-10-15", "2026-10-16"):
        q = hub(service(through)).quotes("IN", ["TCS"])["TCS"]
        assert q["price"] - q["prev_close"] == pytest.approx(q["change"], abs=0.005)
        assert (q["price"] / q["prev_close"] - 1) * 100 == pytest.approx(q["change_pct"], abs=0.006)


@time_machine.travel(SAT_0001_IST, tick=False)
def test_whichever_copy_of_the_candles_a_page_reads_the_answer_is_the_same():
    """The race: the watchlist reads 15 days, the company page 370, the chart 365; a copy cached by one was served to
    another. Each of them, in any order, now ends on the latest completed session."""
    k = service(through="2026-10-15")
    t = token(k, "TCS")
    seen = [k.history(t, "1d", d)[-1] for d in (370, 15, 365, 15, 370)]
    assert {(str(b["t"])[:10], b["c"]) for b in seen} == {("2026-10-16", 2465.0)}


@time_machine.travel(SAT_0001_IST, tick=False)
def test_a_cached_copy_without_the_latest_session_is_read_again_within_a_minute_not_six_hours():
    with time_machine.travel(SAT_0001_IST, tick=False) as clock:
        k = service(through="2026-10-15")
        k.kite.quote_fails = True                     # no quote to complete it with: the stale copy has to be served
        t = token(k, "TCS")
        assert closes(k.history(t, "1d", 370))[-1][0] == "2026-10-15"
        calls = k.kite.history_calls
        k.history(t, "1d", 370)
        assert k.kite.history_calls == calls          # within the minute it is reused
        k.kite.through, k.kite.quote_fails = "2026-10-16", False       # the broker's history catches up
        clock.shift(timedelta(seconds=61))
        bars = k.history(t, "1d", 370)
        assert k.kite.history_calls == calls + 1      # ...and is read again, not kept for the six hours
        assert closes(bars)[-2:] == [("2026-10-15", 2350.0), ("2026-10-16", 2465.0)] and len(bars) == len(set(b["t"] for b in bars))


@time_machine.travel(SAT_0001_IST, tick=False)
def test_a_complete_copy_is_kept_for_its_full_time():
    k = service(through="2026-10-16")
    t = token(k, "TCS")
    k.history(t, "1d", 370)
    calls = k.kite.history_calls
    with time_machine.travel(SAT_0001_IST + timedelta(hours=2), tick=False):
        k.history(t, "1d", 370)
    assert k.kite.history_calls == calls


@time_machine.travel(SAT_0001_IST, tick=False)
def test_a_quote_of_another_session_is_never_made_into_a_candle():
    k = service(through="2026-10-14")
    k.kite.through = "2026-10-14"                      # history two sessions behind; the quote is of the 16th
    bars = k.history(token(k, "TCS"), "1d", 370)
    # the 15th cannot be made from a quote of the 16th: the series has a gap, and the last candle is the 16th's
    assert closes(bars)[-2:] == [("2026-10-14", 2305.0), ("2026-10-16", 2465.0)]


def test_candles_are_not_behind_while_the_session_has_not_settled():
    # Friday 16:30 IST: the 16th closed at 15:30 but its candle is final only at 18:30; the 15th is the latest completed
    friday_1630 = datetime(2026, 10, 16, 11, 0, tzinfo=UTC)
    bars = [{"t": "2026-10-15T00:00:00+05:30", "c": 1.0}]
    assert last_session.latest_day("IN", friday_1630) == "2026-10-15" and not last_session.behind(bars, "IN", friday_1630)
    assert last_session.behind(bars, "IN", SAT_0001_IST)


@time_machine.travel(FRI_1000_IST, tick=False)
def test_while_the_market_trades_the_candles_are_not_held_to_todays_session():
    k = service(through="2026-10-15")
    assert closes(k.history(token(k, "TCS"), "1d", 370))[-1][0] == "2026-10-15"
    assert k.kite.history_calls == 1


# ---------- last_session_move and the index strip ----------
@time_machine.travel(SAT_0001_IST, tick=False)
def test_stale_candles_and_a_newer_quote_give_the_newer_sessions_move():
    bars = [{"t": f"{d}T00:00:00+05:30", "c": c} for d, c in CLOSES["TCS"].items() if d <= "2026-10-15"]
    quote = {"price": 2465.0, "prev_close": 2465.0, "change": 0.0, "change_pct": 0.0, "at": "2026-10-16T15:59:58+05:30"}
    q = C.last_session_move(quote, bars)
    assert (q["price"], q["prev_close"], q["change"], q["change_pct"], q["change_day"]) == (2465.0, 2350.0, 115.0, 4.89, "2026-10-16")
    assert quote["change_pct"] == 0.0 and len(bars) == 4        # the inputs are never changed


@time_machine.travel(SAT_0001_IST, tick=False)
def test_candles_that_are_ahead_of_an_older_quote_set_the_price_too():
    bars = [{"t": f"{d}T00:00:00+05:30", "c": c} for d, c in CLOSES["TCS"].items()]
    quote = {"price": 2350.0, "prev_close": 2350.0, "change": 0.0, "change_pct": 0.0, "at": "2026-10-15T15:29:59+05:30"}
    q = C.last_session_move(quote, bars)
    assert q["price"] == 2465.0 and q["change_day"] == "2026-10-16" and q["change_pct"] == 4.89


@time_machine.travel(SAT_0001_IST, tick=False)
def test_the_index_strip_and_the_company_page_agree_on_the_same_session():
    k = service(through="2026-10-15")                 # after a restart, history one session behind
    h = hub(k)
    page = h.quotes("IN", ["TCS"])["TCS"]
    for symbol, name in (("^NSEI", "NIFTY 50"), ("^BSESN", "SENSEX"), ("TCS", "TCS")):
        candles = h.chart("IN", symbol, "1m", "1d")["candles"]
        last, prev = candles[-1], candles[-2]                  # how the My space strip reads a tile (lib/mine.ts)
        assert str(last["t"])[:10] == "2026-10-16", symbol
        assert last["c"] == CLOSES[name]["2026-10-16"] and prev["c"] == PREV_OF_FRIDAY[name], symbol
    strip_pct = round((candles[-1]["c"] / candles[-2]["c"] - 1) * 100, 2)
    assert strip_pct == page["change_pct"] == 4.89 and str(candles[-1]["t"])[:10] == page["change_day"]


@time_machine.travel(SAT_0001_IST, tick=False)
def test_a_complete_history_gives_the_same_answer_as_a_lagging_one():
    lag = hub(service(through="2026-10-15")).quotes("IN", ["TCS"])["TCS"]
    full = hub(service(through="2026-10-16")).quotes("IN", ["TCS"])["TCS"]
    keys = ("price", "prev_close", "change", "change_pct", "change_day")
    assert {x: lag[x] for x in keys} == {x: full[x] for x in keys}


def test_the_holdings_session_is_the_days_the_change_belongs_to():
    from app import holdings
    # the last trade was on the 16th, the change worked out for the 15th would be a different session
    assert holdings.session_day({"at": "2026-10-16T15:59:58+05:30", "change_day": "2026-10-15"}, "IN") == "2026-10-15"
    assert holdings.session_day({"at": "2026-10-16T15:59:58+05:30"}, "IN") == "2026-10-16"
