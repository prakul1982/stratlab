"""Round 93 (24 Oct 2026, emails): a weekly's headlines say their day, a headline cut inside an amount ends before it,
another country's credit rating stays out of the US brief, the sample receipt's number reads as a sample, every owner test
email fits in one hour, and the events reminder sample falls on a weekday."""
from datetime import date, datetime, timezone

from app import email_previews, lifecycle, main
from app.newsletter import content as C, write as W


def _heads(weekly):
    f = {"region": "IN", "weekly": weekly, "kind": "market",
         "headlines": [{"headline": "Sensex drops 460 points today", "url": "https://example.com/a", "at": "2026-10-22T10:00:00Z", "source": "ET"}]}
    return next(s for s in W.market_sections(f) if s["title"] == "Headlines")["items"]


def test_a_weekly_headline_says_its_day_and_keeps_its_own_title():
    item = _heads(True)[0]
    assert item["text"] == "Sensex drops 460 points today" and item["day"] == "Thu 22 Oct"
    assert W._row(item).title == "Thu 22 Oct: Sensex drops 460 points today"
    daily = _heads(False)[0]
    assert "day" not in daily and W._row(daily).title == "Sensex drops 460 points today"


def test_a_headline_cut_inside_an_amount_ends_before_it():
    cut = "Why did market fall today? Sensex drops 460 points, Nifty closes below 22,700. Key factors behind Rs 3"
    assert C.tidy_title(cut) == "Why did market fall today? Sensex drops 460 points, Nifty closes below 22,700. Key factors behind…"
    whole = "Reliance Industries posts quarterly profit growth and raises its dividend payout to Rs 10"
    assert C.tidy_title(whole) == whole                       # a whole amount at the end stays


def test_another_countrys_credit_rating_stays_out_of_the_us_brief():
    assert C.other_region("US", "Moody's holds steady on France's credit rating as budget talks drag on")
    assert not C.other_region("US", "Moody's holds the US credit rating steady")
    assert not C.other_region("IN", "Moody's holds steady on France's credit rating")


def test_the_sample_receipt_number_reads_as_a_sample(monkeypatch):
    from app import invoices
    monkeypatch.setattr(invoices, "seller", lambda: {**{f: "" for f in invoices.FIELDS}, "prefix": "SL"})
    assert lifecycle.sample_invoice(datetime(2026, 10, 24, tzinfo=timezone.utc))["number"] == "SL/2026-27/SAMPLE"


def test_every_owner_test_email_fits_in_one_hour():
    assert main.TEST_MAILS_HOUR >= len(lifecycle.EMAILS) + 1


def test_the_events_reminder_sample_is_for_a_weekday(monkeypatch):
    seen = []
    from app import market_events as M
    monkeypatch.setattr(email_previews, "_today", lambda: date(2026, 10, 24))            # a Saturday
    real = M.reminder_text
    monkeypatch.setattr(M, "reminder_text", lambda evs, n, day: seen.append(day) or real(evs, n, day))
    email_previews._events()
    assert seen == [date(2026, 10, 26)]
