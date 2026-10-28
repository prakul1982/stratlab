"""RC-4 (28 Oct 2026): the blog's research posts and the IPO tracker behind one of them. One test or more for each thing the review found
and fixed (the IPO post counted 62 of 115 issues and put SME issues under "Main board"; the SIP post said nine years of ten)."""
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app import blog, blog_research, ipo

# ---------- RC4-003: the IPO tracker keeps a listed issue's listing-day figures past the refresh window ----------
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def listed_row(rid: str, days_ago: int, **more) -> dict:
    day = (NOW.astimezone(ipo.IST).date() - timedelta(days=days_ago)).isoformat()
    return {"id": rid, "market": "IN", "segment": "mainboard", "name": rid.title(), "symbol": rid.upper(), "listing": day, "open": day, "close": day, "price": 100.0, **more}


def test_an_old_listed_issue_is_read_once_for_its_listing_day_and_then_left_alone(monkeypatch):
    calls = []

    def performance(row, yahoo, today=None, now=None):
        calls.append(row["id"])
        return None if row["id"] == "nodata" else {"issue_price": 100.0, "listing_change_pct": 5.0, "day_change_pct": 8.0, "day_close": 108.0, "change_pct": 9.0, "latest": 109.0}
    monkeypatch.setattr(ipo, "performance", performance)
    monkeypatch.setitem(ipo._wire, "yahoo", lambda: object())
    rows = [listed_row("fresh", 10), listed_row("edge", ipo.PERF_DAYS), listed_row("old", 100), listed_row("nodata", 100),
            listed_row("kept", 110, perf={"day_change_pct": 3.0, "at": "x"})]
    assert ipo.attach_perf(rows, NOW) == 3
    assert sorted(calls) == ["edge", "fresh", "old"] or sorted(calls) == ["edge", "fresh", "nodata", "old"]
    by = {r["id"]: r for r in rows}
    assert by["old"]["perf"]["day_change_pct"] == 8.0 and by["old"]["perf"]["at"]            # the figure the blog's post counts
    assert by["kept"]["perf"] == {"day_change_pct": 3.0, "at": "x"}                           # one it has is not read again
    assert by["nodata"].get("perf") is None and by["nodata"]["perf_tried"] == "2026-10-28"
    calls.clear()
    assert ipo.attach_perf(rows, NOW) == 2                                                  # the recent ones every read; the old one has its figures
    assert sorted(calls) == ["edge", "fresh"] and "old" not in calls and "nodata" not in calls
    calls.clear()
    ipo.attach_perf(rows, NOW + timedelta(days=ipo.PERF_RETRY_DAYS + 1))
    assert "nodata" in calls                                                                # tried again after a week
    assert "old" not in calls and "kept" not in calls


def test_an_issue_not_yet_listed_or_with_no_listing_day_is_not_read(monkeypatch):
    monkeypatch.setattr(ipo, "performance", lambda *a, **k: pytest.fail("a read for an issue that has not listed"))
    monkeypatch.setitem(ipo._wire, "yahoo", lambda: object())
    soon = listed_row("soon", -5, listing_expected=True)
    nolisting = {**listed_row("nolist", 100), "listing": None}
    assert ipo.attach_perf([soon, nolisting], NOW) == 0


# ---------- RC4-003: the IPO post does not call an issue of unknown segment a main board one ----------
def test_a_listed_issue_with_no_segment_is_its_own_line_in_the_post():
    base = {"market": "IN", "price": 100.0, "listing": "2026-10-01", "open": "2026-09-24", "close": "2026-09-26"}
    perf = {"basis": "exchange", "issue_price": 100.0, "day_close": 110.0, "day_change_pct": 10.0}
    rows = [{**base, "id": "a", "name": "Main Co", "symbol": "MAINCO", "segment": "mainboard", "perf": perf},
            {**base, "id": "b", "name": "Unknown Co", "symbol": None, "segment": None, "perf": perf},
            {**base, "id": "c", "name": "Small Co", "symbol": "SMALL", "segment": "sme", "perf": perf}]
    facts_ = blog_research.ipo_facts(rows, NOW)
    assert {f["name"]: f["segment"] for f in facts_} == {"Main Co": "mainboard", "Unknown Co": None, "Small Co": "sme"}
    post = blog_research.ipo_listing_day(facts_, NOW)
    seg = next(b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "Segment")["rows"]
    assert [r[:2] for r in seg] == [["Main board", "1"], ["SME", "1"], ["Segment not recorded", "1"]]
    text = blog.plain_text(post["blocks"])
    assert "an issue whose segment the tracker did not record has a line of its own" in text
    all_known = blog_research.ipo_listing_day([f for f in facts_ if f["segment"]], NOW)
    assert "has a line of its own" not in blog.plain_text(all_known["blocks"]) and "the segment table keeps them apart." in blog.plain_text(all_known["blocks"])


# ---------- RC4-004: the SIP post ----------
def index_series(first: date, last: date) -> dict[str, float]:
    out, d, level, n = {}, first, 10000.0, 0
    while d <= last:
        if d.weekday() < 5:
            n += 1
            level *= 1 + 0.0004 + (0.012 if n % 37 == 0 else 0) - (0.014 if n % 29 == 0 else 0)
            out[d.isoformat()] = round(level, 2)
        d += timedelta(days=1)
    return out


def test_ten_years_less_a_few_days_of_closes_are_ten_years():
    closes = index_series(date(2016, 11, 1), date(2026, 10, 28))                    # what a 3,650-day read of the index gives
    post = blog_research.sip_vs_lump(closes, NOW)
    text = blog.plain_text(post["blocks"])
    assert "The latest 10 years: 1 Nov 2016 to 28 Oct 2026" in text and "The history is 10 years at most" in text
    assert "120 months" in text
    assert "latest 10 years" in post["summary"]
    # nine years of closes are nine, and four are the least a post is made from
    assert "The latest 9 years" in blog.plain_text(blog_research.sip_vs_lump(index_series(date(2017, 11, 1), date(2026, 10, 28)), NOW)["blocks"])
    assert blog_research.sip_vs_lump(index_series(date(2022, 11, 20), date(2026, 10, 28)), NOW) is None


def test_the_post_says_why_the_charges_and_the_deepest_fall_are_the_same_for_both():
    post = blog_research.sip_vs_lump(index_series(date(2016, 11, 1), date(2026, 10, 28)), NOW)
    table = next(b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "")["rows"]
    charges, fall = next(r for r in table if r[0] == "Charges paid"), next(r for r in table if r[0].startswith("Deepest fall"))
    assert charges[1] == charges[2] and fall[1] == fall[2]                           # the engine's own result: both are the same arithmetic
    assert fall[0] == "Deepest fall of the units' price"
    text = blog.plain_text(post["blocks"])
    assert "so it is the same number for the SIP and the lump sum" in text and "Charges are a share of each purchase" in text
    assert not blog_research.advice_words(post)
