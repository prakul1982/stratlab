"""IA-2 items 40 and 41 (owner, 30 Oct: an IPO page showed a red "Today's summary limit is reached"): since SUMMARY_READER went to 2,
the scheduled catch-up re-summarised every old document and used up the whole day's cap, so a person opening an IPO was turned away.
Now a person always gets the summary written on the spot (counted apart, never capped); the cap is the catch-up's alone, and the
catch-up takes the issues people look at first (open, upcoming, just listed), the old listed ones last. Admin shows both counts and
the backlog."""
import json

from app import admin_jobs, db, ipo as I, ipo_docs as D
from tests.test_ipo import NOW, by_id, docs, headers, quote_ai, read_all, w  # noqa: F401  (fixtures)


def test_a_person_gets_the_summary_even_when_the_days_cap_is_used_up(docs, monkeypatch):  # noqa: F811
    read_all(docs)
    quote_ai(monkeypatch)
    day = I._ai_day()
    db.set_setting("ipo:ai:" + day, str(I.AI_PER_DAY))                      # the catch-up spent the whole cap today
    r = docs["client"].post("/invest/ipos/in-bonfig/summary", headers=headers("basic-token"))
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["state"] == "ready"
    # counted apart, for Admin; the catch-up's count is untouched
    assert db.get_setting("ipo:ai:asked:" + day) == "1" and db.get_setting("ipo:ai:" + day) == str(I.AI_PER_DAY)
    assert "ai_limit" not in json.dumps(r.json())


def test_the_cap_holds_the_scheduled_catch_up_only(docs, monkeypatch):  # noqa: F811
    read_all(docs)
    calls = []
    quote_ai(monkeypatch, calls)
    job = I.Job(sleep=lambda s: None)
    job.read_docs(NOW, limit=6)                                             # reads documents; writes up to two summaries
    made = len(calls)
    db.set_setting("ipo:ai:" + I._ai_day(), str(I.AI_PER_DAY))
    job.read_docs(NOW, limit=6)
    assert len(calls) == made                                               # nothing more today
    assert any("catch-up limit" in p and "still gets its summary" in p for p in job.status["problems"])


def test_the_catch_up_takes_the_issues_people_look_at_first(docs, monkeypatch):  # noqa: F811
    read_all(docs)
    # every document read first, so the catch-up has a choice of all of them
    for m in ("IN", "US"):
        for r in I.load(m)["rows"]:
            d = I.doc_to_read(r)
            if d and not I.facts_of(d):
                try:
                    I.read_doc(r, d, None)
                except Exception:
                    pass
    waiting = [r for m in ("IN", "US") for r in I.load(m)["rows"] if (d := I.doc_to_read(r)) and (f := I.facts_of(d)) and f.get("excerpt") and not I.summary_of(d)]
    ranks = sorted(I._catch_up_rank(r, NOW) for r in waiting)
    assert len(set(ranks)) >= 2, ranks                                      # the world has issues at more than one stage
    quote_ai(monkeypatch)
    I.Job(sleep=lambda s: None).read_docs(NOW, limit=0)
    done = [r for r in waiting if I.summary_of(I.doc_to_read(r))]
    assert len(done) == 2
    assert sorted(I._catch_up_rank(r, NOW) for r in done) == ranks[:2]       # the two at the front of the queue, never an old listed one before them


def test_the_order_open_upcoming_just_listed_filed_old_listed(monkeypatch):
    old, recent = NOW.date().replace(year=NOW.year - 1).isoformat(), NOW.date().isoformat()
    rank = {}
    for st in ("open", "closed", "upcoming", "filed", "listed"):
        monkeypatch.setattr(I, "stage_of", lambda r, n=None, s=st: s)        # the stage alone decides here
        rank[st] = I._catch_up_rank({"listing": recent}, NOW)
        if st == "listed":
            rank["listed long ago"] = I._catch_up_rank({"listing": old, "priced": old}, NOW)
    assert rank == {"open": 0, "closed": 0, "upcoming": 1, "listed": 2, "filed": 3, "listed long ago": 4}


def test_admin_shows_todays_counts_and_the_backlog(docs, monkeypatch):  # noqa: F811
    read_all(docs)
    day = I._ai_day()
    db.set_setting("ipo:ai:" + day, "37")
    db.set_setting("ipo:ai:asked:" + day, "4")
    got = I.ai_counts()
    assert got["scheduled"] == 37 and got["asked"] == 4 and got["cap"] == I.AI_PER_DAY == 120     # the cap is not raised
    assert got["waiting"] > 0 and got["days"] == -(-got["waiting"] // 120)
    row = next(r for r in admin_jobs.rows() if r["id"] == "ipo")
    assert "AI summaries today: 37 of 120 by the catch-up, 4 written when someone opened an IPO (never capped)." in row["note"]
    assert f"{got['waiting']} document" in row["note"] and "at the catch-up's 120 a day" in row["note"]


def test_the_summary_reader_is_still_two():
    assert D.SUMMARY_READER == 2
