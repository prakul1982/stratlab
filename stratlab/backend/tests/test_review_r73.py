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
