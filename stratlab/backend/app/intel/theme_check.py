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
EVIDENCE_MAX = 1200           # ...with the lines of its own filings after it (theme_routes.own_filings, THEMES item 6)
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


def clean_description(text, limit: int = EVIDENCE_CHARS) -> str:
    return " ".join(str(text or "").split())[:limit]


_SENTENCE = re.compile(r"[^.;!?]+")


def own_words(about, group_text, claimed) -> str:
    """The first sentence of the company's own description that speaks of the group's work (a distinctive word in common with
    the group) AND says what the AI claimed (two distinctive words in common with its quote), or "". Used when the AI says the
    company does the work but its quote isn't the description's exact words: the free models paraphrase, and a paraphrase
    dropped every company of a theme (31 Oct, "India Defence"). A quote the description doesn't back still places nothing."""
    want = stems(claimed)
    for part in _SENTENCE.findall(str(about or "")):
        words = part.split()
        if len(words) < MIN_QUOTE_WORDS:
            continue
        quote = " ".join(words[:MAX_QUOTE_WORDS])
        if supports(quote, group_text) and len(stems(quote) & want) >= 2 and quote_in(quote, about):
            return quote
    return ""


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
            elif ev and clean_description(ev.get("about"), EVIDENCE_MAX):
                got[sym] = {**ev, "about": clean_description(ev["about"], EVIDENCE_MAX)}
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
            res = None
        if not res:              # no answer, or none that could be read: not a "no" for every company, so they wait for the next request
            failed = True
            for c in batch:
                pending.add(c["symbol"])
            continue
        for c in batch:
            ev = evidence[c["symbol"]]
            for gid in c["groups"]:
                g = by_id[gid]
                v = res.get(f"{gid}|{c['symbol']}")
                if v is None:            # this pair went unanswered: asked again next time, not counted as a "no"
                    pending.add(c["symbol"])
                    continue
                gtext = f"{g['name']} {g['text']}"
                quote = v["quote"] if quote_in(v["quote"], ev["about"]) and supports(v["quote"], gtext) else (own_words(ev["about"], gtext, v["quote"]) if v["does"] else "")
                ok = bool(v["does"]) and bool(quote)
                answer = {"does": ok, "quote": quote if ok else ""}
                cache[(theme, gid, g["name"], c["symbol"], norm(ev["about"])[:200])] = answer
                got[f"{gid}|{c['symbol']}"] = answer
    left_out = 0
    unconfirmed = set()

    def keep(gid, cos):
        nonlocal left_out
        kept = []
        for c in cos:
            sym = c.get("ticker")
            v = got.get(f"{gid}|{sym}")
            if v and v["does"]:
                kept.append({**c, "what": v["quote"].strip(" ,;:-–—"), "verified": True})
            elif v is None:
                # not checked yet (the AI or a source busy) or nothing to check it by (no description found): shown, marked not yet
                # confirmed. A theme is for finding the companies in it; hiding every one a free model couldn't answer for left
                # "India Defence" with none (owner, 31 Oct). Only a clear "no" from the company's own words leaves it out.
                kept.append({**c, "what": "", "verified": False})
                unconfirmed.add(sym)
            else:
                left_out += 1
        return kept
    out["value_chain"] = [{**v, "companies": keep(f"L{i}", v.get("companies") or [])} for i, v in enumerate(out.get("value_chain") or [])]
    out["sub_themes"] = [{**s, "companies": keep(f"S{i}", s.get("companies") or [])} for i, s in enumerate(out.get("sub_themes") or [])]
    placed = {c["ticker"] for v in out["value_chain"] + out["sub_themes"] for c in v["companies"]}
    out["screen"] = [x for x in out.get("screen") or [] if x.get("ticker") in placed]
    out["clusters"] = [c for c in ({**c, "companies": [x for x in c.get("companies") or [] if x.get("ticker") in placed]} for c in out.get("clusters") or []) if c["companies"]]
    out["placements"] = {"checked": not pending and not failed, "pending": len(pending), "left_out": left_out, "placed": len(placed),
                         "unconfirmed": len(unconfirmed)}
    return out


# ---------- how each company earns (R25: the owner's outside review, "avoid grouping businesses with fundamentally different revenue
# models just because they belong to the same broad theme": hardware resellers beside IT services, an 18-company "mid-tier" catch-all) ----------
# id: (family, the name a layer of such companies gets, what they have in common). Companies of one family earn the same way; a layer never
# mixes families (theme_base.by_model). The list is the same for every theme and both markets; "unknown" when the evidence doesn't show it.
# R27 (comparable segments, generic by sector): business process outsourcing apart from IT services; contract makers (CDMO, EMS, foundry,
# OSAT) apart from product companies (own brands, IDM, fabless); parts and ingredient makers apart from makers of finished goods (auto OEM vs
# components); insurers by type; developers who sell what they build apart from landlords. Each of these is its own family.
MODELS = {
    "project_services": ("services", "Project and consulting services", "fees for projects and time worked for clients"),
    "managed_services": ("services", "Managed and outsourced IT services", "multi-year contracts to run and maintain clients' IT systems"),
    "bpo": ("bpo", "Business process outsourcing", "multi-year contracts to run business processes such as customer service, back offices "
                                                   "and claims for clients"),
    "software": ("software", "Software products and subscriptions", "licences and subscriptions for software they own"),
    "royalties": ("royalties", "Designs licensed for royalties", "licence fees and royalties on designs and patents they own"),
    "platform": ("platform", "Platforms and marketplaces", "commissions, listing fees or advertising on platforms they run"),
    "hardware_resale": ("resale", "Hardware resale and integration", "selling and installing hardware that others make"),
    "distribution": ("resale", "Distribution and trading", "the margin on goods bought from makers and sold on to businesses"),
    "retail": ("resale", "Retail", "the margin on goods bought, held in stock and sold to consumers in their own stores or online"),
    "manufacturing": ("making", "Makers of their own products", "making and selling finished products of their own"),
    "fabless": ("making", "Product designers that outsource making", "selling products of their own design that contract makers produce"),
    "components": ("components", "Parts, component and ingredient makers", "making parts, components or ingredients that other manufacturers "
                                                                          "build into their own products"),
    "contract_manufacturing": ("contract_making", "Contract manufacturing", "making products to other companies' designs and orders"),
    "capacity": ("capacity", "Data centres, hosting and networks", "renting out computing, data-centre or network capacity, and connectivity to businesses"),
    # q1 (the GPT review of the live R34 Telecom deck: Jio and Vodafone Idea left out, the operators' common model "licences and subscriptions for
    # software they own"): a network operator's subscriptions are for a service it runs on its own network, never software it licenses
    "telecom_services": ("telecom_services", "Telecom and broadband operators", "subscriptions and usage charges for mobile, broadband and "
                                                                                 "fixed-line services on networks they run"),
    "construction": ("construction", "Engineering and construction contracts", "contracts to design and build projects for clients"),
    "lending": ("lending", "Lenders", "interest on loans they make"),
    "underwriting": ("underwriting", "Insurers", "premiums for the risks they insure, and returns on the premiums they invest"),
    "life_insurance": ("life_insurance", "Life insurers", "premiums for life, pension and savings policies, and returns on the money they invest"),
    "general_insurance": ("general_insurance", "General and health insurers", "premiums for motor, health, property and other non-life risks, "
                                                                             "and returns on the premiums they invest"),
    "reinsurance": ("reinsurance", "Reinsurers", "premiums from other insurers for the risks they pass on"),
    "broking": ("financial_fees", "Brokers and distributors of financial products", "commissions and fees for selling or arranging others' financial and insurance products"),
    "asset_management": ("financial_fees", "Fund and asset managers", "fees on the money they manage"),
    "market_infrastructure": ("financial_fees", "Exchanges, depositories and ratings", "fees for trading, settling, holding or rating securities"),
    "resources": ("resources", "Mining, oil, gas and farming", "selling what they mine, drill or grow"),
    "utility": ("utility", "Power, gas and water supply", "selling power, gas or water, much of it at regulated tariffs"),
    # R29 (the owner's review of the live R27 Utilities and Metals decks: regulated networks beside generators and traders, miners beside
    # fabricators): the kinds of utility and of metals business are families of their own, so a layer never mixes them
    "regulated_utility": ("regulated_utility", "Regulated transmission and distribution", "tariffs a regulator sets for carrying or distributing "
                                                                                         "power or gas over networks they own"),
    "power_generation": ("generation", "Power generation", "selling the power their own plants generate, under long-term contracts or in the market"),
    "power_trading": ("power_trading", "Power trading and renewable project developers", "the margin on power they trade, and developing, selling or "
                                                                                         "running renewable projects"),
    "commodity_mining": ("mining", "Miners and primary metal producers", "selling ore, coal and primary metal they mine, smelt or make from ore"),
    "metal_processing": ("metal_processing", "Metal processors and fabricators", "turning metal they buy into pipes, wires, sheets, castings and "
                                                                                "fabricated parts"),
    "property": ("property", "Property and leasing", "rent and leases on property or equipment they own"),
    "property_development": ("development", "Property developers", "selling homes, offices and plots they build"),
    "care": ("care", "Hospitals, clinics and diagnostics", "fees for care, treatment and tests"),
    "media": ("media", "Media and content", "advertising, subscriptions and licences for content they own"),
    "transport": ("transport", "Transport and logistics", "fees for moving and storing goods or people"),
    "consumer_services": ("consumer_services", "Hotels, travel and consumer services", "fees paid by consumers for stays, trips, meals or courses"),
    "holding": ("holding", "Diversified groups", "several businesses that earn in different ways"),
}


# a layer holding more than one model of a family: its name and what its companies have in common (one model: the model's own)
FAMILIES = {
    "services": ("IT services for clients", "fees from clients for IT projects, time worked or multi-year contracts to run their systems"),
    "resale": ("Resale and distribution", "the margin on goods that others make"),
    "making": ("Makers of their own products", "selling products of their own, made in their own plants or by contract makers"),
    "financial_fees": ("Financial fees and commissions", "fees and commissions on financial products, money managed or securities"),
}
CONFIDENCE = ("high", "medium", "low")       # R27: how directly a company's evidence states its model; "low" counts as unknown in a layer's figures
TAGS_MAX = 3                                 # secondary ways of earning kept a company


def model_family(model) -> str:
    """A revenue model's family ("services", "resale", "lending"...), or "" for "unknown" or a word not on the list."""
    return MODELS[model][0] if model in MODELS else ""


# outsourced assembly and test (OSAT): packaging and testing others' chips (R27: contract making); R37: "manufacturing services in assembly and
# testing" (ASE) too
OSAT_WORDS = r"\bosat\b|(?:assembly|packaging) and test(?:ing)? services|manufacturing services in (?:assembly|packaging)"


# ---------- a model is kept only when the company's own evidence shows it (R26) ----------
# The live R25 Cybersecurity deck had "commissions, listing fees or advertising on platforms" for two firms that sell security subscriptions over
# their own networks: nothing in their words spoke of a marketplace. A model that is easy to give wrongly needs words of its kind in the company's
# evidence (its official industry, its description, its segments' names, its filings' titles); a model not listed here needs none.
MODEL_NEEDS = {
    "platform": r"marketplace|commission|advertis|take[- ]rate|listing fee|listings|classified|aggregator|gross merchandise|gmv|booking platform|"
                r"connects (?:buyers|sellers|users|customers)|two-sided|(?:e-?)?commerce platforms?|online travel|food delivery|ride-hailing|"
                r"third[- ]party sellers",
    "hardware_resale": r"resell|resale|reseller|distribut|system integrat|systems integrat|value[- ]added|channel partner|authori[sz]ed partner|"
                       r"install|trading|dealer|partner of (?:leading|global)|brands? such as",
    "distribution": r"distribut|wholesal|trading|trader|dealer|stockist|import|export|supply chain services",
    "retail": r"retail|store|outlet|showroom|e-?commerce|online shop|consumer brand|direct[- ]to[- ]consumer|supermarket|hypermarket",
    "royalties": r"royalt|licens|patent|intellectual property|\bip\b",
    "contract_manufacturing": r"contract manufactur|\bems\b|electronics manufacturing services|\bcdmo\b|\bcmo\b|\bcrams\b|\bodm\b|on behalf of|"
                              r"to (?:the|their|customers'?) (?:designs|specifications)|job work|for (?:global )?(?:brands|oems)|"
                              # lane n2: a foundry makes chips to its customers' designs (R27: foundries are contract makers)
                              r"(?:dedicated|independent|pure[- ]play|specialty) (?:semiconductor )?foundr|\bas a foundry\b|foundry (?:services|business)|"
                              r"designs provided by (?:them|its customers|our customers)|"
                              # R36: chips made "using specialty process technologies" (Tower) and wafers to customers' specifications
                              r"manufactur\w*\s+(?:integrated circuits|semiconductors|chips|wafers)\s+(?:using|with|on)\s+(?:its\s+|their\s+)?(?:own\s+)?"
                              r"(?:specialty|advanced|mature|analog|differentiated)?\s*process(?:es)? technolog|"
                              r"(?:to|according to|based on) (?:its |our |their )?customers?'? (?:own |proprietary )?(?:\w+ )?(?:designs|specifications)|"
                              # R37 (lane r2, the live R35 Semiconductors deck: Amkor and ChipMOS, "packaging and test services", left out as "way
                              # of earning not shown"): packaging and testing others' chips (OSAT) is contract making in so many words
                              + OSAT_WORDS + r"|electronics system design and manufactur|\besdm\b|contract-led manufactur|custom synthesis",
    "lending": r"\bloan|lend|credit|financ|bank|nbfc|microfinance|mortgage|deposit",
    "underwriting": r"insur|underwrit|premium|reinsur|assurance",
    "broking": r"brok|intermediar|distribut|commission|agent|advis|wealth|insurance web|aggregator",
    "asset_management": r"asset manag|fund|mutual|\bamc\b|wealth|portfolio manag|investment manag",
    "market_infrastructure": r"exchange|depositor|clearing|rating|registr|custod|settlement",
    # R27: the new segments, and a consumer-services label only with consumer words (the live R26 IT deck put a visa and e-governance
    # services firm alone under "Hotels, travel and consumer services")
    "bpo": r"\bbpo\b|\bbpm\b|business process|customer (?:service|experience|support|care)|contact cent|call cent|back[- ]office|"
           r"claims (?:processing|management)|transaction processing|\bkpo\b|knowledge process",
    "components": r"component|\bparts\b|ingredient|\bapis?\b|active pharmaceutical|intermediates|castings|forgings|bearings|tier[- ]?(?:1|i|one)\b|"
                  r"supplier to|suppl(?:y|ies) to (?:oems|automakers|vehicle makers|manufacturers)|for (?:oems|automakers|vehicle makers)",
    "fabless": r"fabless|design(?:s|ing)? (?:of )?(?:chips|semiconductors|integrated circuits|socs?)|without (?:its own )?fab|"
               r"outsourc(?:es|ed|ing) (?:its |the )?(?:manufactur|fabrication|production)|made by (?:foundr|contract)",
    "life_insurance": r"life insur|life assur|annuit|pension|endowment|term (?:plan|insurance)|ulip",
    "general_insurance": r"general insur|non[- ]life|health insur|motor insur|property (?:and|&) casualty|\bp&c\b|casualty|crop insur|"
                         r"fire insur|marine insur|standalone health",
    "reinsurance": r"reinsur",
    "property_development": r"develop|residential projects|housing projects|township|plotted|apartments|homes|villas|real estate projects|"
                            r"sold (?:units|homes)|bookings|pre-?sales",
    # R29: each kind of utility and of metals business needs words of its kind
    "regulated_utility": r"transmission|distribution of (?:power|electricity|gas)|power distribution|electricity distribution|discoms?\b|"
                         r"distribution licen|regulated (?:tariffs?|returns?|assets?|business)|city gas distribution|\bcgd\b|substations?|grid",
    "power_generation": r"generat|power (?:plants?|stations?|projects)|thermal|hydro|nuclear|coal-fired|gas-fired|\bmw\b|megawatt|\bgw\b|gigawatt|"
                        r"installed capacity",
    "power_trading": r"power trading|trading (?:of |in )?(?:power|electricity)|electricity trading|power exchange|renewable|solar|wind|green energy|"
                     r"\bppas?\b|power purchase agreements?|hybrid (?:power|projects)",
    "commodity_mining": r"\bmin(?:e|es|ing|er|ers)\b|\bores?\b|\bcoal\b|bauxite|smelt|primary (?:alumini?um|metal|zinc|copper|lead)|integrated steel|"
                        r"blast furnace|steel ?making|pig iron|sponge iron|ferro ?alloys?|lignite",
    "metal_processing": r"\bpipes?\b|\btubes?\b|\bwires?\b|re-?rolling|cold[- ]rolled|galvani[sz]|extru|fabricat|\bcastings?\b|\bforgings?\b|"
                        r"conductors|\bstrips?\b|processing of (?:steel|metals?|alumini?um|copper)|value[- ]added (?:steel|metal)|foils?\b|"
                        r"(?:steel|metal|alumini?um|copper) products",
    "telecom_services": r"telecom|cellular|\bmobile\b|wireless|broadband|fixed[- ]line|landline|\b[2345]g\b|subscribers?|\barpu\b|spectrum|"
                        r"unified licen[cs]e|internet service|\bftth\b|fib(?:re|er) to the home|telephon|radiotelephone|network operator",
    "consumer_services": r"hotel|resort|hospitality|\btours?\b|travel (?:agen|services|booking|packages)|holiday|restaurant|quick[- ]service|"
                         r"food service|dining|cafe|educat|school|coaching|courses|tuition|amusement|theme park|wellness|salon|fitness|gym|"
                         r"cinema|multiplex|entertainment cent",
}


# R27: words that state a model in so many words, for its confidence: "high" when the company's own words (description, business read,
# segments, filings) have them, "medium" when only its official industry does, "low" when nothing does. A model with needs uses them too.
MODEL_WORDS = {
    "project_services": r"project|consult|time[- ](?:and|&)[- ]material|fixed[- ]price|professional services|implementation|engineering services|"
                        r"digital (?:transformation|engineering)|staffing|talent|\bit services\b|"
                        # lane n2: "an engineering and technology services company", "a software service provider"
                        r"\b(?:it|technology|software|engineering|digital|testing|validation)[- ](?:and [a-z]+ )?services?\b",
    "managed_services": r"managed (?:services|infrastructure)|outsourc|multi-year|annuity|application (?:maintenance|management|support)|"
                        r"infrastructure management|remote infrastructure|run (?:and|&) maintain|\bams\b",
    "software": r"software|\bsaas\b|subscription|licen[cs]|cloud-based|products? suite|own (?:platform|product)",
    "manufacturing": r"manufactur|\bmakes?\b|\bmaker\b|produc|plants?\b|factor(?:y|ies)|\bbrands?\b|\bidm\b|fabs?\b|integrated device",
    "capacity": r"data cent|hosting|colocation|cloud infrastructure|bandwidth|network|telecom|towers?\b|fib(?:re|er)|connectivity|broadband|"
                r"mobile (?:services|operator)|subscribers|spectrum|\bgpu",
    "construction": r"construct|\bepc\b|engineering, procurement|contractor|infrastructure projects|order (?:book|backlog)|turnkey",
    "resources": r"\bmin(?:e|es|ing)\b|\bores?\b|\boil\b|\bgas\b|explor|\bcoal\b|crops?\b|plantation|drill|quarr|bauxite|iron ore|copper|zinc|gold",
    "utility": r"\bpower\b|electricity|generation|transmission|distribution of (?:power|electricity|gas)|tariff|water supply|city gas|utility|"
               r"megawatt|\bmw\b|\bgw\b",
    "property": r"\brent|lease|leasing|\breit|commercial (?:space|property|real estate)|office (?:space|parks?)|malls?\b|warehous|annuity assets",
    "care": r"hospital|clinic|diagnostic|patients|healthcare services|pathology|\blabs?\b|beds\b",
    "media": r"media|broadcast|channels?\b|\bfilms?\b|content|publish|advertis|streaming|newspaper|music",
    "transport": r"logistic|transport|freight|shipping|courier|airline|cargo|\bports?\b|warehous|\brail|fleet",
    "holding": r"conglomerate|diversified|group companies|subsidiaries|holding company|several businesses",
}


def _words_of(model) -> str:
    return "|".join(x for x in (MODEL_NEEDS.get(model), MODEL_WORDS.get(model)) if x)


def _split_evidence(evidence) -> tuple[str, str]:
    """(its official industry line, the rest: its own words) of a company's evidence (model_evidence puts "Industry: …." first)."""
    t = str(evidence or "")
    m = re.match(r"\s*Industry:\s*([^.]*)\.\s*", t)
    return (m.group(1), t[m.end():]) if m else ("", t)


def model_confidence(model, evidence, said="") -> str:
    """How directly a company's evidence states its model (R27): "high" when its own words have words of the model's kind, "medium" when
    only its official industry does, "low" when nothing does; never above what the AI said of it (`said`, one of CONFIDENCE), except that a chip designer without fabs
    is a fabless one of "medium" at least (R32). "" for unknown."""
    if model not in MODELS:
        return ""
    words = _words_of(model)
    industry, own = _split_evidence(evidence)
    level = "high" if words and re.search(words, own, re.I) else "medium" if words and re.search(words, industry, re.I) else "low"
    if said in CONFIDENCE and CONFIDENCE.index(said) > CONFIDENCE.index(level):
        level = said
    if level == "low" and family_shown(model, own):
        level = "medium"           # lane n2: its own words show its family's way of earning (Wipro, "IT, consulting and business process services")
    if level == "low" and model == "fabless" and chip_designer(evidence):
        level = "medium"           # R32: a semiconductor industry and the company's design words are enough (the live R31 deck left 29 of 37 out)
    if level == "low" and model == "components" and chip_materials(own):
        level = "medium"           # R35: its own words name the materials it supplies for chips: the rule that made it an ingredient maker shows it
    return level


def own_words_show(model, evidence) -> bool:
    """Whether a company's own words (not its official industry) show its model: words of the model's kind, or of its family's (lane n2)."""
    if model not in MODELS:
        return False
    _, own = _split_evidence(evidence)
    words = _words_of(model)
    return bool(words and re.search(words, own, re.I)) or family_shown(model, own)


def family_shown(model, own) -> bool:
    """Whether a company's own words have words of another model of its model's family (lane n2, the outside review of the live R33 IT deck:
    Wipro, "a global Information technology, consulting and business process services company", left out of "Large-scale outsourcing" as
    its words named consulting, not managed services): a layer holds one family (theme_base.by_model), so the family shown is what its
    figures need; never more than "medium"."""
    fam = model_family(model)
    if not fam:
        return False
    sibs = [m_ for m_, v in MODELS.items() if v[0] == fam and m_ != model]
    return any(_words_of(m_) and re.search(_words_of(m_), str(own or ""), re.I) for m_ in sibs)


def model_tags(tags, model, evidence) -> list[str]:
    """A company's secondary ways of earning (R27: a vehicle maker's financing arm, a drug maker's contract making beside its own brands): each on
    the list, not its primary model, and stated by its evidence (words of the tag's kind); at most TAGS_MAX, in the AI's order."""
    out = []
    for t in tags if isinstance(tags, (list, tuple)) else []:
        t = str(t or "")
        words = _words_of(t)
        if t in MODELS and t != model and t not in out and words and re.search(words, str(evidence or ""), re.I):
            out.append(t)
    return out[:TAGS_MAX]


# R27: a company's own words that state how it earns in so many words; one that the AI left unknown is given the model these show when
# exactly one model's do ("medium": stated, but not read by the AI), so a small company with a telling sentence isn't left out
MODEL_SAYS = {
    "software": r"subscription revenue|licen[cs]e (?:fees|revenue|income)|software[- ]as[- ]a[- ]service|\bsaas\b|sells? (?:its own )?software (?:products|licen)",
    "project_services": r"time[- ](?:and|&)[- ]material|fixed[- ]price (?:projects|contracts)|consulting fees|staff augmentation",
    "managed_services": r"managed services contracts|infrastructure management services|application maintenance (?:and support|contracts)",
    "bpo": r"business process (?:outsourcing|management)|\bbpo\b|contact cent(?:re|er) services|call cent(?:re|er) services",
    "contract_manufacturing": r"contract manufactur|\bcdmo\b|\bcrams\b|electronics manufacturing services|\bems provider|\bosat\b|pure-play foundry|"
                              r"(?:dedicated|independent) (?:semiconductor )?foundr",
    "fabless": r"fabless",
    "platform": r"commission income|take rate|online marketplace|gross merchandise value|marketplace (?:revenue|commissions?|fees)",
    "lending": r"interest income (?:on|from) loans|loan book|\bnbfc\b|non-banking financ",
    "life_insurance": r"life insurance company|life insurer",
    "general_insurance": r"general insurance company|general insurer|health insurer|non-life insurer",
    "reinsurance": r"reinsurer|reinsurance company",
    "hardware_resale": r"(?:authori[sz]ed|channel) (?:partner|reseller|distributor) (?:of|for)|value[- ]added reseller|system integrator for",
    "property_development": r"real estate develop|residential (?:real estate )?develop",
    "telecom_services": r"telecom(?:munications?)? (?:service providers?|operators?)|providers? of telecommunications? services|mobile network operators?|"
                        r"(?:mobile|wireless|broadband|cellular) (?:and (?:home )?broadband )?operators?|wireless carriers?",
}


def model_from_words(evidence) -> str:
    """The one model a company's own words state in so many words (MODEL_SAYS), or "" when none or more than one does. Its customers named
    ("to telecom operators", "catering to mobile network operators") are not its own model (q1)."""
    _, own = _split_evidence(evidence)
    own = not_customers(own)
    hits = [m_ for m_, rx in MODEL_SAYS.items() if re.search(rx, own, re.I)]
    if not hits and chip_designer(evidence):          # R32: a chip designer that owns no fabs says it in its own way ("designs GPUs and SoCs")
        return "fabless"
    return hits[0] if len(hits) == 1 else ""


# ---------- R37 (lane r2): the words that state how a company earns, for a company no answer gave a model ----------
# The live R35 maps left 255 of 1,334 companies with no model, 217 of them with no words read at all (IT "Engineering R&D services" 39 of 57,
# Auto "Component and systems suppliers (smaller)" 39 of 66, Chemicals "Specialty and performance chemicals (smaller)" 93 of 93): a kept
# placement never read their own descriptions, and once read ("Sintercom India Ltd manufactures sintered metal components and auto components")
# no rule took the model they state. These are each family's words in so many words, beside MODEL_SAYS; a company whose words name two ways
# of earning, or none, or a business that has stopped, stays unknown (never a guess).
OWN_SAYS = {
    "contract_manufacturing": r"contract manufactur|contract-led manufactur|custom synthesis|custom manufactur|\bcdmo\b|\bcrams\b|\bems\b(?! certifi)|"
                              r"electronics manufacturing services|electronics system design and manufactur|\besdm\b|on behalf of (?:its |their )?(?:customers|clients)",
    "components": r"\b(?:auto(?:motive)?|automobile|vehicle|tractor|engine) (?:[\w-]+ ){0,2}(?:components?|parts|ancillar\w*)\b|\bcomponents? manufacturers?\b|"
                  r"\bmanufactur\w* (?:and \w+ )?(?:of )?(?:[\w&/,-]+ ){0,4}?components\b|\btier[- ]?(?:1|i|one) supplier",
    "project_services": r"software (?:development|consultancy|consulting|outsourcing) services|\bsoftware development\b|\bit (?:consult\w*|services)\b|"
                        r"information technology services|(?:technical|technology|it) consult(?:ing|ancy)(?: services)?|\bsoftware services\b|"
                        r"customi[sz]ed software (?:solutions|development)",
    "software": r"\b(?:develops?|sells?|licen[cs]es?)(?: and \w+)? (?:its |our )?own (?:software )?products|\bsoftware products? (?:company|developer)",
    "lending": r"\b(?:commercial|private sector|public sector|scheduled) bank\b|\bbanking (?:and financial services )?company",
}
# making or trading in so many words: a maker of its own products ("manufactures", "is engaged in the manufacturing of", "a manufacturer of",
# "produces"), or a trader of others' goods; a parts maker when its official industry is one of parts or components
MAKER_SAYS = (r"\bmanufactures\b|\bmanufacturers? (?:and \w+ )?of\b|\b(?:engaged in|in the business of|business of|does|involved in) (?:the )?"
              r"(?:business of )?(?:the )?(?:manufactur\w*|production)\b|\bmanufacturing (?:and|&) (?:sell|sale|market|suppl|export)\w*|\bproduces\b|"
              r"\bproducers? (?:and \w+ )?of\b|\bmakes\b|\bmanufacturing company\b")
TRADER_SAYS = (r"\btrad(?:ing|es|er|ers)\b(?! (?:name|mark)s?\b)|\bdistribut(?:es|or|ors|ion)\b|\bwholesal\w*|\bdeals? in\b(?! (?:the )?manufactur)|"
               r"\bdealers?\b|\bstockists?\b|\bimports?\b")
# trading as the business itself ("engaged in trading of chemicals", "a distributor of"), not shares or securities traded beside another business
DISTRIBUTOR_SAYS = (r"\b(?:engaged in|in the business of|business of|deals? in|primarily) (?:the )?(?:business of )?(?:trading|distribution|wholesale)\b"
                    r"(?! (?:in|of) (?:shares|securities|derivatives|stocks))|\btraders? (?:of|in) (?!shares|securities)|\bdistributors? (?:of|for)\b|\bwholesalers?\b")
# making of any kind, which a distributor's words never name; its being a distributor in so many words
MAKING_ANY = r"manufactur|\bproduc(?:es|ing|tion|ers?)\b|\bmakes\b"
IS_DISTRIBUTOR = r"\b(?:is|as) an? (?:[\w-]+ ){0,4}distributor"
# the customers it sells to ("sells its products to auto parts manufacturing companies") are not its own business
_SOLD_TO = re.compile(r"\b(?:sells?|supplies|supplying|caters?|catering|serves?|serving)\s+(?:its |their )?(?:products |goods )?to\s+[^.;]{0,100}", re.I)
# a reseller's words beside its services: its IT services are not shown as its own model
RESELLER = r"multi-brand|\bresell|value[- ]added reseller|authori[sz]ed (?:partner|distributor|reseller)|channel partner"
PARTS_INDUSTRY = r"\bcomponents?\b|\bparts\b|ancillar"
# a business that has stopped earning: no model is stated, whatever it made before
NOT_OPERATING = (r"not (?:generated|carried on|had) any (?:revenue|business)|\bnil (?:operating )?revenue|non-operating|operations are (?:currently )?"
                 r"(?:closed|suspended)|stopped manufactur|used to manufacture|historically manufactured|suspension of work|"
                 r"under (?:corporate )?insolvency|\bcirp\b")


def stated_model(evidence) -> str:
    """The one model a company's own words state (R37), for a company no answer gave one: the words of MODEL_SAYS and OWN_SAYS (a contract
    maker's over a parts maker's when both are named: it makes parts to others' orders), else making words without trading words (a maker of
    its own products; a parts maker in a parts industry) or trading as its business without making words (a distributor). "" when its words
    name more than one way of earning (its own products made beside contract work, a parts distributor, IT services beside reselling), none,
    or a business that has stopped; the customers it names are not its own model."""
    industry, own = _split_evidence(evidence)
    own = _SOLD_TO.sub(" ", not_customers(own))
    if not own.strip() or re.search(NOT_OPERATING, own, re.I):
        return ""
    hits = {m_ for m_, rx in list(MODEL_SAYS.items()) + list(OWN_SAYS.items()) if re.search(rx, own, re.I)}
    if not hits and chip_designer(evidence):          # R32: a chip designer that owns no fabs says it in its own way
        return "fabless"
    if {"contract_manufacturing", "components"} <= hits:
        hits.discard("components")
    if len(hits) > 1:
        return ""
    makes = re.search(MAKER_SAYS, re.sub(OWN_SAYS["contract_manufacturing"], " ", own, flags=re.I), re.I)
    if hits:
        md = next(iter(hits))
        if model_family(md) == "services" and re.search(RESELLER, own, re.I):
            return ""
        if md == "contract_manufacturing" and makes:
            return ""
        if md in ("contract_manufacturing", "components") and re.search(IS_DISTRIBUTOR, own, re.I):
            return ""
        return md
    if makes and not re.search(TRADER_SAYS, own, re.I):
        return "components" if re.search(PARTS_INDUSTRY, industry, re.I) else "manufacturing"
    if not re.search(MAKING_ANY, own, re.I) and re.search(DISTRIBUTOR_SAYS, own, re.I):
        return "distribution"
    return ""


# R40 (the owner's review of the live Release 39 Consumer retail deck: "Online retailers and marketplaces" took no online seller, its map name
# "Online marketplaces" stating a platform's way of earning): the ways of earning a layer's own name states in so many words, a retailer's
# and a platform's beside the words of stated_model
NAME_STATES = {"retail": r"\bretail(?:ers?|ing)?\b|\bstores?\b|\bshops?\b", "platform": r"\bmarketplaces?\b|\bplatforms?\b"}


def name_models(name) -> set[str]:
    """The ways of earning a layer's name states (R40): the one stated_model reads in it, and each of NAME_STATES it names
    ("Online retailers and marketplaces": retail and platform)."""
    got = {m_ for m_, rx in NAME_STATES.items() if re.search(rx, str(name or ""), re.I)}
    one = stated_model(name)
    return got | ({one} if one else set())


# ---------- q1: a network operator's subscriptions are for a service it runs, not software (the GPT review of the live R34 Telecom deck) ----------
# Its customers named are never what it is: a tower company leases "to wireless telecom operators", a messaging platform caters "to mobile network
# operators (MNOs)"
_CUSTOMERS = re.compile(r"\b(?:to|for|serving|serves|catering to|customers(?: such as| include| including)?|clients(?: such as| include)?)\s+"
                        r"(?:[\w&,()-]+\s+){0,5}?(?:telecom\w*|mobile|wireless|broadband|cellular)\s+(?:network\s+|service\s+)?"
                        r"(?:operators?|service providers?|providers?|carriers?|companies|businesses|industry)\b(?:\s*\([^)]{0,12}\))?", re.I)
# its own words that it runs a network service for subscribers
TELECOM_OPERATOR = (r"telecom(?:munications?)?(?: and digital)? (?:services?|operators?|service providers?|business(?:es)?|activities)\b|"
                    r"mobile (?:services|operators?|network operators?|telephony|and (?:home )?broadband)|wireless (?:services|carriers?|operators?|"
                    r"telecommunications?)|wired and wireless|cellular (?:services|operators?|networks?)|fixed[- ]line|landline|"
                    r"(?:home )?broadband (?:services|business|operators?|providers?)|\b[45]g (?:services|networks?)|unified licen[cs]e|telecom circles?|"
                    r"internet service providers?|\bftth\b|fib(?:re|er) to the home")
# its official industry that it is an operator (India's "Telecom - Cellular & Fixed line services", the SEC's radiotelephone and telephone codes)
TELECOM_INDUSTRY = r"cellular|fixed[- ]line|radiotelephone|telephone communications|wireless telecom"
# software it owns, sold by licence or subscription: a software company, whatever network it serves
SOFTWARE_OWN = (r"software (?:products?|licen\w*|platforms?|solutions)|\bsaas\b|\bcpaas\b|software[- ]as[- ]a[- ]service|cloud communications|"
                r"communications platform")
# the network's passive parts, its gear or its building: towers and data centres are leased, equipment is made, networks are built for others
NOT_OPERATOR = (r"\btowers?\b|passive (?:telecom )?infrastructure|infrastructure sharing|tenanc|colocation|data cent|manufactur|equipment|\bepc\b|"
                r"installing|commissioning")


def not_customers(own) -> str:
    """A company's own words with the customers it names taken out (q1: "leases tower space to wireless telecom operators")."""
    return _CUSTOMERS.sub(" ", str(own or ""))


def telecom_operator(evidence) -> bool:
    """Whether a company's evidence shows a network operator that sells mobile, broadband or fixed-line services (q1, generic for both markets):
    its own words say so (telecommunication services, mobile and broadband, wired and wireless, a unified licence, landline), or its official
    industry is an operator's and its own words name nothing of towers, data centres, equipment or network building; never a company whose
    own words name software it owns sold by licence or subscription, nor one whose words name operators only as its customers."""
    industry, own = _split_evidence(evidence)
    own = not_customers(own)
    if re.search(SOFTWARE_OWN, own, re.I):
        return False
    if re.search(TELECOM_OPERATOR, own, re.I):
        return True
    return bool(re.search(TELECOM_INDUSTRY, industry, re.I)) and not re.search(NOT_OPERATOR, own, re.I)


def business_text(b) -> str:
    """The stored business read of a company's page (deepdive: "summary" of what it sells, to whom and how it earns, each segment's line, its
    customers) as one text for its model's evidence (R27); "" when none is stored."""
    if not isinstance(b, dict):
        return ""
    parts = [str(b.get("summary") or "")]
    parts += [f"{x.get('name')}: {x.get('what')}" for x in (b.get("segments") or [])[:6] if isinstance(x, dict) and x.get("name") and x.get("what")]
    if b.get("customers"):
        parts.append(f"Customers: {b['customers']}")
    return clean_description(" ".join(" ".join(p.split()).rstrip(" .") + "." for p in parts if str(p).strip()), 600)


_EARNS = re.compile(r"revenue|earn|income|fees?\b|subscription|licen[cs]|contracts?\b|clients?\b|customers?\b|outsourc|commission|"
                    r"premium|interest|rent|tariff|sells?\b|supplies|manufactur|makes|distribut|resell", re.I)


def earning_lines(*texts, limit: int = 300) -> str:
    """The sentences of a company's stored texts that speak of how it earns (revenue, fees, contracts, clients, subscriptions...), first ones
    first, so a telling sentence deep in a long description reaches the model's question (R27: IT services showed how 14 of 51 earn)."""
    out, seen = [], set()
    for t in texts:
        for x in re.split(r"(?<=[.;!?])\s+", " ".join(str(t or "").split())):
            k = x.lower()[:80]
            if len(x) >= 25 and _EARNS.search(x) and k not in seen:
                seen.add(k)
                out.append(x.rstrip())
    return clean_description(" ".join(out), limit)


def model_supported(model, evidence) -> bool:
    """Whether a company's evidence (its industry, description, segments, filings: one text) shows words of the kind its model needs (MODEL_NEEDS);
    a model with no such need is supported by any evidence, an unknown model by none."""
    if model not in MODELS:
        return False
    need = MODEL_NEEDS.get(model)
    return not need or bool(re.search(need, str(evidence or ""), re.I))


def model_evidence(industry="", about="", segments=(), filings="", limit: int = 420, business="", earns=None) -> str:
    """One company's evidence of how it earns, from what the app already keeps (R26: the IT services layer of 50 had 8 models known when only the
    stored descriptions were sent): its official industry (with its sub-industries), the names of the segments its documents report, its
    own description and the titles of its filings. R27: also its company page's business read when stored (`business`: what it sells, to whom
    and how it earns, its segments' lines and customers), and the sentences of its texts that speak of how it earns put first, so a telling
    sentence past the start of a long description is in (`earns` given: those sentences, for evidence sent beside the description). "" when
    nothing is kept."""
    parts = []
    if str(industry or "").strip():
        parts.append(f"Industry: {' '.join(str(industry).split())}.")
    segs = [" ".join(str(s).split()) for s in segments or [] if str(s or "").strip()][:6]
    if segs:
        parts.append(f"Segments: {', '.join(segs)}.")
    if str(business or "").strip():
        parts.append("Business: " + clean_description(business, 300))
    lead = clean_description(about, 600) if str(about or "").strip() else ""
    earns = (earning_lines(about, limit=240) if lead else "") if earns is None else clean_description(earns, 240)
    if earns and earns[:60] not in lead[:200]:
        parts.append(earns)
    if lead:
        parts.append(lead)
    if str(filings or "").strip() and str(filings) not in str(about or ""):
        parts.append(clean_description(filings, 200))
    return clean_description(" ".join(parts), limit)


# R29: the kinds of business the broad themes hold, kept apart in every model question
KEEP_APART = ("regulated_utility (a regulator sets its tariffs for transmission or distribution networks) apart from power_generation (sells the "
              "power its plants generate) and power_trading (trades power, or develops renewable projects); utility only when the kind isn't shown. "
              "commodity_mining (mines, smelts or makes primary metal from ore) apart from metal_processing (turns metal it buys into pipes, wires, "
              "sheets, castings or parts); resources for oil, gas and farming. retail (holds and sells its own stock) apart from platform (a "
              "marketplace earning commissions on others' goods). lending for a housing finance or home-loan company, never property_development "
              "(sells what it builds) or property (rents and leases, REITs). fabless for a company that designs chips or products and has them "
              "made by foundries or contract makers; manufacturing only when it also owns its fabs or plants (IDM). telecom_services (a network operator's "
              "mobile, broadband or fixed-line subscriptions) apart from software (licences and subscriptions for software it owns).")


def refine_model(model, evidence) -> str:
    """A broad model made exact where the company's evidence shows one kind only (R29, generic for every theme): "utility" as regulated
    networks, generation or trading and renewables by its official industry or else its own words; "resources" as commodity_mining by mining
    words (never oil, gas or farming); a maker in a metals industry as commodity_mining or metal_processing by its industry or else its own
    words. The model as given when the evidence shows none or more than one."""
    industry, own = _split_evidence(evidence)
    text = f"{industry} {own}"

    def one(cands, hints=None):
        if hints:
            hit = [c for c in cands if re.search(hints[c], industry, re.I)]
            if len(hit) == 1:
                return hit[0]
        hit = [c for c in cands if re.search(MODEL_NEEDS[c], own, re.I)]
        return hit[0] if len(hit) == 1 else ""
    if model == "utility":
        return one(("regulated_utility", "power_generation", "power_trading"), REFINE_HINTS) or model
    # q1 (the live R34 Telecom deck: every operator "software", 5 of 8 left out): a network operator's subscriptions are telecom services
    if model in ("software", "capacity", "unknown", "") and telecom_operator(evidence):
        return "telecom_services"
    # R37 (lane r2, the live R35 Real estate deck: HDFC Bank in "Home loan lenders" with no model): a company the answer gave no model whose
    # official industry is a bank's or a lender's earns interest on its loans, whatever theme it sits in (banks with home loans are lenders)
    if model in ("unknown", "") and re.search(LENDING_INDUSTRY + "|" + BANK_INDUSTRY, industry, re.I) and not re.search(NOT_LENDER, text, re.I):
        return "lending"
    if model == "resources" and not re.search(r"\boil\b|\bgas\b|petroleum|crude|crops?\b|plantation|farm|\btea\b|coffee|sugar", text, re.I):
        return "commodity_mining" if re.search(MODEL_NEEDS["commodity_mining"], text, re.I) else model
    # R31 (the owner's review of the live R30 Real estate deck): a lender is never a developer or a landlord, and a developer who sells what it
    # builds is never a landlord who leases what it owns (REITs, annuity assets)
    if model in ("property_development", "property", "construction") and (
            re.search(LENDING_INDUSTRY, industry, re.I) or (re.search(HOME_LOAN_WORDS, own, re.I) and not re.search(MODEL_NEEDS["property_development"], own, re.I)
                                                            and not re.search(MODEL_WORDS["property"], own, re.I))):
        return "lending"
    # R37 (lane r2, the live R35 Real estate deck: "Mall and retail property owners" held two developers and a landlord): a company whose own
    # words say it operates malls or offices it owns, lets space on licence or lease, or earns rent, and say nothing of building to sell, is a
    # landlord whatever its official industry ("Residential, Commercial Projects" files every Indian real estate company)
    if model in ("property_development", "property") and re.search(LANDLORD_SAYS, own, re.I) and not re.search(DEVELOPER_SAYS, own, re.I):
        return "property"
    if model in ("property_development", "property"):
        hit = [c for c in ("property_development", "property") if re.search(REFINE_HINTS[c], industry, re.I)]
        if len(hit) != 1:
            hit = [c for c in ("property_development", "property") if re.search(_words_of(c), own, re.I)]
        return hit[0] if len(hit) == 1 else model
    # R31 (the live R30 Semiconductors deck: "Fabless chip design" beside "Product designers that outsource making"): one boundary, a company
    # that designs and has others make is fabless; one that also owns its fabs (an IDM) is a maker
    # R32 (the live R31 deck: "How they earn is shown for only 8 of these 37 companies"): a designer whose evidence says it designs or develops
    # chips, GPUs or SoCs and owns no fabs is fabless, whether the AI called it a maker or left it unknown; own fabs make it an IDM (a maker)
    # R34 (GPT review of R31.5: a semiconductor materials supplier shown among equipment makers): a company whose own words say it supplies
    # materials, chemicals, gases or substrates for chips or electronics, and not machines, is an ingredient maker (components)
    if model in ("manufacturing", "unknown", "") and chip_materials(own):
        return "components"
    # q1 (the GPT review of the live R34 Semiconductors deck: GlobalFoundries in "Other semiconductor companies", TSMC and UMC called makers
    # of their own products, so the foundry layer held makers and the one contract maker had no layer): a foundry is a contract maker
    if model in ("manufacturing", "unknown", "") and foundry(evidence):
        return "contract_manufacturing"
    # R37 (lane r2, the live R35 Semiconductors deck: ASE, "a leading provider of semiconductor manufacturing services in assembly and testing",
    # among the materials makers): a chip company given parts or ingredients whose own words show packaging and test services (OSAT) or a
    # foundry's, and name no materials it supplies, is a contract maker
    if model == "components" and re.search(SEMI_INDUSTRY, text, re.I) and foundry(evidence) and not chip_materials(own):
        return "contract_manufacturing"
    # R36 (GPT review of the live R35 deck: STMicroelectronics among the contract makers): a chip maker that names products of its own and no
    # customers' designs is a maker of its own products (an IDM), whatever "contract manufacturing" its encyclopedia line says
    if model == "contract_manufacturing" and chip_idm(evidence):
        model = "manufacturing"
    if model in ("manufacturing", "fabless", "unknown", "") and re.search(SEMI_INDUSTRY, text, re.I):
        fab, out = re.search(FAB_OWN, own, re.I), re.search(OUTSOURCED, own, re.I)
        if fab and not out:
            return "manufacturing"
        if (out and not fab) or chip_designer(evidence):
            return "fabless"
        return model
    # lane n2 (the outside review of the live R33 Consumer retail deck: online retailers and marketplace operators compared as one): a
    # "retail" company whose own words say it earns commissions or fees on others' goods and nothing of selling stock of its own is a
    # marketplace (platform); a retailer with a marketplace beside its stores stays a retailer, the marketplace its tag
    if model == "retail" and re.search(MODEL_SAYS["platform"], own, re.I) and not re.search(RETAIL_STOCK, own, re.I):
        return "platform"
    # R36 (GPT review of the live R35 Consumer retail deck: Amazon, "products to be sold by us and by third parties", among marketplaces that
    # earn commissions): a company whose own words say it sells goods of its own (sold by us, its own stores, first-party, inventory it owns)
    # is a retailer, its marketplace beside them a tag
    if model == "platform" and re.search(SELLS_OWN, own, re.I):
        return "retail"
    if model in ("manufacturing", "components") and re.search(METALS_INDUSTRY, industry, re.I):
        return one(("commodity_mining", "metal_processing"), REFINE_HINTS) or model
    return model


CHIP_MATERIALS = (r"(?:semiconductor|electronic|electronics|chip|wafer)s?\b[^.]{0,40}\b(?:materials|chemicals|gases|substrates|slurr\w+|photoresists?)|"
                  r"(?:materials|chemicals|gases|substrates)\b[^.]{0,30}\b(?:for|used in)\b[^.]{0,20}\b(?:semiconductors?|chips?|electronics|wafers?)")
# equipment as the company's own product; "original equipment manufacturers" and equipment makers named as its customers are not (R35: annual
# reports name them)
_OWN_EQUIPMENT = (r"\bequipment(?! (?:manufacturers?|makers?|suppliers?|vendors?|companies|customers|oems?)\b)|\bmachines\b|"
                  r"\btools\b(?! (?:manufacturers?|makers?|suppliers?|vendors?|companies|customers)\b)")


# chips or devices as the company's own product (R36, live: Wolfspeed, "developer and manufacturer of wide-bandgap semiconductors, focused on
# silicon carbide materials and devices", is a chip maker whose words also name the material it works in)
_OWN_CHIPS = (r"(?:manufactur\w*|\bmakes?|\bmakers?|\bproduc(?:es|ers?)|\bdevelop\w*|\bdesign\w*)\b[^.;]{0,40}\b(?:semiconductors|chips|integrated circuits|"
              r"devices)\b|\bmaterials and devices\b")


# q1: a foundry's own words (it makes chips to its customers' designs); "strong" ones stand whatever else its words name, the plain
# "semiconductor foundry" only when it names no machines or tools of its own (an equipment maker's customers are foundries)
FOUNDRY_STRONG = (r"\bas a foundry\b|designs provided by (?:them|its customers|our customers|customers)|(?:dedicated|independent|pure[- ]play) "
                  r"(?:specialty )?(?:semiconductor )?foundr|\bfoundry services\b|"
                  # R36: what it makes is its customers' (wafers to customer specifications, chips to customers' designs)
                  r"(?:to|according to|based on) (?:its |our |their )?customers?'? (?:own |proprietary )?(?:\w+ )?(?:designs|specifications)|"
                  # outsourced assembly and test (OSAT): packaging and testing others' chips is contract making too (R27)
                  + OSAT_WORDS)
# R36 (GPT review of the live R35 Semiconductors deck: STMicroelectronics, "a semiconductor contract manufacturing and design company" that
# makes "a wide range of microelectronics, including the widely used STM8 and STM32 microcontrollers", among the contract makers): contract
# manufacturing of chips said in so many words is a foundry's only when the company names no products of its own (OWN_PRODUCTS); so is a maker
# of chips "using specialty process technologies" (Tower: what a specialty foundry offers its customers, not a product of its own)
FOUNDRY_WORDS = (r"(?:specialty|semiconductor|wafer|analog|logic) foundr(?:y|ies)\b|\bfoundry (?:company|business|services|provider)|"
                 r"contract manufactur\w*(?: company| services)?\b[^.]{0,30}\b(?:semiconductors?|chips?|wafers?|integrated circuits?)|"
                 r"(?:semiconductors?|chips?|wafers?|integrated circuits?)\b[^.]{0,40}\bcontract manufactur|"
                 r"manufactur\w*\s+(?:integrated circuits|semiconductors|chips|wafers)\s+(?:using|with|on)\s+(?:its\s+|their\s+)?(?:own\s+)?"
                 r"(?:specialty|advanced|mature|analog|differentiated)?\s*process(?:es)? technolog")
# a company's own products named in its words: a range or portfolio of them, its own brands or product lines, products widely used
OWN_PRODUCTS = (r"(?:manufactur\w*|makes?|produc(?:es|ing)|designs?|sells?|markets?|offers?)\s+(?:a\s+)?(?:wide|broad|diverse|large)\s+"
                r"(?:range|portfolio|array|variety|catalog(?:ue)?)\s+of\b|\b(?:its|our)\s+(?:own\s+)?(?:branded\s+)?(?:products|brands?|"
                r"product (?:lines?|portfolio|families))\b|\bwidely used\b|\bportfolio of (?:its own )?(?:products|semiconductors|chips)\b")
# contract making in words no product company uses of itself: a foundry's own, or an EMS, CDMO or job worker's
CONTRACT_STRONG = (FOUNDRY_STRONG + r"|\bems\b|electronics manufacturing services|\bcdmo\b|\bcmo\b|\bcrams\b|\bodm\b|on behalf of|job work|"
                   r"for (?:global )?(?:brands|oems)")
# a company that has foundries make its chips, or makes and sells its own (an IDM), is no foundry
NOT_FOUNDRY = (r"(?:rel(?:y|ies|ying) (?:on|upon)|third[- ]party|external|outside|outsourc\w*|through|by)\s+(?:[\w-]+\s+){0,2}foundr|\bidm\b|"
               r"integrated device manufactur|\bdesigns?,? (?:develops?,? )?(?:and )?manufactures?,? and sells\b")
_FOUNDRY_CUSTOMERS = re.compile(r"\b(?:to|for|serving|serves|customers?(?: such as| include| including)?|clients)\s+(?:[\w&,()-]+\s+){0,6}?"
                                r"foundr\w*", re.I)


def foundry(evidence) -> bool:
    """Whether a company's own words show a foundry: it makes chips to its customers' designs (q1: "as a foundry", "a leading semiconductor
    foundry", "contract manufacturing of semiconductors"), or packages and tests them (OSAT), foundries named as its customers left out; never one that has foundries make its
    chips, nor an IDM."""
    _, own = _split_evidence(evidence)
    own = _FOUNDRY_CUSTOMERS.sub(" ", str(own or ""))
    if re.search(NOT_FOUNDRY, own, re.I):
        return False
    if re.search(FOUNDRY_STRONG, own, re.I):
        return True
    return (bool(re.search(FOUNDRY_WORDS, own, re.I)) and not re.search(_OWN_EQUIPMENT, own, re.I) and not chip_materials(own)
            and not re.search(OWN_PRODUCTS, own, re.I))


def chip_idm(evidence) -> bool:
    """Whether a company given contract manufacturing makes and sells chips of its own (R36: STMicroelectronics): its industry or words are
    a chip maker's, its own words name products of its own (OWN_PRODUCTS), and none says it makes to others' designs or orders
    (CONTRACT_STRONG), so it is no foundry (foundry)."""
    industry, own = _split_evidence(evidence)
    own = _FOUNDRY_CUSTOMERS.sub(" ", str(own or ""))
    return (bool(re.search(SEMI_INDUSTRY, f"{industry} {own}", re.I)) and bool(re.search(OWN_PRODUCTS, own, re.I))
            and not re.search(CONTRACT_STRONG, own, re.I) and not foundry(evidence))


def chip_materials(own) -> bool:
    """Whether a company's own words say it supplies materials, chemicals, gases or substrates for chips or electronics, and no machines,
    chips or devices of its own (R34; R35: one rule for its model and for how surely its evidence shows it)."""
    own = re.sub(r"(?i)\boriginal equipment\b", " ", str(own or ""))
    return bool(re.search(CHIP_MATERIALS, own, re.I)) and not re.search(_OWN_EQUIPMENT, own, re.I) and not re.search(_OWN_CHIPS, own, re.I)


SELLS_OWN = (r"\bsold by us\b|\bwe sell (?!services|advertising|ads\b)|\bsells? (?:its|our) own (?:products|goods|merchandise)|"
             r"\bfirst[- ]party (?:sales|retail|products|goods)|\b1p\b|\b(?:our|its) (?:own )?(?:online (?:and physical )?|physical |retail )?stores\b|"
             r"\b(?:own|owned) inventory|\binventory (?:we|it) owns?\b|\bnet product sales\b")
# R36 (GPT review of the live R35 Semiconductors deck: FTC Solar's trackers and T1 Energy's modules among "Makers of their own products"): the SEC
# files solar module, tracker and inverter makers under semiconductors (SIC 3674); one whose own words describe solar products or installations
# and no chips is in another business, whatever its code says. (official industry, its own words of another business, chip words that keep it)
OFF_INDUSTRY = ((r"semiconductor|\bchips?\b|integrated circuits?",
                 r"\bsolar\b|photovoltaic|\bpv\b (?:modules?|panels?|cells?|industry|systems?)",
                 r"integrated circuits?|\bchips?\b|chipsets?|microcontrollers?|(?:micro)?processors?|\bics\b|\basics?\b|\bgpus?\b|"
                 r"wafer fab|semiconductor (?:devices|chips|equipment|manufacturing)|power semiconductors?|\bleds?\b|lasers?"),
                # R40 (the owner's review of the live Release 39 Consumer retail deck: Ferrellgas and Suburban Propane, propane distributors,
                # filed as retail): fuel distribution to homes and businesses with no shop, apparel or merchandise of its own is another business
                (r"\bretail",
                 r"\bpropane\b|heating oil|\bfuel oil\b|\blpg\b|liquefied petroleum gas|natural gas distribution",
                 r"\bstores?\b|\bshops?\b|apparel|clothing|merchandise|grocer|supermarket|e-?commerce|department"))


def off_industry(evidence) -> bool:
    """Whether a company's official industry files it with a theme its own words show it is not in (R36, OFF_INDUSTRY: a solar module or
    tracker maker filed as semiconductors): kept out of the theme's layers' figures, as a company of another business."""
    industry, own = _split_evidence(evidence)
    return any(re.search(ind, industry, re.I) and re.search(other, own, re.I) and not re.search(keep, own, re.I)
               for ind, other, keep in OFF_INDUSTRY)


RETAIL_STOCK = (r"\bstores?\b|\bshops?\b|inventor(?:y|ies)|\bretailer|\bwe sell\b|\bsells\b|\bselling\b|merchandise|own[- ]brands?|private label|"
                r"first[- ]party|\b1p\b|direct sales|supermarket|hypermarket")
REFINE_HINTS = {"regulated_utility": r"transmission|distribution|electric utilit", "power_generation": r"power generation|electric services",
                "power_trading": r"power trading|renewable", "commodity_mining": r"\bcoal\b|minerals|mining|pig iron|sponge iron|ferro ?alloys|"
                r"diversified metals|precious metals", "metal_processing": r"products|pipes|tubes|castings|forgings|wires|fabricat",
                "property": r"\breits?\b|real estate investment trust|leasing|rental|renting|annuity", "property_development": r"residential|developers?|"
                r"housing projects|commercial projects"}
LENDING_INDUSTRY = (r"housing finance|home finance|mortgage|non[- ]?banking financ|\bnbfc|consumer finance|microfinance|\blending\b|"
                    r"finance compan|credit institution")
# R37: a bank's official industry ("Private Sector Bank", the SEC's "National Commercial Banks"); an investment bank earns fees, not interest
BANK_INDUSTRY = r"\bbanks?\b|\bbanking\b|savings institution"
NOT_LENDER = r"investment bank|banking software|core banking|banking (?:technology|solutions)"
# R37: a landlord's own words (operates malls or offices, lets space on licence or lease, earns rent), and a developer's who builds to sell
LANDLORD_SAYS = (r"\bmalls? operator|\boperat\w* (?:(?:&|and) manag\w* )?(?:of )?(?:retail |shopping )?malls\b|"
                 r"\b(?:offers?|leases?|lets?|rents?|licen[cs]es?)\b[^.;]{0,60}\bon (?:a )?(?:licen[cs]e|leave and licen[cs]e|lease|rental) basis|"
                 r"\brental income|\blease rentals?\b|\bannuity (?:income|assets|portfolio)|\breal estate investment trust|\breits?\b")
DEVELOPER_SAYS = (r"\bdevelop(?:s|ing|er|ers)\b|build (?:&|and) sell|\bsale of (?:residential )?(?:units|flats|apartments|plots|homes|villas)|\bsells? (?:the )?(?:homes|apartments|"
                  r"flats|plots|units|villas)\b|residential (?:real estate )?develop|housing projects")
OWN_SAYS["property"] = LANDLORD_SAYS             # a landlord's words state its model too (stated_model)
HOME_LOAN_WORDS = r"home loans?|housing loans?|housing finance|mortgage loans?|loans? (?:against|for) (?:property|homes|housing)"
SEMI_INDUSTRY = r"semiconductor|\bchips?\b|integrated circuits?"
FAB_OWN = (r"own (?:wafer )?fabs?\b|its fabs\b|own fabrication|wafer fab(?:s|rication)? (?:plants?|facilit|lines?)|fabrication (?:plants?|facilit)|"
           r"\bidm\b|integrated device manufactur|"
           # R37 (lane r2, the live R35 deck: Texas Instruments "fabless"): a chip maker's own words that it designs, makes and sells its chips, or
           # runs its own manufacturing sites, as an annual report says them (theme_routes reads one for a chip company whose words say neither)
           r"\bdesigns?,? (?:develops?,? )?(?:and )?(?:manufactures?|makes),? (?:tests?,? )?(?:and )?(?:sells?|markets?)\b|"
           r"\bdesigns? and (?:makes?|manufactures?) (?:[\w-]+ ){0,3}(?:semiconductors|chips)\b|"
           r"\b(?:own|owns|operates?) (?:and operates? )?(?:\w+ )?(?:semiconductor |wafer )?(?:manufacturing|fabrication) (?:sites|facilities|plants|fabs)\b|"
           r"\binternal (?:wafer )?(?:manufacturing|fabrication) capacity|\b(?:300|200)[- ]?(?:mm|millimeter) (?:wafer )?fabs?\b")
OUTSOURCED = (r"fabless|without (?:its own )?fab|outsourc(?:es|ed|ing) (?:its |the |all )?(?:chip |wafer )?(?:manufactur|fabrication|production)|"
              r"made by (?:third-party )?(?:foundr|contract)|(?:to|through|by|at|from) (?:third-party |external )?foundr|"
              r"foundr\w* (?:make|manufactur|produc|fabricat)")
# R32: a chip designer's own words, and what is never one (design software and IP licensors, equipment makers)
CHIP_NOUNS = (r"semiconductors?|\bchips?\b|chipsets?|\bgpus?\b|graphics processors?|\bcpus?\b|\bsocs?\b|systems?[- ]on[- ](?:a[- ])?chips?|"
              r"(?:micro)?processors?|microcontrollers?|integrated circuits?|\bics\b|\basics?\b|\bfpgas?\b")
DESIGN_VERB = r"\b(?:designs?|develops?|designing|developing|designers?|developers?)\b"
DESIGN_CHIP = DESIGN_VERB + r"[^.;]{0,60}?(?:" + CHIP_NOUNS + ")"
CHIP_ONLY = r"\bgpus?\b|\bsocs?\b|\basics?\b|\bfpgas?\b|microcontrollers?|microprocessors?"
NOT_DESIGNER = (r"electronic design automation|\beda\b|(?:software|tools)\b[^.]{0,30}\b(?:to|for) (?:the )?design|"
                r"licens\w*\b[^.]{0,30}(?:\bip\b|intellectual property|architectures?|\bcores?\b)|(?:semiconductor|wafer fab\w*|capital) equipment")
MAKES_OWN = r"manufactur|\bproduc(?:es|tion)\b|\bmakes\b"
MODEL_NEEDS["fabless"] += "|" + DESIGN_CHIP


def chip_designer(evidence) -> bool:
    """Whether a company's evidence shows a chip designer that owns no fabs (R32): a semiconductor industry or chip words, its own words that
    it designs or develops chips, GPUs or SoCs (or, in a semiconductor industry, that it designs or develops at all) or has foundries make
    them; never with own-fab words, design software or IP licensing, equipment, or making words without foundries."""
    industry, own = _split_evidence(evidence)
    text = f"{industry} {own}"
    if not (re.search(SEMI_INDUSTRY, text, re.I) or re.search(CHIP_ONLY, text, re.I)):
        return False
    if re.search(FAB_OWN, own, re.I) or re.search(NOT_DESIGNER, own, re.I):
        return False
    if re.search(OUTSOURCED, own, re.I):
        return True
    if re.search(MAKES_OWN, own, re.I):
        return False
    return bool(re.search(DESIGN_CHIP, own, re.I) or (re.search(SEMI_INDUSTRY, industry, re.I) and re.search(DESIGN_VERB, own, re.I)))


# ---------- R31: a sub-basis within a family (the owner's review of the live R30 Metals deck: "highest in Aluminium and copper smelting (41%)
# and lowest in Ferro alloy producers (13%)", one family, different commodities). A family may declare a key its layers must share, beside
# the family, before a figure ranks them; each company's value is read from its evidence (official industry first, then its own words) ----------
COMMODITIES = (("steel", r"\bsteel|sponge iron|pig iron|stainless"), ("aluminium", r"alumini?um|bauxite|alumina"),
               ("zinc_lead", r"\bzinc\b|\blead (?:and|&) zinc|\blead (?:ingots?|metal|smelt|ores?|concentrates?)"), ("copper", r"\bcopper\b"),
               ("iron_ore", r"iron ore|\bpellets?\b"), ("coal", r"\bcoal\b|lignite|\bcoke\b"),
               ("precious", r"\bgold\b|\bsilver\b|platinum|precious metal"),
               ("ferro_alloys", r"ferro ?alloys?|ferro[- ]?(?:chrome|manganese|silicon)|silico[- ]?manganese|\bmanganese ore"),
               ("oil_gas", r"\boil\b|\bgas\b|petroleum|crude"))
SUB_BASIS = {"mining": "commodity", "metal_processing": "commodity", "resources": "commodity"}
SUB_WORDS = {"commodity": "commodity"}
_MAKES_STEEL = re.compile(r"(?:makes?|produces?|manufactur\w*|integrated)\b[^.]{0,40}\bsteel|steel ?making|blast furnace", re.I)


def commodity_of(evidence) -> str:
    """The commodity a metals or resources company's evidence shows (R31): one of COMMODITIES' keys by its official industry, else by its own
    words; "mixed" when they show more than one (iron ore and coal mined, zinc and aluminium), "other" when none."""
    industry, own = _split_evidence(evidence)

    def hits(text):
        h = [k for k, rx in COMMODITIES if re.search(rx, text, re.I)]
        if "steel" in h and _MAKES_STEEL.search(text):           # ore and coal bought to make steel: a steel maker
            h = [k for k in h if k not in ("iron_ore", "coal")]
        if "ferro_alloys" in h:                                  # "ferro alloys for steel": the alloy is what it sells
            h = [k for k in h if k != "steel"]
        return h
    for text in (industry, own):
        h = hits(text)
        if len(h) == 1:
            return h[0]
        if len(h) > 1:
            return "mixed"
    return "other"


def contract_kind(evidence) -> str:
    """R37 (lane r2): a contract maker's kind, from its own words: "osat" (packaging and test services for others), "foundry" (chips made to
    its customers' designs), "" for any other (a CDMO, an EMS maker) or none shown."""
    _, own = _split_evidence(evidence)
    if re.search(OSAT_WORDS, own, re.I):
        return "osat"
    return "foundry" if foundry(evidence) else ""


SUB_OF = {"commodity": commodity_of, "kind": contract_kind}
# R37: contract makers by kind: foundries and packaging and test services earn by contract alike, yet a layer holds one kind, and a company
# moving by how it earns joins only a contract layer of its own kind (theme_base.by_model); a CDMO or EMS maker has none and goes as before
SUB_BASIS["contract_making"] = "kind"
SUB_WORDS["kind"] = "kind"
SUB_JOIN = {"contract_making"}


def sub_basis(family: str, evidences: list) -> str:
    """The sub-basis of a group of one family's companies (R31): "" when the family declares none (SUB_BASIS); else the value most of them
    (more than half) share, or "mixed"."""
    key = SUB_BASIS.get(family or "")
    if not key or not evidences:
        return ""
    from collections import Counter
    vals = [SUB_OF[key](e) for e in evidences]
    top, n = Counter(vals).most_common(1)[0]
    return top if n * 2 > len(vals) and top not in ("mixed", "other") else "mixed"
METALS_INDUSTRY = r"iron (?:&|and) steel|steel|alumini?um|copper|zinc|non[- ]ferrous|metals?\b|ferro|mining|minerals"


MODEL_SYSTEM = """You say how listed companies earn most of their revenue, using ONLY the EVIDENCE given for each (its official industry, the
segments it reports, its own description, its filings' titles); no other knowledge and no figure. An earlier answer for each was not shown by its
evidence ("was"). For each company give the ONE model from this list: """ + ", ".join(MODELS) + """; "unknown" when the evidence doesn't show it.
A model needs words of its kind in the evidence: platform needs a marketplace, commissions, listing fees, advertising or a take rate; hardware_resale
needs reselling, distributing or installing others' hardware; distribution needs trading or wholesale; a company that sells subscriptions to a
service it runs on its own network is telecom_services (mobile, broadband, fixed-line) or capacity (computing, data-centre or network capacity
for businesses), one for software it owns is software, never platform; consumer_services needs hotels, travel, meals, courses or
other services paid for by consumers (services run for governments or companies are bpo or managed_services).
""" + KEEP_APART + """
Reply with ONLY this JSON: {"models": {"<symbol>": "<model>"}}"""


def recheck_models(rejected: list[dict], ask, theme: str) -> dict:
    """{symbol: model} for companies whose first model their evidence didn't show ([{symbol, name, was, evidence}]), asked once more with the
    evidence; a model is kept only when it is on the list and the evidence shows it (model_supported). An AI that can't answer raises."""
    import json
    if not rejected:
        return {}
    payload = {"theme": theme, "companies": [{"symbol": c["symbol"], "name": c.get("name") or c["symbol"], "was": c.get("was") or "",
                                              "evidence": clean_description(c.get("evidence") or "", 420)} for c in rejected]}
    got = ask(MODEL_SYSTEM, "EVIDENCE:\n" + json.dumps(payload, ensure_ascii=False))
    pairs = [(s, x.get("model") if isinstance(x, dict) else x) for s, x in model_items(got.get("models") if isinstance(got, dict) else None)]
    ev = {c["symbol"]: c.get("evidence") or "" for c in rejected}
    return {s: str(m) for s, m in pairs if s in ev and str(m) in MODELS and model_supported(str(m), ev[s])}


# ---------- a layer's name fits how its companies earn once each holds one model (R26) ----------
# The live R25 IT services deck: "Cloud, hardware and IT infrastructure" held only hardware resellers once the layers were split by model
# ("In common: selling and installing hardware that others make"). The split's layers go to the same name check as the placement's (RENAME).
NAMES_SYSTEM = """You check the names of the layers of a map of an industry theme. Each LAYER's companies now earn the same way ("how_they_earn",
from their own descriptions). For a layer whose name or description speaks of a different kind of business or way of earning than what its
MEMBERS do and how they earn (for example a name about cloud or infrastructure for companies that resell hardware others make), give a name (at
most 6 words) and a description (2 sentences: what these companies do and how they earn, and what sets this layer apart) that fit them. Leave out
a layer that fits. Never a catch-all name ("mid-tier", "other", "diversified players"). Use only what is given, no other knowledge, and no figure.
Reply with ONLY this JSON: {"rename": [{"layer": "<layer id>", "name": "", "description": ""}]}"""
NAMES_MEMBERS = 12


def _renames(got, ids: dict) -> dict:
    """{layer name: {"name", "description"}} from an answer's "rename" list: a layer id that is the map's, a name with no figure that isn't a stand-in."""
    from .ai import stand_in, theme_text
    rename = {}
    for x in (got.get("rename") if isinstance(got, dict) else None) or []:
        if isinstance(x, dict) and str(x.get("layer")) in ids:
            name = " ".join(str(x.get("name") or "").split())[:60]
            desc = theme_text(x.get("description"), 400)
            if name and not re.search(r"\d", name) and not stand_in(name):
                rename[ids[str(x["layer"])]] = {"name": name, "description": desc or ""}
    return rename


def names_for_models(layers: list[dict], ask, theme: str) -> dict:
    """{layer name: {"name", "description"}} for the layers (each with its `model` line, theme_base.by_model) whose name no longer fits how their
    companies earn. One AI answer; an AI that can't answer raises."""
    import json
    if not layers:
        return {}
    ids = {f"L{i}": v.get("layer") or "" for i, v in enumerate(layers)}
    payload = {"theme": theme, "layers": {k: {"name": ids[k], "what_it_is": str(layers[i].get("description") or "")[:240],
                                              "how_they_earn": str((layers[i].get("model") or {}).get("line") or ""),
                                              "members": [f"{c.get('ticker') or ''} · " + (c.get("name") or c.get("ticker") or "")
                                                          + (f": {str(c.get('what'))[:120]}" if c.get("what") else "")
                                                          for c in (layers[i].get("companies") or [])[:NAMES_MEMBERS]]}
                                          for i, k in enumerate(ids)}}
    return _renames(ask(NAMES_SYSTEM, "LAYERS:\n" + json.dumps(payload, ensure_ascii=False)), ids)


# ---------- the companies the map didn't place, each in the best of its layers (R21) ----------
PLACE_SYSTEM2 = """You sort listed companies into the layers of a map of an industry theme. Every company given is in the theme already (the
stock exchange files it under the theme's industry). Use only the companies' descriptions and industries given, no other knowledge, and no figure.
1. PLACE: for each COMPANY, pick the one LAYER (by its id) whose work its own description shows best; "none" when no layer fits.
2. RENAME: for a layer whose name or description doesn't fit the companies in it after step 1 (its MEMBERS and those you placed there), give a
   name (at most 6 words) and a description (2 sentences: what these companies do and how they earn, and what sets this layer apart) that fit
   them. Leave out a layer that fits. Never a catch-all name ("mid-tier", "other", "diversified players").
3. EXTRA: when 5 or more of the companies (or more than a sixth of all) fit no layer, propose up to 2 more layers for them, from their own
   descriptions, each with the symbols it holds. Keep business models whose economics differ apart (what is designed, made, supplied or serviced,
   and to whom); never one layer for the whole industry.
4. MODEL: for every symbol given (each COMPANY and each layer's MEMBERS, written "SYMBOL · name"), the ONE way it earns most of its revenue, as its
   own description shows it, from this list: """ + ", ".join(MODELS) + """; "unknown" when the description doesn't show it.
   A company that resells or installs hardware others make is hardware_resale, one that makes its own is manufacturing; one that sells
   licences or subscriptions to software it owns is software, one paid for projects or people's time is project_services.
   Read each one's "evidence" too (its official industry and sub-industry, the segments it reports, its business read, its filings' titles).
   platform only with a marketplace, commissions, listing fees, advertising or a take rate in its evidence; a mobile, broadband or fixed-line
   service sold by subscription over its own network is telecom_services, computing or network capacity for businesses is capacity, and
   software is only for software the company owns. Keep apart: bpo (customer service, back offices, claims run for clients) from managed_services
   (running clients' IT systems) and project_services; contract_manufacturing (CDMO, CRAMS, EMS, foundry, OSAT: made to others' designs) from
   manufacturing (its own finished products and brands, an IDM) and fabless (its own designs made by contract makers); components (parts,
   components or ingredients such as APIs sold to other manufacturers) from manufacturing (finished goods, such as vehicles); life_insurance,
   general_insurance (non-life and health) and reinsurance (underwriting only when the type isn't shown); property_development (sells what it
   builds) from property (rents and leases). """ + KEEP_APART + """
   "also": other models from the list that its evidence shows it earns a real part of its revenue from (a vehicle maker's financing arm is
   lending; a drug maker that also makes for others is contract_manufacturing), at most 3, [] when none. "confidence": "high" when its evidence
   says how it earns in so many words, "medium" when it follows from its industry or products, "low" when it is a guess.
Reply with ONLY this JSON: {"place": [{"symbol": "", "layer": "<layer id or none>"}], "rename": [{"layer": "<layer id>", "name": "", "description": ""}],
"extra": [{"name": "", "description": "", "symbols": [""]}], "models": {"<symbol>": {"model": "<model>", "also": ["<model>"], "confidence": "high"}}}"""
MODEL_MEMBERS = 60            # a layer's members sent with their symbols for step 4 (the largest first, as the layer lists them; R26: 40 left
                              # the tail of a 50-company layer without a model)
MEMBER_EVIDENCE = 160         # ...each with this much of its evidence (model_evidence) beside its own words


def place_in_layers(layers: list[dict], companies: list[dict], ask, theme: str) -> dict:
    """One AI answer for a map (R21, R22): {"place": {symbol: layer name or ""}, "rename": {layer name: {"name", "description"}}, "extra":
    [{"name", "description", "symbols"}], "models": {symbol: model}} (R25: each company's revenue model from MODELS, for the companies given and
    the layers' members; "unknown" left out). A layer id that isn't the map's, a symbol not asked about, a name that is empty or a description with
    a figure are dropped (the caller keeps the map's own name, and places the rest by their words)."""
    import json
    from .ai import stand_in, theme_text
    ids = {f"L{i}": v.get("layer") or "" for i, v in enumerate(layers)}
    payload = {"theme": theme, "layers": {k: {"name": ids[k], "what_it_is": str(layers[i].get("description") or "")[:240],
                                              "members": [f"{c.get('ticker') or ''} · " + (c.get("name") or c.get("ticker") or "")
                                                          + (f": {str(c.get('what'))[:120]}" if c.get("what") else "")
                                                          + (f" [evidence: {clean_description(c.get('evidence'), MEMBER_EVIDENCE)}]" if c.get("evidence") else "")
                                                          for c in (layers[i].get("companies") or [])[:MODEL_MEMBERS]]}
                                          for i, k in enumerate(ids)},
               "companies": [{"symbol": c["symbol"], "name": c["name"], "industry": c.get("industry") or "",
                              "description": clean_description(c.get("about") or "", 220),
                              **({"evidence": clean_description(c.get("evidence"), 260)} if c.get("evidence") else {})} for c in companies]}
    got = ask(PLACE_SYSTEM2, "COMPANIES:\n" + json.dumps(payload, ensure_ascii=False)) if companies or layers else {}
    got = got if isinstance(got, dict) else {}
    asked = {c["symbol"] for c in companies}
    place = {}
    for x in got.get("place") or []:
        if isinstance(x, dict) and x.get("symbol") in asked:
            lid = str(x.get("layer") or "")
            if lid in ids:
                place[x["symbol"]] = ids[lid]
            elif lid.lower() == "none":
                place[x["symbol"]] = ""
    rename = _renames(got, ids)
    extra = []
    for x in (got.get("extra") or [])[:2]:
        if isinstance(x, dict):
            name = " ".join(str(x.get("name") or "").split())[:60]
            syms = [s_ for s_ in x.get("symbols") or [] if s_ in asked and place.get(s_, "") == ""]
            if name and not re.search(r"\d", name) and not stand_in(name) and len(syms) >= 2:
                extra.append({"name": name, "description": theme_text(x.get("description"), 400) or "", "symbols": syms})
    members = {c.get("ticker") for v in layers for c in (v.get("companies") or [])[:MODEL_MEMBERS] if c.get("ticker")}
    # how each company earns (R25): only a symbol asked about and a model on the list; "unknown" and anything else is left out (it stays put).
    # R27: with its secondary models ("also") and how sure the answer is ("confidence"), each as given (theme_base checks them on the evidence)
    models, tags, said = {}, {}, {}
    for s_, x in model_items(got.get("models")):
        md = x.get("model") if isinstance(x, dict) else x
        if (s_ in asked or s_ in members) and str(md) in MODELS:
            models[s_] = str(md)
            if isinstance(x, dict):
                also = [str(t) for t in (x.get("also") or x.get("tags") or []) if str(t) in MODELS and str(t) != str(md)] if isinstance(x.get("also") or x.get("tags"), list) else []
                if also:
                    tags[s_] = also[:TAGS_MAX]
                if str(x.get("confidence") or "").lower() in CONFIDENCE:
                    said[s_] = str(x["confidence"]).lower()
    return {"place": place, "rename": rename, "extra": extra, "models": models, "tags": tags, "confidence": said}


def model_items(raw) -> list[tuple]:
    """[(symbol, model or {"model", "also", "confidence"})] from an answer's "models": a mapping, or a list of {"symbol", "model", ...}."""
    if isinstance(raw, dict):
        return list(raw.items())
    if isinstance(raw, list):
        return [(x.get("symbol"), x if ("also" in x or "confidence" in x) else x.get("model")) for x in raw if isinstance(x, dict)]
    return []


# ---------- claims: tailwinds, risks and a layer's policy line ----------
CLAIM_SYSTEM = """You check whether claims about a theme are still current, using ONLY the dated headlines given for each claim.
TODAY is given. For each CLAIM decide:
- "current": a headline dated within the last 18 months shows the programme, rule or event the claim rests on is in force or happening now. Give that headline's id.
- "outdated": a headline shows it has ended, been replaced, withdrawn or completed (for example a scheme that ran to a date and was succeeded by another). Give that headline's id, and in "replaced_by" the name of what replaced it only if the headline names it.
- "unclear": the headlines don't settle it, or there are none.
Use no knowledge beyond the headlines. A claim with no programme, rule or event in it is "unclear".
Reply with ONLY this JSON: {"claims": [{"id": "", "status": "current" | "outdated" | "unclear", "headline": "<headline id or empty>", "replaced_by": ""}]}"""
RECENT_DAYS = 550


def source_fits(claim: str, headline: str, anchor: str = "") -> bool:
    """Whether a dated headline is about what a claim rests on (LIVE7A-013: a claim on the CHIPS Act's grants to four named chipmakers was
    shown beside "Bosch begins production at Roseville chip fab", a headline about none of them): it shares a distinctive word with the
    claim, and, when the claim names the programme or rule it rests on (`anchor`: its policy or search words), with that too (two of them
    when the anchor has more than two)."""
    h = stems(headline)
    if not h or not (stems(claim) & h):
        return False
    a = stems(anchor)
    return not a or len(a & h) >= (1 if len(a) <= 2 else 2)


def claims_fit(out: dict) -> dict:
    """The map with each tailwind or risk whose dated headline isn't about it (source_fits) shown as general background, as served (a map
    checked before LIVE7A-013 kept such a pairing)."""
    out = dict(out)
    for key in ("tailwinds", "risks"):
        items = []
        for c in out.get(key) or []:
            if isinstance(c, dict) and c.get("status") == "current" and isinstance(c.get("source"), dict) \
                    and not source_fits(c.get("text") or "", c["source"].get("headline") or "", c.get("anchor") or ""):
                c = {"text": c.get("text") or "", "status": "general", "source": None}
            items.append(c)
        out[key] = items
    return out


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
        anchor = c["policy"] or c["search"]
        if status == "current" and h and (today - _day(h["at"])).days <= RECENT_DAYS and source_fits(c["text"], h["headline"], anchor):
            return True, {"text": c["text"], "status": "current", "anchor": anchor,
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


# ---------- new listings in the theme (the IPO tracker's issues, matched the way companies are placed) ----------
MAX_LISTINGS = 24


def match_listings(items: list[dict], out: dict, ask, theme: str, cache=None) -> list[dict]:
    """The IPO tracker's issues ({id, name, text}: the issuer's name, industry and what its offer says) that belong in the theme: each is put
    to the same question as a company, whether its own words show it does the work of a layer or sub-theme, and is kept only with words that are
    in its text and speak of that group. A first cut by shared distinctive words keeps the AI to a few issues. Returns [{id, groups: [names], what}]."""
    groups = groups_of(out)
    by_id = {g["id"]: g for g in groups}
    theme_stems = stems(f"{theme} {out.get('sector') or ''}") | set().union(*[stems(f"{g['name']} {g['text']}") for g in groups]) if groups else set()
    cands = [i for i in items if i.get("text") and stems(i["text"]) & theme_stems][:MAX_LISTINGS]
    cache = cache if cache is not None else {}
    got: dict[str, dict] = {}
    todo = []
    for i in cands:
        need = []
        for gid in by_id:
            key = ("ipo", theme, gid, by_id[gid]["name"], i["id"], norm(i["text"])[:200])
            if key in cache:
                got[f"{gid}|{i['id']}"] = cache[key]
            else:
                need.append(gid)
        if need:
            todo.append({"symbol": i["id"], "name": i["name"], "about": clean_description(i["text"]), "industry": "", "groups": need})
    for k in range(0, len(todo), BATCH):
        batch = todo[k:k + BATCH]
        res = verdicts(batch, by_id, ask, theme)             # an AI that can't answer raises: the caller tries again later
        for c in batch:
            for gid in c["groups"]:
                v = res.get(f"{gid}|{c['symbol']}") or {"does": False, "quote": ""}
                g = by_id[gid]
                ok = bool(v["does"]) and quote_in(v["quote"], c["about"]) and supports(v["quote"], f"{g['name']} {g['text']}")
                answer = {"does": ok, "quote": v["quote"] if ok else ""}
                cache[("ipo", theme, gid, g["name"], c["symbol"], norm(c["about"])[:200])] = answer
                got[f"{gid}|{c['symbol']}"] = answer
    result = []
    for i in cands:
        hits = [(by_id[g]["name"], got[f"{g}|{i['id']}"]["quote"]) for g in by_id if got.get(f"{g}|{i['id']}", {}).get("does")]
        if hits:
            result.append({"id": i["id"], "groups": [h[0] for h in hits], "what": hits[0][1].strip(" ,;:-–—")})
    return result
