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


def ground_sector(out: dict, region: str, lookup) -> dict:
    """A theme map with only tickers that are real and belong to the company named (R5O-008):
    - "Listed companies across the chain": a row whose company can't be found is dropped;
    - "Who's in it" and the value chain: the company stays by name, without a ticker (it isn't on the list);
    - "Funds to track": a fund that can't be found is dropped."""
    res = Resolver(lookup, region)

    def fix(c: dict) -> dict:
        if not c.get("ticker"):
            return {**c, "ticker": "", "listed": False}
        got = res.resolve(c.get("name"), c.get("ticker"))
        return {**c, "ticker": got["symbol"] if got else "", "listed": bool(got)}

    def fix_all(cos: list[dict]) -> list[dict]:
        seen, keep = set(), []
        for c in cos:
            f = fix(c)
            k = f["ticker"] or f.get("name")
            if k not in seen:
                seen.add(k)
                keep.append(f)
        return keep

    out = dict(out)
    screen = []
    for s in out.get("screen") or []:
        got = res.resolve(s.get("name"), s.get("ticker"))
        if got and got["symbol"] not in {x["ticker"] for x in screen}:
            screen.append({**s, "ticker": got["symbol"]})
    out["screen"] = screen
    out["clusters"] = [{**c, "companies": fix_all(c.get("companies") or [])} for c in out.get("clusters") or []]
    out["value_chain"] = [{**v, "companies": fix_all(v.get("companies") or [])} for v in out.get("value_chain") or []]
    funds = []
    for e in out.get("etfs") or []:
        got = res.resolve(e.get("name"), e.get("ticker"))
        if got and got["symbol"] not in {x["ticker"] for x in funds}:
            funds.append({"ticker": got["symbol"], "name": got["name"] or e.get("name") or ""})
    out["etfs"] = funds
    out["checked"] = True
    return out


# ---------- prose: facts only, every claim checked against the numbers given (R5O-018, R5O-027) ----------
# advice, forecasts and judgements, which no read may carry ("indicating limited upside", "sell it short")
ADVICE = re.compile(
    r"\b(buy|sell|hold|accumulate|avoid|short)\b\s+(the |this |its |these )?(stock|shares?|it|them|position)\b|\bsell\b[^.]{0,30}\bshort\b"
    r"|\bshort[- ]sell|\bgo short\b|\b(limited|more|further|significant|little|some|potential|further)\s+(upside|downside)\b|\bupside\b|\bdownside\b"
    r"|\b(target price|price target)s?\b|\bundervalued\b|\bovervalued\b|\b(cheap|expensive|bargain)\b|\battractive(ly)?\s+(valued|valuation|entry)\b"
    r"|\bworth (buying|owning|a look)\b|\boutlook\b|\bforecast|\bpredict|\bexpect(s|ed)?\s+to\b|\blikely to\b|\bpoised\b|\bset to\b"
    r"|\b(will|should|could|may|might)\s+(rise|fall|go|climb|drop|rally|gain|continue|outperform|underperform|benefit|recover|rebound|see|drive|lead|weigh|boost|pressure|support)\b"
    r"|\bopportunit(y|ies)\b|\bmultibagger\b|\b(good|great|right|ideal) time\b|\brecommend", re.I)

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


def range_claims_ok(s: str, indices: list[dict]) -> bool:
    """A claim about 52-week lows or highs holds for at least one index given (R5O-018: "well below their 52-week
    lows" while NIFTY was above its low)."""
    lv = [(i.get("price"), i.get("low52"), i.get("high52")) for i in indices if i.get("price")]
    if _BELOW_LOW.search(s):
        return any(lo and p <= lo * 1.001 for p, lo, _ in lv)
    if _NEAR_LOW.search(s):
        return any(lo and p <= lo * 1.03 for p, lo, _ in lv)
    if _HIGHS.search(s):
        return any(hi and p >= hi * 0.995 for p, _, hi in lv)
    if _NEAR_HIGH.search(s):
        return any(hi and p >= hi * 0.97 for p, _, hi in lv)
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


def market_facts(indices: list[dict]) -> list[dict]:
    """The index numbers the market read may use, with where each sits in its 52-week range spelt out."""
    out = []
    for i in indices:
        p, lo, hi = i.get("price"), i.get("low52"), i.get("high52")
        out.append({**i, "from_low_pct": round((p / lo - 1) * 100, 2) if p and lo else None,
                    "from_high_pct": round((p / hi - 1) * 100, 2) if p and hi else i.get("from_high_pct")})
    return out


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


def ground_pulse(out: dict, indices: list[dict], headlines: list[dict]) -> dict:
    """The market read with only what the index numbers and the headlines support: a sentence with a number not in
    them, a 52-week claim the levels contradict, a move the wrong way, a central bank, flow or sector no headline
    names, or any advice or outlook is dropped; a company is listed only when a headline names it (R5O-018)."""
    facts = market_facts(indices)
    support = " ".join(str(h.get("headline") or "") for h in headlines).lower()
    pool = fact_numbers({"i": facts, "h": [h.get("headline") for h in headlines]})

    def claim(s):
        return range_claims_ok(s, facts) and direction_ok(s, facts) and _topics_backed(s, support)
    res = dict(out)
    res["tone"] = keep_sentences(out.get("tone"), pool, claim) or template_tone(indices)
    named = lambda x: bool(x) and str(x).lower() in support          # noqa: E731
    res["hot"] = [{**h, "why": keep_sentences(h.get("why"), pool, claim)} for h in out.get("hot") or []
                  if named(h.get("name")) or named(h.get("ticker"))]
    res["hot"] = [h for h in res["hot"] if h["why"]]
    res["flows"] = [{**f, "detail": keep_sentences(f.get("detail"), pool, claim)} for f in out.get("flows") or []]
    res["flows"] = [f for f in res["flows"] if f["detail"] and _topics_backed(f.get("title") or "", support)]
    res["themes"] = [{**t, "detail": keep_sentences(t.get("detail"), pool, claim)} for t in out.get("themes") or []]
    res["themes"] = [t for t in res["themes"] if t["detail"] and (not t.get("example") or named(t.get("example")))]
    res["checked"] = True
    return res


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
    that match the calendar. Trading ideas are rules to test, worded as such, never instructions (R5O-027)."""
    pool = fact_numbers(facts)
    sym = str(facts.get("symbol") or "")
    res = dict(read)
    fy = lambda t: fix_fiscal_labels(t, today, region)        # noqa: E731
    for k in ("summary", "valuation_note", "position"):
        res[k] = keep_sentences(read.get(k) or "", pool)
    for k in ("bull", "bear", "watch"):
        res[k] = [x for x in (keep_sentences(fy(str(i)) if k == "watch" else str(i), pool) for i in read.get(k) or []) if x]
    ideas = []
    for i in read.get("ideas") or []:
        text = rule_words(str(i.get("text") or ""), sym)
        if not text:
            continue
        ideas.append({**i, "text": text, "why": keep_sentences(str(i.get("why") or ""), pool, None)})
    res["ideas"] = ideas
    res["checked"] = True
    return res


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
