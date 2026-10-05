"""Paper trading of option structures on live quotes.

Nothing here models a premium: every fill is the real bid (when selling) or ask (when
buying) from the exchange at that moment, less any extra slippage the user sets, and
open legs are marked at what closing them would get. The engine is a state machine
fed one snapshot of quotes at a time, so tests can drive it with made-up quotes.

A position still open when its contracts expire (the square-off set after the derivatives close, or the session down
at the time) is settled the way the clearing corporation settles it: each leg at its intrinsic value against the
settlement price, the underlying's official close on the expiry day (since 3 Aug 2026 set by the closing auction for
stocks with derivatives and, through them, for indices; data/sessions.py). No brokerage on settlement; the STT on
exercised options is not modelled."""
import math
from datetime import datetime, timedelta

from ..data import sessions
from ..engine import costs as C
from ..models import OptionStrategy

TICK = 0.05


class Contracts:
    """The option contracts of one underlying and expiry."""

    def __init__(self, rows: list[dict], lot: int, expiry: str, exchange: str):
        # rows: {"opt": "CE"|"PE", "strike": float, "symbol": str}
        self.expiry, self.lot, self.exchange = expiry, int(lot), exchange
        self.by = {(r["opt"], float(r["strike"])): r for r in rows}
        self.strikes = sorted({float(r["strike"]) for r in rows})

    def key(self, opt: str, strike: float) -> str | None:
        r = self.by.get((opt, float(strike)))
        return f"{self.exchange}:{r['symbol']}" if r else None

    def step(self, around: float) -> float:
        """The gap between strikes near a price."""
        s = self.strikes
        if len(s) < 2:
            return 1.0
        i = min(range(len(s)), key=lambda j: abs(s[j] - around))
        gaps = [b - a for a, b in zip(s[max(0, i - 3):i + 3], s[max(1, i - 2):i + 4]) if b > a]
        return min(gaps) if gaps else s[1] - s[0]

    def atm(self, spot: float) -> float:
        return min(self.strikes, key=lambda k: (abs(k - spot), k))

    def strike_for(self, atm: float, opt: str, offset: float, unit: str) -> float | None:
        """The strike `offset` away from the money: up for calls, down for puts."""
        s = self.strikes
        sign = 1 if opt == "CE" else -1
        if unit == "points":
            target = atm + sign * offset
            return min(s, key=lambda k: (abs(k - target), k))
        i = s.index(atm) + sign * int(round(offset))
        return s[i] if 0 <= i < len(s) else None


def _hm(t: str) -> tuple[int, int]:
    h, m = t.split(":")
    return int(h), int(m)


def _at(now: datetime, t: str) -> datetime:
    h, m = _hm(t)
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def fill_price(q: dict | None, side: str, slip_ticks: int) -> float | None:
    """What an order fills at: the bid when selling, the ask when buying, falling back to the last price."""
    if not q:
        return None
    best = q.get("bid") if side == "sell" else q.get("ask")
    px = best if best and best > 0 else q.get("ltp")
    if not px or px <= 0:
        return None
    px += (-1 if side == "sell" else 1) * slip_ticks * TICK
    return max(round(px, 2), TICK)


class OptionsEngine:
    def __init__(self, s: OptionStrategy, state: dict | None = None, margin_fn=None, freeze_default: int = 0,
                 settle_fn=None):
        self.s = s
        self.margin_fn = margin_fn            # legs -> margin needed, or None when it can't be had
        self.settle_fn = settle_fn            # expiry -> the settlement price (the underlying's official close), or None
        self.freeze = s.costs.freeze or freeze_default
        self.kind = {"MCX": "in_mcx_opt", "CDS": "in_cds_opt", "BFO": "in_bse_opt"}.get(s.exchange, "in_opt")
        st = state or {}
        self.cash = st.get("cash", s.sizing.capital)
        self.pos = st.get("pos")
        self.trades = st.get("trades", [])
        self.events = st.get("events", [])
        self.day = st.get("day")
        self.entries_today = st.get("entries_today", 0)
        self.day_realised = st.get("day_realised", 0.0)
        self.halted = st.get("halted", False)
        self.cool_until = st.get("cool_until")
        self.note = st.get("note", "")
        self.used_signal = st.get("used_signal")    # the rules' trade we last acted on, so a stop doesn't re-enter it

    def dump(self) -> dict:
        return {"cash": self.cash, "pos": self.pos, "trades": self.trades[-500:], "events": self.events[-400:],
                "day": self.day, "entries_today": self.entries_today, "day_realised": self.day_realised,
                "halted": self.halted, "cool_until": self.cool_until, "note": self.note, "used_signal": self.used_signal}

    def legs_for(self, direction: str | None):
        """The structure for a signal's direction: the legs as set for long, calls and puts swapped for short."""
        if direction != "short":
            return self.s.legs
        return [lg.model_copy(update={"opt": "PE" if lg.opt == "CE" else "CE"}) for lg in self.s.legs]

    # ---------- marks ----------
    def _mark(self, leg: dict, quotes: dict) -> float:
        """What closing a leg gets now; remembers the last good mark when a quote is missing."""
        px = fill_price(quotes.get(leg["key"]), "buy" if leg["side"] == "sell" else "sell", 0)
        if px is not None:
            leg["mark"] = px
        return leg.get("mark", leg["entry"])

    @staticmethod
    def _leg_pnl(leg: dict, px: float) -> float:
        return (leg["entry"] - px) * leg["qty"] if leg["side"] == "sell" else (px - leg["entry"]) * leg["qty"]

    def mtm(self, quotes: dict) -> float:
        """The open trade's profit before costs: legs already closed plus open legs at their closing price."""
        p = self.pos
        if not p:
            return 0.0
        return p["closed_pnl"] + sum(self._leg_pnl(l, self._mark(l, quotes)) for l in p["legs"] if l["open"])

    def equity(self, quotes: dict | None = None) -> float:
        if not self.pos:
            return self.cash
        q = quotes or {}
        return self.cash + self.mtm(q) - self.pos["costs"]

    # ---------- orders ----------
    def _order(self, now: datetime, leg: dict, side: str, px: float, why: str, pnl: float | None = None) -> dict:
        slices = max(1, math.ceil(leg["qty"] / self.freeze)) if self.freeze else 1
        cost = C.total(C.order_costs(self.kind, side, leg["qty"], px, slices * self.s.costs.brokerage))
        self.pos["costs"] += cost
        self.pos["orders"] += slices
        ev = {"t": now.isoformat(), "side": side, "qty": leg["qty"], "px": px, "why": why, "sym": leg["sym"],
              "strike": leg.get("strike"), "opt": leg.get("opt"), "slices": slices}
        if pnl is not None:
            ev["pnl"] = round(pnl, 2)
        self.events.append(ev)
        return ev

    def _open_leg(self, now, contracts: Contracts, quotes, opt, side, strike, qty, why, out) -> bool:
        key = contracts.key(opt, strike)
        px = fill_price(quotes.get(key), side, self.s.costs.slippageTicks) if key else None
        if px is None:
            return False
        sym = key.split(":", 1)[1]
        leg = {"key": key, "sym": sym, "opt": opt, "side": side, "strike": strike, "qty": qty, "entry": px,
               "mark": px, "open": True}
        self.pos["legs"].append(leg)
        out.append(self._order(now, leg, side, px, why))
        return True

    def _close_leg(self, now, leg, quotes, why, out):
        side = "buy" if leg["side"] == "sell" else "sell"
        px = fill_price(quotes.get(leg["key"]), side, self.s.costs.slippageTicks) or leg.get("mark", leg["entry"])
        pnl = self._leg_pnl(leg, px)
        leg.update(open=False, exit=px, mark=px)
        self.pos["closed_pnl"] += pnl
        out.append(self._order(now, leg, side, px, why, pnl))

    def _expired(self, now: datetime, expiry: str) -> bool:
        """The contracts have stopped trading: the expiry day's derivatives close has passed."""
        today = now.date().isoformat()
        return expiry < today or (expiry == today and now.time() >= sessions.fo_close(now.date()))

    def _settle_expiry(self, now: datetime, under: float, out: list):
        """Every open leg at its intrinsic value against the settlement price, then the trade is closed."""
        p = self.pos
        for leg in p["legs"]:
            if not leg["open"]:
                continue
            k = leg["strike"]
            px = round(max(0.0, under - k) if leg["opt"] == "CE" else max(0.0, k - under), 2)
            pnl = self._leg_pnl(leg, px)
            leg.update(open=False, exit=px, mark=px)
            p["closed_pnl"] += pnl
            ev = {"t": now.isoformat(), "side": "buy" if leg["side"] == "sell" else "sell", "qty": leg["qty"], "px": px,
                  "why": f"Expiry settlement at {under:,.2f}", "sym": leg["sym"], "strike": k, "opt": leg.get("opt"),
                  "slices": 0, "pnl": round(pnl, 2)}
            self.events.append(ev)
            out.append(ev)
        self._exit(now, {}, "Expiry settlement", out)

    # ---------- the structure ----------
    def _plan(self, contracts: Contracts, atm: float, legs=None) -> list[tuple] | None:
        """(opt, side, strike, lots) for each leg around a centre strike, or None when a strike doesn't exist."""
        out = []
        for lg in legs or self.s.legs:
            k = contracts.strike_for(atm, lg.opt, lg.offset, self.s.offsetUnit)
            if k is None:
                return None
            out.append((lg.opt, lg.side, k, lg.lots))
        return out

    def _units(self, contracts: Contracts, plan: list[tuple]) -> int:
        """How many units of the structure to trade."""
        z = self.s.sizing
        if z.mode == "lots":
            return z.lots
        if not self.margin_fn:
            self.note = "Margin sizing needs the broker's margin service, which isn't available; used 1 unit."
            return 1
        legs = [{"key": contracts.key(o, k), "side": sd, "qty": n * contracts.lot} for o, sd, k, n in plan]
        one = self.margin_fn(legs)
        if not one or one <= 0:
            self.note = "Couldn't get the margin for this structure; used 1 unit."
            return 1
        cap = min(z.capital, self.cash) * z.safety
        units = max(0, int(cap // one))
        for _ in range(5):   # margin isn't linear in size, so confirm the full size fits and shrink if not
            if units <= 0:
                break
            need = self.margin_fn([{**l, "qty": l["qty"] * units} for l in legs])
            if need is None or need <= cap:
                break
            units = max(0, int(units * cap / need))
        if units <= 0:
            self.note = f"Not enough capital for even one unit (needs about {one:,.0f} of margin)."
        return units

    def _enter(self, now, spot, contracts: Contracts, quotes, out, direction: str | None = None) -> bool:
        atm = contracts.atm(spot)
        plan = self._plan(contracts, atm, self.legs_for(direction))
        if plan is None:
            self.note = "A strike this structure needs isn't listed for that expiry."
            return False
        missing = [(o, sd, k) for o, sd, k, _ in plan if fill_price(quotes.get(contracts.key(o, k)), sd, 0) is None]
        if missing:
            legs = ", ".join(f"{k:g} {o} ({'buy' if sd == 'buy' else 'sell'})" for o, sd, k in missing)
            note = f"No price yet for {legs}, so no entry. It enters once every leg has a bid, ask or last price."
            if note != self.note:            # once per change, so the server log shows which contract had no price
                print("options: no quote for", [contracts.key(o, k) for o, _, k in missing], "spot", spot)
            self.note = note
            return False
        self.note = ""
        units = self._units(contracts, plan)
        if units <= 0:
            return False
        self.pos = {"opened": now.isoformat(), "center": atm, "spot_in": spot, "legs": [], "closed_pnl": 0.0,
                    "costs": 0.0, "orders": 0, "peak": 0.0, "low": 0.0, "rolls": 0, "expiry": contracts.expiry,
                    "units": units, "last_check": now.isoformat(), "credit": 0.0, "dir": direction}
        # buy the hedges first, as a broker would, so the sold legs get the margin benefit
        for opt, side, k, n in sorted(plan, key=lambda x: x[1] != "buy"):
            self._open_leg(now, contracts, quotes, opt, side, k, n * units * contracts.lot, "Entry", out)
        p = self.pos
        p["credit"] = sum((l["entry"] if l["side"] == "sell" else -l["entry"]) * l["qty"] for l in p["legs"])
        self.entries_today += 1
        return True

    def _exit(self, now, quotes, why, out):
        p = self.pos
        for leg in p["legs"]:
            if leg["open"]:
                self._close_leg(now, leg, quotes, why, out)
        net = p["closed_pnl"] - p["costs"]
        self.cash += net
        self.day_realised += net
        self.trades.append({
            "opened": p["opened"], "closed": now.isoformat(), "why": why, "pnl": round(net, 2),
            "gross": round(p["closed_pnl"], 2), "costs": round(p["costs"], 2), "credit": round(p["credit"], 2),
            "rolls": p["rolls"], "units": p["units"], "orders": p["orders"], "best": round(p["peak"], 2),
            "worst": round(p["low"], 2), "spot_in": p["spot_in"], "expiry": p["expiry"],
            "legs": [{"sym": l["sym"], "side": l["side"], "qty": l["qty"], "entry": l["entry"], "exit": l.get("exit")}
                     for l in p["legs"]],
        })
        self.pos = None
        if self.s.timing.cooldown:
            self.cool_until = (now + timedelta(minutes=self.s.timing.cooldown)).isoformat()

    def _recenter(self, now, spot, contracts: Contracts, quotes, out):
        p, r = self.pos, self.s.recenter
        last = datetime.fromisoformat(p["last_check"])
        if now < last + timedelta(minutes=r.every):
            return
        p["last_check"] = now.isoformat()
        atm = contracts.atm(spot)
        if abs(atm - p["center"]) < r.threshold * contracts.step(spot) - 1e-9:
            return
        legs = [lg for lg in self.legs_for(p.get("dir")) if r.roll == "all" or lg.side == "sell"]
        plan = self._plan(contracts, atm, legs)
        if plan is None or any(fill_price(quotes.get(contracts.key(o, k)), sd, 0) is None for o, sd, k, _ in plan):
            return   # try again at the next check
        for leg in p["legs"]:
            if leg["open"] and (r.roll == "all" or leg["side"] == "sell"):
                self._close_leg(now, leg, quotes, "Re-centre", out)
        for opt, side, k, n in sorted(plan, key=lambda x: x[1] != "buy"):
            self._open_leg(now, contracts, quotes, opt, side, k, n * p["units"] * contracts.lot, "Re-centre", out)
        p["center"] = atm
        p["rolls"] += 1
        p["credit"] = p["closed_pnl"] + sum((l["entry"] if l["side"] == "sell" else -l["entry"]) * l["qty"]
                                           for l in p["legs"] if l["open"])

    # ---------- one pass ----------
    def step(self, now: datetime, spot: float | None, contracts: Contracts | None, quotes: dict, fresh: bool,
             want: dict | None = None) -> list[dict]:
        """Act on one snapshot. `fresh` is False when the quotes are old (market closed, holiday, dead feed).
        With a signal set, `want` is the rules' open trade ({"dir": "long"|"short", "key": its entry time}) or None."""
        sig = self.s.signal
        out: list[dict] = []
        t, rk = self.s.timing, self.s.risk
        today = now.date().isoformat()
        if self.day != today:
            self.day, self.entries_today, self.day_realised, self.halted = today, 0, 0.0, False
        p = self.pos
        if p:
            if self.settle_fn and p.get("expiry") and self._expired(now, p["expiry"]):
                px = self.settle_fn(p["expiry"])
                if px is not None:
                    self._settle_expiry(now, float(px), out)
                    return out
            if not fresh:
                return out   # without live prices no stop can be judged; hold and wait
            if now >= _at(now, t.squareoff) or p["opened"][:10] != today:
                self._exit(now, quotes, "Square-off", out)
                return out
            if sig and (not want or want["dir"] != p.get("dir")):
                self._exit(now, quotes, "The rules exited" if not want else "The rules turned " + want["dir"], out)
                return out
            if rk.legStopPct:
                for leg in p["legs"]:
                    if leg["open"] and leg["side"] == "sell" and self._mark(leg, quotes) >= leg["entry"] * (1 + rk.legStopPct / 100):
                        self._close_leg(now, leg, quotes, "Leg stop", out)
                if not any(l["open"] and l["side"] == "sell" for l in p["legs"]):
                    self._exit(now, quotes, "Leg stops hit", out)
                    return out
            m = self.mtm(quotes)
            p["peak"], p["low"] = max(p["peak"], m), min(p["low"], m)
            basis = abs(p["credit"]) or 1.0
            stop = rk.stop if rk.stopType == "amount" else basis * rk.stop / 100 if rk.stopType == "credit_pct" else 0
            tgt = rk.tgt if rk.tgtType == "amount" else basis * rk.tgt / 100 if rk.tgtType == "credit_pct" else 0
            why = None
            if stop and m <= -stop:
                why = "Stop loss"
            elif tgt and m >= tgt:
                why = "Target"
            elif rk.trailAfter and rk.trailBy and p["peak"] >= rk.trailAfter and m <= p["peak"] - rk.trailBy:
                why = "Trailing stop"
            elif rk.dailyLoss and self.day_realised + m - p["costs"] <= -rk.dailyLoss:
                why, self.halted = "Daily loss cap", True
            if why:
                self._exit(now, quotes, why, out)
                return out
            if self.s.recenter.enabled and contracts and spot and now < _at(now, t.lastEntry):
                self._recenter(now, spot, contracts, quotes, out)
            return out
        # flat: may we enter? Outside the window, say why instead of leaving an old note up
        if self.halted:
            self.note = "The daily loss cap was hit, so no more entries today."
            return out
        if self.entries_today >= t.maxEntries:
            self.note = f"Took today's {t.maxEntries} entries; next entries on the next market day."
            return out
        if not (_at(now, t.entry) <= now < _at(now, t.lastEntry)) or now >= _at(now, t.squareoff):
            self.note = "" if now < _at(now, t.entry) else f"Entries stop at {t.lastEntry}; next entry at {t.entry} on the next market day."
            return out
        if self.cool_until and now < datetime.fromisoformat(self.cool_until):
            return out
        if sig:
            if not want:
                self.note = "Waiting for the rules to signal a trade."
                return out
            if want["key"] == self.used_signal:
                self.note = "Already traded this signal; waiting for the next one."
                return out
            if want["dir"] == "short" and sig.short == "none":
                self.note = "The rules are short; this session only takes long signals."
                return out
        if not fresh or not spot or not contracts:
            self.note = "Waiting for live prices." if not fresh else "Waiting for the option chain."
            return out
        if self._enter(now, spot, contracts, quotes, out, want["dir"] if sig else None) and sig:
            self.used_signal = want["key"]
        return out

    def legs_view(self, quotes: dict) -> list[dict]:
        if not self.pos:
            return []
        out = []
        for l in self.pos["legs"]:
            px = self._mark(l, quotes) if l["open"] else l.get("exit", l["entry"])
            out.append({"sym": l["sym"], "opt": l["opt"], "side": l["side"], "strike": l["strike"], "qty": l["qty"],
                        "entry": l["entry"], "mark": px, "open": l["open"], "pnl": round(self._leg_pnl(l, px), 2)})
        return out
