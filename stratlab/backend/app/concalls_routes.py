"""The pages' side of concalls.py (the Calendar's "Earnings calls" tab) and groups.py (Invest's business groups)."""
from fastapi import APIRouter, Depends

from . import concalls, groups, results, scan
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows, plan_of
from .responses import err, ok

router = APIRouter(tags=["research"])


def _mine(uid: str, region: str) -> set[str]:
    """The person's stocks as the other calendar tabs count them: holdings, watchlist, notebooks and paper sessions."""
    return set(results.my_stocks(uid, region)) | {m["symbol"] for m in scan.watchlist_members(uid, region)}


@router.get("/research/earnings-calls")
def earnings_calls(region: str = "IN", scope: str = "all", when: str = "upcoming", kind: str = "all", q: str = "",
                   profile=Depends(current_profile)):
    """Upcoming (or the last three weeks') earnings calls and meetings with analysts or investors, India from the companies'
    filings and the US from the results calendar, for every company or the person's own stocks. Stored; nothing is
    fetched from a source here. This week's calls, with their notice and webcast or dial-in link, on every plan; the full
    calendar (every week ahead, the calls held and what was filed after them, the filters) on earnings_calls' plan."""
    region = "US" if region.upper() == "US" else "IN"
    if when not in ("upcoming", "past"):
        err(400, "bad_when", "Pick coming up or held.")
    if kind not in ("all", "call", "meet"):
        err(400, "bad_kind", "Pick earnings calls, analyst meets or both.")
    full = allows(plan_of(profile), "earnings_calls")
    if not full and (scope == "mine" or when == "past" or kind != "all" or q.strip()):
        err(402, "upgrade_required", f"The full earnings-call calendar (calls held, transcripts, filters and your stocks) is on the "
                                     f"{PLANS[FEATURE_PLAN['earnings_calls']]['name']} plan.")
    mine = _mine(profile["id"], region)
    return ok({**concalls.view(region, "mine" if scope == "mine" else "all", mine, when, kind, q[:60], full=full), "mine_count": len(mine),
               "plan_needed": None if full else PLANS[FEATURE_PLAN["earnings_calls"]]["name"]})


@router.get("/invest/groups")
def business_groups(profile=Depends(current_profile)):
    """India's business groups that the promoters named in the companies' shareholding filings make out (groups.py),
    each with its listed companies' combined market value and the day's move; the longer moves on group_figures' plan."""
    full = allows(plan_of(profile), "group_figures")
    return ok({**groups.index_view(full), "plan_needed": None if full else PLANS[FEATURE_PLAN["group_figures"]]["name"]})


@router.get("/invest/groups/of/{symbol}")
def group_of(symbol: str, profile=Depends(current_profile)):
    """The business group a company belongs to, for a link on its page; {"group": None} when it is in none."""
    return ok({"group": groups.group_of(symbol.upper()[:20])})


@router.get("/invest/groups/{slug}")
def business_group(slug: str, profile=Depends(current_profile)):
    """One business group: its listed companies with their last close, moves, market value and promoter holding, and
    the promoter names that tie them together. The members, their market value and the day's change on every plan; the
    longer changes, the promoter holding and the members' heatmap on group_figures' plan."""
    full = allows(plan_of(profile), "group_figures")
    got = groups.group_view(slug[:60], full)
    if got is None:
        err(404, "not_found", "That business group isn't one the shareholding filings make out.")
    return ok({**got, "plan_needed": None if full else PLANS[FEATURE_PLAN["group_figures"]]["name"]})
