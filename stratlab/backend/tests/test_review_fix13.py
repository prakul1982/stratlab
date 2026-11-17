"""fix13 (LIVE11A, 17-18 Nov 2026): the scored live review of Release 66. Each test fails before its fix and passes after."""
from app import main  # noqa: F401, I001
from app.intel import mood


def _sectors():
    rows = [{"name": f"S{i}", "label": f"Sector {i}", "change_pct": round(1.95 - i * 0.19, 2)} for i in range(16)]
    return {"up": 12, "down": 4, "unchanged": 0, "of": 16, "rows": rows}


def _closed(**kw):
    p = {"region": "IN", "is_open": False, "today": "2026-11-18", "session": "2026-11-17",
         "moves": [{"name": "NIFTY 50", "change_pct": 0.38}, {"name": "SENSEX", "change_pct": 0.52}, {"name": "NIFTY BANK", "change_pct": 1.13}],
         "compare": {"index": "NIFTY 50", "avg_abs": 0.6, "days": 20, "ratio": 0.6, "words": "a smaller move than usual"},
         "breadth": {"group": "NIFTY 500", "live": False, "day": "2026-11-17", "adv": 261, "dec": 238, "unch": 1, "stocks": 500, "pct50": 58.0},
         "sectors": _sectors(), "movers": None,
         "flows": {"as_of": "2026-11-17", "rows": [{"day": "2026-11-17", "fii": 4195, "dii": 197}]},
         "risk": None, "global": None, "calendar": None}
    p.update(kw)
    p["headline"] = mood.headline_of(p["moves"], p["sectors"], p["compare"], mood.same_session(p["breadth"], p["session"]))
    p["lines"] = mood.lines_of(p)
    return p


# ---------- LIVE11A-001: a closed session's re-read never drops a section; its final read is served as it is ----------
def test_a_later_read_of_a_closed_session_keeps_the_sectors_an_earlier_read_had():
    old = _closed(flows={"as_of": "2026-11-16", "rows": [{"day": "2026-11-16", "fii": 4865, "dii": -3519}]})
    assert "12 of 16 sector indices up" in old["headline"]
    new = _closed(sectors=None)                         # 04:35 IST: the broker's quotes off for the night, no sector quotes
    assert "sector" not in new["headline"]
    got = mood.carry_over(old, new)
    assert got["sectors"] == old["sectors"] and "12 of 16 sector indices up" in got["headline"]
    assert any(line.startswith("12 of 16 sector indices rose") for line in got["lines"])
    assert got["flows"]["as_of"] == "2026-11-17"        # the newer flows row the re-read added stays
    assert not mood.verify(got)
    # an older breadth day never replaces a newer one; a read of another session carries nothing
    assert mood.carry_over(old, _closed(breadth={**old["breadth"], "day": "2026-11-16"}))["breadth"]["day"] == "2026-11-17"
    assert mood.carry_over(old, _closed(session="2026-11-18", sectors=None))["sectors"] is None
    assert mood.carry_over({**old, "is_open": True}, new)["sectors"] is None


def test_the_final_read_of_a_closed_session_is_served_without_a_read_on_visit(monkeypatch):
    from app.intel import company
    m = mood.Mood(hub=None)
    m._seeded.add("IN")
    final = _closed()
    assert mood.is_final(final) and mood.missing_parts(final) == []
    m.payloads.put("IN", final, 0.0)                     # read long ago: past every freshness limit
    monkeypatch.setattr(m, "_session_now", lambda region: "2026-11-17")
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(m, "_build_kept", lambda region, force=False: (_ for _ in ()).throw(AssertionError("read again on a visit")))
    got, at = m.get("IN", wait=0)
    assert got["final"] is True and not got.get("refreshing") and got["sectors"] == final["sectors"] and at == 0.0


def test_a_read_that_is_not_final_yet_is_read_again_and_keeps_every_section(monkeypatch):
    m = mood.Mood(hub=None)
    m._seeded.add("IN")
    early = _closed(breadth={"group": "NIFTY 500", "live": True, "day": "2026-11-17", "adv": 261, "dec": 238, "unch": 1, "stocks": 500})
    assert "breadth of 2026-11-17" in mood.missing_parts(early)[0]          # the live round, not the evening's count
    m.payloads.put("IN", early, 0.0)
    monkeypatch.setattr(m, "build", lambda region: _closed(sectors=None))
    monkeypatch.setattr(m, "_keep", lambda region, value: None)
    got = m._build_kept("IN")
    assert got["sectors"] == early["sectors"] and got["final"] is True and got["carried"] == ["sectors"]


# ---------- LIVE11A-002: the US read waits for the breadth count of the session that closed ----------
def test_the_after_close_read_is_done_only_with_that_sessions_breadth(monkeypatch):
    from app import mood_job
    from app.intel import routes
    behind = _closed(region="US", breadth={"group": "S&P 500", "live": False, "day": "2026-11-16", "adv": 145, "dec": 353, "unch": 2, "stocks": 500})
    assert mood.tables_of(behind) == "2026-11-17 without that session's breadth count"

    class Hub:
        def __init__(self, value):
            self.value, self.reads = value, 0
            self.payloads = mood.Mood(hub=None).payloads

        def refresh_now(self, region):
            self.reads += 1
            self.payloads.put(region, self.value)
            return self.value
    hub = Hub(behind)
    monkeypatch.setattr(routes, "mood_hub", lambda: hub)
    hub.payloads.put("US", behind)
    assert mood_job._mood_payload("US", "2026-11-17") != "2026-11-17" and hub.reads == 1     # read again, not done
    hub.value = _closed(region="US", breadth={**behind["breadth"], "day": "2026-11-17", "adv": 75, "dec": 424})
    assert mood_job._mood_payload("US", "2026-11-17") == "2026-11-17" and hub.reads == 2
    assert mood_job._mood_payload("US", "2026-11-17") == "2026-11-17" and hub.reads == 2      # kept and complete: no read


# ---------- LIVE11A-015: a price both cards show is at its newest close on both ----------
def test_a_price_both_markets_show_is_at_its_newest_close_on_both():
    ten = {"label": "US 10-year yield", "symbol": "^TNX", "tag": "yield", "price": 5.12, "change_pct": -0.6, "day": "2026-11-16", "same_day": False, "change_bp": -3}
    vix = {"label": "India VIX", "symbol": "^INDIAVIX", "tag": "vol", "price": 15.52, "change_pct": 1.0, "day": "2026-11-17", "same_day": True}
    india = _closed(risk={"rows": [vix, ten]})
    us = {"risk": {"rows": [{**ten, "price": 5.10, "change_bp": -2, "change_pct": -0.4, "day": "2026-11-17"}]}}
    got = mood.newest_rows(india, us)
    assert got["risk"]["rows"][1]["price"] == 5.10 and got["risk"]["rows"][1]["day"] == "2026-11-17" and got["risk"]["rows"][0] == vix
    assert mood.newest_rows(india, {"risk": {"rows": [{**ten, "day": "2026-11-13"}]}})["risk"]["rows"][1]["price"] == 5.12
