"""Security review of the India market-audit fixes (5 Oct 2026): untrusted text and links from the exchanges can't
stall or crash a check, a failing check can't pin the background audit to one company, and the BSE year-by-year
filings fallback stays bounded."""
import time
from datetime import datetime, timedelta, timezone

from app import audit, deepdive
from app.intel import filings as F


# ---------- a source's error message is untrusted and can be long: stripping "Try again" stays linear ----------
def test_plain_is_fast_on_a_long_message_and_still_strips_try_again():
    assert audit._plain("The exchange feed is busy. Try again in a minute.") == "The exchange feed is busy"
    for s in (" " * 60000 + "x", "Try again " * 6000 + ".x", ("Try again" + "a" * 20) * 3000 + ".x"):
        t = time.monotonic()
        audit._plain(s)
        assert time.monotonic() - t < 0.5


# ---------- a filing's PDF link is untrusted: a malformed one can't break every deep dive of the company ----------
BAD = [{"url": "https://[nsearchives.nseindia.com/corporate/ACME_Q1FY27ConcallTranscript.pdf", "at": "2026-08-01T19:00",
        "subject": "Analysts/Institutional Investor Meet/Con. Call Updates", "category": "concall", "text": ""},
       {"url": "https://nsearchives.nseindia.com/corporate/ACME_Q1FY27_Investor_Presentation.pdf", "at": "2026-08-01T18:00",
        "subject": "Investor Presentation", "category": "presentation", "text": ""}]


def test_malformed_filing_link_is_read_as_words_not_an_error():
    assert deepdive._file_words(BAD[0]["url"]).strip()
    kinds = [d["kind"] for d in deepdive.documents(BAD)]
    assert "presentation" in kinds and "transcript" in kinds
    assert deepdive.meetings(BAD, "2026-01-01T00:00") == {"meets": 1, "calls": 1, "calls_due": 1, "shareholder": 0, "filed": 2}


# ---------- one check that throws can't hold the background audit on the same company forever ----------
def test_a_check_that_throws_is_stored_and_the_audit_moves_on(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        listing = [{"symbol": s, "name": s, "listed": (now - timedelta(days=d)).date().isoformat()}
                   for s, d in (("AAA", 1), ("BBB", 2))]
        calls = []

        def check(sym):
            calls.append(sym)
            if sym == "AAA":
                raise ValueError("unexpected page")
            return {"symbol": sym, "name": sym, "seconds": 0.1, "issues": []}
        a = audit.MarketAudit(lambda: listing, check, pause=0)
        a.set_enabled(True)
        assert a.step() == "AAA"
        assert a.rows["AAA"]["issues"][0]["level"] == "error"           # a finding, retried later at the batches' pace
        assert a.step() == "BBB" and calls == ["AAA", "BBB"]
    finally:
        w["close"]()


def test_offline_broker_pauses_without_checking_anything(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        listing = [{"symbol": "AAA", "name": "AAA", "listed": datetime.now(timezone.utc).date().isoformat()}]
        calls = []
        a = audit.MarketAudit(lambda: listing, lambda s: calls.append(s), pause=0, ready_fn=lambda: False)
        a.set_enabled(True)
        assert [a.step() for _ in range(5)] == [None] * 5 and calls == []
        assert a.status()["paused"] == "offline"
    finally:
        w["close"]()


# ---------- BSE's year-by-year fallback: a bounded number of requests ----------
def test_bse_year_by_year_fallback_is_bounded():
    b = F.BSEFilings()
    pages = []
    b._page = lambda code, frm, to, page: pages.append((frm, to, page)) or {"Table": []}
    assert b.announcements("500001", 366 * 5) == []
    assert len(pages) <= 7                       # the whole window, then a year at a time
    assert all(frm <= to for frm, to, _ in pages)
