"""Find a company by whatever people call it: its symbol, its name or the start of it ("HDFC Bank", "Apollo Hosp"), a
common short name ("RIL", "Airtel", "Google"), a BSE code or an ISIN, with room for one slip of the keyboard
("Relaince", "Infosis").

One index per list of companies, built once in memory when the list changes, so a keystroke is a handful of
dictionary lookups rather than a walk over every row. Best first:

    0  EXACT    the symbol, BSE code or ISIN exactly ("INFY", "500325", "INE009A01021"; "hdfc bank" is HDFCBANK too)
    1  NAMED    a short name people use, or the whole name ("RIL", "Infosys", "Apollo Hospitals Enterprise Ltd")
    2  SYMBOL   a symbol starting with what's typed ("HDFC" → HDFCAMC, HDFCBANK…)
    3  NAME     a name starting with it ("Apollo Hospitals", "HDFC Ba")
    4  WORDS    a name with a word starting with each word typed, in any order ("hospitals apollo", "tata cons")
    5  CLOSE    the same with one typo in a word of five letters or more, or a swapped or wrong letter in a four-letter one

Within a group: indices before stocks before contracts (the caller's `rank`), well-known companies first (`boost`),
then the shorter symbol or the name with fewer other words, then the name in order. Names are compared without case,
punctuation or the legal form (Ltd, Limited, Inc, Corp, Plc…)."""
import re
import unicodedata
from bisect import bisect_left

EXACT, NAMED, SYMBOL, NAME, WORDS, CLOSE = range(6)
NOT_FOUND = 9

# what a name is called, not what it is: dropped from names and from what's typed
LEGAL = {"ltd", "limited", "inc", "incorporated", "corp", "corporation", "plc", "llc", "co", "company", "the", "and",
         "of", "&", "sa", "ag", "nv", "se", "lp"}
# the broker's list cuts long names short: "APOLLO HOSPITALS ENTER. L", "TATA CONSULTANCY SERV LT"
CUT_LIMITED = {"l", "li", "lim", "limi", "limit", "lt", "ltd"}
ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
_TOKEN = re.compile(r"[a-z0-9&]+")

# short names people use for a company, by market: name -> symbols it means (the first listed first)
ALIASES = {
    "IN": {
        "RIL": ["RELIANCE"], "SBI": ["SBIN"], "STATE BANK": ["SBIN"], "HDFC": ["HDFCBANK"], "ICICI": ["ICICIBANK"],
        "KOTAK": ["KOTAKBANK"], "AXIS": ["AXISBANK"], "AIRTEL": ["BHARTIARTL"], "BHARTI AIRTEL": ["BHARTIARTL"],
        "L&T": ["LT"], "LNT": ["LT"], "LARSEN": ["LT"], "M&M": ["M&M"], "MAHINDRA": ["M&M"], "HUL": ["HINDUNILVR"],
        "HINDUSTAN UNILEVER": ["HINDUNILVR"], "BAJAJ FINANCE": ["BAJFINANCE"], "ASIAN PAINTS": ["ASIANPAINT"],
        "SUN PHARMA": ["SUNPHARMA"], "MARUTI SUZUKI": ["MARUTI"], "ZOMATO": ["ETERNAL"], "INFOSYS": ["INFY"],
        # Tata Motors demerged in 2025: passenger vehicles kept the listing (TMPV), commercial vehicles listed as TMCV
        "TATA MOTORS": ["TMPV", "TMCV", "TATAMOTORS"], "TATAMOTORS": ["TMPV", "TMCV"],
        "HPCL": ["HINDPETRO"], "IOCL": ["IOC"], "NALCO": ["NATIONALUM"], "HZL": ["HINDZINC"], "BOB": ["BANKBARODA"],
        "LIC": ["LICI"], "DMART": ["DMART"], "POLICYBAZAAR": ["POLICYBZR"], "NYKAA": ["NYKAA"], "PAYTM": ["PAYTM"],
        "JIO": ["JIOFIN"], "ULTRATECH": ["ULTRACEMCO"], "DR REDDY": ["DRREDDY"], "DR REDDYS": ["DRREDDY"],
        "BANKNIFTY": ["NIFTY BANK"], "BANK NIFTY": ["NIFTY BANK"], "NIFTY": ["NIFTY 50"], "NIFTY50": ["NIFTY 50"],
        "FINNIFTY": ["NIFTY FIN SERVICE"], "MIDCPNIFTY": ["NIFTY MID SELECT"], "VIX": ["INDIA VIX"],
    },
    "US": {
        "GOOGLE": ["GOOGL", "GOOG"], "ALPHABET": ["GOOGL", "GOOG"], "FACEBOOK": ["META"], "BERKSHIRE": ["BRK-B", "BRK-A"],
        "COKE": ["KO"], "COCA COLA": ["KO"], "JP MORGAN": ["JPM"], "JPMORGAN": ["JPM"], "DISNEY": ["DIS"], "J&J": ["JNJ"],
        "P&G": ["PG"], "AT&T": ["T"], "TSMC": ["TSM"], "LILLY": ["LLY"], "PEPSI": ["PEP"], "BOFA": ["BAC"],
        "BANK OF AMERICA": ["BAC"], "EXXON": ["XOM"], "WALMART": ["WMT"], "MCDONALDS": ["MCD"],
    },
}


def tokens(text: str | None) -> list[str]:
    """The words of a name or of what's typed, for matching: lower case, accents and punctuation gone ("Dr. Reddy's"
    → dr reddys), without its legal form. A name made only of such words keeps them ("The Company")."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"['’`]", "", t).replace(".", " ").replace("-", " ").replace("/", " ")
    words = _TOKEN.findall(t)
    kept = [w for w in words if w not in LEGAL]
    if len(kept) > 1 and kept[-1] in CUT_LIMITED:
        kept.pop()
    return kept or words


def compact(text: str | None) -> str:
    return "".join(tokens(text))


def _sym_key(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "").upper())


def _osa1(a: str, b: str) -> bool:
    """Whether two different words are one edit apart: a letter added, dropped or changed, or two neighbours swapped."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 1 or a == b:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _deletes(w: str) -> set[str]:
    return {w[:i] + w[i + 1:] for i in range(len(w))}


class NameIndex:
    """An index over `rows` (any dicts). `symbol(row)` and `name(row)` say what each is; `names(row)` gives other
    names to match (the exchange's full name beside the broker's short one); `codes(row)` other exact identifiers
    (BSE code, ISIN); `rank(row)` orders kinds within a group (lower first); `boost` is a set of well-known symbols
    that come first among equals; `aliases` maps a short name to the symbols it means."""

    def __init__(self, rows: list[dict], symbol=lambda r: r["symbol"], name=lambda r: r.get("name"),
                 names=lambda r: (), codes=lambda r: (), rank=lambda r: 0, boost: set | None = None,
                 aliases: dict[str, list[str]] | None = None):
        self.rows = rows
        boost = {s.upper() for s in boost or ()}
        self._sym, self._key, self._words = [], [], []
        exact, named, postings = {}, {}, {}
        for i, r in enumerate(rows):
            sym = _sym_key(symbol(r))
            all_names = [n for n in (name(r), *names(r)) if n]
            words = sorted({w for n in all_names for w in tokens(n)})
            first = tokens(all_names[0]) if all_names else []
            self._sym.append(sym)
            self._words.append(words)
            # kind, well-known first, then fewer other words (set per query), then the name in order
            self._key.append((rank(r), 0 if sym in boost or sym.split("-")[0] in boost else 1, len(first), compact(all_names[0] if all_names else sym)))
            for k in {sym, sym.replace("-", "").replace(".", ""), *(_sym_key(c) for c in codes(r) if c)}:
                exact.setdefault(k, []).append(i)
            for n in all_names:
                named.setdefault(compact(n), []).append(i)
            for w in words:
                postings.setdefault(w, []).append(i)
        by_sym = {}
        for i, s in enumerate(self._sym):
            by_sym.setdefault(s, []).append(i)
        self._alias = {}
        for a, targets in (aliases or {}).items():
            hits = [i for t in targets for i in by_sym.get(_sym_key(t), [])]
            if hits:
                self._alias.setdefault(compact(a), []).extend(hits)
        self._exact, self._named, self._postings = exact, named, postings
        self._sym_sorted = sorted((s, i) for i, s in enumerate(self._sym))
        self._name_sorted = sorted({(n, i) for n, ids in named.items() for i in ids})
        self._alias_sorted = sorted({(a, i) for a, ids in self._alias.items() for i in ids})
        self._vocab = sorted(postings)
        self._del: dict[str, list[str]] = {}
        for w in self._vocab:
            if len(w) >= 4:
                for d in _deletes(w):
                    self._del.setdefault(d, []).append(w)

    # ---------- the pieces ----------
    def _prefix(self, sorted_pairs, p: str):
        j = bisect_left(sorted_pairs, (p,))
        while j < len(sorted_pairs) and sorted_pairs[j][0].startswith(p):
            yield sorted_pairs[j]
            j += 1

    def _word_hits(self, w: str, cut: bool = False) -> set[int]:
        """Rows with a word starting with `w`; with `cut`, also a word `w` starts with (the broker's list cuts names
        short: "Apollo Hospitals Enterprise" is "APOLLO HOSPITALS ENTER")."""
        out: set[int] = set()
        j = bisect_left(self._vocab, w)
        while j < len(self._vocab) and self._vocab[j].startswith(w):
            out.update(self._postings[self._vocab[j]])
            j += 1
        if cut:
            for k in range(3, len(w)):
                out.update(self._postings.get(w[:k], ()))
        return out

    def _close_words(self, w: str) -> set[str]:
        """Words in the index one typo from `w` (same first letter; a four-letter word only by a changed or swapped
        letter)."""
        if len(w) < 4:
            return set()
        cands = set(self._del.get(w, ()))
        for d in _deletes(w):
            if d in self._postings:
                cands.add(d)
            cands.update(self._del.get(d, ()))
        return {c for c in cands if c[0] == w[0] and (len(w) > 4 or len(c) == 4) and len(c) >= 4 and _osa1(w, c)}

    # ---------- search ----------
    def search(self, q: str, limit: int = 25, keep=None) -> list[tuple[int, dict]]:
        """The best `limit` rows for what's typed, each with its group (EXACT … CLOSE). `keep(row)` filters."""
        raw = str(q or "").strip()
        if not raw:
            return []
        qs, qw = _sym_key(raw), tokens(raw)
        qc = "".join(qw)
        best: dict[int, int] = {}

        def put(ids, tier):
            for i in ids:
                if best.get(i, NOT_FOUND) > tier:
                    best[i] = tier
        put(self._exact.get(qs, ()), EXACT)
        if ISIN.fullmatch(qs):                  # an ISIN is only ever an exact match
            return self._ordered(best, qw, limit, keep)
        if qc:
            put(self._alias.get(qc, ()), NAMED)
            put(self._named.get(qc, ()), NAMED)
        put((i for _, i in self._prefix(self._sym_sorted, qs)), SYMBOL)
        if qc:
            put((i for _, i in self._prefix(self._name_sorted, qc)), NAME)
            if len(qc) >= 3:                    # "zom" for Zomato; shorter would match half the short names
                put((i for _, i in self._prefix(self._alias_sorted, qc)), NAME)
        if qw and (len(qw) > 1 or len(qw[0]) >= 2):
            sets = [self._word_hits(w, cut=n > 0) for n, w in enumerate(qw)]   # the first word typed in full
            strict = set.intersection(*sorted(sets, key=len))
            put(strict, WORDS)
            if len(best) < limit:
                loose = []
                for w, s in zip(qw, sets):
                    near = set()
                    for c in self._close_words(w):
                        near.update(self._postings[c])
                    loose.append(s | near)
                put(set.intersection(*sorted(loose, key=len)) - strict, CLOSE)
        return self._ordered(best, qw, limit, keep)

    def _ordered(self, best: dict[int, int], qw: list[str], limit: int, keep) -> list[tuple[int, dict]]:
        def key(i):
            t, (kind, known, nwords, name) = best[i], self._key[i]
            tie = len(self._sym[i]) if t == SYMBOL else max(0, nwords - len(qw))
            return (t, kind, known, tie, name, self._sym[i])
        out = []
        for i in sorted(best, key=key):
            if keep is None or keep(self.rows[i]):
                out.append((best[i], self.rows[i]))
                if len(out) >= limit:
                    break
        return out


def tier_of(q: str, symbol: str, name: str | None, market: str | None = None) -> int:
    """How well one row from elsewhere (a search answer from outside) matches what's typed: its group, or NOT_FOUND."""
    got = NameIndex([{"symbol": symbol or "", "name": name}], aliases=ALIASES.get(market or "", {})).search(q, 1)
    return got[0][0] if got else NOT_FOUND
