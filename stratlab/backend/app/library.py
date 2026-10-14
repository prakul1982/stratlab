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


def _group_of(nb: dict, exp: dict) -> dict | None:
    """The group an experiment ran on, from the experiment itself. The notebook's group is used only when it is that
    same group; the notebook may have been switched since."""
    inst = exp.get("instrument") or {}
    g = exp.get("group")
    if not g and inst.get("type") != "GROUP":
        return None
    ng = nb.get("group") or {}
    if ng and inst.get("id") == f"GROUP:{ng.get('id')}":
        return ng
    members = [{k: m[k] for k in ("id", "symbol") if m.get(k)} for m in (g or {}).get("members") or []]
    return {"id": str(inst.get("id") or "GROUP:custom")[6:] or "custom", "name": (g or {}).get("name") or inst.get("name"),
            "market": inst.get("market"), "maxOpen": (g or {}).get("max_open"), "members": members}


def entry(nb: dict, exp: dict, owner: str, author: str, description: str, entry_id: str | None = None) -> dict:
    from .engine.verdict import restate_empty
    exp = restate_empty(exp)                 # a run saved before accounts stopped at zero is published with its account held to what it had
    v = exp.get("verdict") or {}
    st = exp.get("stats") or {}
    inst = exp.get("instrument") or {}
    ngroup = _group_of(nb, exp)
    return {
        "id": entry_id or secrets.token_urlsafe(8),
        "name": nb.get("name") or "Untitled", "question": nb.get("question") or "", "description": description.strip(),
        "author": author.strip() or "A StratLab user",
        "market": inst.get("market") or (ngroup or {}).get("market") or "IN",
        "instrument": None if ngroup else {k: inst.get(k) for k in ("id", "symbol", "name", "market", "currency")},
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


def versus_hold(e: dict) -> dict | None:
    """The return after costs beside buying and holding over the same period, as the notebook's verdict states it
    (R5O-014): {ret, hold, gap} in percent, `gap` negative when the rules trail buy and hold. None when either is
    missing or the rules never traded."""
    st = e.get("stats") or {}
    r, h = st.get("ret"), st.get("buy_hold")
    if not ran(e) or not isinstance(r, (int, float)) or not isinstance(h, (int, float)):
        return None
    return {"ret": round(r, 2), "hold": round(h, 2), "gap": round(r - h, 2)}


CHECK_IDS = ("unseen", "nearby", "shuffle", "sample")


def checks_of(e: dict) -> list[dict]:
    """The four checks with their result: as stored with the verdict, or, for an entry published before the checks were
    kept, worked out from what it does keep (the unseen years' return, the trade count, how many passed, and that the
    nearby-settings check is never run on a group). A result that can't be told apart (failed or only a warning) is
    "not_passed". [{"id", "status"}] in the checks' order."""
    v, st = e.get("verdict") or {}, e.get("stats") or {}
    stored = {c.get("id"): c.get("status") for c in v.get("checks") or [] if isinstance(c, dict) and c.get("id") in CHECK_IDS}
    if len(stored) == len(CHECK_IDS):
        return [{"id": k, "status": stored[k]} for k in CHECK_IDS]
    if not isinstance(v.get("passed"), int) or not isinstance(v.get("total"), int):
        return [{"id": k, "status": stored[k]} for k in CHECK_IDS if k in stored]      # too little kept to tell
    n, unseen = st.get("trades"), st.get("unseen")
    got: dict[str, str] = dict(stored)
    if e.get("group") and "nearby" not in got:
        got["nearby"] = "skip"                         # never run on a group of instruments (verdict.evaluate_portfolio)
    if "unseen" not in got:
        got["unseen"] = "warn" if not isinstance(unseen, (int, float)) else "pass" if unseen > 0 else "fail"
    if "sample" not in got and isinstance(n, int):
        got["sample"] = "pass" if n >= 30 else "warn" if n >= 15 else "fail"
    if "shuffle" not in got and isinstance(n, int) and n < 5:
        got["shuffle"] = "skip"
    left = [k for k in CHECK_IDS if k not in got]
    passes = max(0, int(v.get("passed") or 0) - sum(1 for s in got.values() if s == "pass"))
    for k in left:                                     # the passes not yet placed go to the checks still unknown
        if passes:
            got[k], passes = "pass", passes - 1
        elif k == "shuffle" and v.get("verdict") == "edge":
            got[k] = "warn"                            # an edge never has a failed bad-luck check
        else:
            got[k] = "not_passed"
    return [{"id": k, "status": got[k]} for k in CHECK_IDS]


def _pc(x: float) -> str:
    s = f"{abs(x):.1f}"
    return ("" if float(s) == 0 else "+" if x > 0 else "−") + s + "%"


def label(e: dict) -> str:
    """The verdict as a fact about the checks, the same words on the library card and the strategy's own page (R6V-005):
    no claim for a check that wasn't run."""
    v = (e.get("verdict") or {}).get("verdict")
    if v == "edge":
        checks = checks_of(e)
        run = [c for c in checks if c["status"] != "skip"]
        passed = sum(1 for c in run if c["status"] == "pass")
        if not run:
            return "Passed the checks"
        if passed == len(CHECK_IDS):
            return "Passed all four checks"
        return f"Passed {passed} of the {len(run)} checks run" if passed < len(run) else f"Passed all {len(run)} checks run"
    if v == "luck":
        by = {c["id"]: c["status"] for c in checks_of(e)}
        if by.get("unseen") == "fail":
            return "Lost money on the unseen years"
        if by.get("nearby") == "fail":
            return "Failed the nearby-settings check"
    return {"mixed": "Mixed check results", "luck": "Failed a robustness check", "not_enough": "Too few trades",
            "no_edge": "Lost money after costs"}.get(v or "", "Not tested")


def restated(e: dict) -> dict:
    """The verdict's headline and summary from its own facts, so a stored entry never claims more than its checks
    showed (an entry published before this said "doesn't depend on one exact setting" with that check not run):
    the comparison with buy and hold in the headline as well as the label, then one sentence per check."""
    v, st = dict(e.get("verdict") or {}), e.get("stats") or {}
    hold = versus_hold(e)
    lab = label(e)
    head = lab
    if hold:
        rel = ("about the same as" if abs(hold["gap"]) < 0.05 else "less than" if hold["gap"] < 0 else "more than")
        head = f"{lab}, and returned {rel} buy and hold"
        if hold["gap"] <= -1:
            # behind buy and hold: the shortfall leads, before any check it passed (R6V-005: "Passed all 3 checks run"
            # above "+55.8% vs +172.9%, 117.1 points behind")
            head = f"{abs(hold['gap']):.1f} points behind buy and hold after costs; {lab[:1].lower() + lab[1:]}"
    out: list[str] = []
    if hold:
        diff = "" if abs(hold["gap"]) < 0.05 else f", {abs(hold['gap']):.1f} points {'more' if hold['gap'] < 0 else 'less'}"
        out.append(f"It returned {_pc(hold['ret'])} after costs; buying and holding over the same period returned "
                   f"{_pc(hold['hold'])}{diff}.")
    n = st.get("trades")
    kind = v.get("verdict")
    if kind == "not_enough" or (isinstance(n, int) and n < MIN_TRADES):
        out.append(reason(e) or "Too few trades to tell skill from luck.")
    elif kind == "no_edge":
        out.append("It lost money after costs over the period, so there was no edge to test.")
    else:
        unseen = st.get("unseen")
        for c in checks_of(e):
            s = c["status"]
            if c["id"] == "unseen":
                out.append({"pass": "It kept making money on the years it wasn't tuned on"
                                    + (f" ({_pc(unseen)})." if isinstance(unseen, (int, float)) else "."),
                            "fail": "It lost money on the years it wasn't tuned on.",
                            "warn": "No trades happened in the years it wasn't tuned on, so it couldn't be tested there."}
                           .get(s, "The unseen-years check didn't pass."))
            elif c["id"] == "nearby":
                out.append({"pass": "Settings near the chosen ones made money too.",
                            "fail": "Most settings near the chosen ones lost money.",
                            "skip": "The nearby-settings check wasn't run (it isn't run on a group of stocks), so this "
                                    "doesn't show whether the result depends on the exact settings."}
                           .get(s, "The nearby-settings check didn't pass."))
            elif c["id"] == "shuffle":
                out.append({"pass": "With the trades in a worse order, the worst fall stayed close to the one it had.",
                            "warn": "With the trades in a worse order, the worst fall was much deeper.",
                            "fail": "With the trades in a worse order, the worst fall was 35% or more in 1 of 20 reshuffles.",
                            "skip": "The bad-luck check couldn't reshuffle these trades."}
                           .get(s, "The bad-luck fall check didn't pass."))
            elif c["id"] == "sample" and isinstance(n, int):
                out.append({"pass": f"{n} trades, enough to judge.", "warn": f"{n} trades, a small sample: a few lucky trades could decide the result."}
                           .get(s, f"{n} trades, too few to tell skill from luck."))
    # the engine's own headline and summary stay as they were stored; pages show these instead
    v.update(label=lab, fact_headline=head + ".", fact_summary=" ".join(out), checks=checks_of(e))
    return v


def public(e: dict, viewer: str | None = None) -> dict:
    """What anyone sees: everything but the owner's id and who reported it (flags say whether it's yours)."""
    st = e.get("stats") or {}
    if (st.get("ret") or 0) < -100 or (st.get("mdd") or 0) < -100:      # published before accounts stopped at zero
        e = {**e, "stats": {**st, "ret": max(st["ret"], -100.0) if isinstance(st.get("ret"), (int, float)) else st.get("ret"),
                            "mdd": max(st["mdd"], -100.0) if isinstance(st.get("mdd"), (int, float)) else st.get("mdd")}}
    out = {k: v for k, v in e.items() if k not in ("owner", "source") + MODERATION}
    out["ran"], out["reason"], out["vs_hold"] = ran(e), reason(e), versus_hold(e)
    out["verdict"] = restated(e)
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
    if len(reports) >= HIDE_AFTER and not e.get("hidden") and not e.get("official"):      # hiding StratLab's own is the owner's call
        e["hidden"], e["hidden_by"] = True, "reports"
    return e


def moderate(e: dict, action: str) -> dict:
    """The site owner's decision: hide it, or restore it (which clears the reports)."""
    if action == "hide":
        return {**e, "hidden": True, "hidden_by": "admin"}
    return {**{k: v for k, v in e.items() if k not in MODERATION}, "reports": {}}


def mod_key(e: dict) -> str | None:
    """Where an entry's reports and hiding are kept apart from the entry: by who published which notebook version, so
    they outlive the entry (deleted and published again)."""
    src = e.get("source") or {}
    return f"libmod:{e.get('owner')}:{src.get('nid')}:{src.get('v')}" if e.get("owner") and src.get("nid") else None


def hide_key(e: dict) -> str | None:
    """A hide is kept per author and notebook, so a later version published from it starts hidden too."""
    src = e.get("source") or {}
    return f"libhide:{e.get('owner')}:{src.get('nid')}" if e.get("owner") and src.get("nid") else None


def remember(e: dict):
    """Keep the entry's moderation state under its own key (and its hide under the notebook's)."""
    k = mod_key(e)
    if k:
        db.set_setting(k, json.dumps({m: e[m] for m in MODERATION if m in e}))
    h = hide_key(e)
    if h and e.get("hidden"):
        db.set_setting(h, json.dumps({m: e[m] for m in ("hidden", "hidden_by") if m in e}))


def clear_hide(e: dict):
    """The site owner restored it: later entries from the same notebook are no longer hidden."""
    h = hide_key(e)
    if h:
        db.delete_setting(h)


def remove_of_notebook(owner: str, nid: str):
    """Take down every entry this user published from the notebook, whatever became of its experiment."""
    for e in all_entries(everything=True):
        if e.get("owner") == owner and (e.get("source") or {}).get("nid") == nid:
            remove(e.get("id"))


def carry_moderation(old: dict | None, new: dict) -> dict:
    """Publishing again keeps the reports and any hiding, from the earlier entry and from the state kept under its own
    key (the entry may have been deleted): re-publishing can't be used to clear them."""
    k = mod_key(new)
    kept = db.json_value(db.get_setting(k), {}) if k else {}
    h = hide_key(new)
    hid = db.json_value(db.get_setting(h), {}) if h else {}
    for src in (kept, hid, old or {}):
        if src.get("reports"):
            new["reports"] = {**(new.get("reports") or {}), **src["reports"]}
        if src.get("hidden"):
            new.update({m: src[m] for m in ("hidden", "hidden_by") if m in src})
    return new


_official_cache: list = [0.0, []]
OFFICIAL_TTL = 60.0          # seconds a visitor's list is reused: the public routes need no account, so a crowd can't each read the store


def save(e: dict):
    remember(e)
    db.set_setting(PREFIX + e["id"], json.dumps(e))
    _official_cache[0] = 0.0


def load(eid: str) -> dict | None:
    if not ID.match(eid or ""):
        return None
    raw = db.get_setting(PREFIX + eid)
    return json.loads(raw) if raw else None


def add_copy(eid: str):
    """Count one copy on a fresh read of the entry, so a hide or report made meanwhile isn't written over."""
    e = load(eid)
    if e:
        e["copies"] = (e.get("copies") or 0) + 1
        db.set_setting(PREFIX + eid, json.dumps(e))


def remove(eid: str):
    if ID.match(eid or ""):
        db.delete_setting(PREFIX + eid)
        _official_cache[0] = 0.0


def take_down(experiments: list[dict]):
    """Remove the public links and library entries that experiments point to."""
    from . import public
    for e in experiments:
        public.unpublish(e.get("public"))
        remove(e.get("library"))


def public_entries() -> list[dict]:
    """StratLab's own visible entries, for the routes that need no sign-in (kept for a minute)."""
    import time
    if time.time() - _official_cache[0] >= OFFICIAL_TTL:
        _official_cache[:] = [time.time(), [e for e in all_entries() if is_public(e)]]
    return _official_cache[1]


def all_entries(everything: bool = False) -> list[dict]:
    """The newest 1000 entries, or with `everything` every one (a read of the whole prefix, a page at a time)."""
    out = []
    for raw in ([v for _, v in db.all_settings_with_prefix(PREFIX)] if everything else db.settings_with_prefix(PREFIX)):
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
