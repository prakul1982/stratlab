"""Round 63 (19 Oct 2026): India's open, live — the backend side, each on the reviewer's own example."""
from datetime import date, datetime, timedelta, timezone

from app import main  # noqa: F401  (loads the app's modules in their order)
from app import market_events as M, positioning, vix

IST = timezone(timedelta(hours=5, minutes=30))
AT = datetime(2026, 10, 19, 9, 33, tzinfo=IST)


def test_the_vix_card_reads_the_next_expiry_on_an_expiry_day(monkeypatch):
    # R63-001: NIFTY ATM IV 34.41% beside India VIX 14.73 at 09:33, the morning its weekly options expire
    def chain_now(od, name, choice, now):
        if choice == "current":
            return {"expiry": "2026-10-19", "taken_at": AT.isoformat(), "source": "live"}, AT, {"atm_iv": 34.41, "atm": 23150}
        return {"expiry": "2026-10-27", "taken_at": AT.isoformat(), "source": "live"}, AT, {"atm_iv": 15.2, "atm": 23150}
    monkeypatch.setattr(positioning, "chain_now", chain_now)
    monkeypatch.setattr(positioning, "chain_series", lambda name, since=None, roll_expiry_day=False: [])
    got = vix.nifty_iv(None, AT)["today"]
    assert (got["iv"], got["expiry"], got["rolled"]) == (15.2, "2026-10-27", True)
    # any other day the nearest expiry is read, as before
    got = vix.nifty_iv(None, AT - timedelta(days=3))["today"]
    assert (got["iv"], got["rolled"]) == (34.41, False)


def test_the_year_line_takes_the_next_expiry_on_expiry_days(monkeypatch):
    days = {"2026-10-16": {"front": "2026-10-20", "x": {"2026-10-20": {"atm_iv": 14.1}, "2026-10-27": {"atm_iv": 14.5}}},
            "2026-10-19": {"front": "2026-10-19", "x": {"2026-10-19": {"atm_iv": 34.4}, "2026-10-27": {"atm_iv": 15.2}}}}
    monkeypatch.setattr(positioning, "chain_history", lambda name: days)
    rolled = positioning.chain_series("NIFTY", roll_expiry_day=True)
    assert [(p["day"], p["expiry"], p["atm_iv"]) for p in rolled] == [("2026-10-16", "2026-10-20", 14.1), ("2026-10-19", "2026-10-27", 15.2)]
    # the PCR and the other history keep the front expiry
    assert positioning.chain_series("NIFTY")[1]["atm_iv"] == 34.4


def test_the_calendar_keeps_past_weeklies_and_shows_sensex_thursdays():
    # R63-006: only 19 and 27 Oct carried an expiry; the SENSEX weekly on 22 Oct and the Tuesdays before were missing
    listed = lambda ex, name: ["2026-10-19", "2026-10-27", "2026-11-03"] if ex == "NFO" else ["2026-10-22", "2026-10-29"]  # noqa: E731
    evs = M.expiry_events(date(2026, 10, 19), listed, date(2026, 10, 1), date(2026, 10, 31))
    by = {}
    for e in evs:
        by.setdefault(e["title"], []).append(e["date"])
    assert by["NIFTY weekly expiry"] == ["2026-10-06", "2026-10-13", "2026-10-19"]
    assert by["Monthly F&O expiry"] == ["2026-10-27"]
    assert by["SENSEX weekly expiry"] == ["2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22"]
    assert by["SENSEX monthly expiry"] == ["2026-10-29"]
    detail = {e["date"]: e["detail"] for e in evs}
    assert "a Monday this time: Tuesday 20 Oct is a market holiday." in detail["2026-10-19"]
    assert detail["2026-10-22"].endswith("(they expire on Thursdays).")
