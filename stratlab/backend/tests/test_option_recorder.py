from datetime import datetime, timezone

from app.options.recorder import Recorder, compact, in_hours, parse_targets


class Data:
    def __init__(self, ready=True):
        self._ready = ready
        self.calls = []

    def ready(self):
        return self._ready

    def pick_expiry(self, ex, name, choice):
        return "2026-09-30"

    def chain(self, ex, name, choice, around=10):
        self.calls.append((ex, name, choice))
        if name == "BROKEN":
            raise RuntimeError("quote failed")
        exp = "2026-09-30" if choice == "current" else "2026-10-07"
        return {"expiry": exp, "spot": 25010.5, "lot": 75,
                "rows": [{"strike": 25000.0, "ce": {"bid": 100, "ask": 101, "ltp": 100.5, "oi": 5000}, "pe": None}]}


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_targets_and_hours():
    assert parse_targets("NFO:NIFTY, bfo:sensex,MCX:CRUDEOIL,junk") == [("NFO", "NIFTY"), ("BFO", "SENSEX")]
    assert parse_targets("") == []
    assert in_hours(utc(2026, 9, 24, 4, 0))          # 09:30 IST Thursday
    assert not in_hours(utc(2026, 9, 24, 3, 30))     # 09:00 IST
    assert not in_hours(utc(2026, 9, 26, 5, 0))      # Saturday


def test_compact_rows():
    assert compact({"rows": [{"strike": 100.0, "ce": {"bid": 1, "ask": 2, "ltp": 1.5, "oi": 9}, "pe": None}]}) == \
        [[100.0, 1, 2, 1.5, 9, None, None, None, None]]


def test_records_current_and_next_in_hours_only():
    saved = []
    d = Data()
    r = Recorder(d, saved.append, [("NFO", "NIFTY"), ("NFO", "BROKEN")])
    assert r.run_once(utc(2026, 9, 24, 12, 0)) == 0 and not saved          # 17:30 IST: closed
    assert r.run_once(utc(2026, 9, 24, 4, 0)) == 2
    assert [(s["name"], s["expiry"]) for s in saved] == [("NIFTY", "2026-09-30"), ("NIFTY", "2026-10-07")]
    assert saved[0]["chain"][0][:5] == [25000.0, 100, 101, 100.5, 5000] and saved[0]["spot"] == 25010.5
    assert r.status["today"] == 2 and "BROKEN" in r.status["last_error"]
    assert Recorder(Data(ready=False), saved.append, [("NFO", "NIFTY")]).run_once(utc(2026, 9, 24, 4, 0)) == 0
