"""Round 11 review of the live site (9 Oct 2026): the My Stocks email's price and move, the holiday count in Admin, and Admin's
AI status. Nothing here depends on the time of day: every clock is a fixed instant, India's zone named."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import ai_providers as P, ai_rank as R, db, official_close
from app.ai_catalog import PROVIDERS
from app.config import settings
from app.data import calendar as cal
from app.newsletter import content

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
    content._cache.clear()
    yield store
    official_close.forget()
    content._cache.clear()


def _ist(d: str, hm: str) -> datetime:
    h, m = hm.split(":")
    return datetime.fromisoformat(d).replace(hour=int(h), minute=int(m), tzinfo=IST)


def _bars(n: int = 260, last_day: str = "2026-10-09", last_close: float = 2171.5, prev_close: float = 2077.0):
    """n daily candles ending on `last_day`, the day before closing at `prev_close` (the broker's pre-auction figures)."""
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


# ---------- R11P-002: the My Stocks email's price and move are the site's official close and the pair it is measured from ----------
def _wire(monkeypatch, bars, quote=("2026-10-09T15:59:00+05:30", 2156.0)):
    """The real `_symbol_data` path: the broker's candles come back as cached before the auction, whatever hook was set on them."""
    monkeypatch.setattr(content, "_main", lambda: SimpleNamespace(
        markets=object(), filings_feed=SimpleNamespace(announcements=lambda s, n: []),
        research_hub=SimpleNamespace(news=SimpleNamespace(search=lambda *a, **k: []))))
    monkeypatch.setattr(content.universes, "resolve", lambda registry, region, members: (["IN:2953217"], []))
    monkeypatch.setattr(content.scan, "_bars", lambda registry, iid: [dict(b) for b in bars])
    monkeypatch.setattr(content, "surveillance_lines", lambda s, since: None)
    monkeypatch.setattr(content.deals, "recent_for", lambda s, since: [])
    official_close.setup(None, lambda syms: {"TCS": {"price": quote[1], "at": quote[0]}}, force=True)


def test_my_stocks_email_shows_the_sites_close_and_its_move_even_from_a_pre_auction_candle(monkeypatch, mem):
    """9 Oct 2026, 16:19 IST: the email said TCS 2,171.50 ▲4.60%; the site and NSE say 2,156.00, +3.85% on 2,076.00."""
    official_close.save("2026-10-08", {"TCS": 2076.0})                      # the bhavcopy of the day before
    _wire(monkeypatch, _bars())                                              # 2,171.50 and 2,077.00, the broker's copy
    real = content._symbol_data
    now = _ist("2026-10-09", "16:19")
    monkeypatch.setattr(content, "_symbol_data", lambda r, s, d: real(r, s, d, now=now))
    row = content.stock_row("IN", "TCS", date(2026, 10, 9), False, "2026-10-08T16:19")
    assert row["price"] == 2156.0 and row["change_pct"] == 3.85              # one pair: 2,156.00 against 2,076.00
    assert row["change_pct"] != round((2156.0 / 2077.0 - 1) * 100, 2)       # the day before is the official 2,076.00, not 2,077.00


def test_the_week_is_measured_between_two_official_closes_too(monkeypatch, mem):
    bars = _bars()
    ref_day = bars[-6]["t"][:10]                                             # a week back
    official_close.save(ref_day, {"TCS": 2000.0})
    _wire(monkeypatch, bars)
    real = content._symbol_data
    now = _ist("2026-10-09", "16:19")
    monkeypatch.setattr(content, "_symbol_data", lambda r, s, d: real(r, s, d, now=now))
    row = content.stock_row("IN", "TCS", date(2026, 10, 9), True, "2026-10-02T16:19")
    assert row["price"] == 2156.0 and row["change_pct"] == round((2156.0 / 2000.0 - 1) * 100, 2)


def test_no_official_close_before_the_auction_has_matched_leaves_the_candle(monkeypatch, mem):
    _wire(monkeypatch, _bars())
    got = content._symbol_data("IN", "TCS", date(2026, 10, 9), now=_ist("2026-10-09", "15:25"))
    assert got["bars"][-1]["c"] == 2171.5 and "official" not in got["bars"][-1]


def test_other_regions_and_missing_candles_are_left_alone(mem):
    us = _bars()
    assert content.official_bars("US", "AAPL", us) is us
    assert content.official_bars("IN", "TCS", None) is None
    assert content.official_bars("IN", "TCS", []) == []


def test_with_reference_sets_only_the_stored_close_of_the_reference_day(mem):
    bars = _bars()
    out = official_close.with_reference(bars, "TCS", "2026-10-08")
    assert out is bars                                                       # nothing stored for that day: as it is
    official_close.save("2026-10-08", {"TCS": 2076.0})
    out = official_close.with_reference(bars, "TCS", "2026-10-08")
    assert out[-2]["c"] == 2076.0 and out[-2]["official"] is True and out[-1]["c"] == 2171.5
    assert bars[-2]["c"] == 2077.0 and "official" not in bars[-2]            # the cached copy is never changed in place
    assert official_close.with_reference([], "TCS", "2026-10-08") == []


# ---------- R11P-006: Admin's holiday count says what the owner added by hand ----------
def test_holidays_from_the_exchange_are_not_counted_as_added_by_hand(mem):
    cal._extra.clear()
    exchange = [f"2026-{m:02d}-{d:02d}" for m, d in ((1, 26), (3, 3), (12, 25))]
    mem[cal.AUTO + "IN"] = json.dumps({"days": exchange, "at": "2026-10-09T10:00:00+00:00"})
    assert cal.hand_added("IN") == set()
    mem[cal.SETTING + "IN"] = json.dumps(["2026-12-25", "2027-03-22"])      # one the exchange also lists, one only the owner pasted
    cal._extra.clear()
    assert cal.hand_added("IN") == {"2027-03-22"}
    status = main.calendar_status()
    assert status["by_hand"] == ["2027-03-22"] and "2027-03-22" in status["added"] and "2026-01-26" in status["added"]
    assert status["auto"]["count"] == 3
    cal._extra.clear()


# ---------- R11P-007: Admin System's AI status agrees with its own detail line ----------
@pytest.fixture
def ai_clean(monkeypatch):
    for p in PROVIDERS.values():
        monkeypatch.setattr(settings, p.key_env, "")
        if p.name != "anthropic":
            monkeypatch.setattr(settings, p.model_env, "auto")
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "")
    monkeypatch.setattr(settings, "AI_PROVIDERS", "auto")
    monkeypatch.setattr(settings, "AI_PROVIDERS_RESEARCH", "auto")
    monkeypatch.setattr(P, "_sleep", lambda s: None)


def _view(name):
    return next(p for p in P.admin_view()["providers"] if p["name"] == name)


def test_a_provider_whose_measuring_stopped_on_used_up_credit_is_not_ok_and_working(ai_clean, monkeypatch):
    monkeypatch.setattr(settings, PROVIDERS["huggingface"].key_env, "k-hf")
    monkeypatch.setattr(settings, PROVIDERS["groq"].key_env, "k-groq")
    hf, groq = R.status("huggingface"), R.status("groq")
    hf.last_ok, hf.model = 1_000.0, "some/model"                      # it answered once, hours ago
    hf.ranked_at, hf.rank_error = 2_000.0, "stopped measuring: the free credit is used up"      # and the measuring after it stopped on credit
    groq.last_ok, groq.ranked_at = 3_000.0, 3_000.0
    v = _view("huggingface")
    assert v["result"] == "quota" and v["state"] == "warn" and v["answering"] is False and v["quota"]["limited"] is True
    assert "Working" not in v["state_text"]
    # one sentence: the provider's own words are not repeated in brackets after the same words
    assert v["state_text"] == "Free credit was used up when its models were last measured; it resets on its own."
    assert _view("groq")["state"] == "ok"
    # a good answer after the measuring puts it back to working
    hf.last_ok = 4_000.0
    again = _view("huggingface")
    assert again["result"] == "working" and again["state"] == "ok"


def test_the_measured_quota_line_keeps_a_provider_s_other_words_once():
    assert P._measured_quota_text("stopped measuring: the free credit is used up") == \
        "Free credit was used up when its models were last measured; it resets on its own."
    assert P._measured_quota_text("stopped measuring: HTTP 402: monthly included credits are used up for this account") == \
        "Free credit was used up when its models were last measured (HTTP 402: monthly included credits are used up for this account); it resets on its own."
    assert P._measured_quota_text(None).startswith("Free credit was used up when its models were last measured;")


def test_who_is_asked_puts_a_provider_out_of_credit_last_and_marks_it(ai_clean, monkeypatch):
    for n in ("huggingface", "groq", "mistral"):
        monkeypatch.setattr(settings, PROVIDERS[n].key_env, "k-" + n)
    hf = R.status("huggingface")
    hf.last_ok, hf.ranked_at, hf.rank_error = 1_000.0, 2_000.0, "stopped measuring: the free credit is used up"
    routes = P.admin_view()["routes"]
    for task, r in routes.items():
        flags = [s["out_of_credit"] for s in r["steps"]]
        assert flags == sorted(flags), task                              # the ones out of credit come after the others
        assert all(s["out_of_credit"] == (s["provider"] == "huggingface") for s in r["steps"]), task
    assert any(s["out_of_credit"] for r in routes.values() for s in r["steps"])
