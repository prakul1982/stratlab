"""/money/... API for the tax tools: dividends, advance tax and the long-term gains exemption.

Everything here is the signed-in user's own data, built on the tax report's inputs (main.tax_inputs): their trades,
F&O totals and income, My Holdings and the stored corporate actions. Free sees the year totals, the due dates and
the exemption used; Basic adds the dividend detail; Pro adds the advance tax amounts and the lot-by-lot facts."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from . import corp_actions, holdings, holdings_file, tax_lots
from . import money_advance_tax as adv
from . import money_dividends as divs
from . import money_ltcg as ltcg
from .auth import current_profile
from .kite_service import IST
from .plans import allows

router = APIRouter(prefix="/money", tags=["money"])
US_LOOKUPS = 15                   # US holdings whose dividend history is read while the page waits


def _m():
    """The main module, for the shared helpers (ok, throttle, the tax report's inputs). Imported late: it imports us."""
    from . import main
    return main


class DividendUploadReq(BaseModel):
    filename: str = Field("", max_length=200)
    data: str = Field(..., max_length=8 * 1024 * 1024)


class IncludeReq(BaseModel):
    fy: int = Field(..., ge=2000, le=2100)
    include: bool


class Payment(BaseModel):
    d: date
    amount: float = Field(..., ge=0, le=1e11)


class AdvanceReq(BaseModel):
    fy: int = Field(..., ge=2000, le=2100)
    tds: float = Field(0, ge=0, le=1e11)
    paid: list[Payment] = Field(default_factory=list, max_length=adv.MAX_PAYMENTS)


class RemindReq(BaseModel):
    on: bool


def today() -> date:
    return datetime.now(IST).date()


# ---------- dividends ----------
def dividend_parts(uid: str, fetch: bool = True) -> tuple[dict, list[dict], list[dict], float | None]:
    """(stored, estimated, ahead, rupees a dollar) for the user: what they uploaded, and the estimate from My Holdings
    × the dividends declared. `fetch` reads missing company histories (the page); the tax report uses what's stored."""
    M = _m()
    t = today()
    stored = divs.load(uid)
    h = holdings.load(uid)
    ind = holdings.indian(h["items"])
    us = [i for i in h["items"] if holdings.market_of(i) == "US"]
    syms = [i["symbol"] for i in ind]
    if fetch and syms:
        M._corp_histories(uid, syms, t)
    cal = corp_actions.load("IN")["rows"]
    acts = {s: corp_actions.actions_for("IN", s, None, t, fetch=False, cal=cal) for s in syms}
    paid, ahead = divs.estimate(ind, acts, t, h["updated_at"])
    if us:
        sources = M.corp_job.sources() if fetch else None
        us_acts = {}
        for i in us[:US_LOOKUPS]:
            try:
                us_acts[i["symbol"]] = corp_actions.history("US", i["symbol"], sources, t, fetch=fetch)
            except Exception as e:
                print("US dividends:", i["symbol"], str(e)[:120])
        p2, a2 = divs.estimate(us, us_acts, t, h["updated_at"], "US")
        paid, ahead = paid + p2, ahead + a2
    rate = M.usd_inr() if us or any(r["cur"] == "USD" for r in stored["rows"]) else None
    return stored, paid, ahead, rate


def dividend_view(profile, fetch: bool = True) -> dict:
    stored, est, ahead, rate = dividend_parts(profile["id"], fetch)
    return divs.view(stored, est, ahead, rate, today(), full=allows(profile["_plan"], "dividends"))


def dividends_for_tax(profile) -> dict[int, float]:
    """{fy: dividends} the user includes in the tax report's total estimate. Never stops the report."""
    try:
        stored, est, ahead, rate = dividend_parts(profile["id"], fetch=False)
        return divs.for_total(divs.view(stored, est, ahead, rate, today()))
    except Exception as e:
        print("dividends for the tax report:", str(e)[:160])
        return {}


def import_from_tax_file(profile, data: bytes, filename: str) -> int:
    """The dividend sheet of a tax P&L uploaded to the tax report, saved with the user's dividends. How many added."""
    rows = divs.from_tax_file(data, filename)
    return divs.add(profile["id"], rows, filename, "statement")[0] if rows else 0


@router.get("/dividends")
def dividends(profile=Depends(current_profile)):
    """Dividend income per financial year (from the user's files, or estimated from their holdings), the TDS expected,
    US dividends with the US tax withheld, and whether each year goes into the total tax estimate."""
    return _m().ok(dividend_view(profile))


@router.post("/dividends/import", openapi_extra={"requestBody": {"content": {
    "application/json": {"schema": DividendUploadReq.model_json_schema()},
    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
async def dividends_import(request: Request, filename: str = Query("", max_length=200), profile=Depends(current_profile)):
    """A dividend file: a CSV or Excel file of the user's dividends, or their broker's tax P&L with a dividend sheet.
    The file is the request body (the name in the query), or base64 in JSON ({filename, data})."""
    from fastapi.concurrency import run_in_threadpool
    M = _m()
    M.throttle(profile, "dividend_import", 30, 3600, "That's a lot of uploads in an hour. Try again a little later.")
    body = await request.body()
    if request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json":
        try:
            req = DividendUploadReq.model_validate_json(body)
        except Exception:
            M.err(400, "bad_upload", "The file didn't arrive whole. Pick it again.")
        filename = req.filename
        data = M.upload_bytes(req.data, "A dividend file is much smaller; check it's the right file.", holdings_file.TAX_MAX_BYTES)
    else:
        if len(body) > holdings_file.TAX_MAX_BYTES:
            M.err(413, "file_too_big", f"That file is larger than {holdings_file.TAX_MAX_BYTES // (1024 * 1024)} MB.")
        data = body
    return await run_in_threadpool(_import, profile, data, filename)


def _import(profile, data: bytes, filename: str):
    M = _m()
    try:
        got = divs.parse_upload(data, filename)
    except holdings_file.FileError as e:
        M.err(400, "bad_file", str(e))
    src = "statement" if any(r["src"] == "statement" for r in got["rows"]) else "csv"
    added, dup = divs.add(profile["id"], got["rows"], filename, src)
    return M.ok({"read": len(got["rows"]), "added": added, "duplicates": dup, "problems": got["problems"][:50],
                 "dividends": dividend_view(profile, fetch=False)})


@router.put("/dividends/include")
def dividends_include(req: IncludeReq, profile=Depends(current_profile)):
    """Include a year's dividends in the total tax estimate, or leave them out."""
    M = _m()
    M.throttle(profile, "tax_edit", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    divs.set_include(profile["id"], req.fy, req.include)
    return M.ok(dividend_view(profile, fetch=False))


@router.delete("/dividends")
def dividends_delete(profile=Depends(current_profile)):
    """Delete the uploaded dividends and the include choices (the estimate from holdings is worked out, not stored)."""
    divs.delete(profile["id"])
    return {"deleted": True}


# ---------- advance tax ----------
def advance_view(profile, fy: int | None = None) -> dict:
    """The year's instalments: dates for everyone, amounts on Pro."""
    M = _m()
    t = today()
    fy = fy or tax_lots.fy_of(t.isoformat())
    full = allows(profile["_plan"], "tax_tools")
    saved = adv.load(profile["id"])
    mine = saved["years"].get(fy) or adv.clean_year({})
    out = {"fy": fy, "label": tax_lots.fy_label(fy), "dates": adv.due_dates(fy), "remind": saved["remind"],
           "locked": not full, "as_of": t.isoformat(), "assumptions": adv.ASSUMPTIONS, "threshold": adv.THRESHOLD,
           "current_fy": tax_lots.fy_of(t.isoformat())}
    if not full:
        return out
    i = M.tax_inputs(profile)
    c = tax_lots.compute(i["trades"], i["acts"], i["fmv"], i["today"])
    stored, est, ahead, rate = dividend_parts(profile["id"], fetch=False)
    dv = divs.view(stored, est, ahead, rate, t)
    div_events = divs.events(dv, stored, est, rate, fy)
    inputs = i["income"].get(fy)

    def tax_by(cut: str | None) -> float:
        rows = [r for r in c["realised"] if cut is None or r["sold"] <= cut]
        div = sum(a for d, a in div_events if cut is None or d <= cut)
        y = tax_lots.with_total(tax_lots.year(fy, rows, c["intraday"], limit=0), i["business"], inputs, div)
        return (y["total"].get("total") or 0.0) if y["total"].get("available") else 0.0
    full_tax = tax_by(None)
    upto = [tax_by(d["date"]) for d in adv.due_dates(fy)[:3]] + [full_tax]
    business = any(b["fy"] == fy for b in i["business"]) or any(x["fy"] == fy for x in c["intraday"])
    out.update({"schedule": adv.schedule(fy, full_tax, upto, mine["tds"], mine["paid"], t, business), "inputs": mine,
                "dividends_in_estimate": round(sum(a for _, a in div_events), 2),
                "dividend_tds": next((y["tds"]["expected"] for y in dv["years"] if y["fy"] == fy), 0.0),
                "income_saved": bool(inputs)})
    return out


@router.get("/advance-tax")
def advance_tax(fy: int | None = Query(None, ge=2020, le=2100), profile=Depends(current_profile)):
    """The year's advance tax instalments: the due dates, and (Pro) the cumulative amounts due by each from the total
    tax estimate, less the TDS and advance tax entered, with section 234C and 234B interest."""
    return _m().ok(advance_view(profile, fy))


@router.put("/advance-tax")
def advance_tax_save(req: AdvanceReq, profile=Depends(current_profile)):
    """Save the year's TDS and the advance tax paid (date and amount of each payment)."""
    M = _m()
    M.need(profile, "tax_tools", "Advance tax amounts")
    M.throttle(profile, "tax_edit", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    adv.save_year(profile["id"], req.fy, {"tds": req.tds, "paid": [{"d": p.d.isoformat(), "amount": p.amount} for p in req.paid]})
    return M.ok(advance_view(profile, req.fy))


@router.put("/advance-tax/reminders")
def advance_tax_reminders(req: RemindReq, profile=Depends(current_profile)):
    """Turn the reminders 7 days and 1 day before each due date on or off (email to a confirmed address, and phone
    notifications where set up). Dates only; no amounts are sent."""
    M = _m()
    M.throttle(profile, "tax_edit", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    adv.set_remind(profile["id"], req.on)
    return {"remind": req.on}


# ---------- the long-term exemption ----------
@router.get("/ltcg")
def long_term(profile=Depends(current_profile)):
    """This year's long-term exemption used and left, and (Pro) each open long-term lot's gain at today's price, the
    lots turning long-term in the next 30, 60 or 90 days, and the open lots below cost."""
    M = _m()
    i = M.tax_inputs(profile)
    c = tax_lots.compute(i["trades"], i["acts"], i["fmv"], i["today"])
    full = allows(profile["_plan"], "tax_tools")
    out = ltcg.tracker(c, i["quotes"], i["today"], full)
    below = tax_lots.below_cost(c["open"], i["quotes"], i["today"])
    return M.ok({**out, "below_cost": below if full else {**below, "rows": []}, "names": c["names"],
                 "prices": i["live"], "trades": len(i["trades"])})


def delete_all(uid: str):
    """Every Money tax-tools figure the user saved: with "Delete my tax data"."""
    divs.delete(uid)
    adv.delete(uid)
