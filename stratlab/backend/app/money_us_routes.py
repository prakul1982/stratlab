"""/money/us-tax: US stocks in Indian tax, for the signed-in user.

The user's US trades (a file from their US broker, or typed in; My Holdings' US stocks show which ones still need
their purchases), each sale's gain in rupees under Rule 115, US dividends with the 25% withheld and the foreign tax
credit, and the calendar year's Schedule FA table. Free sees every lot's term and each year's totals; Pro adds the
sale-by-sale rupee workings, the credit and Schedule FA (plans.py: us_tax). The sales also go into the tax report,
where they share set-off with Indian gains (main.tax_view, for plans with us_tax)."""
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from . import holdings, holdings_file, money_fx as fx, money_us_tax as us
from .money_mf import add_months
from .auth import current_profile
from .kite_service import IST
from .plans import FEATURE_PLAN, PLANS, allows
from .tax_lots import fy_label, fy_of

router = APIRouter(prefix="/money/us-tax", tags=["money"])
MAX_SYMBOLS = 40                  # US stocks whose history is read for one page


def _m():
    """The main module, for the shared helpers (ok, throttle, the tax report). Imported late: it imports us."""
    from . import main
    return main


def today() -> date:
    return datetime.now(IST).date()


class TradeReq(BaseModel):
    d: date
    side: str = Field(..., pattern="^(B|S)$")
    sym: str = Field(..., min_length=1, max_length=10)
    qty: float = Field(..., gt=0, le=us.MAX_QTY)
    price: float = Field(..., ge=0, le=us.MAX_PRICE)
    fees: float = Field(0, ge=0, le=us.MAX_PRICE)

    @field_validator("sym")
    @classmethod
    def ticker(cls, v: str) -> str:
        v = v.strip().upper().replace(".", "-")
        if not holdings.US_TICKER.fullmatch(v):
            raise ValueError("A US ticker is 1 to 6 letters or digits, like AAPL or BRK-B.")
        return v


class UploadReq(BaseModel):
    filename: str = Field("", max_length=200)
    data: str = Field(..., max_length=8 * 1024 * 1024)


# ---------- the stock's history: splits, dividends and closes ----------
def _yahoo():
    return _m().markets.providers["US"].yahoo


def stock_history(trades: list[dict], t: date, closes_from: date | None = None) -> dict:
    """{"splits": {sym: [...]}, "dividends": {sym: [{d, per_share}]}, "closes": {sym: {day: close}}, "missing": [sym]}
    for the stocks in the trades. Closes (in today's shares) only from `closes_from`, for Schedule FA. A stock whose
    history can't be read is listed in `missing`; its lots are then matched without splits."""
    first: dict[str, str] = {}
    for x in trades:
        first[x["sym"]] = min(first.get(x["sym"], x["d"]), x["d"])
    out = {"splits": {}, "dividends": {}, "closes": {}, "missing": []}
    try:
        y = _yahoo()
    except Exception:
        out["missing"] = sorted(first)
        return out
    for sym in sorted(first)[:MAX_SYMBOLS]:
        days = min((t - date.fromisoformat(first[sym])).days + 10, 3650 * 3)
        try:
            ev = y.events(sym, max(days, 30))
            out["splits"][sym] = [{"date": s["date"], "numerator": s["numerator"], "denominator": s["denominator"]} for s in ev["splits"]]
            out["dividends"][sym] = [{"d": d["date"], "per_share": d["amount"]} for d in ev["dividends"]]
            if closes_from:
                got = y.chart(sym, "1d", (t - closes_from).days + 10)
                out["closes"][sym] = {c["t"][:10]: c["c"] for c in got["candles"] if c.get("c")}
        except Exception as e:
            print("US tax history:", sym, str(e)[:120])
            out["missing"].append(sym)
    return out


def dividend_rows(uid: str, trades: list[dict], hist_divs: dict[str, list[dict]], splits: dict[str, list[dict]]) -> list[dict]:
    """The user's US dividends in dollars ({d, sym, amount, tds, src}): the lines of their own dividend files where a
    financial year has any, else each dividend in the stock's history × the shares the trades held on its ex-date
    (labelled estimated, dated by the ex-date)."""
    from . import money_dividends as divs
    own = [r for r in divs.load(uid)["rows"] if r["cur"] == "USD"]
    own_years = {fy_of(r["d"]) for r in own}
    out = [{"d": r["d"], "sym": r["sym"], "amount": r["amount"], "tds": r.get("tds"), "src": r.get("src") or "csv"} for r in own]
    for sym, rows in hist_divs.items():
        sp = splits.get(sym) or []
        lots = us.replay([x for x in trades if x["sym"] == sym], sp, "9999-12-31")
        for dv in rows:
            if fy_of(dv["d"]) in own_years:
                continue
            day_before = (date.fromisoformat(dv["d"]) - timedelta(days=1)).isoformat()      # held at the start of the ex-date
            q = sum(us._qty_on(l["changes"], day_before) for l in lots)
            if q > 1e-7:
                out.append({"d": dv["d"], "sym": sym, "amount": round(q * us._after_factor(sp, day_before) * dv["per_share"], 4),
                            "tds": None, "src": "estimated"})
    return sorted(out, key=lambda r: r["d"])


def avg_rate(year: dict | None) -> float:
    """The year's average rate of Indian tax (total tax ÷ total income) from the tax report's estimate, for the credit."""
    t = (year or {}).get("total") or {}
    inc = ((t.get("income") or {}).get("total") or 0.0) if t.get("available") else 0.0
    return (t.get("total") or 0.0) / inc if inc > 0 else 0.0


# ---------- for the tax report ----------
def for_tax(profile, fetch: bool = True) -> dict:
    """The US sales in the tax report's row shape (with their buckets), their names, and per financial year a short
    summary for the report's US section. Empty when the user has no US trades; rows only on plans with us_tax."""
    data = us.load(profile["id"])
    if not data["trades"]:
        return {"rows": [], "names": {}, "years": {}, "allowed": allows(profile["_plan"], "us_tax"), "count": 0}
    t = today()
    h = stock_history(data["trades"], t) if fetch else {"splits": {}, "dividends": {}, "closes": {}, "missing": []}
    hist = fx.ensure("USD", fetch)
    m = us.match(data["trades"], h["splits"])
    rows = us.realised(m, hist)
    years: dict[int, dict] = {}
    for r in rows:
        y = years.setdefault(r["fy"], {"count": 0, "st": 0.0, "lt": 0.0, "unpriced": 0, "fallback": False})
        y["count"] += 1
        if r["unpriced"]:
            y["unpriced"] += 1
            continue
        y["st" if r["term"] == "ST" else "lt"] += r["gain_inr"]
        y["fallback"] |= r["fallback"]
    allowed = allows(profile["_plan"], "us_tax")
    return {"rows": us.tax_rows(rows) if allowed else [], "names": us.names(data["trades"], _known(profile["id"])),
            "years": {fy: {**y, "st": round(y["st"], 2), "lt": round(y["lt"], 2)} for fy, y in years.items()},
            "allowed": allowed, "count": len(data["trades"]), "plan": PLANS[FEATURE_PLAN["us_tax"]]["name"]}


def _known(uid: str) -> dict[str, str]:
    """US company names from My Holdings, by ticker."""
    return {i["symbol"]: i.get("name") or i["symbol"] for i in holdings.load(uid)["items"] if holdings.market_of(i) == "US"}


# ---------- Schedule FA ----------
def fa_build(cy: int, trades: list[dict], h: dict, hist: dict, divs_all: list[dict], known: dict[str, str]) -> dict:
    """Schedule FA for a calendar year from the trades and the stocks' history: the dividends from the user's own
    files where a stock has any that year, else from the stock's history."""
    fa_divs: dict[str, list[dict]] = {}
    own = [r for r in divs_all if r["src"] != "estimated" and str(r["d"])[:4] == str(cy)]
    for r in own:
        fa_divs.setdefault(r["sym"], []).append({"d": r["d"], "amount": r["amount"]})
    for sym, dv in h["dividends"].items():
        if sym not in fa_divs:
            fa_divs[sym] = [{"d": x["d"], "per_share": x["per_share"]} for x in dv]
    fa = us.schedule_fa(cy, trades, h["splits"], h["closes"], fa_divs, hist, {**known, **{x["sym"]: x["name"] for x in trades if x.get("name")}})
    return {**fa, "missing_history": h["missing"]}


def fa_for(profile, cy: int) -> dict | None:
    """Schedule FA for one calendar year, or None without US trades (for the ITR export)."""
    uid = profile["id"]
    trades = us.load(uid)["trades"]
    if not trades:
        return None
    t = today()
    h = stock_history(trades, t, date(cy, 1, 1))
    return fa_build(cy, trades, h, fx.ensure("USD"), dividend_rows(uid, trades, h["dividends"], h["splits"]), _known(uid))


def us_dividends(profile, fy: int, year: dict | None) -> dict | None:
    """One financial year's US dividends with the foreign tax credit (for the ITR export), or None without US trades
    or US dividends."""
    from . import money_dividends as divs
    uid = profile["id"]
    trades = us.load(uid)["trades"]
    if trades:
        h = stock_history(trades, today())
        rows = dividend_rows(uid, trades, h["dividends"], h["splits"])
    else:
        rows = [{"d": r["d"], "sym": r["sym"], "amount": r["amount"], "tds": r.get("tds"), "src": r.get("src")}
                for r in divs.load(uid)["rows"] if r["cur"] == "USD"]
    if not any(fy_of(r["d"]) == fy for r in rows):
        return None
    out = us.dividends(rows, fx.ensure("USD"), fy, avg_rate(year))
    out["estimated"] = any(r["src"] == "estimated" and fy_of(r["d"]) == fy for r in rows)
    return out


# ---------- the page ----------
def view(profile, fy: int | None = None, cy: int | None = None) -> dict:
    """Everything the page shows: the trades, the gaps against My Holdings, each financial year's gains (sale by sale
    on Pro), dividends and the credit (Pro), every open lot's term, and Schedule FA for a calendar year (Pro)."""
    uid = profile["id"]
    t = today()
    full = allows(profile["_plan"], "us_tax")
    data = us.load(uid)
    trades = data["trades"]
    cy = cy or t.year - 1
    h = stock_history(trades, t, date(cy, 1, 1) if full and trades else None)
    hist = fx.ensure("USD")
    known = _known(uid)
    m = us.match(trades, h["splits"])
    rows = us.realised(m, hist)
    # every lot still open, with its term today and the day it turns long term
    open_lots = []
    for l in m["open"]:
        lt = us.long_term(l["d"], t.isoformat())
        open_lots.append({"symbol": l["sym"], "bought": l["d"], "qty": round(l["qty"], 6), "cost_usd": round(l["cost_usd"], 2),
                          "term": "LT" if lt else "ST", "long_from": None if lt else (add_months(l["d"], us.LT_MONTHS) + timedelta(days=1)).isoformat()})
    # My Holdings' US stocks the trades don't cover
    have: dict[str, float] = {}
    for l in m["open"]:
        have[l["sym"]] = have.get(l["sym"], 0.0) + l["qty"] * us._after_factor(h["splits"].get(l["sym"]) or [], t.isoformat())
    gaps = []
    for i in holdings.load(uid)["items"]:
        if holdings.market_of(i) != "US":
            continue
        got = have.get(i["symbol"], 0.0)
        if float(i["qty"]) - got > 1e-4:
            gaps.append({"symbol": i["symbol"], "name": i.get("name") or i["symbol"], "held": float(i["qty"]), "in_trades": round(got, 6),
                         "missing": round(float(i["qty"]) - got, 6), "avg": i.get("avg")})
    fys = sorted({r["fy"] for r in rows} | {fy_of(t.isoformat()), fy_of(t.isoformat()) - 1}, reverse=True)
    fy = fy if fy in fys else fy_of(t.isoformat()) - 1          # the year being filed now, like every Money page
    tax_year = None
    if full and trades:
        tax_year = next((y for y in _m().tax_view(profile)["years"] if y["fy"] == fy), None)
    divs_all = dividend_rows(uid, trades, h["dividends"], h["splits"]) if trades or full else []
    years = []
    for y in fys:
        mine = [r for r in rows if r["fy"] == y]
        priced = [r for r in mine if not r["unpriced"]]
        out = {"fy": y, "label": fy_label(y), "count": len(mine), "unpriced": len(mine) - len(priced),
               "st": round(sum(r["gain_inr"] for r in priced if r["term"] == "ST"), 2),
               "lt": round(sum(r["gain_inr"] for r in priced if r["term"] == "LT"), 2),
               "sale": round(sum(r["sale_inr"] for r in priced), 2), "fallback": any(r.get("fallback") for r in priced)}
        if full and y == fy:
            out["rows"] = [_row(r) for r in sorted(mine, key=lambda r: (r["sold"], r["sym"]))]
            out["dividends"] = us.dividends(divs_all, hist, y, avg_rate(tax_year))
            out["dividends"]["estimated"] = any(r["src"] == "estimated" and fy_of(r["d"]) == y for r in divs_all)
        years.append(out)
    fa = fa_build(cy, trades, h, hist, divs_all, known) if full and trades else None
    sbi_days = sorted(hist["sbi"])
    return {"as_of": t.isoformat(), "fy": fy, "cy": cy, "cys": list(range(t.year - 1, t.year - 6, -1)), "locked": not full,
            "plan": PLANS[FEATURE_PLAN["us_tax"]]["name"],
            "trades": sorted(({**x, "id": x.get("id") or ""} for x in trades), key=lambda x: (x["d"], x["sym"]), reverse=True),
            "files": data["files"], "gaps": gaps, "short": {k: round(v, 6) for k, v in m["short"].items()}, "open_lots": open_lots,
            "years": years, "fa": fa, "facts": us.FACTS, "assumptions": us.ASSUMPTIONS, "missing_history": h["missing"],
            "rates": {"available": bool(hist["sbi"] or hist["rbi"]), "sbi_from": sbi_days[0] if sbi_days else None,
                      "sbi_to": sbi_days[-1] if sbi_days else None, "source": fx.SBI, "fallback": fx.RBI},
            "names": {k: v["name"] for k, v in us.names(trades, known).items()}}


def _row(r: dict) -> dict:
    rate = lambda x: {"rate": x["rate"], "on": x["on"], "fallback": x["fallback"]} if x else None
    return {"symbol": r["sym"], "bought": r["bought"], "sold": r["sold"], "qty": round(r["qty"], 6), "cost_usd": round(r["cost_usd"], 2),
            "sale_usd": round(r["sale_usd"], 2), "rate_buy": rate(r["rate_buy"]), "rate_sell": rate(r["rate_sell"]),
            "cost": round(r["cost_inr"], 2) if not r["unpriced"] else None,
            "indexed_cost": round(r["indexed_cost"], 2) if r.get("indexed_cost") is not None else None,
            "sale": round(r["sale_inr"], 2) if not r["unpriced"] else None, "gain": round(r["gain_inr"], 2) if not r["unpriced"] else None,
            "term": r["term"], "rate": r["rate"], "bucket": r["bucket"]}


@router.get("")
def us_tax(fy: int | None = Query(None, ge=2000, le=2100), cy: int | None = Query(None, ge=2000, le=2100),
           profile=Depends(current_profile)):
    """US stocks in Indian tax: the user's US trades, each year's gains in rupees (Rule 115), every open lot's term,
    and on Pro the sale-by-sale workings, US dividends with the foreign tax credit, and Schedule FA for a calendar
    year. Arithmetic on the user's own trades, not tax advice."""
    return _m().ok(view(profile, fy, cy))


@router.post("/trades")
def add_trade(req: TradeReq, profile=Depends(current_profile)):
    """Add one US purchase or sale by hand (date, buy or sell, ticker, shares, price and fees in dollars)."""
    M = _m()
    M.throttle(profile, "tax_edit", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    if req.d > today():
        M.err(400, "future_date", "That date is still to come.")
    row = {"d": req.d.isoformat(), "side": req.side, "sym": req.sym, "qty": round(req.qty, 6), "price": round(req.price, 6),
           "fees": round(req.fees, 4), "src": "manual", "id": uuid.uuid4().hex[:12]}
    data = us.load(profile["id"])
    if len(data["trades"]) >= us.MAX_TRADES:
        M.err(400, "too_many", f"Up to {us.MAX_TRADES:,} US trades are kept.")
    data["trades"].append(row)
    us.save(profile["id"], data)
    return M.ok(view(profile, fy_of(row["d"])))


@router.delete("/trades/{tid}")
def delete_trade(tid: str, profile=Depends(current_profile)):
    """Delete one US trade (by its id: trades typed in, or read from a file since ids were added)."""
    M = _m()
    if not us.remove(profile["id"], tid[:40]):
        M.err(404, "not_found", "That trade isn't in your list.")
    return M.ok(view(profile))


@router.post("/import", openapi_extra={"requestBody": {"content": {
    "application/json": {"schema": UploadReq.model_json_schema()},
    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
async def import_trades(request: Request, filename: str = Query("", max_length=200), profile=Depends(current_profile)):
    """A file of US trades from the user's US broker (CSV or Excel: date, buy or sell, ticker, shares, price in
    dollars, fees). The file is the request body (the name in the query), or base64 in JSON ({filename, data})."""
    from fastapi.concurrency import run_in_threadpool
    M = _m()
    M.throttle(profile, "us_import", 30, 3600, "That's a lot of uploads in an hour. Try again a little later.")
    body = await request.body()
    if request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json":
        try:
            req = UploadReq.model_validate_json(body)
        except Exception:
            M.err(400, "bad_upload", "The file didn't arrive whole. Pick it again.")
        filename = req.filename
        data = M.upload_bytes(req.data, "A trades file is much smaller; check it's the right file.", us.MAX_BYTES)
    else:
        if len(body) > us.MAX_BYTES:
            M.err(413, "file_too_big", f"That file is larger than {us.MAX_BYTES // (1024 * 1024)} MB.")
        data = body
    return await run_in_threadpool(_import, profile, data, filename)


def _import(profile, data: bytes, filename: str):
    M = _m()
    try:
        got = us.parse_upload(data, filename)
    except holdings_file.FileError as e:
        M.err(400, "bad_file", str(e))
    for r in got["rows"]:
        r["id"] = uuid.uuid4().hex[:12]
    added, dup = us.add(profile["id"], got["rows"], filename)
    return M.ok({"read": len(got["rows"]), "added": added, "duplicates": dup, "problems": got["problems"][:50],
                 "month_first": got["month_first"], "us": view(profile)})


@router.delete("")
def delete_all(profile=Depends(current_profile)):
    """Delete every US trade the user saved."""
    us.delete(profile["id"])
    return {"deleted": True}


@router.get("/schedule-fa.csv")
def fa_csv(cy: int = Query(..., ge=2000, le=2100), profile=Depends(current_profile)):
    """Schedule FA Table A3 for a calendar year as a CSV, laid out like the schedule (Pro)."""
    from . import money_itr
    M = _m()
    M.need(profile, "us_tax", "Schedule FA")
    M.throttle(profile, "tax_export", 60, 3600, "That's a lot of downloads in an hour. Try again a little later.")
    v = view(profile, None, cy)
    return Response(money_itr.csv_text(money_itr.fa_table(v["fa"])), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="stratlab-schedule-FA-CY{cy}.csv"'})
