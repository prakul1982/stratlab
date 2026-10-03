"""The data audit: every company in a set run through the deep dive's numbers, checks and documents on the live server,
with each number compared against its source and every gap written down. Run from the admin page; nothing here uses
AI, so a full run costs no AI allowance. The aim is that nothing StratLab shows needs checking anywhere else."""
import threading
import time
from datetime import datetime, timezone

from . import db, sector_members, universes

KEY = "audit:last"
MAX_SYMBOLS = 300
PE_TOLERANCE = 0.25            # our P/E from market cap and trailing profit vs the page's stated P/E (minority
                               # shares and one-offs beyond this are explained on the page by a note)
TTM_TOLERANCE = 0.05           # trailing-year revenue vs the last four quarters added up
PRICE_TOLERANCE = 0.03         # prices from different sources, allowing for a day's move


def sets() -> list[dict]:
    """The sets an audit can run on: the ready-made groups, and every sector's main stocks together."""
    out = [{"id": p["id"], "name": p["name"], "count": len(p["symbols"])} for p in universes.PRESETS["IN"]]
    every = all_sector_stocks()
    out.append({"id": "sectors", "name": "Every sector's main stocks", "count": len(every)})
    return out


def all_sector_stocks() -> list[str]:
    seen: list[str] = []
    for p in universes.PRESETS["IN"]:
        seen += [s for s in p["symbols"] if s not in seen]
    for syms in sector_members.IN.values():
        seen += [s for s in syms if s not in seen]
    return seen


def symbols_for(set_id: str, custom: list[str] | None = None) -> list[str]:
    if custom:
        return list(dict.fromkeys(s.strip().upper() for s in custom if s.strip()))[:MAX_SYMBOLS]
    if set_id == "sectors":
        return all_sector_stocks()[:MAX_SYMBOLS]
    for p in universes.PRESETS["IN"]:
        if p["id"] == set_id:
            return list(p["symbols"])
    raise ValueError("Unknown set")


def _issue(level: str, area: str, detail: str) -> dict:
    return {"level": level, "area": area, "detail": detail}


def _off(a, b) -> float | None:
    """How far apart two numbers are, as a fraction of the second."""
    if a is None or b is None or not b:
        return None
    return abs(a - b) / abs(b)


def _last_ttm(table: dict | None, *prefixes: str):
    """The trailing-twelve-month value of a row, when the table has a TTM column."""
    if not table or not table.get("cols") or str(table["cols"][-1]).upper() != "TTM":
        return None
    for name, vals in (table.get("rows") or {}).items():
        if any(name.lower().startswith(p.lower()) for p in prefixes) and vals:
            return vals[-1] if len(vals) == len(table["cols"]) else None
    return None


FINANCIAL = {"lender", "insurer", "holding"}


def check_numbers(p: dict, nums: dict, snap: dict, group: str | None = None) -> list[dict]:
    out = []
    years = nums.get("years") or []
    if len(years) < 5:
        out.append(_issue("gap", "Numbers", f"Only {len(years)} years of annual results"))
    missing = [y["year"] for y in years if y.get("sales") is None or y.get("profit") is None]
    if missing:
        out.append(_issue("gap", "Numbers", f"Revenue or profit missing for {', '.join(missing[:4])}"))
    if not nums.get("bank") and group not in FINANCIAL:
        # a margin below -100% (a loss bigger than sales) or profit above sales (other income) happen; above 100% can't
        odd = [y["year"] for y in years if y.get("opm") is not None and y["opm"] > 100]
        if odd:
            out.append(_issue("mismatch", "Numbers", f"Operating margin above 100% in {', '.join(odd[:4])}"))
        if len(years) >= 3 and all(y.get("capex") is None for y in years[-3:]):
            out.append(_issue("gap", "Capex", "No capex estimate for the last three years"))
    ttm = _last_ttm(p.get("pl"), "Net Profit")
    if snap.get("pe") and snap.get("market_cap_cr") and ttm and ttm > 0:
        ours = snap["market_cap_cr"] / ttm
        off = _off(ours, snap["pe"])
        explained = any("P/E is based on" in n for n in nums.get("notes") or [])
        if off is not None and off > PE_TOLERANCE and not explained:
            out.append(_issue("mismatch", "Valuation", f"P/E {snap['pe']:.1f} on the company page, {ours:.1f} from market cap ÷ trailing profit"))
    ttm_sales = _last_ttm(p.get("pl"), "Sales", "Revenue")
    q = [x.get("sales") for x in (nums.get("quarters") or [])[-4:]]
    if ttm_sales and len(q) == 4 and all(v is not None for v in q):
        off = _off(sum(q), ttm_sales)
        if off is not None and off > TTM_TOLERANCE:
            out.append(_issue("mismatch", "Numbers", f"Trailing revenue {ttm_sales:,.0f} cr vs last four quarters {sum(q):,.0f} cr"))
    return out


def check_prices(snap: dict, trend: dict | None, exchange: float | None) -> list[dict]:
    out = []
    if not trend:
        out.append(_issue("gap", "Prices", "No daily prices, so no trend or stage"))
    ours = trend.get("price") if trend else None
    for label, other in (("the exchange's live quote", exchange), ("the company page", snap.get("price"))):
        off = _off(ours, other)
        if off is not None and off > PRICE_TOLERANCE:
            out.append(_issue("mismatch", "Prices", f"Last close {ours:,.2f} vs {other:,.2f} on {label}"))
            break
    return out


def check_view(view: dict) -> list[dict]:
    """Classification, valuation, checklist and documents, from the same view a user sees."""
    out = []
    cl = view.get("checklist") or {}
    ind = cl.get("industry") or {}
    if not ind.get("path"):
        out.append(_issue("gap", "Industry", f"No industry classification; treated as {ind.get('label') or 'a general business'}"))
    v = view.get("valuation") or {}
    if v.get("value") is None and "made a loss" not in (v.get("why") or ""):
        out.append(_issue("gap", "Valuation", f"No {v.get('short') or 'valuation'} figure"))
    na = [c["label"] for c in cl.get("checks", []) if c.get("state") == "na"]
    if len(na) >= 3:
        out.append(_issue("gap", "Checklist", f"{len(na)} checks couldn't be judged: {', '.join(na[:5])}"))
    if view.get("doc_note"):
        out.append(_issue("error", "Documents", view["doc_note"]))
    else:
        kinds = [d["kind"] for d in view.get("documents") or []]
        if "presentation" not in kinds:
            out.append(_issue("gap", "Documents", "No investor presentation filed in the last two years"))
        if "transcript" not in kinds:
            out.append(_issue("gap", "Documents", "No call transcript filed in the last two years"))
    return out


def check_documents(docs: list[dict], read) -> list[dict]:
    """Whether the newest presentation and the newest transcript can be turned into text (the step that decides
    whether the AI read and the report card can work). `read(candidates, problems)` returns the readable pairs."""
    out = []
    for kind, label in (("presentation", "presentation"), ("transcript", "call transcript")):
        cands = [d for d in docs if d["kind"] == kind]
        if not cands:
            continue
        problems: list[str] = []
        try:
            got = read(cands, problems)
        except Exception as e:
            got, problems = [], [str(e)]
        if not got:
            out.append(_issue("gap", "Documents", f"No readable {label}: {'; '.join(problems[:2]) or 'nothing came back'}"))
    return out


class Skipped(Exception):
    pass


class Breaker:
    """Stops calling a source after it has failed `limit` times in a row (the same refusal on every company is one
    finding, not two hundred); later calls raise Skipped."""

    def __init__(self, fn, limit: int = 3):
        self.fn, self.limit, self.fails = fn, limit, 0

    def __call__(self, *a):
        if self.fails >= self.limit:
            raise Skipped()
        try:
            out = self.fn(*a)
        except Exception:
            self.fails += 1
            raise
        self.fails = 0
        return out


def audit_company(sym: str, base_fn, view_fn, exchange_price=None, read=None) -> dict:
    """One company, start to finish. Each source failing shows up as an error row, never stops the run."""
    t0 = time.monotonic()
    issues: list[dict] = []
    name = sym
    try:
        base = base_fn(sym)
        view = view_fn(sym, base)
        name = view.get("name") or sym
        group = ((view.get("checklist") or {}).get("industry") or {}).get("group")
        issues += check_numbers(base["p"], view["numbers"], view.get("snapshot") or {}, group)
        ex = None
        if exchange_price:
            try:
                ex = exchange_price(sym)
            except Skipped:
                ex = None
            except Exception as e:
                issues.append(_issue("error", "Prices", f"Exchange price unavailable: {str(e)[:120]}"))
        issues += check_prices(view.get("snapshot") or {}, base.get("trend"), ex)
        issues += check_view(view)
        if read and view.get("documents"):
            issues += check_documents(view["documents"], lambda c, pr: read(c, pr, base["p"]))
    except Exception as e:
        d = getattr(e, "detail", None)          # an HTTP error from a data source carries its message here
        msg = d.get("message") if isinstance(d, dict) else d if isinstance(d, str) else str(e)
        issues.append(_issue("error", "Company page", (msg or e.__class__.__name__)[:200]))
    return {"symbol": sym, "name": name, "seconds": round(time.monotonic() - t0, 1), "issues": issues}


def summarise(rows: list[dict]) -> dict:
    by_area: dict[str, dict[str, int]] = {}
    for r in rows:
        for i in r["issues"]:
            a = by_area.setdefault(i["area"], {"mismatch": 0, "gap": 0, "error": 0})
            a[i["level"]] += 1
    clean = sum(1 for r in rows if not r["issues"])
    secs = [r["seconds"] for r in rows]
    return {"companies": len(rows), "clean": clean, "by_area": by_area,
            "mismatches": sum(a["mismatch"] for a in by_area.values()), "gaps": sum(a["gap"] for a in by_area.values()),
            "errors": sum(a["error"] for a in by_area.values()),
            "avg_seconds": round(sum(secs) / len(secs), 1) if secs else None,
            "slowest": sorted(({"symbol": r["symbol"], "seconds": r["seconds"]} for r in rows), key=lambda x: -x["seconds"])[:5]}


class Runner:
    """One audit at a time, in a background thread; progress is readable while it runs and the result is saved."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state: dict = {"running": False}
        self._stop = threading.Event()

    def cancel(self):
        """Stop after the company being checked now; what's done so far is kept and saved."""
        self._stop.set()

    def status(self) -> dict:
        with self.lock:
            if self.state.get("running") or self.state.get("rows") is not None:
                return self._public()
        try:
            import json
            saved = db.get_setting(KEY)
            return json.loads(saved) if saved else {"running": False}
        except Exception:
            return {"running": False}

    def _public(self) -> dict:
        s = dict(self.state)
        s["summary"] = summarise(s.get("rows") or [])
        return s

    def start(self, symbols: list[str], label: str, check, docs: bool) -> dict:
        with self.lock:
            if self.state.get("running"):
                raise RuntimeError("An audit is already running.")
            self.state = {"running": True, "label": label, "docs": docs, "total": len(symbols), "done": 0, "rows": [],
                          "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None, "cancelled": False}
            self._stop.clear()
        threading.Thread(target=self._run, args=(symbols, check), daemon=True).start()
        return self.status()

    def _run(self, symbols: list[str], check):
        import json
        for sym in symbols:
            if self._stop.is_set():
                with self.lock:
                    self.state["cancelled"] = True
                break
            row = check(sym)
            with self.lock:
                self.state["rows"].append(row)
                self.state["done"] += 1
        with self.lock:
            self.state["running"] = False
            self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
            result = self._public()
        try:
            db.set_setting(KEY, json.dumps(result))
        except Exception as e:
            print("could not save the audit:", e)
