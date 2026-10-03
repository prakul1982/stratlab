"""The data audit: every company in a set run through the deep dive's numbers, checks and documents on the live server,
with each number compared against its source and every gap written down. Run from the admin page; nothing here uses
AI, so a full run costs no AI allowance. The aim is that nothing StratLab shows needs checking anywhere else."""
import threading
import time
from datetime import datetime, timedelta, timezone

from . import db, sector_members, universes

KEY = "audit:last"
MAX_SYMBOLS = 600
PE_TOLERANCE = 0.25            # our P/E from market cap and trailing profit vs the page's stated P/E (minority
                               # shares and one-offs beyond this are explained on the page by a note)
TTM_TOLERANCE = 0.05           # trailing-year revenue vs the last four quarters added up
TTM_ROUNDING = 2               # ...but tiny companies' quarters are shown in whole crore, so 2 cr apart is rounding
PRICE_TOLERANCE = 0.03         # prices from different sources, allowing for a day's move


# whole NSE indices, read from the exchange's own constituent lists when the audit starts
INDEX_SETS = {"nifty500": ("NIFTY 500", "NIFTY 500", 500), "niftynext50": ("NIFTY NEXT 50", "NIFTY Next 50", 50),
              "midcap150": ("NIFTY MIDCAP 150", "NIFTY Midcap 150", 150), "smallcap250": ("NIFTY SMALLCAP 250", "NIFTY Smallcap 250", 250)}


def sets(region: str = "IN") -> list[dict]:
    """The sets an audit can run on: the ready-made groups, every sector's main stocks, and (India) whole NSE indices."""
    if region == "US":
        out = [{"id": p["id"], "name": p["name"], "count": len(p["symbols"])} for p in universes.PRESETS["US"]]
        return out + [{"id": "sectors", "name": "Every sector's main US stocks", "count": len(all_sector_stocks("US"))}]
    out = [{"id": p["id"], "name": p["name"], "count": len(p["symbols"])} for p in universes.PRESETS["IN"]]
    every = all_sector_stocks()
    out.append({"id": "sectors", "name": "Every sector's main stocks", "count": len(every)})
    out += [{"id": k, "name": f"{name} (the exchange's list)", "count": n} for k, (_, name, n) in INDEX_SETS.items()]
    return out


def all_sector_stocks(region: str = "IN") -> list[str]:
    seen: list[str] = []
    for p in universes.PRESETS[region]:
        seen += [s for s in p["symbols"] if s not in seen]
    for syms in getattr(sector_members, region).values():
        seen += [s for s in syms if s not in seen]
    return seen


def symbols_for(set_id: str, custom: list[str] | None = None, members=None, region: str = "IN") -> list[str]:
    """`members(index)` gives an NSE index's stocks (the exchange feed), for the whole-index sets."""
    if set_id in INDEX_SETS and not custom and region == "IN":
        if members is None:
            raise ValueError("Index lists aren't available here.")
        return members(INDEX_SETS[set_id][0])[:MAX_SYMBOLS]
    if custom:
        return list(dict.fromkeys(s.strip().upper() for s in custom if s.strip()))[:MAX_SYMBOLS]
    if set_id == "sectors":
        return all_sector_stocks(region)[:MAX_SYMBOLS]
    for p in universes.PRESETS[region]:
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
        # a margin above 100% means costs came out negative (provisions written back): the margin is the company
        # page's own figure, shown as filed, so it is worth a look but isn't our reading going wrong
        odd = [y["year"] for y in years if y.get("opm") is not None and y["opm"] > 100]
        if odd:
            out.append(_issue("gap", "Numbers", f"The company page shows an operating margin above 100% in {', '.join(odd[:4])} (costs written back)"))
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
        if off is not None and off > TTM_TOLERANCE and abs(sum(q) - ttm_sales) > TTM_ROUNDING:
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
    """Classification, valuation, checklist and documents, from the same view a user sees. US companies are checked
    for their annual and quarterly reports; Indian ones for presentations and call transcripts."""
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
    elif view.get("region") == "US":
        kinds = [d["kind"] for d in view.get("documents") or []]
        if "annual_report" not in kinds:
            out.append(_issue("gap", "Documents", "No annual report (10-K) filed in the last two years"))
        if "quarterly_report" not in kinds:
            out.append(_issue("gap", "Documents", "No quarterly report (10-Q) filed in the last two years"))
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


NOT_COVERED = ("has no annual results filed", "isn't a company that files with the SEC")


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
        msg = (msg or e.__class__.__name__)[:200]
        # shells, SPACs, trusts and funds file no annual results: nothing for the app to show, not something broken
        uncovered = any(x in msg for x in NOT_COVERED)
        issues.append(_issue("gap" if uncovered else "error", "Company page", msg))
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

    def start(self, symbols: list[str], label: str, check, docs: bool, region: str = "IN") -> dict:
        with self.lock:
            if self.state.get("running"):
                raise RuntimeError("An audit is already running.")
            self.state = {"running": True, "label": label, "docs": docs, "region": region, "total": len(symbols), "done": 0, "rows": [],
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
            try:
                row = check(sym)
            except Exception as e:                # one company failing never stops the run, or leaves it "running"
                row = {"symbol": sym, "name": sym, "seconds": 0, "issues": [_issue("error", "Audit", str(e)[:200] or e.__class__.__name__)]}
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


MARKET = "audit:market"        # settings keys: the switch and list state, the list itself, and results in shards
RETRY_HOURS = 6                # a check that failed because a source was down is tried again after this long
MAX_TRIES = 3                  # ...this many times in all, then it is left as it is
TRANSIENT_AREAS = {"Company page", "Prices", "Audit"}      # errors from a source being unreachable, not from the data
NEW_DAYS = 30                  # listed (or first seen on the list) within this many days: checked
LIST_EVERY = 86400             # re-read the exchange's list of companies once a day


def _shard(sym: str, key: str = MARKET) -> str:
    if sym.startswith("BSE:"):                  # thousands of BSE-only companies: ten shards of their own
        return f"{key}:rows:bse{sym[-1]}"
    c = sym[:1].upper()
    return f"{key}:rows:{c if c.isalpha() else '0'}"


def _transient(row: dict) -> bool:
    """The check failed because a source couldn't be reached (busy, down, blocked), not because the data was wrong."""
    return any(i.get("level") == "error" and i.get("area") in TRANSIENT_AREAS for i in row.get("issues") or [])


class MarketAudit:
    """New listings, checked in the background as they appear. The exchange's list is read once a day; a company that
    listed (or first showed up on the list) in the last NEW_DAYS days is checked once, a delisted company is dropped,
    and a check that failed only because a source was down is tried again. The thousands of companies already listed
    are not re-run: going through a whole market takes more than a day and its storage. Each result is saved as it
    finishes, so a restart carries on where it stopped. Gives way while a hand-started audit runs."""

    def __init__(self, list_fn, check_fn, busy_fn=lambda: False, pause: float = 3.0, key: str = MARKET):
        self.list_fn, self.check_fn, self.busy_fn, self.pause, self.key = list_fn, check_fn, busy_fn, pause, key
        self.lock = threading.Lock()
        self.loaded = False
        self.state: dict = {"enabled": False, "list_at": None, "list_tried_at": None, "list_error": None}
        self.listing: dict[str, dict] = {}
        self.rows: dict[str, dict] = {}
        self.current: str | None = None
        self.secs: list[float] = []

    # storage
    def _load(self):
        if self.loaded:
            return
        import json
        try:
            self.state.update(json.loads(db.get_setting(self.key) or "{}"))
            self.listing = json.loads(db.get_setting(f"{self.key}:list") or "{}")
            for c in [*"ABCDEFGHIJKLMNOPQRSTUVWXYZ0", *(f"bse{d}" for d in "0123456789")]:
                self.rows.update(json.loads(db.get_setting(f"{self.key}:rows:{c}") or "{}"))
        except Exception as e:
            print("could not load the market audit:", e)
        self.loaded = True

    def _save(self, *what: str):
        import json
        try:
            for w in what:
                if w == "state":
                    db.set_setting(self.key, json.dumps(self.state))
                elif w == "list":
                    db.set_setting(f"{self.key}:list", json.dumps(self.listing))
                else:                                   # a symbol: save its shard
                    key = _shard(w, self.key)
                    db.set_setting(key, json.dumps({s: r for s, r in self.rows.items() if _shard(s, self.key) == key}))
        except Exception as e:
            print("could not save the market audit:", e)

    # control
    def set_enabled(self, on: bool):
        with self.lock:
            self._load()
            self.state["enabled"] = bool(on)
            self._save("state")

    def refresh_list(self, force: bool = False) -> bool:
        """Read the exchange's list when it is a day old (or now, when forced). Keeps the last good list on failure."""
        with self.lock:
            self._load()
            last = self.state.get("list_tried_at")
            if not force and last and time.time() - datetime.fromisoformat(last).timestamp() < LIST_EVERY:
                return False
            self.state["list_tried_at"] = datetime.now(timezone.utc).isoformat()
        try:
            got = self.list_fn()
        except Exception as e:
            with self.lock:
                self.state["list_error"] = str(e)[:200]
                self._save("state")
            return False
        today = datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            first = not self.listing         # the first read: nothing in it is new, it's just the start
            fresh = {c["symbol"]: {"name": c.get("name") or c["symbol"], "listed": c.get("listed"),
                                   "seen": (self.listing.get(c["symbol"]) or {}).get("seen") or (None if first or c.get("old") else today)}
                     for c in got}
            gone = [s for s in self.rows if s not in fresh]
            for s in gone:
                self.rows.pop(s)
            self.listing = fresh
            self.state.update(list_at=self.state["list_tried_at"], list_error=None)
            self._save("state", "list", *{_shard(s, self.key): s for s in gone}.values())
        return True

    def _is_new(self, sym: str, today) -> bool:
        info = self.listing.get(sym) or {}
        d = info.get("listed") or info.get("seen")
        try:
            return d is not None and (today - datetime.fromisoformat(d).date()).days <= NEW_DAYS
        except ValueError:
            return False

    def queue(self) -> list[str]:
        """Companies due a check, in order: new listings not yet checked (newest first), then failed checks to retry."""
        now = datetime.now(timezone.utc)
        today = now.date()
        retry_cut = (now - timedelta(hours=RETRY_HOURS)).isoformat()
        new, retry = [], []
        for sym, info in self.listing.items():
            row = self.rows.get(sym) or {}
            at = row.get("at")
            if not at:
                if self._is_new(sym, today):
                    new.append((info.get("listed") or info.get("seen") or "", sym))
            elif _transient(row) and (row.get("tries") or 1) < MAX_TRIES and at < retry_cut:
                retry.append((at, sym))           # a source was down or busy: try again later
        return [s for _, s in sorted(new, reverse=True)] + [s for _, s in sorted(retry)]

    # work
    def step(self) -> str | None:
        """Check one due company; returns its symbol, or None when there's nothing to do right now."""
        with self.lock:
            self._load()
            if not self.state.get("enabled"):
                return None
        if self.busy_fn():
            return None
        self.refresh_list()
        with self.lock:
            due = self.queue()
            if not due:
                return None
            sym = self.current = due[0]
        try:
            row = self.check_fn(sym)
        finally:
            with self.lock:
                self.current = None
        row["at"] = datetime.now(timezone.utc).isoformat()
        with self.lock:
            prev = self.rows.get(sym) or {}
            row["tries"] = (prev.get("tries") or 1) + 1 if _transient(prev) and _transient(row) else 1
            if sym in self.listing:
                self.rows[sym] = row
                self.secs = (self.secs + [row.get("seconds") or 0])[-50:]
                self._save(sym)
        return sym

    def loop(self):
        while True:
            try:
                did = self.step()
            except Exception as e:
                print("market audit step failed:", e)
                did = None
            time.sleep(self.pause if did else 60)

    def checked_since(self, since_iso: str) -> list[dict]:
        """Every company checked since a time, with or without problems."""
        with self.lock:
            self._load()
            return [r for r in self.rows.values() if (r.get("at") or "") >= since_iso]

    def status(self) -> dict:
        with self.lock:
            self._load()
            due = self.queue()
            today = datetime.now(timezone.utc).date()
            rows = list(self.rows.values())
            new = sorted(({"symbol": s, "name": i.get("name"), "listed": i.get("listed"),
                           "checked": bool((self.rows.get(s) or {}).get("at"))}
                          for s, i in self.listing.items() if self._is_new(s, today)), key=lambda x: x["listed"] or "", reverse=True)
            avg = (sum(self.secs) / len(self.secs) + self.pause) if self.secs else None
            return {**{k: self.state.get(k) for k in ("enabled", "list_at", "list_tried_at", "list_error")},
                    "listed": len(self.listing), "checked": len(self.rows), "due": len(due), "current": self.current,
                    "eta_hours": round(len(due) * avg / 3600, 1) if avg else None, "new_listings": new[:30],
                    "summary": summarise(rows), "rows": [r for r in rows if r.get("issues")]}
