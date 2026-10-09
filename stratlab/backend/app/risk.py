"""One view across every running paper session: what's at stake, today's result, and the worst day so far.

Sessions in different currencies are never added together; each currency gets its own totals. Works on
session snapshots, so single instruments, groups and option structures all count the same way.

The worst day and the deepest fall are read from each session's whole history, not from its minute-by-minute equity
curve, which keeps only the last few hundred points (R8B-002: an options session's curve began at 13:49 on its fourth
day, so that day's whole loss since the start, −₹2,11,285, read as one day's move). A session's day closes come from:
- its closed trades (the P&L after each one, from its start at its capital);
- the closing equity it keeps for every day (`day_equity`, open positions at their marks), which wins for the days it has;
- now, for today."""
from .kite_service import ist_date

END = "T23:59:59"              # a day's close sorts after every trade of that day
KEEP_DAYS = 3660               # day closes a session keeps


def _currency(snap: dict) -> str:
    inst = snap.get("instrument") or {}
    return inst.get("currency") or ("INR" if inst.get("market", "IN") == "IN" else "USD")


def open_value(snap: dict) -> float:
    """What the open positions are worth now: shares or coins at the last price, option legs at their marks."""
    kind = snap.get("kind")
    if kind == "group":
        return sum(abs((m.get("position") or {}).get("qty", 0) * (m.get("price") or 0)) for m in snap.get("members") or [])
    if kind == "options":
        return sum(abs(l.get("qty", 0) * (l.get("mark") or 0)) for l in snap.get("legs") or [] if l.get("open"))
    acct = snap.get("account") or {}
    return abs((acct.get("qty") or 0) * (snap.get("last_price") or 0))


def _daily(curve: list[dict]) -> dict[str, float]:
    """The last equity of each day."""
    out: dict[str, float] = {}
    for p in curve or []:
        if p.get("eq") is not None:
            out[str(p["t"])[:10]] = float(p["eq"])
    return out


def note_days(days: dict | None, curve: list[dict]) -> dict:
    """A session's closing equity of each day ({day: equity}), kept apart from its capped minute curve: the curve's last
    equity of each day it still holds goes in, and days it no longer holds stay (R8B-002)."""
    days = dict(days or {})
    for d, v in _daily(curve).items():
        days[d] = round(v, 2)
    if len(days) > KEEP_DAYS:
        days = dict(sorted(days.items())[-KEEP_DAYS:])
    return days


def closed_list(trades: list[dict]) -> list[list]:
    """[[when it closed, P&L]] for every closed trade (an options trade's "closed", a rule trade's "exit_t")."""
    out = []
    for t in trades or []:
        when = t.get("closed") or t.get("exit_t") if isinstance(t, dict) else None
        if when and t.get("pnl") is not None:
            out.append([str(when), round(float(t["pnl"]), 2)])
    return out


def _series(s: dict, cap: float, eq: float, today: str) -> tuple[dict[str, float], list[tuple[str, float]], bool]:
    """One session's P&L at each day's close and at each point it can be read ({day: pnl}, [(time, pnl)]), and whether
    its history goes back to its start (then the day before its first is its capital)."""
    acct = s.get("account") or {}
    rows = s.get("closed")
    if rows is None:
        rows = closed_list(s.get("trades") or [])
    rows = sorted((str(t), float(p)) for t, p in rows if t)
    realised = acct.get("realised")
    # trades a snapshot no longer lists (it shows the latest ones): their sum starts the running total
    base = float(realised) - sum(p for _, p in rows) if realised is not None and rows else 0.0
    complete = abs(base) < 1.0
    closes: dict[str, float] = {}
    points: list[tuple[str, float]] = []
    cum = base
    for t, p in rows:
        cum += p
        points.append((t, cum))
        closes[t[:10]] = cum
    kept = {**(s.get("day_equity") or {}), **_daily(s.get("equity_curve") or [])}
    for d, v in kept.items():
        if d <= today:
            closes[d] = float(v) - cap
    closes.setdefault(today, eq - cap)
    points += [(d + END, v) for d, v in closes.items()]
    return closes, sorted(points), complete


def _carry(series: dict[str, float] | list[tuple[str, float]], at: str, seed: float) -> float:
    """A series' last value at or before `at` (seed before its first)."""
    items = sorted(series.items()) if isinstance(series, dict) else series
    got = seed
    for k, v in items:
        if k > at:
            break
        got = v
    return got


def summary(snaps: list[dict], today: str | None = None) -> dict:
    today = today or ist_date().isoformat()
    sessions, by_cur = [], {}
    for s in snaps:
        acct = s.get("account") or {}
        cap = float(acct.get("capital") or 0)
        eq = float(acct.get("equity") if acct.get("equity") is not None else cap)
        closes, points, complete = _series(s, cap, eq, today)
        before = [v for d, v in sorted(closes.items()) if d < today]
        start_of_day = cap + before[-1] if before else cap
        row = {"id": s["id"], "name": s.get("name"), "kind": s.get("kind") or "single", "currency": _currency(s),
               "market": (s.get("instrument") or {}).get("market"), "capital": cap, "equity": round(eq, 2),
               "pnl": round(eq - cap, 2), "today": round(eq - start_of_day, 2), "open_value": round(open_value(s), 2),
               "trades": acct.get("trades", 0)}
        sessions.append(row)
        # before its history starts a session counts at its capital when that history is whole, else at its first value
        seed_day = 0.0 if complete else (sorted(closes.items())[0][1] if closes else 0.0)
        seed_pt = 0.0 if complete else (points[0][1] if points else 0.0)
        by_cur.setdefault(row["currency"], []).append((row, closes, points, seed_day, seed_pt))

    currencies = []
    for cur, items in by_cur.items():
        dates = sorted({d for _, closes, _, _, _ in items for d in closes})
        # each session's P&L carried forward to days it has no close
        combined = [(d, sum(_carry(closes, d, seed) for _, closes, _, seed, _ in items)) for d in dates]
        start = sum(seed for _, _, _, seed, _ in items)
        moves = [(d, round(v - (combined[i - 1][1] if i else start), 2)) for i, (d, v) in enumerate(combined)]
        cap = sum(r["capital"] for r, *_ in items)
        # the deepest fall: after every closed trade and at every day's close, from the highest point before it
        times = sorted({t for _, _, points, _, _ in items for t, _ in points})
        peak = cap + sum(seed for *_, seed in items)
        fall = None
        for t in times:
            e = cap + sum(_carry(points, t, seed) for _, _, points, _, seed in items)
            peak = max(peak, e)
            pct = e / peak - 1 if peak else 0.0
            if pct < 0 and (fall is None or pct < fall["pct"]):
                fall = {"pct": pct, "pnl": round(e - peak, 2), "date": t[:10]}
        worst = min(moves, key=lambda m: m[1]) if moves else None
        best = max(moves, key=lambda m: m[1]) if moves else None
        rows = [r for r, *_ in items]
        currencies.append({
            "currency": cur, "sessions": len(rows), "capital": round(cap, 2),
            "equity": round(sum(r["equity"] for r in rows), 2), "pnl": round(sum(r["pnl"] for r in rows), 2),
            "today": round(sum(r["today"] for r in rows), 2), "open_value": round(sum(r["open_value"] for r in rows), 2),
            "worst_day": {"date": worst[0], "pnl": worst[1]} if worst and worst[1] < 0 else None,
            "best_day": {"date": best[0], "pnl": best[1]} if best and best[1] > 0 else None,
            "max_drawdown_pct": round(fall["pct"] * 100, 2) if fall else 0.0,
            "deepest_fall": {"pnl": fall["pnl"], "pct": round(fall["pct"] * 100, 2), "date": fall["date"]} if fall else None,
            "curve": [{"t": d, "pnl": round(v, 2)} for d, v in combined][-180:],
        })
    currencies.sort(key=lambda c: -c["capital"])
    return {"currencies": currencies, "sessions": sorted(sessions, key=lambda r: -r["open_value"])}
