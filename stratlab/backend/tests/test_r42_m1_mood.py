"""Release 42, lane m1: Mood's figures dated with their own session (LIVE7A-001), a yield's move in basis points (LIVE7A-023), the day's
close count after the bell (LIVE7A-015), and the index's last close on every plan (LIVE7A-024)."""
import time
from datetime import datetime, timezone

from app import breadth, breadth_live
from app.intel import mood
from tests.test_breadth import IST_OPEN, mem, runner  # noqa: F401  (fixtures)
from tests.test_breadth_live import live, quotes


def test_the_session_is_the_index_levels_own_day():
    levels = [{"name": "S&P 500", "day": "2026-11-10"}, {"name": "NASDAQ", "day": "2026-11-10"}]
    assert mood.session_of(levels, "S&P 500") == "2026-11-10"
    assert mood.session_of([{"name": "NASDAQ", "day": "2026-11-11"}, {"name": "DOW", "day": "2026-11-10"}], "S&P 500") == "2026-11-11"
    assert mood.session_of([], "S&P 500") is None


def test_a_copy_of_an_earlier_session_is_answered_with_its_own_date_and_read_again(monkeypatch):
    # US at 06:42 ET on 12 Nov: the kept read (made before the open on 11 Nov) holds 10 Nov's figures while the index levels are 11 Nov's
    from app.intel import company

    class Hub:
        day = "2026-11-10"

        def indices_now(self, region, wait=0.0):
            return [{"name": "S&P 500", "day": self.day}], 0.0
    hub = Hub()
    m = mood.Mood(hub)
    m._seeded.add("US")
    builds = []
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(m, "build", lambda region: builds.append(region) or {"is_open": False, "today": "2026-11-11", "session": hub.day, "n": len(builds)})
    first, _ = m.get("US", 5.0)
    assert first["session"] == "2026-11-10" and not first.get("refreshing")
    hub.day = "2026-11-11"                                   # a newer session has closed since
    got, _ = m.get("US", 5.0)
    assert got["session"] == "2026-11-10" and got["behind"] == "2026-11-11" and got["refreshing"] is True and got["n"] == 1
    for _ in range(50):
        if m.payloads.kept("US")[1]["n"] == 2:
            break
        time.sleep(0.05)
    again, _ = m.get("US", 5.0)
    assert again["session"] == "2026-11-11" and not again.get("behind")


def test_a_kept_copy_without_a_session_falls_back_to_its_day(monkeypatch):
    from app.intel import company

    class Hub:
        def indices_now(self, region, wait=0.0):
            return [{"name": "NIFTY 50", "day": "2026-11-12"}], 0.0
    m = mood.Mood(Hub())
    m._seeded.add("IN")
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    m.payloads.put("IN", {"is_open": False, "today": "2026-11-11"})
    monkeypatch.setattr(m, "build", lambda region: {"is_open": False, "today": "2026-11-12", "session": "2026-11-12"})
    got, _ = m.get("IN", 5.0)
    assert got["session"] == "2026-11-11" and got["refreshing"] is True


def test_a_yields_move_is_in_basis_points():
    spec = [("US 10-year yield", "^TNX", "yield"), ("Gold", "GC=F", "gold")]
    got = {"^TNX": {"price": 4.98, "prev_close": 4.861, "change_pct": 2.45}, "GC=F": {"price": 2400.0, "change_pct": 0.5}}
    rows = {r["symbol"]: r for r in mood.quote_rows(spec, got, "2026-11-12")}
    assert rows["^TNX"]["change_bp"] == 12 and rows["^TNX"]["change_pct"] == 2.45
    assert "change_bp" not in rows["GC=F"]
    # without a previous close, from the change itself
    rows = mood.quote_rows(spec[:1], {"^TNX": {"price": 4.98, "change_pct": 2.45}}, "2026-11-12")
    assert rows[0]["change_bp"] == 12


AFTER = datetime(2026, 10, 1, 10, 15, tzinfo=timezone.utc)          # 15:45 IST, Thursday 1 Oct 2026: the market has shut


def test_after_the_bell_one_more_round_is_the_days_close_count(mem):  # noqa: F811
    runner().run("IN", IST_OPEN)
    lv = live(mem)
    lv.round("IN", datetime(2026, 10, 1, 9, 45, tzinfo=timezone.utc))      # the 15:15 round
    job = breadth_live.LiveJob(live(mem, q=quotes(up=1010.0, down=101.5)))  # the closing session moved two of them
    assert breadth_live.view("nifty500", AFTER)["as_of"] == "15:15"
    assert job.tick(AFTER) == 1
    v = breadth_live.view("nifty500", AFTER)
    assert v["state"] == "final" and v["as_of"] == "15:30" and v["close"] is True
    assert (v["latest"]["adv"], v["latest"]["dec"]) == (2, 0)          # DOWN closed above its previous close; the close's own count
    assert job.tick(AFTER.replace(minute=30)) == 0                       # once a day
    # not before the closing session's prices are in, and never on a day with no rounds
    job2 = breadth_live.LiveJob(live(mem))
    assert not job2.close_due("IN", datetime(2026, 10, 1, 10, 3, tzinfo=timezone.utc))          # 15:33 IST
    assert not job2.close_due("IN", datetime(2026, 10, 2, 10, 15, tzinfo=timezone.utc))         # no rounds that day


def test_the_index_close_is_in_todays_numbers_for_every_plan(mem):  # noqa: F811
    runner().run("IN", IST_OPEN)
    v = breadth.view("nifty500", full=False)
    assert v["history"] is None
    idx = v["today"]["index"]
    full = breadth.view("nifty500", full=True)["history"]["index"]
    assert idx["value"] == full[-1] and idx["prev"] == full[-2]
