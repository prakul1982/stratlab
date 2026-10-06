"""/trade/journal: the real-trade journal's API (the Trade space).

Everything here is the signed-in user's own trades. Free keeps the last 50 closed trades with the trade list, the
journal fields and the basic stats; Basic and up keep every trade and add the honesty checks, the breakdowns, the
R-multiples and paper vs real. Facts about past trades only: nothing here says what to do next."""
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from . import db, holdings_file, tax_lots
from . import journal as J
from .auth import current_profile
from .kite_service import IST
from .plans import FEATURE_PLAN, PLANS, allows, journal_limit

router = APIRouter(prefix="/trade/journal", tags=["journal"])
TIME = r"^([01]?\d|2[0-3]):[0-5]\d(:[0-5]\d)?$"


def _m():
    """The main module, for the shared helpers (ok, err, throttle). Imported late: it imports us."""
    from . import main
    return main


def today() -> date:
    return datetime.now(IST).date()


class UploadReq(BaseModel):
    filename: str = Field("", max_length=200)
    data: str = Field(..., max_length=8 * 1024 * 1024)
    mode: Literal["add", "replace"] = "add"


class ManualReq(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    segment: Literal["eq", "fut", "opt", "com", "cur", "us", "crypto"] = "eq"
    side: Literal["long", "short"] = "long"
    entry_date: date
    entry_time: str | None = Field(None, pattern=TIME)
    exit_date: date
    exit_time: str | None = Field(None, pattern=TIME)
    qty: float = Field(..., gt=0, le=1e9)
    entry_price: float = Field(..., ge=0, le=1e9)
    exit_price: float = Field(..., ge=0, le=1e9)
    charges: float | None = Field(None, ge=0, le=1e9)


class NoteReq(BaseModel):
    tag: str = Field("", max_length=40)
    notes: str = Field("", max_length=2000)
    links: list[str] = Field(default_factory=list, max_length=5)
    emotions: list[str] = Field(default_factory=list, max_length=20)
    mistakes: list[str] = Field(default_factory=list, max_length=20)
    stop: float | None = Field(None, ge=0, le=1e11)
    target: float | None = Field(None, ge=0, le=1e11)
    side: Literal["long", "short"] | None = None


class SettingsReq(BaseModel):
    capital: float | None = Field(None, ge=1, le=1e11)
    brokerage_delivery: float = Field(0, ge=0, le=1000)
    brokerage_other: float = Field(20, ge=0, le=1000)
    show: Literal["all", "real", "practice"] | None = None     # real trades, chart replay practice, or both (kept when left out)


class LinkReq(BaseModel):
    tag: str = Field(..., min_length=1, max_length=40)
    session: str | None = Field(None, max_length=64)


def _clock(v: str | None) -> str:
    if not v:
        return ""
    parts = (v.split(":") + ["00"])[:3]
    return ":".join(p.zfill(2) for p in parts)


def _row(t: dict) -> dict:
    """One trade as the page shows it, rounded."""
    out = {k: t.get(k) for k in ("id", "symbol", "u", "segment", "side", "entry_t", "exit_t", "hold_s", "hold_days", "fills",
                                 "src", "expired", "charges_from", "note")}
    for k, dp in (("qty", 6), ("entry", 4), ("exit", 4), ("gross", 2), ("charges", 2), ("net", 2), ("r", 2)):
        out[k] = J._r(t.get(k), dp)
    out["segment_label"] = J.SEGMENTS.get(t["segment"], t["segment"])
    out["currency"] = J.MARKETS[J.market_of(t["segment"])]["currency"]
    return out


# the tax report keeps F&O, commodity and currency as totals per year (not line by line), so they show beside the trades
# as totals and are never added into the trade stats; the journal segments each total covers
TAX_SEGMENTS = {"fno": ("fut", "opt"), "commodity": ("com",), "currency": ("cur",)}


def tax_totals(uid: str, segment: str) -> list[dict]:
    """The tax report's F&O, commodity and currency totals per financial year, newest first (only those of the chosen
    segment, or all of them)."""
    try:
        chunks = tax_lots.load(uid)["business"]
    except Exception as e:                    # the tax report beside the journal is extra: a failure never stops the page
        print("journal: tax totals:", str(e)[:120])
        return []
    out = []
    for fy in sorted({c["fy"] for c in chunks}, reverse=True):
        for seg in tax_lots.business_year(fy, chunks)["segments"]:
            if segment == "all" or segment in TAX_SEGMENTS.get(seg["seg"], ()):
                out.append({"fy": fy, "seg": seg["seg"], "label": seg["label"], "trades": seg["trades"], "pnl": seg["pnl"],
                            "charges": seg["charges"], "net": seg["net"], "turnover": seg["turnover"], "first": seg["first"], "last": seg["last"]})
    return out


def _paper_list(uid: str) -> list[dict]:
    try:
        rows = db.user_sessions(uid, 50)
    except Exception as e:                   # paper trading beside real is extra: a failure never stops the page
        print("journal: paper sessions:", str(e)[:120])
        return []
    return [{"id": r["id"], "name": r["name"], "status": r.get("status"),
             "symbol": (r.get("instrument") or {}).get("symbol") or (r.get("instrument") or {}).get("type")} for r in rows]


def view(profile, data: dict | None = None, segment: str = "all", market: str = "") -> dict:
    """The journal page: the trades (newest first), open positions, the stats, and on Basic and up the checks, the
    breakdowns, R-multiples and the paper sessions to compare with."""
    uid, plan = profile["id"], profile["_plan"]
    data = data or J.load(uid)
    got = J.trades(uid, data, today())
    every = got["trades"]
    show = data["settings"].get("show", "all")
    practice = sum(1 for t in every if t["src"] == "practice")
    allt = every if show == "all" or not practice else [t for t in every if (t["src"] == "practice") == (show == "practice")]
    # each market (India, US stocks, crypto) is worked out apart, in its own currency; India is the default unless the
    # journal holds only another market. Within India a segment can be picked (equity delivery, intraday, futures, ...).
    held = {m: sum(1 for t in allt if J.market_of(t["segment"]) == m) for m in J.MARKETS}
    market = market if market in J.MARKETS else ("in" if held["in"] or not any(held.values()) else next(m for m in J.MARKETS if held[m]))
    in_market = [t for t in allt if J.market_of(t["segment"]) == market]
    seg_count = {k: sum(1 for t in in_market if t["segment"] == k) for k in J.SEGMENTS if market == "in" and k not in J.OTHER_SEGMENTS}
    segment = segment if segment in seg_count and seg_count[segment] else "all"
    allt = [t for t in in_market if segment == "all" or t["segment"] == segment]
    limit = journal_limit(plan)
    shown = allt[-limit:] if limit else allt
    full = allows(plan, "journal")
    cap = data["settings"]["capital"]
    return {"as_of": today().isoformat(), "updated_at": data["updated_at"], "full": full, "limit": limit,
            "count": len(shown), "total": len(allt), "beyond_limit": len(allt) - len(shown), "removed": len(data["hidden"]),
            "trades": [_row(t) for t in reversed(shown[-J.MAX_LIST:])], "open": got["open"], "unmatched": got["unmatched"], "overlap": got["overlap"],
            "summary": J.summary(shown, cap), "verdict": J.verdict(shown, cap, J.MARKETS[market]["symbol"]) if full and shown else None,
            "breakdowns": J.breakdowns(shown) if full else None, "r": J.r_distribution(shown) if full else None,
            "practice_count": practice, "real_count": len(every) - practice, "show": show if practice else "all",
            "files": data["files"], "settings": data["settings"], "links": data["links"] if full else {},
            "paper": _paper_list(uid) if full else [], "tags": sorted({t["note"]["tag"] for t in allt if t["note"].get("tag")}),
            "market": market, "markets": [{"id": m, **J.MARKETS[m], "n": n} for m, n in held.items()],
            "currency": J.MARKETS[market]["currency"], "segment": segment, "segment_counts": {k: n for k, n in seg_count.items() if n},
            "tax_totals": tax_totals(uid, segment) if market == "in" else [],
            "emotions": J.EMOTIONS, "mistakes": J.MISTAKES, "segments": J.SEGMENTS, "assumptions": J.ASSUMPTIONS,
            "plan_name": PLANS[FEATURE_PLAN["journal"]]["name"]}


@router.get("")
def journal(segment: str = Query("all", max_length=20), market: str = Query("", max_length=10), profile=Depends(current_profile)):
    """The user's real trades paired into round trips, with their notes and the stats. `market` picks India, US stocks or
    crypto (each in its own currency); `segment` narrows India to one segment."""
    return _m().ok(view(profile, None, segment, market))


@router.get("/brief")
def brief(profile=Depends(current_profile)):
    """A line for the Trade home: how many closed real trades, their P&L after charges and win rate (no checks run;
    chart replay practice isn't counted here)."""
    j = J.load(profile["id"])
    allt = [t for t in J.trades(profile["id"], j, today())["trades"] if t["src"] != "practice" and J.market_of(t["segment"]) == "in"]
    limit = journal_limit(profile["_plan"])
    shown = allt[-limit:] if limit else allt
    nets = [t["net"] for t in shown]
    return _m().ok({"count": len(shown), "net": J._r(sum(nets)), "last": shown[-1]["exit_t"][:10] if shown else None,
                    "win_rate": J._r(sum(1 for v in nets if v > 0) / len(nets) * 100, 1) if nets else None})


@router.post("/import", openapi_extra={"requestBody": {"content": {
    "application/json": {"schema": UploadReq.model_json_schema()},
    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
async def import_file(request: Request, filename: str = Query("", max_length=200), mode: Literal["add", "replace"] = Query("add"),
                      profile=Depends(current_profile)):
    """A tradebook, a tax P&L file or the broker's ZIP of them (equity and F&O). The file is the request body (the
    name and mode in the query), or base64 in JSON ({filename, data, mode}). Trades already in the journal are skipped;
    "replace" swaps every imported trade for this file's (trades added by hand and the notes stay)."""
    from fastapi.concurrency import run_in_threadpool
    M = _m()
    body = await request.body()
    cap = holdings_file.FNO_MAX_BYTES
    if request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json":
        try:
            req = UploadReq.model_validate_json(body)
        except Exception:
            M.err(400, "bad_upload", "The file didn't arrive whole. Pick it again.")
        filename, mode = req.filename, req.mode
        data = M.upload_bytes(req.data, J.hf.TOO_BIG, cap)
    else:
        if len(body) > cap:
            M.err(413, "file_too_big", f"That file is larger than {cap // (1024 * 1024)} MB. {J.hf.TOO_BIG}")
        data = body
    return await run_in_threadpool(_import, profile, data, filename, mode)


def _import(profile, data: bytes, filename: str, mode: str):
    M = _m()
    M.throttle(profile, "journal_import", 40, 3600, "That's a lot of uploads in an hour. Try again a little later.")
    if not data:
        M.err(400, "bad_file", "That file is empty.")
    try:
        parsed = J.parse(data, filename)
    except holdings_file.FileError as e:
        M.err(400, "bad_file", str(e))
    j = J.load(profile["id"])
    if mode == "replace":
        j["fills"], j["lines"], j["hidden"], j["files"] = [], [], [], []
    res = J.add(j, parsed)
    if res["added"] or mode == "replace":
        j["files"] = j["files"] + [{"name": (filename or "file")[:80], "broker": parsed["broker"], "trades": res["added"],
                                    "at": datetime.now(IST).isoformat(timespec="minutes")}]
        j = J.save(profile["id"], j)
    return M.ok({"broker": parsed["broker"], "read": len(parsed["fills"]) + len(parsed["lines"]), **res,
                 "problems": parsed["problems"][:200], "problem_count": len(parsed["problems"]), "skipped": parsed["skipped"][:50],
                 "files": parsed["files"][:50], "journal": view(profile, j)})


@router.post("/import-tax")
def import_tax(profile=Depends(current_profile)):
    """Bring in the equity trades already uploaded to the tax report (tradebook lines and tax P&L exits)."""
    M = _m()
    M.throttle(profile, "journal_import", 40, 3600, "That's a lot of uploads in an hour. Try again a little later.")
    got = J.from_tax(tax_lots.load(profile["id"])["trades"])
    if not got["fills"] and not got["lines"]:
        M.err(404, "no_tax_trades", "Your tax report has no trades yet. Upload your tradebook here instead.")
    j = J.load(profile["id"])
    res = J.add(j, got)
    if res["added"]:
        j["files"] = j["files"] + [{"name": "From the tax report", "broker": "", "trades": res["added"],
                                    "at": datetime.now(IST).isoformat(timespec="minutes")}]
        j = J.save(profile["id"], j)
    return M.ok({**res, "journal": view(profile, j)})


def _edit(profile):
    _m().throttle(profile, "journal_edit", 300, 3600, "That's a lot of changes in an hour. Try again a little later.")


@router.post("/trades")
def add_trade(req: ManualReq, profile=Depends(current_profile)):
    """Add a trade by hand: the instrument, long or short, entry and exit, quantity and prices (charges worked out
    at the published rates unless entered)."""
    M = _m()
    _edit(profile)
    ed, xd = req.entry_date.isoformat(), req.exit_date.isoformat()
    et, xt = _clock(req.entry_time), _clock(req.exit_time)
    if (xd, xt or "99") < (ed, et or "00"):
        M.err(400, "bad_dates", "The exit is before the entry. Check the dates and times.")
    j = J.load(profile["id"])
    if len(j["manual"]) >= J.MAX_MANUAL:
        M.err(400, "too_many", f"The journal keeps up to {J.MAX_MANUAL:,} trades added by hand. Import your tradebook instead.")
    limit = journal_limit(profile["_plan"])
    if limit is not None and len(J.trades(profile["id"], j, today())["trades"]) >= limit:
        M.upgrade(f"Your plan keeps the last {limit} trades in the journal. {PLANS[FEATURE_PLAN['journal']]['name']} keeps every trade.")
    j["manual"].append({"id": J.new_id(), "sym": J.clean_symbol(req.symbol), "segment": req.segment, "side": req.side,
                        "ed": ed, "et": et, "xd": xd, "xt": xt, "qty": req.qty, "entry": req.entry_price, "exit": req.exit_price,
                        **({"charges": req.charges} if req.charges is not None else {})})
    return M.ok(view(profile, J.save(profile["id"], j)))


def _find(profile, j: dict, tid: str) -> dict:
    t = next((t for t in J.trades(profile["id"], j, today())["trades"] if t["id"] == tid), None)
    if not t:
        _m().err(404, "not_found", "That trade isn't in your journal.")
    return t


@router.put("/trades/{tid}/note")
def set_note(tid: str, req: NoteReq, profile=Depends(current_profile)):
    """A trade's journal entry: setup tag, notes, links, feelings, mistakes, planned stop and target, and the side
    when the file didn't say."""
    _edit(profile)
    tid = tid[:40]
    j = J.load(profile["id"])
    _find(profile, j, tid)
    note = J.clean_note(req.model_dump())
    j["notes"].pop(tid, None)
    if note:
        if len(j["notes"]) >= J.MAX_NOTES:
            _m().err(400, "too_many", f"The journal keeps notes on up to {J.MAX_NOTES:,} trades.")
        j["notes"][tid] = note
    return _m().ok(view(profile, J.save(profile["id"], j)))


@router.delete("/trades/{tid}")
def remove_trade(tid: str, profile=Depends(current_profile)):
    """Remove a trade: one added by hand is deleted; an imported one is left out of the journal (and comes back with
    "Show removed trades")."""
    _edit(profile)
    tid = tid[:40]
    j = J.load(profile["id"])
    t = _find(profile, j, tid)
    if t["src"] == "manual":
        j["manual"] = [m for m in j["manual"] if m["id"] != tid]
    elif t["src"] == "practice":
        j["practice"] = [m for m in j["practice"] if m["id"] != tid]
    else:
        j["hidden"] = j["hidden"] + [tid]
    j["notes"].pop(tid, None)
    return _m().ok(view(profile, J.save(profile["id"], j)))


@router.post("/restore")
def restore(profile=Depends(current_profile)):
    """Bring back every imported trade that was removed."""
    _edit(profile)
    j = J.load(profile["id"])
    j["hidden"] = []
    return _m().ok(view(profile, J.save(profile["id"], j)))


@router.put("/settings")
def settings(req: SettingsReq, profile=Depends(current_profile)):
    """The trading capital (for drawdowns as a %), the brokerage a tradebook line pays, and whether the page shows real
    trades, chart replay practice or both."""
    _edit(profile)
    j = J.load(profile["id"])
    got = req.model_dump()
    if got["show"] is None:
        got["show"] = j["settings"].get("show", "all")
    j["settings"] = J.clean_settings(got)
    return _m().ok(view(profile, J.save(profile["id"], j)))


@router.put("/links")
def link(req: LinkReq, profile=Depends(current_profile)):
    """Remember which paper session a setup tag is compared with (or forget it)."""
    M = _m()
    M.need(profile, "journal", "Paper vs real")
    _edit(profile)
    j = J.load(profile["id"])
    tag = req.tag.strip()[:40]
    j["links"].pop(tag, None)
    if req.session:
        if not db.get_session_row(profile["id"], M.check_id(req.session)):
            M.err(404, "not_found", "Paper session not found.")
        j["links"][tag] = req.session
        j["links"] = dict(list(j["links"].items())[-100:])
    return M.ok(view(profile, J.save(profile["id"], j)))


@router.get("/compare")
def compare(tag: str = Query(..., min_length=1, max_length=40), session: str = Query(..., max_length=64),
            profile=Depends(current_profile)):
    """One setup's real trades beside a paper session's trades: the same per-trade facts for each."""
    M = _m()
    M.need(profile, "journal", "Paper vs real")
    row = db.get_session_row(profile["id"], M.check_id(session))
    if not row:
        M.err(404, "not_found", "Paper session not found.")
    live = M.manager.sessions.get(row["id"])
    if live is not None and getattr(live, "user_id", None) == profile["id"]:
        try:
            row = {**row, "state": live.state()}         # a running session: its trades now, not when last saved
        except Exception as e:
            print("journal compare: live state:", str(e)[:120])
    j = J.load(profile["id"])
    allt = J.trades(profile["id"], j, today())["trades"]
    want = tag.strip().lower()
    real = [t for t in allt if (t["note"].get("tag") or "").lower() == want]
    out = J.compare(real, J.paper_trades(row))
    return M.ok({**out, "tag": tag.strip(), "session": {"id": row["id"], "name": row["name"], "status": row.get("status")},
                 "note": "Position sizes differ between paper and real, so compare the rates and per-trade figures."})


@router.delete("")
def delete_all(profile=Depends(current_profile)):
    """Delete my journal: every imported and added trade, the practice trades, the notes, the settings and the paper
    links, at once."""
    J.delete(profile["id"])
    return {"deleted": True}
