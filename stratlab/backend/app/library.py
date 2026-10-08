"""The public strategy library: rules people publish together with their honest verdict.

An entry is published from one experiment, so it carries the exact rules that were tested and the
verdict they earned. "Probably luck" and "No edge here" are listed as plainly as "Likely a real edge".
Nothing personal is shown: only an optional name the author types. Others copy the rules into their own
notebook and run them fresh. Entries live in app_settings under "lib:<id>" (no extra table needed)."""
import json
import re
import secrets
from datetime import datetime, timezone

from . import db

PREFIX = "lib:"
ID = re.compile(r"^[A-Za-z0-9_-]{6,24}$")
RANK = {"edge": 0, "mixed": 1, "not_enough": 2, "luck": 3, "no_edge": 4}
REASONS = {"spam": "Spam or advertising", "offensive": "Offensive or abusive", "misleading": "Misleading or a scam",
           "personal": "Shares someone's personal details", "other": "Something else"}
HIDE_AFTER = 3          # reports from different people before an entry is hidden until the owner of the site looks
MODERATION = ("reports", "hidden", "hidden_by")


def _unseen(exp: dict) -> float | None:
    for c in (exp.get("verdict") or {}).get("checks") or []:
        if c.get("id") == "unseen" and c.get("status") != "skip":
            got = (c.get("data") or {}).get("unseen_ret")
            return got or None            # exactly 0 is no trade at all in the unseen years: no result, not "0.0%"
    return None


def entry(nb: dict, exp: dict, owner: str, author: str, description: str, entry_id: str | None = None) -> dict:
    v = exp.get("verdict") or {}
    st = exp.get("stats") or {}
    inst = exp.get("instrument") or {}
    g = exp.get("group")
    ngroup = nb.get("group")
    return {
        "id": entry_id or secrets.token_urlsafe(8),
        "name": nb.get("name") or "Untitled", "question": nb.get("question") or "", "description": description.strip(),
        "author": author.strip() or "A StratLab user",
        "market": inst.get("market") or (ngroup or {}).get("market") or "IN",
        "instrument": None if g else {k: inst.get(k) for k in ("id", "symbol", "name", "market", "currency")},
        "group": None if not ngroup else {k: ngroup.get(k) for k in ("id", "name", "market", "maxOpen", "members")},
        "tf": exp.get("tf"), "side": (exp.get("strategy") or {}).get("side", "long"),
        "range": exp.get("range"), "strategy": exp.get("strategy"),
        "verdict": {**{k: v.get(k) for k in ("verdict", "headline", "summary", "passed", "total")},
                    "checks": [{"id": c.get("id"), "status": c.get("status")} for c in v.get("checks") or [] if isinstance(c, dict)]},
        "stats": {"ret": st.get("ret"), "buy_hold": st.get("buy_hold_ret"), "mdd": st.get("mdd"), "trades": st.get("n"), "unseen": _unseen(exp)},
        "published_at": datetime.now(timezone.utc).isoformat(), "copies": 0,
        "owner": owner, "source": {"nid": nb.get("id"), "v": exp.get("v")},
    }


CHECK_NAME = {"unseen": "unseen years", "nearby": "nearby settings", "shuffle": "bad-luck fall", "sample": "enough trades"}
MIN_TRADES = 15          # the verdict's own floor: fewer trades than this is "not enough evidence"


def ran(e: dict) -> bool:
    """Whether the experiment traded at all. One that didn't has no return, fall or unseen result to show: those are
    "not run", not 0.0%."""
    n = (e.get("stats") or {}).get("trades")
    return n is None or n > 0


def reason(e: dict) -> str | None:
    """One line for why the verdict is what it is, from the verdict's own facts: the trade count, and which of its
    checks passed, failed or weren't run."""
    v, st = e.get("verdict") or {}, e.get("stats") or {}
    n = st.get("trades")
    if n is not None and n < MIN_TRADES:
        return "No trades in this period, so nothing was tested." if n == 0 else f"Only {n} trade{'s' if n != 1 else ''} in this period, too few to tell skill from luck."
    if v.get("verdict") == "no_edge" and (st.get("ret") or 0) <= 0:
        return "Lost money after costs over the period, so there was no edge to test."
    checks = [c for c in v.get("checks") or [] if c.get("id") in CHECK_NAME]
    if not checks:
        return None
    groups: dict[str, list[str]] = {"pass": [], "fail": [], "skip": []}
    for c in checks:
        groups[c.get("status") if c.get("status") in groups else "fail"].append(CHECK_NAME[c["id"]])
    parts = [f"{label}: {', '.join(groups[k])}" for k, label in (("pass", "Passed"), ("fail", "Failed"), ("skip", "Not run")) if groups[k]]
    return ". ".join(parts) + "."


def public(e: dict, viewer: str | None = None) -> dict:
    """What anyone sees: everything but the owner's id and who reported it (flags say whether it's yours)."""
    out = {k: v for k, v in e.items() if k not in ("owner", "source") + MODERATION}
    out["ran"], out["reason"] = ran(e), reason(e)
    out["mine"] = bool(viewer and e.get("owner") == viewer)
    out["reported"] = bool(viewer and viewer in (e.get("reports") or {}))
    if out["mine"] and e.get("hidden"):
        out["hidden"] = True   # the author is told it's hidden, not who reported it
    return out


OFFICIAL_OWNER = "stratlab"        # the owner id of the entries StratLab publishes itself (library_seed.py)
PUBLIC_HIDDEN = ("seed",)          # StratLab's own bookkeeping on its entries, not for visitors


def is_public(e: dict) -> bool:
    """Whether a visitor without an account may read this entry: only StratLab's own (made by the app's own backtest and
    verdict, published as StratLab), and not hidden. A user's entry is never public here, however it was published."""
    return bool(e.get("official")) and e.get("owner") == OFFICIAL_OWNER and not e.get("hidden")


def public_view(e: dict) -> dict:
    """An official entry as a visitor sees it: what `public` shows signed-in people, read only, nothing about a viewer."""
    out = public(e)
    for k in PUBLIC_HIDDEN:
        out.pop(k, None)
    out.pop("mine", None)
    out.pop("reported", None)
    out.pop("hidden", None)
    return out


def visible(e: dict, viewer: str | None = None) -> bool:
    return not e.get("hidden") or bool(viewer and e.get("owner") == viewer)


def report(e: dict, viewer: str, reason: str) -> dict:
    """One report per person; enough of them hides the entry until it's reviewed."""
    reports = dict(e.get("reports") or {})
    reports[viewer] = {"reason": reason if reason in REASONS else "other", "at": datetime.now(timezone.utc).isoformat()}
    e = {**e, "reports": reports}
    if len(reports) >= HIDE_AFTER and not e.get("hidden"):
        e["hidden"], e["hidden_by"] = True, "reports"
    return e


def moderate(e: dict, action: str) -> dict:
    """The site owner's decision: hide it, or restore it (which clears the reports)."""
    if action == "hide":
        return {**e, "hidden": True, "hidden_by": "admin"}
    return {**{k: v for k, v in e.items() if k not in MODERATION}, "reports": {}}


def carry_moderation(old: dict | None, new: dict) -> dict:
    """Publishing again keeps the reports and any hiding: re-publishing can't be used to clear them."""
    if old:
        new.update({k: old[k] for k in MODERATION if k in old})
    return new


def save(e: dict):
    db.set_setting(PREFIX + e["id"], json.dumps(e))


def load(eid: str) -> dict | None:
    if not ID.match(eid or ""):
        return None
    raw = db.get_setting(PREFIX + eid)
    return json.loads(raw) if raw else None


def remove(eid: str):
    if ID.match(eid or ""):
        db.delete_setting(PREFIX + eid)


def all_entries() -> list[dict]:
    out = []
    for raw in db.settings_with_prefix(PREFIX):
        try:
            out.append(json.loads(raw))
        except (TypeError, ValueError):
            continue
    return out


def search(entries: list[dict], market: str = "", verdict: str = "", q: str = "", sort: str = "best") -> list[dict]:
    words = [w for w in q.lower().split() if w]
    rows = [e for e in entries
            if (not market or e.get("market") == market)
            and (not verdict or (e.get("verdict") or {}).get("verdict") == verdict)
            and all(w in " ".join([e.get("name", ""), e.get("description", ""), e.get("question", ""),
                                   (e.get("instrument") or {}).get("symbol") or "", (e.get("group") or {}).get("name") or ""]).lower()
                    for w in words)]
    if sort == "new":
        rows.sort(key=lambda e: e.get("published_at") or "", reverse=True)
    elif sort == "copied":
        rows.sort(key=lambda e: (-(e.get("copies") or 0), e.get("published_at") or ""))
    else:   # best: the strongest verdicts first, then what held up on unseen data
        rows.sort(key=lambda e: (RANK.get((e.get("verdict") or {}).get("verdict"), 9),
                                 -((e.get("stats") or {}).get("unseen") or -1e9), -((e.get("stats") or {}).get("ret") or -1e9)))
    rows.sort(key=lambda e: not ran(e))          # strategies that never traded have no evidence: below the rest, whatever the sort
    return rows
