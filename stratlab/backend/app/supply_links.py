"""The customer and supplier map (MVP): links between companies named in their own filings, kept in two tables
(supply_links, supply_docs in the app schema), read one document at a time by a nightly job that is off until Admin turns
it on, and shown on each company page.

Sources, read through the existing readers (no document is stored, only the link and its quote):
- India: the exchange's whole-market announcements, one call a day (filings.NSEFilings.market_orders): the order-win
  filings the classifier recognises. The filer is the supplier; the buyer it names is the customer. The 600-character
  summary is read first; the filing's PDF (Docs.text, the exchange's hosts only) only when the summary names no one.
- US: the latest annual report of S&P 500 companies, a few a night in turn (SEC.document, Business and Risk factors).

Rules first (supply_extract); the cheapest AI model (ai_providers.complete with bulk=True: Haiku only, free providers first)
only when the rules are unsure, within a monthly cap Admin sets. A link is kept only when its quote is in the document
word for word and holds the counterparty's name.

Counterparties are matched to listed companies with name_search: linked only on an exact symbol, a known short name or the
whole name, when exactly one company fits (or a name Admin confirmed before). A name that fits more than one company, or
only part of a name, goes to Admin's review queue and shows as plain text meanwhile; an unlisted buyer (a ministry, a
railway zone, a private firm) is kept as text, never linked. Facts as filed: nothing here scores a link or a company."""
from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from . import db, job_status, leader, name_search, run_marks
from . import supply_extract as X
from .admin import admin_profile
from .auth import current_profile
from .intel.net import SourceError
from .plans import FEATURE_PLAN, PLANS, allows, plan_of
from .responses import err, ok

router = APIRouter(tags=["research"])
admin_router = APIRouter(tags=["admin"])

IST = timezone(timedelta(hours=5, minutes=30))
SWITCH_KEY = "supply:on"                 # "1": the nightly job runs (off by default)
AI_CAP_KEY = "supply:ai_cap"             # AI calls a month the job may make (Admin sets it)
AI_USED_KEY = "supply:ai:"               # supply:ai:<YYYY-MM> = calls made that month
STATE_KEY = "supply:state"               # {"in_through": day, "us_cursor": n}
ALIAS_KEY = "supply:alias:"              # supply:alias:<region> = {name as filed: symbol Admin confirmed}
RUN_KEY = "supply:night"
RUN_AT, RUN_UNTIL = "01:40", "04:00"     # India time: after the evening reads and the filings index
MAX_RUN_S = 30 * 60
AI_CAP_DEFAULT = 200
IN_FIRST_DAYS = 7                        # days of order filings the first run reads
IN_MAX_DAYS = 10                         # days one run catches up at most
ORDER_CAP = 150                          # order filings read a night
US_CAP = 15                              # annual reports read a night
RUN_NOW_ORDERS, RUN_NOW_US = 20, 3
FREE_ROWS = 3                            # links a Free card shows; the rest are locked
SHOWN = ("auto", "confirmed", "text", "review")
LINKED = ("auto", "confirmed")
FEATURE, FEATURE_PRO = "supply", "supply_pro"
GOV = re.compile(r"\b(?:Ministry|Department|Railways?|Authority|Government|Municipal|Council|Commission|Navy|Army|Air Force|Defen[cs]e|"
                 r"Directorate|Nigam|Mandal|Board|Administration|Agency|Bureau|Metro Rail|Zone)\b")
NOTE = ("Links are read from the companies' own filings by fixed rules, and by an AI model only where the rules were unsure; each "
        "keeps the sentence it comes from, word for word, with a link to the filing. A company is linked only when the name fits "
        "exactly one listed company; other names are shown as filed. A link says what a filing said on its date, not that it "
        "still holds. Facts, not advice.")

_feeds: dict = {"filings": None, "sec": None, "docs": None}
_lock = threading.Lock()
_index_cache: dict[str, tuple[float, name_search.NameIndex]] = {}


def setup(filings_fn, sec_fn, docs_fn) -> None:
    """The sources (main.py's): the exchange's filings, the SEC client and the document reader."""
    _feeds.update(filings=filings_fn, sec=sec_fn, docs=docs_fn)


def _feed(name: str):
    fn = _feeds.get(name)
    return fn() if fn else None


def _sb():
    return db.sb()


def _json(key: str, default):
    try:
        return db.json_value(db.get_setting(key), default)
    except Exception:
        return default


# ---------- settings ----------
def enabled() -> bool:
    try:
        return db.get_setting(SWITCH_KEY) == "1"
    except Exception:
        return False


def switch(on: bool) -> None:
    if on:
        db.set_setting(SWITCH_KEY, "1")
    else:
        db.delete_setting(SWITCH_KEY)


def ai_cap() -> int:
    try:
        return max(0, int(db.get_setting(AI_CAP_KEY) or AI_CAP_DEFAULT))
    except (TypeError, ValueError):
        return AI_CAP_DEFAULT


def ai_used(month: str | None = None) -> int:
    month = month or datetime.now(IST).strftime("%Y-%m")
    try:
        return int(db.get_setting(AI_USED_KEY + month) or 0)
    except (TypeError, ValueError):
        return 0


def _ai_take() -> bool:
    """One AI call from this month's cap, or False when the cap is used up."""
    month = datetime.now(IST).strftime("%Y-%m")
    with _lock:
        used = ai_used(month)
        if used >= ai_cap():
            return False
        db.set_setting(AI_USED_KEY + month, str(used + 1))
    return True


def ask_ai(text: str, basis: str) -> list[dict]:
    """The AI's links for a document the rules were unsure of (the cheapest model, within the monthly cap); [] when the cap is
    used up or no model answers."""
    if not text.strip() or not _ai_take():
        return []
    from . import ai_providers
    try:
        reply = ai_providers.complete(X.AI_SYSTEM, text[:6000], max_tokens=600, kind="quick", want_json=True, bulk=True)
    except Exception as e:
        print("supply links: AI not read:", str(e)[:160])
        return []
    return X.from_ai(reply, text, basis)


# ---------- matching ----------
def universe(region: str) -> list[dict]:
    """[{symbol, name}] of every listed company of a market (the company pages' list)."""
    from . import stock_pages
    return [{"symbol": s, "name": (v or {}).get("name") or s} for s, v in stock_pages.companies(region).items()]


def aliases(region: str) -> dict[str, str]:
    """Names as filed that Admin confirmed: {name: symbol}."""
    got = _json(ALIAS_KEY + region, {})
    return got if isinstance(got, dict) else {}


def remember(region: str, name: str, symbol: str) -> None:
    got = aliases(region)
    got[X.plain(name)[:120]] = symbol
    db.set_setting(ALIAS_KEY + region, json.dumps(got))
    _index_cache.pop(region, None)


def _index(region: str) -> name_search.NameIndex:
    hit = _index_cache.get(region)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    learned = {k: [v] for k, v in aliases(region).items()}
    idx = name_search.NameIndex(universe(region), aliases={**name_search.ALIASES.get(region, {}), **learned})
    _index_cache[region] = (time.time(), idx)
    return idx


def match(name: str, region: str, self_symbol: str | None = None) -> dict | None:
    """How a counterparty's name meets the listed companies: {"state", "symbol", "candidates"}.
    auto: an exact symbol, a known short name or the whole name, with exactly one company; review: it fits more than one, or
    only part of a name (Admin picks); text: no listed company fits, or an unlisted public body. None: it is the filer itself."""
    hits = _index(region).search(name, 6)
    if not hits:
        return {"state": "text", "symbol": None, "candidates": None}
    best = hits[0][0]
    top = sorted({r["symbol"] for t, r in hits if t == best})
    if self_symbol and top == [self_symbol]:
        return None
    if best in (name_search.EXACT, name_search.NAMED) and len(top) == 1:
        return {"state": "auto", "symbol": top[0], "candidates": None}
    if GOV.search(name):
        return {"state": "text", "symbol": None, "candidates": None}
    cands = [{"symbol": r["symbol"], "name": r.get("name")} for _, r in hits if r["symbol"] != self_symbol][:5]
    return {"state": "review", "symbol": None, "candidates": cands} if cands else {"state": "text", "symbol": None, "candidates": None}


# ---------- storage ----------
def norm(name: str) -> str:
    return name_search.compact(name) or X.plain(name).lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_before(url: str) -> bool:
    try:
        return bool(_sb().table("supply_docs").select("id").eq("doc_url", url).limit(1).execute().data)
    except Exception:
        return False


def save_doc(url: str, region: str, symbol: str, kind: str, said_on: str | None, links: int, method: str | None, error: str | None = None):
    _sb().table("supply_docs").insert({"doc_url": url, "region": region, "symbol": symbol, "kind": kind, "said_on": said_on,
                                       "links": links, "method": method, "error": (error or None) and error[:200]}).execute()


def save_links(links: list[dict], region: str, stated_by: str, stated_name: str | None, doc_url: str, doc_title: str,
               said_on: str | None) -> int:
    """Store a document's links (each already checked against the document). The same counterparty named again in the same
    way takes the newer quote and date; a link Admin confirmed, kept as text or rejected stays so."""
    n = 0
    for x in links:
        m = match(x["counterparty"], region, stated_by)
        if m is None:
            continue
        cp = norm(x["counterparty"])
        row = {"region": region, "stated_by": stated_by, "stated_name": stated_name, "direction": x["direction"],
               "counterparty": X.plain(x["counterparty"])[:160], "cp_norm": cp, "cp_region": region, "basis": x["basis"],
               "share_pct": x.get("share_pct"), "amount": x.get("amount"), "quote": X.plain(x["quote"])[:900], "doc_url": doc_url,
               "doc_title": doc_title[:160], "said_on": said_on, "method": x.get("method") or "rule", "updated_at": _now()}
        old = (_sb().table("supply_links").select("id,state,said_on").eq("region", region).eq("stated_by", stated_by)
               .eq("direction", x["direction"]).eq("cp_norm", cp).eq("basis", x["basis"]).limit(1).execute().data)
        if old:
            if (old[0].get("said_on") or "") > (said_on or ""):
                continue                                 # an older filing read late: the newer quote stays
            if old[0]["state"] in ("confirmed", "text", "rejected"):
                row.pop("cp_region", None)
            else:
                row.update(state=m["state"], cp_symbol=m["symbol"], candidates=m["candidates"])
            _sb().table("supply_links").update(row).eq("id", old[0]["id"]).execute()
        else:
            _sb().table("supply_links").insert({**row, "state": m["state"], "cp_symbol": m["symbol"], "candidates": m["candidates"]}).execute()
        n += 1
    return n


# ---------- reading one document ----------
def read_order(item: dict, docs=None) -> dict:
    """One order-win filing: its links, by rules on the summary, then on the filing's PDF, then the AI."""
    head = f"{item.get('subject') or ''}. {item.get('text') or ''}"
    links, unsure = X.extract_order(head, item.get("company"))
    method, doc = "rule", head
    if unsure and docs is not None and item.get("url"):
        try:
            body = docs.text(item["url"])[:8000]
        except Exception:
            body = ""
        if body.strip():
            links, unsure = X.extract_order(body, item.get("company"))
            doc = body
    if unsure:
        links, method = ask_ai(doc, "order_win"), "ai"
    said = str(item.get("at") or "")[:10] or None
    n = save_links(links, "IN", item["symbol"], item.get("company"), item.get("url") or "", item.get("subject") or "Order filing", said)
    save_doc(item.get("url") or f"nse:{item['id']}", "IN", item["symbol"], "order", said, n, method if links else None)
    return {"links": n, "method": method}


def read_annual(sec, sym: str, name: str | None, d: dict) -> dict:
    """One annual report's Business and Risk factors parts: its links, by rules, then the AI on the sentences they were unsure of."""
    from .intel import sec as S
    url = d["url"]
    try:
        full = sec.document(url)
    finally:
        try:
            sec.cache.pop(("doc", url))              # the report's text is not kept in the process
        except Exception:
            pass
    text = "\n\n".join(p for p in (S.section(full, *S.SECTIONS["business"]), S.section(full, *S.SECTIONS["risks"])) if p) or full[:120000]
    del full
    links, unsure = X.extract_annual(text, name)
    method = "rule"
    if unsure:
        more = [x for x in ask_ai(" ".join(unsure), "concentration") if X.kept(x, text)]
        seen = {(x["direction"], x["counterparty"].lower()) for x in links}
        add = [x for x in more if (x["direction"], x["counterparty"].lower()) not in seen]
        if add:
            links, method = links + add, "rule+ai"
    said = d.get("at")
    n = save_links(links, "US", sym, name, url, d.get("title") or "Annual report", said)
    save_doc(url, "US", sym, "annual_report", said, n, method if links else None)
    return {"links": n, "method": method}


# ---------- the nightly job ----------
class Job:
    """Once a night when switched on: the order filings since the last run, then a few annual reports, one document at a time."""

    def __init__(self):
        self.status = job_status.Status("supplylinks", {"last_run": None, "last_error": None, "read": 0, "links": 0})
        self.lock = threading.Lock()
        self.running = False
        self.started: float | None = None
        self.clock = time.monotonic

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="supply-links").start()

    def _loop(self):
        time.sleep(900)
        while True:
            try:
                if leader.leading():
                    self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
            time.sleep(300)

    def tick(self, now: datetime) -> dict | None:
        if not enabled():
            return None
        local = now.astimezone(IST)
        if not (RUN_AT <= local.strftime("%H:%M") < RUN_UNTIL):
            return None
        run = run_marks.claim(RUN_KEY, local.date().isoformat())
        if run is None:
            return None
        out = self.run(ORDER_CAP, US_CAP, today=local.date())
        if out.get("ok"):
            run.done()
        return out

    def run(self, orders: int, annuals: int, today: date | None = None, max_s: float = MAX_RUN_S) -> dict:
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "error": "A run is already going."}
        self.running, self.started = True, time.time()
        began = self.clock()
        left = lambda: max_s - (self.clock() - began)  # noqa: E731
        out = {"ok": True, "read": 0, "links": 0, "ai": 0, "problems": []}
        try:
            today = today or datetime.now(IST).date()
            self.india(orders, today, left, out)
            self.us(annuals, left, out)
            self.status.update(last_run=_now(), read=out["read"], links=out["links"], problems=out["problems"][:5],
                               last_error=out["problems"][0] if out["problems"] and not out["read"] else None)
        except Exception as e:
            out.update(ok=False, error=str(e)[:200])
            self.status.update(last_error=str(e)[:200])
        finally:
            self.running, self.started = False, None
            self.lock.release()
        return out

    def india(self, cap: int, today: date, left, out: dict) -> None:
        feed = _feed("filings")
        if feed is None or not hasattr(feed, "market_orders"):
            return
        st = _json(STATE_KEY, {})
        try:
            day = date.fromisoformat(st["in_through"])
        except (KeyError, TypeError, ValueError):
            day = today - timedelta(days=IN_FIRST_DAYS)
        day = max(day, today - timedelta(days=IN_MAX_DAYS))
        docs, through, done = _feed("docs"), st.get("in_through"), 0
        while day <= today and done < cap and left() > 0:
            try:
                items = feed.market_orders(day)
            except SourceError as e:
                out["problems"].append(f"India {day}: {str(e)[:120]}")
                break
            full = True
            for it in items:
                if done >= cap or left() <= 0:
                    full = False
                    break
                if read_before(it.get("url") or f"nse:{it['id']}"):
                    continue
                try:
                    got = read_order(it, docs)
                    out["links"] += got["links"]
                    out["ai"] += got["method"] == "ai"
                except Exception as e:
                    out["problems"].append(f"{it.get('symbol')}: {str(e)[:120]}")
                done += 1
                out["read"] += 1
            if not full:
                break
            through = day.isoformat()
            day += timedelta(days=1)
        if through:
            st["in_through"] = min(through, (today - timedelta(days=1)).isoformat())    # today is read again tomorrow
            db.set_setting(STATE_KEY, json.dumps(st))

    def us(self, cap: int, left, out: dict) -> None:
        sec = _feed("sec")
        if sec is None or cap <= 0:
            return
        from . import universes
        from .intel import sec as S
        ciks, names = universes.sp500_ciks(), universes.sp500_names()
        syms = sorted(ciks)
        if not syms:
            return
        st = _json(STATE_KEY, {})
        at = int(st.get("us_cursor") or 0) % len(syms)
        tried = 0
        while tried < min(cap, len(syms)) and left() > 0:
            sym = syms[(at + tried) % len(syms)]
            tried += 1
            try:
                d = next((x for x in S.documents(sec.submissions(ciks[sym]), days=400) if x["kind"] == "annual_report"), None)
                if d and not read_before(d["url"]):
                    got = read_annual(sec, sym, names.get(sym), d)
                    out["links"] += got["links"]
                    out["read"] += 1
            except SourceError as e:
                out["problems"].append(f"{sym}: {str(e)[:120]}")
                if getattr(e, "busy", False):
                    break
            except Exception as e:
                out["problems"].append(f"{sym}: {str(e)[:120]}")
        st = _json(STATE_KEY, {})
        st["us_cursor"] = (at + tried) % len(syms)
        db.set_setting(STATE_KEY, json.dumps(st))


job = Job()


# ---------- what a page shows ----------
RELATION = {  # (whose document, direction) -> the company page's section
    ("own", "customer"): ("names_customers", "Names as customers"),
    ("other", "supplier"): ("named_supplier_by", "Named as a supplier by"),
    ("own", "supplier"): ("names_suppliers", "Names as suppliers"),
    ("other", "customer"): ("named_customer_by", "Named as a customer by"),
}
BASIS = {"order_win": "Order win", "concentration": "Share of sales", "customer_named": "Named customer", "supplier_named": "Named supplier"}


def _item(r: dict, own: bool) -> dict:
    group, words = RELATION[("own" if own else "other", r["direction"])]
    linked = r["state"] in LINKED and bool(r.get("cp_symbol"))
    who = ({"name": r["counterparty"], "symbol": r["cp_symbol"] if linked else None, "region": r.get("cp_region") or r["region"]} if own
           else {"name": r.get("stated_name") or r["stated_by"], "symbol": r["stated_by"], "region": r["region"]})
    basis = BASIS.get(r["basis"], r["basis"])
    if r["basis"] == "concentration" and r.get("share_pct") is not None:
        basis = f"{r['share_pct']:g}% of sales"
    return {"id": r["id"], "group": group, "relation": words, **who, "basis": basis, "amount": r.get("amount"), "quote": r["quote"],
            "said_on": r.get("said_on"), "doc_url": r["doc_url"], "doc_title": r.get("doc_title"), "method": r.get("method"),
            "as_filed": own and not linked}


def company_links(region: str, symbol: str) -> list[dict]:
    """Every link shown on a company's page, newest first: what its filings name, and where other companies' filings name it."""
    t = _sb().table("supply_links")
    own = [r for r in t.select("*").eq("region", region).eq("stated_by", symbol).execute().data or [] if r["state"] in SHOWN]
    named = [r for r in _sb().table("supply_links").select("*").eq("cp_region", region).eq("cp_symbol", symbol).execute().data or []
             if r["state"] in LINKED and r["stated_by"] != symbol]
    items = [_item(r, True) for r in own] + [_item(r, False) for r in named]
    items.sort(key=lambda i: (i.get("said_on") or "", i["name"]), reverse=True)
    return items


def _symbol(region: str, symbol: str) -> tuple[str, str]:
    region, symbol = str(region or "").upper(), str(symbol or "").strip().upper()
    if region not in ("IN", "US") or not re.fullmatch(r"[A-Z0-9&\-._]{1,20}", symbol):
        err(400, "bad_symbol", "That doesn't look like a market and ticker.")
    return region, symbol


@router.get("/research/links/{region}/{symbol}")
def links_for(region: str, symbol: str, profile=Depends(current_profile)):
    """A company's customers and suppliers named in filings. Free: the latest FREE_ROWS links; Basic: every link with its quote
    and source; Pro: the same plus the CSV and the theme view."""
    region, symbol = _symbol(region, symbol)
    plan = plan_of(profile)
    items = company_links(region, symbol)
    full = allows(plan, FEATURE)
    shown = items if full else items[:FREE_ROWS]
    return ok({"region": region, "symbol": symbol, "items": shown, "total": len(items), "locked": len(items) - len(shown),
               "full": full, "csv": allows(plan, FEATURE_PRO), "plan_for_all": PLANS[FEATURE_PLAN[FEATURE]]["name"],
               "plan_for_csv": PLANS[FEATURE_PLAN[FEATURE_PRO]]["name"], "note": NOTE})


@router.get("/research/links/{region}/{symbol}/csv")
def links_csv(region: str, symbol: str, profile=Depends(current_profile)):
    """The same links as a CSV (Pro)."""
    region, symbol = _symbol(region, symbol)
    if not allows(plan_of(profile), FEATURE_PRO):
        err(402, "upgrade_required", f"The links as a CSV are on the {PLANS[FEATURE_PLAN[FEATURE_PRO]]['name']} plan.")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Section", "Company", "Symbol", "Basis", "Amount", "Said on", "Quote", "Document", "Link"])
    for i in company_links(region, symbol):
        w.writerow([i["relation"], i["name"], i["symbol"] or "", i["basis"], i["amount"] or "", i["said_on"] or "",
                    i["quote"], i["doc_title"] or "", i["doc_url"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{symbol.lower()}-customers-suppliers.csv"'})


def theme_view(region: str, members: dict[str, str]) -> dict:
    """Links among a theme's members by value-chain layer ({ticker: layer}): layer-to-layer counts (supplier's layer to the
    customer's), the edges, and the counterparties outside the theme named most often."""
    rows = [r for r in (_sb().table("supply_links").select("*").eq("region", region).in_("stated_by", sorted(members)).execute().data or [])
            if r["state"] in SHOWN]
    edges, pairs, outside = [], {}, {}
    for r in rows:
        linked = r["state"] in LINKED and r.get("cp_symbol")
        sup, cus = (r["stated_by"], r.get("cp_symbol")) if r["direction"] == "customer" else (r.get("cp_symbol"), r["stated_by"])
        if linked and r["cp_symbol"] in members and r["cp_symbol"] != r["stated_by"]:
            key = (members[sup], members[cus])
            pairs[key] = pairs.get(key, 0) + 1
            edges.append({"supplier": sup, "customer": cus, "supplier_layer": members[sup], "customer_layer": members[cus],
                          "quote": r["quote"], "said_on": r.get("said_on"), "doc_url": r["doc_url"], "stated_by": r["stated_by"]})
        else:
            k = r["counterparty"] if not linked else r["cp_symbol"]
            o = outside.setdefault(k, {"name": r["counterparty"], "symbol": r["cp_symbol"] if linked else None, "links": 0, "members": set()})
            o["links"] += 1
            o["members"].add(r["stated_by"])
    top = sorted(outside.values(), key=lambda o: (-o["links"], o["name"]))[:10]
    return {"layers": [{"from": a, "to": b, "links": n} for (a, b), n in sorted(pairs.items(), key=lambda kv: -kv[1])],
            "edges": sorted(edges, key=lambda e: e.get("said_on") or "", reverse=True)[:100],
            "outside": [{**o, "members": sorted(o["members"])} for o in top], "members": len(members)}


@router.get("/research/links/theme")
def links_theme(region: str = Query("IN"), q: str = Query(..., min_length=2, max_length=80), profile=Depends(current_profile)):
    """Who sells to whom among a stored theme's members, by layer (Pro). Other plans get the count only."""
    region = region.upper()
    if region not in ("IN", "US"):
        err(400, "bad_region", "Pick India or the US.")
    from .intel import theme_library
    got = theme_library.stored(region, q)
    chain = ((got or {}).get("payload") or {}).get("value_chain") or []
    members = {str(c.get("ticker") or "").upper(): str(v.get("layer") or "") for v in chain if isinstance(v, dict)
               for c in v.get("companies") or [] if isinstance(c, dict) and c.get("ticker")}
    if not members:
        return ok({"available": False, "allowed": allows(plan_of(profile), FEATURE_PRO), "members": 0})
    view = theme_view(region, members)
    if not allows(plan_of(profile), FEATURE_PRO):
        return ok({"available": True, "allowed": False, "members": len(members), "links": len(view["edges"]),
                   "plan": PLANS[FEATURE_PLAN[FEATURE_PRO]]["name"]})
    return ok({"available": True, "allowed": True, **view})


# ---------- Admin ----------
@admin_router.get("/admin/supply-links")
def admin_status(_=Depends(admin_profile)):
    """The switch, the AI cap and this month's use, and the review queue (names that fit more than one company)."""
    queue = [r for r in _sb().table("supply_links").select("*").eq("state", "review").execute().data or []]
    queue.sort(key=lambda r: r.get("said_on") or "", reverse=True)
    return ok({"on": enabled(), "ai_cap": ai_cap(), "ai_used": ai_used(),
               "queue": [{"id": r["id"], "region": r["region"], "stated_by": r["stated_by"], "counterparty": r["counterparty"],
                          "direction": r["direction"], "quote": r["quote"], "said_on": r.get("said_on"), "doc_url": r["doc_url"],
                          "candidates": r.get("candidates") or []} for r in queue[:100]], "waiting": len(queue)})


@admin_router.post("/admin/supply-links/review/{link_id}")
def admin_review(link_id: str, body: dict, _=Depends(admin_profile)):
    """Settle a name in the queue: {"symbol": <one of its candidates>} links it (and remembers the name, so the same name is linked
    from now on, and the other queued rows with it); {"action": "text"} keeps it as filed, unlinked; {"action": "reject"} hides it."""
    rows = _sb().table("supply_links").select("*").eq("id", link_id).execute().data
    if not rows:
        err(404, "not_found", "That link isn't in the queue any more.")
    r = rows[0]
    action, symbol = str(body.get("action") or "").lower(), str(body.get("symbol") or "").upper()
    if symbol:
        if symbol not in {c.get("symbol") for c in r.get("candidates") or []}:
            err(400, "bad_symbol", "Pick one of the companies offered.")
        remember(r.get("cp_region") or r["region"], r["counterparty"], symbol)
        same = [x for x in _sb().table("supply_links").select("id,counterparty,stated_by").eq("state", "review")
                .eq("cp_norm", r["cp_norm"]).execute().data or [] if x["stated_by"] != symbol]
        for x in same:
            _sb().table("supply_links").update({"state": "confirmed", "cp_symbol": symbol, "candidates": None, "updated_at": _now()}).eq("id", x["id"]).execute()
        return ok({"ok": True, "linked": len(same), "message": f"Linked to {symbol}, here and in {max(0, len(same) - 1)} more."})
    if action not in ("text", "reject"):
        err(400, "bad_action", "Pick a company, keep the name as filed, or reject the link.")
    _sb().table("supply_links").update({"state": "text" if action == "text" else "rejected", "cp_symbol": None, "candidates": None,
                                        "updated_at": _now()}).eq("id", link_id).execute()
    return ok({"ok": True, "message": "Kept as filed, unlinked." if action == "text" else "Rejected: it is hidden everywhere."})


@admin_router.post("/admin/supply-links/on")
def admin_on(_=Depends(admin_profile)):
    switch(True)
    return ok({"ok": True, "message": "The customer and supplier map is on: it reads filings each night at 1:40 AM IST."})


@admin_router.post("/admin/supply-links/off")
def admin_off(_=Depends(admin_profile)):
    switch(False)
    return ok({"ok": True, "message": "The customer and supplier map is off: nothing more is read. Links already found stay."})


@admin_router.post("/admin/supply-links/ai-cap")
def admin_ai_cap(body: dict, _=Depends(admin_profile)):
    try:
        n = int(body.get("calls"))
    except (TypeError, ValueError):
        err(400, "bad_cap", "Give the AI calls a month as a whole number.")
    if not 0 <= n <= 5000:
        err(400, "bad_cap", "The cap is between 0 and 5,000 calls a month.")
    db.set_setting(AI_CAP_KEY, str(n))
    return ok({"ok": True, "message": f"At most {n:,} AI calls a month."})


@admin_router.post("/admin/supply-links/run")
def admin_run(_=Depends(admin_profile)):
    """A small run now, in the background (a few filings and one or two annual reports)."""
    if job.running:
        return ok({"ok": True, "message": "A run is already going."})
    threading.Thread(target=lambda: job.run(RUN_NOW_ORDERS, RUN_NOW_US, max_s=10 * 60), daemon=True, name="supply-links-now").start()
    return ok({"ok": True, "message": f"Started: up to {RUN_NOW_ORDERS} order filings and {RUN_NOW_US} annual reports."})


def admin_row() -> dict:
    """The job's row on Admin -> Data and jobs (admin_jobs.rows)."""
    from .admin_jobs import _row
    st = job_status.kept("supplylinks", dict(job.status))
    on = enabled()
    log = []
    if st.get("last_run"):
        log.append(f"Last run: {st.get('read', 0)} documents read, {st.get('links', 0)} links kept.")
    log.append(f"AI calls this month: {ai_used():,} of {ai_cap():,}.")
    try:
        waiting = len(_sb().table("supply_links").select("id").eq("state", "review").execute().data or [])
        log.append(f"Names waiting for review: {waiting:,} (Admin -> Data -> Customer and supplier names).")
    except Exception:
        pass
    log += [str(p) for p in (st.get("problems") or [])[:3]]
    schedule = (f"Each night at 1:40 AM IST: up to {ORDER_CAP} Indian order filings and {US_CAP} US annual reports, one at a time, "
                f"for at most {MAX_RUN_S // 60} minutes") if on else "Off"
    run = [{"label": "Run now", "path": "/admin/supply-links/run"},
           {"label": "Turn off", "path": "/admin/supply-links/off"} if on else {"label": "Turn on", "path": "/admin/supply-links/on"}]
    return _row("supply-links", "Customer and supplier map", schedule, st.get("last_run"), st.get("last_error"), log, run,
                running=job.running, note=None if on else "Off: switch it on to read order filings and annual reports each night.",
                started=job.started)
