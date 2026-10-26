"""The pages' side of redflags.py: red-flag filings across every company, and US holders above 5% (13D and 13G)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from . import redflags, results, scan
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows, plan_of
from .responses import err, ok

router = APIRouter(tags=["research"])
NOTE = {
    "IN": "From the companies' own filings with the exchange. Labels come from fixed keyword rules on each filing's subject; "
          "a label is a reason to read the filing, not a verdict on the company. Not advice.",
    "US": "From the Form 8-K items companies file with the SEC: the item number is the company's own, and the label names that item. "
          "An item is a reason to read the filing, not a verdict on the company. Not advice.",
}


def _need(profile: dict, feature: str, what: str):
    if not allows(plan_of(profile), feature):
        err(402, "upgrade_required", f"{what} is on the {PLANS[FEATURE_PLAN[feature]]['name']} plan.")


@router.get("/research/redflags")
def red_flags(region: str = "IN", scope: str = "all", flag: str = "", frm: str = "", to: str = "", q: str = "", page: int = 1,
              size: int = redflags.PAGE, profile=Depends(current_profile)):
    """The latest red-flag filings across every company (`scope=all`) or the user's own stocks (`mine`), newest first,
    paged, with the type and date filters. Stored daily; nothing is fetched from a source here. Basic and up."""
    region = "US" if region.upper() == "US" else "IN"
    _need(profile, "filings", "Red flags across companies")
    mine = None
    if scope == "mine":
        # "your stocks", as the results and corporate-actions pages count them: watchlist, holdings, notebooks and paper
        # sessions, in both markets (DE-036: India's tab said "Your stocks", the US one "Your watchlist")
        mine = set(results.my_stocks(profile["id"], region)) | {m["symbol"] for m in scan.watchlist_members(profile["id"], region)}
    out = redflags.listing(region, flag[:200], frm[:10], to[:10], page, size, q, mine)
    return ok({**out, "scope": "mine" if scope == "mine" else "all", "note": NOTE[region], "watchlist": None if mine is None else len(mine)})


@router.get("/research/holders-us")
def us_holders_list(symbol: str = "", form: str = "", page: int = 1, size: int = redflags.PAGE, holder: str = "", profile=Depends(current_profile)):
    """US holders above 5%: the Schedule 13D and 13G filings of one company (any plan) or of every S&P 500 company
    (Basic and up), newest first, with the holder's name and share of the class as the cover page gives them. `holder`
    finds one holder's filings across companies (DF-018), Basic and up as the cross-company list is."""
    if not symbol.strip() or holder.strip():
        _need(profile, "holders", "The latest 13D and 13G filings across companies")
    out = redflags.holders_listing(symbol, form, page, size, holder=holder)
    return ok({**out, "note": "Filed by anyone holding more than 5% of a company's shares: a 13D when the stake is active, a 13G when it is passive, "
                              "and an amendment when it changes. Names and percentages are as the filer's cover page states them. Not advice."})


@router.get("/research/us-company/{symbol}")
def us_company_filings(symbol: str, profile=Depends(current_profile)):
    """What a US company's page shows of its SEC filings, from the stored reads (nothing is fetched here), free on every plan as India's company
    filings are: the Form 8-K items flagged over the last year, and the holders above 5% from the Schedule 13D and 13G filings (RC2A-027: a US
    company's page had no owners, filings or red flags section)."""
    sym = "".join(ch for ch in (symbol or "").upper() if ch.isalnum() or ch in "-.")[:12].replace(".", "-")
    if not sym:
        err(404, "not_found", "That company isn't on the list.")
    today = datetime.now(ZoneInfo("America/New_York")).date()
    flags = redflags.listing("US", "", (today - timedelta(days=365)).isoformat(), today.isoformat(), 1, 25, "", {sym})
    holders = redflags.holders_listing(sym, "", 1, 12)
    return ok({"symbol": sym,
               "flags": {k: flags[k] for k in ("items", "total", "from", "to", "as_of", "updated_at", "covers")},
               "holders": {k: holders[k] for k in ("items", "total", "as_of", "updated_at", "newest", "unread", "covers")},
               "note": NOTE["US"]})
