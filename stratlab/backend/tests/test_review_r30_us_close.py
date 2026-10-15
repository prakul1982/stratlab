"""Round 30, the US close (15 Oct 2026): each test is built on what the reviewer saw."""
import base64
from datetime import datetime, timezone

import time_machine

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import scan
from app.intel import ai as A, company as C, routes as research_routes
from app.intel.news import publisher_url
from app.newsletter import content, write

UTC = timezone.utc


# ---------- R30-001: the brief reads the scan's own rows ----------
def _bars(closes):
    return [{"t": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000} for i, c in enumerate(closes)]


def test_the_brief_and_the_scan_agree_on_stage_2_and_the_supertrend(monkeypatch):
    # GOOGL: in Stage 2 for one day, its Supertrend up for 19 days: the scan says "In Stage 2 + Supertrend"
    row = scan.analyse(_bars([100 + i * 0.5 for i in range(200)]))
    googl = {"symbol": "GOOGL", "price": 349.22, "chg": 0.5, **row, "stage": 2, "st_up": True, "st_days": 19, "stage_days": 1, "signal": "st_s2"}
    unh = {"symbol": "UNH", "price": 406.67, "chg": 2.8, **row, "stage": 2, "st_up": False, "st_days": 3, "stage_days": 1, "signal": "stage2"}
    old = {"symbol": "OLD", "price": 10.0, "chg": 0.1, **row, "stage": 2, "st_up": True, "st_days": 19, "stage_days": 40, "signal": "st_s2"}
    monkeypatch.setattr(scan, "run", lambda reg, market, members: {"rows": [googl, unh, old]})
    monkeypatch.setattr(content, "_main", lambda: type("M", (), {"markets": None})())
    got = content.stage2_names("US", False)
    assert [r["symbol"] for r in got["st_s2"]] == ["GOOGL"]          # what the scan's row says: Stage 2 and the Supertrend up
    assert [r["symbol"] for r in got["stage2"]] == ["UNH"]
    assert all(r["symbol"] != "GOOGL" for r in got["stage2"])


def test_the_briefs_lists_are_the_scans_rows_on_the_same_candles(monkeypatch):
    from app import universes
    series = {"AAPL": [100 + i * 0.5 for i in range(200)], "MSFT": [100 + i * 0.5 for i in range(150)] + [175 - i * 0.8 for i in range(50)],
              "NVDA": [200 - i * 0.3 for i in range(190)] + [143 + i * 4 for i in range(10)]}

    class Reg:
        @staticmethod
        def provider(market):
            return None
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: _bars(series[iid.split(":")[1]]))
    monkeypatch.setattr(scan.universes, "resolve", lambda reg, market, members: ([f"US:{m['symbol']}" for m in members], []))
    monkeypatch.setattr(scan, "company_name", lambda *a, **k: "X")
    monkeypatch.setattr(content, "_main", lambda: type("M", (), {"markets": Reg})())
    monkeypatch.setattr(universes, "PRESETS", {**universes.PRESETS, "US": [{"id": "t", "name": "Test", "symbols": list(series)}]})
    res = scan.run(Reg, "US", [{"symbol": s} for s in series])
    got = content.stage2_names("US", True)
    rule = {x["symbol"] for x in got["st_s2"]}
    only = {x["symbol"] for x in got["stage2"]}
    assert not rule & only
    for r in res["rows"]:
        new = min(r["st_days"], r.get("stage_days") or 99) <= 5
        assert (r["symbol"] in rule) == (r["stage"] == 2 and r["st_up"] and new)
        assert (r["symbol"] in only) == (r["stage"] == 2 and not r["st_up"] and (r.get("stage_days") or 99) <= 5)


# ---------- R30-007: the brief names its window ----------
def test_the_brief_says_which_window_new_means():
    f = {"kind": "market", "region": "US", "day": "2026-10-15", "weekly": False,
         "scan": {"group": "20 of the largest US companies", "st_s2": [{"symbol": "LLY"}], "stage2": []}}
    assert "newly matched the Stage 2 + Supertrend rule today." in write.template(f)
    assert write.market_sections(f)[0]["title"].startswith("Newly matched Stage 2 + Supertrend today")
    assert "in the last 5 days" in write.template({**f, "weekly": True})


# ---------- R30-002: the pulse after the close ----------
CLOSE_UTC = datetime(2026, 10, 15, 20, 0, tzinfo=UTC)         # 16:00 EDT


def test_an_index_level_is_never_stamped_after_the_close():
    q = {"price": 7744.06, "change_pct": 0.33, "prev_close": 7718.6, "at": "2026-10-15T20:58:00+00:00"}        # 16:58 ET
    lvl = C.index_level("S&P 500", q, "US", datetime(2026, 10, 15, 21, 0, tzinfo=UTC))
    assert datetime.fromisoformat(lvl["at"]) == CLOSE_UTC and lvl["pre_close"] is False


def test_a_level_from_before_the_close_is_marked_once_the_market_has_closed():
    q = {"price": 7745.46, "prev_close": 7718.6, "at": "2026-10-15T19:32:00+00:00"}                           # 15:32 ET
    assert C.index_level("S&P 500", q, "US", datetime(2026, 10, 15, 20, 16, tzinfo=UTC))["pre_close"] is True
    assert C.index_level("S&P 500", q, "US", datetime(2026, 10, 15, 19, 40, tzinfo=UTC))["pre_close"] is False   # still trading
    close = {**q, "at": "2026-10-15T19:59:58+00:00"}
    assert C.index_level("S&P 500", close, "US", datetime(2026, 10, 15, 20, 16, tzinfo=UTC))["pre_close"] is False


@time_machine.travel(datetime(2026, 10, 15, 20, 16, 41, tzinfo=UTC), tick=False)
def test_the_mood_never_says_closed_at_for_a_level_from_before_the_close(monkeypatch):
    seen = {}

    def fake(system, text, **k):
        seen["facts"] = text
        return '{"tone": "The S&P 500 closed at 7,745.46, up 0.34%.", "hot": [], "flows": [], "themes": []}'
    monkeypatch.setattr(A, "complete", fake)
    q = {"price": 7745.46, "change_pct": 0.34, "prev_close": 7718.6, "at": "2026-10-15T19:32:00+00:00"}
    idx = [C.index_level("S&P 500", q, "US")]
    early = research_routes.before_close_at("US", idx)
    assert early == "15:32 ET"
    out = A.pulse("US", "", idx, [], (None, None), closed=False, before_close=early)
    assert "closed at" not in out["tone"] and "as of 15:32 ET" in seen["facts"] and "The market has closed for the day" not in seen["facts"]
    # with the close's own level the read says closed
    out = A.pulse("US", "", idx, [], (None, None), closed=True)
    assert "The market has closed for the day" in seen["facts"]


def test_a_mood_written_on_a_pre_close_level_is_not_kept_for_the_close():
    row = {"name": "S&P 500", "day": "2026-10-15", "change_pct": 0.34}
    assert research_routes.mood_key([{**row, "pre_close": True}], False) != research_routes.mood_key([{**row, "pre_close": False}], False)


# ---------- R30-004: provisional label ----------
def test_a_settling_level_is_marked_so_the_page_can_say_provisional():
    q = {"price": 7744.06, "prev_close": 7718.6, "at": "2026-10-15T20:00:00+00:00"}
    assert C.index_level("S&P 500", q, "US", datetime(2026, 10, 15, 20, 16, tzinfo=UTC))["settling"] is True


# ---------- R30-006: headline links ----------
def _token(url: str) -> str:
    raw = b"\x08\x13\x22" + bytes([len(url)]) + url.encode() + b"\xd2\x01\x00"
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_a_google_redirect_that_carries_the_story_is_resolved_without_a_request():
    story = "https://www.reuters.com/markets/us/stocks-rise-2026-10-15/"
    assert publisher_url(f"https://news.google.com/rss/articles/{_token(story)}?oc=5") == story
    assert publisher_url("https://www.cnbc.com/x") == "https://www.cnbc.com/x"
    assert publisher_url(None) is None


def test_a_redirect_with_no_story_address_is_plain_text_not_a_link():
    google = "https://news.google.com/rss/articles/CBMi" + "x" * 400 + "?oc=5"
    story = "https://www.reuters.com/markets/us/stocks-rise-2026-10-15/"
    issue = {"id": "market.US.2026-10-15", "kind": "market", "region": "US", "day": "2026-10-15", "weekly": False,
             "subject": "Market Brief US", "summary": "S&P 500 +0.33% today.", "indices": [], "at": "2026-10-15T16:52:00-04:00",
             "sections": [{"title": "Headlines", "items": [
                 {"text": "Wall Street ends higher", "url": google},
                 {"text": "Stocks gain on tech", "url": f"https://news.google.com/rss/articles/{_token(story)}"},
                 {"text": "No address at all", "url": None}]}]}
    html, text = write.render(issue)
    assert "news.google.com" not in html and "news.google.com" not in text
    assert f"{story}" in text or "/news-link/market.US.2026-10-15/1" in text
    assert "/news-link/market.US.2026-10-15/0" not in html and "/news-link/market.US.2026-10-15/2" not in html
    assert "Wall Street ends higher" in html and "No address at all" in html


def test_the_stored_headline_url_is_the_publishers_when_the_token_has_it():
    story = "https://www.reuters.com/markets/us/stocks-rise-2026-10-15/"
    rows = [{"headline": "Wall Street ends higher as tech rallies - US stock market", "url": f"https://news.google.com/rss/articles/{_token(story)}",
             "at": "2026-10-15T19:00:00+00:00", "source": "Reuters"}]
    got = content.pick_headlines("US", rows, "2026-10-15", "2026-10-15")
    assert got and got[0]["url"] == story
