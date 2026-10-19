"""Round 70 (19 Oct 2026): the owner on Chrome the evening before a holiday — the backend side, on the reviewer's examples."""
from app import main  # noqa: F401  (loads the app's modules in their order)
from app.intel import grounding as g

IDX = [{"name": "NIFTY 50", "price": 22888.95, "change_pct": -1.11}, {"name": "SENSEX", "price": 73852.90, "change_pct": -1.17}]


def test_the_market_read_keeps_the_pages_points_and_vix_not_a_headlines():
    # R70-002: "The India VIX jumped 6% … as the Sensex and Nifty fell over 900 points" beside VIX +4.48% and NIFTY −257
    assert not g.index_moves_ok("The India VIX jumped 6%, reflecting sharp investor nervousness as the Sensex and Nifty "
                                "fell over 900 points.", IDX)
    assert g.index_moves_ok("The Sensex fell 874 points and the NIFTY 257 points.", IDX)
    assert not g.index_moves_ok("India VIX spiked 6% today.", IDX)                       # no VIX among the levels given
    assert g.index_moves_ok("India VIX rose 4.48% to 14.69.", IDX + [{"name": "India VIX", "price": 14.69, "change_pct": 4.48}])
    assert g.index_moves_ok("Shares of Tata Steel rose 30 points.", IDX)                # a stock's points are a headline's
    out = g.ground_pulse({"tone": "NIFTY 50 closed at 22,888.95, down 1.11%. The India VIX jumped 6% as the Sensex fell "
                                  "over 900 points."}, IDX, [{"headline": "Sensex crashes 900 points, India VIX spikes 6%"}])
    assert "VIX" not in out["tone"] and "22,888.95" in out["tone"]


def test_a_reads_iso_day_is_written_the_apps_way():
    # R70-010: "a net purchase of ₹1,166 cr as of 2026‑10‑16"
    assert g.app_dates("as of 2026‑10‑16.", None).endswith("Fri, 16 Oct.")


def test_the_paper_list_marks_a_session_at_its_loss_cap(monkeypatch):
    # R70-005: the list said "running" with no word of the cap the session hit
    class Eng:
        halted = True

    class S:
        id, engine = "s1", Eng()
    monkeypatch.setattr(main.manager, "user_running", lambda uid: [S()])
    monkeypatch.setattr(main.db, "user_sessions", lambda uid: [{"id": "s1", "status": "running"}, {"id": "s2", "status": "stopped"}])
    rows = main.list_live(profile={"id": "u1"})
    assert rows[0].get("cap_hit") is True and "cap_hit" not in rows[1]
