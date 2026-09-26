from app import db


def test_profile_is_cached_briefly_and_dropped_on_update(monkeypatch):
    reads, rows = [], {"u9": {"id": "u9", "plan": "free"}}
    monkeypatch.setattr(db, "get_profile", lambda uid, email=None: reads.append(uid) or dict(rows[uid]))

    class Q:
        def update(self, f): rows["u9"].update(f); return self
        def eq(self, *a): return self
        def execute(self): return type("R", (), {"data": [dict(rows["u9"])]})()
    monkeypatch.setattr(db, "sb", lambda: type("S", (), {"table": lambda self, n: Q()})())
    db.forget_profile("u9")

    a = db.cached_profile("u9")
    a["_plan"] = "mutated"                      # callers add keys; the cached copy must not change
    b = db.cached_profile("u9")
    assert len(reads) == 1 and "_plan" not in b

    db.update_profile("u9", plan="pro")         # a plan change is seen on the very next request
    assert db.cached_profile("u9")["plan"] == "pro" and len(reads) == 2

    monkeypatch.setattr(db, "PROFILE_TTL", -1)  # and it expires on its own
    db.forget_profile("u9")
    db.cached_profile("u9"); db.cached_profile("u9")
    assert len(reads) == 4
