"""Checks on a theme map's claims against sources the app reads, so a company sits only where its own words put it and a
policy is named only while a dated source still shows it (THEME-1 items 2, 6 and 8).

- Placement (items 2 and 6): the map (intel/ai.py `sector`) puts companies in value-chain layers and sub-themes. A company stays in a
  group only when its own description (its profile as the company wrote it, read once and kept) says it does that
  group's work: the AI answers yes or no for each pair, and gives the words from the description that show it. The words
  must be in the description, exactly, and must share a distinctive word with the group; otherwise the company is left
  out. Those words are what the page shows as "what it does", in the company's own words. Fewer companies, all of them
  right, is the aim: a company with no description to check is left out, and a pair the AI can't show is left out.
- Claims (item 8): each tailwind and risk (and a layer's policy line) that names a programme, rule or event is put
  beside the dated headlines found for it. The AI says whether the headlines show it still current, or ended or replaced;
  it must name the headline, which must exist and be recent for "current". Ended or replaced claims are dropped; a claim
  no headline settles stays, marked as general background that no dated source was found for.

No figure is made here: every sentence shown is a company's own words, a headline as published, or the map's text."""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

from ..ai_providers import AIError

# words a group's name or text shares with every other group, which prove nothing about the work
_WORK_GENERIC = {
    "and", "the", "for", "with", "from", "that", "this", "its", "their", "are", "was", "has", "have", "which", "who", "into", "such", "than",
    "also", "per", "all", "any", "more", "most", "other", "other", "each", "both", "over", "under", "across", "between", "within", "make",
    "makes", "made", "making", "company", "companies", "business", "businesses", "india", "indian", "global", "world", "market", "markets",
    "sector", "industry", "industries", "service", "services", "product", "products", "layer", "chain", "value", "supply", "demand",
    "raw", "material", "materials", "processing", "process", "processes", "manufacturing", "manufacture", "manufactures", "production",
    "produce", "produces", "producer", "producers", "supplier", "suppliers", "supplies", "provide", "provides", "providing", "provider",
    "providers", "operate", "operates", "operating", "operator", "operators", "build", "builds", "building", "builder", "builders",
    "develop", "develops", "developing", "development", "developer", "developers", "engineering", "infrastructure", "equipment",
    "technology", "technologies", "solutions", "systems", "system", "energy", "power", "end", "use", "used", "using", "key", "main",
    "major", "large", "leading", "largest", "one", "two", "three", "first", "new", "part", "parts", "components", "component",
    "assembly", "extraction", "mining", "mine", "mines", "miners", "etc", "including", "includes", "based", "focus", "focused",
}
_TOKEN = re.compile(r"[a-z0-9]+")
MIN_QUOTE_WORDS = 4
MAX_QUOTE_WORDS = 40
EVIDENCE_CHARS = 700          # a company's description as sent to the AI (and kept): enough to say what it does
BATCH = 6                     # companies per AI request: small enough for a free model to read each description carefully
EVIDENCE_BUDGET = 40.0        # seconds a request may spend reading company descriptions before it answers with what it has


def norm(text) -> str:
    """Words only, lower case, one space between: what a quote is compared by."""
    return " ".join(_TOKEN.findall(str(text or "").lower().replace("&", " and ")))


def stems(text) -> set[str]:
    """The distinctive word starts (five letters) of a text: a word that says what work, not that it is work."""
    out = set()
    for w in _TOKEN.findall(str(text or "").lower()):
        if len(w) > 3 and w not in _WORK_GENERIC:
            out.add(w[:5])
    return out


def quote_in(quote, text) -> bool:
    """Whether `quote` is, word for word (case and punctuation aside), in `text`, and long enough to say something."""
    q, t = norm(quote), norm(text)
    n = len(q.split())
    return MIN_QUOTE_WORDS <= n <= MAX_QUOTE_WORDS and f" {q} " in f" {t} "


def supports(quote, group_text) -> bool:
    """Whether the quote speaks of what the group is about: it shares a distinctive word start with the group's name and text."""
    return bool(stems(quote) & stems(group_text))


def clean_description(text) -> str:
    return " ".join(str(text or "").split())[:EVIDENCE_CHARS]


# ---------- the groups of a map ----------
def groups_of(out: dict) -> list[dict]:
    """[{id, kind, index, name, text, companies}] for the map's value-chain layers ("L0"...) and sub-themes ("S0"...)."""
    groups = []
    for i, v in enumerate(out.get("value_chain") or []):
        groups.append({"id": f"L{i}", "kind": "layer", "index": i, "name": v.get("layer") or "", "text": v.get("description") or "",
                       "companies": v.get("companies") or []})
    for i, s in enumerate(out.get("sub_themes") or []):
        groups.append({"id": f"S{i}", "kind": "sub", "index": i, "name": s.get("name") or "", "text": s.get("detail") or "",
                       "companies": s.get("companies") or []})
    return groups


PLACE_SYSTEM = """You check where listed companies belong in a map of an industry theme. For each CHECK, decide whether the
company ITSELF does the work of the GROUP, using ONLY the company's own description given for it.
Rules:
- "does" is true only when the description says this company does that work (makes, mines, refines, processes, builds, operates,
  supplies it). Being in a related industry, being a customer, being a supplier of something else, or belonging to a group of companies that does it, is NOT enough.
  A diversified company counts only when its description names this very work. When unsure, answer false.
- "quote" is 6 to 30 words copied word for word from that company's description, showing the work. Empty when "does" is false.
- Use no knowledge beyond the descriptions.
Reply with ONLY this JSON: {"checks": [{"id": "<group id>|<symbol>", "does": true | false, "quote": ""}]}"""


def verdicts(batch: list[dict], groups_by_id: dict, ask, theme: str) -> dict[str, dict]:
    """{"<group id>|<symbol>": {"does", "quote"}} for one batch of companies ({symbol, name, about, industry, groups: [ids]}).
    A missing or unreadable answer is no answer (the pair is not placed)."""
    import json
    wanted = {f"{g}|{c['symbol']}" for c in batch for g in c["groups"]}
    payload = {"theme": theme,
               "groups": {gid: {"name": groups_by_id[gid]["name"], "what_it_is": groups_by_id[gid]["text"][:300]}
                          for gid in sorted({g for c in batch for g in c["groups"]})},
               "companies": [{"symbol": c["symbol"], "name": c["name"], "industry": c.get("industry") or "", "description": c["about"],
                              "check_groups": c["groups"]} for c in batch]}
    got = ask(PLACE_SYSTEM, "CHECKS:\n" + json.dumps(payload, ensure_ascii=False))
    out = {}
    for x in (got.get("checks") if isinstance(got, dict) else None) or []:
        if isinstance(x, dict) and str(x.get("id")) in wanted:
            out[str(x["id"])] = {"does": x.get("does") is True, "quote": " ".join(str(x.get("quote") or "").split())}
    return out


def gather_evidence(symbols: list[str], read, budget: float = EVIDENCE_BUDGET, workers: int = 4) -> tuple[dict, set]:
    """({symbol: {about, industry, name}} for the companies whose description could be read, {symbols still unread: the time ran
    out or the source was busy}). `read(symbol)` returns the description, None when the company has none (it is then
    never placed), or raises when the source can't answer now (it is tried again on a later request)."""
    got, pending = {}, set()
    started = time.monotonic()
    todo = list(symbols)
    if not todo:
        return got, pending

    def one(sym):
        if time.monotonic() - started > budget:
            return sym, "late"
        try:
            return sym, read(sym)
        except Exception as e:                     # a source that can't answer now: this company waits for the next request
            print("theme check: description not read:", sym, type(e).__name__, str(e)[:100])
            return sym, "late"
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(todo)))) as pool:
        futures = [pool.submit(one, s) for s in todo]
        for f in as_completed(futures):
            sym, ev = f.result()
            if ev == "late":
                pending.add(sym)
            elif ev and clean_description(ev.get("about")):
                got[sym] = {**ev, "about": clean_description(ev["about"])}
    return got, pending


def check_placements(out: dict, evidence_of, ask, theme: str, verdict_cache=None, budget: float = EVIDENCE_BUDGET) -> dict:
    """The map with only the companies whose own description shows they do their group's work. Each kept company in a
    layer or sub-theme carries "what" (the words from its description). Also gives "placements": {"checked": every company
    could be checked, "pending": how many couldn't be yet, "left_out": how many named pairs were dropped}. `evidence_of(symbols)`
    -> ({symbol: {about, industry}}, pending symbols); `ask(system, text)` is the AI's JSON answer; `verdict_cache` is a
    dict that keeps a pair's answer for the next request."""
    out = dict(out)
    groups = groups_of(out)
    by_id = {g["id"]: g for g in groups}
    syms: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for g in groups:
        for c in g["companies"]:
            if c.get("ticker"):
                syms.setdefault(c["ticker"], []).append(g["id"])
                names.setdefault(c["ticker"], c.get("name") or c["ticker"])
    evidence, pending = evidence_of(sorted(syms))
    cache = verdict_cache if verdict_cache is not None else {}
    got: dict[str, dict] = {}
    todo = []
    for sym, gids in syms.items():
        ev = evidence.get(sym)
        if not ev:
            continue
        need = []
        for gid in gids:
            key = (theme, gid, by_id[gid]["name"], sym, norm(ev["about"])[:200])
            if key in cache:
                got[f"{gid}|{sym}"] = cache[key]
            else:
                need.append(gid)
        if need:
            todo.append({"symbol": sym, "name": names[sym], "about": ev["about"], "industry": ev.get("industry") or "", "groups": need})
    failed = False
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            res = verdicts(batch, by_id, ask, theme)
        except AIError:
            failed = True
            for c in batch:
                pending.add(c["symbol"])
            continue
        for c in batch:
            ev = evidence[c["symbol"]]
            for gid in c["groups"]:
                v = res.get(f"{gid}|{c['symbol']}") or {"does": False, "quote": ""}
                g = by_id[gid]
                ok = bool(v["does"]) and quote_in(v["quote"], ev["about"]) and supports(v["quote"], f"{g['name']} {g['text']}")
                answer = {"does": ok, "quote": v["quote"] if ok else ""}
                cache[(theme, gid, g["name"], c["symbol"], norm(ev["about"])[:200])] = answer
                got[f"{gid}|{c['symbol']}"] = answer
    left_out = 0

    def keep(gid, cos):
        nonlocal left_out
        kept = []
        for c in cos:
            sym = c.get("ticker")
            v = got.get(f"{gid}|{sym}")
            if v and v["does"]:
                kept.append({**c, "what": v["quote"], "verified": True})
            elif sym in pending:
                continue                           # not checked yet: not shown yet
            else:
                left_out += 1
        return kept
    out["value_chain"] = [{**v, "companies": keep(f"L{i}", v.get("companies") or [])} for i, v in enumerate(out.get("value_chain") or [])]
    out["sub_themes"] = [{**s, "companies": keep(f"S{i}", s.get("companies") or [])} for i, s in enumerate(out.get("sub_themes") or [])]
    placed = {c["ticker"] for v in out["value_chain"] + out["sub_themes"] for c in v["companies"]}
    out["screen"] = [x for x in out.get("screen") or [] if x.get("ticker") in placed]
    out["clusters"] = [c for c in ({**c, "companies": [x for x in c.get("companies") or [] if x.get("ticker") in placed]} for c in out.get("clusters") or []) if c["companies"]]
    out["placements"] = {"checked": not pending and not failed, "pending": len(pending), "left_out": left_out, "placed": len(placed)}
    return out


# ---------- claims: tailwinds, risks and a layer's policy line ----------
CLAIM_SYSTEM = """You check whether claims about a theme are still current, using ONLY the dated headlines given for each claim.
TODAY is given. For each CLAIM decide:
- "current": a headline dated within the last 18 months shows the programme, rule or event the claim rests on is in force or happening now. Give that headline's id.
- "outdated": a headline shows it has ended, been replaced, withdrawn or completed (for example a scheme that ran to a date and was succeeded by another). Give that headline's id, and in "replaced_by" the name of what replaced it only if the headline names it.
- "unclear": the headlines don't settle it, or there are none.
Use no knowledge beyond the headlines. A claim with no programme, rule or event in it is "unclear".
Reply with ONLY this JSON: {"claims": [{"id": "", "status": "current" | "outdated" | "unclear", "headline": "<headline id or empty>", "replaced_by": ""}]}"""
RECENT_DAYS = 550


def claims_of(out: dict) -> list[dict]:
    """[{id, kind, text, search}] the map's tailwinds and risks (objects {"text", "policy", "search"}, or plain texts)."""
    claims = []
    for kind, key in (("tailwind", "tailwinds"), ("risk", "risks")):
        for i, t in enumerate(out.get(key) or []):
            if isinstance(t, str):
                t = {"text": t, "search": ""}
            if isinstance(t, dict) and str(t.get("text") or "").strip():
                claims.append({"id": f"{kind[0].upper()}{i}", "kind": kind, "text": str(t["text"]), "search": " ".join(str(t.get("search") or "").split())[:80],
                               "policy": " ".join(str(t.get("policy") or "").split())[:80]})
    return claims


def _day(v) -> date | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def check_claims(out: dict, search, ask, today: date | None = None) -> dict:
    """The map with each tailwind and risk as {"text", "status": "current" | "general", "source": {headline, at, outlet, url}} and
    the ones found ended or replaced dropped. `search(query)` -> [{headline, at, source, url}] (dated headlines); a search that
    fails leaves the claim general. `ask` as in check_placements."""
    import json
    today = today or datetime.now(timezone.utc).date()
    claims = claims_of(out)
    found: dict[str, list[dict]] = {}
    for c in claims:
        q = c["search"] or c["policy"]
        if not q:
            continue
        try:
            rows = [r for r in (search(q) or []) if r.get("headline") and _day(r.get("at"))]
        except Exception as e:
            print("theme check: headlines not read:", q, type(e).__name__, str(e)[:100])
            rows = []
        rows.sort(key=lambda r: str(r.get("at")), reverse=True)
        found[c["id"]] = [{"id": f"{c['id']}.{j}", **r} for j, r in enumerate(rows[:8])]
    asked = [c for c in claims if found.get(c["id"])]
    verdict: dict[str, dict] = {}
    if asked:
        payload = {"today": today.isoformat(),
                   "claims": [{"id": c["id"], "claim": c["text"],
                               "headlines": [{"id": h["id"], "date": str(h["at"])[:10], "headline": h["headline"]} for h in found[c["id"]]]} for c in asked]}
        got = ask(CLAIM_SYSTEM, "CLAIMS:\n" + json.dumps(payload, ensure_ascii=False))     # an AI that can't answer now raises: the caller tries again later
        for x in (got.get("claims") if isinstance(got, dict) else None) or []:
            if isinstance(x, dict) and str(x.get("id")) in found:
                verdict[str(x["id"])] = x

    def settle(c):
        """(keep, shown claim)"""
        v = verdict.get(c["id"]) or {}
        h = next((h for h in found.get(c["id"], []) if h["id"] == str(v.get("headline") or "")), None)
        status = str(v.get("status") or "")
        if status == "outdated" and h:
            return False, None
        if status == "current" and h and (today - _day(h["at"])).days <= RECENT_DAYS:
            return True, {"text": c["text"], "status": "current",
                          "source": {"headline": h["headline"], "at": str(h["at"])[:10], "outlet": h.get("source") or "", "url": h.get("url") or ""}}
        return True, {"text": c["text"], "status": "general", "source": None}
    out = dict(out)
    for kind, key in (("tailwind", "tailwinds"), ("risk", "risks")):
        shown = []
        for c in [c for c in claims if c["kind"] == kind]:
            keep_it, item = settle(c)
            if keep_it:
                shown.append(item)
        out[key] = shown
    return out
