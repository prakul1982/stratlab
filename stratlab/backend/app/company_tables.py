"""A company's tables beside its page and its deep dive (lane c-f2): its peers, its financial statements by year and quarter,
and its shareholding by quarter. India and the US.

Every figure is one StratLab already keeps:

- Peers come from the stored screens index (screens.load_index): the company's own industry in the stored classification
  first, widened to its sector when the industry has too few, then the companies nearest it in market value (the theme
  code's "own sector, similar market value" comparison, theme_data.comparable_peers, without its ten-company floor: a page
  shows the nearest few instead of none). Market value, sales growth (3-year compounded), EBITDA margin, net margin, ROCE (ROE
  for a bank or other lender, whose capital is its deposits), P/E, each as the index stores it.
- Statements are the fundamentals pages' own tables (India: profit and loss, balance sheet, cash flow, ratios, quarters, as
  the company page and the deep dive read them, consolidated and standalone where both are kept; the US: the same tables built
  from the company's SEC filings). Nothing is filled in: a figure a period doesn't have is None ("–" on the page, with a note).
  The few ratios worked out here are plain arithmetic on two figures of the same column (a margin, a debt-to-equity).
- Shareholding is the fundamentals page's quarterly shareholding table (promoters, FIIs, DIIs, government, public, the number
  of shareholders), the same table "Who owns it" shows the latest quarter of. US companies file no such pattern: said so.

Plans (the owner: "the public stuff is only to attract people"): Free sees a teaser (the three nearest peers and its own row,
the latest three years of profit and loss, the latest quarter's shareholding); Basic sees everything, sorts the peers and gets
the shareholding chart (feature tables); Pro downloads the statements as a workbook or CSV and the peers as CSV
(Pro's feature export, beside a notebook's export). The trimming is done here, so a locked figure never leaves the server.

Facts only: no figure is called good or bad, no company is ranked as a choice."""
import csv
import io
import math
import re
import statistics

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from .auth import current_profile
from .branding import public_text
from .intel.net import NotFound, SourceError
from .plans import FEATURE_PLAN, PLANS, allows, plan_of
from .responses import err, ok

router = APIRouter(tags=["research"])

FULL = "tables"                  # Basic: every peer and sorting, every statement and quarter, 12 quarters of shareholding and the chart
EXPORT = "export"                # Pro's export: the statements as a workbook or CSV, the peers as CSV
PEERS_MAX = 10                   # peers in the full table
PEERS_FREE = 3                   # peers a Free account or a visitor sees, beside the company's own row
PEERS_WIDEN = 3                  # an industry with fewer peers than this is widened to the company's sector
YEARS_MAX = 12                   # years of statements kept on the page (as many as stored, up to this)
YEARS_FREE = 3                   # the latest years of profit and loss a Free account sees
QUARTERS_MAX = 12                # quarters of results and of shareholding
MISSING_NOTE = "– : the stored filings have no figure for that period."

_wire: dict = {"screener": None, "sec": None, "facts": None, "bse_code": None, "index": None}


def setup(screener=None, sec=None, facts=None, bse_code=None, index=None) -> None:
    """The readers this module uses, given by main: getters of the Indian fundamentals source and the SEC reader (tests swap the
    objects on main, so they are asked for each time), a company's stored page facts (region, symbol) -> dict, the BSE code of a
    BSE-only company, and the screens index (region) -> dict."""
    _wire.update(screener=screener, sec=sec, facts=facts, bse_code=bse_code, index=index)


def _source(name: str):
    got = _wire.get(name)
    try:
        return got() if callable(got) else got
    except Exception:
        return None


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _r(v, dp: int = 1) -> float | None:
    v = _num(v)
    return None if v is None else round(v, dp)


def _region(region: str) -> str:
    r = str(region or "").upper()
    if r not in ("IN", "US"):
        err(400, "bad_region", "Company pages cover India (IN) and the US (US).")
    return r


_SYM = re.compile(r"^[A-Z0-9][A-Z0-9&\-._^]{0,19}$")


def _symbol(symbol: str, region: str) -> str:
    s = str(symbol or "").strip().upper()
    if region == "US":
        s = s.replace(".", "-")
    if not _SYM.match(s):
        err(400, "bad_symbol", "That doesn't look like a ticker.")
    return s


def access(profile: dict) -> dict:
    """What this account sees: {"full": Basic and up, "export": Pro}."""
    plan = plan_of(profile)
    return {"full": allows(plan, FULL), "export": allows(plan, EXPORT)}


def plan_name(feature: str) -> str:
    return PLANS[FEATURE_PLAN[feature]]["name"]


def lock(message: str, feature: str = FULL) -> dict:
    """A locked part, said with the plan that gives it (the page adds the plan's price and its button)."""
    return {"plan": FEATURE_PLAN[feature], "message": public_text(message)}


# ---------- peers ----------
def is_lender(row: dict | None, facts: dict | None) -> bool:
    """A bank or other lender: its stored page says so; else its index row has a return on equity and neither an EBITDA margin nor a
    return on capital employed (the index leaves both out for a lender)."""
    if isinstance(facts, dict) and facts.get("bank") is not None:
        return bool(facts.get("bank"))
    row = row or {}
    return row.get("opm") is None and row.get("roce") is None and row.get("roe") is not None


def peer_set(rows: list[dict], symbol: str) -> tuple[dict | None, list[dict], str]:
    """(the company's own index row, its peers nearest first, the set's basis "industry" | "sector" | "none"). Peers share its
    industry (its sector when the industry has fewer than PEERS_WIDEN others), its market and, for a US company, its kind of
    filer (a foreign filer beside foreign filers only); they are ordered by how near their market value is to its own (the
    theme's "similar market value", half to twice first), those with no market value last. At most PEERS_MAX."""
    own = next((r for r in rows if r.get("symbol") == symbol), None)
    if not own:
        return None, [], "none"

    def alike(r: dict) -> bool:
        return r.get("symbol") != symbol and bool(r.get("foreign")) == bool(own.get("foreign"))
    basis, got = "none", []
    if own.get("industry"):
        got = [r for r in rows if alike(r) and r.get("industry") == own["industry"]]
        basis = "industry" if got else "none"
    if len(got) < PEERS_WIDEN and own.get("sector"):
        wide = [r for r in rows if alike(r) and r.get("sector") == own["sector"]]
        if len(wide) > len(got):
            got, basis = wide, "sector"
    if not got:
        return own, [], "none"
    cap = _num(own.get("market_cap"))

    def distance(r: dict) -> tuple:
        m = _num(r.get("market_cap"))
        if m is None or m <= 0:
            return (2, 0.0, r.get("symbol") or "")
        if not cap or cap <= 0:
            return (1, -m, r.get("symbol") or "")
        return (0, abs(math.log(m / cap)), r.get("symbol") or "")
    return own, sorted(got, key=distance)[:PEERS_MAX], basis


def peer_row(r: dict, lender: bool, own: bool = False) -> dict:
    """One line of the peers table, as the index stores it."""
    return {"symbol": r.get("symbol"), "name": r.get("name") or r.get("symbol"), "own": own,
            "market_cap": _num(r.get("market_cap")), "sales_growth": _r(r.get("sales_cagr_3y")),
            "ebitda": None if lender else _r(r.get("opm")), "net": _r(r.get("net_margin")),
            "ret": _r(r.get("roe")) if lender else _r(r.get("roce")), "pe": _r(r.get("pe"))}


PEER_KEYS = ("market_cap", "sales_growth", "ebitda", "net", "ret", "pe")


def median_row(rows: list[dict]) -> dict:
    """The median of each column over the rows given (those with the figure), and how many it is of."""
    out: dict = {}
    for k in PEER_KEYS:
        vals = [x[k] for x in rows if x.get(k) is not None]
        out[k] = (round(statistics.median(vals), 1 if k != "market_cap" else 0) if vals else None)
        out[f"{k}_n"] = len(vals)
    return out


BASIS_WORDS = {"industry": "same industry, nearest in market value", "sector": "same sector (its industry has too few listed companies), nearest in market value",
               "none": "no companies of its industry or sector in the stored list"}


def peers_view(region: str, symbol: str, rows: list[dict], facts: dict | None, see: dict, as_of: str | None = None) -> dict:
    own, peers, basis = peer_set(rows, symbol)
    lender = is_lender(own, facts)
    all_rows = [peer_row(r, lender) for r in peers]
    shown = all_rows if see["full"] else all_rows[:PEERS_FREE]
    hidden = len(all_rows) - len(shown)
    out = {"symbol": symbol, "region": region, "basis": basis, "basis_words": BASIS_WORDS[basis], "lender": lender,
           "return_label": "ROE" if lender else "ROCE", "unit": "₹ crore" if region == "IN" else "$ million",
           "own": peer_row(own, lender, own=True) if own else None, "rows": shown, "total": len(all_rows),
           "median": median_row(shown) if shown else None, "can_sort": see["full"], "can_export": see["export"], "as_of": as_of,
           "locked": None, "export_locked": None}
    if hidden > 0:
        out["locked"] = lock(f"The other {hidden} peer{'s' if hidden != 1 else ''} and sorting the table are on the {plan_name(FULL)} plan.")
    if see["full"] and not see["export"] and all_rows:
        out["export_locked"] = lock(f"Downloading the peers as CSV is on the {plan_name(EXPORT)} plan.", EXPORT)
    return out


def _index(region: str) -> dict:
    load = _wire.get("index")
    if load is None:
        from . import screens
        load = screens.load_index
    try:
        return load(region) or {}
    except Exception:
        return {}


def _facts(region: str, symbol: str) -> dict | None:
    f = _wire.get("facts")
    try:
        return f(region, symbol) if f else None
    except Exception:
        return None


def _peers(region: str, symbol: str, see: dict) -> dict:
    ix = _index(region)
    return peers_view(region, symbol, ix.get("rows") or [], _facts(region, symbol), see, ix.get("at"))


@router.get("/research/company/{region}/{symbol}/peers")
def peers(region: str, symbol: str, profile=Depends(current_profile)):
    """The company's peers with their market value and returns. Free: the three nearest and its own row; Basic: up to ten, sortable."""
    r = _region(region)
    return ok(_peers(r, _symbol(symbol, r), access(profile)))


def _csv(head: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head)
    for row in rows:
        w.writerow(["" if v is None else (f"'{v}" if isinstance(v, str) and v[:1] in "=+-@" else v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _file(data: bytes, name: str, media: str) -> Response:
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                             "Cache-Control": "private, no-store"})


def _need_export(profile) -> None:
    if not access(profile)["export"]:
        err(402, "upgrade_required", f"Downloading a company's tables is on the {plan_name(EXPORT)} plan.")


@router.get("/research/company/{region}/{symbol}/peers.csv")
def peers_csv(region: str, symbol: str, profile=Depends(current_profile)):
    """The full peers table as CSV (Pro)."""
    _need_export(profile)
    r = _region(region)
    sym = _symbol(symbol, r)
    v = _peers(r, sym, {"full": True, "export": True})
    head = ["Symbol", "Name", f"Market value ({v['unit']})", "Sales growth, 3 years (% a year)", "EBITDA margin (%)", "Net margin (%)",
            f"{v['return_label']} (%)", "P/E"]
    lines = [v["own"]] if v["own"] else []
    lines += v["rows"]
    body = [[x["symbol"], x["name"], *(x[k] for k in PEER_KEYS)] for x in lines]
    if v["median"]:
        body.append(["", "Median of the peers", *(v["median"][k] for k in PEER_KEYS)])
    return _file(_csv(head, body), f"stratlab-{sym}-peers.csv", "text/csv; charset=utf-8")


# ---------- statements ----------
def is_year(col) -> bool:
    return str(col).strip().upper() != "TTM"


SECTIONS = (("pl", "Profit and loss"), ("balance", "Balance sheet"), ("cashflow", "Cash flow"), ("ratios_table", "Ratios"))


def _label(k: str) -> str:
    return re.sub(r"\s*\+\s*$", "", str(k)).strip()


def kind_of(label: str) -> str:
    """How a row's figures are written: a percentage, days, a per-share figure, a count or money."""
    t = label.lower()
    # a growth row is a percentage even where the source's label has no "%" (LIVE8B-017: "Sales growth 16 15 9 4" printed as money)
    if "%" in t or "margin" in t or "growth" in t:
        return "pct"
    if "days" in t or "cycle" in t:
        return "days"
    if t.startswith("eps") or "per share" in t:
        return "per_share"
    if "no. of" in t or "number of" in t:
        return "count"
    if "debt to equity" in t or t.endswith("(x)"):
        return "ratio"
    return "money"


def aligned(t: dict | None, cols: list[str]) -> list[dict]:
    """A table's rows on the given columns ({label, kind, values}); a column the table doesn't have is None in every row."""
    if not t or not t.get("cols"):
        return []
    at = {str(c).strip(): i for i, c in enumerate(t["cols"])}
    out = []
    for k, vals in (t.get("rows") or {}).items():
        vals = list(vals or [])
        row = [(_num(vals[at[c]]) if c in at and at[c] < len(vals) else None) for c in cols]
        out.append({"label": _label(k), "kind": kind_of(_label(k)), "values": row})
    return out


def _find(rows: list[dict], *starts: str) -> list | None:
    hit = next((r for r in rows if r["label"].lower().startswith(starts)), None)
    return hit["values"] if hit else None


def _ratio(a: list | None, b: list | None, scale: float = 100.0, dp: int = 1) -> list | None:
    if not a or not b:
        return None
    out = [round(x / y * scale, dp) if x is not None and y not in (None, 0) and y > 0 else None for x, y in zip(a, b)]
    return out if any(v is not None for v in out) else None


def _growth(a: list | None) -> list | None:
    if not a:
        return None
    out = [None] + [round((y / x - 1) * 100, 1) if x not in (None, 0) and x > 0 and y is not None else None for x, y in zip(a, a[1:])]
    return out if any(v is not None for v in out) else None


def worked_ratios(pl: list[dict], bal: list[dict], have: set[str], lender: bool) -> list[dict]:
    """The usual ratios worked out from two figures of the same year, each only where the page's own ratios table doesn't
    already have it: sales growth, EBITDA margin, net margin, return on equity (year-end equity), debt to equity."""
    sales = _find(pl, "sales", "revenue")
    profit = _find(pl, "net profit")
    equity = _find(bal, "equity", "total equity", "shareholders")
    reserves = _find(bal, "reserves")
    if equity and reserves and _find(bal, "equity capital"):
        equity = [(a + b) if a is not None and b is not None else None for a, b in zip(_find(bal, "equity capital"), reserves)]
    debt = _find(bal, "borrowings", "debt")
    out = []

    def add(label: str, values, kind="pct"):
        if values and not any(label.lower().startswith(h) for h in have):
            out.append({"label": label, "kind": kind, "values": values, "worked": True})
    add("Sales growth %" if not lender else "Revenue growth %", _growth(sales))
    if not lender and not _find(pl, "opm"):
        add("EBITDA margin %", _ratio(_find(pl, "operating profit"), sales))
    add("Net margin %", _ratio(profit, sales))
    add("Return on equity %", _ratio(profit, equity))
    if not lender:
        add("Debt to equity", _ratio(debt, equity, 1.0, 2), "ratio")
    return out


def statements_view(p: dict, region: str, symbol: str, see: dict, bases: list[str]) -> dict:
    """The statements of one fundamentals page in the page's shape: years (oldest first, at most YEARS_MAX), each section's rows,
    the ratios, the last QUARTERS_MAX quarters; trimmed to the latest YEARS_FREE years of profit and loss for Free."""
    pl_t = p.get("pl") or {}
    cols = [str(c).strip() for c in pl_t.get("cols") or [] if is_year(c)]
    if not cols:      # no profit and loss table: the balance sheet's years
        cols = [str(c).strip() for c in (p.get("balance") or {}).get("cols") or [] if is_year(c)]
    stored = len(cols)
    cols = cols[-YEARS_MAX:]
    lender = bool(p.get("bank")) or any(str(k).lower().startswith(("revenue", "financing")) for k in (pl_t.get("rows") or {}))
    sections = []
    for key, title in SECTIONS:
        rows = aligned(p.get(key), cols)
        if key == "ratios_table":
            have = {r["label"].lower().rstrip(" %") for r in rows}
            rows = rows + worked_ratios(sections[0]["rows"] if sections else [], next((s["rows"] for s in sections if s["key"] == "balance"), []),
                                        have, lender)
        rows = [r for r in rows if any(v is not None for v in r["values"])]
        if rows:
            sections.append({"key": key, "title": title, "rows": rows})
    q_t = p.get("quarters") or {}
    q_cols = [str(c).strip() for c in q_t.get("cols") or []][-QUARTERS_MAX:]
    q_rows = [r for r in aligned(q_t, q_cols) if any(v is not None for v in r["values"])]
    missing = any(v is None for s in sections for r in s["rows"] for v in r["values"]) or any(v is None for r in q_rows for v in r["values"])
    unit = p.get("unit") or ("₹ crore" if region == "IN" else "$ million")
    if region == "IN" and unit in ("₹ Cr", "Rs Cr"):
        unit = "₹ crore"
    out = {"symbol": symbol, "region": region, "name": p.get("name") or symbol, "unit": unit, "currency": p.get("currency") or ("INR" if region == "IN" else "USD"),
           "basis": p.get("basis") or "consolidated", "bases": bases, "basis_note": public_text(p["basis_note"]) if p.get("basis_note") else None,
           "lender": lender, "years_stored": stored, "cols": cols, "sections": sections,
           "quarters": {"cols": q_cols, "rows": q_rows} if q_cols and q_rows else None,
           "full": see["full"], "can_export": see["export"], "locked": None, "export_locked": None,
           "notes": [MISSING_NOTE] if missing else [], "numbers_at": p.get("fetched_at")}
    if not see["full"]:
        keep = cols[-YEARS_FREE:]
        pl = next((s for s in sections if s["key"] == "pl"), None)
        out["cols"] = keep
        out["sections"] = [{**pl, "rows": [{**r, "values": r["values"][-len(keep):]} for r in pl["rows"]]}] if pl and keep else []
        more = [t for s, t in ((s["key"], s["title"]) for s in sections) if s != "pl"]
        out["quarters"] = None
        out["locked"] = lock(f"All {len(cols)} years of profit and loss, the balance sheet, cash flow, ratios and the last {len(q_cols) or QUARTERS_MAX} quarters"
                             f"{', standalone and consolidated' if len(bases) > 1 else ''} are on the {plan_name(FULL)} plan.")
        out["hidden"] = {"years": max(0, len(cols) - len(keep)), "sections": more, "quarters": len(q_cols)}
        out["notes"] = [MISSING_NOTE] if any(v is None for s in out["sections"] for r in s["rows"] for v in r["values"]) else []
    elif not see["export"]:
        out["export_locked"] = lock(f"Downloading the statements as Excel or CSV is on the {plan_name(EXPORT)} plan.", EXPORT)
    return out


def _same(a: dict, b: dict) -> bool:
    """Two fundamentals pages of the same company (the other basis of the page read): the same name and the same latest year."""
    def last(p):
        cols = [c for c in (p.get("pl") or {}).get("cols") or [] if is_year(c)]
        return str(cols[-1]).strip() if cols else None
    return bool(a.get("name")) and a.get("name") == b.get("name") and last(a) is not None and last(a) == last(b)


def india_pages(symbol: str) -> dict[str, dict]:
    """{basis: page} for an Indian company: the page the company page reads (consolidated, unless those accounts go back much less
    far), and the other basis when the source keeps it for the same company."""
    scr = _source("screener")
    if scr is None:
        err(503, "source_error", "Company figures aren't available just now.")
    code = None
    try:
        code = _wire["bse_code"](symbol) if _wire.get("bse_code") else None
    except Exception:
        code = None
    try:
        p = scr.company(code or symbol)
    except NotFound as e:
        err(404, "not_found", str(e))
    except SourceError as e:
        err(503 if getattr(e, "busy", False) else 502, "source_error", str(e))
    basis = p.get("basis") or "consolidated"
    pages = {basis: p}
    other = "standalone" if basis == "consolidated" else "consolidated"
    page = getattr(scr, "_page", None)
    if callable(page):
        try:
            q = page(f"/company/{code or symbol}/" + ("consolidated/" if other == "consolidated" else ""))
        except Exception:
            q = None
        if isinstance(q, dict) and q.get("pl") and _same(p, q):
            pages[other] = {**q, "basis": other}
    return pages


def us_pages(symbol: str) -> dict[str, dict]:
    sec = _source("sec")
    if sec is None:
        err(503, "source_error", "Company figures aren't available just now.")
    try:
        p = sec.company(symbol)
    except NotFound as e:
        err(404, "not_found", str(e))
    except SourceError as e:
        err(503 if getattr(e, "busy", False) else 502, "source_error", str(e))
    return {"consolidated": {**p, "basis": "consolidated"}}


def pages_of(region: str, symbol: str) -> dict[str, dict]:
    return india_pages(symbol) if region == "IN" else us_pages(symbol)


def _statements(region: str, symbol: str, basis: str | None, see: dict) -> dict:
    pages = pages_of(region, symbol)
    order = [b for b in ("consolidated", "standalone") if b in pages]
    first = next(iter(pages))
    # another basis than the page's own is part of the full statements (Basic)
    pick = basis if basis in pages and (see["full"] or basis == first) else first
    return statements_view(pages[pick], region, symbol, see, order)


@router.get("/research/company/{region}/{symbol}/statements")
def statements(region: str, symbol: str, basis: str | None = None, profile=Depends(current_profile)):
    """Profit and loss, balance sheet, cash flow and ratios by year (up to twelve), and the last twelve quarters. Free: the latest three
    years of profit and loss."""
    r = _region(region)
    return ok(_statements(r, _symbol(symbol, r), basis, access(profile)))


def statement_sheets(v: dict) -> list[tuple[str, list[list], set[int] | None]]:
    """The statements as workbook sheets: one per section and one for the quarters, the unit in the first cell."""
    sheets = []
    for s in v["sections"]:
        rows = [[f"{s['title']} ({v['unit']}, {v['basis']})", *v["cols"]]] + [[r["label"], *r["values"]] for r in s["rows"]]
        sheets.append((s["title"], rows, None))
    if v.get("quarters"):
        q = v["quarters"]
        sheets.append(("Quarters", [[f"Quarters ({v['unit']}, {v['basis']})", *q["cols"]]] + [[r["label"], *r["values"]] for r in q["rows"]], None))
    return sheets


@router.get("/research/company/{region}/{symbol}/statements.{fmt}")
def statements_file(region: str, symbol: str, fmt: str, basis: str | None = None, profile=Depends(current_profile)):
    """Every statement as an Excel workbook (a sheet each) or one CSV (Pro)."""
    if fmt not in ("xlsx", "csv"):
        err(404, "not_found", "That download isn't offered.")
    _need_export(profile)
    r = _region(region)
    sym = _symbol(symbol, r)
    v = _statements(r, sym, basis, {"full": True, "export": True})
    sheets = statement_sheets(v)
    if not sheets:
        err(404, "no_figures", "No statements are stored for this company.")
    name = f"stratlab-{sym}-statements-{v['basis']}"
    if fmt == "xlsx":
        from . import xlsx_write
        return _file(xlsx_write.workbook(sheets), f"{name}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    body: list[list] = []
    for title, rows, _ in sheets:
        if body:
            body.append([])
        body.extend(rows)
    head, rest = body[0], body[1:]
    return _file(_csv([str(x) for x in head], rest), f"{name}.csv", "text/csv; charset=utf-8")


# ---------- shareholding ----------
HOLDER_ROWS = (("promoters", ("promoter",)), ("fiis", ("fii", "foreign inst")), ("diis", ("dii", "domestic inst")),
               ("government", ("government",)), ("public", ("public",)), ("others", ("others",)),
               ("shareholders", ("no. of shareholders", "number of shareholders")))
PLEDGE_NOTE = ("The share of promoters' holdings pledged isn't in the stored filings. Pledges and releases the promoters disclosed are "
               "under Deals and insider trades on this page.")
US_NOTE = ("US companies don't file a quarterly shareholding pattern by category, and StratLab doesn't store institutional or insider "
           "ownership shares for them. Holders above 5%, from their Schedule 13D and 13G filings, are under Holders above 5% on this page.")


def holding_quarters(t: dict | None) -> list[dict]:
    """The shareholding table as quarters, oldest first: {quarter, promoters, fiis, diis, government, public, others, shareholders,
    pledge} (percent of shares, the count of shareholders; None where the quarter has no figure; pledge is never stored)."""
    if not t or not t.get("cols"):
        return []
    cols = [str(c).strip() for c in t["cols"]]
    rows = {_label(k).lower(): list(v or []) for k, v in (t.get("rows") or {}).items()}
    out = []
    for i, c in enumerate(cols):
        q = {"quarter": c, "pledge": None}
        for key, starts in HOLDER_ROWS:
            vals = next((v for k, v in rows.items() if k.startswith(starts)), None)
            x = _num(vals[i]) if vals and i < len(vals) else None
            q[key] = (int(round(x)) if x is not None else None) if key == "shareholders" else _r(x, 2)
        out.append(q)
    return out[-QUARTERS_MAX:]


def shareholding_view(region: str, symbol: str, p: dict | None, see: dict) -> dict:
    if region == "US":
        return {"symbol": symbol, "region": region, "available": False, "note": US_NOTE, "quarters": [], "full": see["full"], "locked": None}
    qs = holding_quarters((p or {}).get("shareholding"))
    if not qs:
        return {"symbol": symbol, "region": region, "available": False, "quarters": [], "full": see["full"], "locked": None,
                "note": "No quarterly shareholding pattern is stored for this company yet."}
    keys = [k for k, _ in HOLDER_ROWS if k != "shareholders" and any(q[k] is not None for q in qs)]
    out = {"symbol": symbol, "region": region, "available": True, "keys": keys, "quarters": qs if see["full"] else qs[-1:],
           "stored": len(qs), "full": see["full"], "chart": see["full"] and len(qs) > 1, "pledge_note": PLEDGE_NOTE,
           "locked": None, "numbers_at": (p or {}).get("fetched_at")}
    if not see["full"] and len(qs) > 1:
        out["locked"] = lock(f"The last {len(qs)} quarters and the chart of who owns it are on the {plan_name(FULL)} plan.")
    return out


@router.get("/research/company/{region}/{symbol}/shareholding")
def shareholding(region: str, symbol: str, profile=Depends(current_profile)):
    """Promoters, FIIs, DIIs and the public by quarter, with the number of shareholders (India). Free: the latest quarter; Basic: twelve
    quarters and the chart. US companies: a note."""
    r = _region(region)
    sym = _symbol(symbol, r)
    see = access(profile)
    if r == "US":
        return ok(shareholding_view(r, sym, None, see))
    pages = pages_of(r, sym)
    return ok(shareholding_view(r, sym, next(iter(pages.values())), see))
