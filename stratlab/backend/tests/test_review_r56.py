"""Round 56: a change waiting for a look names each circular once."""
from app import main  # noqa: F401  (loads the modules in the order they need)
from app import rules_watch as RW


def test_a_pending_change_names_each_circular_once():
    c = {"date": "October 16, 2026", "subject": "Review of certain aspects of the Closing Auction Session", "url": "u"}
    pending = {"at": "2026-10-16T18:00", "why": "new circular",
               "items": [{**c, "id": "a"}, {**c, "id": "b"}, {**c, "id": "c", "subject": c["subject"] + " "}, {**c, "id": "d"},
                         {"id": "e", "date": "October 15, 2026", "subject": "Revision in lot sizes", "url": "v"}]}
    got = RW._once(pending)
    assert [i["date"] for i in got["items"]] == ["October 16, 2026", "October 15, 2026"]
    assert RW._once(None) is None
