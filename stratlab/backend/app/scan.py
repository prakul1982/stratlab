"""Stage 2 + Supertrend ("ST S2") scans over a group of stocks, the ready-made ST S2 strategy, and the daily
watchlist alert.

A scan reads each member's daily candles and reports facts: its Weinstein stage, whether the price is above its
Supertrend and since when, and whether both line up. It never says "buy": the user's own rules decide."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from . import db, scan_presets, universes
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


def _bars(registry, iid: str) -> list[dict]:
    hit = _cache.get(iid)
    if hit is not None:
        return hit
    prov, inst = registry.resolve(iid)
    if not prov or not inst:
        raise LookupError("not found")
    bars = prov.history(inst, "1d", DAYS)
    _cache.set(iid, bars, 900)
    return bars


def run(registry, market: str, members: list[dict]) -> dict:
    """Scan a group: members are {"symbol"} or {"id"}. Rows sorted with fresh ST S2 signals first."""
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
            return iid, None, f"{iid.split(':', 1)[-1]}: {str(e)[:80] or e.__class__.__name__}"

    rows, problems = [], []
    for iid, res, problem in _pool.map(one, ids):
        if res is None:
            problems.append(problem or f"{iid.split(':', 1)[-1]}: not enough history")
            continue
        inst = names.get(iid) or {}
        rows.append({"id": iid, "symbol": inst.get("symbol") or iid.split(":", 1)[-1], "name": inst.get("name"),
                     "currency": inst.get("currency"), **res})
    rows.sort(key=lambda r: (RANK.get(r["signal"], 3), -(r["chg"] or 0)))
    return {"rows": rows, "missing": missing, "problems": problems,
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
            res = scan_presets.evaluate(_bars(registry, iid), only=[preset])
            inst = (prov.instrument(iid.split(":", 1)[1]) if prov else None) or {}
            return iid, res, inst, None
        except Exception as e:     # one member's data problem mustn't sink the rest
            return iid, None, {}, f"{iid.split(':', 1)[-1]}: {str(e)[:80] or e.__class__.__name__}"

    rows, problems, checked, days = [], [], 0, []
    for iid, res, inst, problem in _pool.map(one, ids):
        if res is None:
            problems.append(problem or f"{iid.split(':', 1)[-1]}: not enough history")
            continue
        checked += 1
        days.append(res["as_of"])
        m = res["matches"].get(preset)
        if m:
            rows.append({"symbol": inst.get("symbol") or iid.split(":", 1)[-1], "name": inst.get("name"), "currency": inst.get("currency"),
                         "price": res["price"], "chg": res["chg"], "as_of": res["as_of"], "days_ago": m["days_ago"], "day": m["day"],
                         "detail": m["detail"]})
    rows.sort(key=lambda r: (r["days_ago"], r["symbol"]))
    return {"rows": rows, "checked": checked, "as_of": max(days, default=None), "missing": missing, "problems": problems}


# ---------- the daily watchlist alert ----------
ALERT_KEY = "scanalert:"          # app_settings: scanalert:<uid> = {"uid", "on"}
SEND_AT = {"IN": ("Asia/Kolkata", "16:05"), "US": ("America/New_York", "16:20")}


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
        from .data.calendar import is_trading_day
        tz, at = SEND_AT[market]
        local = now.astimezone(ZoneInfo(tz))
        day = local.date().isoformat()
        if local.strftime("%H:%M") < at or self.last.get(market) == day or not is_trading_day(market, local.date()):
            return None
        if db.get_setting(f"scanalert-day:{market}") == day:        # another run already sent today's (after a restart)
            self.last[market] = day
            return None
        return day

    def tick(self, now: datetime):
        for market in SEND_AT:
            day = self.due(market, now)
            if not day:
                continue
            self.last[market] = day
            db.set_setting(f"scanalert-day:{market}", day)
            sent = 0
            for raw in db.settings_with_prefix(ALERT_KEY):
                try:
                    sub = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not sub.get("on"):
                    continue
                profile = db.get_profile(sub["uid"])
                members = watchlist_members(sub["uid"], market)
                if not members or not self.can_alert(profile):
                    continue
                fresh = [r for r in run(self.registry, market, members)["rows"] if r["signal"] == "fresh" and r["st_days"] == 1]
                if fresh:
                    self.notify(profile, "StratLab: Stage 2 + Supertrend signals", alert_text(market, fresh), url="/research/scan")
                    sent += 1
            self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
