"""Made-up exchange files in the exchange's own format (participant-wise open interest and volume, the FII/DII cash
numbers) and recorded option chains, for the positioning tests and the browser tests' fake world."""
import random
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

from app import positioning as P

FIXTURES = Path(__file__).parent / "fixtures" / "positioning"
HEAD = ("Client Type,Future Index Long,Future Index Short,Future Stock Long,Future Stock Short\t,Option Index Call Long,"
        "Option Index Put Long,Option Index Call Short,Option Index Put Short,Option Stock Call Long,Option Stock Put Long,"
        "Option Stock Call Short,Option Stock Put Short,Total Long Contracts\t,Total Short Contracts\t")
BASE = {"Client": [229586, 92463, 1985563, 206817, 1773024, 1386440, 1561427, 1641697, 1488617, 657004, 1015411, 371426],
        "DII": [62090, 95010, 104245, 2391380, 0, 0, 0, 0, 0, 0, 24, 0],
        "FII": [41052, 147218, 1144220, 1010327, 322174, 264985, 193624, 165720, 108625, 121262, 159010, 151005],
        "Pro": [64018, 61056, 357286, 142797, 808734, 742436, 1349196, 1186016, 409062, 262006, 632229, 368841]}


def participant_csv(day: date, kind: str = "oi") -> str:
    """A day's file as the exchange writes it: a quoted title line with the date, a header with stray tabs, the four
    participants and a total, CRLF line ends. Numbers drift from day to day (seeded by the day)."""
    rng = random.Random(day.toordinal() * (1 if kind == "oi" else 7))
    rows, tot = [], [0] * 14
    for who, base in BASE.items():
        vals = [int(v * rng.uniform(0.85, 1.15)) if v else 0 for v in base]
        if kind == "vol":
            vals = [v // 3 for v in vals]
        longs = sum(vals[i] for i in (0, 2, 4, 5, 8, 9))
        shorts = sum(vals[i] for i in (1, 3, 6, 7, 10, 11))
        vals += [longs, shorts]
        tot = [a + b for a, b in zip(tot, vals)]
        rows.append(",".join([who, *map(str, vals)]))
    what = "Open Interest (no. of contracts)" if kind == "oi" else "Trading Volumes"
    title = f'"Participant wise {what} in Equity Derivatives as on {day:%b} {day:%d}, {day:%Y}",,,,,,,,,,,,,,'
    return "\r\n".join([title, HEAD, *rows, ",".join(["TOTAL", *map(str, tot)])]) + "\r\n"


def cash_answer(day: date) -> list[dict]:
    """The exchange's provisional FII/DII numbers for a day, as its API sends them (₹ crore, as text)."""
    rng = random.Random(day.toordinal())
    out = []
    for cat in ("DII **", "FII/FPI *"):
        buy, sell = round(rng.uniform(9000, 16000), 2), round(rng.uniform(9000, 16000), 2)
        out.append({"category": cat, "date": day.strftime("%d-%b-%Y"), "buyValue": f"{buy:.2f}", "sellValue": f"{sell:.2f}",
                    "netValue": f"{buy - sell:.2f}"})
    return out


def trading(day: date) -> bool:
    from app.data.calendar import is_trading_day
    return is_trading_day("IN", day)


def published(day: date, today: date) -> bool:
    """Files exist for every trading day up to today (the fake world's exchange publishes at once)."""
    return day <= today and trading(day)


def answer(path: str, today: date | None = None):
    """(status, text or JSON) for an exchange path the positioning feed asks for; None for any other path."""
    import re
    today = today or date.today()
    m = re.fullmatch(r"/content/nsccl/fao_participant_(oi|vol)_(\d{2})(\d{2})(\d{4})\.csv", path)
    if m:
        d = date(int(m.group(4)), int(m.group(3)), int(m.group(2)))
        return (200, participant_csv(d, m.group(1))) if published(d, today) else (404, "Not Found")
    if path in P.CASH_PATHS:
        d = today
        while not trading(d):
            d -= timedelta(days=1)
        return 200, cash_answer(d)
    return None


def chain(spot: float, sigma: float, expiry: str, at: datetime, gap: float = 50, each_side: int = 15, seed: int = 1) -> list[list]:
    """A recorded chain priced with Black's formula at `sigma`, with open interest peaking a few strikes out of the
    money on each side and the day's volumes."""
    rng = random.Random(seed)
    t = max(P.years_to(expiry, at), 1 / 365)
    atm = round(spot / gap) * gap
    rows = []
    for i in range(-each_side, each_side + 1):
        k = atm + i * gap
        c, p = P.black76(spot, k, t, sigma, "CE"), P.black76(spot, k, t, sigma, "PE")
        coi = int(20000 + 300000 * 2.718 ** (-((k - atm - 4 * gap) / (5 * gap)) ** 2) * rng.uniform(0.9, 1.1))
        poi = int(20000 + 260000 * 2.718 ** (-((k - atm + 3 * gap) / (5 * gap)) ** 2) * rng.uniform(0.9, 1.1))
        rows.append([k, round(c - 0.05, 2), round(c + 0.05, 2), round(c, 2), coi, round(p - 0.05, 2), round(p + 0.05, 2),
                     round(p, 2), poi, coi // 10, poi // 10])
    return rows


def record_days(add, name: str, days: list[date], spot: float = 25000.0, gap: float = 50, sigmas: list[float] | None = None,
                spot_of=None):
    """Save the closing recordings (15:25 India time) of the days given, the current and next expiry by the exchange's
    rule (weekly for NIFTY and SENSEX, monthly for the other indices: app/data/expiries.py), through `add(row)`
    (db.add_option_snapshot)."""
    from app.data.expiries import rule_expiries
    for i, d in enumerate(days):
        sigma = (sigmas or [])[i] if sigmas else 0.11 + 0.04 * ((i * 7) % 10) / 10
        at = datetime.combine(d, dtime(15, 25), P.IST)
        s = round(spot_of(at), 2) if spot_of else spot + i * 10        # the day's own level (`spot_of(time)`), else a steady rise
        exps = [e.isoformat() for e in rule_expiries(P.NAMES[name], name, d, 2)]
        for ex in exps:
            add({"taken_at": at.astimezone(timezone.utc).isoformat(), "exchange": P.NAMES[name], "name": name, "expiry": ex,
                 "spot": s, "lot": 75, "chain": chain(s, sigma, ex, at, gap, seed=d.toordinal())})


def weekdays_before(today: date, n: int) -> list[date]:
    out, d = [], today - timedelta(days=1)
    while len(out) < n:
        if trading(d):
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)
