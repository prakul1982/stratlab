"""Backtests in worker processes give the same answer as in the server's own process, and errors come back intact."""
import math
from datetime import datetime, timedelta, timezone

import pytest

from app import compute, research
from app.models import Strategy
from tests.stress_requests import EMA


def bars(n=400):
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [{"t": (t0 + timedelta(days=i)).isoformat(), "o": 100 + 10 * math.sin(i / 9), "h": 102 + 10 * math.sin(i / 9),
             "l": 98 + 10 * math.sin(i / 9), "c": 100 + 10 * math.sin((i + 1) / 9), "v": 1000} for i in range(n)]


def data():
    return {"bars": bars(), "start": 50, "lot": 1, "kind": "flat", "days": 400, "max_days": 3650,
            "inst": {"id": "CSV:X", "symbol": "X", "market": "CSV", "currency": ""}}


def test_a_worker_process_gives_the_same_backtest(monkeypatch):
    s = Strategy(**EMA)
    here = research.run(s, data())
    monkeypatch.setenv("BACKTEST_PROCESSES", "1")
    compute._reset()
    try:
        there = compute.run(s, data())
    finally:
        compute._reset()
    assert there["trades"] == here["trades"] and there["verdict"]["headline"] == here["verdict"]["headline"]
    assert len(there["trades"]) > 0


def test_errors_come_back_from_a_worker_intact():
    import pickle
    e = pickle.loads(pickle.dumps(research.ResearchError(422, "too_few_bars", "Not enough prices.")))
    assert (e.status, e.code, e.message) == (422, "too_few_bars", "Not enough prices.")


def test_in_process_when_workers_are_off(monkeypatch):
    monkeypatch.setenv("BACKTEST_PROCESSES", "0")
    assert compute.run(Strategy(**EMA), data())["verdict"]
