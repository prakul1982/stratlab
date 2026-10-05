"""/trade/replay: chart replay practice (the Trade space, Basic).

Start a session on any instrument and date (or a random NIFTY 50 stock and date, both hidden until the end), step
through the candles on StratLab's own price chart, and finish: the practice orders are filled again here against the
real candles (replay.py), and the trades go into the trade journal marked as practice. Facts about a historical
simulation only."""
import random
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import journal as J
from . import replay as R
from . import universes
from .auth import current_profile
from .kite_service import IST
from .plans import FEATURE_PLAN, PLANS, allows

router = APIRouter(prefix="/trade/replay", tags=["replay"])
STARTS_PER_HOUR = 40


def _m():
    """The main module, for the shared helpers and the markets registry. Imported late: it imports us."""
    from . import main
    return main


class StartReq(BaseModel):
    instrument: str | None = Field(None, max_length=60)
    tf: str = Field("1d", pattern=r"^(5m|15m|1h|1d)$")
    start: date | None = None
    random: bool = False


class FinishReq(BaseModel):
    cursor: int = Field(..., ge=0, le=100_000)
    orders: list[dict] = Field(default_factory=list, max_length=R.MAX_ORDERS)
    save: bool = True


def today() -> date:
    return datetime.now(IST).date()


def _fail(e: R.ReplayError):
    _m().err(e.status, e.code, e.message)


def _brokerage(uid: str, inst: dict, tf: str) -> float:
    """The brokerage the journal is set to: delivery's for shares held overnight, the other for the rest."""
    s = J.load(uid)["settings"]
    if R.cost_kind(inst) == "flat":
        return 0.0
    if inst.get("market", "IN") not in ("IN", "MCX", "CDS"):
        return 0.0
    return s["brokerage_delivery"] if R.cost_kind(inst) == "in_eq" and tf == "1d" else s["brokerage_other"]


@router.get("")
def overview(profile=Depends(current_profile)):
    """The user's unfinished sessions and the practice trades already in the journal."""
    uid = profile["id"]
    rows = sorted(R.load_all(uid).values(), key=lambda s: s["created"], reverse=True)
    j = J.load(uid)
    practice = [t for t in J.trades(uid, j, today())["trades"] if t["src"] == "practice"]
    return _m().ok({"allowed": allows(profile["_plan"], "chart_replay"), "plan": PLANS[FEATURE_PLAN["chart_replay"]]["name"],
                    "sessions": [{"id": s["id"], "label": R.label(s), "tf": s["tf"], "created": s["created"], "hidden": bool(s.get("hidden"))} for s in rows],
                    "practice": {**R.summary(practice), "last": practice[-1]["exit_t"][:10] if practice else None},
                    "tfs": list(R.TFS), "note": R.NOTE})


@router.post("")
def start(req: StartReq, profile=Depends(current_profile)):
    """A new session: the candles before the start to read the chart, and the ones to step through after it."""
    M = _m()
    M.need(profile, "chart_replay", "Chart replay practice")
    M.throttle(profile, "replay_start", STARTS_PER_HOUR, 3600, "That's a lot of replays in an hour. Try again a little later.")
    rng = random.Random()
    if req.random and not req.instrument:
        ids, _ = universes.resolve(M.markets, "IN", [{"symbol": s} for s in rng.sample(R_POOL(), 5)])
        if not ids:
            M.err(503, "data_offline", "Market data for India is offline right now. Try again soon.")
        inst_id = ids[0]
    elif req.instrument:
        inst_id = req.instrument
    else:
        M.err(400, "no_instrument", "Pick an instrument, or a random one.")
    prov, inst = M.get_instrument(inst_id)
    if M.needs_fno(inst) and not M.fno(profile):
        M.upgrade("Replaying Indian futures and options is on the Pro plan.")
    max_days = (getattr(prov, "max_days", None) or {}).get(req.tf)
    if not max_days:
        M.err(400, "bad_tf", "This market doesn't have candles of that size.")
    t = today()
    if req.random:
        begin = R.random_start(req.tf, max_days, t, rng)
    else:
        if req.start is None:
            M.err(400, "no_start", "Pick a start date.")
        begin = req.start
        if begin >= t:
            M.err(400, "too_recent", "Pick a date in the past.")
        if (t - begin).days > max_days - 15:
            M.err(400, "too_early", f"Candles of this size go back about {max_days} days here. Pick a later date or a bigger candle.")
    days = min(R.days_back(req.tf, begin, t), max_days)
    try:
        bars = prov.history(inst, req.tf, days)
    except Exception as e:
        if isinstance(e, M.KiteNotReady):
            raise
        M.report(e, where="replay candles")
        M.err(503, "prices_unavailable", "Couldn't load the candles for that replay. Try again in a minute.")
    try:
        window, first = R.window(bars, req.tf, begin)
    except R.ReplayError as e:
        _fail(e)
    s = R.create(profile["id"], inst, req.tf, window, first, begin, hidden=req.random)
    return M.ok(R.public(s, _brokerage(profile["id"], s["inst"], s["tf"])))


def R_POOL() -> list[str]:
    """NIFTY 50 stocks: liquid, with long histories, for a random replay."""
    return next(p["symbols"] for p in universes.PRESETS["IN"] if p["id"] == "nifty50")


def _session(profile, rid: str) -> dict:
    s = R.get(profile["id"], rid)
    if not s:
        _m().err(404, "not_found", "That replay isn't open any more. Start a new one.")
    return s


@router.get("/{rid}")
def reopen(rid: str, profile=Depends(current_profile)):
    s = _session(profile, rid)
    return _m().ok(R.public(s, _brokerage(profile["id"], s["inst"], s["tf"])))


@router.post("/{rid}/finish")
def finish(rid: str, req: FinishReq, profile=Depends(current_profile)):
    """End the session: the orders filled again here against the real candles, anything open closed at the last candle
    shown, the symbol and dates revealed, and the trades saved to the journal as practice."""
    M = _m()
    M.need(profile, "chart_replay", "Chart replay practice")
    uid = profile["id"]
    s = _session(profile, rid)
    bars, first = s["bars"], s["first"]
    if not first - 1 <= req.cursor < len(bars):
        M.err(400, "bad_cursor", "That candle isn't in this replay.")
    try:
        orders = R.check_orders(req.orders, first, req.cursor)
    except R.ReplayError as e:
        _fail(e)
    inst = s["inst"]
    brokerage = _brokerage(uid, inst, s["tf"])
    got = R.simulate(bars, orders, first, req.cursor, R.cost_kind(inst), R.qty_step(inst), brokerage)
    trades = got["trades"]
    saved, why_not = 0, None
    rupees = (inst.get("currency") or "INR") == "INR"
    if req.save and trades and rupees:
        j = J.load(uid)
        rows = R.journal_rows(s, trades)
        room = J.MAX_PRACTICE - len(j["practice"])
        if room < len(rows):
            j["practice"] = j["practice"][len(rows) - room:]      # the oldest practice trades make way
        j["practice"] = j["practice"] + rows
        for r in rows:
            if len(j["notes"]) < J.MAX_NOTES:
                j["notes"][r["id"]] = {"tag": "Practice", "notes": f"Chart replay, {s['tf']} candles"}
        J.save(uid, j)
        saved = len(rows)
    elif req.save and trades and not rupees:
        why_not = "The journal keeps trades in rupees, so practice in other currencies isn't saved to it."
    R.drop(uid, rid)
    shown = [{**{k: t[k] for k in ("side", "entry_i", "exit_i", "entry_t", "exit_t", "why", "fills")},
              **{k: round(t[k], 4) for k in ("qty", "entry", "exit")}, **{k: round(t[k], 2) for k in ("gross", "charges", "net")}}
             for t in trades]
    return M.ok({"trades": shown, "summary": R.summary(trades), "fills": len(got["fills"]), "skipped": got["skipped"][:50],
                 "reveal": {"symbol": inst.get("symbol"), "name": inst.get("name"), "start": s["start"],
                            "from": str(bars[first]["t"])[:10], "to": str(bars[req.cursor]["t"])[:10],
                            "candles": max(0, req.cursor - first + 1)},
                 "bars": bars[:req.cursor + 1] if s.get("hidden") else None,
                 "saved": saved, "why_not_saved": why_not, "currency": inst.get("currency") or "INR", "note": R.NOTE})


@router.delete("/{rid}")
def discard(rid: str, profile=Depends(current_profile)):
    """Throw a session away without saving anything."""
    if not R.drop(profile["id"], rid):
        _m().err(404, "not_found", "That replay isn't open any more.")
    return {"deleted": True}


@router.delete("")
def discard_all(profile=Depends(current_profile)):
    """Every unfinished session (practice trades already saved stay in the journal)."""
    R.forget(profile["id"])
    return {"deleted": True}
