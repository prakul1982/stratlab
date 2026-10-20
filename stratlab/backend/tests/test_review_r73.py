"""Round 73: the secrets filter keeps uvicorn's access log printable, the Plans page says how GST stands, the offer line
says when a paid period starts."""
import io
import logging

from app.connect import redact


def _access(path: str) -> str:
    from uvicorn.logging import AccessFormatter
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False))
    handler.addFilter(redact.SecretFilter())
    lg = logging.getLogger("uvicorn.access")
    lg.addHandler(handler)
    old = lg.level
    lg.setLevel(logging.INFO)
    errors = io.StringIO()
    import sys
    real, sys.stderr = sys.stderr, errors          # logging prints "--- Logging error ---" here when formatting fails
    try:
        lg.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", path, "1.1", 200)
    finally:
        sys.stderr = real
        lg.removeHandler(handler)
        lg.setLevel(old)
    assert "Logging error" not in errors.getvalue()
    return stream.getvalue()


def test_access_log_line_prints_without_a_logging_error():
    assert '"GET /markets HTTP/1.1" 200' in _access("/markets")


def test_access_log_still_masks_a_token_in_the_path():
    out = _access("/inbound/email/brevo?k=hook-secret-0123456789")
    assert "hook-secret-0123456789" not in out and "?k=***" in out and " 200" in out


def test_a_secret_split_between_message_and_argument_is_still_masked():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(redact.SecretFilter())
    lg = logging.getLogger("r73-test")
    lg.addHandler(handler)
    lg.setLevel(logging.INFO)
    lg.info("password=%s", "hunter2hunter2")
    lg.info("plain %s line", "words")
    lg.removeHandler(handler)
    out = stream.getvalue()
    assert "hunter2hunter2" not in out and "plain words line" in out


def test_one_headline_per_index_move_and_one_live_blog():
    from app.newsletter import content
    titles = [
        "Sensex Crashes 900 Points, Nifty 50 Below 22,900; Axis, HDFC Bank, Trent Top Losers",
        "Sensex Today | Nifty 50 | Stock Market Live Updates: Sensex slumps over 900 pts, Nifty below 22,900; India VIX spikes 6%",
        "Sensex Today | Stock Market Live: Sensex, Nifty at day's low; Bajaj Finance slips 2% ahead of earnings",
        "Sensex crashes 900 points: Why is stock market down today?",
        "Sensex plunges over 900 points, Nifty50 below 22,900 - top reasons for fall",
        "RBI keeps repo rate unchanged as Sensex and Nifty watch bond yields",
    ]
    rows = [{"headline": t, "url": f"https://news.example/{i}", "at": "2026-10-19T08:00:00Z", "source": "Example"}
            for i, t in enumerate(titles)]
    got = [h["headline"] for h in content.pick_headlines("IN", rows, "0000-00-00", "9999-99-99")]
    assert got[0] == titles[0]
    assert titles[2] in got                         # the one live blog, its own story
    assert not {titles[1], titles[3], titles[4]} & set(got)
    assert content.story_keys("Dow jumps 1,200 points") == {"move:dow:1200"}
    assert content.story_keys("Nifty ends flat; IT stocks gain") == set()


def test_an_options_poll_failing_the_same_way_is_said_once_and_retried_each_minute(capsys):
    import time
    from app.options import session as S
    from tests.test_options import at, quiet_session
    s, _ = quiet_session()

    def down(*a, **k):
        raise RuntimeError("Indian market data is offline: the broker login has ended.")
    real = s.data.quotes
    s.data.quotes = down
    for _ in range(3):
        s.next_poll = 0.0
        s.on_timer(at("09:40"))
    assert capsys.readouterr().out.count("options poll failed") == 1
    assert not s.poll_ok and s.next_poll > time.time() + S.POLL + 30        # the repeat waits a minute, not 5 s
    s.data.quotes = real                                                    # the broker is back: polls go on as before
    s.next_poll = 0.0
    s.on_timer(at("09:41"))
    assert s.poll_ok and s.next_poll <= time.time() + S.POLL


from tests.test_review_r7v import mem, us  # noqa: E402,F401  (the in-memory settings table and a US page's facts)


def test_the_stock_price_pass_stops_when_the_broker_login_has_ended(mem, capsys):
    import json
    from datetime import datetime, timezone
    from app import stock_pages
    from app.kite_service import KiteNotReady
    now = datetime(2026, 10, 9, 0, 30, tzinfo=timezone.utc)
    built = now.timestamp() - 30 * 3600
    for i, sym in enumerate(("AAA", "BBB", "CCC")):
        mem[f"stocks:page:US:{sym}"] = json.dumps({"ts": built, "facts": us(symbol=sym, price_at="2026-10-07", market_cap=1_000.0 * (3 - i))})
    asked = []

    def down(region, sym):
        asked.append(sym)
        raise KiteNotReady("Indian market data is offline: the broker login has ended.")
    pages = stock_pages.Pages(lambda r, c: None)
    got = pages.refresh_prices("US", down, gap=0, now=now)
    assert asked == ["AAA"] and capsys.readouterr().out.count("price refresh failed") == 1
    assert got["failed"] == 1 and got["left"] == 2 and "US" not in pages.prices_done      # tried again at the next run

    def one_bad(region, sym):                       # one company with no prices: the others are still read
        if sym == "AAA":
            raise RuntimeError("no candles")
        return [{"t": "2026-10-08T00:00:00-04:00", "o": 1, "h": 1, "l": 1, "c": 1.0}]
    got = pages.refresh_prices("US", one_bad, gap=0, now=now)
    assert got["refreshed"] == 2 and got["failed"] == 1
