"""Release 42, lane m1: a special session seen on the exchange's candles is kept for every process (LIVE7A-019: the 8 Nov Muhurat
session, noted only where the candles were read, was missing from the next day's brief, measured from 6 Nov)."""
from datetime import date

from app import db
from app.data import calendar as C
from app.newsletter import content


def test_a_noted_special_session_is_known_to_another_process(monkeypatch):
    mem = {}
    monkeypatch.setattr(db, "get_setting", lambda k: mem.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: mem.__setitem__(k, v))
    monkeypatch.setattr(C, "_noted", {})
    monkeypatch.setattr(C, "_special", {})
    C.note_session("IN", date(2026, 11, 8))                       # Sunday 8 Nov 2026, seen on the exchange's daily candles
    assert C.SESSIONS_KEY + "IN" in mem
    # another process: nothing noted in its memory, the database has it
    monkeypatch.setattr(C, "_noted", {})
    monkeypatch.setattr(C, "_special", {})
    assert "2026-11-08" in C.special_days("IN")
    assert C.had_session("IN", date(2026, 11, 8)) and not C.is_trading_day("IN", date(2026, 11, 8))
    assert content.previous_trading_day("IN", date(2026, 11, 9)) == date(2026, 11, 8)
    # noted again: no second write
    writes = []
    monkeypatch.setattr(db, "set_setting", lambda k, v: writes.append(k))
    C.note_session("IN", "2026-11-08")
    assert writes == []
