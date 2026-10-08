"""Named large shareholders across companies: the "1% lists" in each quarter's shareholding pattern.

Every listed company files its shareholding pattern with the exchange within three weeks of each quarter's end, as an
XBRL document. Besides the category totals it names the promoter group's members and every public shareholder that
holds more than 1% of the company (mutual funds, insurers, foreign portfolio investors, companies, individuals). This
module reads those names into {holder, company, quarter, shares, %}:

- one company's named holders, with the change since the quarter before (the company page's "Named holders");
- a search over every company read, by holder name, with quarter-on-quarter changes and "new" and "dropped below 1%"
  lines (Invest's "Named holders" page);
- following a holder (a name and the spellings the user ticked): a message when a new quarter's filing changes them.

The exchange's market-wide list of shareholding filings (one call for any date range) says which filings are new; the
job reads each new XBRL once and keeps the last four quarters per company in app_settings (shp:co:<SYMBOL>).

Facts only: names and numbers as filed, listed alphabetically or by stake size within one company. Nobody is ranked,
called a "superstar" or "smart money", and holdings are only those above 1% at the quarter's end."""
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import db
from .auth import current_profile
from .intel.net import SourceError, TTLCache
from .plans import FEATURE_PLAN, PLANS, allows, plan_of
from .responses import err, ok

KEY = "shp:co:"                 # shp:co:<SYMBOL> = {"name", "isin", "q": {"2026-06-30": {"rec", "filed", "url", "rows": [[name, kind, group, shares, pct]]}}}
STATE_KEY = "shp:state"         # {"listed_to": ISO day read up to, "backfilled": bool, "queue": [[symbol, quarter, rec, url, filed, name]]}
FOLLOW_KEY = "holderfollow:"    # holderfollow:<uid> = {"uid", "items": [{"id", "label", "names": [keys], "created_at"}]}
KEEP_QUARTERS = 4
MIN_PCT = 1.0                   # the filing names public holders above 1%; promoter-group members below it are left out
LIST_PATH = "/api/corporate-share-holdings-master"
REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"
XBRL_HOSTS = ("nsearchives.nseindia.com", "archives.nseindia.com", "www.nseindia.com")
MAX_XBRL = 8 * 1024 * 1024
LIST_DAYS = 10                  # the daily read looks this far back (late and revised filings)
BACKFILL_DAYS = 200             # the first read: about two filing seasons, so each company has two quarters
BATCH = 100                     # XBRL documents read per job tick
PAUSE = 1.0                     # seconds between documents: a steady pace for the exchange's archive
MAX_QUEUE = 8000
MAX_FOLLOWS = 20
MAX_RESULTS = 40                # name groups a search answers with
LIST_AT = "21:00"               # India time: the day's filings are listed after this
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&\-_.]{0,19}$")
NOTE = ("From each company's quarterly shareholding pattern filed with the exchange. The filing names every public "
        "shareholder above 1% and the promoter group's members; only holdings above 1% at the quarter's end are shown. "
        "Names are as filed: one holder can appear under more than one spelling. Facts, not advice.")

_cache = TTLCache(max_items=200, max_bytes=64 * 1024 * 1024)
_lock = threading.Lock()
_feed = {"fn": None}


def setup(feed_fn):
    """Where the exchange is read from: main.py's exchange client, or a test's fake."""
    _feed["fn"] = feed_fn


def forget():
    """Drop the copies in memory (between tests)."""
    _cache.clear()


def _nse(feed=None):
    feed = feed if feed is not None else (_feed["fn"]() if _feed["fn"] else None)
    if feed is None:
        raise SourceError("the exchange", "The exchange client isn't set up.")
    return getattr(feed, "nse", feed)


# ---------- names ----------
HONORIFICS = {"MR", "MRS", "MS", "DR", "SHRI", "SMT", "SH", "KUM", "KUMARI", "SMT.", "M S", "MESSRS"}
ABBREV = {"LTD": "LIMITED", "PVT": "PRIVATE", "CORP": "CORPORATION", "CO": "COMPANY", "INTL": "INTERNATIONAL", "AND": "AND"}


def norm(name: str) -> str:
    """A holder's name as a matching key: upper case, punctuation and titles dropped, common abbreviations spelled out.
    "Mr. Ashish R. Kacholia" → "ASHISH R KACHOLIA"; "HDFC Trustee Co. Ltd" → "HDFC TRUSTEE COMPANY LIMITED"."""
    s = str(name or "").upper().replace("&", " AND ")
    s = re.sub(r"\bM/S\.?", " ", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    toks = [ABBREV.get(t, t) for t in s.split() if t not in HONORIFICS]
    return " ".join(toks)[:160]


def tidy_name(name: str) -> str:
    """The name as filed, with the line breaks and doubled spaces of the XBRL text taken out."""
    return " ".join(str(name or "").split())[:160]


def alike(a: str, b: str) -> bool:
    """Two keys that probably name the same holder: the same first and last word, at least two words each
    ("ASHISH KACHOLIA" and "ASHISH RAMESHCHANDRA KACHOLIA"). Shown to the user, who can untick a spelling."""
    x, y = a.split(), b.split()
    return a == b or (len(x) >= 2 and len(y) >= 2 and x[0] == y[0] and x[-1] == y[-1])


def matches(query: str, key: str) -> bool:
    """Every word of the query starts a word of the name ("kach" finds KACHOLIA; "ashish kach" too)."""
    q = norm(query).split()
    words = key.split()
    return bool(q) and all(any(w.startswith(t) for w in words) for t in q)


# ---------- the XBRL document ----------
# the "Details of shares held by ..." axes: the kind of holder each names (promoter-group rows say so themselves)
KINDS = {
    "MutualFundsOrUTI": "Mutual fund", "InsuranceCompanies": "Insurance company",
    "ProvidentFundsOrPensionFunds": "Provident or pension fund", "AlternativeInvestmentFunds": "Alternative investment fund",
    "InstitutionsForeignPortfolioInvestorOne": "Foreign portfolio investor", "InstitutionsForeignPortfolioInvestorTwo": "Foreign portfolio investor",
    "ForeignDirectInvestment": "Foreign direct investor", "Banks": "Bank", "IndianFinancialInstitutionsOrBanks": "Bank or financial institution",
    "OtherInstitutionsDomestic": "Other institution", "OtherInstitutionsForeign": "Other institution", "ForeignInstitutions": "Foreign institution",
    "ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh": "Individual",
    "ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh": "Individual",
    "NonResidentIndians": "Non-resident Indian", "NonResidentIndividualsOrForeignIndividuals": "Foreign individual",
    "BodiesCorporate": "Company", "ForeignCompanies": "Foreign company", "DirectorsAndDirectorsRelatives": "Director or relative",
    "RelativesOfPromotersOtherThanPromoterGroup": "Promoter's relative", "IndividualsOrHUF": "Individual or HUF",
    "OthersIndianShareholders": "Company", "OtherForeignShareholders": "Foreign company", "OtherNonInstitutions": "Other",
    "CentralGovernmentOrStateGovernments": "Government", "EmployeeBenefitsTrusts": "Employee trust",
    "ShareholdingByCompaniesOrBodiesCorporateWhereCentralOrStateGovernmentIsPromoter": "Government company",
    "SovereignWealthFundsDomestic": "Sovereign wealth fund", "SovereignWealthFundsForeign": "Sovereign wealth fund",
    "ForeignGovernment": "Foreign government",
}
# not investors: shares the law parks with a fund or a suspense account, and the depository behind ADRs or GDRs
SKIP = {"InvestorEducationAndProtectionFund", "SharesWhichRemainUnclaimedForPublicShareholders", "CustodianOrDRHolder",
        "SignificantBeneficialOwners"}
SUBKIND = {"Bodies Corporate": "Company", "Overseas Corporate Bodies": "Foreign company", "HUF": "HUF", "LLP": "LLP",
           "Trusts": "Trust", "Trust": "Trust", "Partnership Firms": "Firm", "Firm": "Firm", "Societies": "Society",
           "Clearing Members": None, "Unclaimed or Suspense or Escrow Account": None, "Employees": "Employee",
           "Independent Director or his relatives": "Director or relative", "Director or Director's Relatives": "Director or relative",
           "Person Acting in Concert": "Person acting in concert", "ESOP or ESOS or ESPS": "Employee trust"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _axis_of(dimension: str) -> str:
    """"in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis" → "MutualFundsOrUTI"."""
    a = re.sub(r"Axis$", "", dimension.split(":")[-1])
    return re.sub(r"^(?:DetailsOfSharesHeldBy|DetailsSharesHeldBy|DetailsOf)", "", a)


def _number(v) -> float | None:
    try:
        x = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) < 1e15 else None


class BadFiling(ValueError):
    """The document isn't a shareholding pattern we can read."""


def parse_xbrl(data: bytes | str) -> dict:
    """A shareholding-pattern XBRL as {"symbol", "name", "isin", "quarter": "2026-06-30", "holders": [...]}: each named
    holder above 1% with its kind, "promoter" or "public", shares and percent (a percent of all shares, two places).
    A holder named twice in one filing (two accounts) is counted once, with both added up."""
    raw = data.encode() if isinstance(data, str) else bytes(data)
    head = raw[:4000].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in raw.upper():
        raise BadFiling("an XBRL document never needs a DTD")       # rules out entity-expansion tricks
    try:
        root = ElementTree.fromstring(raw)   # nosec B314: a document with a DTD is refused above
    except ElementTree.ParseError:
        raise BadFiling("not XML") from None
    axis: dict[str, str] = {}
    facts: dict[str, dict[str, str]] = {}
    for el in root:
        tag = _local(el.tag)
        if tag == "context":
            cid = el.get("id") or ""
            for m in el.iter():
                dim = m.get("dimension")
                if dim:
                    axis[cid] = _axis_of(dim)
                    break
        elif el.get("contextRef"):
            facts.setdefault(el.get("contextRef"), {})[tag] = " ".join((el.text or "").split())
    meta = {}
    for f in facts.values():
        for k in ("Symbol", "NameOfTheCompany", "ISIN", "DateOfReport", "ScripCode"):
            if f.get(k) and k not in meta:
                meta[k] = f[k]
    pcts = [_number(f.get("ShareholdingAsAPercentageOfTotalNumberOfShares")) for f in facts.values()]
    scale = 1.0 if max([p for p in pcts if p is not None] or [0]) > 1.5 else 100.0    # filed as a fraction (0.0391) or a percent
    held: dict[tuple[str, str], dict] = {}
    for cid, f in facts.items():
        name = tidy_name(f.get("NameOfTheShareholder"))
        if not name:
            continue
        inst = cid[2:] if cid.startswith("D_") else cid
        g = facts.get(inst, {})
        ax = axis.get(cid) or axis.get(inst) or ""
        if ax in SKIP or (f.get("WhetherACategoryOrMoreThan1PercentageOfShareholding") or "").lower().startswith("category"):
            continue
        promoter = "TypeOfPromoterShareholding" in f or "TypeOfPromoterShareholding" in g
        sub = f.get("CategoryOfOtherIndianShareholders") or f.get("CategoryOfOtherForeignShareholders") or f.get("CategoryOfOtherNonInstitutions") or ""
        kind = KINDS.get(ax) or re.sub(r"(?<=[a-z])(?=[A-Z])", " ", ax).capitalize() or "Other"
        if sub in SUBKIND:
            if SUBKIND[sub] is None:
                continue                      # a category's total (clearing members, a suspense account), not a holder
            kind = SUBKIND[sub]
            if ax == "OtherForeignShareholders" and kind == "Company":
                kind = "Foreign company"
        shares = _number(g.get("NumberOfShares") or f.get("NumberOfShares") or g.get("NumberOfFullyPaidUpEquityShares"))
        pct = _number(g.get("ShareholdingAsAPercentageOfTotalNumberOfShares") or f.get("ShareholdingAsAPercentageOfTotalNumberOfShares"))
        if pct is None or shares is None or shares < 0:
            continue
        key = (norm(name), "promoter" if promoter else "public")
        if not key[0]:
            continue
        h = held.setdefault(key, {"name": name, "kind": kind, "group": key[1], "shares": 0, "pct": 0.0})
        h["shares"] += int(shares)
        h["pct"] += pct * scale
    holders = [{**h, "pct": round(h["pct"], 2)} for h in held.values() if h["pct"] >= MIN_PCT - 1e-9]
    holders.sort(key=lambda h: (-h["pct"], h["name"]))
    quarter = (meta.get("DateOfReport") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", quarter):
        raise BadFiling("no quarter date")
    return {"symbol": (meta.get("Symbol") or "").upper(), "name": tidy_name(meta.get("NameOfTheCompany")),
            "isin": meta.get("ISIN") or "", "quarter": quarter, "holders": holders}


# ---------- the exchange's lists ----------
def _day(v) -> str | None:
    """"30-JUN-2026" or "17-JUL-2026 10:17:48" → "2026-06-30"."""
    try:
        return datetime.strptime(str(v or "").strip()[:11].title(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _stamp(v) -> str:
    """"17-JUL-2026 10:17:48" → "2026-07-17T10:17" (India time); "" when unreadable."""
    try:
        return datetime.strptime(str(v or "").strip().title(), "%d-%b-%Y %H:%M:%S").isoformat(timespec="minutes")
    except ValueError:
        return ""


def list_rows(data) -> list[dict]:
    """The exchange's shareholding-filing list as [{symbol, name, quarter, filed, rec, url}], one per filing with an
    XBRL document on the exchange's archive."""
    rows = data.get("data") if isinstance(data, dict) else data
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").strip().upper()
        url = str(r.get("xbrl") or "").strip()
        q = _day(r.get("date"))
        if not SYMBOL.match(sym) or not q or not _xbrl_ok(url):
            continue
        out.append({"symbol": sym, "name": tidy_name(r.get("name")) or sym, "quarter": q,
                    "filed": _stamp(r.get("broadcastDate") or r.get("systemDate")) or q, "rec": str(r.get("recordId") or url)[:40], "url": url})
    return out


def _xbrl_ok(url: str) -> bool:
    m = re.match(r"^https://([^/]+)/", url or "")
    return bool(m) and m.group(1) in XBRL_HOSTS and url.lower().endswith(".xml")


def latest_per_quarter(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """Each (company, quarter)'s newest filing: a revised filing replaces the first."""
    out: dict[tuple[str, str], dict] = {}
    for r in rows:
        k = (r["symbol"], r["quarter"])
        if k not in out or r["filed"] > out[k]["filed"]:
            out[k] = r
    return out


def read_list(nse, frm: date, to: date, symbol: str | None = None) -> list[dict]:
    """The exchange's shareholding filings broadcast between two days (or one company's every filing)."""
    params = {"index": "equities"}
    if symbol:
        params["symbol"] = symbol
    else:
        params.update(from_date=frm.strftime("%d-%m-%Y"), to_date=to.strftime("%d-%m-%Y"))
    data = nse._get(LIST_PATH, params, referer=REFERER, circuit="shp")
    if not isinstance(data, (list, dict)):
        raise SourceError("the exchange", "The exchange's shareholding list wasn't in the expected shape.")
    return list_rows(data)


def fetch_xbrl(nse, url: str) -> bytes:
    """One filing's XBRL document from the exchange's archive."""
    import httpx
    if not _xbrl_ok(url):
        raise SourceError("the exchange", "That isn't a filing on the exchange's archive.")
    try:
        r = nse.http.get(url, headers={"Accept": "application/xml,text/xml,*/*"})
    except httpx.HTTPError as e:
        raise SourceError("the exchange", f"Couldn't reach the exchange's archive ({e.__class__.__name__}).", busy=True) from None
    if r.status_code in (401, 403, 429) or r.status_code >= 500:
        raise SourceError("the exchange", f"The exchange's archive is busy ({r.status_code}). Try again later.", busy=True)
    if r.status_code >= 400:
        raise SourceError("the exchange", f"The filing isn't on the exchange's archive ({r.status_code}).")
    if len(r.content) > MAX_XBRL:
        raise SourceError("the exchange", "The filing is too large to read here.")
    return r.content


# ---------- what's stored ----------
def company(symbol: str) -> dict:
    """One company's stored quarters: {"name", "isin", "q": {quarter: {...}}} (empty "q" when none is stored)."""
    hit = _cache.get(("co", symbol))
    if hit is not None:
        return hit
    got = db.json_value(db.get_setting(KEY + symbol), {})
    out = {"name": got.get("name") or symbol, "isin": got.get("isin") or "", "q": got.get("q") if isinstance(got.get("q"), dict) else {}}
    _cache.set(("co", symbol), out, 600)
    return out


def store(symbol: str, row: dict, parsed: dict) -> tuple[dict | None, dict]:
    """Keep one filing's named holders under its quarter (the newest KEEP_QUARTERS quarters stay). Returns the quarter
    before it (None when none is stored) and the new one, for the followed-holder messages."""
    with _lock:
        co = db.json_value(db.get_setting(KEY + symbol), {})
        qs = co.get("q") if isinstance(co.get("q"), dict) else {}
        old = qs.get(row["quarter"])
        if old and old.get("filed", "") > row["filed"]:
            return None, old                                  # a newer (revised) filing is already stored
        qs[row["quarter"]] = {"rec": row["rec"], "filed": row["filed"], "url": row["url"],
                              "rows": [[h["name"], h["kind"], h["group"], h["shares"], h["pct"]] for h in parsed["holders"]]}
        keep = sorted(qs)[-KEEP_QUARTERS:]
        co = {"name": parsed.get("name") or row.get("name") or co.get("name") or symbol, "isin": parsed.get("isin") or co.get("isin") or "",
              "q": {k: qs[k] for k in keep}}
        db.set_setting(KEY + symbol, json.dumps(co, separators=(",", ":"), ensure_ascii=False))
        _cache.clear()
    before = [k for k in keep if k < row["quarter"]]
    return (co["q"][before[-1]] if before else None), co["q"].get(row["quarter"], {})


def _rows(qrow: dict | None) -> list[dict]:
    out = []
    for r in (qrow or {}).get("rows") or []:
        try:
            name, kind, group, shares, pct = r
            out.append({"name": str(name), "key": norm(name), "kind": str(kind), "group": str(group), "shares": int(shares), "pct": float(pct)})
        except (TypeError, ValueError):
            continue
    return out


def _change(now: dict | None, before: dict | None, had_before: bool) -> str | None:
    if now and before:
        d = round(now["pct"] - before["pct"], 2)
        return "up" if d > 0 or (d == 0 and now["shares"] > before["shares"]) else "down" if d < 0 or now["shares"] < before["shares"] else "same"
    if now:
        return "new" if had_before else None
    return "dropped" if before else None


def company_view(symbol: str) -> dict | None:
    """The company page's list: each named holder in the latest quarter by stake size (promoter group, then public),
    with the change since the quarter before, and the holders that dropped below 1% (or out of the list)."""
    co = company(symbol)
    qs = sorted(co["q"])
    if not qs:
        return None
    latest, prev = co["q"][qs[-1]], (co["q"][qs[-2]] if len(qs) > 1 else None)
    now_rows, before_rows = _rows(latest), _rows(prev)
    before = {(r["key"], r["group"]): r for r in before_rows}
    holders = []
    for r in now_rows:
        b = before.pop((r["key"], r["group"]), None)
        holders.append({**{k: r[k] for k in ("name", "kind", "group", "shares", "pct")}, "prev_pct": b["pct"] if b else None,
                        "prev_shares": b["shares"] if b else None, "change": _change(r, b, prev is not None),
                        "pct_change": round(r["pct"] - b["pct"], 2) if b else None})
    holders.sort(key=lambda h: (h["group"] != "promoter", -h["pct"], h["name"]))
    dropped = sorted(({"name": b["name"], "kind": b["kind"], "group": b["group"], "prev_pct": b["pct"], "prev_shares": b["shares"]}
                      for b in before.values()), key=lambda h: (-h["prev_pct"], h["name"]))
    return {"symbol": symbol, "name": co["name"], "quarter": qs[-1], "prev_quarter": qs[-2] if prev else None,
            "filed": latest.get("filed"), "url": latest.get("url"), "holders": holders, "dropped": dropped, "note": NOTE}


def ensure_company(symbol: str, nse=None) -> None:
    """Read a company's two latest quarters now when they aren't stored (its page opened before the job got to it).
    At most once every few hours per company."""
    if _cache.get(("tried", symbol)):
        return
    _cache.set(("tried", symbol), True, 6 * 3600)
    nse = _nse(nse)
    rows = sorted(latest_per_quarter(read_list(nse, date.today(), date.today(), symbol)).values(), key=lambda r: r["quarter"])[-2:]
    have = company(symbol)["q"]
    for r in rows:
        if have.get(r["quarter"], {}).get("filed", "") >= r["filed"]:
            continue
        parsed = parse_xbrl(fetch_xbrl(nse, r["url"]))
        store(symbol, r, parsed)


# ---------- the search ----------
def _index() -> dict[str, dict]:
    """Every stored company's two latest quarters, for the search: {symbol: {"name", "quarters": [prev, latest]}}."""
    hit = _cache.get("index")
    if hit is not None:
        return hit
    out = {}
    try:
        for k, raw in db.all_settings_with_prefix(KEY):
            co = db.json_value(raw, {})
            qs = co.get("q") if isinstance(co.get("q"), dict) else {}
            if qs:
                keep = sorted(qs)[-2:]
                out[k[len(KEY):]] = {"name": co.get("name") or k[len(KEY):], "q": {q: qs[q] for q in keep}}
    except Exception:
        return {}
    _cache.set("index", out, 600)
    return out


COVERAGE_KEY = "holders:coverage"
_building = threading.Lock()


def _build_behind() -> None:
    """Build the search index in a background thread (one at a time), so the next search finds it ready."""
    if not _building.acquire(blocking=False):
        return

    def work():
        try:
            coverage(wait=True)
        finally:
            _building.release()
    threading.Thread(target=work, daemon=True, name="holders-index").start()


def coverage(wait: bool = False) -> dict:
    """How much the search covers: companies read and the latest quarter among them. Opening the page with nothing
    searched read every company's stored holders to count them (13.7 s, R5O-025): without the index in memory the
    count kept from the last build answers, and the index is built behind it."""
    queued = len(db.json_value(db.get_setting(STATE_KEY), {}).get("queue") or [])
    if not wait and _cache.get("index") is None:
        kept = db.json_value(db.get_setting(COVERAGE_KEY), {})
        if kept.get("companies") is not None:
            _build_behind()
            return {"companies": kept["companies"], "latest_quarter": kept.get("latest_quarter"), "queued": queued}
    idx = _index()
    latest = [max(c["q"]) for c in idx.values() if c["q"]]
    out = {"companies": len(idx), "latest_quarter": max(latest) if latest else None}
    try:
        if db.json_value(db.get_setting(COVERAGE_KEY), {}) != out and idx:
            db.set_setting(COVERAGE_KEY, json.dumps(out))
    except Exception as e:                      # only a head start for the next cold start
        print("holders coverage:", str(e)[:120])
    return {**out, "queued": queued}


def search(query: str) -> list[dict]:
    """Name groups that match the query, alphabetical: {"label", "names": [{"key", "name", "companies"}]}. Spellings that
    look like one holder (same first and last word) are grouped; the user can untick any of them."""
    keys: dict[str, dict] = {}
    for sym, co in _index().items():
        for q in sorted(co["q"]):                      # oldest first: the name shown is the latest spelling filed
            for r in _rows(co["q"][q]):
                if matches(query, r["key"]):
                    k = keys.setdefault(r["key"], {"key": r["key"], "name": r["name"], "companies": set(), "q": ""})
                    if q >= k["q"]:
                        k["name"], k["q"] = r["name"], q
                    k["companies"].add(sym)
    groups: list[dict] = []
    for k in sorted(keys.values(), key=lambda x: x["key"]):
        g = next((g for g in groups if any(alike(k["key"], n["key"]) for n in g["names"])), None)
        if g is None:
            groups.append({"names": []})
            g = groups[-1]
        g["names"].append({"key": k["key"], "name": k["name"], "companies": len(k["companies"])})
    for g in groups:
        g["names"].sort(key=lambda n: (-n["companies"], n["key"]))
        g["label"] = g["names"][0]["name"]
        g["companies"] = len({s for n in g["names"] for s in keys[n["key"]]["companies"]})
    groups.sort(key=lambda g: g["label"].upper())
    return groups[:MAX_RESULTS]


def holdings(keys: list[str]) -> dict:
    """Every company where one of the holder's spellings appears, alphabetical by company: the latest quarter's shares
    and percent, the quarter before, and what changed ("new", "up", "down", "same", or "dropped" below 1%)."""
    want = {norm(k) for k in keys if norm(k)}
    rows = []
    for sym, co in _index().items():
        qs = sorted(co["q"])
        latest, prev = co["q"][qs[-1]], (co["q"][qs[-2]] if len(qs) > 1 else None)
        now = [r for r in _rows(latest) if r["key"] in want]
        before = [r for r in _rows(prev) if r["key"] in want]
        if not now and not before:
            continue
        def total(rs):
            if not rs:
                return None
            return {"shares": sum(r["shares"] for r in rs), "pct": round(sum(r["pct"] for r in rs), 2), "names": sorted({r["name"] for r in rs}),
                    "kind": rs[0]["kind"], "group": rs[0]["group"]}
        n, b = total(now), total(before)
        rows.append({"symbol": sym, "company": co["name"], "quarter": qs[-1], "prev_quarter": qs[-2] if prev else None,
                     "filed": latest.get("filed"), "url": latest.get("url"),
                     "names": (n or b)["names"], "kind": (n or b)["kind"], "group": (n or b)["group"],
                     "shares": n["shares"] if n else None, "pct": n["pct"] if n else None,
                     "prev_shares": b["shares"] if b else None, "prev_pct": b["pct"] if b else None,
                     "change": _change(n, b, prev is not None), "pct_change": round(n["pct"] - b["pct"], 2) if n and b else None})
    rows.sort(key=lambda r: r["company"].upper())
    held = [r for r in rows if r["pct"] is not None]
    return {"rows": rows, "count": len(held), "dropped": sum(1 for r in rows if r["change"] == "dropped"),
            "new": sum(1 for r in rows if r["change"] == "new"), "keys": sorted(want)}


# ---------- following a holder ----------
def follows(uid: str) -> list[dict]:
    got = db.json_value(db.get_setting(FOLLOW_KEY + uid), {})
    return [i for i in got.get("items") or [] if isinstance(i, dict) and i.get("id") and i.get("names")]


def _save_follows(uid: str, items: list[dict]):
    db.set_setting(FOLLOW_KEY + uid, json.dumps({"uid": uid, "items": items}, separators=(",", ":"), ensure_ascii=False))


def follow(uid: str, label: str, names: list[str]) -> dict:
    keys = sorted({norm(n) for n in names if norm(n)})[:12]
    if not keys:
        raise ValueError("Pick at least one name to follow.")
    items = follows(uid)
    same = next((i for i in items if i.get("names") == keys), None)
    if same:
        same["label"] = tidy_name(label)[:80] or same["label"]
    else:
        if len(items) >= MAX_FOLLOWS:
            raise ValueError(f"You can follow up to {MAX_FOLLOWS} holders. Unfollow one first.")
        import secrets
        same = {"id": secrets.token_hex(5), "label": tidy_name(label)[:80] or keys[0].title(), "names": keys,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        items.append(same)
    _save_follows(uid, items)
    return same


def unfollow(uid: str, fid: str) -> bool:
    items = follows(uid)
    left = [i for i in items if i.get("id") != fid]
    if len(left) == len(items):
        return False
    _save_follows(uid, left)
    return True


def change_line(label: str, company_name: str, symbol: str, before: dict | None, now: dict | None, quarter: str) -> str | None:
    """One followed holder's change in one company, in words: "new in Safari Industries (SAFARI) at 1.84%"."""
    q = _quarter_words(quarter)
    if now and not before:
        return f"{label}: new in {company_name} ({symbol}) at {now['pct']:.2f}% ({q})"
    if before and not now:
        return f"{label}: no longer listed above 1% in {company_name} ({symbol}), was {before['pct']:.2f}% ({q})"
    if now and before and (now["shares"] != before["shares"] or abs(now["pct"] - before["pct"]) >= 0.01):
        way = "up" if now["shares"] > before["shares"] or now["pct"] > before["pct"] else "down"
        return f"{label}: {way} in {company_name} ({symbol}) from {before['pct']:.2f}% to {now['pct']:.2f}% ({q})"
    return None


def _quarter_words(q: str) -> str:
    try:
        return "quarter to " + date.fromisoformat(q).strftime("%-d %b %Y")
    except ValueError:
        return q


def follow_changes(symbol: str, company_name: str, before_q: dict | None, now_q: dict, quarter: str) -> dict[str, list[str]]:
    """{uid: [lines]} for the users following a holder whose entry in this company changed between two quarters."""
    if before_q is None:
        return {}
    b_rows, n_rows = _rows(before_q), _rows(now_q)
    out: dict[str, list[str]] = {}
    for k, raw in db.all_settings_with_prefix(FOLLOW_KEY):
        row = db.json_value(raw, {})
        uid = row.get("uid") or k[len(FOLLOW_KEY):]
        for f in row.get("items") or []:
            keys = set(f.get("names") or [])
            def total(rs):
                hit = [r for r in rs if r["key"] in keys]
                return {"shares": sum(r["shares"] for r in hit), "pct": round(sum(r["pct"] for r in hit), 2)} if hit else None
            line = change_line(f.get("label") or "A holder you follow", company_name, symbol, total(b_rows), total(n_rows), quarter)
            if line:
                out.setdefault(uid, []).append(line)
    return out


def message(lines: list[str]) -> str:
    more = f"; and {len(lines) - 6} more" if len(lines) > 6 else ""
    return ("Holders you follow, from new shareholding filings: " + "; ".join(lines[:6]) + more +
            ". Holdings above 1% at the quarter's end, as filed. Not advice.")


# ---------- the job ----------
def _state() -> dict:
    return db.json_value(db.get_setting(STATE_KEY), {})


def _save_state(st: dict):
    st["queue"] = (st.get("queue") or [])[:MAX_QUEUE]
    db.set_setting(STATE_KEY, json.dumps(st, separators=(",", ":")))


def enqueue(rows: list[dict], st: dict, per_company: int | None = None) -> int:
    """Add the filings not stored yet (each company's newest `per_company` quarters when given), newest first."""
    best = latest_per_quarter(rows)
    if per_company:
        by: dict[str, list] = {}
        for (sym, q), r in best.items():
            by.setdefault(sym, []).append(r)
        best = {(r["symbol"], r["quarter"]): r for rs in by.values() for r in sorted(rs, key=lambda r: r["quarter"])[-per_company:]}
    queued = {(x[0], x[1]): x for x in st.get("queue") or []}
    added = 0
    for (sym, q), r in best.items():
        have = company(sym)["q"].get(q)
        if have and have.get("filed", "") >= r["filed"]:
            continue
        old = queued.get((sym, q))
        if old and old[4] >= r["filed"]:
            continue
        queued[(sym, q)] = [sym, q, r["rec"], r["url"], r["filed"], r["name"]]
        added += 1
    st["queue"] = sorted(queued.values(), key=lambda x: (x[1], x[4]), reverse=True)
    return added


class Job:
    """Every five minutes: once a day (evening) read the exchange's list of shareholding filings for the last few days;
    the first time, about two filing seasons back. Then read up to BATCH queued XBRL documents, store each company's
    named holders, and tell followers of a holder whose entry changed (not during the first fill)."""

    def __init__(self, feed_fn, notify, can_alert, sleep=time.sleep):
        self.feed_fn, self.notify, self.can_alert, self.sleep = feed_fn, notify, can_alert, sleep
        self.status = {"last_run": None, "read": 0, "queued": 0, "sent": 0, "last_error": None, "listed": None}
        self.last_list = None

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="named-holders").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("named holders:", e)
            time.sleep(300)

    def list_due(self, now: datetime) -> date | None:
        from zoneinfo import ZoneInfo
        local = now.astimezone(ZoneInfo("Asia/Kolkata"))
        st = _state()
        if not st.get("backfilled"):
            return local.date()
        if local.strftime("%H:%M") < LIST_AT or st.get("listed_to") == local.date().isoformat() or self.last_list == local.date():
            return None
        return local.date()

    def refresh_list(self, today: date) -> int:
        nse = _nse(self.feed_fn())
        st = _state()
        added = 0
        if not st.get("backfilled"):
            to = today
            rows: list[dict] = []
            while to > today - timedelta(days=BACKFILL_DAYS):
                frm = max(to - timedelta(days=30), today - timedelta(days=BACKFILL_DAYS))
                rows += read_list(nse, frm, to)
                to = frm - timedelta(days=1)
                self.sleep(PAUSE)
            added = enqueue(rows, st, per_company=2)
            st["backfilled"] = True
            st["filling"] = True                 # the first fill: no messages until its queue is read
        else:
            added = enqueue(read_list(nse, today - timedelta(days=LIST_DAYS), today), st)
        st["listed_to"] = today.isoformat()
        _save_state(st)
        self.last_list = today
        self.status.update(listed=today.isoformat(), queued=len(st["queue"]))
        return added

    def read_queue(self, limit: int = BATCH) -> int:
        st = _state()
        queue = st.get("queue") or []
        if not queue:
            if st.get("filling"):
                st["filling"] = False
                _save_state(st)
            return 0
        nse = _nse(self.feed_fn())
        quiet = bool(st.get("filling"))
        done, sent, msgs = 0, 0, {}
        for item in list(queue[:limit]):
            sym, q, rec, url, filed, name = item
            try:
                parsed = parse_xbrl(fetch_xbrl(nse, url))
            except SourceError as e:
                if e.busy:
                    self.status["last_error"] = str(e)[:200]
                    break                        # the archive is turning us away: the rest wait for the next tick
                parsed = None
            except BadFiling:
                parsed = None
            queue.remove(item)
            done += 1
            if parsed is not None and (not parsed["symbol"] or parsed["symbol"] == sym):
                before, now = store(sym, {"symbol": sym, "quarter": q, "rec": rec, "url": url, "filed": filed, "name": name}, parsed)
                if not quiet:
                    for uid, lines in follow_changes(sym, parsed.get("name") or name, before, now, q).items():
                        msgs.setdefault(uid, []).extend(lines)
            self.sleep(PAUSE)
        st["queue"] = queue
        _save_state(st)
        for uid, lines in msgs.items():
            try:
                p = db.cached_profile(uid)
            except Exception:
                continue
            if self.can_alert(p):
                self.notify(p, "StratLab: holders you follow", message(lines), "/invest/holders")
                sent += 1
        self.status.update(read=self.status["read"] + done, queued=len(queue), sent=self.status["sent"] + sent)
        return done

    def tick(self, now: datetime) -> int:
        day = self.list_due(now)
        if day:
            self.refresh_list(day)
        n = self.read_queue()
        self.status.update(last_run=now.isoformat(timespec="minutes"), last_error=None if n or not day else self.status["last_error"])
        return n


# ---------- the routes ----------
router = APIRouter(tags=["invest"])


def _allowed(profile: dict) -> bool:
    return allows(plan_of(profile), "holders")


def _need(profile: dict, what: str):
    if not _allowed(profile):
        err(402, "upgrade_required", f"{what} is on the {PLANS[FEATURE_PLAN['holders']]['name']} plan.")


@router.get("/research/holders/{symbol}")
def named_holders(symbol: str, profile=Depends(current_profile)):
    """One Indian company's named holders above 1% in its latest shareholding pattern, with the change since the
    quarter before. For everyone: searching a holder across companies and following one is the paid part."""
    sym = str(symbol or "").strip().upper()
    if not SYMBOL.match(sym):
        err(400, "bad_symbol", "That doesn't look like a ticker.")
    problem = None
    try:
        ensure_company(sym)
    except (SourceError, BadFiling) as e:
        problem = str(e)
    got = company_view(sym)
    if got is None:
        if problem:
            err(503, "holders_unavailable", f"The shareholding filing couldn't be read just now ({problem}). Try again later.")
        # nothing filed (or not listed on NSE) is an answer, not a fault: an empty 200 the page leaves out quietly
        return ok({"symbol": sym, "available": False, "holders": [], "dropped": [], "search": _allowed(profile),
                   "message": f"No shareholding filing found for {sym} on the exchange."})
    return ok({**got, "available": True, "search": _allowed(profile)})


@router.get("/invest/holders")
def holder_search(q: str = "", profile=Depends(current_profile)):
    """Search named holders across every company read, by name. Basic and up."""
    _need(profile, "Searching named holders across companies")
    q = q.strip()[:80]
    if q and len(norm(q).replace(" ", "")) < 3:
        err(400, "short_query", "Type at least three letters of the holder's name.")
    return ok({"q": q, "groups": search(q) if q else [], "coverage": coverage(), "follows": follows(profile["id"]), "note": NOTE})


class HoldingsReq(BaseModel):
    names: list[str] = Field(min_length=1, max_length=12)


@router.post("/invest/holders/holdings")
def holder_holdings(req: HoldingsReq, profile=Depends(current_profile)):
    """Every company where the chosen spellings of a holder appear, alphabetical, with the quarter-on-quarter change."""
    _need(profile, "Searching named holders across companies")
    names = [n for n in req.names if isinstance(n, str) and norm(n)]
    if not names:
        err(400, "no_names", "Pick at least one name.")
    return ok({**holdings(names), "coverage": coverage(), "note": NOTE})


class FollowReq(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    names: list[str] = Field(min_length=1, max_length=12)


@router.put("/invest/holders/follow")
def holder_follow(req: FollowReq, profile=Depends(current_profile)):
    """Follow a holder (the spellings ticked): a message when a new quarter's filing changes their list."""
    _need(profile, "Following a holder")
    try:
        item = follow(profile["id"], req.label, req.names)
    except ValueError as e:
        err(400, "bad_follow", str(e))
    return ok({"item": item, "follows": follows(profile["id"])})


@router.delete("/invest/holders/follow/{fid}")
def holder_unfollow(fid: str, profile=Depends(current_profile)):
    if not re.fullmatch(r"[0-9a-f]{6,20}", fid or ""):
        err(404, "not_found", "That holder isn't followed.")
    if not unfollow(profile["id"], fid):
        err(404, "not_found", "That holder isn't followed.")
    return ok({"follows": follows(profile["id"])})
