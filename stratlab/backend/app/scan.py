"""Stage 2 + Supertrend ("ST S2") scans over a group of stocks, the ready-made ST S2 strategy, and the daily
watchlist alert.

A scan reads each member's daily candles and reports facts: its Weinstein stage, whether the price is above its
Supertrend and since when, and whether both line up. It never says "buy": the user's own rules decide."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from . import db, leader, run_marks, scan_presets, universes
from .engine.indicators import stage, supertrend
from .intel.net import TTLCache

DAYS = 420                 # enough daily candles for the 150-day average plus its 20-day slope
FRESH = 5                  # a Supertrend flip up within this many candles counts as a fresh signal
MAX = 50
_cache = TTLCache(max_items=4000)
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scan")

ST_S2 = {
    "name": "ST S2: Stage 2 + Supertrend", "tf": "1d", "side": "long", "entryJoin": "all",
    "text": "Buy when the stock is in Stage 2 and the price is above the Supertrend; sell when it crosses back below.",
    # "is above", not "crosses above": the Supertrend often turns up before Stage 2 is confirmed, so entry comes on the
    # first day both are true, and again whenever the price climbs back over the Supertrend while still in Stage 2
    "entry": [{"l": {"t": "stage", "p": 150, "m": 20}, "op": "eq", "r": {"t": "num", "v": 2}},
              {"l": {"t": "price"}, "op": "gt", "r": {"t": "supertrend", "p": 10, "m": 3}}],
    "exit": [{"l": {"t": "price"}, "op": "xb", "r": {"t": "supertrend", "p": 10, "m": 3}}],
    # the Supertrend flip is the stop; a wide % stop only guards against a gap through it
    "risk": {"capital": 500000, "riskPct": 1, "maxAlloc": 20, "sl": 12, "tgt": 0, "brokerage": 20, "slippage": 0.05},
}


def analyse(bars: list[dict]) -> dict | None:
    """Stage, Supertrend state and the ST S2 signal on the latest candle."""
    if len(bars) < 30:
        return None
    df = pd.DataFrame(bars)
    for col in "ohlc":
        df[col] = df[col].astype(float)
    c = df["c"]
    st = supertrend(df, 10, 3)
    stg = stage(c, 150, 20)
    up = (c > st).fillna(False).to_numpy()
    last = len(df) - 1
    flip = 0
    while flip < last and up[last - flip - 1] == up[last]:
        flip += 1
    s = stg.iloc[-1]
    stage_now = None if pd.isna(s) else int(s)
    since = 0
    while stage_now is not None and since < last and stg.iloc[last - since - 1] == s:
        since += 1
    prev = float(c.iloc[-2]) if len(c) > 1 else None
    st_up = bool(up[last])
    in_s2 = stage_now == 2 and st_up
    return {
        "price": float(c.iloc[-1]), "chg": (float(c.iloc[-1]) / prev - 1) * 100 if prev else None,
        "stage": stage_now, "stage_days": since + 1 if stage_now else None,
        "st_up": st_up, "st_days": flip + 1, "st_level": None if pd.isna(st.iloc[-1]) else float(st.iloc[-1]),
        "signal": "fresh" if in_s2 and flip + 1 <= FRESH else "st_s2" if in_s2 else "stage2" if stage_now == 2 else None,
        "t": bars[-1]["t"], "recent": [float(x) for x in c.iloc[-5:]],
        "day_low": float(df["l"].iloc[-1]), "day_high": float(df["h"].iloc[-1]),    # the last session's range
    }


RANK = {"fresh": 0, "st_s2": 1, "stage2": 2, None: 3}


SETTLED_MARKETS = ("US",)  # India's daily candles take the official close in the broker's own cache (kite_service, R8B-001)


def settled_at(market: str, now: datetime | None = None) -> float | None:
    """When the market's latest close settled (its close plus the public pages' settle step), as a timestamp; None for a
    market whose candles aren't held to it here. Candles read before it may carry closing prints still settling."""
    if market not in SETTLED_MARKETS:
        return None
    try:
        from .stock_pages import last_close, settle
        _, at = last_close(market, now)
        return at.timestamp() + settle(market)
    except Exception:                     # no calendar: the cache's own lifetime decides
        return None


def _bars(registry, iid: str) -> list[dict]:
    """A stock's daily candles, kept for 15 minutes; a copy read before its market's close settled is read again once it
    has (R13-005: the US large-cap scan kept NVDA at the provisional $229.48 for half an hour after the 16:00 close, against
    the final $229.28), so the scans, the brief built from them and the company pages say the same close."""
    market = iid.split(":", 1)[0] if ":" in iid else "IN"
    settled = settled_at(market)
    hit = _cache.get(iid)
    if hit is not None:
        at, bars = hit if isinstance(hit, tuple) else (time.time(), hit)
        if settled is None or at >= settled or time.time() < settled:
            return bars
    prov, inst = registry.resolve(iid)
    if not prov or not inst:
        raise LookupError("not found")
    if settled is not None and time.time() >= settled:
        try:                              # the source's own copy too must be from after the settle point
            bars = prov.history(inst, "1d", DAYS, ttl=max(60.0, time.time() - settled))
        except TypeError:                 # a source without its own cache control
            bars = prov.history(inst, "1d", DAYS)
    else:
        bars = prov.history(inst, "1d", DAYS)
    _cache.set(iid, (time.time(), bars), 900)
    return bars


def _label(prov, iid: str) -> str:
    """How a skipped stock is named: its symbol, never the broker's numeric instrument id ("195818241") (R5O-023)."""
    try:
        inst = prov.instrument(iid.split(":", 1)[1]) if prov else None
    except Exception:
        inst = None
    sym = (inst or {}).get("symbol")
    return str(sym) if sym else iid.split(":", 1)[-1]


def _why(e: Exception) -> str:
    text = str(e)[:80]
    return "not enough daily prices yet" if not text or "history" in text.lower() or isinstance(e, (IndexError, TypeError)) else text


def run(registry, market: str, members: list[dict], budget: float | None = None) -> dict:
    """Scan a group: members are {"symbol"} or {"id"}. Rows sorted with fresh ST S2 signals first. With `budget`
    (seconds), the stocks not read by then are left out and listed in "late" rather than waited for."""
    t0 = time.monotonic()
    ids, missing = universes.resolve(registry, market, members[:MAX])
    prov = registry.provider(market)
    names = {}

    def one(iid):
        try:
            res = analyse(_bars(registry, iid))
            inst = prov.instrument(iid.split(":", 1)[1]) if prov else None
            names[iid] = inst or {}
            return iid, res, None
        except Exception as e:     # one member's data problem mustn't sink the rest
            return iid, None, f"{_label(prov, iid)}: {_why(e)}"

    rows, problems, late = [], [], []
    if budget is None:
        done = list(_pool.map(one, ids))
    else:
        jobs = {iid: _pool.submit(one, iid) for iid in ids}
        wait(jobs.values(), timeout=max(0.0, budget - (time.monotonic() - t0)))
        done = [f.result() for f in jobs.values() if f.done()]
        late = [_label(prov, iid) for iid, f in jobs.items() if not f.done()]
        for f in jobs.values():
            f.cancel()                # not started yet: leave the pool to others
    newest = max((str(res["t"])[:10] for _, res, _ in done if res), default=None)
    for iid, res, problem in done:
        if res is None:
            problems.append(problem or f"{_label(prov, iid)}: not enough daily prices yet")
            continue
        if scan_presets.is_stale(res["t"], newest):       # no candle for weeks: its "latest" stage and signal are old
            problems.append(f"{_label(prov, iid)}: no recent daily prices")
            continue
        inst = names.get(iid) or {}
        rows.append({"id": iid, "symbol": inst.get("symbol") or iid.split(":", 1)[-1], "name": inst.get("name"),
                     "currency": inst.get("currency"), **res})
    rows.sort(key=lambda r: (RANK.get(r["signal"], 3), -(r["chg"] or 0)))
    return {"rows": rows, "missing": missing, "problems": problems, **({"late": late} if budget is not None else {}),
            "counts": {k: sum(1 for r in rows if r["signal"] == k) for k in ("fresh", "st_s2", "stage2")}}


def run_preset(registry, market: str, members: list[dict], preset: str) -> dict:
    """One scan preset (scan_presets) over a small group, read live from the daily candles: {"rows" (the stocks that
    match, most recent match first), "checked", "as_of", "missing", "problems"}. Facts only."""
    if preset not in scan_presets.BY_ID:
        raise KeyError(preset)
    ids, missing = universes.resolve(registry, market, members[:MAX])
    prov = registry.provider(market)

    def one(iid):
        try:
            res = scan_presets.evaluate(_bars(registry, iid), only=[preset], live=True)
            inst = (prov.instrument(iid.split(":", 1)[1]) if prov else None) or {}
            return iid, res, inst, None
        except Exception as e:     # one member's data problem mustn't sink the rest
            return iid, None, {}, f"{_label(prov, iid)}: {_why(e)}"

    rows, problems, checked, days = [], [], 0, []
    done = list(_pool.map(one, ids))
    newest = max((res["as_of"] for _, res, _, _ in done if res), default=None)
    for iid, res, inst, problem in done:
        if res is None:
            problems.append(problem or f"{_label(prov, iid)}: not enough daily prices yet")
            continue
        if scan_presets.is_stale(res["as_of"], newest):   # no candle for weeks: its match would read as today's
            problems.append(f"{_label(prov, iid)}: no recent daily prices")
            continue
        checked += 1
        days.append(res["as_of"])
        m = res["matches"].get(preset)
        if m:
            rows.append({"symbol": inst.get("symbol") or iid.split(":", 1)[-1], "name": inst.get("name"), "currency": inst.get("currency"),
                         "price": res["price"], "chg": res["chg"], "as_of": res["as_of"], "days_ago": m["days_ago"], "day": m["day"],
                         "detail": m["detail"]})
    rows.sort(key=lambda r: (r["days_ago"], r["symbol"]))
    return {"rows": rows, "checked": checked, "asked": len(ids) + len(missing), "as_of": max(days, default=None), "missing": missing,
            "problems": problems}


# ---------- the daily watchlist alert ----------
ALERT_KEY = "scanalert:"          # app_settings: scanalert:<uid> = {"uid", "on"}
SEND_AT = {"IN": ("Asia/Kolkata", "16:05"), "US": ("America/New_York", "16:50")}


def alert_on(uid: str) -> bool:
    try:
        return bool(json.loads(db.get_setting(ALERT_KEY + uid) or "{}").get("on"))
    except (ValueError, TypeError):
        return False


def set_alert(uid: str, on: bool):
    db.set_setting(ALERT_KEY + uid, json.dumps({"uid": uid, "on": bool(on)}))


def watchlist_members(uid: str, region: str) -> list[dict]:
    try:
        items = json.loads(db.get_setting(f"watchlist:{uid}") or "{}").get("items") or []
    except (ValueError, TypeError):
        items = []
    return [{"symbol": i["symbol"]} for i in items if i.get("region") == region and i.get("symbol")]


def alert_text(market: str, fresh: list[dict]) -> str:
    names = ", ".join(r["symbol"] for r in fresh[:8]) + (f" and {len(fresh) - 8} more" if len(fresh) > 8 else "")
    return (f"Stage 2 + Supertrend on your {'India' if market == 'IN' else 'US'} watchlist: {names} "
            f"{'is' if len(fresh) == 1 else 'are'} in Stage 2 with the Supertrend turning up. Your rules, not advice.")


class Alerts:
    """Once a day after the close, tell each subscriber which watchlist stocks just gave an ST S2 signal. Each minute
    it also runs `checks` (each fn(now)): the stock alerts people set, checked while their market is open."""

    def __init__(self, registry, notify, can_alert, checks=()):
        self.registry, self.notify, self.can_alert, self.checks = registry, notify, can_alert, list(checks)
        self.last: dict[str, str] = {}
        self.status = {"last_run": None, "sent": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="scan-alerts").start()

    def _loop(self):
        while True:
            if not leader.leading():      # another container leads: it runs this pass
                time.sleep(60)
                continue
            now = datetime.now(ZoneInfo("UTC"))
            for check in self.checks:
                try:
                    check(now)
                except Exception as e:      # the stock alerts failing mustn't stop the daily one
                    print("stock alerts:", e)
            try:
                self.tick(now)
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("scan alerts:", e)
            time.sleep(60)

    def due(self, market: str, now: datetime) -> str | None:
        from .data.calendar import is_trading_day, shifted
        tz, at = SEND_AT[market]
        local = now.astimezone(ZoneInfo(tz))
        at = shifted(market, local.date(), at)
        day = local.date().isoformat()
        if local.strftime("%H:%M") < at or self.last.get(market) == day or not is_trading_day(market, local.date()):
            return None
        st = run_marks.status(f"scanalert-day:{market}", day)
        if st == "done":                   # another run already sent today's (after a restart)
            self.last[market] = day
        return None if st else day         # "running": another container is on it; a quiet one is resumed

    def tick(self, now: datetime):
        for market in SEND_AT:
            day = self.due(market, now)
            if not day:
                continue
            marks = run_marks.claim(f"scanalert-day:{market}", day)      # or the run a restart cut short
            if not marks:
                continue
            sent = 0
            for raw in db.settings_with_prefix(ALERT_KEY):
                try:
                    sub = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not sub.get("on") or marks.seen(sub["uid"]):
                    continue
                marks.beat()
                try:
                    profile = db.get_profile(sub["uid"])
                    members = watchlist_members(sub["uid"], market)
                    if not members or not self.can_alert(profile):
                        continue
                    fresh = [r for r in run(self.registry, market, members)["rows"] if r["signal"] == "fresh" and r["st_days"] == 1]
                    if fresh:
                        marks.record(sub["uid"])         # before the send: a kill in between drops one, never doubles
                        self.notify(profile, "StratLab: Stage 2 + Supertrend signals", alert_text(market, fresh), url="/research/scan")
                        sent += 1
                except Exception as e:             # one user's trouble must not stop the others' alerts
                    print("scan alert failed:", sub.get("uid"), str(e)[:120])
            marks.done()
            self.last[market] = day
            self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
