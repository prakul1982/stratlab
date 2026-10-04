"""Made-up rupees-a-dollar histories for tests (never real rates): SBI's TT buying rate on weekdays from 2020, the RBI
reference rate on weekdays from 2015, each rising a paisa a day so every date has its own rate."""
from datetime import date, timedelta

from app import money_fx


def rate(d: date, base: float = 70.0) -> float:
    return round(base + (d - date(2015, 1, 1)).days * 0.01, 4)


def history(sbi_from: date = date(2020, 1, 1), rbi_from: date = date(2015, 1, 1), to: date = date(2026, 12, 31)) -> dict:
    sbi, rbi = {}, {}
    d = rbi_from
    while d <= to:
        if d.weekday() < 5:
            rbi[d.isoformat()] = rate(d, 69.5)
            if d >= sbi_from:
                sbi[d.isoformat()] = rate(d)
        d += timedelta(days=1)
    return {"sbi": sbi, "rbi": rbi, "at": None}


def seed(**kw):
    """Store the made-up history as the app's own (and fresh, so nothing is fetched)."""
    h = history(**kw)
    money_fx.forget()
    money_fx.save(h["sbi"], h["rbi"])
    return money_fx.load()
