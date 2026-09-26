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
            return (c.get("data") or {}).get("unseen_ret")
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
        "verdict": {k: v.get(k) for k in ("verdict", "headline", "summary", "passed", "total")},
        "stats": {"ret": st.get("ret"), "buy_hold": st.get("buy_hold_ret"), "mdd": st.get("mdd"), "trades": st.get("n"), "unseen": _unseen(exp)},
        "published_at": datetime.now(timezone.utc).isoformat(), "copies": 0,
        "owner": owner, "source": {"nid": nb.get("id"), "v": exp.get("v")},
    }


def public(e: dict, viewer: str | None = None) -> dict:
    """What anyone sees: everything but the owner's id and who reported it (flags say whether it's yours)."""
    out = {k: v for k, v in e.items() if k not in ("owner", "source") + MODERATION}
    out["mine"] = bool(viewer and e.get("owner") == viewer)
    out["reported"] = bool(viewer and viewer in (e.get("reports") or {}))
    if out["mine"] and e.get("hidden"):
        out["hidden"] = True   # the author is told it's hidden, not who reported it
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
    return rows
