"""R75: Admin's Overview counts are not stored over a forget. A read that began before "Tell me when plans open" (which forgets the
kept counts) used to finish after it and store its older counts, so Admin showed 0 people on the list for 45 seconds."""
from app import main  # noqa: F401  (first: it loads the modules in the order they need)
from app import admin


def test_a_read_that_began_before_a_forget_does_not_store_its_counts(monkeypatch):
    main.forget_overview()
    seen = {"n": 0}
    calls = []

    def stats(month_start, include_test=False, extra=None):
        calls.append(1)
        n = seen["n"]
        if len(calls) == 1:          # while the first read is under way, someone joins the list (which forgets the kept counts)
            seen["n"] = 1
            main.forget_overview()
        return {"plan_interest": n}

    monkeypatch.setattr(admin, "stats", stats)
    monkeypatch.setattr(main, "revenue_since", lambda days=30: {})
    client = object()
    monkeypatch.setattr(main.db, "sb", lambda: client)          # the kept counts name the database client they were read from
    assert main.overview_stats()["plan_interest"] == 0      # the read that began first answers with what it read...
    assert main.overview_stats()["plan_interest"] == 1      # ...but did not keep it: the next read counts the person
    assert main.overview_stats()["plan_interest"] == 1 and len(calls) == 2    # and that one is kept
    main.forget_overview()
