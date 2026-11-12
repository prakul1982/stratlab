"""Customer and supplier links named in filings (the customer and supplier map, MVP): the rules that find them in a
document's text, the check that keeps one, and the AI's job when the rules are unsure.

Two kinds of document, read as they are filed:
- an Indian order-win filing (the exchange's "order" category): the filer is the supplier, the buyer it names is the
  customer ("received an order worth Rs 450 crore from Bharat Electronics Limited");
- a US annual report's Business and Risk factors parts: customer concentration ("Walmart Inc. accounted for 21% of
  our net sales") and sole or main suppliers ("we rely on TSMC to manufacture our wafers").

A link is kept only when its quote is word for word in the document and holds the counterparty's name. Prospects ("in
talks with", "emerged as the lowest bidder"), past or lost customers ("no longer", "terminated"), hypotheticals ("if
Walmart were to"), questions and analysts' words give no link, and an unnamed customer ("one customer", "Customer A")
is never guessed. Facts as filed: nothing here says what a link means for anyone."""
import json
import re

# ---------- text ----------
_QUOTES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " ", "\u2013": "-", "\u2014": "-", "\u200b": " ",
                         "\u2022": ". ", "\u25cf": ". ", "\u25aa": ". "})


def plain(s: str | None) -> str:
    """Spaces and curly quotes made plain, so a quote and its document compare as text."""
    return re.sub(r"\s+", " ", str(s or "").translate(_QUOTES)).strip()


def verbatim(quote: str | None, doc: str | None) -> bool:
    """Whether the quote is in the document word for word (only spacing and curly quotes may differ)."""
    q = plain(quote)
    return len(q) >= 12 and q in plain(doc)


def names_in(name: str | None, quote: str | None) -> bool:
    """Whether the counterparty's name, as the link gives it, is inside the quote."""
    n = plain(name).lower()
    return len(n) >= 2 and n in plain(quote).lower()


def kept(link: dict, doc: str) -> bool:
    """The rule every stored link passes: its quote is in the document and names the counterparty."""
    return verbatim(link.get("quote"), doc) and names_in(link.get("counterparty"), link.get("quote"))


_ABBR = re.compile(r"(?:\b(?:Ltd|Inc|Co|Corp|Pvt|Nos?|Rs|Mr|Ms|Dr|St|M/s|vs|viz|approx|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\."
                   r"|\b(?:[A-Z]\.)+)$")


def sentences(text: str) -> list[str]:
    """The document's sentences, without splitting at "Ltd.", "Inc.", "Rs." or "U.S."."""
    parts = re.split(r"(?<=[.;!?])\s+(?=[\"'(]?[A-Z0-9])", plain(text))
    out: list[str] = []
    for p in parts:
        if out and _ABBR.search(out[-1]):
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    return [s for s in out if s]


# ---------- names ----------
_TOKEN = re.compile(r"\((?:[^()]{1,40})\)|[A-Za-z0-9][\w&.'/-]*|&")
CONNECT = {"of", "&", "de", "du"}           # inside a name only between two capitalised words
CONNECT_IN = CONNECT | {"and"}                     # an Indian buyer's name can hold "and" ("Ministry of Road Transport and Highways")
# capitalised words that start a sentence or a phrase, not a name
NOT_NAMES = {"we", "our", "its", "it", "this", "these", "that", "such", "each", "one", "two", "three", "certain", "some", "various",
             "company", "the company", "customer", "customers", "client", "clients", "supplier", "suppliers", "during", "in", "for",
             "fiscal", "fy", "year", "years", "sales", "revenue", "revenues", "net", "total", "no", "none", "any", "all", "other", "others",
             "company's", "governments", "order", "orders", "contract", "contracts", "letter", "award", "exchange",
             "board", "director", "directors", "management", "limited", "ltd", "inc", "january", "february", "march", "april", "may",
             "june", "july", "august", "september", "october", "november", "december", "however", "additionally", "also", "as",
             "approximately", "although", "while", "if", "after", "before", "since", "following", "pursuant", "further"}
UNNAMED = re.compile(r"^(?:customer|client|vendor|supplier)\s+[A-Z0-9]\b|^(?:a|an|one|two|three|several|certain|some|its|our|their|leading|"
                     r"reputed|large|major|domestic|international|overseas|global|foreign|private|public|prestigious|renowned)\b", re.I)
WHOLE_NOT = {"u.s.", "us", "government", "united states", "india", "the government"}     # never a name on their own
BAD_NAME = re.compile(r"^(?:FY|CY|Q[1-4]|H[12])?['\s]?\d|^Item\b|^Note\b|^Part\b", re.I)
_ENDS = {"ltd.", "inc.", "co.", "corp.", "pvt.", "l.p.", "n.v.", "s.a.", "plc."}


def _cap(t: str) -> bool:
    return t[0].isupper() or t[0].isdigit() and any(c.isupper() for c in t)


def take_name(s: str, india: bool = False) -> str | None:
    """The name at the start of `s` ("Bharat Electronics Limited for supply of ..." → "Bharat Electronics Limited"): capitalised
    words, with "of" or "&" between two of them and a short form in brackets; "M/s." and "the" in front are dropped. None when
    the words there are not a name (lower case, or a word such as "Customer A" or "a leading OEM")."""
    s = plain(s)
    s = re.sub(r"^(?:M/s\.?|Messrs\.?)\s*", "", s, flags=re.I)
    s = re.sub(r"^the\s+", "", s, flags=re.I)
    if not s or UNNAMED.match(s):
        return None
    conn = CONNECT_IN if india else CONNECT
    got: list[str] = []
    end = 0
    for m in _TOKEN.finditer(s[:220]):
        gap = s[end:m.start()]
        if got and gap.strip():          # a comma or other mark between words ends the name
            break
        t = m.group(0)
        if t.startswith("("):
            if not got:
                break
            got.append(t)
        elif t.lower() == "and" and got and got[-1].lower().rstrip(".") in {"limited", "ltd", "inc", "corporation", "company"}:
            break                         # "Power Grid Corporation of India Limited and NTPC Limited": two names
        elif _cap(t) or (got and t.lower() in conn):
            got.append(t)
        else:
            break
        end = m.end()
        if t.endswith(".") and t.lower() not in _ENDS and not re.fullmatch(r"(?:[A-Z]\.)+", t):
            break                         # the sentence ends here
    while got and (got[-1].lower() in conn or got[-1].lower() in {"the", "a"}):
        got.pop()
    if not got:
        return None
    name = " ".join(got)
    if name.endswith(".") and got[-1].lower() not in _ENDS and not re.fullmatch(r"(?:[A-Z]\.)+", got[-1]):
        name = name[:-1]
    first = got[0].lower().rstrip(".,")
    if (first in NOT_NAMES or name.lower() in NOT_NAMES or name.lower() in WHOLE_NOT or len(name) < 2 or UNNAMED.match(name)
            or BAD_NAME.match(name)):
        return None
    return name


def name_list(s: str, india: bool = False) -> list[str]:
    """Names in a list ("Walmart, Target and Costco"): each piece that is a name from start to end."""
    out = []
    first = take_name(s, india)
    if not first:
        return out
    out.append(first)
    rest = plain(s)
    rest = rest[rest.find(first) + len(first):] if first in rest else ""
    while len(out) < 6:
        m = re.match(r"\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s*&\s+)", rest)
        if not m:
            break
        nxt = take_name(rest[m.end():], india=False)
        if not nxt:
            break
        out.append(nxt)
        rest = rest[m.end():]
        rest = rest[rest.find(nxt) + len(nxt):]
    return out


def names_found(s: str) -> list[str]:
    """Every name in some words, in order, none inside another ("The Home Depot" once, not "Depot" again)."""
    s = plain(s)
    out, covered = [], 0
    for m in re.finditer(r"(?:^|(?<=[\s,(\"']))[A-Z0-9]", s):
        if m.start() < covered:
            continue
        n = take_name(s[m.start():])
        run = re.match(r"[A-Z0-9][\w&.'/-]*(?:\s+(?:of\s+|&\s+|de\s+)?[A-Z0-9][\w&.'/-]*)*", s[m.start():])
        covered = m.start() + (run.end() if run else 1)
        if n:
            at = s.find(n, m.start())
            out.append(n)
            covered = max(covered, (at if at >= 0 else m.start()) + len(n))
    return out


def name_before(s: str) -> str | None:
    """The last name in the words before a verb ("During fiscal 2025, sales to Walmart Inc. and its affiliates" → "Walmart Inc.")."""
    got = names_found(s)
    return got[-1] if got else None


# ---------- what gives no link ----------
PROSPECT = re.compile(r"\b(?:in (?:talks|discussions|negotiations) with|potential (?:customer|client|order)s?|prospective|"
                      r"expects? to (?:receive|win|sign|secure)|expected to (?:receive|win|sign|secure)|lowest bidder|\bL-?1\b|emerged as|"
                      r"bid(?:s|ding)? (?:for|submitted)|tender(?:s)? (?:floated|issued)|memorandum of understanding|\bMoU\b|"
                      r"letter of intent|\bLoI\b|non-binding|may (?:award|place|become)|pipeline|evaluating|exploring)", re.I)
PAST = re.compile(r"\b(?:no longer|lost|former(?:ly)?|ceased|terminat\w*|cancel\w*|discontinu\w*|short[- ]clos\w*|did not renew|"
                  r"not (?:be )?renewed|exited|wound down|withdrawn)\b", re.I)
HYPO_LEAD = re.compile(r"^(?:if|should|were|in the event|assuming|suppose|unless|although no|no single)\b|\b(?:loss of|if|could|would|might)\b", re.I)
ASIDE = re.compile(r"\banalysts?\b|\?", re.I)
# an "order" in the legal sense (a court's or a regulator's), not a customer's
LEGAL = re.compile(r"\b(?:court|tribunal|NCLT|NCLAT|SEBI|commissioner|penalty|show cause|demand notice|GST|income tax|arbitra\w*|"
                   r"adjudicat\w*|appellate)\b", re.I)


def ruled_out(sentence: str, before_name: str = "") -> bool:
    """A sentence about a prospect, a past or lost relationship, a question or an analyst, or a hypothetical about the name."""
    return bool(PROSPECT.search(sentence) or PAST.search(sentence) or ASIDE.search(sentence) or HYPO_LEAD.search(before_name.strip()))


AMOUNT = re.compile(r"(?:Rs\.?|INR|₹)\s*[\d,]+(?:\.\d+)?\s*(?:crores?|cr\b\.?|lakhs?|million|billion|mn\b|bn\b)", re.I)
PCT = re.compile(r"(\d{1,2}(?:\.\d+)?)\s?(?:%|percent\b)")


def _link(counterparty, direction, basis, quote, share=None, amount=None, method="rule") -> dict:
    return {"counterparty": counterparty, "direction": direction, "basis": basis, "quote": quote, "share_pct": share,
            "amount": amount, "method": method}


# ---------- India: order wins ----------
ORDER_TRIGGERS = [
    re.compile(r"\b(?:orders?|contracts?|work orders?|purchase orders?|letter of (?:award|acceptance)|LoA|LOA|award)\b[^.;]{0,200}?\b(?:from|by)\s+", re.I),
    re.compile(r"\b(?:received|secured|bagged|won|awarded|bags|wins|secures|receives)\b[^.;]{0,160}?\bfrom\s+", re.I),
    re.compile(r"\b(?:signed|entered into|executed)\b[^.;]{0,60}?\b(?:contracts?|agreements?|orders?)\b[^.;]{0,40}?\bwith\s+", re.I),
]
ORDER_WORDS = re.compile(r"\b(?:orders?|contracts?|letter of (?:award|acceptance)|LoA|work order|award(?:ed)?|bagg(?:ed|ing))\b", re.I)


def extract_order(text: str, filer: str | None = None) -> tuple[list[dict], bool]:
    """Customers an order-win filing names: (links, unsure). `unsure` is True when the filing talks of an order and names no
    one the rules could read (and doesn't plainly leave the buyer unnamed): then the AI may read it."""
    links: list[dict] = []
    saw_order, decided = False, False
    filer_words = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", filer or "")} - {"limited", "ltd", "india", "the"}
    for s in sentences(text):
        if not ORDER_WORDS.search(s):
            continue
        saw_order = True
        if ruled_out(s) or LEGAL.search(s):
            decided = True
            continue
        for rx in ORDER_TRIGGERS:
            for m in rx.finditer(s):
                after = s[m.end():]
                if UNNAMED.match(re.sub(r"^the\s+", "", after, flags=re.I)):
                    decided = True                 # "from a leading global OEM": the buyer is not named
                    continue
                for name in name_list(after, india=True):
                    words = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", name)} - {"limited", "ltd", "india", "the"}
                    if filer_words and words and words <= filer_words:
                        continue                   # the filer itself ("XYZ Limited has received ... by XYZ")
                    if HYPO_LEAD.search(s[:m.start()]):
                        continue
                    amt = AMOUNT.search(s)
                    links.append(_link(name, "customer", "order_win", s, amount=amt.group(0) if amt else None))
                    decided = True
    out = _dedupe(links, text)
    return out, saw_order and not decided and not out


# ---------- US: annual report ----------
CONC = re.compile(r"\b(?:accounted for|represented|comprised|constituted|made up|were|was)\b[^.;]{0,60}?(?P<pct>\d{1,2}(?:\.\d+)?)\s?(?:%|percent\b)"
                  r"[^.;]{0,40}?\b(?:of\s+)?(?:our\s+|the company's\s+|its\s+|total\s+|consolidated\s+|net\s+|worldwide\s+)*"
                  r"(?:net\s+)?(?:sales|revenues?|net revenues?|product revenues?)\b", re.I)
CONC2 = re.compile(r"\b(?:accounted for|represented|comprised)\s+(?:our\s+|the company's\s+|its\s+|total\s+|consolidated\s+)*(?:net\s+)?"
                   r"(?:sales|revenues?)\s+of\s+(?:approximately\s+|about\s+)?(?P<pct>\d{1,2}(?:\.\d+)?)\s?%", re.I)
CONC3 = re.compile(r"\b(?:net sales|sales|revenues?|net revenues?)\s+(?:to|from)\s+(?P<who>[^.;%]{2,140}?)\s*,?\s+(?:were|was|accounted for|"
                   r"represented|comprised|totaled|totalled)\s+(?:approximately\s+|about\s+|roughly\s+)?(?P<pct>\d{1,2}(?:\.\d+)?)\s?(?:%|percent\b)", re.I)
CUST_NAMED = [re.compile(r"\b(?:largest|biggest|principal|primary|most significant|major)\s+customers?(?:\s+in\s+(?:fiscal\s+)?\d{4})?\s*"
                         r"(?:,|is|are|include|includes|were|was)\s+(?:our\s+(?:reseller|distributor|partner)\s+)?", re.I)]
CUST_BEFORE = re.compile(r"\s+(?:is|was|remains|has been)\s+(?:our|the company's|its)\s+(?:largest|biggest|principal|primary|most significant|single largest)\s+customer\b", re.I)
SUP_AFTER = [
    re.compile(r"\b(?:we|the company)\s+(?:currently\s+)?(?:rely|relies|depend|depends)\s+(?:primarily\s+|heavily\s+|substantially\s+|solely\s+|"
               r"exclusively\s+|significantly\s+|entirely\s+)?(?:up)?on\s+", re.I),
    re.compile(r"\b(?:purchase|purchases|source|sources|obtain|obtains|buy|buys|procure|procures)\s+(?:substantially all|all|most|the majority|"
               r"a majority|a significant portion|a substantial portion|nearly all)\s+of\s+(?:our|its|the company's)\s+[\w\s,-]{1,60}?\s+from\s+", re.I),
    re.compile(r"\b(?:sole[- ]source|key|principal|major|main|primary)\s+suppliers?\s+(?:include|includes|are|is)\s+", re.I),
    re.compile(r"\b(?:we|the company)\s+(?:use|uses|utilize|utilizes|engage|engages)\s+(?:third[- ]party\s+)?(?:foundries|contract manufacturers|"
               r"suppliers|manufacturers|subcontractors)[^.;]{0,40}?\bsuch as\s+", re.I),
    re.compile(r"\b(?:manufactured|produced|supplied|made|fabricated)\s+(?:exclusively|solely|only|entirely|primarily)\s+by\s+", re.I),
]
SUP_BY = re.compile(r"\b(?:manufactured|produced|supplied|made|fabricated)\s+by\s+", re.I)      # only beside "sole supplier" and the like
SUP_BEFORE = re.compile(r"\s+(?:is|was|remains|has been)\s+(?:currently\s+|now\s+|presently\s+)?(?:our|the company's|its|the)\s+(?:sole|single|only|primary|principal|largest|main|"
                        r"major|exclusive)\s+(?:supplier|source|manufacturer|provider|foundry|vendor)\b", re.I)
_CLAUSE = re.compile(r"[;:]")


def _clause_start(s: str, at: int) -> int:
    cut = [m.end() for m in _CLAUSE.finditer(s[:at])]
    return cut[-1] if cut else 0


GEO = re.compile(r"^(?:the\s+)?(?:U\.?S\.?|United States|America|Americas|North America|South America|Latin America|Central America|Europe|EMEA|"
                 r"APAC|Asia|Asia Pacific|Far East|Middle East|Africa|Canada|Mexico|China|Japan|India|Australia|United Kingdom|UK|Germany|"
                 r"France|Korea|South Korea|Taiwan|Brazil|International|Domestic)$", re.I)
_APPOSITION = re.compile(r",\s*(?:which|who|our|its|the|a|an|including|together|collectively|in the aggregate|and its)\b[^,]*,\s*$", re.I)
_TRAIL = re.compile(r"(?:\s*,?\s*(?:who|which|that)|\s+(?:and|together with) (?:its|their) (?:affiliates|subsidiaries)|\s+collectively|\s+combined"
                    r"|(?:,\s*|\s+)(?:Inc|LLC|Ltd|Corp|Co|plc|L\.P|N\.V|S\.A|Limited)\.?)\s*,?\s*$", re.I)


def subject_names(words: str) -> list[str]:
    """The name(s) a clause ends with, before its verb: "Walmart, our largest customer," → [Walmart]; "Nike, Inc. ("Nike"),
    Skechers ... and Crocs, Inc. ("Crocs")" → three names; "two customers" → []. A name a clause holds elsewhere (a place, a
    brand, a company acquired) is not its subject."""
    r = plain(words).rstrip()
    short = None
    for _ in range(6):
        before = r
        m = re.search(r"\s*\(\s*(?:\"([^\"]{2,40})\"|'([^']{2,40})'|[^()]*)\s*\)\s*,?$", r)
        if m:
            short = short or m.group(1) or m.group(2)
            r = r[:m.start()].rstrip() + ("," if r.rstrip().endswith(",") else "")
        r = _APPOSITION.sub("", r).rstrip()
        r = _TRAIL.sub("", r).rstrip()
        if r == before:
            break
    r = r.rstrip(" ,")
    found = names_found(r)
    if not found:
        return []
    last = found[-1]
    if not r.rstrip(" .\"'").endswith(last.rstrip(".")):
        return []
    if short and short in last and not last.startswith(short):
        last = last[last.index(short):]          # "Encapsulation Catalent Pharma Solutions ("Catalent")": the name starts at its short form
    out = [last]
    tail = r[:r.rfind(last.split()[0])].rstrip()
    if len(found) > 1 and re.search(r"(?:,|\band\b|&)$", tail):
        out = [n for n in found if n != last][-3:] + out
    return [n for n in out if not GEO.match(n)]


def extract_annual(text: str, filer: str | None = None) -> tuple[list[dict], list[str]]:
    """Customers and suppliers a US annual report names: (links, unsure sentences). An unsure sentence gives a share of sales for
    more than one company at once ("respectively"), or names as a share of sales a company the report also calls a supplier or
    a brand (a retailer's vendors: "Nike accounted for 24% of our net sales")."""
    links: list[dict] = []
    unsure: list[str] = []
    sents = [x for x in sentences(text) if len(x) <= 900]
    vendorish = [x for x in sents if re.search(r"\b(?:suppliers?|vendors?|brands?|manufacturers?)\b", x, re.I) and not re.search(r"\bcustomers?\b", x, re.I)]
    for s in sents:
        low = s.lower()
        m = CONC3.search(s) or CONC.search(s) or CONC2.search(s)
        if m:
            start = m.start("who") if m.re is CONC3 else m.start()
            stop = m.end("who") if m.re is CONC3 else m.start()
            region = s[_clause_start(s, start):stop]
            if re.search(r"\bcustomers? in (?!(?:fiscal\s+)?\d{4})|\bsales (?:in|outside|of|distributed)\b|\boutside\b|\bsegment\b(?!'s net)", region, re.I):
                m = None                          # a place's or a product's share, not a customer's
        if m:
            hit = re.search(r"\b(?:net\s+)?(?:sales|revenues?)\s+(?:to|from)\s+", region, re.I) if m.re is not CONC3 else True
            if m.re is CONC3:
                one = take_name(region)
                names = [one] if one else []
            elif hit:
                one = take_name(region[hit.end():])
                names = [one] if one else []
            else:
                names = subject_names(region)
            if len(names) > 1:
                if "respectively" in low and not ruled_out(s, region):
                    unsure.append(s)
                continue                          # a share several companies make together: not one company's
            if names:
                name = names[0]
                if ruled_out(s, region[:region.find(name)] if name in region else region):
                    continue
                if any(name.lower() in v.lower() for v in vendorish):
                    unsure.append(s)              # the report calls it a supplier or a brand too: the AI reads it
                    continue
                links.append(_link(name, "customer", "concentration", s, share=float(m.group("pct"))))
                continue
        b = CUST_BEFORE.search(s)
        if b:
            before = s[_clause_start(s, b.start()):b.start()]
            got = subject_names(before)
            if len(got) == 1 and not ruled_out(s, before[:before.find(got[0])] if got[0] in before else before):
                links.append(_link(got[0], "customer", "customer_named", s))
            continue
        for rx in CUST_NAMED:
            for mm in rx.finditer(s):
                if ruled_out(s, s[:mm.start()]):
                    continue
                for name in name_list(s[mm.end():]):
                    links.append(_link(name, "customer", "customer_named", s))
        prev = 0
        for b in SUP_BEFORE.finditer(s):
            before = s[max(prev, _clause_start(s, b.start())):b.start()]
            prev = b.end()
            got = subject_names(before)
            if len(got) == 1 and not ruled_out(s, before[:before.find(got[0])] if got[0] in before else before):
                links.append(_link(got[0], "supplier", "supplier_named", s))
        sole = re.search(r"\b(?:sole|single|exclusive|only)\s+(?:supplier|source|manufacturer)", s, re.I)
        for rx in SUP_AFTER + ([SUP_BY] if sole else []):
            for mm in rx.finditer(s):
                if ruled_out(s, s[_clause_start(s, mm.start()):mm.start()]):
                    continue
                for name in name_list(s[mm.end():]):
                    links.append(_link(name, "supplier", "supplier_named", s))
    if filer:
        own = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", filer)} - {"inc", "corp", "corporation", "company", "the"}
        links = [x for x in links if not ({w.lower() for w in re.findall(r"[A-Za-z]{3,}", x["counterparty"])} - {"inc", "corp", "corporation", "company", "the"} <= own)]
    return _dedupe(links, text), unsure[:8]


def _dedupe(links: list[dict], doc: str) -> list[dict]:
    """Each counterparty once per direction (the first quote), and only links that pass `kept`."""
    out, seen = [], set()
    for x in links:
        key = (x["direction"], plain(x["counterparty"]).lower())
        if key in seen or not kept(x, doc):
            continue
        seen.add(key)
        out.append(x)
    return out


# ---------- the AI, when the rules are unsure ----------
AI_SYSTEM = (
    "You read a company's filing and list the customers and suppliers it NAMES. Answer only with JSON: "
    '{"links":[{"counterparty":"name exactly as written","direction":"customer|supplier","current":true,"quote":"one sentence copied word for word"}]}. '
    "Rules: only relationships the company states as current; leave out prospects (in talks, bids, lowest bidder, MoU), past or lost "
    "customers, competitors, analysts' names, hypotheticals (if, could, would) and unnamed customers (one customer, Customer A). "
    "The quote must be copied exactly from the text and contain the name. No link: {\"links\":[]}.")


def from_ai(reply: str, doc: str, basis: str) -> list[dict]:
    """The AI's links that pass the same checks as the rules' own: current, a word-for-word quote with the name in it, and
    not a prospect, a past customer, a question or a hypothetical."""
    try:
        data = json.loads(reply)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", str(reply or ""), re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except ValueError:
            data = {}
    out = []
    for x in (data.get("links") if isinstance(data, dict) else None) or []:
        if not isinstance(x, dict) or x.get("current") is False:
            continue
        name, quote, direction = plain(x.get("counterparty")), plain(x.get("quote")), x.get("direction")
        if direction not in ("customer", "supplier") or not name or UNNAMED.match(name) or name.lower() in NOT_NAMES:
            continue
        before = quote[:quote.lower().find(name.lower())] if name.lower() in quote.lower() else quote
        if ruled_out(quote, before):
            continue
        pct = PCT.search(quote) if basis == "concentration" else None
        amt = AMOUNT.search(quote) if basis == "order_win" else None
        b = basis if direction == "customer" else "supplier_named"
        out.append(_link(name, direction, b, quote, share=float(pct.group(1)) if pct else None,
                         amount=amt.group(0) if amt else None, method="ai"))
    return _dedupe(out, doc)
