"""/money/... API for the tax tools: dividends, advance tax and the long-term gains exemption.

Everything here is the signed-in user's own data, built on the tax report's inputs (main.tax_inputs): their trades,
F&O totals and income, My Holdings and the stored corporate actions. Free sees the year totals, the due dates and
the exemption used; Basic adds the dividend detail; Pro adds the advance tax amounts and the lot-by-lot facts."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from . import corp_actions, holdings, holdings_file, instrument_kinds, tax_due, tax_lots, tax_total
from . import money_advance_tax as adv
from . import money_dividends as divs
from . import money_ltcg as ltcg
from .auth import current_profile
from .kite_service import IST
from .plans import FEATURE_PLAN, PLANS, allows
from .tax_lots import money

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
    corp_actions.prefetch("IN", syms)
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
                 "date_note": got.get("date_note"), "dividends": dividend_view(profile, fetch=False)})


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
def tax_computed(profile, i: dict) -> tuple[dict, list[dict], list[dict]]:
    """The tax report's sales: compute() plus the mutual fund and US sales, split into (the whole `c`, the sales taxed
    like shares, the other units' sales). `c["equity_open"]` is the open lots taxed like shares; `c["mf"]` and `c["us"]` are the added sales."""
    from . import money_us_routes
    M = _m()
    c = tax_lots.compute(i["trades"], i["acts"], i["fmv"], i["today"])
    mf = M.tax_mf(profile)
    usr = money_us_routes.for_tax(profile)
    c["realised"] += mf["rows"] + usr["rows"]
    c["names"].update(mf["names"])
    c["names"].update(usr["names"])
    c["mf"], c["us"] = mf, usr
    equity, units = tax_lots.split_units(c)
    c["equity_open"] = [l for l in c["open"] if instrument_kinds.tax_class(instrument_kinds.code_of(c["names"].get(l["key"]) or {})) == "equity"]
    return c, equity, units


def advance_view(profile, fy: int | None = None, i: dict | None = None) -> dict:
    """The year's instalments: dates for everyone, amounts on Pro. With no year asked for, Pro opens on the year before
    when its tax is still unpaid (DH-020: it opened on FY 2026-27's "None due" while FY 2025-26 had ₹77.6 lakh to pay);
    a year still owing beside the one shown is named in `owed`. `i`: the tax report's inputs, when already read."""
    t = today()
    cur = tax_lots.fy_of(t.isoformat())
    full = allows(profile["_plan"], "tax_tools")
    i = i or _m().tax_inputs(profile)
    if not full:
        return _advance_year(profile, fy or cur, None, i)
    last = _advance_year(profile, cur - 1, i)
    owing = (last.get("payable") or {}).get("total", 0) > 0.5 and t <= tax_due.revise_by(cur - 1)
    if fy is None and owing:
        return {**last, "opened_on_owed": True}
    out = last if fy == cur - 1 else _advance_year(profile, fy or cur, i)
    if owing and out["fy"] != cur - 1:
        p = last["payable"]
        out["owed"] = {"fy": p["fy"], "label": p["label"], "total": p["total"], "balance": p["balance"], "due": p["due"]}
    return out


def _exemption(fy: int, whole: dict) -> float | None:
    """The basic exemption limit of the regime, age band and residency the year's total was worked out for: income within it
    needs no return (RC2B-003). None when the total isn't available."""
    v = whole.get("inputs") or {}
    r = tax_total.rules(fy, v.get("regime", "new"), v.get("age", "below60"), v.get("resident", True)) if whole.get("available") else None
    return tax_total.basic_exemption(r["slabs"]) if r else None


def _advance_year(profile, fy: int, i: dict | None, plain: dict | None = None) -> dict:
    """One year's advance tax view (advance_view); `i` None on a plan without the amounts, which gets `plain` (the
    tax report's inputs) for the shares of the year's tax by each date: the tax report shows that total on every plan,
    so locking 15%, 45%, 75% and 100% of it hid only arithmetic (DH-021); the TDS and payments, what is still due and
    the interest stay on Pro."""
    t = today()
    full = i is not None
    # the reminders are the money calendar's (Basic), as Plans lists them: a plan without them never shows them on (DP2-004)
    can_remind = allows(profile["_plan"], "money_reminders")
    saved = adv.load(profile["id"])
    mine = saved["years"].get(fy) or adv.clean_year({})
    out = {"fy": fy, "label": tax_lots.fy_label(fy), "dates": adv.due_dates(fy), "remind": saved["remind"] and can_remind,
           "remind_locked": not can_remind, "remind_plan": PLANS[FEATURE_PLAN["money_reminders"]]["name"],
           "locked": not full, "as_of": t.isoformat(), "assumptions": adv.ASSUMPTIONS, "threshold": adv.THRESHOLD,
           "current_fy": tax_lots.fy_of(t.isoformat())}
    if not full:
        if plain is not None:
            try:
                c, equity, units = tax_computed(profile, plain)
                y = tax_lots.years_with_total([fy], equity, c["intraday"], instrument_kinds.bucket_rows(units, c["names"]), units,
                                              c["names"], plain["business"], plain["income"], dividends_for_tax(profile), limit=0)[fy]
                tax = (y["total"].get("total") or 0.0) if y["total"].get("available") else 0.0
                out["plain"] = {"tax": round(tax, 2), "due": tax >= adv.THRESHOLD,
                                "rows": [{**d, "amount": round(tax * d["pct"], 2)} for d in adv.due_dates(fy)]}
            except Exception as e:
                print("advance tax shares:", type(e).__name__)
        return out
    c, equity, units = tax_computed(profile, i)
    stored, est, ahead, rate = dividend_parts(profile["id"], fetch=False)
    dv = divs.view(stored, est, ahead, rate, t)
    div_events = divs.events(dv, stored, est, rate, fy)
    inputs = i["income"].get(fy)

    earlier = divs.for_total(dv)

    whole: dict = {}

    def tax_by(cut: str | None) -> float:
        """The year's total tax as the report works it out (years_with_total, with the losses brought forward), on the
        sales and dividends up to `cut`."""
        rows = [r for r in equity if cut is None or r["sold"] <= cut]
        other = [r for r in units if cut is None or r["sold"] <= cut]
        div = sum(a for d, a in div_events if cut is None or d <= cut)
        y = tax_lots.years_with_total([fy], rows, c["intraday"], instrument_kinds.bucket_rows(other, c["names"]), other, c["names"],
                                      i["business"], i["income"], {**earlier, fy: div}, limit=0)[fy]
        if cut is None:
            whole.update(y["total"])
        return (y["total"].get("total") or 0.0) if y["total"].get("available") else 0.0
    full_tax = tax_by(None)
    upto = [tax_by(d["date"]) for d in adv.due_dates(fy)]       # the last, to 15 March: the 234C proviso covers later gains
    business = any(b["fy"] == fy for b in i["business"]) or any(x["fy"] == fy for x in c["intraday"])
    turnover = tax_lots.business_year(fy, i["business"])["turnover"] + sum(x.get("turnover") or 0 for x in c["intraday"] if x["fy"] == fy)
    audit = tax_total.audit_applies(fy, turnover, business)      # the audit case's date, as extended (R29B-015, DH-001)
    s = adv.schedule(fy, full_tax, upto, mine["tds"], mine["paid"], t, business, audit)
    rounded = (whole.get("rounded") or {}).get("tax")
    out.update({"schedule": s, "inputs": mine,
                # DH-003: the year's tax with the interest on it and what's paid taken off, as one figure
                "payable": adv.payable(fy, s, full_tax if rounded is None else rounded, (whole.get("income") or {}).get("total") or 0.0,
                                       mine["paid"], t, business, audit, exempt=_exemption(fy, whole)),
                "return_due": tax_due.due(fy, tax_due.return_kind(business, audit))["date"].isoformat(), "audit": audit,
                "dividends_in_estimate": round(sum(a for _, a in div_events), 2),
                "dividend_tds": next((y["tds"]["expected"] for y in dv["years"] if y["fy"] == fy), 0.0),
                "income_saved": bool(inputs)})
    return out


WHEN = ("first", "second", "third", "last")


def _instalment_dates(profile, cur: int, i: dict) -> list[dict]:
    """This year's instalments for the calendar: the amount still due by each, or that none is due."""
    out = []
    now = _advance_year(profile, cur, i)
    s = now.get("schedule")
    for r in (s or {}).get("instalments") or []:
        if r["status"] == "passed":
            continue
        n = WHEN[r["n"]]
        if not s["due"]:
            out.append({"date": r["date"], "kind": "advance_none", "id": f"adv{r['n']}{cur}",
                        "title": f"Advance tax, {n} instalment: none due for {now['label']}",
                        "detail": f"Your {now['label']} estimate, less TDS, is {money(s['net'])}: below {money(s['threshold'])}, so no "
                                  "advance tax is due (section 208). It changes when your files or income for the year do.",
                        "url": "/money/tax-tools?tab=advance"})
        else:
            out.append({"date": r["date"], "kind": "advance_due", "id": f"adv{r['n']}{cur}", "amount": r["to_pay"],
                        "title": f"Advance tax, {n} instalment ({r['pct'] * 100:g}%): {money(r['to_pay'])} still due",
                        "detail": f"{r['pct'] * 100:g}% of {now['label']}'s estimated tax less TDS is {money(r['required'])} by "
                                  f"{r['label']}; paid by then so far {money(r['paid'])}. From your figures in Tax tools.",
                        "url": "/money/tax-tools?tab=advance"})
    return out


def _unpaid_date(profile, cur: int, i: dict, t: date) -> list[dict]:
    """The year before's tax still unpaid, as one item: on the return's due date while it is ahead, today once it has passed
    (the interest is running and a belated return can be filed until its last day, named in the item)."""
    last = _advance_year(profile, cur - 1, i)
    p = last.get("payable")
    if not (p and p["total"] > 0.5 and t <= tax_due.belated(cur - 1)):
        return []
    late = tax_due.belated(cur - 1)
    on = t if p["past_due"] else date.fromisoformat(p["due"])
    return [{"date": on.isoformat(), "kind": "self_assessment", "id": f"sa{cur - 1}", "amount": p["total"],
             "title": f"{p['label']} tax still unpaid: {money(p['total'])}",
             "detail": (f"Self-assessment tax is paid before the return is filed (section 140A). The figure is the tax "
                        f"less TDS and payments entered, with interest under sections 234A, 234B and 234C, as if paid by "
                        f"{tax_due.day(late if p['past_due'] else on)}. The return's due date is {tax_due.day(date.fromisoformat(p['due']))}"
                        + (f"; a belated return can be filed until {tax_due.day(late)}." if p["past_due"] else ".")),
             "url": "/money/tax-tools?tab=advance"}]


def calendar_dates(uid: str, days: int = 90, frm: date | None = None) -> list[dict]:
    """The money calendar's own tax items (its hook, money_calendar.HOOKS), for a plan with the advance tax amounts and
    tax files: this year's instalments with the amount still due by each, or that none is due when the estimate is under
    the threshold (DH-043: a generic 75% item for an estimate of ₹0), and the year before's tax still unpaid, on its
    return's due date (DH-040: no item said there was tax to pay before filing). Each instalment stands in for the plain
    one of its date (its kind has "advance" in it)."""
    from . import db
    from .plans import plan_of
    profile = db.get_profile(uid)
    if not profile:
        return []
    profile = {**profile, "_plan": plan_of(profile)}
    data = tax_lots.load(uid)
    if not allows(profile["_plan"], "tax_tools") or not (data["trades"] or data["business"]):
        return []
    t = today()
    cur = tax_lots.fy_of(t.isoformat())
    i = _m().tax_inputs(profile)
    out = []
    # RC2B-019, DH-043: the two parts stand apart, so one that fails (this year's schedule) doesn't take the year before's
    # unpaid tax out of the calendar with it
    try:
        out += _instalment_dates(profile, cur, i)
    except Exception as e:
        print("calendar instalments:", type(e).__name__)
    try:
        out += _unpaid_date(profile, cur, i, t)
    except Exception as e:
        print("calendar unpaid tax:", type(e).__name__)
    return out


def payable_for_report(profile, i: dict) -> dict | None:
    """The year being filed, for the tax report's headline (DH-003): the amount payable with the interest on Pro (it
    needs the TDS and payments entered in Tax tools), the plan that has it otherwise. Never stops the report."""
    fy = tax_lots.fy_of(today().isoformat()) - 1
    if not allows(profile["_plan"], "tax_tools"):
        return {"fy": fy, "locked": True, "plan": PLANS[FEATURE_PLAN["tax_tools"]]["name"]}
    try:
        p = _advance_year(profile, fy, i).get("payable")
        return {**p, "locked": False} if p else None
    except Exception as e:
        print("payable for the tax report:", type(e).__name__)
        return None


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
    if req.on:                    # turning them off is always allowed (DP2-004: Free could turn them on)
        M.need(profile, "money_reminders", "Advance tax reminders")
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
    c, equity, units = tax_computed(profile, i)
    full = allows(profile["_plan"], "tax_tools")
    out = ltcg.tracker({**c, "realised": equity, "open": c["equity_open"], "unit_rows": instrument_kinds.bucket_rows(units, c["names"])},
                       i["quotes"], i["today"], full)
    below = tax_lots.below_cost(c["open"], i["quotes"], i["today"])
    if not full:                  # lot-by-lot facts are Pro: a locked figure is no figure, never a false 0 (DP2-003)
        out = {**out, "open_lt": None, "soon_counts": None}
    return M.ok({**out, "below_cost": below if full else {**below, "rows": []}, "names": c["names"],
                 "prices": i["live"], "trades": len(i["trades"])})


def delete_all(uid: str):
    """Every Money tax-tools figure the user saved, and their US trades: with "Delete my tax data"."""
    divs.delete(uid)
    adv.delete(uid)
    from . import money_us_tax
    money_us_tax.delete(uid)
