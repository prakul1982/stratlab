"""Lane site81: the LIVE18A / LIVE18B site findings (live review after Release 80, Fri 20 Nov 2026)."""
import json
import re
import time
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app import db, ipo, money_networth, positioning as P, scan_presets
from app.data import yahoo_markets as YM
from app.intel import mood
from app.main import app

FRONT = Path(__file__).resolve().parents[2] / "frontend"


# ---------- LIVE18A-001: a Mood card stored before Release 80 is served in today's words ----------
def _card(lines: list[str], adding=None, taking=None, index="S&P 500") -> dict:
    return {"region": "US", "session": "2026-11-19", "is_open": False, "headline": "Negative: the S&P 500 down on the day.",
            "lines": lines, "movers": [{"index": index, "adding": adding or [], "taking": taking or [], "of": 100}]}


ALPHABET = [{"symbol": "GOOGL", "name": "Alphabet", "change_pct": -3.46, "points": -13.4}]
OLD_US = ["2.0 times its 20-day average daily move (1.03%).", "37 of 500 S&P 500 stocks rose and 462 fell on 19 Nov.", "Alphabet took off about 13."]


def test_live18a_001_the_stored_broken_movers_sentence_is_written_again_from_its_own_figures():
    got = mood.mend_lines(_card(OLD_US, taking=ALPHABET))
    assert got["lines"][:2] == OLD_US[:2]
    assert got["lines"][2] == "Alphabet took about 13 points off the S&P 500."
    # India's: both halves, the second without its unit before
    india = _card(["Maruti Suzuki India added about 40 points to the NIFTY 50 and Tata Consultancy Services took off about 16."], index="NIFTY 50",
                  adding=[{"symbol": "MARUTI", "name": "Maruti Suzuki India", "change_pct": 4.1, "points": 40.2}],
                  taking=[{"symbol": "TCS", "name": "Tata Consultancy Services", "change_pct": -1.55, "points": -16.1}])
    assert mood.mend_lines(india)["lines"] == ["Maruti Suzuki India added about 40 points to the NIFTY 50 and Tata Consultancy Services took about 16 points off it."]
    # one point said "1 point" before too
    one = _card(["Apple took off about 1 point."], taking=[{"symbol": "AAPL", "name": "Apple", "change_pct": -0.1, "points": -1.0}])
    assert mood.mend_lines(one)["lines"] == ["Apple took about 1 point off the S&P 500."]


def test_live18a_001_a_card_already_in_todays_words_or_without_movers_is_left_as_it_is():
    new = _card(OLD_US[:2] + ["Alphabet took about 13 points off the S&P 500."], taking=ALPHABET)
    assert mood.mend_lines(new) is new
    bare = {"lines": ["Alphabet took off about 13."]}                 # no stored figures to write it from: not guessed
    assert mood.mend_lines(bare) is bare
    assert mood.mend_lines(None) is None
    assert mood.lines_of({"movers": [{"index": "S&P 500", "adding": [], "taking": ALPHABET}]}) == ["Alphabet took about 13 points off the S&P 500."]


def test_live18a_001_a_card_kept_in_the_database_is_mended_as_the_server_starts_and_on_every_read(monkeypatch):
    # site83 (LIVE20A-002), updated on purpose: a card kept by an earlier release is now read again, never served (test_site83); one of
    # this release's way of working the figures out ("method") is still taken up at the start and mended as before
    store = {mood.KEEP_KEY + "US": json.dumps({"at": time.time() - 60, "value": {**_card(OLD_US, taking=ALPHABET), "method": mood.METHOD}})}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    m = mood.Mood(hub=None)
    m._seed("US")
    assert m.payloads.kept("US")[1]["lines"][2] == "Alphabet took about 13 points off the S&P 500."
    # a read that answers with the old words (a closed session's final read is served as it is) is mended on the way out
    monkeypatch.setattr(m, "_get", lambda region, wait=20.0: (_card(OLD_US, taking=ALPHABET), time.time()))
    value, _ = m.get("US")
    assert value["lines"][2] == "Alphabet took about 13 points off the S&P 500."


# ---------- LIVE18B-001: USD/INR's daily closes are each day's real close ----------
def _fx_candles():
    # the source's daily candles of USDINR=X as sent on 20 Nov 2026 (each day's price at its start, open and close alike)
    days = [("2026-11-17", 93.9591), ("2026-11-18", 93.4746), ("2026-11-19", 93.4652), ("2026-11-20", 93.28)]
    return [{"t": f"{d}T00:00:00+00:00", "o": p, "h": p, "l": p, "c": p, "v": 0} for d, p in days]


def test_live18b_001_a_pairs_day_closes_at_the_next_days_open_and_the_newest_at_the_quote():
    meta = {"regularMarketPrice": 93.29, "regularMarketTime": int(datetime.fromisoformat("2026-11-20T00:20:52+00:00").timestamp()), "exchangeTimezoneName": "UTC"}
    got = YM.fx_day_closes(_fx_candles(), meta)
    assert [b["c"] for b in got] == [93.4746, 93.4652, 93.28, 93.29]
    assert round((got[2]["c"] / got[1]["c"] - 1) * 100, 2) == -0.2            # 19 Nov: 93.28, −0.20% (Yahoo's close), not 93.47 −0.01%
    assert all(b["l"] <= min(b["o"], b["c"]) and b["h"] >= max(b["o"], b["c"]) for b in got)
    # before the source has a candle for the new day (00:12 UTC, the reviewer's minute): one from the quote, so 19 Nov closes at its price
    early = YM.fx_day_closes(_fx_candles()[:-1], meta)
    assert [b["t"][:10] for b in early] == ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
    assert early[2]["c"] == 93.29 and early[3]["c"] == 93.29
    assert YM.fx_day_closes([], meta) == []


def test_live18b_001_the_fx_provider_gives_those_closes_and_other_markets_are_unchanged():
    meta = {"regularMarketPrice": 93.28, "regularMarketTime": int(datetime.fromisoformat("2026-11-20T00:20:52+00:00").timestamp()),
            "exchangeTimezoneName": "Europe/London", "currency": "INR"}

    class FakeYahoo:
        WINDOW = 400

        def chart(self, sym, tf="1d", days=365, ttl=None, exact=False):
            return {"meta": meta, "candles": _fx_candles()}

    fx = YM.YahooProvider("FX", FakeYahoo())
    bars = fx.history(fx.instrument("USDINR=X"), "1d", 30)
    assert [b["c"] for b in bars][-2:] == [93.28, 93.28]
    us = YM.YahooProvider("US", FakeYahoo())
    assert [b["c"] for b in us.history({"token": "SPY", "market": "US"}, "1d", 30)][-2:] == [93.4652, 93.28]


# ---------- LIVE18A-009: a US issue's changes are against the offer price the row shows ----------
ANT = {"id": "us-ant", "market": "US", "name": "Anthropic, PBC", "symbol": "ANT", "currency": "USD", "low": 83.0, "high": 83.0, "priced": "2026-11-19"}


def test_live18a_009_the_offer_price_of_a_one_price_band_is_the_issue_price():
    assert ipo.offer_price(ANT) == 83.0
    assert ipo.offer_price({**ANT, "low": 80.0, "high": 85.0}) is None
    assert ipo.offer_price({**ANT, "price": 84.0}) == 84.0
    stored = {"issue_price": None, "listing_price": 111.5, "listing_change_pct": None, "day_close": 97.17, "day_change_pct": None,
              "latest": 97.17, "latest_date": "2026-11-19", "change_pct": None, "listed": "2026-11-19", "basis": "prices"}
    got = ipo.official_perf(ANT, stored, datetime(2026, 11, 20, 0, 27))
    assert got["issue_price"] == 83.0 and got["listing_change_pct"] == 34.34 and got["change_pct"] == 17.07 and got["day_change_pct"] == 17.07
    # a band of two prices has no issue price: the changes stay unsaid
    assert ipo.official_perf({**ANT, "high": 85.0}, stored, datetime(2026, 11, 20, 0, 27))["listing_change_pct"] is None


# ---------- LIVE18B-008: the option underlyings answer as a list with the feed offline, never a 503 ----------
def test_live18b_008_offline_the_underlyings_list_is_the_recorded_one_with_the_offline_line(monkeypatch):
    monkeypatch.setattr(main.options_data, "ready", lambda: False)
    monkeypatch.setattr(main, "options_recorded", lambda profile=None: [{"exchange": "NFO", "name": "NIFTY", "recorded": True}])
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "pro", "plan": "pro"}
    try:
        c = TestClient(app)
        r = c.get("/options/underlyings", params={"offline": "list"})
        assert r.status_code == 200
        body = r.json()
        assert body["rows"] == [{"exchange": "NFO", "name": "NIFTY", "recorded": True}]
        assert body["offline"].startswith("Option quotes come from the live feed, which is offline")
        assert c.get("/options/underlyings").status_code == 503              # the plain answer is as before
    finally:
        app.dependency_overrides.clear()


def test_live18b_008_online_the_list_comes_with_no_offline_line(monkeypatch):
    monkeypatch.setattr(main.options_data, "ready", lambda: True)
    monkeypatch.setattr(main.options_data, "underlyings", lambda: [{"exchange": "NFO", "name": "NIFTY"}])
    monkeypatch.setattr(main, "keep_underlyings", lambda rows: None)
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "pro", "plan": "pro"}
    try:
        assert TestClient(app).get("/options/underlyings", params={"offline": "list"}).json() == {"offline": None, "rows": [{"exchange": "NFO", "name": "NIFTY"}]}
    finally:
        app.dependency_overrides.clear()


# ---------- LIVE18B-005: a share's change is worked out from the two days' unrounded shares ----------
def test_live18b_005_the_long_share_change_is_from_unrounded_shares():
    now = {"fii": {"fut_idx_long": 73516, "fut_idx_short": 141763}}
    was = {"fii": {"fut_idx_long": 65342, "fut_idx_short": 136012}}
    fii = next(r for r in P.participant_view(now, was) if r["id"] == "fii")
    assert fii["fut_idx_long_pct"] == 34.1
    assert fii["fut_idx_long_pct_chg"] == 1.7                      # 34.149 − 32.452; from the rounded 34.1 − 32.5 it read +1.6


# ---------- LIVE18B-013: Net worth's holdings row says "the latest prices", whose time it gives ----------
def test_live18b_013_the_holdings_rule_does_not_say_today():
    src = Path(money_networth.__file__).read_text()
    assert "at today's prices" not in src and '"From My Holdings, at the latest prices"' in src


# ---------- LIVE18B-009: the scan page's first list of scans is the server's own ----------
def test_live18b_009_the_pages_list_of_ready_made_scans_is_the_servers():
    ts = (FRONT / "src" / "lib" / "scanList.ts").read_text()
    body = re.search(r"=\s*(\[[\s\S]*\]);\s*$", ts).group(1)
    assert json.loads(body) == scan_presets.listing()
