"""One view across every running paper session: what's at stake, today's result, and the worst day so far.

Sessions in different currencies are never added together; each currency gets its own totals. Works on
session snapshots, so single instruments, groups and option structures all count the same way."""
from datetime import date


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


def summary(snaps: list[dict], today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    sessions, by_cur = [], {}
    for s in snaps:
        acct = s.get("account") or {}
        cap = float(acct.get("capital") or 0)
        eq = float(acct.get("equity") if acct.get("equity") is not None else cap)
        days = _daily(s.get("equity_curve") or [])
        before = [v for d, v in sorted(days.items()) if d < today]
        start_of_day = before[-1] if before else cap
        row = {"id": s["id"], "name": s.get("name"), "kind": s.get("kind") or "single", "currency": _currency(s),
               "market": (s.get("instrument") or {}).get("market"), "capital": cap, "equity": round(eq, 2),
               "pnl": round(eq - cap, 2), "today": round(eq - start_of_day, 2), "open_value": round(open_value(s), 2),
               "trades": acct.get("trades", 0)}
        sessions.append(row)
        by_cur.setdefault(row["currency"], []).append((row, days))

    currencies = []
    for cur, items in by_cur.items():
        dates = sorted({d for _, days in items for d in days})
        combined = []
        for d in dates:              # each session's P&L carried forward to days it has no candle
            total = 0.0
            for row, days in items:
                past = [v for k, v in days.items() if k <= d]
                total += (days[max(k for k in days if k <= d)] - row["capital"]) if past else 0.0
            combined.append((d, total))
        moves = [(d, round(v - (combined[i - 1][1] if i else 0.0), 2)) for i, (d, v) in enumerate(combined)]
        cap = sum(r["capital"] for r, _ in items)
        peak, dd = cap, 0.0
        for _, v in combined:
            peak = max(peak, cap + v)
            dd = min(dd, (cap + v) / peak - 1 if peak else 0.0)
        worst = min(moves, key=lambda m: m[1]) if moves else None
        best = max(moves, key=lambda m: m[1]) if moves else None
        rows = [r for r, _ in items]
        currencies.append({
            "currency": cur, "sessions": len(rows), "capital": round(cap, 2),
            "equity": round(sum(r["equity"] for r in rows), 2), "pnl": round(sum(r["pnl"] for r in rows), 2),
            "today": round(sum(r["today"] for r in rows), 2), "open_value": round(sum(r["open_value"] for r in rows), 2),
            "worst_day": {"date": worst[0], "pnl": worst[1]} if worst and worst[1] < 0 else None,
            "best_day": {"date": best[0], "pnl": best[1]} if best and best[1] > 0 else None,
            "max_drawdown_pct": round(dd * 100, 2),
            "curve": [{"t": d, "pnl": round(v, 2)} for d, v in combined][-180:],
        })
    currencies.sort(key=lambda c: -c["capital"])
    return {"currencies": currencies, "sessions": sorted(sessions, key=lambda r: -r["open_value"])}
