"""Checks on what the AI writes, in code, against data StratLab holds.

- Tickers (R5O-008): every company or fund the AI names with a ticker is looked up in the market's list of listed
  companies. The ticker must exist and its listed name must agree with the name the AI gave; otherwise the name is
  looked up and the right ticker used, and if neither works the ticker is dropped ("BHARTIARTL | Bharat Heavy
  Electricals" becomes BHEL, "MDSL" becomes MAZDOCK, the unlisted "TATASYS" loses its ticker).
"""
import re

from .. import name_search

# a name agrees with another when most of the shorter one's words start the same way as the other's (the broker's
# list cuts names short: "TATA CONSULTANCY SERV LT", "SOLAR INDUSTRIES (I) LTD")
AGREE_SHARE = 2 / 3
# words that say what kind of company, not which one: two names sharing only these don't agree
GENERIC = {"india", "indian", "industries", "industry", "international", "global", "holdings", "group", "systems",
           "technologies", "technology", "tech", "enterprises", "services", "solutions", "bank", "financial", "finance",
           "energy", "power", "infra", "infrastructure", "engineering", "electricals", "electronics", "ventures",
           "etf", "fund", "index", "nifty", "bees", "trust", "shares", "ishares", "spdr", "vanguard", "invesco"}


def _words(name: str | None) -> list[str]:
    return [w for w in name_search.tokens(name) if w not in ("i", "l", "lt", "ltd")]


def _same_word(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 3 and long_.startswith(short)


def names_agree(a: str | None, b: str | None) -> bool:
    """Whether two names are the same company's: 'Bharat Heavy Electricals Ltd' and 'BHARAT HEAVY ELECTRICALS' do,
    'Bharat Heavy Electricals' and 'BHARTI AIRTEL' or 'BHARAT ELECTRONICS' don't."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    if name_search.compact(a) == name_search.compact(b):
        return True
    short, long_ = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    hits = [w for w in short if any(_same_word(w, x) for x in long_)]
    if not _same_word(short[0], long_[0]) and short[0] not in long_:
        return False                    # the first word names the company ("Tata …", "Bharat …")
    if not [w for w in hits if w not in GENERIC] and len(short) > 1:
        return False
    return len(hits) >= max(1, -(-len(short) * 2 // 3))


TICKER = re.compile(r"^[A-Z0-9][A-Z0-9&.\-]{0,19}$")


class Resolver:
    """Looks companies up in one market's list. `lookup(q, region)` gives [{symbol, name}] for what's typed (a
    symbol or a name), best first, from StratLab's own lists. Each answer is kept for the rest of the call."""

    def __init__(self, lookup, region: str):
        self.lookup, self.region, self._seen = lookup, region, {}

    def _rows(self, q: str) -> list[dict]:
        q = " ".join(str(q or "").split())[:80]
        if not q:
            return []
        if q not in self._seen:
            try:
                self._seen[q] = [r for r in (self.lookup(q, self.region) or []) if isinstance(r, dict) and r.get("symbol")]
            except Exception as e:      # the list is down: nothing can be checked, so nothing is passed as checked
                print("grounding: lookup failed,", self.region, type(e).__name__, str(e)[:120])
                self._seen[q] = []
        return self._seen[q]

    def resolve(self, name: str | None, ticker: str | None) -> dict | None:
        """{symbol, name} for a company the AI named, or None when it can't be found in the list."""
        t = str(ticker or "").strip().upper()
        if t.endswith((".NS", ".BO")):
            t = t.rsplit(".", 1)[0]
        if t and TICKER.match(t):
            for r in self._rows(t):
                if str(r["symbol"]).upper() == t and (not name or names_agree(name, r.get("name"))):
                    return {"symbol": t, "name": r.get("name") or name}
        if name:
            for r in self._rows(name)[:6]:
                if names_agree(name, r.get("name")):
                    return {"symbol": str(r["symbol"]).upper(), "name": r.get("name") or name}
        return None


# words an industry shares with every other, which say nothing about the theme
_IND_GENERIC = {"and", "the", "of", "other", "others", "services", "service", "products", "product", "diversified", "industries",
                "industry", "misc", "miscellaneous", "general", "goods", "related", "activities", "allied", "india", "indian"}


def _stems(text: str | None) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]+", str(text or "").lower()) if len(w) > 2 and w not in _IND_GENERIC}


def tidy_text(t):
    """A doubled full stop ("...partnerships..") made single; an ellipsis stays (R6O-017). A comma or semicolon left
    before a full stop ("strategic offset mandates,.") goes (DE-014)."""
    if not isinstance(t, str):
        return t
    t = re.sub(r"\s*[,;:]+\s*(?=\.(?!\.))", "", t)
    return re.sub(r"(?<!\.)\.\.(?!\.)", ".", t)


def exchange_list(out: dict, rows: list[dict], cap: int = 40) -> dict:
    """The listed companies the exchange's own classification puts in the theme's industries (DE-013: Bharat Dynamics,
    BEML, Data Patterns and Solar Industries were missing from an "India defence" map): an industry counts when two
    or more of the map's listed companies are in it, or when it shares a word with the theme. `rows`: the screener's
    stored index ({symbol, name, industry}). {"industries", "companies" (A to Z, at most `cap`), "total"}; the map's own
    companies are marked `named`. None when no industry qualifies."""
    ind = {r.get("symbol"): r.get("industry") for r in rows or [] if r.get("symbol") and r.get("industry")}
    mapped = {x.get("ticker") for x in out.get("screen") or []}
    for group in (out.get("clusters") or []) + (out.get("value_chain") or []):
        mapped |= {c.get("ticker") for c in group.get("companies") or []}
    mapped.discard("")
    mapped.discard(None)
    counts: dict[str, int] = {}
    for t in mapped:
        if ind.get(t):
            counts[ind[t]] = counts.get(ind[t], 0) + 1
    theme = _stems(out.get("sector"))
    keep = sorted(i for i, n in counts.items() if n >= 2 or (_stems(i) & theme))
    if not keep:
        return {}
    found = sorted((r for r in rows if r.get("industry") in keep and r.get("symbol")), key=lambda r: str(r.get("name") or r["symbol"]).lower())
    return {"industries": keep, "total": len(found),
            "companies": [{"ticker": r["symbol"], "name": listed_name(r.get("name"), r["symbol"]), "industry": r["industry"],
                           "named": r["symbol"] in mapped} for r in found[:cap]]}


_THEME_WORDS = {"ai", "ev", "evs", "it", "5g", "ipo", "psu", "psus", "fmcg", "capex", "defence", "defense", "railways", "rail", "solar",
                "wind", "power", "energy", "green", "hydrogen", "data", "centers", "centres", "cloud", "chips", "semiconductors", "banks",
                "banking", "fintech", "insurance", "pharma", "healthcare", "hospitals", "tourism", "travel", "retail", "consumer",
                "electrification", "grid", "nuclear", "water", "cement", "steel", "metals", "mining", "gold", "oil", "gas", "auto",
                "autos", "batteries", "lithium", "robotics", "cybersecurity", "software", "telecom", "media", "gaming", "space",
                "shipbuilding", "infrastructure", "housing", "real", "estate", "chemicals", "fertilisers", "fertilizers", "agri",
                "agriculture", "textiles", "logistics", "drones", "aviation", "airlines", "biotech", "glp", "obesity", "india", "us"}


def vocabulary(rows: list[dict]) -> set[str]:
    """Every word in the listed companies' names, sectors and industries, and the usual theme words: what a theme typed
    is checked against before an AI read is spent on it (DE-015)."""
    words = set(_THEME_WORDS)
    for r in rows or []:
        for f in ("name", "sector", "industry"):
            words |= {w for w in re.findall(r"[a-z0-9]+", str(r.get(f) or "").lower()) if len(w) > 1}
    return words


def _gibberish(w: str) -> bool:
    """A typed word that can't be a word: three of one letter in a row, five consonants in a row, or no vowel in a word
    longer than four letters ("zzz", "asdkjh", "qwrtpl")."""
    return bool(re.search(r"(.)\1\1", w) or re.search(r"[bcdfghjklmnpqrstvwxz]{5}", w) or (len(w) > 4 and not re.search(r"[aeiouy]", w)))


def looks_like_theme(q: str, vocab: set[str]) -> bool:
    """Whether a typed theme reads as words: one of them is a word the listed companies or the usual themes use, or most of
    them look like words. "asdkjh qwe zzz" doesn't; "India defence", "grid electrification" and "GLP-1 drugs" do."""
    words = [w for w in re.findall(r"[a-z0-9]+", str(q or "").lower()) if w]
    if not words:
        return False
    if any(w in vocab or (len(w) > 3 and w.rstrip("s") in vocab) for w in words):
        return True
    return sum(1 for w in words if not _gibberish(w)) > len(words) / 2 and any(len(w) > 3 for w in words)


def listed_only(out: dict) -> dict:
    """A map kept from before DE-013 as today's would be: no company that isn't on the list, none named twice."""
    def only(cos):
        seen, keep = set(), []
        for c in cos or []:
            if c.get("ticker") and c.get("listed", True) and c["ticker"] not in seen:
                seen.add(c["ticker"])
                keep.append(c)
        return keep
    out = dict(out)
    out["clusters"] = [c for c in ({**c, "companies": only(c.get("companies"))} for c in out.get("clusters") or []) if c["companies"]]
    out["value_chain"] = [{**v, "companies": only(v.get("companies"))} for v in out.get("value_chain") or []]
    return out


def listed_name(name: str | None, fallback: str | None = None) -> str:
    """A company's name as the exchange's list writes it, in title case when the list has it in capitals."""
    from ..stock_pages import proper_name
    return proper_name(str(name or fallback or "").strip()) or str(fallback or "")


def ground_sector(out: dict, region: str, lookup) -> dict:
    """A theme map of listed companies only, each under the name the exchange lists it by (R5O-008, DE-013):
    - every company, in "Listed companies across the chain", "Who's in it" and the value chain, is looked up in the
      market's list by its ticker and name; one that can't be found is dropped, not shown as "not listed" (the AI
      called Larsen & Toubro Infotech, listed as LTM, "not listed");
    - a company found is named as the list names it, so a unit put under its parent's ticker reads as the listed parent
      ("Larsen & Toubro Defence" under LT is Larsen & Toubro), and each listed company shows once per group;
    - "Funds to track": a fund that can't be found is dropped.
    A doubled full stop in the text is made single (R6O-017); drop_unrelated then checks each company's industry."""
    res = Resolver(lookup, region)

    def fix(c: dict) -> dict | None:
        got = res.resolve(c.get("name"), c.get("ticker")) if c.get("name") or c.get("ticker") else None
        return {**c, "ticker": got["symbol"], "name": listed_name(got.get("name"), c.get("name")), "listed": True} if got else None

    def fix_all(cos: list[dict]) -> list[dict]:
        seen, keep = set(), []
        for c in cos:
            f = fix(c)
            if f and f["ticker"] not in seen:
                seen.add(f["ticker"])
                keep.append(f)
        return keep

    out = dict(out)
    screen = []
    for s in out.get("screen") or []:
        got = res.resolve(s.get("name"), s.get("ticker"))
        if got and got["symbol"] not in {x["ticker"] for x in screen}:
            screen.append({**s, "ticker": got["symbol"], "name": listed_name(got.get("name"), s.get("name"))})
    out["screen"] = screen
    out["clusters"] = [{**c, "companies": fix_all(c.get("companies") or [])} for c in out.get("clusters") or []]
    out["value_chain"] = [{**v, "companies": fix_all(v.get("companies") or [])} for v in out.get("value_chain") or []]
    funds = []
    for e in out.get("etfs") or []:
        got = res.resolve(e.get("name"), e.get("ticker"))
        if got and got["symbol"] not in {x["ticker"] for x in funds}:
            funds.append({"ticker": got["symbol"], "name": got["name"] or e.get("name") or ""})
    out["etfs"] = funds
    for k in ("summary", "core", "market_size"):
        out[k] = tidy_text(out.get(k))
    out["sub_themes"] = [{**x, "detail": tidy_text(x.get("detail"))} for x in out.get("sub_themes") or []]
    out["value_chain"] = [{**x, "description": tidy_text(x.get("description"))} for x in out.get("value_chain") or []]
    out["screen"] = [{**x, "one_line": tidy_text(x.get("one_line"))} for x in out.get("screen") or []]
    out["tailwinds"] = [tidy_text(x) for x in out.get("tailwinds") or []]
    out["risks"] = [tidy_text(x) for x in out.get("risks") or []]
    out["checked"] = True
    return out


def drop_unrelated(out: dict, industry_of) -> dict:
    """With `industry_of(symbol)` (the screener's stored industry), a listed company in "Who's in it" or the value chain
    whose industry shares nothing with the theme or with the industries of the theme's most direct names (the "Listed
    companies across the chain") is dropped as clearly unrelated (R6O-017: Reliance under "Missiles & Rocketry",
    Havells and MTNL under "Defence Electronics & Systems"). A company whose industry isn't known stays."""
    if not industry_of:
        return out

    def ind(sym):
        try:
            return industry_of(sym) if sym else None
        except Exception:
            return None
    direct = {x["ticker"] for x in out.get("screen") or []}
    core = _stems(out.get("sector"))
    for x in out.get("screen") or []:
        core |= _stems(ind(x["ticker"]))
    if not (out.get("screen") or []):
        return out                                  # nothing to measure against: the map stays as the AI gave it

    def keep(c):
        if not c.get("ticker") or c["ticker"] in direct:
            return True
        i = ind(c["ticker"])
        return not i or bool(_stems(i) & core)
    out["clusters"] = [{**c, "companies": [x for x in c.get("companies") or [] if keep(x)]} for c in out.get("clusters") or []]
    out["clusters"] = [c for c in out["clusters"] if c["companies"]]
    out["value_chain"] = [{**v, "companies": [x for x in v.get("companies") or [] if keep(x)]} for v in out.get("value_chain") or []]
    return out


# ---------- prose: facts only, every claim checked against the numbers given (R5O-018, R5O-027) ----------
# advice, forecasts and judgements, which no read may carry ("indicating limited upside", "sell it short")
ADVICE = re.compile(
    r"\b(buy|sell|hold|accumulate|avoid|short)\b\s+(the |this |its |these )?(stock|shares?|it|them|position)\b|\bsell\b[^.]{0,30}\bshort\b"
    r"|\bshort[- ]sell|\bgo short\b|\b(limited|more|further|significant|little|some|potential|further)\s+(upside|downside)\b|\bupside\b|\bdownside\b"
    r"|\b(target price|price target)s?\b|\bundervalued\b|\bovervalued\b|\b(cheap|expensive|bargain)\b|\battractive(ly)?\s+(valued|valuation|entry)\b"
    r"|\bworth (buying|owning|a look)\b|\boutlook\b|\bforecast|\bpredict|\bexpect(s|ed)?\s+to\b|\blikely to\b|\bpoised\b|\bset to\b"
    r"|\b(will|should|could|may|might)\s+(rise|fall|go|climb|drop|rally|gain|continue|outperform|underperform|benefit|recover|rebound|see|drive|lead|weigh|boost|pressure|support)\b"
    r"|\bopportunit(y|ies)\b|\bmultibagger\b|\b(good|great|right|ideal) time\b|\brecommend"
    # R12-004: a buy level or a pick repeated from a headline ("Jim Cramer set a buy level for Starbucks")
    r"|\bbuy[- ](level|point|zone|signal|range|alert)s?\b|\b(his|her|their) (take|picks?) on\b|\bstocks? to watch\b|\bbreakouts?\b"
    # a call on any subject, in any form ("buying chances", "a strong buy", "look like a buy", "add equities", "accumulate on dips")
    r"|\b(buy|buying|sell|selling|hold|holding)\s+(chances?|opportunit\w+|ideas?|calls?|ratings?|recommendations?|candidates?|(on|the) dips?)\b"
    r"|\b(a|an|the|strong|outright|clear|rated)\s+(strong\s+)?(buy|sell)\b(?!\s+(back|side|order|price|volume|rate))|\b(strong|clear) hold\b|\ba hold\b"
    r"|\b(you|investors?|traders?|buyers?)\s+(can|could|may|might|should|must|ought to|would do well to)\s+(buy|sell|hold|add|pick|accumulate|trim|load)\b"
    r"|\baccumulat(e|es|ing)\b|\bgo(ing)? long\b|\bgo(ing)? short\b|\bload(ing)? up\b|\bbuy(ing)? the dips?\b"
    r"|\badd(ing)?\s+(to\s+)?(equit\w+|stocks?|shares?|positions?|exposure|your|the (stock|shares)|it|them)\b"
    r"|\b(good|great|solid|safe|core|ideal|best)\s+(long[- ]term\s+)?(hold|holding)s?\b|\blong[- ]term (hold|holding)\b"
    r"|\b(top|better|best|safer|stock|favou?rite|my|our)\s+picks?\b|\bpick(ing)? (up )?(the |this )?(stock|shares|it|them)\b"
    r"|\bwinners?\b|\b(safer|better|best|smarter)\s+(choice|bet|option|investment|buy)\b|\b(a |the )(good|great|safe|smart|sound) (investment|bet)\b"
    r"|\battractive\b|\bprefer(s|red)?\s+(alpha|beta|the|this|that|it|\w+ (over|to))\b|\b(should|would|may|might|could|can) prefer\b"
    r"|\bworth (owning|holding|a place|adding|picking)\b|\bdeserves?\b|\bplace in (a|your|any|every) (\w+ )?(portfolio|watchlist)\b"
    r"|\bbargains?\b|\bstrong buy\b"
    # a forecast of a price level or a multiple ("will hit 25000", "will double by 2030")
    r"|\b(will|could|may|might|should|would|can|to|is set to|is likely to|is expected to)\s+(hit|reach|touch|cross|surpass|double|triple|quadruple|halve|soar|plunge|crash|tank|surge|skyrocket)\b(?<!\bto hit)(?<!\bto touch)(?<!\bto cross)(?<!\bto reach)", re.I)

# subjects a market read may mention only when a headline (or the facts) does: central banks, macro data, flows, sectors
TOPICS = ("fed", "federal reserve", "fomc", "minutes", "powell", "ecb", "boj", "rbi", "repo", "rate cut", "rate hike", "inflation",
          "cpi", "gdp", "payrolls", "jobs report", "unemployment", "tariff", "crude", "oil", "brent", "gold", "dollar", "rupee",
          "yield", "treasur", "bond", "fii", "dii", "foreign investors", "foreign funds", "inflow", "outflow", "rotat",
          "utilities", "energy stocks", "metal", "pharma", "it stocks", "information technology", "tech stocks", "technology stocks",
          "banks", "banking stocks", "financials", "auto", "fmcg", "realty", "real estate", "telecom", "media", "psu", "defence",
          "consumer", "healthcare", "industrials", "small-cap", "small cap", "mid-cap", "mid cap", "earnings season", "geopolit",
          "war", "election", "budget", "monsoon")
_NUM = re.compile(r"(?<![\w.])[-−+]?\d[\d,]*(?:\.\d+)?")
_PERIOD_AFTER = re.compile(r"^\s*(?:-|\s)?(?:day|days|week|weeks|month|months|year|years|candle|candles|period|session|sessions|quarter|quarters)\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z₹$\"'(])")


def _numbers(text: str) -> list[tuple[float, str]]:
    out = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(0).replace(",", "").replace("−", "-")
        try:
            v = float(raw)
        except ValueError:
            continue
        out.append((v, text[m.end():m.end() + 12]))
    return out


def fact_numbers(facts) -> list[float]:
    """Every number in the facts (values and numbers inside strings), with the usual unit steps (crore, lakh crore,
    billion, trillion) so "₹7.51 lakh crore" matches a market value of 7,51,000 crore."""
    pool: list[float] = []

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            pool.append(float(x))
        elif isinstance(x, str):
            pool.extend(v for v, _ in _numbers(x))
            for m in _MONEY.finditer(x):          # an amount with its unit ("₹3.1 lakh cr") as the whole amount too
                unit = _UNIT.get(re.sub(r"\s+", " ", (m.group(3) or "").lower()))
                if unit:
                    pool.append(float(m.group(2).replace(",", "")) * unit)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
    walk(facts)
    out = set()
    for p in pool:
        for k in (1, 1e-2, 1e-3, 1e-5, 1e-7, 1e-9, 1e-12, 100):
            out.add(abs(p * k))
    return sorted(out)


def number_backed(v: float, after: str, pool: list[float]) -> bool:
    """A number in the text is one of the facts' (to its rounding), a year, a small count, or a period length
    ("14-day", "50-day")."""
    a = abs(v)
    if v.is_integer() and (1900 <= a <= 2100 or a <= 12):
        return True
    if _PERIOD_AFTER.match(after or "") and a <= 500:
        return True
    tol = max(0.051, a * 0.012)
    from bisect import bisect_left
    i = bisect_left(pool, a - tol)
    return i < len(pool) and pool[i] <= a + tol


def _topics_backed(s: str, support: str) -> bool:
    low = s.lower()
    for t in TOPICS:
        if re.search(r"\b" + re.escape(t), low) and not re.search(r"\b" + re.escape(t), support):
            return False
    return True


def whole_sentences(text: str | None, cap: int) -> str:
    """At most `cap` characters, ending at the end of a sentence: never a read that stops mid-sentence, cut by a length
    cap or by the model running out of room (R51-005: "…while TCS uses Sep 2026" with no ending)."""
    t = " ".join(str(text or "").split())
    if len(t) > cap:
        t = t[:cap]
    if t and t[-1] not in ".!?\"'\u201d)":
        ends = [m.end() for m in re.finditer(r"[.!?][\"'\u201d)]?(?=\s|$)", t)]
        t = t[:ends[-1]] if ends else ""
    return t.strip()


def keep_sentences(text: str, pool: list[float], check=None) -> str:
    """The sentences of `text` that carry no advice or forecast, whose every number is in the facts, and that pass
    `check` (a claim test of the caller's). The rest are dropped, not rewritten."""
    kept = []
    for s in _SENT.split(" ".join(str(text or "").split())):
        if not s or ADVICE.search(s):
            continue
        if not all(number_backed(v, after, pool) for v, after in _numbers(s)):
            continue
        if check and not check(s):
            continue
        kept.append(s)
    return " ".join(kept)


# --- the market read ---
_BELOW_LOW = re.compile(r"\b(below|under|beneath|breach\w*|broke|breaking|fresh|new|record|lowest)\b[^.]{0,40}\b52[- ]week lows?\b"
                        r"|\b52[- ]week lows?\b[^.]{0,20}\b(breached|broken|hit|touched)\b|\b(new|fresh|record) lows?\b", re.I)
_NEAR_LOW = re.compile(r"\b(near|close to|at|around|just above|approach\w*)\b[^.]{0,30}\b52[- ]week lows?\b", re.I)
_HIGHS = re.compile(r"\b(above|fresh|new|record|all[- ]time)\b[^.]{0,30}\bhighs?\b|\b52[- ]week highs?\b[^.]{0,20}\b(hit|touched|crossed)\b", re.I)
_NEAR_HIGH = re.compile(r"\b(near|close to|at|around|just below|approach\w*)\b[^.]{0,30}\b(52[- ]week|record) highs?\b", re.I)


# "well below their 52-week highs", "far above its lows": a distance claim, held to every index the sentence speaks of
_FAR_BELOW_HIGH = re.compile(r"\b(well|far|deep(?:ly)?|sharply|significantly|substantially|much|way)\s+(below|under|off|short of)\b"
                             r"[^.]{0,30}\bhighs?\b", re.I)
_FAR_ABOVE_LOW = re.compile(r"\b(well|far|comfortably|significantly|substantially|much|way)\s+(above|over|off)\b[^.]{0,30}\blows?\b", re.I)
FAR_PCT = 5.0       # how far from a high or low "well below" or "far above" needs: a few percent is close, not far


def _spoken_of(s: str, indices: list[dict]) -> list[dict]:
    """The indices a sentence names (by full name, else by first word: "the Nifty"), else every one given ("all three
    indices")."""
    full = [i for i in indices if i.get("name") and re.search(r"(?<!\w)" + re.escape(str(i["name"])) + r"(?!\w)", s, re.I)]
    if full:
        return full
    first = [i for i in indices if i.get("name") and re.search(r"(?<!\w)" + re.escape(str(i["name"]).split()[0]) + r"(?!\w)", s, re.I)]
    return first or indices


def range_claims_ok(s: str, indices: list[dict]) -> bool:
    """A claim about 52-week lows or highs holds for at least one index given (R5O-018: "well below their 52-week
    lows" while NIFTY was above its low). "Well below" a high, or "far above" a low, holds only when every index the
    sentence speaks of is at least FAR_PCT away (DE-016: "All three indices closed well below their 52-week highs" with
    the S&P 500 2.8% below its high)."""
    lv = [(i.get("price"), i.get("low52"), i.get("high52")) for i in indices if i.get("price")]
    if _FAR_BELOW_HIGH.search(s) or _FAR_ABOVE_LOW.search(s):
        high = bool(_FAR_BELOW_HIGH.search(s))
        for i in _spoken_of(s, indices):
            p, lo, hi = i.get("price"), i.get("low52"), i.get("high52")
            ref = hi if high else lo
            if not (p and ref) or (high and p > ref * (1 - FAR_PCT / 100)) or (not high and p < ref * (1 + FAR_PCT / 100)):
                return False
        return half_claim_ok(s, indices)
    if _BELOW_LOW.search(s):
        return any(lo and p <= lo * 1.001 for p, lo, _ in lv)
    if _NEAR_LOW.search(s):
        return any(lo and p <= lo * 1.03 for p, lo, _ in lv)
    if _HIGHS.search(s):
        return any(hi and p >= hi * 0.995 for p, _, hi in lv)
    if _NEAR_HIGH.search(s):
        return any(hi and p >= hi * 0.97 for p, _, hi in lv)
    return half_claim_ok(s, indices)


_UPPER = re.compile(r"\b(upper|top) (half|end|part)\b", re.I)
_LOWER = re.compile(r"\b(lower|bottom) (half|end|part)\b", re.I)


def half_claim_ok(s: str, indices: list[dict]) -> bool:
    """"In the upper half of their 52-week ranges" holds only when each index it speaks of sits above the middle of its
    range (R58-001: NIFTY 4.36% above its low and 12.24% below its high is about a quarter of the way up, the lower half).
    The indices the sentence names, else every one given."""
    up, down = _UPPER.search(s), _LOWER.search(s)
    if not up and not down:
        return True
    named = [i for i in indices if i.get("name") and re.search(r"\b" + re.escape(str(i["name"]).split()[0]) + r"\b", s, re.I)]
    for i in named or indices:
        p, lo, hi = i.get("price"), i.get("low52"), i.get("high52")
        if not (p and lo and hi and hi > lo):
            continue
        where = (p - lo) / (hi - lo)
        if (up and where < 0.5) or (down and where > 0.5):
            return False
    return True


def direction_ok(s: str, indices: list[dict]) -> bool:
    """A sentence naming an index and saying it rose or fell agrees with its change on the day."""
    for i in indices:
        name, ch = str(i.get("name") or ""), i.get("change_pct")
        if ch is None or not name:
            continue
        short = name.split()[0]
        if not re.search(r"\b" + re.escape(short) + r"\b", s, re.I):
            continue
        up = re.search(r"\b(rose|gained|climbed|advanced|rallied|jumped|surged|up|higher)\b", s, re.I)
        down = re.search(r"\b(fell|lost|declined|dropped|slid|slipped|tumbled|sank|down|lower)\b", s, re.I)
        if up and not down and ch < 0 or down and not up and ch > 0:
            return False
    return True


def magnitude_ok(s: str, indices: list[dict]) -> bool:
    """A size claim agrees with the moves given: "double-digit percentage gains" needs a move of 10% or more
    (R28-004: said of indices up 1.7 to 2.1%)."""
    if not re.search(r"\bdouble[- ]digit\b", s, re.I):
        return True
    moves = [abs(i["change_pct"]) for i in indices if i.get("change_pct") is not None]
    return any(m >= 10 for m in moves)


_POINTS = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:-|\s)?points?\b", re.I)
_INDEX_WORDS = re.compile(r"\b(nifty|sensex|s&p|nasdaq|dow|index|indices|benchmark)\b", re.I)
_VIX_PCT = re.compile(r"\bvix\b[^.]*?\d[\d,]*(?:\.\d+)?\s*%|\d[\d,]*(?:\.\d+)?\s*%[^.]*?\bvix\b", re.I)


def index_moves_ok(s: str, indices: list[dict]) -> bool:
    """A day's move in points, or the VIX's move in percent, agrees with the levels the page shows, not with a headline
    written during the day (R70-002: "the India VIX jumped 6% … the Sensex and Nifty fell over 900 points" beside a VIX
    up 4.48% and a NIFTY down 257 points). A points figure must be one index's change within 2%; a VIX percentage needs
    the VIX among the levels given."""
    moves = []
    for i in indices:
        p, c = i.get("price"), i.get("change_pct")
        if p and c is not None and c > -100:
            moves.append(abs(p - p / (1 + c / 100)))
    # points of an index, not of a share price ("the stock rose 30 points" is a headline's to give)
    for m in (_POINTS.finditer(s) if _INDEX_WORDS.search(s) else ()):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if not any(abs(v - x) <= max(2.0, x * 0.02) for x in moves):
            return False
    if _VIX_PCT.search(s):
        vix = [abs(i["change_pct"]) for i in indices if "vix" in str(i.get("name") or "").lower() and i.get("change_pct") is not None]
        nums = [float(x.replace(",", "")) for x in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*%", s)]
        if not vix or not any(abs(n - v) <= 0.06 for n in nums for v in vix):
            return False
    return True


def session_headlines(headlines: list[dict], day) -> list[dict]:
    """The headlines dated on `day` or later; an older story is not today's news (R28-004: a 14 Oct line in the 15 Oct
    read). A headline with no date is kept."""
    iso = day.isoformat() if hasattr(day, "isoformat") else str(day)
    return [h for h in headlines if not str(h.get("at") or "")[:10] or str(h.get("at"))[:10] >= iso]


def market_facts(indices: list[dict]) -> list[dict]:
    """The index numbers the market read may use, with where each sits in its 52-week range spelt out."""
    out = []
    for i in indices:
        p, lo, hi = i.get("price"), i.get("low52"), i.get("high52")
        out.append({**i, "from_low_pct": round((p / lo - 1) * 100, 2) if p and lo else None,
                    "from_high_pct": round((p / hi - 1) * 100, 2) if p and hi else i.get("from_high_pct")})
    return out


def _card_inr(name: str) -> bool:
    """Whether an index card groups its level the Indian way (the NIFTYs and the SENSEX), as Research.tsx IndexStrip does."""
    return "NIFTY" in name.upper() or name.upper() == "SENSEX"


_INDEX_LEVEL = re.compile(r"(?<![\w.,₹$−+-])(\d{1,3}(?:,\d{2,3})+|\d{3,})(\.\d+)?(?!\d|,\d|\.\d|\s?%)")


def card_levels(text, indices: list[dict]):
    """The index levels in a read written as the index cards show them: whole points, grouped the card's way (DE-017:
    "22,600.0" and "73,123.83" in the text beside cards of 22,600 and 73,124). Only a number that is an index's level
    (to half a point) is touched; points moves, percentages and money stay as written."""
    if not isinstance(text, str) or not text:
        return text
    levels = [(float(i["price"]), _card_inr(str(i.get("name") or ""))) for i in indices
              if isinstance(i.get("price"), (int, float)) and i["price"] >= 100]

    def one(m):
        try:
            v = float((m.group(1) + (m.group(2) or "")).replace(",", ""))
        except ValueError:
            return m.group(0)
        for p, inr in levels:
            if abs(v - p) <= 0.51:
                return _grouped(float(int(p + 0.5)), 0, inr)        # Math.round's half-up, as the card rounds
        return m.group(0)
    return _INDEX_LEVEL.sub(one, text)


_COUNT_NAMES = {2: "both", 3: "all three", 4: "all four"}


def mood_line(indices: list[dict], sectors: dict | None = None, compare: dict | None = None) -> str:
    """The mood in plain words, worked out from the day's index moves (and StratLab's sector count and how big a day it is
    against the index's usual one, when there are those), so it is a fact of the numbers and never the AI's impression
    (DD-001: a read that recited the levels and gave no mood). The index levels and moves are not said again: the cards
    above carry them (MOOD-1). The wording is mood.headline_of's, the one the Market pulse tables are checked against."""
    from . import mood
    return mood.headline_of(indices, sectors, compare)


# the subjects a day's headlines are often about, for naming the main story when the AI gives none that holds (DD-001)
_STORIES = (("crude oil prices", r"\b(crude|brent|oil prices?)\b"), ("the rupee", r"\brupee\b"),
            ("interest rates", r"\b(rbi|repo|rate cuts?|rate hikes?|fed|federal reserve|fomc|interest rates?|monetary policy)\b"),
            ("inflation", r"\b(inflation|cpi|wpi)\b"), ("quarterly results", r"\b(q[1-4]|quarterly|results|earnings)\b"),
            ("foreign investors' flows", r"\b(fiis?|fpis?|foreign (?:investors|funds|portfolio))\b"),
            ("tariffs and trade", r"\b(tariffs?|trade (?:deal|war|talks|pact))\b"),
            ("geopolitics", r"\b(war|geopolitic\w*|ceasefire|sanctions?|missile|strikes? on)\b"),
            ("gold and silver", r"\b(gold|silver)\b"), ("bond yields", r"\b(bond|treasury) yields?\b"),
            ("technology shares", r"\b(it stocks|it shares|tech stocks|tech shares|technology stocks|chip\w*|semiconductor\w*|ai stocks)\b"),
            ("bank shares", r"\b(bank stocks|bank shares|banking stocks|psu banks|lenders)\b"))


def _phrase_stems(phrase: str) -> list[str]:
    return [w[:max(4, len(w) - 2)] for w in _cause_words(phrase)]


def headline_count(phrase: str, titles: list[str]) -> int:
    """How many headlines carry every word of a phrase (by stem, as cause_backed reads them)."""
    stems = _phrase_stems(phrase)
    if not stems:
        return 0
    return sum(1 for t in titles if all(re.search(r"\b" + re.escape(w), str(t or "").lower()) for w in stems))


def story_of(driver: str, titles: list[str]) -> dict | None:
    """The day's main story as the headlines tell it: {"label", "n", "of", "indices"} where `indices` are the positions in
    `titles` of the headlines that carry it. The AI's `driver` (every word of it in a headline) or the subject of _STORIES,
    whichever more headlines carry, at least two; None when no subject is in two. The page marks exactly these headlines,
    so "3 of 8" can be counted by eye (MOOD-1: "crude oil prices (3 of 8)" beside headlines none of which were about it)."""
    titles = [str(t or "") for t in titles]
    best, n, hits = "", 0, []
    d = " ".join(str(driver or "").split()).strip(" .")
    if d and len(d) <= 60 and not ADVICE.search(d) and not _PREVIEW.search(d) and not re.search(r"\d", d):
        stems = _phrase_stems(d)
        if stems:
            hits = [i for i, t in enumerate(titles) if all(re.search(r"\b" + re.escape(w), t.lower()) for w in stems)]
        best = d if d[:2].isupper() else d[:1].lower() + d[1:]           # "crude oil", but "RBI policy" as written
        n = len(hits)
    if n < 2:
        best, n, hits = "", 0, []
    for name, rx in _STORIES:            # a subject more headlines carry is the main story, the AI's naming ties
        got = [i for i, t in enumerate(titles) if re.search(rx, t, re.I)]
        if len(got) > n:
            best, n, hits = name, len(got), got
    if n < 2:
        return None
    return {"label": best, "n": n, "of": len(titles), "indices": hits}


def main_story(driver: str, titles: list[str]) -> str:
    """The sentence for story_of: "" when there is no story."""
    titles = [str(t or "") for t in titles if t]
    st = story_of(driver, titles)
    return f"The main story in today's headlines: {st['label']} ({st['n']} of {st['of']})." if st else ""


def flows_source(cash: dict | None) -> str:
    """Where the FII and DII figures a read quotes come from, said without naming any data vendor (DD-001)."""
    if not cash or not cash.get("as_of"):
        return ""
    try:
        from datetime import date as _date
        d = _date.fromisoformat(str(cash["as_of"])[:10])
        day = f"{d.day} {d.strftime('%b')}"
    except ValueError:
        return ""
    return f"FII and DII figures are the exchange's provisional cash-market numbers for {day}, in ₹ crore; the final ones can differ a little."


def template_tone(indices: list[dict]) -> str:
    """The market read from the numbers alone, when nothing the AI wrote survives the checks."""
    def pc(x):
        return f"{'+' if x > 0 else '−' if x < 0 else ''}{abs(x):.2f}%"
    parts = []
    for i in market_facts(indices)[:3]:
        if i.get("price") is None:
            continue
        bit = f"{i['name']} at {i['price']:,.2f}"
        if i.get("change_pct") is not None:
            bit += f", {pc(i['change_pct'])} on the day"
        if i.get("from_low_pct") is not None and i.get("from_high_pct") is not None:
            bit += f", {abs(i['from_low_pct']):.1f}% {'above' if i['from_low_pct'] >= 0 else 'below'} its 52-week low and {abs(i['from_high_pct']):.1f}% below its high"
        parts.append(bit + ".")
    return " ".join(parts)


# a claim about how many sectors moved, or that all of them did (R8B-004: "as all sectoral indices turned green", repeated
# from a headline, while NIFTY OIL & GAS closed 0.09% lower): kept only when StratLab's own sector count bears it out
_ALL_SECTORS = re.compile(r"\b(all|every|each|entire)\b[^.;]{0,25}\b(sector\w*|sectoral)\b|\bacross (all |the )?(sectors|the board)\b", re.I)
_COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16}
_N = r"(\d{1,2}|" + "|".join(_COUNT_WORDS) + r")"
_N_SECTORS = re.compile(rf"\b{_N}\b(?:\s+(?:of|out of)\s+(?:the\s+)?{_N}\b)?\s+(?:[a-z&]+\s+){{0,2}}?(?:sector\w*|sectoral)", re.I)
_EXCEPT = re.compile(r"\b(except|barring|but|other than|save for|apart from|bar)\b", re.I)
_GREEN = re.compile(r"\b(green|gain\w*|rose|risen|rising|higher|up|advanc\w*|positive|rall\w*|climb\w*)\b", re.I)
_RED = re.compile(r"\b(red|los[st]\w*|fell|fallen|falling|lower|down|declin\w*|negative|slipp?\w*|slid)\b", re.I)


def _count(w: str | None) -> int | None:
    if not w:
        return None
    return int(w) if w.isdigit() else _COUNT_WORDS.get(w.lower())


def sector_claims_ok(s: str, sectors: dict | None) -> bool:
    """A sentence that counts the sectors that rose or fell, or says all of them did, agrees with StratLab's own count
    (hub.sector_moves). Without that count no such claim is kept."""
    every, counted = _ALL_SECTORS.search(s), _N_SECTORS.search(s)
    if not every and not counted:
        return True
    if not sectors or not sectors.get("of"):
        return False
    up, down, total = int(sectors.get("up") or 0), int(sectors.get("down") or 0), int(sectors["of"])
    green, red = bool(_GREEN.search(s)), bool(_RED.search(s))
    if green == red:
        return False                                    # no clear direction: the claim can't be checked
    same, other = (up, total - up) if green else (down, total - down)
    if every and not counted:
        return other >= 1 if _EXCEPT.search(s) else same == total
    n, of = _count(counted.group(1)), _count(counted.group(2))
    return (of is None or of == total) and n == same


# R10O-004: the mood said "today's upward move suggests a reversal or stabilization of flows" and "strong domestic
# institutional interest", worked out from price moves, on the day StratLab's own Positioning page had the FIIs net
# selling ₹3,569 crore. A sentence about who is buying or selling is kept only when the day's FII and DII figures bear
# its direction out, and one that infers flows from the market's moves is dropped.
_FII = r"fiis?|fpis?|foreign\b[^.,;]{0,30}?\b(?:investors?|funds?|institutions?|flows?|money|selling|buying|outflows?|inflows?|exodus)"
_DII = r"diis?|domestic\b[^.,;]{0,30}?\b(?:investors?|institutions?|funds?|flows?|money|buying|selling|inflows?|outflows?)|mutual funds?"
_FLOWY = re.compile(rf"\b(?:{_FII}|{_DII}|institutional|flows?|inflows?|outflows?|exodus)\b", re.I)
_FII_RX, _DII_RX = re.compile(rf"\b(?:{_FII})\b", re.I), re.compile(rf"\b(?:{_DII})\b", re.I)
_SELL = re.compile(r"\b(sell\w*|sold|outflows?|exodus|withdr\w+|pull\w* out|pulled|exit\w*|dump\w*|offload\w*|net sellers?)\b", re.I)


def flow_text(s: str) -> bool:
    """Whether a text is about the institutions' flows (FIIs, DIIs), the one kind the day's figures can back."""
    return bool(re.search(rf"\b(?:{_FII}|{_DII})\b", s, re.I))


_BUY = re.compile(r"\b(buy\w*|bought|inflows?|net buyers?|purchas\w+|pour\w*|accumulat\w*)\b", re.I)
_INFER = re.compile(r"\b(revers\w*|stabili[sz]\w*|indicat\w*|suggest\w*|signal\w*|reflect\w*|impl\w*|point(?:s|ing)? to|hint\w*|"
                    r"reveal\w*|interest|appetite|confidence|sentiment)\b", re.I)
_CLAUSE = re.compile(r"[;,]|\b(?:while|whereas|but|and|as)\b", re.I)


def flow_claim_ok(s: str, cash: dict | None) -> bool:
    """A sentence about institutional flows ("FIIs sold", "domestic funds bought", "outflows") agrees with the day's
    FII and DII figures `cash` ({"fii": {"net"}, "dii": {"net"}}): the direction is the one the net figure has, for the
    holder it names. A sentence that infers flows or their interest from price moves is dropped; without the day's
    figures a direction can't be checked, so only what a headline reports stays."""
    if not _FLOWY.search(s or ""):
        return True
    if _INFER.search(s):
        return False
    if not cash:
        return True
    for clause in _CLAUSE.split(s):
        sell, buy = bool(_SELL.search(clause)), bool(_BUY.search(clause))
        if not (sell or buy):
            continue
        fii, dii = bool(_FII_RX.search(clause)), bool(_DII_RX.search(clause))
        if fii == dii or (sell and buy):               # no holder named, both named, or both directions: can't be checked
            return False
        net = ((cash.get("fii") if fii else cash.get("dii")) or {}).get("net")
        if not isinstance(net, (int, float)) or (sell and net >= 0) or (buy and net <= 0):
            return False
    return True


def flow_facts(cash: dict | None) -> dict | None:
    """The day's FII and DII figures in ₹ crore as the model reads them, from positioning.cash_today(); None when the
    day's numbers aren't in."""
    if not cash or cash.get("status") != "ok" or not (cash.get("fii") and cash.get("dii")):
        return None
    out = {"as_of": cash.get("as_of")}
    for who in ("fii", "dii"):
        row = cash[who]
        out.update({f"{who}_{k}_crore": row.get(k) for k in ("buy", "sell", "net") if row.get(k) is not None})
    return out


# a sentence that gives a reason for the market's or a sector's move: what follows "because", "driven by", "helped by"…,
# or what comes before "helped", "lifted", "drove"… (R13-011: "strong earnings helped lift most sectors")
_CAUSE_AFTER = re.compile(r"\b(?:because of|because|due to|driven by|thanks to|on the back of|fuel(?:l)?ed by|boosted by|lifted by|"
                          r"helped by|supported by|weighed (?:down )?by|dragged (?:down )?by|pressured by|spurred by|amid)\b(.+)$", re.I)
_CAUSE_BEFORE = re.compile(r"^(.+?)\b(?:helped|helps|lifted|lifts|boosted|boosts|drove|drives|driven|fuel(?:l)?ed|spurred|propelled|pushed|"
                           r"weighed on|dragged|pressured|sent|prompt(?:ed|ing|s)|trigger(?:ed|ing|s)|spark(?:ed|ing|s)|caus(?:ed|ing|es)|"
                           r"led to|leading to|resulting in|resulted in)\b(?!\s+by\b)", re.I)
_PREVIEW = re.compile(r"\b(on tap|ahead|set for|await\w*|expected|could|may|might|preview|what to (watch|expect)|week ahead|look(s|ing)? ahead|due)\b", re.I)
_PLAIN = {"strong", "weak", "solid", "robust", "the", "a", "an", "and", "of", "in", "on", "for", "with", "its", "their", "most",
          "some", "many", "several", "investors", "market", "markets", "stocks", "shares", "index", "indices", "sector", "sectors",
          "gains", "gain", "losses", "loss", "higher", "lower", "rise", "fall", "move", "moves", "session", "day", "today",
          "broad", "broader", "news", "data", "reports", "report", "renewed", "continued", "positive", "negative", "upbeat",
          "optimism", "pessimism", "sentiment", "mood", "buying", "selling", "pressure", "interest"}


def _cause_words(clause: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z'&-]{3,}", clause.lower()) if w not in _PLAIN]


def cause_backed(s: str, headlines: list[str]) -> bool:
    """A sentence that gives a cause for a move is kept only when one headline on the page reports that cause: every word
    of the cause is in a single headline that reports it as having happened (not a preview, "with earnings on tap"). A
    sentence giving no cause is kept. R13-011: "strong earnings helped lift most sectors, with nine advancing and two
    falling" stood on "Wall Street set for weekly gains with earnings, inflation data on tap"."""
    text = " ".join(str(s or "").split())
    m = _CAUSE_AFTER.search(text)              # "…, driven by X", "… because of X": the cause follows
    clause = m.group(1) if m else None
    if clause is None:
        m = _CAUSE_BEFORE.search(text)         # "X helped lift …": the cause comes first
        clause = m.group(1) if m else None
    if clause is None:
        return True
    words = _cause_words(clause)
    if not words:
        return False                       # a cause in words that name nothing ("strong buying"): not backed by anything
    for h in headlines:
        low = str(h or "").lower()
        if not _PREVIEW.search(low) and all(re.search(r"\b" + re.escape(w[:max(4, len(w) - 2)]), low) for w in words):
            return True
    return False


# MOOD-1: a line about a sector agrees with that sector's own move in StratLab's sector table ("Bank and financial sector drag:
# banks and financial stocks dragged the market" stood beside NIFTY BANK +0.54% and 15 of 16 sector indices up)
_DOWNISH = re.compile(r"\b(fell|falls?|falling|drag\w*|weigh\w*|slid\w*|slump\w*|drop\w*|declin\w*|lower|loss\w*|lost|weak\w*|pressur\w*|sank|"
                      r"tumbl\w*|retreat\w*|red|dip\w*|sell-?off|negative)\b", re.I)
_UPISH = re.compile(r"\b(rose|rises?|risen|rising|gain\w*|lift\w*|rall\w*|higher|advanc\w*|climb\w*|jump\w*|surg\w*|boost\w*|strong\w*|green|firm\w*|positive)\b", re.I)
_MOST = re.compile(r"\b(most|majority|many|bulk)\b[^.;]{0,20}\b(sector\w*|sectoral)", re.I)


def sector_direction_ok(s: str, sectors: dict | None) -> bool:
    """A clause that names a sector (bank, IT, pharma, real estate…) and says which way it went agrees with that sector
    index's day in the sector table: never "dragged" a sector that rose, never "gained" one that fell. A clause with both
    directions, or none, can't be checked and stands. "Most sectors" is held to the table's counts too."""
    from .mood import SECTOR_WORDS, sgn
    rows = (sectors or {}).get("rows") or []
    if not rows:
        return True
    for clause in _CLAUSE.split(s or ""):
        up, down = bool(_UPISH.search(clause)), bool(_DOWNISH.search(clause))
        if up == down:
            continue
        if _MOST.search(clause) and sectors.get("of"):
            half = sectors["of"] / 2
            if (up and sectors.get("up", 0) < half) or (down and sectors.get("down", 0) < half):
                return False
        for r in rows:
            rx = SECTOR_WORDS.get(r.get("name"))
            if rx and re.search(rx, clause, re.I):
                d = sgn(r.get("change_pct"))
                if (down and d > 0) or (up and d < 0):
                    return False
    return True


_STOP = set("that this with from have been were which while their about after over into than also more most such only amid said says will would could "
            "should being other these those there where when what they them then some many much very just like year years week today market markets "
            "stocks shares share stock investors company companies index indices sector sectors percent crore billion million trillion higher lower "
            "rose fell gains losses".split())


def _stems(text: str, ignore: str = "") -> set[str]:
    skip = {w[:max(4, len(w) - 2)] for w in re.findall(r"[a-z][a-z'&-]{3,}", ignore.lower())}
    return {st for st in (w[:max(4, len(w) - 2)] for w in re.findall(r"[a-z][a-z'&-]{3,}", str(text or "").lower())
                          if w not in _PLAIN and w not in _STOP) if st not in skip}


def grounded_in(text: str, sources: list[str], share: float = 0.75, ignore: str = "") -> bool:
    """Whether the words that carry a line (not filler, not the company's own name) are in the headlines it must come from:
    at least `share` of them, matched by stem. A line whose words are mostly not in any headline is the AI's own and
    is dropped (MOOD-1: "Reliance bought shares, prompting a lift in the indices" from a headline about something else)."""
    stems = _stems(text, ignore)
    if not stems:
        return True
    src = " ".join(str(x or "") for x in sources).lower()
    return sum(1 for w in stems if re.search(r"\b" + re.escape(w), src)) / len(stems) >= share


def plain_title(t: str) -> str:
    """A headline as a one-liner: without the " - Source" a news feed adds, at most 160 characters."""
    t = re.sub(r"\s+[-\u2013|]\s+[^-\u2013|]{2,40}$", "", " ".join(str(t or "").split()))
    return t if len(t) <= 160 else t[:157].rsplit(" ", 1)[0] + "…"


def ground_pulse(out: dict, indices: list[dict], headlines: list[dict], sectors: dict | None = None, cash: dict | None = None) -> dict:
    """The market read with only what the index numbers and the headlines support: a sentence with a number not in
    them, a 52-week claim the levels contradict, a move the wrong way, a central bank, flow or sector no headline
    names, or any advice or outlook is dropped; a company is listed only when a headline names it (R5O-018). `cash` is
    the day's FII and DII figures (flow_facts): a sentence on who bought or sold agrees with them (R10O-004)."""
    facts = market_facts(indices)
    support = " ".join(str(h.get("headline") or "") for h in headlines).lower()
    flows = flow_facts(cash) if cash and "status" in cash else cash
    pool = fact_numbers({"i": facts, "h": [h.get("headline") for h in headlines], "c": flows, "s": (sectors or {}).get("rows")})
    nets = {w: {"net": flows.get(f"{w}_net_crore")} for w in ("fii", "dii")} if flows else None
    if flows:                       # the day's figures name the institutions: FIIs, DIIs and their flows are backed
        support += " fii dii foreign investors foreign funds inflow outflow"

    titles = [str(h.get("headline") or "") for h in headlines]
    # what a line may also stand on besides a headline: the figures themselves (an index moved, so many sector indices rose, the
    # institutions' net), in the words that describe them
    figure_words = " ".join(str(i.get("name") or "") + " closed rose fell gained lost up down range high low" for i in indices)
    figure_words += " sector sectors sectoral rose fell up down green red" if sectors else ""
    figure_words += " foreign domestic institutions institutional bought sold net netted buyers sellers inflow outflow" if flows else ""
    backed_by = titles + [figure_words]

    def claim(s):
        return (range_claims_ok(s, facts) and magnitude_ok(s, facts) and index_moves_ok(s, facts) and direction_ok(s, facts) and _topics_backed(s, support) and sector_claims_ok(s, sectors)
                and sector_direction_ok(s, sectors) and flow_claim_ok(s, nets) and cause_backed(s, titles))
    res = dict(out)
    # the read says why the market moved, as the headlines report it; it does not say the levels again (the cards carry
    # them) and is never made up from the numbers when nothing survives the checks (MOOD-1)
    # a sentence with figures in it stands on the figures (every one is checked against the facts); one without stands on the words
    # of a headline, or it is the AI's own
    stands = lambda s: bool(re.search(r"\d", s)) or grounded_in(s, backed_by, 0.6)          # noqa: E731
    res["tone"] = keep_sentences(out.get("tone"), pool, lambda s: claim(s) and stands(s))
    named = lambda x: bool(x) and str(x).lower() in support          # noqa: E731
    hot = []
    for h in out.get("hot") or []:
        if not (named(h.get("name")) or named(h.get("ticker"))):
            continue
        mine = [t for t in titles if any(x and re.search(r"\b" + re.escape(str(x).lower()) + r"\b", t.lower()) for x in (h.get("name"), h.get("ticker")))]
        why = keep_sentences(h.get("why"), pool, claim)
        # one line per company: the AI's own words only while they stand on the headlines that name it, else the headline itself
        if not mine:
            continue
        if not why or not grounded_in(why, mine, 0.8, ignore=f"{h.get('name') or ''} {h.get('ticker') or ''}"):
            why = plain_title(mine[0])
        hot.append({**h, "why": why})
    res["hot"] = hot
    both = lambda s: claim(s) and stands(s)          # noqa: E731
    res["flows"] = [{**f, "detail": keep_sentences(f.get("detail"), pool, both)} for f in out.get("flows") or []]
    res["flows"] = [f for f in res["flows"] if f["detail"] and _topics_backed(f.get("title") or "", support) and flow_claim_ok(f.get("title") or "", nets)
                    and sector_direction_ok(f.get("title") or "", sectors)]
    res["themes"] = [{**t, "detail": keep_sentences(t.get("detail"), pool, both)} for t in out.get("themes") or []]
    res["themes"] = [t for t in res["themes"] if t["detail"] and (not t.get("example") or named(t.get("example")))]
    res["checked"] = True
    return res


_OPEN_WORDS = [(re.compile(r"\b(opened|opens|started|began)\b", re.I), "closed"),
               (re.compile(r"\b(is|are) (trading|opening)\b", re.I), "closed"),
               (re.compile(r",?\s*\b(in early trade|at the open(ing)?|in (the )?morning trade|this morning)\b", re.I), "")]


def closed_words(read: dict) -> dict:
    """The market read after the close in the past tense of the close: "opened sharply lower" becomes "closed sharply
    lower", and "in early trade" goes (R6O-025: a read at 23:00 IST said the NIFTY "opened sharply lower" at the
    day's closing level)."""
    def fix(t):
        if not isinstance(t, str):
            return t
        for rx, to in _OPEN_WORDS:
            t = rx.sub(lambda m: (to[:1].upper() + to[1:]) if to and m.group(0)[:1].isupper() else to, t)
        return re.sub(r"\s{2,}", " ", t).strip()
    out = dict(read)
    out["tone"] = fix(read.get("tone"))
    for k, f in (("hot", "why"), ("flows", "detail"), ("themes", "detail")):
        out[k] = [{**x, f: fix(x.get(f))} for x in read.get(k) or []]
    return out


# --- the company read ---
def fiscal_quarter(today, region: str) -> tuple[int, int]:
    """(quarter, fiscal year) of the last quarter that has ended, in India's April-March year: on 8 Oct 2026 that is
    Q2 FY2027 (July to September 2026)."""
    y, m = today.year, today.month
    q_end_month = ((m - 1) // 3) * 3          # the month the last full calendar quarter ended (0 = December last year)
    if q_end_month == 0:
        y, q_end_month = y - 1, 12
    fy = y + 1 if q_end_month >= 4 else y
    q = {6: 1, 9: 2, 12: 3, 3: 4}[q_end_month]
    return q, fy


_FYQ = re.compile(r"\bQ([1-4])\s*FY\s*'?(\d{4}|\d{2})\b", re.I)


def fix_fiscal_labels(text: str, today, region: str) -> str:
    """An Indian company's "Q2 FY2026" for results due now becomes "Q2 FY2027": a quarter label more than a year
    behind the last quarter that ended is the AI's calendar slip, not a fact (R5O-027)."""
    if region != "IN" or not text:
        return text
    q_now, fy_now = fiscal_quarter(today, region)

    def fix(m):
        q, fy = int(m.group(1)), int(m.group(2))
        fy = fy + 2000 if fy < 100 else fy
        if (fy_now - fy) * 4 + (q_now - q) >= 3:       # three quarters or more behind: the label is a year off
            fy = fy + max(1, (fy_now * 4 + q_now - (fy * 4 + q)) // 4)
        return f"Q{q} FY{fy}"
    return _FYQ.sub(fix, text)


def ground_company(read: dict, facts: dict, region: str, today) -> dict:
    """The company read with only what the facts support: no advice, forecasts or judgements ("indicating limited
    upside"), no number that isn't in the facts ("a typical range of 20-30"), and Indian fiscal-quarter labels
    that match the calendar. Trading ideas are rules to test, worded as such, never instructions (R5O-027).

    Every figure is also checked against the page's own table (R6O-001): a CAGR is worked out again from the yearly
    sales and profit, a year's sales, profit, growth or margin must be that year's, a labelled figure (dividend yield,
    P/E, the 1-year return) must be the page's own, a date must be one the facts carry, and a year or quarter already
    reported is never "estimated", "upcoming" or "due"."""
    page = PageFacts(facts, region, today)
    pool = fact_numbers({"facts": facts, "derived": page.derived()})     # with what the table gives: growth, CAGRs, margins
    sym = str(facts.get("symbol") or "")
    res = dict(read)
    fy = lambda t: fix_fiscal_labels(t, today, region)        # noqa: E731
    # a sentence that gives a cause ("...which has driven a recent 2% stock surge") stands only on a headline on the page that reports it
    # (RC2A-026: a RELIANCE read called the Jio IPO's subscription the cause of a 2% surge no headline or price on the page showed)
    titles = [str(h) for h in facts.get("recent_headlines") or []]
    backed = lambda check: (lambda s: check(s) and cause_backed(s, titles))        # noqa: E731
    for k in ("summary", "valuation_note", "position"):
        res[k] = base_noted(keep_sentences(read.get(k) or "", pool, backed(page.check)), facts)
    for k in ("bull", "bear", "watch"):
        check = backed(page.check_watch if k == "watch" else page.check)
        res[k] = [x for x in (base_noted(keep_sentences(fy(str(i)) if k == "watch" else str(i), pool, check), facts) for i in read.get(k) or []) if x]
    ideas = []
    for i in read.get("ideas") or []:
        text = rule_words(str(i.get("text") or ""), sym)
        if not text:
            continue
        # a rule made of a typed-in price, or titled for an indicator it doesn't use, tests nothing (R10O-005)
        if hardcodes_price(text, facts.get("price")) or not idea_uses_what_it_names(i.get("title"), text):
            continue
        ideas.append({**i, "text": text, "why": keep_sentences(str(i.get("why") or ""), pool, backed(page.check))})
    res["ideas"] = ideas
    res["checked"] = True
    return res


_BASE_WORDS = re.compile(r"one-off|base effect|moved by|other income|tax rate|exceptional|unusual", re.I)


def base_noted(text: str, facts: dict) -> str:
    """A line that measures a change against a quarter the quarterly table shows was moved by a one-off (other income several times the
    usual, a tax rate far off it) says so in the same line, as the Key numbers card does (RC2A-026: "Profit growth YoY June 2026 vs
    June 2025 is −24.6%" in Notable figures, with no word of June 2025's ₹15,119 crore of other income)."""
    if not text or not re.search(r"\d", text) or _BASE_WORDS.search(text):
        return text
    for e in facts.get("base_effect_items") or []:
        q = str(e.get("quarter") or "").split()
        if len(q) != 2 or not q[1].isdigit():
            continue
        if re.search(rf"\b{re.escape(q[0])}[a-z]*\.?\s+{q[1]}\b", text, re.I):
            return f"{text.rstrip('. ')} ({str(e.get('text') or '').split(':')[0]})."
    return text


_LEAD = re.compile(r"^\s*(?:(buy|go long(?: on)?|purchase)|(sell(?:\s+\S+)?\s+short|short[- ]sell|short|go short(?: on)?))\s+(?:(?:the\s+)?(?:stock|shares)\s+(?:of\s+)?)?", re.I)


def rule_words(text: str, symbol: str) -> str:
    """A trading idea as a rule to test, not an instruction: "Buy AAPL when …" becomes "Enter long when …",
    "Sell AAPL short when …" becomes "Enter short when …". An idea that isn't a rule (no "when") is dropped."""
    t = " ".join(text.split())
    if symbol:
        t = re.sub(r"\b(buy|sell|short)\s+" + re.escape(symbol) + r"\b", r"\1", t, flags=re.I)
    m = _LEAD.match(t)
    if m:
        t = ("Enter short " if m.group(2) else "Enter long ") + t[m.end():]
    t = re.sub(r"\bsell (it|the position|the trade)\b", "exit", t, flags=re.I)
    t = re.sub(r"\bsell when\b", "exit when", t, flags=re.I)
    t = re.sub(r"\bbuy back when\b", "exit when", t, flags=re.I)
    if not re.search(r"\bwhen\b", t, re.I) or ADVICE.search(re.sub(r"\b(short|exit|enter)\b", "", t, flags=re.I)):
        return ""
    return t[:1].upper() + t[1:]


# ---------- the company read against the page's own table (R6O-001) ----------
_MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_ISO = re.compile(r"\b(20\d\d)[-\u2010\u2011\u2012\u2013](\d\d)[-\u2010\u2011\u2012\u2013](\d\d)\b")   # any hyphen a model writes (R8B-003)
_DMY = re.compile(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(20\d\d)\b", re.I)
_MDY = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d\d)\b", re.I)
_QLABEL = re.compile(r"\bQ([1-4])\s*(?:of\s+)?(?:FY|fiscal(?:\s+year)?)\s*'?(\d{4}|\d{2})\b", re.I)
_FYEAR = re.compile(r"\b(?:FY\s*'?|fiscal(?:\s+year)?\s+)(\d{4}|\d{2})\b", re.I)
_MONEY = re.compile(r"(?:(₹|rs\.?|inr|\$|usd|€|eur)\s*)?(\d[\d,]*(?:\.\d+)?)\s*(lakh\s+crore|lakh\s+cr\b|crore|cr\b|billion|bn\b|b\b|million|mn\b|m\b|trillion|tn\b|t\b|lakh)?", re.I)
_UNIT = {"lakh crore": 1e12, "lakh cr": 1e12, "crore": 1e7, "cr": 1e7, "billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mn": 1e6,
         "m": 1e6, "trillion": 1e12, "tn": 1e12, "t": 1e12, "lakh": 1e5}
_PCT = re.compile(r"([-−+]?\d+(?:\.\d+)?)\s?(?:%|per\s?cent\b|percent\b)", re.I)
_SUBJECT = [("eps", re.compile(r"\b(eps|earnings per share)\b", re.I)),
            ("revenue", re.compile(r"\b(revenue|revenues|sales|turnover|top[- ]line)\b", re.I)),
            ("profit", re.compile(r"\b(net profit|net income|profit|profits|earnings|bottom[- ]line|pat)\b", re.I)),
            ("price", re.compile(r"\b(share price|stock price|price|shares|stock|return)\b", re.I))]
_MOVE = re.compile(r"\b(?:(rose|grew|increased|climbed|improved|expanded|jumped)|(fell|declined|dropped|decreased|shrank|slipped|contracted))\b", re.I)
_LATEST = re.compile(r"\b(latest|most recent|last reported|last full|last fiscal|this) (fiscal )?year\b|\bin the latest year\b", re.I)
_AHEAD = re.compile(r"\b(estimat\w*|upcoming|due|expected|projected|forecast\w*|scheduled|will (report|announce|release|be)|ahead|next|to be (reported|announced|released)|later (today|this))\b", re.I)
_RESULTS = re.compile(r"\b(results?|earnings|report(s|ed|ing)?|release)\b", re.I)
# a label on the business or its figures, which the read must leave to the reader ("strong earnings momentum", "a
# forward P/E of 9.45 indicating low valuation", "indicating leverage exposure")
JUDGE = re.compile(r"\b(strong|weak|healthy|poor|excellent|robust|solid|impressive|stellar|sluggish)\b"
                   r"|\b(stronger|weaker|healthier|safer|superior|inferior|more (attractive|robust|resilient|solid))\b"
                   # "X is better" / "is the better" with nothing factual after it ranks; "better than estimates" does not
                   r"|\bis (the )?better\b(?!\s+than\s+(estimates|expectations|forecasts|consensus|last|the (prior|previous|same)|a year|peers|analysts|\d))"
                   r"|\b(low|high|rich|stretched|modest|lofty|full|undemanding|demanding|reasonable) valuation\b"
                   r"|\b(indicating|suggesting|signalling|signaling)\b", re.I)
_WATCH_PAST = re.compile(r"\b(actual|reported|beat|beats|missed|came in)\b", re.I)

# how big a gap the words make it: "slightly ahead" needs a small one, "far ahead" a large one (DD-061: profit growth of
# 14.9% against 6.3%, more than double, called "slightly ahead")
_SMALL_GAP = re.compile(r"\b(slightly|marginally|a little|a bit|modestly|somewhat|narrowly|fractionally|just)\b\s+"
                        r"(ahead|higher|faster|lower|slower|behind|better|more|less|above|below|greater|bigger|smaller)\b", re.I)
_BIG_GAP = re.compile(r"\b(far|much|well|significantly|substantially|considerably|sharply|vastly|markedly)\s+"
                      r"(ahead|higher|faster|lower|slower|behind|above|below|greater|bigger|smaller|more|less)\b", re.I)
_VS = re.compile(r"\s(?:vs\.?|versus|against|compared (?:with|to)|over)\s", re.I)
_PCT_NUM = re.compile(r"[-−+]?\d[\d,]*(?:\.\d+)?(?=\s?%)")


def _gap_pairs(s: str) -> list[tuple[float, float]]:
    """The figures a comparison sets against each other: "11.2% and 14.9% vs 10.7% and 6.3%" pairs 11.2 with 10.7 and
    14.9 with 6.3. Only when each side of the "vs" has as many percentages as the other."""
    parts = _VS.split(s, maxsplit=1)
    if len(parts) != 2:
        return []
    num = lambda t: [float(x.replace(",", "").replace("−", "-")) for x in _PCT_NUM.findall(t)]       # noqa: E731
    left, right = num(parts[0]), num(parts[1])
    return list(zip(left, right)) if left and len(left) == len(right) else []


def degree_ok(s: str) -> bool:
    """A sentence that sizes a gap agrees with its own figures: "slightly" only when every pair is close (within 25%
    of the larger and 3 points), "far" or "much" only when one pair is wide apart (DD-061). A sentence without pairs
    of figures to check is kept."""
    small, big = _SMALL_GAP.search(s), _BIG_GAP.search(s)
    if not small and not big:
        return True
    pairs = _gap_pairs(s)
    if not pairs:
        return True

    def wide(x, y):
        hi, lo = max(abs(x), abs(y)), min(abs(x), abs(y))
        return abs(x - y) > 3 or (hi > 0 and (hi - lo) / hi > 0.25) or (x < 0) != (y < 0)
    if small and any(wide(x, y) for x, y in pairs):
        return False
    if big and not any(wide(x, y) for x, y in pairs):
        return False
    return True


def _fy_num(t: str) -> int:
    y = int(t)
    return y + 2000 if y < 100 else y


def _dp(text: str) -> int:
    return len(text.split(".", 1)[1]) if "." in text else 0


def _close(stated: float, want: float, dp: int, slack: float = 0.1) -> bool:
    """A stated percentage agrees with the page's to its own rounding (and a tenth of a point for two ways of
    working the same figure out)."""
    return abs(stated - want) <= max(0.051, 0.5 * 10 ** -dp) + slack


def _num_in(text) -> float | None:
    m = _NUM.search(str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "").replace("−", "-"))
    except ValueError:
        return None


def num_or_none(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return _num_in(v)


def json_text(x) -> str:
    import json
    return json.dumps(x, ensure_ascii=False, default=str)


def dates_in(text: str) -> list[str]:
    """Every date written in a text, as YYYY-MM-DD: 2026-10-08, 8 Oct 2026, October 8, 2026."""
    out = []
    for m in _ISO.finditer(text or ""):
        out.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    for m in _DMY.finditer(text or ""):
        out.append(f"{m.group(3)}-{_MONTHS[m.group(2)[:3].lower()]:02d}-{int(m.group(1)):02d}")
    for m in _MDY.finditer(text or ""):
        out.append(f"{m.group(3)}-{_MONTHS[m.group(1)[:3].lower()]:02d}-{int(m.group(2)):02d}")
    return out


def quarter_end(label: str) -> tuple[int, int] | None:
    """(year, month) a results column ends: "Sep 2026" is (2026, 9); "2026-06-30" is (2026, 6)."""
    s = str(label or "").strip()
    m = re.match(r"^(20\d\d)-(\d\d)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d\d)", s, re.I)
    if m:
        return int(m.group(2)), _MONTHS[m.group(1)[:3].lower()]
    return None


def india_quarter(q: int, fy: int) -> tuple[int, int]:
    """(year, month) an Indian fiscal quarter ends: Q2 FY2027 is July to September 2026, so (2026, 9)."""
    return {1: (fy - 1, 6), 2: (fy - 1, 9), 3: (fy - 1, 12), 4: (fy, 3)}[q]


def india_label(end: tuple[int, int]) -> str:
    """"Q2 FY2027" for the quarter that ends in September 2026."""
    y, m = end
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(m)
    return f"Q{q} FY{y + 1 if m >= 6 else y}" if q else ""


class PageFacts:
    """The page's own figures, in the shapes a sentence's claims are checked against: the yearly table (and what it
    gives: growth, CAGRs and margins), the labelled Key numbers, the dates the facts carry and the latest quarter
    reported. A claim of a kind the page can't check falls back to "the number is somewhere in the facts"."""

    def __init__(self, facts: dict, region: str, today):
        self.region, self.today = region, today
        trend = facts.get("annual_trend") or {}
        self.unit = 1e7 if "cr" in str(trend.get("unit") or "").lower() else 1.0
        self.series: dict[str, dict[int, float]] = {}
        for kind in ("revenue", "profit"):
            rows = {}
            for p in trend.get(kind) or []:
                m = re.search(r"(\d{2,4})", str(p.get("y") or ""))
                v = num_or_none(p.get("v"))
                if m and v is not None:
                    rows[_fy_num(m.group(1))] = v
            if rows:
                self.series[kind] = rows
        years = sorted({y for s in self.series.values() for y in s})
        self.years, self.latest = years, (years[-1] if years else None)
        self.labelled = self._labelled(facts)
        self.dates = set(dates_in(json_text(facts))) | {today.isoformat()}
        res = facts.get("results") or {}
        self.last_q = quarter_end(res.get("latest_quarter_end") or res.get("latest_quarter") or "")
        self.status = res.get("status")
        self.next_day = res.get("next_results_date")

    @staticmethod
    def _labelled(facts: dict) -> list[tuple[str, float]]:
        """("group: label", value) for every labelled figure: the Key numbers, the margins, the plain-number rows."""
        out = []
        for k, v in (facts.get("metrics") or {}).items():
            n = num_or_none(v)
            if n is not None:
                out.append((str(k).lower(), n))
        for k, v in (facts.get("margins") or {}).items():
            n = num_or_none(v)
            if n is not None:
                out.append((f"{k} margin", n))
        for row, items in (facts.get("key_facts") or {}).items():
            for k, t in (items or {}).items():
                if "→" in str(t):              # "26% → 27% → 26% (FY22 to FY26)": each year's figure
                    for x in re.findall(r"[-−]?\d+(?:\.\d+)?(?=%)", str(t)):
                        out.append((f"{row}: {k}".lower(), float(x.replace("−", "-"))))
                    continue
                n = _num_in(t)
                if n is not None:
                    out.append((f"{row}: {k}".lower(), n))
        if facts.get("day_change_pct") is not None:
            out.append(("day change", float(facts["day_change_pct"])))
        return out

    # --- what the table gives ---
    def value(self, kind: str, year: int) -> float | None:
        return (self.series.get(kind) or {}).get(year)

    def yoy(self, kind: str, year: int) -> float | None:
        a, b = self.value(kind, year - 1), self.value(kind, year)
        return (b / a - 1) * 100 if a and b is not None and a > 0 else None

    def cagr(self, kind: str, y0: int, y1: int) -> float | None:
        a, b = self.value(kind, y0), self.value(kind, y1)
        if not a or not b or a <= 0 or b <= 0 or y1 <= y0:
            return None
        return ((b / a) ** (1 / (y1 - y0)) - 1) * 100

    def margin(self, year: int | None) -> float | None:
        if year is None:
            return None
        r, p = self.value("revenue", year), self.value("profit", year)
        return p / r * 100 if r and p is not None else None

    def derived(self) -> list[float]:
        """Every figure the yearly table gives: each year's growth and net margin, and the CAGR between any two years.
        The checks below hold each one to the year or span it is stated for."""
        out = []
        for kind in self.series:
            ys = sorted(self.series[kind])
            for i, y1 in enumerate(ys):
                out += [x for x in (self.yoy(kind, y1), self.margin(y1)) if x is not None]
                out += [x for x in (self.cagr(kind, y0, y1) for y0 in ys[:i]) if x is not None]
        return [round(x, 2) for x in out]

    def metric(self, *words, without=()) -> list[float]:
        return [v for k, v in self.labelled if all(re.search(w, k) for w in words) and not any(re.search(w, k) for w in without)]

    # --- reading a sentence ---
    def years_in(self, s: str) -> list[int]:
        bare = _QLABEL.sub(" ", s)
        return [_fy_num(m.group(1)) for m in _FYEAR.finditer(bare)]

    def quarters_in(self, s: str) -> list[tuple[int, int]]:
        out = []
        if self.region == "IN":
            out += [india_quarter(int(m.group(1)), _fy_num(m.group(2))) for m in _QLABEL.finditer(s)]
        mon = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
        for m in re.finditer(r"\b(?:quarter|three months)\s+(?:ended|ending|to)\s+(?:\d{1,2}\s+)?" + mon + r",?\s+(20\d\d)", s, re.I):
            out.append((int(m.group(2)), _MONTHS[m.group(1)[:3].lower()]))
        for m in re.finditer(r"\b" + mon + r"\s+(20\d\d)\s+quarter\b", s, re.I):
            out.append((int(m.group(2)), _MONTHS[m.group(1)[:3].lower()]))
        for m in re.finditer(r"\bquarter\s+(?:ended|ending|to)\s+(20\d\d)-(\d\d)-\d\d", s, re.I):
            out.append((int(m.group(1)), int(m.group(2))))
        return out

    @staticmethod
    def subject(s: str, at: int) -> str | None:
        """The figure a number is about: the nearest of revenue, profit, EPS or price named before it (else after)."""
        best, where = None, -1
        for kind, rx in _SUBJECT:
            for m in rx.finditer(s[:at]):
                if m.start() > where:
                    best, where = kind, m.start()
        if best:
            return best
        for kind, rx in _SUBJECT:
            if rx.search(s[at:]):
                return kind
        return None

    # --- the checks ---
    def check(self, s: str) -> bool:
        return (not JUDGE.search(s) and self._periods_ok(s) and self._dates_ok(s) and self._money_ok(s) and self._percents_ok(s)
                and self._moves_ok(s))

    def _moves_ok(self, s: str) -> bool:
        """A rise or fall between two named years is the yearly table's: "Net income fell from FY24 to FY25" beside a
        table where it rose from 93.74B to 112.01B is dropped (R50-001), and so is a growth told as a quarter's when
        the sentence names a whole year for it."""
        ys = self.years_in(s)
        way = _MOVE.search(s)
        if len(ys) != 2 or ys[0] == ys[1] or not way:
            return True
        kind = next((k for k, rx in _SUBJECT if k in self.series and rx.search(s)), None)
        rows = self.series.get(kind) if kind else None
        if not rows or ys[0] not in rows or ys[1] not in rows:
            return True
        a, b = (rows[ys[0]], rows[ys[1]]) if ys[0] < ys[1] else (rows[ys[1]], rows[ys[0]])
        up = way.group(1) is not None
        return (b > a) == up or a == b

    def check_watch(self, s: str) -> bool:
        """A thing ahead: no reported figure ("actual EPS 2.84") and no period already reported."""
        if _WATCH_PAST.search(s) and re.search(r"\d", s):
            return False
        return self.check(s)

    def _periods_ok(self, s: str) -> bool:
        years = self.years_in(s)
        ahead = bool(_AHEAD.search(s))
        if self.years:
            for y in years:
                if y < self.years[0] or y > self.latest + 1:
                    return False                          # a year the table doesn't have
                if ahead and y <= self.latest:
                    return False                          # a reported year called estimated or upcoming
            if years and _LATEST.search(s) and max(years) != self.latest:
                return False
            if years and max(years) < self.latest and (_PCT.search(s) or self._money_spans(s)):
                return False                              # an old year's figure told as if it were the latest
        qs = self.quarters_in(s)
        if self.last_q:
            if ahead and _RESULTS.search(s) and any(q <= self.last_q for q in qs):
                return False                              # a reported quarter's results called due or upcoming
            if not qs and self.status == "filed" and _RESULTS.search(s) and re.search(r"\b(due|today|upcoming|scheduled)\b", s, re.I):
                if not (self.next_day and self.next_day in dates_in(s)):
                    return False                          # "results are due today" once they are out
        return True

    def _dates_ok(self, s: str) -> bool:
        return all(d in self.dates for d in dates_in(s))

    @staticmethod
    def _money_spans(s: str) -> list[tuple[float, int, int, str]]:
        """(amount, start, end, qualifier) for each sum of money in the text: one with a currency sign or a unit."""
        out = []
        for m in _MONEY.finditer(s):
            cur, raw, unit = m.group(1), m.group(2), re.sub(r"\s+", " ", (m.group(3) or "").lower())
            if not cur and not unit:
                continue
            if unit in ("b", "m", "t") and not cur:
                continue                                  # "5 m" alone is not money
            if _ISO.match(s, m.start(2)):
                continue
            try:
                v = float(raw.replace(",", ""))
            except ValueError:
                continue
            before = s[max(0, m.start() - 18):m.start()].lower()
            q = "over" if re.search(r"\b(over|more than|above|exceed\w*)\s*$", before) else \
                "under" if re.search(r"\b(under|nearly|almost|less than|below|just short of)\s*$", before) else ""
            out.append((v * _UNIT.get(unit, 1.0), m.start(), m.end(), q))
        return out

    @staticmethod
    def _bound_year(s: str, start: int, end: int) -> int | None:
        """The fiscal year a sum is given for: "₹2,40,893 cr in FY24", "FY24 revenue of $391 billion"."""
        after = _FYEAR.search(s[end:end + 30])
        if after and not _QLABEL.search(s[end:end + 30]):
            return _fy_num(after.group(1))
        before = list(_FYEAR.finditer(s[max(0, start - 25):start]))
        return _fy_num(before[-1].group(1)) if before else None

    def _money_ok(self, s: str) -> bool:
        if not self.series:
            return True
        for v, a, b, q in self._money_spans(s):
            y = self._bound_year(s, a, b)
            if y is None:
                continue
            subj = self.subject(s, a)           # a profit figure is held to the profit, not to the revenue that happens to match
            want = [x * self.unit for x in (self.value(k, y) for k in (("revenue", "profit") if subj not in ("revenue", "profit") else (subj,))) if x is not None]
            ok = False
            for w in want:
                if q == "over":
                    ok = ok or v <= w <= v * 1.1
                elif q == "under":
                    ok = ok or v * 0.9 <= w <= v
                else:
                    ok = ok or abs(w - v) <= abs(w) * 0.015
            if not ok:
                return False
        return True

    def _percents_ok(self, s: str) -> bool:
        for m in _PCT.finditer(s):
            raw = m.group(1).replace("−", "-")
            stated, dp = abs(float(raw)), _dp(raw)
            cut = max(s.rfind(",", 0, m.start()), s.rfind(";", 0, m.start()), s.rfind(" and ", 0, m.start()), s.rfind(" while ", 0, m.start()))
            ends = [x for x in (s.find(",", m.end()), s.find(";", m.end()), s.find(" while ", m.end())) if x >= 0]
            clause = s[cut + 1:min(ends or [len(s)])].lower()
            near = s[max(0, m.start() - 70):m.end() + 40].lower()
            want = self.expected(s, m.start(), clause, near)
            if want is None:
                continue                                  # a kind of figure the page has nothing to check against
            way = _way(clause) if not _LEVEL.search(clause) and not _LEVEL_TO.search(s[max(0, m.start() - 8):m.start()]) else 0
            # a stated rise needs a rise on the page, a fall a fall (a 18.5% rise told as a decline)
            if not any(_close(stated, abs(w), dp) and (way * w >= 0 or abs(w) < 0.05) for w in want):
                return False
        return True

    def expected(self, s: str, at: int, clause: str, near: str) -> list[float] | None:
        """The values a percentage may take, from the page, by what it is about; None when the page can't say."""
        subj = self.subject(s, at)
        years = self.years_in(s)
        span = re.search(r"\b(\d{1,2}|three|five|ten)[- ](?:year|yr)s?\b|\b(\d{1,2})y\b", clause)
        n = None
        if span:
            w = span.group(1) or span.group(2)
            n = {"three": 3, "five": 5, "ten": 10}.get(w) or int(w)
        if re.search(r"\bdiv(idend)?s?\.? yield\b|\byield\b", clause) and "dividend" in near or re.search(r"\bdiv(idend)? yield\b", clause):
            return self.metric(r"yield") or None
        if re.search(r"\b(roe|return on equity)\b", clause):
            return self.metric(r"\broe\b") or None
        if re.search(r"\b(roce|return on capital)\b", clause):
            return self.metric(r"\broce\b") or None
        if re.search(r"\bpayout\b", clause):
            return self.metric(r"payout") or None
        if "margin" in clause:
            which = next((w for w in ("gross", "operating", "ebitda", "net") if w in clause), "net")
            if years and self.series:
                return [x for x in (self.margin(max(years)),) if x is not None] if which == "net" else []
            if _LATEST.search(s) and which == "net" and self.margin(self.latest) is not None:
                return [self.margin(self.latest)]
            got = self.metric(which, r"margin")
            if which == "net" and self.margin(self.latest) is not None:
                got.append(self.margin(self.latest))
            return got or None
        rate = re.search(r"\bcagr\b|compound|annuali[sz]ed|a year\b|per year|per annum|annual (growth|rate)|annually|each year|yearly", clause)
        if rate and subj in ("revenue", "profit"):
            if len(set(years)) >= 2 and self.series.get(subj):
                c = self.cagr(subj, min(years), max(years))
                return [c] if c is not None else []
            label = r"sales|revenue" if subj == "revenue" else r"profit|net income"
            got = []
            for k in (n,) if n else range(1, 11):
                if self.latest and self.series.get(subj):
                    c = self.cagr(subj, self.latest - k, self.latest)
                    got += [c] if c is not None else []
                got += self.metric(label, rf"\b{k}\s?y|\b{k} years?\b")
            if not n and self.series.get(subj) and len(self.series[subj]) > 1:
                ys = sorted(self.series[subj])
                c = self.cagr(subj, ys[0], ys[-1])
                got += [c] if c is not None else []
            return got
        if rate and subj == "eps":
            return self.metric(r"eps", rf"\b{n}\s?y" if n else r"\dy") or None
        if subj == "price" or re.search(r"\b(1|one)[- ]year (return|price change|change)\b|\bprice change\b|\b1y return\b", near):
            if re.search(r"\b(1|one)[- ]year\b|\bpast (year|12 months)\b|\blast (year|12 months)\b|\b1y\b|\bover the year\b", near):
                return self.metric(r"1y|1-year|1 year", without=(r"sales|revenue|profit|eps",)) or None
            if re.search(r"\b(today|on the day)\b", near):
                return self.metric(r"day change") or None
            return None
        growth = re.search(r"\b(yoy|year[- ](on|over)[- ]year|grew|growth|rose|increased|increase|declined|decline|fell|dropped|up|down|higher|lower|jumped|slipped)\b", clause)
        if growth and subj in ("revenue", "profit"):
            label = r"sales|revenue" if subj == "revenue" else r"profit|net income"
            if years and self.series.get(subj):
                if len(set(years)) >= 2:          # "from FY19 to FY24": the change over the span, or its yearly rate
                    y0, y1 = min(years), max(years)
                    a, b = self.value(subj, y0), self.value(subj, y1)
                    return [x for x in (self.cagr(subj, y0, y1), (b / a - 1) * 100 if a and b is not None else None) if x is not None]
                return [x for x in (self.yoy(subj, max(years)),) if x is not None]
            if _LATEST.search(s) and self.latest and self.series.get(subj):
                return [x for x in (self.yoy(subj, self.latest),) if x is not None]
            got = self.metric(label, r"yoy|latest")
            if n:
                got += self.metric(label, rf"\b{n}\s?y|\b{n} years?\b")
                c = self.cagr(subj, self.latest - n, self.latest) if self.latest else None
                got += [c] if c is not None else []
            yy = self.yoy(subj, self.latest) if self.latest else None
            got += [yy] if yy is not None else []
            return got or None
        if growth and subj == "eps":
            return self.metric(r"eps") or None
        return None


# ---------- every AI read, as the page writes it (R7O-001, R7O-002) ----------
# ICICIBANK, 9 Oct 2026: "decreased by 0.6261510128913406% on the day", "a P/B ratio of 2.55977229601518", "a net profit
# of ₹57936.0 crore". Every number was in the facts, so the number check passed it. The facts now go to the model as the
# page shows them, and whatever the model writes is written the page's way before it is shown or served again.
_LONG = re.compile(r"(?<![\w.])([-−+]?\d[\d,]*)\.(\d{3,})(?![\d.])")
_CUR_NUM = re.compile(r"(₹|Rs\.?\s?|INR\s|US\$|\$)\s?(\d[\d,]*(?:\.\d+)?)(\s*(?:lakh\s+crore|lakh\s+cr\b|crore|cr\b|lakh|billion|bn\b|million|mn\b|trillion|tn\b))?", re.I)
_UNIT_NUM = re.compile(r"(?<![\w.₹$,])(\d{4,}(?:\.\d+)?)(\s*(?:lakh\s+crore|crore|cr\b))", re.I)


def indian(n: int) -> str:
    """1,95,218: India's grouping."""
    s = str(abs(int(n)))
    head, tail = s[:-3], s[-3:]
    if head:
        s = ",".join(re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head)) + "," + tail
    return ("-" if n < 0 else "") + s


def _grouped(v: float, dp: int, inr: bool) -> str:
    text = f"{v:.{dp}f}"
    whole, _, frac = text.partition(".")
    w = int(whole)
    return (indian(w) if inr else f"{w:,}") + (("." + frac) if frac else "")


def tidy_numbers(text, region: str = "IN"):
    """A read's numbers as the page writes them: never more than two decimals, money grouped the market's way (Indian
    grouping for rupees), a sum in crore without a stray ".0", a price with its paise."""
    if not isinstance(text, str) or not text:
        return text

    def long_dec(m):
        raw = (m.group(1) + "." + m.group(2)).replace(",", "").replace("−", "-")
        try:
            v = float(raw)
        except ValueError:
            return m.group(0)
        out = f"{abs(v):.2f}"
        sign = m.group(1)[:1] if m.group(1)[:1] in "-−+" else ""
        return sign + out
    t = _LONG.sub(long_dec, text)

    def money(m):
        cur, raw, unit = m.group(1), m.group(2), m.group(3) or ""
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            return m.group(0)
        inr = cur.strip().upper().startswith(("₹", "RS", "INR"))
        if unit.strip():
            given = min(2, len(raw.split(".")[1]) if "." in raw else 0)
            # crore is shown whole on the page (₹57,936 crore); billions keep the decimals given ($416.16 billion)
            dp = 0 if (v >= 100 and re.match(r"\s*(lakh|crore|cr)\b", unit, re.I) and "lakh crore" not in unit.lower()) \
                or v == int(v) else given
        else:
            dp = 0 if v >= 100000 or "." not in raw else 2
        return f"{cur}{_grouped(v, dp, inr)}{unit}"
    t = _CUR_NUM.sub(money, t)

    def bare(m):                                 # "57936.0 crore" without a sign
        try:
            v = float(m.group(1))
        except ValueError:
            return m.group(0)
        return f"{_grouped(v, 0, True)}{m.group(2)}"
    t = _UNIT_NUM.sub(bare, t)
    # a fall already says the direction: "has fallen -17.0%" reads as a double negative (R49-013), "fell 17.0%"
    t = _FALL_SIGN.sub(lambda m: m.group(1) + " ", t)
    # a negative percentage with the page's own minus sign, not a hyphen (R50-011: "-17.0%" beside "−13.4%")
    return re.sub(r"(?<![\w.,%)\-\u2212])[-\u2013](?=\d[\d.,]*\s?%)", "\u2212", t)


_FALL_SIGN = re.compile(r"\b(fallen|fell|falls|falling|dropped|drops|declined|declines|slipped|slid|lost|down|lower|decreased)\s+[-\u2212](?=\d)", re.I)


# filler that states nothing ("debt is not explicitly stated, but its financial health can be affected by various market
# and economic factors") and suggestions that a style of trading works ("mean reversion strategies can be effective in
# such cases"), which no read may carry
FILLER = re.compile(r"\bnot (explicitly |clearly |directly )?(stated|disclosed|available|provided|mentioned|given|known|reported)\b"
                    r"|\bcan be (affected|impacted|influenced) by\b|\bvarious (market|economic|macro\w*|external) (and \w+ )?factors\b"
                    r"|\bhighly (competitive|regulated)\b", re.I)
EFFECTIVE = re.compile(r"\bcan (be )?(effective|useful|profitable|successful|rewarding|helpful)\b|\bcan work\b"
                       r"|\b(tend|tends) to (work|be effective|perform|pay off)\b|\bworks? well\b|\b(is|are) (well[- ])?suited\b"
                       r"|\bsuit(s|ed)? (such|this|these|the stock)\b|\beffective (in|when|for|at)\b"
                       r"|\b(could|may|might|can) (capture|benefit|profit|help)\b|\bopportunit", re.I)
# a comparison with a figure the page never shows: its own history or usual range, its peers, the sector or the market
# (R7O-002: "near the lower end of its historical 15-20 range", "high relative to peers", "its multi-year average of
# roughly 30"). Comparisons with the page's own moving averages and ranges stay.
UNSOURCED = re.compile(r"\bhistoric(al(ly)?)?\b|\b(its|their) (usual|typical|normal|long[- ]term|own|past) (range|average|level|multiple|valuation)s?\b"
                       r"|\bmulti[- ]year\b|\b(long[- ]term|five[- ]year|5[- ]year|ten[- ]year|10[- ]year|three[- ]year|3[- ]year) (average|median|mean|range|norm)\b"
                       r"|\bpeers?\b|\bpeer group\b|\b(sector|industry|market|category) (average|median|multiple|norm)s?\b"
                       r"|\b(compared|relative) (to|with) (its |the )?(peers|sector|industry|market|competitors|rivals)\b|\belevated\b"
                       r"|\bwell (above|below)\b|\b(lower|upper|higher|low|high) end\b|\b(above|below) (its|the) (average|norm|usual)\b"
                       r"|\b(premium|discount) to\b|\bthan (its |the )?(peers|sector|industry|rivals|competitors)\b|\b(high|low) relative\b"
                       # "high" or "low" against nothing the page shows (R8O-004: TCS "P/B of 6.6 is relatively high")
                       r"|\b(relatively|comparatively|fairly|rather|quite) (high|low|rich|expensive|cheap|modest|elevated|stretched|attractive|lofty|steep)\b"
                       r"|\b(is|are|looks?|appears?|remains?|seems?) (very )?(rich|expensive|cheap|stretched|lofty|steep|undervalued|overvalued)\b", re.I)
# a trading idea's caption states a fact from the page, never what a figure "suggests", "signals" or makes "suitable",
# and never what would or could happen (R8O-004: "Recent quarterly profit beat suggests upward momentum", "a clear signal of
# a trend shift", "A low RSI would signal oversold conditions", "making it suitable for testing oversold bounces")
# (a moving average's "signal line", an "indicator" and the month of May are facts, not predictions)
PREDICTS = re.compile(r"\bsuggest\w*\b|\bsignal(s|ed|led|ing|ling)?\s+(of|that|an?|the)\b|\b(clear|strong|reliable|good) signal\b"
                      r"|\bindicat(es|ing|ed)\b|\bimpl(y|ies|ied)\b|\bpoints? to\b|\bhint\w*\b"
                      r"|\b(would|could|might|should|will|likely|unlikely|expected to|poised|set to)\b|(?-i:\bmay\b)"
                      r"|\bsuitab\w*\b|\bsuited\b|\bideal\b|\bmaking (it|this|the stock|them)\b"
                      r"|\b(upward|downward|positive|negative|building|strong|weak|bullish|bearish)\s+momentum\b|\btrend shift\b"
                      r"|\bbeat\b|\bbeats\b|\bupside\b|\bdownside\b|\bpotential\b|\bopportunit", re.I)
# a lender's book has no EBITDA, operating margin or debt-to-equity that means anything (R7O-001: ICICIBANK "EBITDA margin -20.0%")
LENDER_WORDS = re.compile(r"\bebitda\b|\boperating (profit )?margin\b|\bdebt[- ]to[- ]equity\b|\bd/e\b|\bcapex\b", re.I)


# a direction word must say what its numbers do (R8B-003: AAPL "Net profit declined from FY24 (93.7 B) to FY25 (112.0 B)",
# a 19.5% rise)
_UP_WORDS = (r"rose|risen|rises|rising|increased|increases|increasing|grew|grown|grows|growing|climbed|climbs|climbing|"
             r"jumped|jumps|improved|improves|expanded|expands|gained|gains|higher|up|surged|soared|advanced")
_DOWN_WORDS = (r"fell|fallen|falls|falling|declined|declines|declining|dropped|drops|dropping|decreased|decreases|decreasing|"
               r"shrank|shrunk|shrinks|slipped|slips|contracted|contracts|lower|down|dipped|dips|slid|slumped|eased")
_MOVE_WORD = re.compile(rf"\b({_UP_WORDS}|{_DOWN_WORDS})\b", re.I)
_UP_NOUNS, _DOWN_NOUNS = r"rise|increase|jump|surge", r"decline|drop|fall|decrease|dip"
_LEVEL = re.compile(r"margin|yield|\broe\b|\broce\b|payout")            # a level, not a change: "fell to 10%" says nothing of sign
_LEVEL_TO = re.compile(r"\b(to|at|of|near|around)\s*$")


def _way(clause: str) -> int:
    """1 when the clause says a figure rose, -1 when it fell, 0 when it says neither or both."""
    up = re.search(rf"\b({_UP_WORDS}|{_UP_NOUNS})\b", clause)
    down = re.search(rf"\b({_DOWN_WORDS}|{_DOWN_NOUNS})\b", clause)
    return 0 if bool(up) == bool(down) else 1 if up else -1


_UP_RE = re.compile(rf"^(?:{_UP_WORDS})$", re.I)
_FROM_TO = re.compile(rf"\b(?P<w>{_UP_WORDS}|{_DOWN_WORDS})\b[^.;]{{0,60}}?\bfrom\b(?P<a>[^;]{{1,50}}?)\bto\b(?P<b>[^;]{{1,60}})", re.I)
_LABELS = re.compile(r"\b(?:FY|CY|Q[1-4]\s*FY|H[12]\s*FY)\s*'?\d{2,4}\b|\bQ[1-4]\b|\b(?:19|20)\d\d\b|\bfiscal(?:\s+year)?\b", re.I)
_AMOUNT = re.compile(r"(?<![\w.])([-−]?\d[\d,]*(?:\.\d+)?)\s*(lakh\s+crore|crore|cr\b|lakh|trillion|tn\b|t\b|billion|bn\b|b\b|"
                     r"million|mn\b|m\b|k\b)?", re.I)
_SCALE = {"lakh crore": 1e12, "crore": 1e7, "cr": 1e7, "lakh": 1e5, "trillion": 1e12, "tn": 1e12, "t": 1e12, "billion": 1e9,
          "bn": 1e9, "b": 1e9, "million": 1e6, "mn": 1e6, "m": 1e6, "k": 1e3}


def _amount(seg: str) -> tuple[float, str] | None:
    m = _AMOUNT.search(_LABELS.sub(" ", seg))
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", "").replace("−", "-"))
    except ValueError:
        return None
    return v, re.sub(r"\s+", " ", (m.group(2) or "").lower())


def moves_agree(s: str) -> bool:
    """False when a sentence says a figure rose (or fell) "from" one amount "to" another that moved the other way."""
    for m in _FROM_TO.finditer(s or ""):
        a, b = _amount(m.group("a")), _amount(m.group("b"))
        if not a or not b:
            continue
        ua, ub = a[1] or b[1], b[1] or a[1]
        va, vb = a[0] * _SCALE.get(ua, 1.0), b[0] * _SCALE.get(ub, 1.0)
        if va == vb or va < 0 or vb < 0:            # a loss that "rose" grows more negative: left alone
            continue
        if bool(_UP_RE.match(m.group("w"))) != (vb > va):
            return False
    return True


def _fy_years(s: str) -> list[int]:
    out = []
    for m in _FYEAR.finditer(s or ""):
        y = int(m.group(1))
        out.append(y + 2000 if y < 100 else y)
    return out


def newest_move_year(texts) -> int | None:
    """The newest fiscal year that any sentence about a figure moving names, across a read."""
    years = [y for t in texts for s in _SENT.split(str(t or "")) if _MOVE_WORD.search(s) and not _AHEAD.search(s)
             for y in _fy_years(s)]
    return max(years) if years else None


def stale_move(s: str, newest: int | None) -> bool:
    """A sentence about a figure moving between years older than the newest one the read reports (AAPL's risks listed
    "Revenue fell from FY22 to FY23" beside FY25's figures): no longer the current picture."""
    if newest is None or not _MOVE_WORD.search(s):
        return False
    years = _fy_years(s)
    return bool(years) and max(years) < newest


def plain_ok(s: str, lender: bool = False) -> bool:
    """A sentence any read may keep: no filler, no suggestion that a style of trading works, no comparison with a
    figure the page doesn't show, for a bank or lender no EBITDA or operating margin, and no direction word that its
    own numbers contradict."""
    return not (FILLER.search(s) or EFFECTIVE.search(s) or UNSOURCED.search(s) or (lender and LENDER_WORDS.search(s))
                or SIZED.search(s) or not moves_agree(s))


# a figure labelled by size, which is the reader's call ("Dividend yield 0.3% is low", "Debt of ₹4.03 lakh crore remains
# sizable", R55-010): the page states the number
SIZED = re.compile(r"\b(is|are|remains?|stays?|looks?|seems?|appears?|was|were)\s+(still\s+|relatively\s+|quite\s+|very\s+|rather\s+)?"
                   r"(low|high|sizable|sizeable|large|elevated|significant|substantial|small|thin|meagre|meager|hefty|considerable|"
                   r"modest|limited|minimal|negligible|manageable|comfortable|moderate)\b(?!\s+(than|as|in|at|for|of|on)\b)", re.I)


# A holding's change is a difference between two shares of the company, so it is said in percentage points: "FIIs'
# ownership fell by 2.41%" reads as a 2.41% fall of the holding itself, not from 24.10% to 21.69% (round 39).
# "share of FIIs" and "FIIs' share" too (R64-009: "Share of FIIs fell by 2.41% to 9.07%"), never a bare "share", which is
# often the share price
_HOLD_NOUN = (r"(?:shareholding|holding|holdings|stake|ownership|share(?=\s+of\b)|"
              r"(?:FII|FPI|DII|promoter|public|retail|institutional|foreign|mutual\s+fund)s?['’]?\s+share)")
_HOLD_GAP = r"(?:\s+(?!company\b|companies\b|price\b|prices\b|profit\b|sales\b|revenue\b|income\b)[\w'’-]+){0,3}"
_HOLD_VERB = (r"(?:fell|fall(?:s|en)?|declin(?:e|es|ed)|decreas(?:e|es|ed)|dropped|drops?|reduced|rose|rises?|risen|increas(?:e|es|ed)|grew|grows?|climbed|jumped|"
              r"slipped|dipped|shrank|"
              r"cut|raised|lowered|trimmed|lifted|up|down|changed)")
_HOLD_MOVE = re.compile(
    rf"(\b{_HOLD_NOUN}\b{_HOLD_GAP}\s+{_HOLD_VERB}\s+by\s+|\b{_HOLD_VERB}\s+(?:its|their|the|his|her)?\s*{_HOLD_NOUN}\s+by\s+)"
    r"(\d+(?:\.\d+)?)\s?(?:%|per\s?cent\b|percent\b)(?!\s*points?)", re.I)


def holding_points(text):
    """A holding's change by N% said as N percentage points ("FIIs ownership fell by 2.41%" -> "... by 2.41 percentage
    points"). A change of a holding is a difference between two shares, never a percentage of the holding."""
    if not isinstance(text, str):
        return text
    return _HOLD_MOVE.sub(lambda m: f"{m.group(1)}{m.group(2)} percentage points", text)


def plain_sentences(text, lender: bool = False, region: str = "IN") -> str:
    """The sentences of a stored or fresh read that pass plain_ok, with their numbers written the page's way."""
    if not isinstance(text, str):
        return ""
    keep = [s for s in _SENT.split(" ".join(text.split())) if s and plain_ok(s, lender)]
    return tidy_numbers(holding_points(" ".join(keep)), region)


# a trading idea's name says what kind of rule it is: a "Mean Reversion Strategy" that enters on a moving-average
# crossover is dropped (R7O-001)
_STYLE_TITLE = [("reversion", re.compile(r"revers|oversold|\bdip\b|pullback|pull-back|bounce|\bfade", re.I)),
                ("breakout", re.compile(r"break[- ]?out|breaks? out|new high|52[- ]week high", re.I)),
                ("trend", re.compile(r"trend|momentum|crossover|cross[- ]over|golden cross|moving average cross", re.I))]
_STYLE_RULE = [("breakout", re.compile(r"\b(52[- ]week|\d+[- ](day|week|month)|n[- ]day|prior|previous|recent) high\b|\bbreaks? (out )?above\b"
                                      r"|\bchannel\b|\bdonchian\b|\brange high\b|\bresistance\b|\bupper (bollinger )?band\b", re.I)),
               ("reversion", re.compile(r"\brsi\b[^,.;]{0,40}\b(below|under|drops|falls|less than|crosses below)\b|\boversold\b"
                                        r"|\blower (bollinger )?band\b|\b(falls|drops|is|trades|closes) [\d.]+% below\b|\bcrosses below\b", re.I)),
               ("trend", re.compile(r"\bcrosses above\b|\bgolden cross\b|\bcloses? above (its|the) \d+[- ]day\b|\bsupertrend\b|\bmacd\b", re.I))]


def idea_style(text: str) -> str | None:
    """What kind of rule an idea enters on (its part before the exit): breakout, reversion or trend; None when unclear."""
    entry = re.split(r"\b(exit|sell|close|cover)\b", str(text or ""), maxsplit=1, flags=re.I)[0]
    for kind, rx in _STYLE_RULE:
        if rx.search(entry):
            return kind
    return None


def idea_matches_name(title, text) -> bool:
    named = next((k for k, rx in _STYLE_TITLE if rx.search(str(title or ""))), None)
    got = idea_style(text)
    return named is None or got is None or named == got


# R10O-005: a rule that compares the price with a number typed into it ("Enter long when price rises above 8255") tests
# one day's price, which stops being current tomorrow; a rule to test is made of indicators and percentages.
_LEVEL = re.compile(
    r"\b(price|prices|close|closes|closing|trades?|rises?|climbs?|breaks?|crosses|stays?|remains?|drops?|falls?|dips?|recovers?|"
    r"rebounds?|reaches?|hits?|moves?|goes|gets?)\b[^.;]{0,40}?\b(above|below|over|under|to|at|through|beyond|past|near|reclaims?)\s+"
    r"(?:the\s+)?(?:level\s+(?:of\s+)?|price\s+(?:of\s+)?)?(₹|rs\.?\s*|inr\s*|\$|usd\s*)?(\d[\d,]*(?:\.\d+)?)(?!\d)"
    r"(?!\s*(?:%|-)|\s*(?:day|week|month|period|minute|min|hour|x\b|times|percent|per\s?cent|shares|sessions|candles?|bars?))", re.I)
_NOT_PRICE = re.compile(r"\b(volume|rsi|atr|macd|adx|average|avg|sma|ema|ratio|yield|p/e|margin|growth|vix|stochastic|cci|momentum)\b", re.I)


def hardcodes_price(text, price=None) -> bool:
    """Whether a trading idea's rule compares the price with a level typed into it. With the current `price`, a level
    within 40% of it; without, any level of 100 or more (or one marked with a currency)."""
    cur = None
    try:
        cur = float(price) if price is not None else None
    except (TypeError, ValueError):
        cur = None
    for clause in re.split(r"(?<=[;.])\s+|,\s+(?=exit\b|sell\b|stop\b)", " ".join(str(text or "").split()), flags=re.I):
        for m in _LEVEL.finditer(clause):
            if _NOT_PRICE.search(clause[:m.start(4)]) and not re.search(r"\bprice\b", clause[:m.start(4)], re.I):
                continue
            try:
                level = float(m.group(4).replace(",", ""))
            except ValueError:
                continue
            if cur and cur > 0:
                if abs(level / cur - 1) <= 0.4:
                    return True
            elif level >= 100 or (m.group(3) and level >= 10):
                return True
    return False


_NAMED_INDICATORS = [
    (re.compile(r"\bsma\b|simple moving average", re.I), re.compile(r"\bsma\b|simple moving average|moving average|\d+[- ]day average", re.I)),
    (re.compile(r"\bema\b|exponential", re.I), re.compile(r"\bema\b|exponential", re.I)),
    (re.compile(r"\bmoving average\b", re.I), re.compile(r"\bsma\b|\bema\b|moving average|\d+[- ]day average", re.I)),
    (re.compile(r"\brsi\b|relative strength", re.I), re.compile(r"\brsi\b|relative strength", re.I)),
    (re.compile(r"\bmacd\b", re.I), re.compile(r"\bmacd\b", re.I)),
    (re.compile(r"\bbollinger\b", re.I), re.compile(r"\bbollinger\b|\bbands?\b", re.I)),
    (re.compile(r"\batr\b", re.I), re.compile(r"\batr\b|average true range", re.I)),
    (re.compile(r"\bsupertrend\b", re.I), re.compile(r"\bsupertrend\b", re.I)),
]
_N_DAY_EXTREME = re.compile(r"\b(\d+)[- ](day|week|month)s?\s+(high|low)\b", re.I)


def idea_uses_what_it_names(title, text) -> bool:
    """A trading idea that names an indicator in its title ("Trend following with 20-day SMA", "Mean reversion to 5-day
    low") uses it in its rule (R10O-005: POLYCAB's "SMA" idea entered on a typed-in price)."""
    title, text = str(title or ""), str(text or "")
    for named, used in _NAMED_INDICATORS:
        if named.search(title) and not used.search(text):
            return False
    for m in _N_DAY_EXTREME.finditer(title):
        want = re.compile(rf"\b{m.group(1)}[- ]{m.group(2)}s?\s+{m.group(3)}\b", re.I)
        if not want.search(text):
            return False
    return True


_WEEKDAY = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def app_dates(text, today=None) -> str:
    """ISO dates in a read written the app's way: "2026-10-17" is "Sat, 17 Oct" (the page header's form), with the year
    when it isn't this one (R8O-004)."""
    from datetime import date as _date
    if not isinstance(text, str):
        return text
    year = (today or _date.today()).year

    def one(m):
        try:
            d = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return m.group(0)
        return f"{_WEEKDAY[d.weekday()]}, {d.day} {_MON[d.month - 1]}" + ("" if d.year == year else f" {d.year}")
    return _ISO.sub(one, text)


# a holder class that "fell" or "rose" by the points of a reclassification (a depositary bank moved from FIIs to Public):
# the page explains it, and a read never calls it selling or buying (R8O-004: ICICIBANK "FIIs shareholding fell by 12.98
# points" in its risks)
_CLASS_WORDS = {"FIIs": r"\bfiis?\b|\bforeign (institutional |portfolio )?investors?\b|\bfpis?\b", "DIIs": r"\bdiis?\b|\bdomestic institution\w*",
                "Public": r"\bpublic\b|\bretail\b", "Promoters": r"\bpromoters?\b", "Government": r"\bgovernment\b"}
_MOVED = re.compile(r"\b(fell|fall\w*|declin\w*|dropp?\w*|reduc\w*|cut|sold|sell\w*|exit\w*|lower\w*|decreas\w*|shed|trimm?\w*|"
                    r"rose|rise\w*|risen|increas\w*|bought|buy\w*|add\w*|rais\w*|higher|jump\w*|climb\w*|grew|grow\w*|up|down)\b", re.I)


def mentions_class_move(s: str, classes) -> bool:
    """Whether a sentence speaks of a moved holder class's holding changing."""
    for c in classes or ():
        rx = _CLASS_WORDS.get(str(c))
        if rx and re.search(rx, s, re.I) and _MOVED.search(s):
            return True
    return False


def plain_caption(text, lender: bool = False, region: str = "IN") -> str:
    """A trading idea's caption: the plain sentences that state a fact, none that predicts or calls the stock suitable."""
    kept = plain_sentences(text, lender, region)
    return " ".join(s for s in _SENT.split(kept) if s and not PREDICTS.search(s))


_MON_NUM = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_WRITTEN_DAY = re.compile(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\w*(?:,? (\d{4}))?\b", re.I)


def past_watch(text: str, today=None) -> bool:
    """A "what to watch" line about a day already gone ("2026-06-30", or as a stored read writes it, "Tue, 30 Jun"),
    or a quarter's end, which is a past date by the time its results are known (R55-002)."""
    from datetime import date as _date
    today = today or _date.today()
    if re.search(r"\bquarter[- ]end\b|\bquarter ended\b", text, re.I):
        return True
    days = []
    for y, m, d in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        days.append((int(y), int(m), int(d)))
    for d, mon, y in _WRITTEN_DAY.findall(text):
        try:
            day = _date(int(y) if y else today.year, _MON_NUM[mon[:3].lower()], int(d))
        except ValueError:
            continue
        # a day written without its year is this year's, unless that is more than half a year gone ("15 Jan" in October
        # is next January's)
        if day < today and (y or (today - day).days <= 183):
            return True
    for y, m, d in days:
        try:
            if _date(y, m, d) < today:
                return True
        except ValueError:
            continue
    return False


def polish_company(read: dict, region: str = "IN", lender: bool = False, today=None) -> dict:
    """The checks every company read gets, fresh or stored, at no cost: numbers the page's way, no filler, no
    "can be effective", no comparison the page can't show, no EBITDA for a lender, and only trading ideas whose rule
    is the kind their name says (R7O-001, R7O-002); captions that state facts and predict nothing, a holder class's
    reclassification told as the page tells it, and dates the app's way (R8O-004). Run again whenever a stored read is
    served."""
    out = dict(read)
    move = read.get("class_move") if isinstance(read.get("class_move"), dict) else None
    classes = (move or {}).get("classes") or ()
    note_used = False

    def prose(text) -> str:
        nonlocal note_used
        kept = []
        for s in _SENT.split(plain_sentences(text or "", lender, region)):
            if not s:
                continue
            if classes and mentions_class_move(s, classes):
                if not note_used and move.get("note"):          # the page's own explanation, once
                    kept.append(str(move["note"]).split(" The named holders")[0])
                    note_used = True
                continue
            kept.append(s)
        return app_dates(" ".join(kept), today)

    for k in ("summary", "valuation_note", "position"):
        out[k] = prose(read.get(k))
    # a strength or a risk about a move between years older than the newest the read reports isn't current (R8B-003)
    newest = newest_move_year([read.get(k) for k in ("summary", "position")] + list(read.get("bull") or []) + list(read.get("bear") or []))
    for k in ("bull", "bear", "watch"):
        items = []
        for i in read.get(k) or []:
            if k == "watch" and past_watch(str(i), today):
                continue          # R55-002: "Tue, 30 Jun latest quarter end" is behind the reader, not something to watch
            x = plain_sentences(str(i), lender, region)
            # a strength or a risk is never a reclassification of holders: left out (the page explains it)
            x = " ".join(s for s in _SENT.split(x) if s and not (classes and mentions_class_move(s, classes))
                         and not (k != "watch" and stale_move(s, newest)))
            if x:
                items.append(app_dates(x, today))
        out[k] = items
    ideas = []
    for i in read.get("ideas") or []:
        if not isinstance(i, dict) or not idea_matches_name(i.get("title"), i.get("text")):
            continue
        if hardcodes_price(i.get("text")) or not idea_uses_what_it_names(i.get("title"), i.get("text")):
            continue                  # R10O-005: a typed-in price level, or an indicator in the name that the rule doesn't use
        if uses_fundamentals(i.get("text")):
            continue                  # R54-003: a rule on a quarterly figure (an EMA of EBITDA margin) can't be backtested
        why = plain_caption(str(i.get("why") or ""), lender, region)
        if classes and mentions_class_move(why, classes):
            why = ""
        ideas.append({**i, "why": app_dates(why, today)})
    out["ideas"] = ideas
    return out


# figures a company reports once a quarter or a year: a backtest runs on daily prices and volume, so a rule built on
# one of them has no series to test (R54-003: "the 20-day EMA of EBITDA margin")
_FUNDAMENTAL = re.compile(r"\b(ebitda|margins?|eps|earnings per share|revenues?|sales growth|net profit|p/?e( ratio)?|"
                          r"price[- ]to[- ](earnings|book)|book value|roe|roce|debt|dividend yield|cash flow)\b", re.I)


def uses_fundamentals(text) -> bool:
    return bool(_FUNDAMENTAL.search(str(text or "")))


def class_move(shareholding) -> dict | None:
    """{"classes": the two holder classes that offset each other, "note": the page's explanation} from a company's
    shareholding (intel/company.class_move_note), or None."""
    sh = shareholding if isinstance(shareholding, dict) else {}
    note = sh.get("note")
    if not note:
        return None
    rows = [r for r in sh.get("rows") or [] if isinstance(r, dict) and isinstance(r.get("change"), (int, float)) and abs(r["change"]) >= 5]
    classes = [str(r.get("label")) for r in rows if str(r.get("label") or "") and str(r.get("label")) in str(note)]
    return {"classes": classes, "note": str(note)} if classes else None


def to_fixed(v: float, dp: int) -> str:
    """A number to `dp` decimals as the page's JavaScript writes it (toFixed: the exact value of the float, a half rounded
    up), not Python's round-half-even: NVDA's yield of 0.25 read "0.3%" on the page and "0.2%" in its AI read (DD-033)."""
    from decimal import ROUND_HALF_UP, Decimal
    return str(Decimal(v).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP))


def page_value(v, unit: str = "x", dp: int | None = None):
    """A Key numbers figure as the page writes it (lib/researchFormat.ts metricText): "0.9%", "+17.3%", "2.56", "₹527",
    so the model reads, and copies, the page's own figure (R7O-001)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return v
    if unit in ("%", "%±"):
        d = dp if dp is not None else (2 if v != 0 and abs(v) < 0.05 else 1)
        s = f"{to_fixed(abs(v), d)}%"
        return (("+" if v > 0 else "-" if v < 0 else "") if unit == "%±" else ("-" if v < 0 else "")) + s
    if unit == "money":
        return round(float(v), 2)
    if unit == "cr":
        return crore_text(v)
    return round(float(v), 0 if abs(v) >= 100 else 2)


def _nf(x: float, dp: int) -> str:
    """Indian grouping with up to `dp` decimals and no trailing zeros (format.ts nf)."""
    text = f"{x:.{dp}f}"
    whole, _, frac = text.partition(".")
    frac = frac.rstrip("0")
    return indian(int(whole)) + ("." + frac if frac else "")


def _scaled(x: float) -> tuple[str, float]:
    dp = 0 if x >= 100 else 1 if x >= 10 else 2
    n = round(x, dp)
    return _nf(n, dp), n


def crore_text(v_cr: float) -> str:
    """An amount in crore as the page writes it (format.ts inrCompact): "₹925 cr", "₹3,472 cr", "₹3.1 lakh cr", in
    India's grouping (R10C: the model was handed "310,000 crore")."""
    a, sign = abs(v_cr) * 1e7, "-" if v_cr < 0 else ""
    cr = _scaled(a / 1e7) if a >= 1e7 else None
    if a >= 1e12 or (cr and cr[1] >= 1e5):
        return f"{sign}₹{_scaled(a / 1e12)[0]} lakh cr"
    if cr:
        return f"{sign}₹{cr[0]} cr"
    if a >= 1e5:
        return f"{sign}₹{_scaled(a / 1e5)[0]} lakh"
    return f"{'' if round(a) == 0 else sign}₹{_nf(round(a), 0)}"


def rounded(x):
    """Every float in the facts to two decimals (a whole number without ".0"): the model is never handed
    0.6261510128913406 to copy."""
    if isinstance(x, bool) or x is None:
        return x
    if isinstance(x, float):
        r = round(x, 2)
        return int(r) if r == int(r) and abs(r) < 1e15 else r
    if isinstance(x, dict):
        return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, list):
        return [rounded(v) for v in x]
    return x
