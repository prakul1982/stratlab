"""/research/theme-dive: the theme page's deep dive (THEME-1), and the checks the theme map goes through before it is served.

- `checked(region, theme, map)`: the map with only the companies whose own description shows their work, and its tailwinds and
  risks beside the dated headline that supports them (theme_check.py). Kept for a day with the map.
- GET /theme-dive: the tables and sections worked out from the stored company facts (theme_data.py), kept in memory for half an hour.
- GET /theme-dive/prices: returns, breadth and relative strength from the companies' daily closes (theme_prices.py), read at a
  gentle pace and kept until the market's next close.
- GET /theme-dive/news: the latest dated headlines and exchange filings for the theme's companies.

No job of its own: everything is read when a page asks, through the caches the app already keeps. Memory: see DIVE_CACHE, PRICE_CACHE,
EVIDENCE_CACHE and VERDICTS below."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from .. import computed, db
from ..ai_providers import AIError
from ..auth import current_profile
from ..guard import Window
from ..responses import err
from . import ai as A
from . import grounding, theme_base, theme_check, theme_data, theme_library, theme_prices
from . import sector_metrics
from .net import SourceError, TTLCache
from .news import aggregator_url, company_headline, plain_headline, publisher_url

router = APIRouter(tags=["research"])

DIVE_TTL = 30 * 60
DIVE_CACHE = TTLCache(max_items=24, max_bytes=3 * 1024 * 1024)            # a dive is about 60 KB of numbers
PRICE_CACHE = TTLCache(max_items=300, max_bytes=3 * 1024 * 1024)          # one company's reduced closes: 160 weekly closes and a few numbers (about 6 KB)
EVIDENCE_CACHE = TTLCache(max_items=600, max_bytes=1500 * 1024)           # one company's description, 700 characters
NEWS_CACHE = TTLCache(max_items=24, max_bytes=1024 * 1024)
EVIDENCE_DAYS = 30                                                        # a description is read again after this long
NO_DESCRIPTION_DAYS = 3                                                   # ...a company with none, after this long
VERDICTS: dict = {}                                                       # placement answers (a few hundred bytes each), cleared past VERDICT_KEEP
VERDICT_KEEP = 3000
DESCRIBE_READS = 6                                                        # descriptions read from the companies' own pages a request
PLACE_READS = 60                                                          # R28: descriptions read for a theme's companies to place, in its check, at most
PRICE_READS_PER_MINUTE = 20                                               # companies' candles read from the sources a minute, across every theme
PRICE_BUDGET = 45.0                                                       # seconds a request may spend reading candles
price_reads = Window()
_price_gate = threading.BoundedSemaphore(2)
_ai_gate = threading.Lock()
HISTORY_KEEP = 120                                                        # a theme's kept points: about two years of weekly ones


def _routes():
    from . import routes
    return routes


# ---------- the placement and claims checks ----------
FILING_LINES = 8                                                          # lines of a company's own filings added to its description
FILING_CHARS = 480


def own_filings(region: str, sym: str) -> str:
    """"From its own filings: …": the words the app already keeps from the company's own filings, for a description that doesn't name a
    business line it has (THEMES item 6: Tata Motors' profile has no word of its electric cars; its monthly sales filings do). The quoted
    lines of its business updates as read (biz_updates, India), then the exchange's or the SEC's titles of its latest filings on its stored
    page. Nothing is read from a source here; "" when nothing is kept."""
    lines: list[str] = []
    if region == "IN":
        try:
            from .. import biz_updates
            for m in biz_updates.series(biz_updates.stored(sym))[:FILING_LINES]:
                q = ((m.get("latest") or {}).get("source") or {}).get("quote") or " ".join(x for x in (m.get("segment"), m.get("metric")) if x)
                lines.append(str(q))
        except Exception as e:
            print("theme: business updates not read:", sym, type(e).__name__, str(e)[:100])
    try:
        R = _routes()
        f = (R.public_facts(region, sym) if callable(R.public_facts) else None) or {}
        lines += [str(x.get("name") or x.get("title") or "") for x in (f.get("filings") or [])[:FILING_LINES] if isinstance(x, dict)]
    except Exception as e:
        print("theme: filings not read:", sym, type(e).__name__, str(e)[:100])
    seen, keep = set(), []
    for x in lines:
        x = " ".join(x.split()).rstrip(" .;")
        if len(x.split()) >= 3 and x.lower() not in seen:
            seen.add(x.lower())
            keep.append(x)
    return ("From its own filings: " + ". ".join(keep[:FILING_LINES]) + ".")[:FILING_CHARS] if keep else ""


def evidence_reader(region: str, names: dict):
    """A function symbol-list -> ({symbol: {about, industry}}, pending) that reads each company's own description once (the company
    page's profile), keeps it for EVIDENCE_DAYS, and reads no more than the request's budget allows."""
    R = _routes()

    def read(sym):
        key = f"theme:evidence:{region}:{sym}"
        hit = EVIDENCE_CACHE.get(key)
        if hit is None:
            try:
                got = db.json_value(db.get_setting(key), {})
            except Exception:
                got = {}
            if got.get("at"):
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(got["at"])).days
                if age < (EVIDENCE_DAYS if got.get("about") else NO_DESCRIPTION_DAYS):
                    hit = got
        if hit is None:
            about, industry = "", ""
            if region == "IN":
                p = R.hub.screener.company(sym)
                about, industry = p.get("about") or "", " > ".join(p.get("industry_path") or [])
            if not about:
                w = R.hub.wiki.company(names.get(sym) or sym)
                about = (w or {}).get("extract") or ""
            hit = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "about": theme_check.clean_description(about), "industry": industry}
            try:
                db.set_setting(key, json.dumps(hit, ensure_ascii=False))
            except Exception as e:
                print("theme: description not kept:", sym, str(e)[:100])
        EVIDENCE_CACHE.set(key, hit, 6 * 3600)
        filed = own_filings(region, sym)
        if not hit.get("about") and not filed:
            return None
        return {**hit, "about": " ".join(x for x in (hit.get("about"), filed) if x)}

    def evidence_of(symbols):
        return theme_check.gather_evidence(symbols, read)
    return evidence_of


def _ask(system: str, text: str) -> dict:
    return A.ask(system, text, _routes()._ai)


def _headlines(region: str):
    R = _routes()

    def search(q):
        out = []
        for n in R.hub.news.search(q, region, limit=12):
            if plain_headline(n.get("headline")):
                url = publisher_url(n.get("url"))
                out.append({"headline": n["headline"], "at": n.get("at"), "source": n.get("source") or "", "url": "" if aggregator_url(url) else (url or "")})
        return out
    return search


def _map_names(m: dict) -> dict:
    return {c["ticker"]: c.get("name") or c["ticker"] for grp in (m.get("value_chain") or []) + (m.get("sub_themes") or []) for c in grp.get("companies") or []}


def _plain_claims(m: dict) -> dict:
    """Tailwinds and risks as {"text", "status": "general", "source": None} when they couldn't be checked."""
    m = dict(m)
    for k in ("tailwinds", "risks"):
        m[k] = [{"text": c["text"], "status": "general", "source": None} for c in m.get(k) or [] if isinstance(c, dict)]
    return m


PENDING_GIVE_UP = 90.0                                                    # seconds a map may wait on companies still being checked
_pending_since: dict = {}                                                 # (market, theme, map time) -> when it was first served unchecked


_sic = {"at": 0.0, "stored": None}


def _sic_stored() -> dict:
    if _sic["stored"] is None or time.time() - _sic["at"] > 3600:
        try:
            _sic["stored"] = db.json_value(db.get_setting(theme_base.SIC_KEY), {})
        except Exception:
            _sic["stored"] = {}
        _sic["at"] = time.time()
    return _sic["stored"]


def _sic_read(sym: str) -> list[str]:
    """A US company's SIC path from its SEC record (the submissions JSON its page reads), [] when it has none."""
    from .. import main
    from .net import NotFound
    from .sec import sic_path
    try:
        subs = main.sec_feed.submissions(main.sec_feed.cik(sym))
    except (NotFound, KeyError):
        return []
    return sic_path(str(subs.get("sic") or ""), subs.get("sicDescription"))


def fill_us_industries(read=None) -> int:
    """A few more US companies' SIC codes read and kept (theme_base.fill_sic); how many are still without one."""
    rows = _routes().index_rows("US")
    stored, n = theme_base.fill_sic(rows, _sic_stored(), read or _sic_read)
    if n:
        try:
            db.set_setting(theme_base.SIC_KEY, json.dumps(stored, separators=(",", ":")))
        except Exception as e:
            print("theme: SEC codes not kept:", str(e)[:100])
        _sic.update(stored=stored, at=time.time())
    return theme_base.unclassified(theme_base.with_sic(rows, stored))


def _rows(region: str) -> list[dict]:
    """The market's index rows, a US company's industry filled from its SEC record where the index has none."""
    rows = _routes().index_rows(region)
    return theme_base.with_sic(rows, _sic_stored()) if region == "US" else rows


def _industries(region: str, theme: str) -> dict:
    """The theme's official industries (theme_base.industries_for), on the market's stored index."""
    return theme_base.industries_for(region, theme, _rows(region), _ask, db.get_setting, db.set_setting)


# ---------- the AI parts, worked out behind the page (LIVE3-001) ----------
# Live, every theme failed at 30 s with "Can't reach the StratLab server": GET /research/sector held the request open while the AI wrote the
# map (up to 60 s), then checked each company and the claims, and a connection on the way closed it at 30 s (Railway logged 499, "client has
# closed the request"). The official-industry base needs no AI, so a request now answers with it at once and the AI parts are written in a
# background thread, one per theme; the page asks again until they are in.
THEME_WAIT = 2.5            # seconds a request waits for an AI part that is quick (a cached answer); a slower one fills in after
FAIL_WAIT = 60.0            # a failed AI part is tried again by a request after this long, not on every poll
JOBS_MAX = 6                # AI parts being written at once, across every theme; past this a request serves what it has
_jobs: dict = {}            # (part, market, theme, ...) -> {"state": "running" | "done" | "failed", "message", "code", "at", "done": Event}
_jobs_lock = threading.Lock()


def _job_run(j: dict, work) -> None:
    from fastapi import HTTPException
    try:
        work()
        j["state"] = "done"
    except HTTPException as e:                    # the person's daily AI limit, every provider busy, an answer that failed
        d = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        j.update(state="failed", message=str(d.get("message") or ""), code=str(d.get("code") or ""))
    except Exception as e:
        print("theme: AI part failed:", type(e).__name__, str(e)[:160])
        j.update(state="failed", message="The AI couldn't write this part just now.", code="ai_failed")
    finally:
        j["at"] = time.time()
        j["done"].set()


def later(key: tuple, work, wait: float | None = None) -> dict:
    """Run `work` once for `key` in a background thread (a second request for the same key joins the one running) and wait at most
    THEME_WAIT for it; returns the job ({"state", "message", "code"}). A finished job is started again when asked (the caller asks only
    when what it stores isn't there); a failed one only FAIL_WAIT after it failed."""
    now = time.time()
    with _jobs_lock:
        j = _jobs.get(key)
        again = j is None or j["state"] == "done" or (j["state"] == "failed" and now - j["at"] >= FAIL_WAIT)
        if again and sum(1 for x in _jobs.values() if x["state"] == "running") >= JOBS_MAX:
            return j or {"state": "running", "message": "", "code": "", "at": now, "done": threading.Event()}
        if again:
            j = {"state": "running", "message": "", "code": "", "at": now, "done": threading.Event()}
            _jobs[key] = j
            threading.Thread(target=_job_run, args=(j, work), daemon=True, name="theme-ai").start()
        if len(_jobs) > VERDICT_KEEP:
            for k in [k for k, x in _jobs.items() if x["state"] != "running"]:
                del _jobs[k]
    j["done"].wait(THEME_WAIT if wait is None else wait)
    return j


def job_of(key: tuple) -> dict | None:
    return _jobs.get(key)


def ai_state(region: str, theme: str, m: dict) -> dict | None:
    """What the page says about the AI parts: {"state": "working"} while the map or its checks are being written, {"state": "failed",
    "message"} when the map couldn't be written (the base is shown without it), None when everything is in."""
    t = theme.lower()
    mj = job_of(("map", region, t))
    cj = job_of(("check",) + check_key(region, theme, m))
    if (mj and mj["state"] == "running") or (cj and cj["state"] == "running"):
        return {"state": "working", "message": ""}
    if not float(m.get("generated_at") or 0):
        if mj and mj["state"] == "failed":
            return {"state": "failed", "message": mj["message"], "code": mj.get("code") or ""}
        return {"state": "working", "message": ""}         # not started yet (JOBS_MAX were running): the page's next ask starts it
    return None


def check_key(region: str, theme: str, m: dict) -> tuple:
    """A checked map's cache key: the market, the theme, the AI map's time and the membership rules' version (theme_base.RULES), so a check
    kept from before a deploy that changed the rules is worked out again, never served with the old companies (R18)."""
    return (region, theme.lower(), int(float(m.get("generated_at") or 0)), theme_base.RULES)


def _base_args(region: str, theme: str, inds: dict) -> dict:
    """with_base's arguments for a theme: its named list, the companies kept out, the industries its name leaves out and the size it names."""
    return {"named": inds.get("named") or (), "exclude": inds.get("except") or (), "drop": inds.get("drop") or (),
            "sized": theme_base.in_band(region, theme_base.size_band(theme), _rows(region))}


def placed(region: str, theme: str, m: dict, out: dict, ask=None) -> dict:
    """The checked map with every company of the theme's industries in one of the map's own layers (theme_base.place_rest, R21): the AI's
    answer is asked once a map and kept in the shared store with it (app/computed.py), so it is never asked again for that map."""
    from .. import computed
    key = ["place", region, theme.lower(), int(float(m.get("generated_at") or 0)), theme_base.RULES]
    try:
        kept = (computed.get("theme:place", key) or {}).get("value") or {}
    except Exception:
        kept = {}
    names = {c["ticker"]: c.get("name") for v in out.get("value_chain") or [] for c in v.get("companies") or []}
    if ask is not None:                       # the background check, about to ask the AI: the companies it places carry their own words
        describe_unplaced(region, out, names, kept)
    about = _about_reader(region, names, 0)                           # stored descriptions only: nothing is read from a page here
    new, got = theme_base.place_rest(out, theme, lambda s_: about(s_), ask=ask, kept=kept, facts_of=_facts_reader(region))
    if ask is not None and got and got != kept and (got.get("names_for") or any(x.get("by") == "ai" for x in (got.get("assign") or {}).values())):
        try:
            computed.put("theme:place", key, got, label=m.get("sector") or theme, region=region)
        except Exception as e:
            print("theme: placements not kept:", type(e).__name__, str(e)[:100])
    return new


def _has_description(region: str, sym: str) -> bool:
    """Whether a company's own description is kept (the shared store's theme:evidence entry), or was looked for lately and none found."""
    k = f"theme:evidence:{region}:{sym}"
    hit = EVIDENCE_CACHE.get(k)
    if hit is None:
        try:
            hit = db.json_value(db.get_setting(k), {}) or {}
        except Exception:
            hit = {}
    if not hit.get("at"):
        return False
    if hit.get("about"):
        return True
    try:                     # none on its page: asked again after NO_DESCRIPTION_DAYS (evidence_reader)
        return (datetime.now(timezone.utc) - datetime.fromisoformat(hit["at"])).days < NO_DESCRIPTION_DAYS
    except Exception:
        return False


def describe_unplaced(region: str, out: dict, names: dict, kept: dict | None) -> list[str]:
    """R28 (the owner's review: IT services "How they earn is shown for only 6 of these 46 companies"): a description is kept only for the
    companies the AI added (their check reads it) and the largest DESCRIBE_MAX on the page, a few a view, so a small company the placement
    sends to the AI had no words of its own and no revenue model. Before the placement asks, the companies of the theme's industries it
    hasn't placed yet (largest first) with no kept description have their own page's description read once and kept in the shared store
    (evidence_reader): at most PLACE_READS a theme check, never for a placement already kept, no job of its own. The symbols read."""
    kept = kept if isinstance(kept, dict) else {}
    done = set((kept.get("assign") or {}) if isinstance(kept.get("assign"), dict) else ())
    rest = [c for v in out.get("value_chain") or [] if v.get("official") and v.get("basis") in ("industry", "list") and not v.get("by_industry")
            for c in v.get("companies") or [] if c.get("ticker") and c["ticker"] not in done]
    if not any(not v.get("official") and v.get("layer") for v in out.get("value_chain") or []):
        return []                               # no layers of the map's own to place them in (theme_base.place_rest)
    want = []
    for c in sorted(rest, key=lambda c: (-(c.get("cap") or 0), c["ticker"]))[:theme_base.PLACE_MAX]:
        if len(want) >= PLACE_READS:
            break
        if not _has_description(region, c["ticker"]):
            want.append(c["ticker"])
    if want:
        try:
            evidence_reader(region, names)(want)
        except Exception as e:                  # a source busy: placed by the words it has, read on a later check
            print("theme: descriptions to place not read:", type(e).__name__, str(e)[:100])
    return want


def _facts_reader(region: str):
    """symbol -> {"industry", "segments", "filings", "business"}: what the app already keeps of how a company earns, beside its description (R26): the official
    industry path its page gave (kept with its description), the names of the segments its documents report (the company page's business read)
    and its filings' titles (own_filings); R27: the business read's summary, segment lines and customers (theme_check.business_text). Nothing is
    read from a source here."""
    def facts_of(sym):
        k = f"theme:evidence:{region}:{sym}"
        hit = EVIDENCE_CACHE.get(k)
        if hit is None:
            try:
                hit = db.json_value(db.get_setting(k), {}) or {}
            except Exception:
                hit = {}
        segs, business = [], ""
        try:
            from .. import deepdive
            b = (deepdive.stored(sym) or {}).get("business") or {}
            segs = [str(x.get("name")) for x in (b.get("segments") or []) if isinstance(x, dict) and x.get("name")]
            business = theme_check.business_text(b)          # R27: the business read's own lines (what it sells, to whom, how it earns)
        except Exception as e:
            print("theme: segments not read:", sym, type(e).__name__, str(e)[:100])
        return {"industry": (hit or {}).get("industry") or "", "segments": segs, "filings": own_filings(region, sym), "business": business}
    return facts_of


def _no_ai(system: str, text: str) -> dict:
    raise AIError("Not asked while a page waits.")


def quick(region: str, theme: str, m: dict) -> dict:
    """The map before its checks are in, worked out with no AI call: every company of the theme's official industries (the curated table,
    the AI's pick kept from before, or the industries named like the theme), the AI's own placements shown as not yet confirmed, and the
    tailwinds and risks as general background until they are checked against dated headlines."""
    inds = theme_base.industries_for(region, theme, _rows(region), _no_ai, db.get_setting, db.set_setting)
    unconfirmed = lambda cos: [{**c, "verified": False} for c in cos or []]      # noqa: E731
    out = {**m, "value_chain": [{**v, "companies": unconfirmed(v.get("companies"))} for v in m.get("value_chain") or []],
           "sub_themes": [{**x, "companies": unconfirmed(x.get("companies"))} for x in m.get("sub_themes") or []]}
    out["placements"] = {"checked": False, "pending": len(_map_names(m)), "left_out": 0}
    out = theme_base.with_base(m, out, _rows(region), inds["industries"], grounding.listed_name, **_base_args(region, theme, inds))
    out = placed(region, theme, m, out, ask=None)                  # the answer kept with the map, else by the companies' words (no AI here)
    key = check_key(region, theme, m)
    claims = A.get("sector_claims", key) or _plain_claims(m)
    out["tailwinds"], out["risks"] = claims["tailwinds"], claims["risks"]
    out["placements"]["industries_by"] = inds["how"]
    return out


def checked(region: str, theme: str, m: dict, wait: bool = False) -> dict:
    """The map as the page shows it, never waiting on the AI (LIVE3-001): the checked map when it is in; otherwise the checks are started
    in the background (`_check`) and the request gets the latest partly checked map, or the base with nothing checked yet (`quick`).
    `wait`: work the checks out here (an admin's blog draft)."""
    if m.get("_library"):                       # the theme library's stored read: checked already (theme_library.py)
        return with_caps(m, _rows(region))
    key = check_key(region, theme, m)
    hit = A.get("sector_checked3", key)
    if hit is None and wait:
        hit = _check(region, theme, m)
    if hit is None:
        later(("check",) + key, lambda: _check(region, theme, m))
        hit = A.get("sector_checked3", key) or A.get("sector_checking", key) or quick(region, theme, m)
    return with_caps(hit, _rows(region))


def with_caps(m: dict, rows: list[dict]) -> dict:
    """The map's market values as the index has them now (LIVE3-003: a map kept for a day showed BDL at the 3 Nov close beside its own
    page's 4 Nov one): the index takes each page's newest close as the price job moves it (screens.note_price)."""
    caps = {r["symbol"]: r.get("market_cap") for r in rows or [] if r.get("symbol")}
    fix = lambda cos: [{**c, "cap": caps[c["ticker"]]} if c.get("ticker") in caps else c for c in cos or []]      # noqa: E731
    return {**m, "value_chain": [{**v, "companies": fix(v.get("companies"))} for v in m.get("value_chain") or []],
            "sub_themes": [{**x, "companies": fix(x.get("companies"))} for x in m.get("sub_themes") or []]}


def _check(region: str, theme: str, m: dict) -> dict:
    """The checks themselves: every company of the theme's official industries (theme_base.py), the AI's placements checked
    against the companies' own descriptions (a "no" moves a base company out of that layer, never out of the theme; an addition from
    another industry is left out), claims against dated headlines. A part that can't be checked right now (a source or the AI is busy) is
    left to the next run; after PENDING_GIVE_UP it is served as it stands, its companies not yet confirmed, and checked again two hours
    on, so the page never waits on one company for minutes (THEMES item 6: "1 company is still being checked" for over two minutes)."""
    key = check_key(region, theme, m)
    hit = A.get("sector_checked3", key)
    if hit is not None:
        return hit
    with _ai_gate:                                  # one check at a time: the sources and the AI are shared
        hit = A.get("sector_checked3", key)
        if hit is not None:
            return hit
        if len(VERDICTS) > VERDICT_KEEP:
            VERDICTS.clear()
        out = theme_check.check_placements(m, evidence_reader(region, _map_names(m)), _ask, theme, VERDICTS)
        missing = None
        if region == "US":
            try:
                missing = fill_us_industries()
            except Exception as e:
                print("theme: SEC codes not filled:", type(e).__name__, str(e)[:100])
        inds = _industries(region, theme)
        out = theme_base.with_base(m, out, _rows(region), inds["industries"], grounding.listed_name, **_base_args(region, theme, inds))
        out = placed(region, theme, m, out, ask=_ask)
        claims = A.get("sector_claims", key)
        if claims is None:
            try:
                claims = theme_check.check_claims(m, _headlines(region), _ask)
                A.keep("sector_claims", key, {"tailwinds": claims["tailwinds"], "risks": claims["risks"]}, 24 * 3600)
            except AIError:
                claims = _plain_claims(m)
        out["tailwinds"], out["risks"] = claims["tailwinds"], claims["risks"]
        p = out["placements"]
        p["industries_by"] = inds["how"]
        if missing is not None:
            p["unclassified"] = missing              # US companies still without an industry on file (none of their SEC records read yet)
        done = p["checked"] and inds["how"] != "pending"
        if len(_pending_since) > VERDICT_KEEP:
            _pending_since.clear()
        if done:
            _pending_since.pop(key, None)
            # 3: the official-industry base (THEMES, 4 Nov); 2: placements re-checked after the 31 Oct fix
            A.keep("sector_checked3", key, out, 24 * 3600)
        elif time.time() - _pending_since.setdefault(key, time.time()) > PENDING_GIVE_UP:
            p["checked"], p["timed_out"] = True, p.get("pending") or 0
            _pending_since.pop(key, None)
            A.keep("sector_checked3", key, out, 2 * 3600, persist=False)     # checked again later, so not kept for everyone
        p["checked"] = p["checked"] and inds["how"] != "pending" or bool(p.get("timed_out"))
        if not p["checked"]:
            A.keep("sector_checking", key, out, 30 * 60)       # served while the next run goes on (LIVE3-001)
    with_descriptions(region, out, DESCRIBE_READS)             # a few more companies' own descriptions read for the next view
    return out


def _about_reader(region: str, names: dict, limit: int = DESCRIBE_READS):
    """symbol -> its stored description, or None: from memory or storage, and at most `limit` read from the company's own page per
    run (largest first), so a theme of hundreds fills in over a few views without a burst of reads."""
    reads = {"n": 0, "missed": 0}
    lock = threading.Lock()

    def about_of(sym):
        k = f"theme:evidence:{region}:{sym}"
        hit = EVIDENCE_CACHE.get(k)
        if hit is None:
            try:
                got = db.json_value(db.get_setting(k), {})
            except Exception:
                got = {}
            if got.get("at"):
                hit = got
                EVIDENCE_CACHE.set(k, hit, 6 * 3600)
        if hit is None:
            with lock:
                if reads["n"] >= limit:
                    reads["missed"] += 1
                    return None
                reads["n"] += 1
            try:
                return (evidence_reader(region, names)([sym])[0].get(sym) or {}).get("about")
            except Exception:
                return None
        return hit.get("about") or own_filings(region, sym) or None         # no description: the lines of its own filings
    about_of.reads = reads
    return about_of


def with_descriptions(region: str, m: dict, reads: int = 0) -> dict:
    """The map with each official-industry company's own one-line description where it is known (theme_base.described). A request reads
    none itself (`reads` 0: a company page can be slow, LIVE3-001): the ones not stored yet are read in the background, DESCRIBE_READS a
    run, for the next view."""
    if m.get("_library"):                       # described already when it was kept
        return m
    want = set(theme_base.to_describe(m))
    read = _about_reader(region, {c["ticker"]: c.get("name") for v in m.get("value_chain") or [] for c in v.get("companies") or []}, reads)
    out = theme_base.described(m, lambda s: read(s) if s in want else None)
    if not reads and read.reads["missed"]:
        later(("describe", region, hash(tuple(sorted(want)))), lambda: with_descriptions(region, m, DESCRIBE_READS), wait=0)
    return out


# ---------- the dive ----------
def facts_piece(region: str, sym: str, fresh: bool = False) -> tuple[dict | None, float | None]:
    """(a company's stored page facts as themes use them, when they were kept): kept once for every theme in the shared store (kind
    "theme:facts"), so two themes with the same company read the same figures, and a Refresh of one theme (`fresh`: taken again from the
    company's stored page) gives the other its new figures too (dive_of: a theme's figures are worked out again when a company piece it
    used was refreshed). A company with no stored page: (None, None)."""
    R = _routes()
    if not fresh:
        hit = computed.get(theme_library.FACTS, [region, sym])
        if hit is not None and isinstance(hit.get("value"), dict):
            return hit["value"], hit.get("at")
    f = R.public_facts(region, sym) if callable(R.public_facts) else None
    if not f:
        return None, None
    kept = computed.put(theme_library.FACTS, [region, sym], f, label=sym, region=region)
    return f, (kept or {}).get("at")


def pieces_moved(region: str, pieces: dict) -> bool:
    """Whether a company piece a stored dive used ({symbol: when kept}) has been kept again since (another theme's Refresh)."""
    if not pieces:
        return False
    ix = computed.index(theme_library.FACTS)["entries"]
    return any(float((ix.get(computed.hkey([region, s])) or {}).get("at") or 0) > float(at or 0) for s, at in pieces.items())


def sources(region: str, theme: str, fresh: bool = False):
    """The stored readers a dive uses, each on the market it is for. Companies' facts come from the shared pieces (facts_piece), taken
    again from their stored pages when `fresh` (a Refresh); the pieces used are on the result's `pieces`."""
    from .. import corp_actions, deals, redflags, report_card, results, shareholders
    R = _routes()
    today = datetime.now(R.IST).date() if region == "IN" else datetime.now(timezone.utc).date()
    hist_key = f"theme:hist:{region}:{theme_data.slug(theme)}"

    def history(_, point):
        try:
            pts = db.json_value(db.get_setting(hist_key), [])
        except Exception:
            pts = []
        pts = [p for p in pts if isinstance(p, dict) and p.get("d")]
        if point.get("pe") is not None and (not pts or (date.fromisoformat(point["d"]) - date.fromisoformat(pts[-1]["d"])).days >= 6):
            pts = (pts + [point])[-HISTORY_KEEP:]
            try:
                db.set_setting(hist_key, json.dumps(pts, separators=(",", ":")))
            except Exception as e:
                print("theme: history not kept:", str(e)[:100])
        return pts

    def card(sym, row):
        stored = report_card.stored(sym) if region == "IN" else None
        if not stored or not row:
            return None
        nums = {"years": [{"year": y["year"], "sales": y["sales"], "profit": y["profit"], "opm": y["opm"], "capex": None} for y in row["years"]],
                "quarters": [], "fye": 3, "bank": row.get("bank"), "unit": row.get("unit") or "₹ crore"}
        return report_card.view(stored, nums, today)

    def segments(sym):                    # the business segments the company's documents report, when they were read (is_diversified)
        from .. import deepdive
        return (((deepdive.stored(sym) or {}).get("business") or {}).get("segments")) or None

    def red(symbols, frm, to):
        return redflags.listing(region, frm=frm.isoformat(), to=to.isoformat(), symbols=symbols, size=200, today=today)["items"]
    pieces: dict = {}

    def facts(sym):
        f, at = facts_piece(region, sym, fresh)
        if at:
            pieces[sym] = at
        return f
    src = theme_data.Sources(
        today, facts=facts, index_rows=lambda: R.index_rows(region),
        shareholding=(lambda s: shareholders.company(s)) if region == "IN" else (lambda s: None),
        insider_buys=(lambda: deals.buys().get("buys") or {}) if region == "IN" else (lambda: {}),
        results=lambda a, b, s: results.between(region, a, b, s), actions=lambda a, b, s: corp_actions.between(region, a, b, s),
        red_flags=red, card=card, history=history, segments=segments,
        corp_history=lambda s: corp_actions.history(region, s, None, fetch=False),
        metrics=sector_metrics.reader(region, fresh))           # R23: filed sector figures, read once and kept for everyone
    src.pieces = pieces
    return src


@router.get("/theme-dive")
def theme_dive(q: str, region: str = "IN", refresh: bool = False, profile=Depends(current_profile)):
    """The theme's figures. R19: kept for everyone in the shared store (dive_of) and served until a Refresh; a Refresh just after the
    theme's own Refresh (its new map) is part of that one and isn't counted again."""
    R = _routes()
    r, theme, m, _ = R.theme_map(profile, region, q)
    m = with_descriptions(r, checked(r, theme, m))
    by = None
    if refresh:
        kept = computed.get(theme_library.DIVE, dive_key(r, theme, m), count=False)
        state = "go" if kept is None else computed.refresh_gate(profile, "theme:dive", kept.get("at"))
        if state != "go":
            return R.ok({**kept["value"]["dive"], "refresh_state": state})
        by = computed.plan_word(profile)
    out = dive_of(r, theme, m, refresh, by=by)
    return R.ok({**out, "refresh_state": "done"} if refresh else out)


def dive_key(r: str, theme: str, m: dict) -> list:
    """A dive's key in the shared store: the market, the stored theme's name (or the search's normalised one), the map's time, how many
    companies are placed and described, and the rules' version."""
    fm = theme_base.for_figures(m)[0]
    said = sum(1 for v in fm["value_chain"] if v.get("official") for c in v["companies"] if c.get("what"))
    return [r, m.get("_library") or theme_library.normalise(theme, r), int(float(m.get("generated_at") or 0)),
            (m.get("placements") or {}).get("placed"), said, theme_base.RULES, f"sm{sector_metrics.VERSION}"]


def requeue(r: str, dive: dict) -> None:
    """R29: a kept dive still waiting for filed figures queues them again (the worker drops a read that fails, e.g. the exchange busy, and a
    kept dive is only worked out again once one of them is stored, so a dropped read left the dive short until a Refresh: the live R27 Banks
    deck's 7 of 19). The queue skips one already queued or stored; nothing is queued with no source set up."""
    fams = dive.get("metrics_families") or {}
    for s_ in dive.get("metrics_pending") or []:
        if fams.get(s_):
            sector_metrics.queue(r, s_, fams[s_])


def figures_waiting(dive: dict) -> int:
    """How many companies' filed sector figures a dive is still waiting for (R29: part of a kept deck's key, so a deck made while they are
    being read is made again once they are in, never kept for the day with a smaller sample)."""
    return len(dive.get("metrics_pending") or [])


def dive_of(r: str, theme: str, m: dict, refresh: bool = False, by: str | None = None) -> dict:
    """The dive for a checked map with its descriptions (the page's tables and sections): kept once for everyone in the shared store
    (kind "theme:dive") and served from there, however old, until a Refresh (owner, 7 Nov); worked out again from the stored company
    pieces (no AI) when one of them was refreshed by another theme (pieces_moved)."""
    fm, figures = theme_base.for_figures(m)
    key = dive_key(r, theme, m)
    if not refresh:
        kept = computed.get(theme_library.DIVE, key)
        if kept is not None and isinstance((kept.get("value") or {}).get("dive"), dict) and not pieces_moved(r, kept["value"].get("pieces") or {}) \
                and not sector_metrics.any_stored(r, kept["value"]["dive"].get("metrics_pending") or []):
            requeue(r, kept["value"]["dive"])
            return kept["value"]["dive"]
    src = sources(r, theme, fresh=True) if refresh else sources(r, theme)
    hit = theme_data.build(r, theme, fm, src)
    hit["placements"], hit["figures"] = m.get("placements"), figures
    late = {x["symbol"]: x["filed_unread"] for x in ((hit.get("sections") or {}).get("quarter") or {}).get("earlier") or [] if x.get("filed_unread")}
    if late:                      # results filed since the stored page was built: the screens' sweep builds those pages first (R18)
        try:
            from .. import stock_pages
            stock_pages.mark_due(r, late)
        except Exception as e:
            print("theme: pages behind a filing not marked:", type(e).__name__, str(e)[:100])
    if (m.get("placements") or {}).get("checked"):
        computed.put(theme_library.DIVE, key, {"dive": hit, "pieces": getattr(src, "pieces", None) or {}}, label=m.get("sector") or theme,
                     region=r, by=by)
        auto_post(r, theme, hit)
    return hit


# ---------- a blog post for a theme people read (R15) ----------
AUTO_POSTS_A_DAY = 3                 # bounded work: at most this many new theme posts a day, whatever people read
AUTO_KEY = "blog:auto_theme"
_auto_lock = threading.Lock()
_auto_busy: set = set()


def auto_post(r: str, theme: str, dive: dict, wait: bool = False) -> None:
    """A theme read with all its placements checked and no blog post yet gets one, from the dive just built (no second read): the owner, 7
    Nov: "if someone searches a theme we don't have a blog about, make a blog out of it automatically". Stored hidden, as every theme post
    is (blog_research.theme_post), for the owner to publish from Admin; one per theme (its address), at most AUTO_POSTS_A_DAY new ones a day;
    no email. Runs beside the request (`wait` for tests); a failure only prints."""
    import os
    if not wait and os.environ.get("THEME_AUTO_POST", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    from .. import blog_research
    try:
        post = blog_research.theme_post(dive, theme, r, notable_only=False)
    except Exception as e:
        print("theme auto post: not made:", type(e).__name__, str(e)[:100])
        return
    if not post:
        return
    slug = post["slug"]
    with _auto_lock:
        if slug in _auto_busy:
            return
        _auto_busy.add(slug)

    def go():
        from .. import blog
        try:
            if blog.get(slug) or blog_research.advice_words(post):
                return
            day = datetime.now(timezone.utc).date().isoformat()
            with _auto_lock:
                st = db.json_value(db.get_setting(AUTO_KEY), {}) or {}
                n = int(st.get("n") or 0) if st.get("day") == day else 0
                if n >= AUTO_POSTS_A_DAY:
                    return
                db.set_setting(AUTO_KEY, json.dumps({"day": day, "n": n + 1}))
            print("theme auto post:", slug, blog.upsert_research(post))
        except Exception as e:
            print("theme auto post: not stored:", slug, type(e).__name__, str(e)[:100])
        finally:
            with _auto_lock:
                _auto_busy.discard(slug)
    if wait:
        go()
    else:
        threading.Thread(target=go, name="theme-auto-post", daemon=True).start()


# ---------- the theme's deck (EXPORT) ----------
def by_of(c: dict) -> str:
    """How a company is in the theme, in the words the page's "In the theme by" column uses."""
    if c.get("base"):
        return "Named in the theme's list" if c.get("basis") == "list" else "Official industry"
    return "Added, confirmed by its own words" if c.get("verified") else "Added, not yet confirmed"


def members_of(m: dict, dive: dict) -> list[dict]:
    """Every company in the theme as the page lists it (each layer's companies, then those named in a sub-theme only), each with its market
    value, and the revenue and margins the dive worked out for it where it has them."""
    figs: dict = {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            figs.setdefault(c["symbol"], c)
    for sub in dive.get("subs") or []:
        for c in sub.get("companies") or []:
            figs.setdefault(c["symbol"], c)
    in_layer = {c["ticker"] for v in m.get("value_chain") or [] for c in v.get("companies") or []}
    groups = [(v.get("layer") or "", v.get("companies") or []) for v in m.get("value_chain") or []]
    only = {}
    for sub in m.get("sub_themes") or []:
        for c in sub.get("companies") or []:
            if c["ticker"] not in in_layer:
                only.setdefault(c["ticker"], c)
    if only:
        groups.append(("Named in a sub-theme only", list(only.values())))
    out = []
    official = {v.get("layer") or "": bool(v.get("official")) and v.get("basis") != "list" for v in m.get("value_chain") or []}
    for layer, cos in groups:
        for c in cos:
            f = figs.get(c["ticker"]) or {}
            out.append({"symbol": c["ticker"], "name": c.get("name") or f.get("name") or c["ticker"], "layer": layer, "official": official.get(layer, False),
                        "industry": c.get("industry") or None, "what": c.get("what") or f.get("what") or None,
                        "cap": c.get("cap") if c.get("cap") is not None else f.get("cap"), "revenue": f.get("revenue"), "ebitda": f.get("ebitda"),
                        "net": f.get("net"), "roce": f.get("roce"), "year": f.get("year"), "by": by_of(c)})
    return out


def deck_view(r: str, m: dict, dive: dict, extra: dict | None = None) -> dict:
    """What theme deck slides are made of (deck.theme_plan): every part of the theme's page (DECK, 5 Nov: "it doesn't contain everything
    there is on the page about the theme"): the map's words and checks, the dive's figures and sections, and the parts the page reads on its
    own (`extra`: news, listings, prices, business; None where they weren't read)."""
    med = ((dive.get("sections") or {}).get("medians") or {}).get("ebitda") or {}
    return {"region": r, "sector": m.get("sector") or dive.get("sector"), "summary": m.get("summary") or "", "core": m.get("core") or "",
            "etfs": m.get("etfs") or [], "generated_at": m.get("generated_at") or 0, "as_of": dive.get("as_of"),
            "unit": dive.get("unit"), "basis": dive.get("basis"), "chain": dive.get("chain") or {}, "layers": dive.get("layers") or [],
            "subs": dive.get("subs") or [], "sections": dive.get("sections") or {}, "company_wide": dive.get("company_wide") or [],
            "members_with_figures": dive.get("members"),
            "members": members_of(m, dive), "tailwinds": m.get("tailwinds") or [], "risks": m.get("risks") or [],
            "placements": m.get("placements") or {}, "figures": dive.get("figures") or {}, "median_ebitda": med.get("median"),
            "checks": dive.get("checks") or {}, "status": dive.get("status") or {}, "with_figures": dive.get("with_figures"),
            "membership": dive.get("membership") or {},
            "news": None, "listings": None, "prices": None, "business": None, **(extra or {})}


def deck_extras(r: str, theme: str, m: dict, profile: dict) -> dict:
    """The parts of the theme's page that it reads on its own, as the page last read them: the latest headlines and the new listings from
    their caches, the prices of the companies already read (no candles fetched for the deck), and the business updates on the plans that
    have them. A part not read yet is None, and the deck says so once."""
    out: dict = {}
    fm = theme_base.for_figures(m)[0]
    stamp = int(float(fm.get("generated_at") or 0))
    hit = NEWS_CACHE.get((r, theme.lower(), stamp))
    out["news"] = hit["items"] if hit else None
    listed = IPO_CACHE.get((r, theme.lower(), int(float(m.get("generated_at") or 0))))
    out["listings"] = listed["items"] if listed and listed.get("checked") else None
    names = _map_names(fm)
    placed = sorted({c["ticker"]: names.get(c["ticker"]) for grp in (fm.get("value_chain") or []) + (fm.get("sub_themes") or [])
                     for c in grp.get("companies") or []}.items())
    if placed and any(PRICE_CACHE.get(f"{r}:{sym}") for sym, _ in placed):
        try:
            prices = gather_prices(r, placed, bars_loader(r), bench_loader(r), budget=0.0)
            out["prices"] = prices if prices.get("companies") else None
        except Exception as e:                       # the deck is made without them, and says so
            print("theme deck: prices not read:", type(e).__name__, str(e)[:100])
    if r == "IN":
        from .. import biz_updates
        if biz_updates._allowed(profile):
            out["business"] = business_of(r, m)
    return out


DECK_CACHE = TTLCache(max_items=24, max_bytes=8 * 1024 * 1024)            # a theme's PDF or PowerPoint, about 200 KB
DECK_TTL = 6 * 3600
REGION_WORD = {"IN": "India", "US": "US"}


def deck_file_name(theme: str, r: str, fmt: str, day: date) -> str:
    """The file's name as the page saves it (lib/deckName.ts): "StratLab - India Defence theme (India) - 7 Nov 2026.pdf", plain ASCII."""
    import re
    import unicodedata
    clean = unicodedata.normalize("NFKD", f"{theme} theme ({REGION_WORD.get(r, r)})").encode("ascii", "ignore").decode()
    clean = re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", clean)).strip()[:120] or "StratLab deck"
    return f"StratLab - {clean} - {day.day} {day.strftime('%b %Y')}.{fmt}"


DECK_MAP_WAIT = 8.0          # seconds a deck request waits for the AI map and its checks before answering "preparing" (R21)
DECK_RETRY = 10              # seconds the page waits before asking again


def map_for_deck(R, profile, region: str, q: str, wait: float = DECK_MAP_WAIT, pending: list | None = None):
    """(market, theme, the checked map with its descriptions) for a deck. The page fills in as the AI parts arrive, but a file is made once:
    a deck made while the AI map was still being written had no map at all (R20: every live R19 deck, made after a deploy emptied the kept
    maps: "Private banks" with no value chain, "Cybersecurity" with the SEC's industries as layers). So it waits, at most `wait` seconds,
    for a map and a check that are running; R21: when they are still running after that (a first map takes longer than any wait), `pending`
    gets True and the route answers "preparing" instead of making a file without the map. A map or check that failed isn't waited for."""
    t0 = time.time()
    r, theme, m, _ = R.theme_map(profile, region, q)     # R19: the theme library's stored read when there is one (kept across deploys)
    # R26: a kept map due to be written again under a newer prompt (ai.map_due) is waited for as a missing one is: the live R25 decks of four
    # themes were made on the old map while the new one was being written, and the next pull differed. sector_map has started the rewrite.
    due = lambda m_: not m_.get("_library") and A.map_due(m_)          # noqa: E731
    if not float(m.get("generated_at") or 0) or due(m):
        j = job_of(("map", r, theme.lower()))
        if j and j["state"] == "running":
            j["done"].wait(max(0.0, wait - (time.time() - t0)))
            r, theme, m, _ = R.sector_map(profile, region, q, False)
    if pending is not None and due(m):
        pending.append(True)                           # R26: never a file on a map that is being replaced, whatever its rewrite's state;
        return r, theme, m                             # nor a check of it worked out for nothing
    c = checked(r, theme, m)
    if not (c.get("placements") or {}).get("checked"):
        j = job_of(("check",) + check_key(r, theme, m))
        if j and j["state"] == "running":
            j["done"].wait(max(0.0, wait - (time.time() - t0)))
            c = checked(r, theme, m)
    if pending is not None:
        mj = job_of(("map", r, theme.lower()))
        cj = job_of(("check",) + check_key(r, theme, m))
        pending.append((not float(m.get("generated_at") or 0) and bool(mj) and mj["state"] == "running")
                       or (not (c.get("placements") or {}).get("checked") and bool(cj) and cj["state"] == "running"))
    return r, theme, with_descriptions(r, c)


@router.get("/theme-dive/deck")
def theme_dive_deck(q: str, region: str = "IN", format: str = "pptx", profile=Depends(current_profile)):
    """The theme deep dive as slides, PowerPoint or PDF (EXPORT): the cover, the value chain, every company with its figures, the
    tailwinds and risks with their sources, and which placements are confirmed. Counted against the plan's monthly decks as a
    company's deck is (Free 1, Basic 5, Pro unlimited); a theme's PDF and PowerPoint are one deck, once a month. A file made today for the
    same read of the theme is kept (DECK_CACHE) and sent again at once: the owner, 6 Nov: "it's taking a whole lot of time to make the pdf"."""
    from .. import biz_updates, deck, main
    if format not in ("pptx", "pdf"):
        err(400, "bad_format", "Pick PowerPoint or PDF.")
    R = _routes()
    pending: list = []
    r, theme, m = map_for_deck(R, profile, region, q, pending=pending)
    mark = main.check_deep(profile, "deck", "", r, mark=f"deck:theme:{r}:{theme_data.slug(theme)}")
    if pending and pending[0]:
        # R21: the AI map or its checks are still being written: no file without them, and nothing counted; the page asks again
        from fastapi.responses import JSONResponse
        return JSONResponse({"preparing": True, "retry_after": DECK_RETRY,
                             "message": "Preparing the deck: the AI map is being written."}, status_code=202)
    today = datetime.now(R.IST).date()
    biz = r == "IN" and bool(biz_updates._allowed(profile))       # the one part of the deck that depends on the plan
    stamp = int(float(m.get("generated_at") or 0))
    seen = (NEWS_CACHE.get((r, theme.lower(), int(float(theme_base.for_figures(m)[0].get("generated_at") or 0)))) is not None,
            bool((IPO_CACHE.get((r, theme.lower(), stamp)) or {}).get("checked")))     # a part read since is in a new file
    # R29 (P0, the live R27 Banks deck: 7 of 19 banks' filed figures): the dive first, so the key says how many companies' filed figures it
    # still waits for; a deck made while they are read is kept under that count and made again from the fuller dive once they are in
    dive = dive_of(r, theme, m)
    waiting = figures_waiting(dive)
    key = (r, theme.lower(), format, today.isoformat(), stamp, biz, seen, theme_base.RULES, deck.THEME_DECK_VERSION, waiting)
    body = DECK_CACHE.get(key)
    if body is None:                           # R20: the file is kept in the shared store too, so a restart or a deploy doesn't rebuild it
        import base64
        from .. import computed
        got = computed.get("deck:theme", list(key))
        if got and isinstance(got.get("value"), str):
            try:
                body = base64.b64decode(got["value"])
            except ValueError:
                body = None
        if body is None:
            view = deck_view(r, m, dive, deck_extras(r, theme, m, profile))
            body, gate = deck.build_theme_gated(view, pdf=format == "pdf")
            # R27: the publication gate's result (pass or fail per item, what was dropped) is kept with the deck, for Admin -> Library;
            # R29: a deck still waiting for filed figures isn't kept in the shared store (it is made again once they are in)
            if not waiting:
                computed.put("deck:theme", list(key), base64.b64encode(body).decode(), label=f"{theme} ({format.upper()}, {today.isoformat()})", region=r,
                             meta={"gate": gate})
        DECK_CACHE.set(key, body, DECK_TTL, size=len(body))
    if mark:                                   # counted once the file is made: a deck that failed to build uses nothing
        db.add_usage(profile["id"], "deck")
        db.add_usage(profile["id"], mark)
    from fastapi.responses import Response
    return Response(body, media_type="application/pdf" if format == "pdf" else "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{deck_file_name(theme, r, format, today)}"'})


# ---------- business updates ----------
def business_reader():
    """symbol -> the company's headline operating figure from the business updates already read and stored (biz_updates), or None."""
    from .. import biz_updates

    def read(sym):
        reads = biz_updates.stored(sym)
        if not reads:
            return None
        h = biz_updates.headline(biz_updates.series(reads))
        if not h:
            return None
        src = h["latest"]["source"]
        return {"metric": h["metric"], "unit": h["unit"], "span": h["span"], "step": h["step"], "period": h["latest"]["period"], "value": h["latest"]["value"],
                "prev": h["prev"]["value"] if h.get("prev") else None, "year_ago": h["year_ago"]["value"] if h.get("year_ago") else None,
                "change_prev": h["change_prev"], "change_year": h["change_year"], "filed": src["at"][:10], "url": src["url"], "page": src.get("page"),
                "exchange": src.get("exchange"), "points": [{"period": p["period"], "value": p["value"]} for p in h["points"]]}
    return read


@router.get("/theme-dive/business")
def theme_dive_business(q: str, region: str = "IN", profile=Depends(current_profile)):
    """The theme's operating figures from business updates, by layer and sub-theme. Basic and up, as the Business updates page is."""
    from .. import biz_updates
    R = _routes()
    if region.upper() != "IN":
        return R.ok({"allowed": True, "layers": [], "subs": [], "companies": 0, "of": 0})
    if not biz_updates._allowed(profile):
        return R.ok({"allowed": False, "layers": [], "subs": [], "companies": 0, "of": 0})
    r, theme, m, _ = R.theme_map(profile, region, q)
    return R.ok(business_of(r, checked(r, theme, m)))


def business_of(r: str, m: dict) -> dict:
    """The theme's business-update figures by layer and sub-theme (the page's section and the deck's slides)."""
    m = theme_base.for_figures(m)[0]
    names = _map_names(m)
    blocks = [{"layer": v.get("layer") or "", "companies": [{"symbol": c["ticker"]} for c in v.get("companies") or []]} for v in m.get("value_chain") or []]
    subs = [{"name": v.get("name") or "", "companies": [{"symbol": c["ticker"]} for c in v.get("companies") or []]} for v in m.get("sub_themes") or []]
    return {"allowed": True, **theme_data.business_section(blocks, subs, names, business_reader())}


# ---------- new listings ----------
IPO_CACHE = TTLCache(max_items=24, max_bytes=512 * 1024)
IPO_DAYS = 365                  # issues that listed this recently, and every issue still to come or open


def ipo_items(region: str, today: date) -> list[dict]:
    """The IPO tracker's issues that are open, coming, awaiting listing or listed in the last year, as {id, name, text, row}."""
    from .. import ipo
    out = []
    for row in ipo.load(region)["rows"]:
        pub = ipo.public(row)
        if pub.get("stage") in (None, "withdrawn", "social", "filed") or row.get("social"):
            continue
        if pub["stage"] == "listed":
            listed = str(pub.get("listing") or "")[:10]
            if not listed or listed < (today - timedelta(days=IPO_DAYS)).isoformat():
                continue
        text = " ".join(x for x in (pub.get("name"), pub.get("industry"), str(pub.get("issue_text") or "")[:500]) if x)
        out.append({"id": pub["id"], "name": pub.get("name") or "", "text": text, "pub": pub})
    return out


@router.get("/theme-dive/listings")
def theme_dive_listings(q: str, region: str = "IN", profile=Depends(current_profile)):
    """New issues in the IPO tracker that belong in the theme, each kept only with words from its own offer that show the work."""
    R = _routes()
    r, theme, m, _ = R.theme_map(profile, region, q)
    m = checked(r, theme, m)
    m = {**m, "value_chain": [v for v in m.get("value_chain") or [] if not v.get("official")]}     # an official industry's layer has no work to match an offer on
    key = (r, theme.lower(), int(float(m.get("generated_at") or 0)))
    skey = [r, m.get("_library") or theme_library.normalise(theme, r), key[2]]
    kept = computed.get("theme:listings", skey)       # R19: kept for everyone with the theme's read
    hit = kept["value"] if kept is not None else IPO_CACHE.get(key)
    if kept is not None:
        IPO_CACHE.set(key, hit, 6 * 3600)              # (the deck reads the page's listings here)
    if hit is None:
        today = datetime.now(timezone.utc).date()
        try:
            items = ipo_items(r, today)
        except Exception as e:
            print("theme listings: tracker not read:", type(e).__name__, str(e)[:100])
            return R.ok({"items": [], "checked": False})
        try:
            with _ai_gate:
                hits = theme_check.match_listings(items, m, _ask, theme, VERDICTS)
        except AIError:
            return R.ok({"items": [], "checked": False})
        by = {i["id"]: i["pub"] for i in items}
        rows = []
        for h in hits:
            p = by[h["id"]]
            rows.append({"id": h["id"], "name": p.get("name"), "symbol": p.get("symbol"), "stage": p.get("stage"), "industry": p.get("industry"),
                         "open": p.get("open"), "close": p.get("close"), "listing": p.get("listing"), "groups": h["groups"], "what": h["what"]})
        hit = {"items": rows, "checked": True}
        IPO_CACHE.set(key, hit, 6 * 3600)
        computed.put("theme:listings", skey, hit, label=m.get("sector") or theme, region=r)
    return R.ok(hit)


# ---------- prices ----------
def bars_loader(region: str):
    """symbol -> daily candles of three years and a bit, from the same source the company pages read; raises when the sources are busy."""
    from .. import main, universes
    reg = main.markets

    def load(sym):
        ids, _ = universes.resolve(reg, region, [{"symbol": sym}])
        if not ids:
            return []
        prov, inst = reg.resolve(ids[0])
        if not prov or not inst:
            return []
        return prov.history(inst, "1d", 1200)
    return load


def bench_loader(region: str):
    from .. import main, rotation
    reg = main.markets

    def load():
        bid, sym = rotation.benchmark_id(reg, region)
        prov, inst = reg.resolve(bid)
        return sym, prov.history(inst, "1d", 1200)
    return load


def _price_ttl(region: str) -> int:
    try:
        from .. import main
        return main._chart_ttl(region)
    except Exception:
        return 900


def gather_prices(region: str, members: list[tuple[str, str]], load, bench, budget: float = PRICE_BUDGET) -> dict:
    """The price section for the members, reading each company's candles that isn't already reduced and kept; a company whose read has
    to wait (the minute's allowance is used, or the time is up) is counted as pending and read on a later request."""
    started = time.monotonic()
    reduced: dict = {}
    todo = []
    for sym, _ in members:
        hit = PRICE_CACHE.get(f"{region}:{sym}")
        if hit is not None:
            reduced[sym] = hit or None
        else:
            todo.append(sym)

    def one(sym):
        if time.monotonic() - started > budget or not price_reads.hit("all", PRICE_READS_PER_MINUTE):
            return sym, "late"
        try:
            return sym, theme_prices.reduce_bars(load(sym))
        except Exception as e:
            print("theme prices: candles not read:", sym, type(e).__name__, str(e)[:100])
            return sym, "late"
    if todo:
        with ThreadPoolExecutor(max_workers=min(4, len(todo))) as pool:
            for sym, red in pool.map(one, todo):
                if red == "late":
                    continue
                PRICE_CACHE.set(f"{region}:{sym}", red or {}, _price_ttl(region))
                reduced[sym] = red
    pending = sum(1 for s, _ in members if s not in reduced)
    bname, braw = None, None
    try:
        bname, braw = bench()
    except Exception as e:
        print("theme prices: index not read:", type(e).__name__, str(e)[:100])
    return theme_prices.compute(members, reduced, theme_prices.reduce_bars(braw or []), bname or "", pending)


@router.get("/theme-dive/prices")
def theme_dive_prices(q: str, region: str = "IN", profile=Depends(current_profile)):
    R = _routes()
    r, theme, m, _ = R.theme_map(profile, region, q)
    m = theme_base.for_figures(checked(r, theme, m))[0]
    names = _map_names(m)
    placed = {c["ticker"]: names.get(c["ticker"]) for grp in (m.get("value_chain") or []) + (m.get("sub_themes") or []) for c in grp.get("companies") or []}
    members = sorted(placed.items())
    if not members:
        return R.ok({"companies": [], "pending": 0, "line": None, "returns": None, "median": {}, "benchmark": ""})
    if not _price_gate.acquire(timeout=30):
        err(503, "busy", "Prices are busy right now. Try again in a minute.")
    try:
        out = gather_prices(r, members, bars_loader(r), bench_loader(r))
    finally:
        _price_gate.release()
    return R.ok(out)


# ---------- news ----------
NEWS_COMPANIES = 6            # the largest companies whose news is searched
NEWS_ITEMS = 20


def theme_news(region: str, theme: str, members: list[dict], search, today: date) -> list[dict]:
    """The latest dated items for a theme: exchange filings kept on each company's page (a company's own announcements), and headlines found
    for the theme and its largest companies. `members`: [{symbol, name, cap, filings}]. Newest first; a headline appears once."""
    items = []
    for c in members:
        for f in c.get("filings") or []:
            items.append({"at": f.get("at"), "headline": f.get("name") or f.get("title"), "company": c["name"], "symbol": c["symbol"],
                          "source": "Exchange filing" if region == "IN" else "SEC filing", "url": f.get("url") or "", "kind": "filing"})
    queries = [(theme, None)] + [(f"{c['name']} share price" if region == "IN" else f"{c['name']} stock", c) for c in sorted(members, key=lambda c: -(c.get("cap") or 0))[:NEWS_COMPANIES]]

    def one(item):
        q, c = item
        try:
            rows = search(q)
        except Exception as e:
            print("theme news: not read:", q, type(e).__name__, str(e)[:100])
            return []
        out = []
        for n in rows:
            if c and not company_headline(c["name"], c["symbol"], n["headline"]):
                continue
            out.append({"at": n.get("at"), "headline": n["headline"], "company": c["name"] if c else None, "symbol": c["symbol"] if c else None,
                        "source": n.get("source") or "", "url": n.get("url") or "", "kind": "news"})
        return out
    with ThreadPoolExecutor(max_workers=3) as pool:
        for rows in pool.map(one, queries):
            items += rows
    seen, out = set(), []
    items = [i for i in items if theme_data.headline_kept(i, region)]          # no quote pages, picks or other markets' news (R16)
    for i in sorted((i for i in items if i.get("at") and i.get("headline")), key=lambda i: str(i["at"]), reverse=True):
        k = " ".join(str(i["headline"]).lower().split())[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append({**i, "at": str(i["at"])[:10]})
    return out[:NEWS_ITEMS]


@router.get("/theme-dive/news")
def theme_dive_news(q: str, region: str = "IN", profile=Depends(current_profile)):
    R = _routes()
    r, theme, m, _ = R.theme_map(profile, region, q)
    m = theme_base.for_figures(checked(r, theme, m))[0]
    key = [r, m.get("_library") or theme_library.normalise(theme, r), int(float(m.get("generated_at") or 0))]
    kept = computed.get("theme:news", key)            # R19: kept for everyone with the theme's read; a Refresh of the theme is a new key
    hit = kept["value"] if kept is not None else None
    if hit is not None:
        NEWS_CACHE.set((r, theme.lower(), key[2]), hit, 20 * 60)     # (the deck reads the page's latest headlines here)
    if hit is None:
        names = _map_names(m)
        members = []
        for sym, name in sorted(names.items()):
            f = (R.public_facts(r, sym) if callable(R.public_facts) else None) or {}
            members.append({"symbol": sym, "name": name, "cap": f.get("market_cap"), "filings": (f.get("filings") or [])[:6]})
        today = datetime.now(timezone.utc).date()
        hit = {"items": theme_news(r, theme, members, _headlines(r), today), "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes")}
        NEWS_CACHE.set((r, theme.lower(), key[2]), hit, 20 * 60)
        computed.put("theme:news", key, hit, label=m.get("sector") or theme, region=r)
    return R.ok(hit)


# ---------- the theme library's index, for the search box (R19) ----------
@router.get("/theme-library/suggest")
def theme_library_suggest(q: str = "", region: str = "IN", profile=Depends(current_profile)):
    """Themes already read and kept for everyone that match what's typed ("Already read: Automotive · India, read 7 Nov"): the one the
    search would be served from first, then names that start with or contain it; with nothing typed, the most searched."""
    R = _routes()
    return R.ok({"items": theme_library.suggest(R.region_of(region), q[:80])})
