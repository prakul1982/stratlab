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
