"""A made-up NAV history for the synthetic statement's flexi cap fund (scheme 900001): weekly NAVs rising from 10 to a
high of 24 on 3 Jun 2024, then easing to 20 on 15 Aug 2024 (the day of its redemption), in the public NAV history
service's answer shape. Other schemes have no records."""
from datetime import date, timedelta

CODE = "900001"


def answer(points: list[tuple[str, float]], name="Example Flexi Cap Fund - Direct Plan - Growth") -> dict:
    return {"data": {"mf_name": "Example Mutual Fund", "scheme_name": "Example Flexi Cap Fund", "date_range": "x",
                     "nav_groups": [{"nav_name": name, "historical_records": [{"date": d, "nav": n, "Plan": "Direct Plan"} for d, n in points]}]}}


def path(start: str, end: str, high_on: str, high: float, low: float = 10.0) -> list[tuple[str, float]]:
    """Weekly NAVs rising from `low` to `high` on `high_on`, then easing to 20 by `end`."""
    a, b, h = date.fromisoformat(start), date.fromisoformat(end), date.fromisoformat(high_on)
    out, d = [], a
    while d <= b:
        n = low + (high - low) * (d - a).days / max(1, (h - a).days) if d <= h else high - (high - 20) * (d - h).days / max(1, (b - h).days)
        out.append((d.isoformat(), round(n, 4)))
        d += timedelta(days=7)
    if out[-1][0] != end:
        out.append((end, 20.0))
    if high_on not in {d for d, _ in out}:          # the high itself, whatever the weekday steps
        out = sorted(out + [(high_on, high)])
    return out


def fetch(code: str, start: str, end: str, first: str = "2018-01-10") -> dict:
    if code != CODE:
        return {}
    return answer([p for p in path(first, "2024-08-15", "2024-06-03", 24.0) if start <= p[0] <= end])
