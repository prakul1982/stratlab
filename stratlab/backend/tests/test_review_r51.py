"""Round 51: an AI comparison never stops mid-sentence."""
from app.intel.grounding import whole_sentences


def test_a_read_cut_by_a_cap_or_the_model_ends_at_a_sentence():
    assert whole_sentences("Reliance grew 9.7% in FY26. Reliance uses Jun 2026 vs Jun 2025, while TCS uses Sep 2026", 700) == "Reliance grew 9.7% in FY26."
    assert whole_sentences("A is 2.5x B. C is fine.", 700) == "A is 2.5x B. C is fine."
    long = "One. " * 200
    out = whole_sentences(long, 700)
    assert len(out) <= 700 and out.endswith(".")
    assert whole_sentences("no ending at all", 700) == ""


def test_a_saved_group_run_reads_true_later():
    from app.engine.verdict import restated
    v = {"headline": "x", "summary": "Lost money. NIFTY 50 stocks are today's members (as of 2025): earlier years include …",
         "notes": ["NIFTY 50 stocks are today's members (as of 2025): earlier years include …"]}
    got = restated(v, {})
    assert "today's members" not in got["summary"] and "were the list's members when this test ran" in got["notes"][0]


def test_a_ready_made_group_runs_on_todays_members(monkeypatch):
    from app import main, universes
    seen = {}
    monkeypatch.setattr(universes, "presets", lambda m: [{"id": "nifty50", "name": "NIFTY 50 stocks", "symbols": ["BSE", "TCS"], "count": 2}])

    class Stop(Exception):
        pass

    def check(profile, n):
        seen["n"] = n
        raise Stop()
    monkeypatch.setattr(main, "check_group_size", check)

    class P:
        def ready(self):
            return True
    monkeypatch.setattr(main.markets, "provider", lambda m: P())
    from app.models import Strategy
    st = Strategy(entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 1}}])
    try:
        main.run_group_test({}, st, {"id": "nifty50", "market": "IN", "members": [{"symbol": "WIPRO"}] * 50}, None, 1)
    except Stop:
        pass
    assert seen["n"] == 2
