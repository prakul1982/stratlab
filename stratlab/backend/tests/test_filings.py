"""Exchange filings: red-flag rules, the timeline, the 3-month summary, and the exchange session handling."""
import json
from datetime import datetime

import httpx
import pytest

from app.intel import filings as F
from app.intel.net import SourceError


def row(desc, text="", when="2026-09-20 18:10:05", seq="1", url="https://nsearchives.nseindia.com/corporate/x.pdf"):
    return {"symbol": "ABC", "desc": desc, "attchmntText": text, "sort_date": when, "seq_id": seq, "attchmntFile": url}


@pytest.mark.parametrize("desc,text,cat,sev", [
    ("Qualified Institutions Placement", "The company has opened its QIP issue", "qip", "red"),
    ("Preferential Issue of shares", "", "preferential", "red"),
    ("Updates", "Board approved raising of funds up to Rs 500 crore", "fund_raise", "red"),
    ("Disclosure under SEBI Takeover Regulations", "Creation of pledge on promoter shares, Regulation 31", "pledge", "red"),
    ("Change in Auditors", "Resignation of the Statutory Auditor with effect from today", "auditor_resign", "red"),
    ("Change in Directorate", "Resignation of Mr X as Independent Director", "kmp_resign", "amber"),
    ("Credit Rating", "CRISIL has downgraded the long-term rating to BBB", "rating_down", "red"),
    ("Credit Rating", "ICRA has reaffirmed the rating at AA", "rating", "info"),
    ("Outcome of Board Meeting", "Financial Results for the quarter ended June 30, 2026", "results", "info"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Transcript of the earnings call", "concall", "info"),
    ("Copy of Newspaper Publication", "", "other", "info"),
])
def test_rules(desc, text, cat, sev):
    assert F.classify(desc, text) == (cat, sev)


def test_timeline_is_newest_first_deduped_and_safe():
    items = F.normalise([
        row("Dividend", when="2026-08-01 10:00:00", seq="a"),
        row("Qualified Institutions Placement", when="2026-09-01 10:00:00", seq="b"),
        row("Qualified Institutions Placement", when="2026-09-01 10:00:00", seq="b"),      # the same filing twice
        row("No date", when="", seq="c"),
        row("Bad link", when="2026-07-01 10:00:00", seq="d", url="javascript:alert(1)"),
        "junk",
    ])
    assert [i["id"] for i in items] == ["b", "a", "d"]
    assert items[0]["label"] == "QIP (fund raise)" and items[0]["url"].startswith("https://")
    assert items[2]["url"] is None


def test_three_month_summary_flags_fund_raise():
    items = F.normalise([row("Qualified Institutions Placement", when="2026-08-10 10:00:00", seq="1"),
                         row("Resignation of CFO", when="2026-09-10 10:00:00", seq="2"),
                         row("Preferential issue", when="2026-01-10 10:00:00", seq="3"),       # older than 3 months
                         row("Dividend", when="2026-09-12 10:00:00", seq="4")])
    s = F.summarise(items, now=datetime(2026, 9, 30))
    assert s["total"] == 3 and s["red"] == 1 and s["amber"] == 1
    assert s["fund_raise"] and s["fund_raise_last"].startswith("2026-08-10")
    assert {f["category"] for f in s["flags"]} == {"qip", "kmp_resign"}


def transport(pages: list):
    """Serves the home page (setting a cookie) and then each queued API response in turn."""
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.url.path, req.headers.get("cookie")))
        if req.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "nsit=abc; Path=/"})
        status, body = pages.pop(0)
        return httpx.Response(status, text=body if isinstance(body, str) else json.dumps(body))
    return httpx.MockTransport(handler), calls


def test_primes_cookies_and_retries_once_after_401():
    t, calls = transport([(401, "{}"), (200, [row("Dividend")])])
    feed = F.NSEFilings(transport=t)
    items = feed.announcements("ABC")
    assert len(items) == 1 and items[0]["category"] == "dividend"
    assert [c[0] for c in calls] == ["/", "/api/corporate-announcements", "/", "/api/corporate-announcements"]
    assert calls[1][1] and "nsit=abc" in calls[1][1]
    assert feed.announcements("ABC") == items and len(calls) == 4          # cached


def test_blocked_page_is_a_clear_error():
    t, _ = transport([(200, "<html>Access Denied</html>")])
    with pytest.raises(SourceError) as e:
        F.NSEFilings(transport=t).announcements("ABC")
    assert "blocking" in str(e.value)


def test_accepts_wrapped_data():
    t, _ = transport([(200, {"data": [row("Buyback offer")]})])
    assert F.NSEFilings(transport=t).announcements("ABC")[0]["category"] == "buyback"


class FakeFeed:
    def __init__(self, by_symbol):
        self.by_symbol, self.cache = by_symbol, F.TTLCache()

    def announcements(self, sym, days=F.LOOKBACK_DAYS):
        if sym not in self.by_symbol:
            raise SourceError("the exchange", "The exchange has nothing for that.")
        return F.normalise(self.by_symbol[sym])


@pytest.fixture
def store(monkeypatch):
    from app import db
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "settings_with_prefix", lambda p, limit=1000: [v for k, v in kv.items() if k.startswith(p)])
    monkeypatch.setattr(db, "get_profile", lambda uid: {"id": uid})
    return kv


def recent(days_ago, hour=19):
    from datetime import timedelta
    return (F.ist_now() - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")


def test_endpoints_are_pro_and_cover_the_watchlist(monkeypatch, store):
    from fastapi.testclient import TestClient
    from app import main
    from app.config import settings
    for k, v in (("RAZORPAY_KEY_ID", "rzp_test_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)
    feed = FakeFeed({"ABC": [row("Qualified Institutions Placement", when=recent(10), seq="1"), row("Dividend", when=recent(3), seq="2")],
                     "XYZ": [row("Dividend", when=recent(5), seq="3")]})
    monkeypatch.setattr(main, "filings_feed", feed)
    store["watchlist:u1"] = json.dumps({"items": [{"region": "IN", "symbol": "XYZ"}, {"region": "IN", "symbol": "ABC"},
                                                  {"region": "IN", "symbol": "NOPE"}, {"region": "US", "symbol": "AAPL"}]})
    who = {"p": {"id": "u1", "plan": "free", "_plan": "free"}}
    main.app.dependency_overrides[main.current_profile] = lambda: who["p"]
    c = TestClient(main.app)
    try:
        assert c.get("/research/filings/ABC").status_code == 402
        who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
        one = c.get("/research/filings/ABC").json()
        assert one["summary"]["fund_raise"] and one["items"][0]["category"] == "dividend"
        assert c.get("/research/filings/NOPE").status_code == 502
        wl = c.get("/research/filings").json()
        assert [r["symbol"] for r in wl["rows"]] == ["ABC", "XYZ"] and wl["rows"][0]["flags"][0]["category"] == "qip"
        assert len(wl["problems"]) == 1 and wl["alerts"] is False
        assert c.put("/research/filings/alerts", json={"on": True}).json() == {"alerts": True}
        assert c.get("/research/filings").json()["alerts"] is True
    finally:
        main.app.dependency_overrides.clear()


def test_daily_alert_sends_only_new_flags_once(monkeypatch, store):
    from datetime import timedelta
    rows = {"ABC": [row("Qualified Institutions Placement", when=recent(40), seq="old")]}
    feed = FakeFeed(rows)
    store["watchlist:u1"] = json.dumps({"items": [{"region": "IN", "symbol": "ABC"}]})
    F.set_alert("u1", True)                        # "seen" starts now: the older QIP isn't news
    sent = []
    job = F.Alerts(feed, notify=lambda p, s, t, url: sent.append(t), can_alert=lambda p: True)
    evening = datetime.now(F.IST).replace(hour=20, minute=45)
    rows["ABC"].append(row("Creation of pledge by promoter", when=recent(0, hour=0), seq="new"))
    rows["ABC"][-1]["sort_date"] = (F.ist_now() + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    job.tick(evening)
    job.tick(evening)
    assert len(sent) == 1 and "ABC: Promoter pledge" in sent[0] and "QIP" not in sent[0] and "not advice" in sent[0]
    store.pop("filingalert-day")                    # next evening
    job.last_day = None
    job.tick(evening)
    assert len(sent) == 1                           # nothing new since
